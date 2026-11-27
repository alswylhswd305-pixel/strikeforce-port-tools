# Busy-spin location: existing log options, and one minimal new hook (log-only)

The watchdog reports "where it spins" from what the runtime can already log. None of these changes what the game does; two of them cost a little time (noted).

## Existing (use these first)
| Option | What it gives | Format the checker reads | Cost |
|---|---|---|---|
| `SF_HLE_LRLOG=1` (already in the VOICEDIAG1786 launcher), `SF_HLE_LRLOG_DUMP=<s>` (default 20) | cumulative calls per (import NID, caller lr, guest tid), dumped every N s → calls/s between two dumps = the polling loop's call sites | `[hle-lrc] dump=N t=ms pairs=P` + `[hle-lrc] N 0xNID 0xLR count ret=0x.. tid=T` | one hash insert per HLE call |
| automatic (no env) | an SPU that re-issues GETLLAR on one 128-byte line 4M times, with pc/lr and the line's first 16 bytes | `[spu-spin] img= pc= lr= GETLLAR ea= x4M; line: ...` | none |
| `SPU_PCSAMPLE=<secs>` | every N s: image, pc, lr and a few regs of every live SPU context | `[pcsample] slot= img= spu=0x pc=0x lr=0x ...` | one line per SPU per period |
| `PS3_SAMPLE=<ms>` (port main.cpp calls `ps3_sampler_start`, fix-log item 7) | host sampler: hottest guest functions (whole process) and samples per host thread (guest / ntdll / other); reports at 0.5, 1, 2, 4, 8 s, then every 10 s | `[samp]   12.3%  func_00058C38  (1234)`, `[samp] tid <host> guest= ntdll= other=` | suspends each thread briefly per sample; use 5-10 ms, not 1 |

Verified on Saud's 17:27 log, `voicediag1786_saud_20261127-172741_stderr.log` on the box:
- The [hle-lrc] deltas between dumps 17 and 18, inside the hang, show guest tid 17 at 65,283 calls/s each:
  - `sys_ppu_thread_get_id` at lr 0x53584;
  - `sys_lwmutex_lock` at lr 0x58C38;
  - `sys_lwmutex_unlock` at lr 0x58CE4.

  Calls at the same `sys_ppu_thread_get_id` call site (lr 0x53584, tid 17), per 20 s window:
  - up to dump 1: 16,458;
  - windows 2 and 3: 44,742 and 50,060;
  - window 4 (t=147708.97–147728.97 s, which contains the start of burst 1 at 147725.77): 217,315;
  - window 5 onward, to the end of the log: about 1.3M each.
- L76798 `[spu-spin] img=437063289 pc=0x0833C lr=0x07470 GETLLAR ea=0x11095F80`.
- `[pcsample]` and `[samp]` were not enabled in that run.

## Missing: per-thread hot PPU PC
`PS3_SAMPLE` ranks hot functions for the whole process. It does not say which host thread runs which function, so a spinning thread cannot be tied to its loop. Minimal new hook, gated by an env var and log-only:

**Env:** `SF_SAMP_TID=1` (needs `PS3_SAMPLE=<ms>`).

**Where:** `runtime/ppu/ppu_loader.cpp`, in `samp_thread()`.
- In both branches that already call `samp_tid2(tid, is_guest, nt)`: after `uint32_t g = samp_lookup(...)` (or `samp_stack_guest`), call `sf_tid_fn_hit(tid, g)`.
- In `samp_report()`, after the existing `[samp] tid` loop, call `sf_tid_fn_report()`.

```c
/* SF_SAMP_TID=1 (log-only): per host thread, the guest functions its samples landed in. */
enum { SF_TT = 64, SF_TF = 16 };
static DWORD    s_tt_id[SF_TT];
static uint32_t s_tt_fn[SF_TT][SF_TF];
static uint32_t s_tt_ct[SF_TT][SF_TF];
static uint32_t s_tt_n[SF_TT];
static void sf_tid_fn_hit(DWORD tid, uint32_t g) {
    static int en = -1; if (en < 0) en = getenv("SF_SAMP_TID") ? 1 : 0;
    if (!en || !g) return;
    int t = -1;
    for (int i = 0; i < SF_TT; i++) { if (s_tt_id[i] == tid) { t = i; break; } if (!s_tt_id[i]) { s_tt_id[i] = tid; t = i; break; } }
    if (t < 0) return;
    s_tt_n[t]++;
    int lo = 0;
    for (int k = 0; k < SF_TF; k++) {
        if (s_tt_fn[t][k] == g) { s_tt_ct[t][k]++; return; }
        if (s_tt_ct[t][k] < s_tt_ct[t][lo]) lo = k;
    }
    s_tt_fn[t][lo] = g; s_tt_ct[t][lo] = 1;          /* replace the coldest slot */
}
static void sf_tid_fn_report(void) {
    for (int t = 0; t < SF_TT && s_tt_id[t]; t++) {
        if (s_tt_n[t] < 20) continue;
        char b[600]; int p = snprintf(b, sizeof b, "[samp-tid] tid=%lu n=%u top:", (unsigned long)s_tt_id[t], s_tt_n[t]);
        for (int r = 0; r < 6; r++) {
            int bi = -1; uint32_t best = 0;
            for (int k = 0; k < SF_TF; k++) if (s_tt_ct[t][k] > best) { best = s_tt_ct[t][k]; bi = k; }
            if (bi < 0) break;
            p += snprintf(b + p, sizeof b - p, " %s%08X:%u", (s_tt_fn[t][bi] & 0x80000000u) ? "spu_LS_" : "func_", s_tt_fn[t][bi] & 0x7FFFFFFFu, best);
            s_tt_ct[t][bi] = 0;                        /* consume for the next rank and the next report */
        }
        s_tt_n[t] = 0;
        fprintf(stderr, "%s\n", b);
    }
}
```

**Thread-id map:** host ids appear in `[cellSpurs] ... tid=` and `[samp]`; guest ids appear in `[sfww]` and `[hle-lrc]`. Join them once per thread with one line, printed where the runtime starts a guest PPU thread (the host thread entry that already prints `[SYS] sys_ppu_thread_create`):

`[sf-tidmap] guest=%u host=%lu name="%s"`

The line is printed once per thread, gated by `SF_SAMP_TID=1`.

**Output** (the checker already reads `[samp-tid]`):
`[samp-tid] tid=42016 n=1890 top: func_00058C38:1201 func_00053584:402 ...`

# SF-RACE: log-only run spec for the gate freeze (voice records PPU/SPU race)
Author: عالم الفيزياء, 2026-11-27 (Asia/Kuwait). Test copy only. **No behaviour change**: every hook below only reads memory/registers and writes log text. Nothing is skipped, clamped, faked or re-ordered.
Checker: `race_check.py` (stdlib, same folder, `--selftest` passes). Analyzer for the older diag lines: `voice_freeze_analyzer.py`.

## 0. What this run must answer
1. **Q-A (assert):** which code is at LS 0x31C20 at the halt (EBOOT blob or flashATRAC.pic), which register the trap tests, and where that register's value came from (LS address, the DMA that filled it, its EA, time).
2. **Q-M (mask/snapshot mismatch):** in the pass before the halt, is a voice in snapshot group g (bitmap 0x111A2000) while its live mask (voice param +0x358, read by the 1168-byte GET at pc block 0x06BC0) lacks bit g? The mixer then allocates it on path 1 (no de-dup) once per such group, which is what doubles/triples the visits (see findings.md §3).
3. **Q-L (lost update, QA lead):** does a PPU store (tid 17 or any tid) land in [record+0x800, record+0x930) between the SPU's 2352-byte record GET (pc block 0x06BC0, lsa 0x3C180) and its 304-byte PUT back to record+0x800 (pc block 0x071EC)?
4. **Q-E (flag order):** does the SPU set 0x00DBA900 before its pass has issued its last record PUT (so tid 7 can run its per-tick update in parallel with the pass)?
5. **Q-V:** visits per pass and repeats (> 176 visits = ring overflow; >= 201 = page 408 = the table).

## 1. Env vars (one launcher; copy PLAY_Strikeforce_VOICEDIAG1786_PAD.bat to PLAY_Strikeforce_SFRACE.bat)
Keep everything the 1786 PAD launcher sets (incl. SPU_INTERP_UNLIFTED=1, PS3_DEV_FLASH, SF_VOICE_MON=1, SF_HLE_LRLOG=1). Add:

| Var | Value | Hook | New? |
|---|---|---|---|
| `SF_RACE` | `1` | master switch for all [sfrace*] hooks below | new |
| `SF_RACE_IMG` | `391227015` | only this SPU image is traced | new |
| `SF_RACE_RING` | `400000` | in-memory ring of records (no fprintf on the hot path); dumped on halt / first EF BLOCKED / exit | new |
| `SF_RACE_LOG` | `play_logs\sfrace_%PID%.log` | dump target of the ring (separate file, not stderr) | new |
| `SF_WW_RANGES` | `11103990:330F0,11136A80:67600,111A1780:880` | existing store watch: voice params, voice records, working table | existing (SF-DIAG 1786) |
| `SF_WW_MAX` | `0` | existing: 0 = no line cap (L3) | existing |
| `SF_WW_TO_RACE` | `1` | send [sfww] hits into the SF_RACE ring with the shared clock instead of stderr | new (2 lines in sf_ww_ranges_hit) |
| `SPU_DUMP_OVL` | `play_logs\ovl_sfrace,0x2FE90` | existing: writes every code body DMA'd to LS 0x2FE90 as `ovl_<EA>.bin` + `[spu-ovl-dump]` line with the source EA (answers Q-A source) | existing (spu_channels.c spu_ovl_dump) |
| `SPU_CALLTRACE` | `1` | existing on 1740_halt_diag: `[SPU-TRACE] halt` + `[SPU-HALT]` regs; check the string is in the exe, else rely on [sfrace-halt] | existing (maybe) |
| `PS3_FSLOG` | `1` | existing: `[fs] open` lines (Now Loading 5444/5443, Voice.bin, flashATRAC.pic) | existing |

Do NOT set PPU_WW_GUARD (it slowed run B to ~32 FPS and moved the timing). Do not set PS3RECOMP_SPU_PUT_WATCH in the same run (stderr volume); it is the fallback for a second run (`PS3RECOMP_SPU_PUT_WATCH=11387860`) if Q-A needs the writer of the zeroed table again.

## 2. Shared clock
Both sides must stamp with the same function. Add one header `runtime/sf_race_clock.h` (new, log-only):
```c
/* SF-RACE: one clock for PPU and SPU logs. Same QPC split formula as spu_host_ns(). */
#pragma once
#include <stdint.h>
#ifdef _WIN32
#include <windows.h>
static inline uint64_t sf_qpc_ns(void) {
    static LARGE_INTEGER f; LARGE_INTEGER c;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return (uint64_t)(c.QuadPart / f.QuadPart) * 1000000000ull
         + (uint64_t)(c.QuadPart % f.QuadPart) * 1000000000ull / (uint64_t)f.QuadPart;
}
#else
#include <time.h>
static inline uint64_t sf_qpc_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec; }
#endif
```

## 3. The ring (new file `runtime/sf_race.c`, log-only)
Fixed-size records, one atomic index, formatting only at dump time, so the hot path costs a hash and a memcpy of <= 64 bytes.
```c
#include "sf_race_clock.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { SFR_DMA = 1, SFR_WW = 2, SFR_EF = 3, SFR_HALT = 4 };
typedef struct { uint64_t q, h, pre, sub; uint32_t kind, img, spu, pc, cmd, ea, lsa, size, tag, tid, fn, lr, old_, new_, w, m358;
                 uint8_t d[256]; uint32_t dn; } sfr_rec;
static sfr_rec* s_ring; static uint32_t s_cap; static atomic_uint s_pos; static int s_on = -1; static atomic_int s_dumped;
int sf_race_on(void) {
    if (s_on < 0) { const char* e = getenv("SF_RACE"); s_on = e && *e == '1';
        if (s_on) { const char* r = getenv("SF_RACE_RING"); s_cap = r ? (uint32_t)atoi(r) : 400000u;
                    s_ring = (sfr_rec*)calloc(s_cap, sizeof(sfr_rec)); if (!s_ring) s_on = 0; } }
    return s_on; }
sfr_rec* sf_race_slot(void) { uint32_t i = atomic_fetch_add(&s_pos, 1); sfr_rec* r = &s_ring[i % s_cap]; memset(r, 0, sizeof *r); r->q = sf_qpc_ns(); return r; }
uint64_t sf_fnv(const uint8_t* p, uint32_t n) { uint64_t h = 1469598103934665603ull; while (n--) { h ^= *p++; h *= 1099511628211ull; } return h; }
void sf_race_dump(const char* why) {
    if (!sf_race_on() || atomic_exchange(&s_dumped, 1)) return;     /* dump once */
    const char* path = getenv("SF_RACE_LOG"); FILE* f = path ? fopen(path, "w") : stderr; if (!f) f = stderr;
    uint32_t end = atomic_load(&s_pos), beg = end > s_cap ? end - s_cap : 0;
    fprintf(f, "[sfrace-dump] why=%s records=%u..%u\n", why, beg, end);
    for (uint32_t i = beg; i < end; i++) { sfr_rec* r = &s_ring[i % s_cap];
        if (r->kind == SFR_DMA) {
            fprintf(f, "[sfrace] q=%llu img=%u spu=%u pc=0x%05X dir=%s ea=0x%08X lsa=0x%05X size=%u tag=%u h=%016llx",
                (unsigned long long)r->q, r->img, r->spu, r->pc, (r->cmd & 0x01) ? "GET" : "PUT", r->ea, r->lsa, r->size, r->tag, (unsigned long long)r->h);
            if (r->pre) fprintf(f, " pre=%016llx", (unsigned long long)r->pre);
            if (r->sub) fprintf(f, " sub=%016llx", (unsigned long long)r->sub);
            if (r->m358 != 0xFFFFFFFFu) fprintf(f, " m358=%08X", r->m358);
            if (r->dn) { fputs(" d=", f); for (uint32_t k = 0; k < r->dn; k++) fprintf(f, "%02x", r->d[k]); }
            fputc('\n', f);
        } else if (r->kind == SFR_WW)
            fprintf(f, "[sfww] r9 0x%08X %X->%X w%u fn=0x%08X lr=0x%08X tid=%u t=%llu q=%llu ch:\n", r->ea, r->old_, r->new_, r->w, r->fn, r->lr, r->tid,
                    (unsigned long long)(r->q / 1000000ull), (unsigned long long)r->q);
        else if (r->kind == SFR_EF)
            fprintf(f, "[sfrace-ef] q=%llu who=%s flag=0x%08X bits=0x%04X tid=%u\n", (unsigned long long)r->q, r->cmd ? "PPU-WAKE" : "SPU", r->ea, r->old_, r->tid);
        else if (r->kind == SFR_HALT)
            fprintf(f, "%s\n", (const char*)r->d);
    }
    if (f != stderr) fclose(f); }
```
(`r->cmd` is set to 1 for GET / 0 for PUT by the SPU hook with the runtime's own `mfc_is_get()`, so the dump never decodes raw MFC opcodes. `SF_RACE_IMG_ID` below = `atoi(getenv("SF_RACE_IMG"))`, cached once in a static.)

## 4. SPU hooks: `runtime/spu/spu_channels.c`, function `spu_wrch()`
Placement: in the `if (channel_is_mfc(channel))` block, around the existing `mfc_channel_write(...)` / `putinputs_after_cmd(ctx, v)` lines (clothv2/spu_channels.c.orig ~L1235-1241; our DMA completes synchronously inside `mfc_channel_write`, so after it returns the GET data is in LS and the PUT data is in guest memory).
```c
/* SF-RACE (log-only): which EAs to trace */
static int sfr_ea_watched(uint32_t ea, uint32_t n) {
    return (ea < 0x11136A80u + 180u*0x930u && ea + n > 0x11103990u)      /* voice params + records */
        || (ea < 0x111A2880u && ea + n > 0x111A2000u)                    /* snapshot bitmap + counts */
        || (ea < 0x11357580u && ea + n > 0x111EF580u && n == 4096u)      /* 4KB ring PUTs (page = (ea-0x111EF580)/4096) */
        || (ea < 0x11388580u && ea + n > 0x11357580u)                    /* past the ring end, incl. table 0x11387860 */
        || (ea < 0x11387860u + 288u && ea + n > 0x11387860u); }
/* before mfc_channel_write (needs the guest bytes BEFORE a PUT) */
uint64_t sfr_pre = 0;
int sfr_hit = 0;
if (channel == MFC_Cmd && sf_race_on() && ctx->image_id == SF_RACE_IMG_ID /* atoi(getenv("SF_RACE_IMG")) cached */) {
    uint32_t ea = ctx->mfc_eal, n = ctx->mfc_size;
    if (!mfc_is_list(v) && n && n <= 0x4000u && sfr_ea_watched(ea, n)) { sfr_hit = 1;
        if (!mfc_is_get(v)) sfr_pre = sf_fnv(vm_base + ea, n); } }
mfc_channel_write(mfc_for(ctx), ctx, channel, v);          /* existing line, unchanged */
if (sfr_hit) {
    sfr_rec* r = sf_race_slot();
    uint32_t ea = ctx->mfc_eal, n = ctx->mfc_size, lsa = ctx->mfc_lsa & SPU_LS_MASK;
    r->kind = SFR_DMA; r->img = ctx->image_id; r->spu = (uint32_t)(uintptr_t)ctx & 0xFFFFu; r->pc = ctx->pc & SPU_LS_MASK;
    r->cmd = mfc_is_get(v) ? 1 : 0; r->ea = ea; r->lsa = lsa; r->size = n; r->tag = ctx->mfc_tag; r->m358 = 0xFFFFFFFFu;
    r->h = mfc_is_get(v) ? sf_fnv(&ctx->ls[lsa], n) : sf_fnv(vm_base + ea, n);
    r->pre = sfr_pre;
    if (mfc_is_get(v) && n == 0x930u) r->sub = sf_fnv(&ctx->ls[(lsa + 0x800u) & SPU_LS_MASK], 304u);   /* record+0x800 as GOT */
    if (mfc_is_get(v) && n == 1168u)  r->m358 = spu_ls_read32(ctx, lsa + 0x358u);                       /* live group mask */
    if (n <= 128u && (ea >= 0x111A2000u && ea < 0x111A2880u)) { memcpy(r->d, &ctx->ls[lsa], n); r->dn = n; } /* snapshot bytes */
}
if (channel == MFC_Cmd) putinputs_after_cmd(ctx, v);        /* existing line, unchanged */
```
Atomic path (flag set by the SPU): the existing early return `if (channel == MFC_Cmd && spu_mfc_atomic(ctx, v)) return;` becomes
```c
if (channel == MFC_Cmd && spu_mfc_atomic(ctx, v)) {
    if (sf_race_on() && (ctx->mfc_eal & ~127u) == (0x00DBA900u & ~127u)) {          /* log-only */
        sfr_rec* r = sf_race_slot(); r->kind = SFR_EF; r->ea = 0x00DBA900u; r->cmd = 0;
        r->old_ = (uint32_t)((vm_base[0x00DBA900u] << 8) | vm_base[0x00DBA901u]); r->tid = ctx->image_id; r->pc = ctx->pc & SPU_LS_MASK; }
    return; }
```
(If the SPU sets the flag through the taskset syscall instead, put the same 4 lines at the top of `spurs_ef_set_from_spu()` in libs/spurs/cellSpurs.c. Use both if unsure; the checker keys only on flag+time.)

## 5. Halt hook: `runtime/spu/spu_channels.c`, function `spu_halt()` (first lines, before the existing `[spu-halt]` print)
```c
if (sf_race_on() && ctx->image_id == SF_RACE_IMG_ID) {          /* log-only */
    uint32_t pc = ctx->pc & SPU_LS_MASK, w = spu_ls_read32(ctx, pc), op8 = w >> 24, ra = (w >> 7) & 0x7F;
    int i10 = (int)((w >> 14) & 0x3FF); if (i10 & 0x200) i10 -= 0x400;
    sfr_rec* r = sf_race_slot(); r->kind = SFR_HALT;
    uint32_t b = ctx->gpr[89]._u32[0] & SPU_LS_MASK;
    int p = snprintf((char*)r->d, sizeof r->d, "[sfrace-halt] q=%llu img=%d pc=0x%05X insn=%08X op8=%02X ra=r%u ra_val=%08X imm=%d r89=%05X r93=%08X",
        (unsigned long long)r->q, ctx->image_id, pc, w, op8, ra, ctx->gpr[ra]._u32[0], i10, b, ctx->gpr[93]._u32[0]);
    (void)p;
    /* second record: LS at r89 (+0x00..+0x7F) = the 288-byte table the divisor came from */
    sfr_rec* r2 = sf_race_slot(); r2->kind = SFR_DMA; r2->img = ctx->image_id; r2->pc = pc; r2->cmd = 1; r2->ea = ctx->gpr[93]._u32[0] + 0x13CE0u;
    r2->lsa = b; r2->size = 0; r2->m358 = 0xFFFFFFFFu; memcpy(r2->d, &ctx->ls[b], 128); r2->dn = 128; r2->h = sf_fnv(&ctx->ls[b], 288);
    sf_race_dump("spu_halt");
}
```
Notes: `heqi` is RI10 (op8 0x7F): ra = bits 18..24 = `(w >> 7) & 0x7F`, imm = bits 8..17. For 0x7F003200 this gives ra=r100, imm=0. The record `r2` is tagged ea = r93+0x13CE0 (the table EA the 288-byte GET at pc ~0x318EC reads), so the checker can match it to the last real [sfrace] GET of 0x11387860 (hash must be equal) and to the last PUT that covered 0x11387860 (the clobber).

## 6. PPU hooks
6a. `sf_ww_ranges_hit()` (SF-DIAG 1786 store watch, the patched source in `sfauto\voicediag1786\*.diag1786`, sfww_block.cpp on the box): after the existing value-changed test, add
```c
static int s_to_race = -1; if (s_to_race < 0) s_to_race = getenv("SF_WW_TO_RACE") ? 1 : 0;
if (s_to_race && sf_race_on()) { sfr_rec* r = sf_race_slot(); r->kind = SFR_WW; r->ea = a; r->old_ = old; r->new_ = v; r->w = width;
    r->fn = ppu_prof_resolve_host(ra); r->lr = c ? (uint32_t)c->lr : 0; r->tid = c ? (unsigned)c->thread_id : 0u; return; }
```
(returns before the stderr print, so the ranges above do not flood stderr; ordering with SPU records is by the shared `q`).
6b. `cellSpursEventFlagWait()` in `libs/spurs/cellSpurs.c`, right after `ef_wait_stats(ea, ef_t0.QuadPart);`:
```c
if (sf_race_on() && ea == 0x00DBA900u) { sfr_rec* r = sf_race_slot(); r->kind = SFR_EF; r->ea = ea; r->cmd = 1; r->old_ = current; r->tid = (uint32_t)GetCurrentThreadId(); }
```
and in the BLOCKED branch (where the `EventFlagWait BLOCKED` line prints for waits/500 == 1): `if (ea == 0x00DBA900u) sf_race_dump("ef_blocked");`.
6c. Process exit (`atexit` registered on first `sf_race_on()`): `sf_race_dump("exit")`.

## 7. Expected output (SF_RACE_LOG file)
```
[sfrace-dump] why=spu_halt records=1203311..1603311
[sfrace] q=147748861234567 img=391227015 spu=4A10 pc=0x06A94 dir=GET ea=0x111A2800 lsa=0x13280 size=128 tag=1 h=... d=00000082000000...
[sfrace] q=... pc=0x06A94 dir=GET ea=0x111A2040 lsa=0x... size=16 tag=1 h=... d=ffffffff...
[sfrace] q=... pc=0x06BC0 dir=GET ea=0x111039.. lsa=0x2F400 size=1168 tag=1 h=... m358=0000000E
[sfrace] q=... pc=0x06BC0 dir=GET ea=0x111373B0 lsa=0x3C180 size=2352 tag=1 h=... sub=...
[sfww] r9 0x111A1784 FF->FD w1 fn=0x00058974 lr=0x00059590 tid=17 t=147748862 q=147748862001234 ch:
[sfrace] q=... pc=0x071EC dir=PUT ea=0x11137BB0 lsa=0x3C980 size=304 tag=1 h=... pre=...
[sfrace] q=... pc=0x0A70C dir=PUT ea=0x11387580 lsa=0x17280 size=4096 tag=0 h=... pre=...
[sfrace-ef] q=... who=SPU flag=0x00DBA900 bits=0x0001 tid=391227015
[sfrace-halt] q=... img=391227015 pc=0x31C20 insn=7F003200 op8=7F ra=r100 ra_val=00000000 imm=0 r89=1F760 r93=11373B80
```
Also on stderr (existing): `[spu-ovl-dump] img=391227015 body ea=0x........ size=... -> ...ovl_XXXXXXXX.bin`, `[fs] open ...`, `[spu] ... unlifted LS 0x31C20`, `[cellSpurs] EventFlagWait BLOCKED ...`.

## 8. How to run and check
1. Build the test copy with only the hooks above (L12: one change = these log hooks). Record exe MD5 next to the logs.
2. Saud plays to the Bandit Trap gate as in the 17:27 session. When it freezes, wait 3 s (the EF BLOCKED dump fires), close the window.
3. Copy `play_logs\sfrace_*.log`, the stderr log, and `play_logs\ovl_sfrace\*.bin` to `/workspace/sf-shared/testloop/sfrace/`.
4. Run on the box:
   - `python3 race_check.py testloop/sfrace/sfrace_<pid>.log --json testloop/sfrace/race.json`
   - `python3 voice_freeze_analyzer.py testloop/sfrace/*stderr*.log --out testloop/sfrace/vf`
   - `python3 spu_mini_decode.py 31B00 <words from ovl_*.bin around 0x31B00..0x31C40>` (I will do the overlay disassembly once the .bin is on the box).
5. Reading the verdict:
   - **M > 0 in the last pass before the halt, V > 200 there, L = 0:** the mask/snapshot mismatch (path-1 allocation) is the root mechanism; next is to see which side's ordering differs from hardware (E, and tid-17 mask writes inside the pass).
   - **L > 0 on the halt pass:** QA's lost-update race is real; the stale PUT is the mechanism.
   - **E shows set_before_pass_end:** the flag/pass ordering in our SPURS path lets tid 7 run during a pass; that is a runtime bug to fix at the root (flag semantics), not in the game.
   - **None, and V never > 176:** the overflow did not happen in this run; the halt has another source of the zero table (check the last PUT covering 0x11387860 in the dump).

Cost note (QA point): the ring keeps formatting off the hot path, but FNV over 2352/4096 bytes per DMA still costs time. If the freeze stops reproducing with SF_RACE=1, drop the 4KB ring PUTs from `sfr_ea_watched` first (page numbers then come from `SPU_PUTINPUTS=1` instead).

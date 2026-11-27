import re,sys,os
O='/workspace/blackhang/orig/'; N='/workspace/blackhang/new/'
def load(f): return open(O+f,'rb').read().decode('latin-1')
def save(f,s): open(N+f,'wb').write(s.encode('latin-1'))
def eol_at(s,i):
    j=s.find('\n',i); return '\r\n' if j>0 and s[j-1]=='\r' else '\n'
def rep(s,anchor,new,count=1,after=True,where=''):
    n=s.count(anchor)
    if n==0 and anchor.replace('\r','') in s: anchor=anchor.replace('\r',''); n=s.count(anchor)
    if n!=count: sys.exit(f'anchor count {n}!={count} {where}: {anchor[:60]!r}')
    i=s.find(anchor); e=eol_at(s,i)
    new=new.replace('\n',e)
    return s.replace(anchor, anchor+new if after else new+anchor)
def sub(s,old,new,where=''):
    if s.count(old)!=1:
        o2=old.replace('\r','').replace('\n','\r\n'); n2=new.replace('\r','').replace('\n','\r\n')
        if s.count(o2)==1: return s.replace(o2,n2)
        o3=old.replace('\r',''); n3=new.replace('\r','')
        if s.count(o3)==1: return s.replace(o3,n3)
    if s.count(old)!=1: sys.exit(f'sub count {s.count(old)} {where}: {old[:60]!r}')
    return s.replace(old,new)

# ---------- spu_workload.c
s=load('spu_workload.c')
s=rep(s,'static void ts_unlock(void) { InterlockedExchange(&s_ts_lock, 0); }','''
/* [sf-blackhang] LOG-ONLY: SPURS task lifecycle in the [sf-lc] format of
 * voicefreeze/lifecycle/sf_lifecycle.py. Only records and prints; it does not
 * change scheduling, tasks or memory. */
#define SFL_N 1024
typedef struct { uint32_t ts, id, args; int img; unsigned long htid; unsigned long long t0; int used; } sfl_ent;
static sfl_ent s_sfl[SFL_N];
static volatile LONG s_sfl_lock;
static void sfl_lock(void)   { while (InterlockedExchange(&s_sfl_lock, 1)) Sleep(0); }
static void sfl_unlock(void) { InterlockedExchange(&s_sfl_lock, 0); }
#ifdef _WIN32
static unsigned long long sfl_ms(void) { return (unsigned long long)GetTickCount64(); }
static unsigned long sfl_tid(void) { return (unsigned long)GetCurrentThreadId(); }
#else
static unsigned long long sfl_ms(void) { struct timespec t; timespec_get(&t, TIME_UTC); return (unsigned long long)t.tv_sec * 1000ull + (unsigned long long)(t.tv_nsec / 1000000); }
static unsigned long sfl_tid(void) { return 0ul; }
#endif
static int sfl_add(uint32_t ts, uint32_t id, uint32_t args, int img)
{
    int k = -1;
    sfl_lock();
    for (int i = 0; i < SFL_N; i++) if (!s_sfl[i].used) {
        k = i; s_sfl[i].used = 1; s_sfl[i].ts = ts; s_sfl[i].id = id; s_sfl[i].args = args;
        s_sfl[i].img = img; s_sfl[i].htid = sfl_tid(); s_sfl[i].t0 = sfl_ms(); break; }
    sfl_unlock();
    return k;
}
static void sfl_del(int k) { if (k < 0) return; sfl_lock(); s_sfl[k].used = 0; sfl_unlock(); }
/* Prints every task host thread still running in taskset ts (all when ts==0). */
int sf_life_dump(uint32_t ts, const char* why)
{
    int n = 0; const unsigned long long now = sfl_ms();
    sfl_lock();
    for (int i = 0; i < SFL_N; i++) if (s_sfl[i].used && (!ts || s_sfl[i].ts == ts)) {
        n++;
        fprintf(stderr, "[sf-lc] live_task at=%s ts=0x%08X task=%u img=%d args=0x%08X htid=%lu age_ms=%llu\\n",
                why, s_sfl[i].ts, s_sfl[i].id, s_sfl[i].img, s_sfl[i].args, s_sfl[i].htid, now - s_sfl[i].t0);
    }
    sfl_unlock();
    fprintf(stderr, "[sf-lc] live_count at=%s ts=0x%08X live=%d\\n", why, ts, n);
    return n;
}''',where='wl1')
s=sub(s,'''static void spu_async_run(spu_async_job* j)
{
    spu_taskset_mark(j->taskset_ea, j->taskid, 1);''','''static void spu_async_run(spu_async_job* j)
{
    /* [sf-blackhang] log-only */
    const uint32_t sfl_ts = j->taskset_ea, sfl_id = j->taskid, sfl_args = j->args_ea;
    const int sfl_img = j->image_id;
    const unsigned long long sfl_t0 = sfl_ms();
    const int sfl_k = sfl_add(sfl_ts, sfl_id, sfl_args, sfl_img);
    int sfl_exited = 0;   /* host_thread_stop is printed only when no task_exit was (one close per run for sf_lifecycle.py) */
    fprintf(stderr, "[sf-lc] host_thread_start ts=0x%08X task=%u img=%d args=0x%08X htid=%lu\\n",
            sfl_ts, sfl_id, sfl_img, sfl_args, sfl_tid());
    spu_taskset_mark(j->taskset_ea, j->taskid, 1);'''.replace('\n','\r\n'),'wl2')
s=rep(s,'''            fprintf(stderr, "[spu_workload] async image=%d RETURNED rc=%d "\r
                    "(job ran to completion, did not loop)\\n", j->image_id, rc);''','''
            fprintf(stderr, "[sf-lc] task_exit ts=0x%08X task=%u img=%d rc=%d htid=%lu ran_ms=%llu\\n",
                    sfl_ts, sfl_id, sfl_img, rc, sfl_tid(), sfl_ms() - sfl_t0);
            sfl_exited = 1;''',where='wl3')
s=sub(s,'''    }\r
    free(j);\r
}\r
\r
#ifdef _WIN32\r
static DWORD WINAPI spu_async_thread''','''    }\r
    if (!sfl_exited) fprintf(stderr, "[sf-lc] host_thread_stop ts=0x%08X task=%u img=%d htid=%lu ran_ms=%llu no_task_exit=1\\n",\r
            sfl_ts, sfl_id, sfl_img, sfl_tid(), sfl_ms() - sfl_t0);\r
    sfl_del(sfl_k);\r
    free(j);\r
}\r
\r
#ifdef _WIN32\r
static DWORD WINAPI spu_async_thread''','wl4')
s=rep(s,'''     * (Twisted Metal's level-load inflate tasks each ran twice, concurrently). */\r
    spu_taskset_mark(j->taskset_ea, j->taskid, 1);''','''
    fprintf(stderr, "[sf-lc] task_create ts=0x%08X task=%u img=%d args=0x%08X via=dispatch_async\\n",
            j->taskset_ea, j->taskid, image_id, args_ea);   /* [sf-blackhang] log-only */''',where='wl5')
save('spu_workload.c',s)

# ---------- cellSpurs.c
s=load('cellSpurs.c')
s=rep(s,'''    printf("[cellSpurs] CreateTaskset() ea=0x%08X spurs=0x%08X wid=%u (real BE layout)\\n", taskset_ea, spurs_ea, ts_wid);''','''
    { extern int sf_life_dump(uint32_t, const char*);   /* [sf-blackhang] log-only */
      fprintf(stderr, "[sf-lc] taskset_create ts=0x%08X spurs=0x%08X wid=%u size=0x%X\\n", taskset_ea, spurs_ea, ts_wid, (unsigned)taskset_size);
      sf_life_dump(taskset_ea, "taskset_create"); }''',where='cs1')
for fn,ev in (('DestroyTaskset','taskset_destroy'),('ShutdownTaskset','taskset_shutdown'),('JoinTaskset','taskset_join')):
    s=sub(s,f'''s32 cellSpurs{fn}(CellSpursTaskset* taskset)\r
{{\r
    taskset = GUEST_PTR(taskset, CellSpursTaskset*);''',f'''s32 cellSpurs{fn}(CellSpursTaskset* taskset)\r
{{\r
    {{ extern int sf_life_dump(uint32_t, const char*);   /* [sf-blackhang] log-only; the runtime does nothing else here */\r
      const uint32_t sf_ea = (uint32_t)(uintptr_t)taskset;\r
      fprintf(stderr, "[sf-lc] {ev} ts=0x%08X runtime=noop_return_ok\\n", sf_ea);\r
      sf_life_dump(sf_ea, "{ev}"); }}\r
    taskset = GUEST_PTR(taskset, CellSpursTaskset*);''',fn)
s=rep(s,'''                   context_ea, task_lsp[0], task_lsp[1], task_lsp[2], task_lsp[3]);''','''
            fprintf(stderr, "[sf-lc] task_create_hle ts=0x%08X task=%u elf=0x%08X ctx=0x%08X arg=%08X.%08X.%08X.%08X\\n",
                    taskset_ea, s_tasks[i].id, (unsigned)(uintptr_t)elf, context_ea,
                    task_arg[0], task_arg[1], task_arg[2], task_arg[3]);   /* [sf-blackhang] log-only */''',where='cs3')
save('cellSpurs.c',s)

# ---------- spu_channels.c
s=load('spu_channels.c')
s=rep(s,'#include "ps3emu/log_first.h"','''
/* [sf-blackhang] LOG-ONLY SPU-side queue line watch (SF_LFQ_LOG_MAX set):
 * queues registered at cellSyncLFQueueInitialize; on each SPU GETLLAR of a
 * registered queue line, print when the pop (h1 @+0) or push (h5 @+8)
 * counter differs from what the previous GETLLAR of that line saw. */
#define SFQ_N 512
static uint32_t s_sfq_q[SFQ_N], s_sfq_dir[SFQ_N], s_sfq_owner[SFQ_N];
static uint8_t  s_sfq_last[SFQ_N][16];
static volatile int s_sfq_n;
static long s_sfq_max = -1; static volatile long s_sfq_cnt;
void sf_lfq_spu_register(uint32_t q, uint32_t owner, uint32_t depth, uint32_t dir, long max)
{
    (void)depth;
    s_sfq_max = max;
    for (int i = 0; i < s_sfq_n; i++) if (s_sfq_q[i] == q) { s_sfq_owner[i] = owner; s_sfq_dir[i] = dir; memset(s_sfq_last[i], 0, 16); return; }
    if (s_sfq_n < SFQ_N) { int i = s_sfq_n; s_sfq_q[i] = q; s_sfq_owner[i] = owner; s_sfq_dir[i] = dir; memset(s_sfq_last[i], 0, 16); s_sfq_n = i + 1; }
}
static void sf_lfq_spu_check(int img, uint32_t pc, uint32_t ea, const uint8_t* line)
{
    const uint32_t q = ea & ~127u;
    for (int i = 0; i < s_sfq_n; i++) if (s_sfq_q[i] == q) {
        uint8_t* L = s_sfq_last[i];
        const unsigned oh1 = (L[0] << 8) | L[1], oh5 = (L[8] << 8) | L[9];
        const unsigned nh1 = (line[0] << 8) | line[1], nh5 = (line[8] << 8) | line[9];
        if (oh1 != nh1 || oh5 != nh5) {
            if (s_sfq_max == 0 || s_sfq_cnt++ < s_sfq_max) {
                const unsigned long tid = (unsigned long)GetCurrentThreadId();
                if (oh1 != nh1) fprintf(stderr, "[sf-lc] lfq_pop q=0x%08X owner=0x%08X dir=%u img=%d pc=0x%05X htid=%lu h1=%u->%u h5=%u via=spu_getllar\\n", q, s_sfq_owner[i], s_sfq_dir[i], img, pc, tid, oh1, nh1, nh5);
                if (oh5 != nh5) fprintf(stderr, "[sf-lc] lfq_push q=0x%08X owner=0x%08X dir=%u img=%d pc=0x%05X htid=%lu h5=%u->%u h1=%u via=spu_getllar\\n", q, s_sfq_owner[i], s_sfq_dir[i], img, pc, tid, oh5, nh5, nh1);
            }
            memcpy(L, line, 16);
        }
        return;
    }
}''',where='ch1')
s=rep(s,'        memcpy(ctx->resv_line, ls, MFC_ATOMIC_LINE);   /* snapshot for compare */','''
        if (s_sfq_n) sf_lfq_spu_check(ctx->image_id, (uint32_t)(ctx->pc & SPU_LS_MASK), ea, ls);   /* [sf-blackhang] log-only */''',where='ch2')
save('spu_channels.c',s)

# ---------- strikeforce_lfqueue.inc (mixed EOL; rep() uses the anchor line's EOL)
s=load('strikeforce_lfqueue.inc')
s=rep(s,'static std::atomic<unsigned> g_init_n{0}, g_push_n{0}, g_full_n{0};','''
/* [sf-blackhang] LOG-ONLY: SF_LFQ_LOG_MAX=<n> sets the cap of the [sf-lfq]/[sf-lfq2]
 * lines (0 = no cap; unset = the old caps) and turns on the SPU-side queue line watch. */
static long sf_lfq_max() { static long v = -2; if (v == -2) { const char* e = getenv("SF_LFQ_LOG_MAX"); long x = e ? strtol(e, nullptr, 0) : -1; if (x < -1) x = -1; v = x; if (e) fprintf(stderr, "[sf-lfq] SF_LFQ_LOG_MAX=%ld (0 = no cap) + SPU-side queue line watch\\n", v); } return v; }
static bool sf_lfq_cap(unsigned n, unsigned def) { const long m = sf_lfq_max(); if (m < 0) return n < def; if (m == 0) return true; return n < (unsigned long)m; }
extern "C" void sf_lfq_spu_register(uint32_t q, uint32_t owner, uint32_t depth, uint32_t dir, long max);''',where='lq1')
s=sub(s,'    if (g_init_n++ < 16)\r\n','    if (sf_lfq_max() >= 0 && rc == 0) sf_lfq_spu_register(q, owner, depth, dir, sf_lfq_max());   /* [sf-blackhang] log-only */\r\n    if (sf_lfq_cap(g_init_n++, 16))\r\n') if '    if (g_init_n++ < 16)\r\n' in s else sub(s,'    if (g_init_n++ < 16)\n','    if (sf_lfq_max() >= 0 && rc == 0) sf_lfq_spu_register(q, owner, depth, dir, sf_lfq_max());   /* [sf-blackhang] log-only */\n    if (sf_lfq_cap(g_init_n++, 16))\n')
s=sub(s,'static int sn = 0; if (sn++ < 16) fprintf','static unsigned sn = 0; if (sf_lfq_cap(sn++, 16)) fprintf')
s=sub(s,'        if (mn++ < 400)\n','        const bool sf_ok = sf_lfq_cap(mn++, 400);\n        if (sf_ok)\n') if '        if (mn++ < 400)\n' in s and '        if (mn++ < 400)\r\n' not in s else sub(s,'        if (mn++ < 400)\r\n','        const bool sf_ok = sf_lfq_cap(mn++, 400);\r\n        if (sf_ok)\r\n')
s=sub(s,'        if (mn <= 400) fprintf','        if (sf_ok) fprintf')
s=sub(s,'    if (g_push_n++ < 24)','    if (sf_lfq_cap(g_push_n++, 24))')
s=sub(s,'    if (sf_lfq_cap(g_push_n++, 24))','''    { static std::atomic<unsigned> sf_lcp{0};   /* [sf-blackhang] log-only */
      if (sf_lfq_max() >= 0 && rc == 0 && sf_lfq_cap(sf_lcp++, 0x7fffffffu))
          fprintf(stderr, "[sf-lc] lfq_push q=0x%08X slot=%u h1=%u blk=%u via=ppu lr=0x%08X\\n", q, slot, h1, blocking, (uint32_t)ctx->lr); }
    if (sf_lfq_cap(g_push_n++, 24))''')
s=sub(s,'    if (sf_lfq_cap(g_init_n++, 16))','''    if (sf_lfq_max() >= 0) fprintf(stderr, "[sf-lc] lfq_init q=0x%08X owner=0x%08X buf=0x%08X size=%u depth=%u dir=%u rc=0x%08X\\n", q, owner, buf, size, depth, dir, rc);   /* [sf-blackhang] log-only */
    if (sf_lfq_cap(g_init_n++, 16))''')
save('strikeforce_lfqueue.inc',s)

# ---------- cellAtrac.c  (SF_ATRAC_LOG=1, field list of sf-shared/atrac-validator/README.md)
s=load('cellAtrac.c')
s=rep(s,'static AtracSlot s_slots[ATRAC_MAX_SLOTS];','''

/* [sf-blackhang] LOG-ONLY: SF_ATRAC_LOG=1 -> one "[sf-atrac] fn=... key=value" line per
 * streaming call (atrac-validator/README.md field list). It only reads state and
 * hashes bytes; nothing feeds back into decoding or the guest. */
#ifdef _WIN32
__declspec(dllimport) unsigned long __stdcall GetCurrentThreadId(void);
#define SFA_TID() ((unsigned long)GetCurrentThreadId())
#else
#define SFA_TID() 0ul
#endif
static int sfa_on(void) { static int v = -1; if (v < 0) { const char* e = getenv("SF_ATRAC_LOG"); v = e ? atoi(e) : 0; if (v) fprintf(stderr, "[sf-atrac] fn=Armed SF_ATRAC_LOG=%d\\n", v); } return v; }
static u32 sfa_fnv(const u8* p, u32 n) { u32 h = 0x811C9DC5u; for (u32 i = 0; i < n; i++) { h ^= p[i]; h *= 0x01000193u; } return h; }
typedef struct { u32 given; u32 ra_wea, ra_len, ra_off; int ra_pending; } SfaSlot;
static SfaSlot s_sfa[ATRAC_MAX_SLOTS];
#define SFA_X(s) (&s_sfa[(int)((s) - s_slots)])
#define SFA(s, fn, fmt, ...) do { if (sfa_on() && (s)) fprintf(stderr, "[sf-atrac] fn=%s tid=%lu h=0x%08X " fmt "\\n", fn, SFA_TID(), (s)->handle_ea, ##__VA_ARGS__); } while (0)
/* AddRecheck: re-hash the ring bytes of the previous add at the next call on this handle. */
static void sfa_recheck(AtracSlot* s)
{
    if (!sfa_on() || !s) return;
    SfaSlot* x = SFA_X(s);
    if (!x->ra_pending) return;
    x->ra_pending = 0;
    SFA(s, "AddRecheck", "off=%u len=%u wea=0x%08X fnv=0x%08X", x->ra_off, x->ra_len, x->ra_wea, sfa_fnv(vm_base + x->ra_wea, x->ra_len));
}''',where='at1')
# DecodeFrame / DecodeError in decode_frame (same decoder call, rc kept for the log)
s=sub(s,'''        if (at3p_decode(s->dec, planes, &n, s->file + at,\r
                        (int)s->t.block_align) < 0 || n != AT3P_SAMPLES) {\r
''','''        const int sfa_rc = at3p_decode(s->dec, planes, &n, s->file + at, (int)s->t.block_align);   /* [sf-blackhang] same call; rc kept for the log */\r
        if (sfa_on()) {\r
            const u8* b = s->file + at; const u32 ba = s->t.block_align;\r
            if (sfa_rc < 0 || n != AT3P_SAMPLES)\r
                SFA(s, "DecodeError", "k=%d off=%u len=%u fnv=0x%08X first16=%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X msg=\\"rc=%d n=%d\\"",\r
                    s->next_frame, at, ba, sfa_fnv(b, ba), b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8],b[9],b[10],b[11],b[12],b[13],b[14],b[15], sfa_rc, n);\r
            else if (s->t.channels == 6)\r
                SFA(s, "DecodeFrame", "k=%d off=%u len=%u fnv=0x%08X b0=0x%02X rc=%d", s->next_frame, at, ba, sfa_fnv(b, ba), b[0], sfa_rc);\r
        }\r
        if (sfa_rc < 0 || n != AT3P_SAMPLES) {\r
''','at2')
s=sub(s,'''    if (decode_frame(s, k) < 0) {\r
''','''    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    if (decode_frame(s, k) < 0) {\r
        SFA(s, "DecodeNoData", "k=%d next_frame=%d fed=%u", k, s->next_frame, s->file_fed);   /* [sf-blackhang] log-only */\r
''','at3')
# GetStreamDataInfo
s=sub(s,'''    ring_release_consumed(s);\r
    if (s->all_on_mem || (s->file_total && s->file_fed >= s->file_total))\r
        return (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY;\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (ppucWritePointer) vm_write32(ppucWritePointer, wea);\r
    if (puiWritableByte) vm_write32(puiWritableByte, wr);\r
    if (puiReadPosition) vm_write32(puiReadPosition, s->file_fed);\r
    return CELL_OK;\r
''','''    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    ring_release_consumed(s);\r
    if (s->all_on_mem || (s->file_total && s->file_fed >= s->file_total)) {\r
        SFA(s, "GetStreamDataInfo", "wea_given=0x0 writable=0 readpos=%u voff=%u vbytes=%u fed=%u rc=0x%08X", s->file_fed, s->valid_off, s->valid_bytes, s->file_fed, (u32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY);\r
        return (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY;\r
    }\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (ppucWritePointer) vm_write32(ppucWritePointer, wea);\r
    if (puiWritableByte) vm_write32(puiWritableByte, wr);\r
    if (puiReadPosition) vm_write32(puiReadPosition, s->file_fed);\r
    SFA_X(s)->given = wea;   /* [sf-blackhang] log-only */\r
    SFA(s, "GetStreamDataInfo", "wea_given=0x%08X writable=%u readpos=%u voff=%u vbytes=%u fed=%u rc=0x0", wea, wr, s->file_fed, s->valid_off, s->valid_bytes, s->file_fed);\r
    return CELL_OK;\r
''','at4')
# AddStreamData
s=sub(s,'''    if (s->all_on_mem || uiAddByte == 0) return CELL_OK;\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (uiAddByte > wr) return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG;\r
    if (s->host) {\r
        if (s->file_fed + uiAddByte > s->host_cap)\r
            return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG;\r
        memcpy(s->host + s->file_fed, vm_base + wea, uiAddByte);\r
    }\r
    s->file_fed += uiAddByte;\r
    s->valid_bytes += uiAddByte;\r
    if (s->file_total && s->file_fed >= s->file_total) s->all_on_mem = 1;\r
    return CELL_OK;\r
''','''    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    const u32 sfa_off = s->file_fed;\r
    if (s->all_on_mem || uiAddByte == 0) { SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x0 voff=%u vbytes=%u fed_after=%u rc=0x0 fnv=0x0 note=%s", uiAddByte, sfa_off, SFA_X(s)->given, s->valid_off, s->valid_bytes, s->file_fed, s->all_on_mem ? "all_on_mem" : "zero_add"); return CELL_OK; }\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (uiAddByte > wr) { SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x%08X voff=%u vbytes=%u fed_after=%u rc=0x%08X fnv=0x0 writable=%u", uiAddByte, sfa_off, SFA_X(s)->given, wea, s->valid_off, s->valid_bytes, s->file_fed, (u32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG, wr); return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG; }\r
    if (s->host) {\r
        if (s->file_fed + uiAddByte > s->host_cap) {\r
            SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x%08X voff=%u vbytes=%u fed_after=%u rc=0x%08X fnv=0x0 note=host_cap", uiAddByte, sfa_off, SFA_X(s)->given, wea, s->valid_off, s->valid_bytes, s->file_fed, (u32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG);\r
            return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG;\r
        }\r
        memcpy(s->host + s->file_fed, vm_base + wea, uiAddByte);\r
    }\r
    s->file_fed += uiAddByte;\r
    s->valid_bytes += uiAddByte;\r
    if (s->file_total && s->file_fed >= s->file_total) s->all_on_mem = 1;\r
    if (sfa_on()) {   /* [sf-blackhang] log-only */\r
        SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x%08X voff=%u vbytes=%u fed_after=%u rc=0x0 fnv=0x%08X", uiAddByte, sfa_off, SFA_X(s)->given, wea, s->valid_off, s->valid_bytes, s->file_fed, sfa_fnv(vm_base + wea, uiAddByte));\r
        SfaSlot* x = SFA_X(s); x->ra_wea = wea; x->ra_len = uiAddByte; x->ra_off = sfa_off; x->ra_pending = 1;\r
    }\r
    return CELL_OK;\r
''','at5')
# ResetPlayPosition
s=sub(s,'''    if (p >= s->t.end) return (s32)CELL_ATRAC_ERROR_ILLEGAL_SAMPLE;\r
    if (!s->all_on_mem && uiWriteByte) {\r
''','''    if (p >= s->t.end) return (s32)CELL_ATRAC_ERROR_ILLEGAL_SAMPLE;\r
    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    const u32 sfa_fed0 = s->file_fed; const s32 sfa_nf0 = s->next_frame;\r
    const u32 sfa_roff = s->t.data_off + (u32)(p / AT3P_SAMPLES) * s->t.block_align;\r
    if (!s->all_on_mem && uiWriteByte) {\r
''','at6')
s=sub(s,'''    }\r
    s->pos = p;\r
    return CELL_OK;\r
}\r
\r
s32 cellAtracGetStreamDataInfo''','''    }\r
    s->pos = p;\r
    SFA(s, "ResetPlayPosition", "sample=%u wb=%u roff=%u fed_before=%u fed_after=%u next_frame_before=%d flushed=0 rc=0x0", uiSample, uiWriteByte, sfa_roff, sfa_fed0, s->file_fed, sfa_nf0);   /* [sf-blackhang] log-only */\r
    return CELL_OK;\r
}\r
\r
s32 cellAtracGetStreamDataInfo''','at6b')
# GetBufferInfoForResetting
s=sub(s,'''    vm_write32(pBufferInfo + 12, roff);\r
    return CELL_OK;\r
''','''    vm_write32(pBufferInfo + 12, roff);\r
    SFA(s, "GetBufferInfoForResetting", "sample=%u info_wea=0x%08X info_bytes=%u info_min=%u info_readpos=%u rc=0x0", uiSample, s->buf_ea, s->buf_size, s->t.block_align, roff);   /* [sf-blackhang] log-only */\r
    return CELL_OK;\r
''','at8')
# SetData
s=sub(s,'''    if (puiWorkMemByte) vm_write32(puiWorkMemByte, 0x1000);\r
''','''    if (puiWorkMemByte) vm_write32(puiWorkMemByte, 0x1000);\r
    memset(SFA_X(s), 0, sizeof(SfaSlot));   /* [sf-blackhang] log-only */\r
    SFA(s, "SetData", "ch=%u ba=%u doff=%u first=%d end=%d ls=%d le=%d buf=0x%08X bufsz=%u read=%u total=%u rc=0x0", t.channels, t.block_align, t.data_off, t.first, t.end, t.loop_start, t.loop_end, pucBufferAddr, s->buf_size, uiReadByte, total);\r
''','at7')
save('cellAtrac.c',s)

print('ok')

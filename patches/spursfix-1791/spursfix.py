#!/usr/bin/env python3
# [sf-spursfix] 1791: stage-change teardown fix for SPURS tasksets (our own HLE code).
# Applies to copies of the bundle1787 sources. Anchors must match exactly once.
import sys, os
D = sys.argv[1] if len(sys.argv) > 1 else 'src'

def edit(fn, pairs):
    p = os.path.join(D, fn)
    b = open(p, 'rb').read().decode('utf-8')
    crlf = '\r\n' in b
    s = b.replace('\r\n', '\n')
    for old, new in pairs:
        n = s.count(old)
        if n != 1:
            raise SystemExit(f'{fn}: anchor count {n}: {old[:70]!r}')
        s = s.replace(old, new)
    if crlf: s = s.replace('\n', '\r\n')
    open(p, 'wb').write(s.encode('utf-8'))
    print('patched', fn)

# ---------------- spu_workload.c ----------------
FIX_BLOCK = r'''
/* [sf-spursfix] Stage-change teardown for SPURS tasksets.
 *
 * Strikeforce ends a stage with cellSpursShutdownTaskset + cellSpursJoinTaskset
 * on each stage taskset, then creates the next stage's tasksets -- some at the
 * SAME guest address (0x14C02A80). Here every task runs on its own host thread,
 * and a task parked in WAIT_SIGNAL stayed parked for ever: Shutdown/Join were
 * no-ops. The old task then shared the taskset's signalled bit with the new
 * task of the same id and could eat its wake-ups (lost handshake at the village
 * load). Real SPURS simply never schedules a shut-down taskset's tasks again.
 *
 * Here: Shutdown marks the taskset "down" and wakes its parked tasks; a task
 * that is (or becomes) parked in a down taskset leaves through the normal
 * task-exit landing pad. Join waits (bounded) until no host thread of that
 * taskset is alive. Create at an address that still has live tasks does the
 * same first, then clears the down mark and the per-taskset run state.
 * SF_SPURSFIX=0 restores the old no-op behaviour (A/B switch);
 * SF_SPURSFIX_JOIN_MS bounds the wait (default 3000). */
#define SF_TSDOWN_MAX 32
static volatile uint32_t s_tsdown[SF_TSDOWN_MAX];
int sf_spursfix_on(void)
{
    static int v = -1;
    if (v < 0) { const char* e = getenv("SF_SPURSFIX"); v = (e && e[0] == '0') ? 0 : 1;
                 fprintf(stderr, "[sf-fix] SF_SPURSFIX=%d (1791 taskset teardown)\n", v); }
    return v;
}
int spu_taskset_is_down(uint32_t ea)
{
    if (!ea) return 0;
    for (int i = 0; i < SF_TSDOWN_MAX; i++) if (s_tsdown[i] == ea) return 1;
    return 0;
}
static void sfx_down_set(uint32_t ea)
{
    if (spu_taskset_is_down(ea)) return;
    for (int i = 0; i < SF_TSDOWN_MAX; i++)
        if (InterlockedCompareExchange((volatile LONG*)&s_tsdown[i], (LONG)ea, 0) == 0) return;
    fprintf(stderr, "[sf-fix] down table full, ts=0x%08X not marked\n", ea);
}
static void sfx_down_clear(uint32_t ea)
{
    for (int i = 0; i < SF_TSDOWN_MAX; i++)
        if (s_tsdown[i] == ea) InterlockedCompareExchange((volatile LONG*)&s_tsdown[i], 0, (LONG)ea);
}
static void sfx_wake_all_parked(void)
{
#ifdef _WIN32
    AcquireSRWLockExclusive(&s_sig_lock);
    WakeAllConditionVariable(&s_sig_cv);
    ReleaseSRWLockExclusive(&s_sig_lock);
#else
    pthread_mutex_lock(&s_sig_lock);
    pthread_cond_broadcast(&s_sig_cv);
    pthread_mutex_unlock(&s_sig_lock);
#endif
}
static int sfx_live(uint32_t ts)
{
    int n = 0;
    sfl_lock();
    for (int i = 0; i < SFL_N; i++) if (s_sfl[i].used && s_sfl[i].ts == ts) n++;
    sfl_unlock();
    return n;
}
void spu_taskset_shutdown_request(uint32_t ea)
{
    if (!ea || !sf_spursfix_on()) return;
    sfx_down_set(ea);
    sfx_wake_all_parked();
    fprintf(stderr, "[sf-lc] taskset_down ts=0x%08X live=%d\n", ea, sfx_live(ea));
}
/* Returns how many host threads of ea are still alive when it gives up (0 = all left). */
int spu_taskset_join_wait(uint32_t ea, const char* why)
{
    if (!ea || !sf_spursfix_on()) return 0;
    static int lim = -1;
    if (lim < 0) { const char* e = getenv("SF_SPURSFIX_JOIN_MS"); lim = e ? atoi(e) : 3000; if (lim < 0) lim = 0; }
    const unsigned long long t0 = sfl_ms();
    int n = sfx_live(ea), last_wake = 0;
    while (n && (int)(sfl_ms() - t0) < lim) {
        Sleep(2);
        int el = (int)(sfl_ms() - t0);
        if (el - last_wake >= 50) { last_wake = el; sfx_wake_all_parked(); }
        n = sfx_live(ea);
    }
    fprintf(stderr, "[sf-lc] taskset_join_done ts=0x%08X at=%s left=%d waited_ms=%llu\n",
            ea, why, n, sfl_ms() - t0);
    if (n) sf_life_dump(ea, "join_timeout");
    return n;
}
/* Called by CreateTaskset before it rewrites the taskset memory. */
void spu_taskset_recreate(uint32_t ea)
{
    if (!ea || !sf_spursfix_on()) return;
    const int live = sfx_live(ea);
    if (live) {
        fprintf(stderr, "[sf-lc] taskset_recreate_live ts=0x%08X live=%d down=%d\n", ea, live, spu_taskset_is_down(ea));
        sf_life_dump(ea, "recreate");
        sfx_down_set(ea);
        sfx_wake_all_parked();
        spu_taskset_join_wait(ea, "recreate");
    }
    sfx_down_clear(ea);
    /* flush the old run's host-side state for this address */
    ts_lock();
    for (int i = 0; i < TS_TRACK; i++) if (s_ts_run[i].ea == ea) memset(s_ts_run[i].running, 0, sizeof s_ts_run[i].running);
    ts_unlock();
    for (int i = 0; i < SPU_WAKE_LATCH_MAX; i++) if (s_wake_latch[i] == ea) s_wake_latch[i] = 0;
    for (uint32_t t = 0; t < 128; t++) spu_taskset_round_drop(ea, t);
    fprintf(stderr, "[sf-lc] taskset_flush ts=0x%08X live_before=%d live_after=%d\n", ea, live, sfx_live(ea));
}

'''

edit('spu_workload.c', [
    ('static void spu_taskset_task_exited(uint32_t taskset_ea, uint32_t done_task)\n{',
     'int spu_taskset_is_down(uint32_t ea);   /* [sf-spursfix] */\nstatic void spu_taskset_task_exited(uint32_t taskset_ea, uint32_t done_task)\n{'),
    ('    for (uint32_t t = 0; t < 128 && run; t++) {',
     '    /* [sf-spursfix] a shut-down taskset starts nothing new */\n    for (uint32_t t = 0; t < 128 && run && !spu_taskset_is_down(taskset_ea); t++) {'),
    ('int spu_taskset_wait_signal(uint32_t taskset_ea, uint32_t taskId)\n{',
     FIX_BLOCK + 'int spu_taskset_wait_signal(uint32_t taskset_ea, uint32_t taskId)\n{\n    int sfx_killed = 0;   /* [sf-spursfix] */'),
    ('''    AcquireSRWLockExclusive(&s_sig_lock);
    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) {
        if (!SleepConditionVariableSRW(''',
     '''    AcquireSRWLockExclusive(&s_sig_lock);
    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId) &&
           !(sfx_killed = spu_taskset_is_down(taskset_ea))) {
        if (!SleepConditionVariableSRW('''),
    ('''    pthread_mutex_lock(&s_sig_lock);
    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId)) {
        struct timespec ts;''',
     '''    pthread_mutex_lock(&s_sig_lock);
    while (!spurs_bitset_test(taskset_ea + CSTS_SIGNALLED, taskId) &&
           !(sfx_killed = spu_taskset_is_down(taskset_ea))) {
        struct timespec ts;'''),
    ('''    if (!drained) spu_signalled_update(taskset_ea, taskId, 0);''',
     '''    if (sfx_killed) {   /* [sf-spursfix] taskset shut down: leave, keep the bit for nobody */
        fprintf(stderr, "[sf-lc] task_kill ts=0x%08X task=%u reason=taskset_down htid=%lu\\n",
                taskset_ea, taskId, sfl_tid());
        spu_serial_acquire();
        return 0x5D;
    }
    if (!drained) spu_signalled_update(taskset_ea, taskId, 0);'''),
])

# ---------------- spu_channels.c ----------------
edit('spu_channels.c', [
    ('''            spu_taskset_wait_signal(ts, tid);
            spu_taskset_parked_del(ts, tid);
            yz_lockstep_block_end(ctx);''',
     '''            const int sfx_rc = spu_taskset_wait_signal(ts, tid);
            spu_taskset_parked_del(ts, tid);
            yz_lockstep_block_end(ctx);
            if (sfx_rc == 0x5D) {   /* [sf-spursfix] taskset shut down while parked: end the task */
                ctx->status = SPU_STATUS_STOPPED_BY_STOP;
                spu_halt(ctx);
                return;
            }'''),
])

# ---------------- cellSpurs.c ----------------
edit('cellSpurs.c', [
    ('''    taskset = GUEST_PTR(taskset, CellSpursTaskset*);
    memset(taskset, 0, taskset_size);''',
     '''    { extern void spu_taskset_recreate(uint32_t);   /* [sf-spursfix] old tasks out before the rewrite */
      spu_taskset_recreate(taskset_ea); }
    taskset = GUEST_PTR(taskset, CellSpursTaskset*);
    memset(taskset, 0, taskset_size);'''),
    ('''      fprintf(stderr, "[sf-lc] taskset_destroy ts=0x%08X runtime=noop_return_ok\\n", sf_ea);
      sf_life_dump(sf_ea, "taskset_destroy"); }''',
     '''      fprintf(stderr, "[sf-lc] taskset_destroy ts=0x%08X runtime=spursfix_join\\n", sf_ea);
      sf_life_dump(sf_ea, "taskset_destroy");
      extern void spu_taskset_shutdown_request(uint32_t); extern int spu_taskset_join_wait(uint32_t, const char*);
      if (sf_ea) { spu_taskset_shutdown_request(sf_ea); spu_taskset_join_wait(sf_ea, "destroy"); } }'''),
    ('''      fprintf(stderr, "[sf-lc] taskset_shutdown ts=0x%08X runtime=noop_return_ok\\n", sf_ea);
      sf_life_dump(sf_ea, "taskset_shutdown"); }''',
     '''      fprintf(stderr, "[sf-lc] taskset_shutdown ts=0x%08X runtime=spursfix\\n", sf_ea);
      sf_life_dump(sf_ea, "taskset_shutdown");
      extern void spu_taskset_shutdown_request(uint32_t);
      if (sf_ea) spu_taskset_shutdown_request(sf_ea); }'''),
    ('''      fprintf(stderr, "[sf-lc] taskset_join ts=0x%08X runtime=noop_return_ok\\n", sf_ea);
      sf_life_dump(sf_ea, "taskset_join"); }''',
     '''      fprintf(stderr, "[sf-lc] taskset_join ts=0x%08X runtime=spursfix_wait\\n", sf_ea);
      sf_life_dump(sf_ea, "taskset_join");
      extern int spu_taskset_join_wait(uint32_t, const char*);
      if (sf_ea) spu_taskset_join_wait(sf_ea, "join"); }'''),
])

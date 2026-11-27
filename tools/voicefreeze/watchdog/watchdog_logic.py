#!/usr/bin/env python3
"""Box-side port of the detection rules in sf_hang_watchdog.ps1 (same regexes, same thresholds).

Replays a saved stderr log and prints which hang signals fire, at which line, in what order.
Detect only: it never touches a process. Time in replay = the game's own ms clock from t= fields
([vm-sum], [sfww], [hle-lr], [hle-lrc] dump); EventFlagWait BLOCKED lines carry their own seconds.

  python3 watchdog_logic.py LOG [--strip-prefix] [--no-progress-sec 20] [--ef-blocked-sec 5]
          [--halt-grace-sec 5] [--spin-calls-per-sec 40000] [--json out.json]
  python3 watchdog_logic.py --selftest
Keep the RULES in step with sf_hang_watchdog.ps1 (section 'Detection rules').
"""
import json, re, sys, argparse

FLAG_EA = 0x00DBA900
RX_EF = re.compile(r'\[cellSpurs\] EventFlagWait BLOCKED tid=(\d+) (\d+)s on pattern 0x([0-9A-Fa-f]+) .*?flagEA=0x([0-9A-Fa-f]+)')
RX_HALT_LINE = re.compile(r'^\[SPU-HALT\] img=(\d+) pc=0x([0-9A-Fa-f]+)|^\[SPU-TRACE\] halt at LS 0x([0-9A-Fa-f]+)')
RX_BRANCH = re.compile(r'^\[spu\] img=(\d+) branched into unlifted LS 0x([0-9A-Fa-f]+) \(lr=0x([0-9A-Fa-f]+)\)')
RX_LSDUMP = re.compile(r'^\s+LS\[0x([0-9A-Fa-f]+)\]: ([0-9A-Fa-f]{8})')
RX_LOADING = re.compile(r"^\[fs\] open '/dev_hdd1/cache/BLUS30471/\d+'|(?i:now ?loading)")
RX_T = re.compile(r'^\[(?:vm-sum|sfww|hle-lr|hle-lrc|vm|vm-cnt|vi)\].*?\bt=(\d+)')
RX_LRC_HDR = re.compile(r'^\[hle-lrc\] dump=(\d+) t=(\d+) pairs=(\d+)')
RX_LRC = re.compile(r'^\[hle-lrc\] (\d+) 0x([0-9A-Fa-f]+) 0x([0-9A-Fa-f]+) (\d+) ret=0x[0-9A-Fa-f]+ tid=(\d+)')
# v2: SPU job lifecycle (always printed by the runtime, no env needed)
RX_DISPATCH = re.compile(r'^\[spu_workload\] dispatch HIT \(async\) fp=0x[0-9A-Fa-f]+ args=0x([0-9A-Fa-f]+) image=(\d+)')
RX_RETURNED = re.compile(r'^\[spu_workload\] async image=(\d+) RETURNED')
RX_SPUSPIN = re.compile(r'^\[spu-spin\] img=(\d+) pc=0x([0-9A-Fa-f]+) lr=0x([0-9A-Fa-f]+) GETLLAR ea=0x([0-9A-Fa-f]+)')
# Lines a hung game still prints on a timer: they are NOT progress.
HEARTBEAT = [re.compile(p) for p in (
    r'^\[vm-sum\]', r'^\[hle-lrc\]', r'^\[cellSpurs\] EventFlagWait BLOCKED', r'^\[spu_workload\] task \d+ .*sleeping \d+s',
    r'^\[samp\]', r'^\[pcsample\]', r'^\[spu-spin\]', r'^\[sfrace', r'^\s*$',
    # v2: printed by the audio side while the game is hung (saud_blackhang_1817 tail)
    r'^\[WAIT\] event_queue_receive\(', r'^\[spu_workload\] WAIT_SIGNAL#', r'^\[cellAtrac\] Atrac3/3\+: ')]
NIDS = {0x350D454E: 'sys_ppu_thread_get_id', 0x1BC200F4: 'sys_lwmutex_unlock', 0x1573DC3F: 'sys_lwmutex_lock',
        0x2A6D9D51: 'sys_lwcond_wait', 0xE9A1BD84: 'sys_lwcond_signal_all', 0xEF87A695: 'sys_lwcond_signal'}


def halt_op(w):
    """True if the SPU word is a conditional halt (heqi/hgti/hlgti RI10, heq/hgt/hlgt RR)."""
    return (w >> 24) in (0x7F, 0x4F, 0x5F) or (w >> 21) in (0x3D8, 0x258, 0x2D8)


class Detector:
    def __init__(self, no_progress_sec=20, ef_blocked_sec=5, halt_grace_sec=5, spin_calls_per_sec=40000,
                 loading_hold_sec=300, flag_ea=FLAG_EA, job_min_returns=50, job_stuck_sec=10, job_stuck_lines=200):
        self.np, self.efs, self.hg, self.spin, self.lhold, self.flag = no_progress_sec, ef_blocked_sec, halt_grace_sec, spin_calls_per_sec, loading_hold_sec, flag_ea
        self.now = None            # ms
        self.signals = []          # every signal seen (fired or not)
        self.fired = None
        self.halt = None; self.pending_branch = None
        self.loading = None; self.last_progress = None
        self.lrc_cur = None; self.lrc_prev = None; self.lrc_dump = {}; self.lrc_progress_since_hdr = 0
        self.spin_top = []
        self.jmin, self.jsec, self.jlines = job_min_returns, job_stuck_sec, job_stuck_lines
        self.jobs = {}             # image -> {'disp','ret','open':[(ln,args)], 'args_open':set}
        self.stuck = None          # (spin_ln, t_ms, image, ret_count_at_spin, text)

    def _sig(self, name, ln, text, detail, fire):
        s = {'signal': name, 'line': ln, 't_ms': self.now, 'text': text[:240], 'detail': detail, 'fires': fire}
        self.signals.append(s)
        if fire and not self.fired:
            self.fired = s
        return s

    def feed(self, ln, line, wall_ms=None):
        m = RX_T.search(line)
        if wall_ms is not None:
            self.now = wall_ms
        elif m:
            self.now = int(m.group(1))
        hb = any(r.search(line) for r in HEARTBEAT)
        if not hb:
            self.last_progress = (ln, self.now, line[:200])
            self.lrc_progress_since_hdr += 1
        # S1 blocked event-flag wait on the mixer flag
        m = RX_EF.search(line)
        if m and int(m.group(4), 16) == self.flag:
            secs = int(m.group(2))
            if secs >= self.efs:
                self._sig('ef_blocked', ln, line, {'tid': int(m.group(1)), 'secs': secs, 'flag': f'0x{self.flag:08X}'}, True)
        # S2 SPU halt
        m = RX_HALT_LINE.search(line)
        if m and not self.halt:
            pc = m.group(2) or m.group(3)
            self.halt = (ln, self.now, pc)
            self._sig('spu_halt', ln, line, {'pc': '0x' + pc.upper(), 'grace_s': self.hg}, False)
        m = RX_BRANCH.search(line)
        if m:
            self.pending_branch = (ln, m.group(2).upper(), m.group(1))
        m = RX_LSDUMP.search(line)
        if m and self.pending_branch and m.group(1).upper() == self.pending_branch[1]:
            w = int(m.group(2), 16)
            if halt_op(w) and not self.halt:
                self.halt = (self.pending_branch[0], self.now, self.pending_branch[1])
                self._sig('spu_halt', self.pending_branch[0], line,
                          {'pc': '0x' + self.pending_branch[1], 'img': self.pending_branch[2], 'word': f'{w:08X}', 'grace_s': self.hg}, False)
            self.pending_branch = None
        # S3 Now Loading marker
        if RX_LOADING.search(line):
            self.loading = (ln, self.now, line[:160])
        # S4b busy-spin from HLE call counts (log-only proxy of the CPU rule)
        m = RX_LRC_HDR.search(line)
        if m:
            self._lrc_close()
            self.lrc_cur = {'no': int(m.group(1)), 't': int(m.group(2)), 'pairs': int(m.group(3)), 'ln': ln, 'calls': {}, 'progress_before': self.lrc_progress_since_hdr}
            self.lrc_progress_since_hdr = 0
        m = RX_LRC.search(line)
        if m and self.lrc_cur and int(m.group(1)) == self.lrc_cur['no']:
            self.lrc_cur['calls'][(int(m.group(2), 16), int(m.group(3), 16), int(m.group(5)))] = int(m.group(4))
        # S5 spu_job_stuck: a short, repeating SPU job (>= job_min_returns completed runs) whose current run
        # spins in a GETLLAR poll ([spu-spin] = 4M re-reads of one line) and never returns
        m = RX_DISPATCH.search(line)
        if m:
            j = self.jobs.setdefault(m.group(2), {'disp': 0, 'ret': 0, 'open': []})
            if j['ret'] == 0 and any(a == m.group(1) for _, a in j['open']):
                self._sig('task_reuse_unreturned', ln, line, {'image': m.group(2), 'args': '0x' + m.group(1),
                          'earlier_dispatches_never_returned': [l for l, a in j['open'] if a == m.group(1)]}, False)
            j['disp'] += 1; j['open'].append((ln, m.group(1)))
        m = RX_RETURNED.search(line)
        if m:
            j = self.jobs.setdefault(m.group(1), {'disp': 0, 'ret': 0, 'open': []})
            j['ret'] += 1
            if j['open']:
                j['open'].pop(0)
            if self.stuck and self.stuck[2] == m.group(1):
                self.stuck = None          # it came back: not stuck
        m = RX_SPUSPIN.search(line)
        if m:
            j = self.jobs.get(m.group(1), {'disp': 0, 'ret': 0, 'open': []})
            det = {'image': m.group(1), 'pc': '0x' + m.group(2), 'lr': '0x' + m.group(3), 'ea': '0x' + m.group(4),
                   'dispatched': j['disp'], 'returned': j['ret']}
            if j['ret'] >= self.jmin and j['open'] and not self.stuck:
                self.stuck = (ln, self.now, m.group(1), j['ret'], line, det)
                self._sig('spu_job_stuck', ln, line, det, False)
            else:
                self._sig('spu_spin_info', ln, line, det, False)
        if self.stuck:
            sl, st, img, rc, txt, det = self.stuck
            if (st is not None and self.now is not None and self.now - st >= self.jsec * 1000) or \
               (st is None and ln - sl >= self.jlines):
                if not any(s['signal'] == 'spu_job_stuck' and s['fires'] for s in self.signals):
                    self._sig('spu_job_stuck', sl, txt, dict(det, confirmed_at_line=ln, rule=f'no RETURNED for {self.jsec}s' if st is not None
                              else f'no RETURNED in {self.jlines} lines (log has no clock)'), True)
        self.tick(ln, line)

    def _lrc_close(self):
        c = self.lrc_cur
        if not c or len(c['calls']) < c['pairs']:
            return                    # incomplete dump (log cut mid-dump): never compare it
        p = self.lrc_prev
        if p and c['t'] > p['t']:
            dt = (c['t'] - p['t']) / 1000.0
            rates = sorted(((n - p['calls'].get(k, 0)) / dt, k) for k, n in c['calls'].items())[::-1][:10]
            self.spin_top = [{'nid': f'0x{k[0]:08X}', 'name': NIDS.get(k[0], '?'), 'lr': f'0x{k[1]:08X}', 'tid': k[2], 'per_s': round(r)} for r, k in rates]
            if rates and rates[0][0] >= self.spin and c['progress_before'] == 0:
                self._sig('busy_spin_hle', c['ln'], f"[hle-lrc] dump={p['no']}->{c['no']}", {'top': self.spin_top[:5], 'interval_s': dt,
                          'progress_lines_in_interval': 0}, True)
        self.lrc_prev = c

    def tick(self, ln=None, line=''):
        if self.now is None:
            return
        if self.halt and self.halt[1] is not None and self.now - self.halt[1] >= self.hg * 1000:
            if not any(s['signal'] == 'spu_halt' and s['fires'] for s in self.signals):
                self._sig('spu_halt', self.halt[0], f'halt at LS 0x{self.halt[2]} + {self.hg}s grace', {'pc': '0x' + self.halt[2]}, True)
        if self.loading and self.loading[1] is not None and self.now - self.loading[1] <= self.lhold * 1000:
            lp = self.last_progress[1] if self.last_progress and self.last_progress[1] is not None else self.loading[1]
            ref = max(lp, self.loading[1])
            if self.now - ref >= self.np * 1000 and not any(s['signal'] == 'loading_no_progress' for s in self.signals):
                self._sig('loading_no_progress', ln, f'Now Loading (L{self.loading[0]}) and no progress line for {self.np}s',
                          {'loading_line': self.loading[0], 'last_progress_line': self.last_progress[0] if self.last_progress else None,
                           'last_progress': self.last_progress[2] if self.last_progress else None}, True)

    def result(self):
        self._lrc_close(); self.lrc_cur = None
        return {'fired': self.fired, 'signals': self.signals, 'spin_top': self.spin_top,
                'last_progress': self.last_progress, 'loading': self.loading}


VERSION = 'v2 2026-11-27'


def replay(path, strip_prefix=False, **kw):
    D = Detector(**kw)
    with open(path, 'rb') as fh:
        for i, b in enumerate(fh, 1):
            line = b.replace(b'\x00', b'').decode('utf-8', 'replace').rstrip('\r\n')
            ln = i
            if strip_prefix:
                m = re.match(r'^(\d+):(.*)$', line)
                if m:
                    ln, line = int(m.group(1)), m.group(2)
            D.feed(ln, line)
    return D.result()


def show(R):
    f = R['fired']
    print('FIRST FIRE:', f"{f['signal']} at L{f['line']} t={f['t_ms']} {f['detail']}" if f else 'none')
    seen = {}
    for s in R['signals']:
        k = (s['signal'], s['fires'])
        if k not in seen:
            seen[k] = s
            print(f"  {'FIRE' if s['fires'] else 'seen'} {s['signal']:20s} L{s['line']} t={s['t_ms']} :: {s['text'][:150]}")
    if R['spin_top']:
        print('  hottest HLE call sites (calls/s, last two [hle-lrc] dumps):')
        for x in R['spin_top'][:5]:
            print(f"    {x['per_s']:>8}/s {x['name']}({x['nid']}) lr={x['lr']} tid={x['tid']}")


def selftest():
    import os, tempfile
    D = Detector(job_min_returns=3, job_stuck_lines=5)
    seq = []
    for i in range(4):
        seq += ["[spu_workload] dispatch HIT (async) fp=0x00010000 args=0x11058B00 image=437063289 -> spawning thread",
                "[spu_workload] async image=437063289 RETURNED rc=0 (job ran to completion, did not loop)"]
    seq += ["[spu_workload] dispatch HIT (async) fp=0x00010000 args=0x16FA3A80 image=361927206 -> spawning thread",
            "[spu_workload] dispatch HIT (async) fp=0x00010000 args=0x16FA3A80 image=361927206 -> spawning thread",
            "[spu_workload] dispatch HIT (async) fp=0x00010000 args=0x11058B00 image=437063289 -> spawning thread",
            "[spu-spin] img=361927206 pc=0x0B42C lr=0x0B420 GETLLAR ea=0x16C53F80 x4M; line: 0 0 0 0",
            "[spu-spin] img=437063289 pc=0x0833C lr=0x07470 GETLLAR ea=0x11095F80 x4M; line: 0CFC0000 00000CFC 0CFC0000 00000CFC"]
    seq += ["[WAIT] event_queue_receive(q=1 timeout=9000000) tid=10 cia=0x0 lr=0x0"] * 6
    for i, l in enumerate(seq, 1):
        D.feed(i, l)
    R2 = D.result(); f2 = R2['fired']
    ok2 = f2 and f2['signal'] == 'spu_job_stuck' and f2['line'] == 13 and \
        any(s['signal'] == 'task_reuse_unreturned' for s in R2['signals']) and R2['last_progress'][0] == 11
    lines = ["[vm-sum] t=1000 union=2 groups: g1=2",
             "[fs] open '/dev_hdd1/cache/BLUS30471/5444' -> fd 6",
             "[sfww] r4 0x111A1784 FF->FD w1 fn=0x00058974 lr=0x00059590 tid=17 t=1500 ch:",
             "[spu] img=391227015 branched into unlifted LS 0x31C20 (lr=0x31A84) -- ending the job",
             "      LS[0x31C20]: 7F003200 1200089A 0C003289",
             "[cellSpurs] EventFlagWait BLOCKED tid=1 4s on pattern 0x0001 (mode=AND, bits=0x0000) flagEA=0x00DBA900 -- w",
             "[vm-sum] t=7000 union=2",
             "[cellSpurs] EventFlagWait BLOCKED tid=1 5s on pattern 0x0001 (mode=AND, bits=0x0000) flagEA=0x00DBA900 -- w",
             "[vm-sum] t=30000 union=2"]
    fd, p = tempfile.mkstemp(); os.write(fd, ('\n'.join(lines) + '\n').encode()); os.close(fd)
    R = replay(p); os.unlink(p)
    names = [s['signal'] for s in R['signals'] if s['fires']]
    ok = names[:3] == ['spu_halt', 'ef_blocked', 'loading_no_progress'] and R['fired']['line'] == 4
    ok &= bool(ok2)
    ok &= halt_op(0x7F003200) and not halt_op(0x42005014) and not halt_op(0x35000000)
    print('SELFTEST', 'OK' if ok else f'FAIL {names}')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('logs', nargs='*'); ap.add_argument('--strip-prefix', action='store_true')
    ap.add_argument('--no-progress-sec', type=int, default=20); ap.add_argument('--ef-blocked-sec', type=int, default=5)
    ap.add_argument('--halt-grace-sec', type=int, default=5); ap.add_argument('--spin-calls-per-sec', type=int, default=40000)
    ap.add_argument('--job-min-returns', type=int, default=50); ap.add_argument('--job-stuck-sec', type=int, default=10)
    ap.add_argument('--job-stuck-lines', type=int, default=200)
    ap.add_argument('--json'); ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    out = {}
    for p in a.logs:
        print('==', p, '(watchdog_logic', VERSION + ')')
        R = replay(p, a.strip_prefix, no_progress_sec=a.no_progress_sec, ef_blocked_sec=a.ef_blocked_sec,
                   halt_grace_sec=a.halt_grace_sec, spin_calls_per_sec=a.spin_calls_per_sec,
                   job_min_returns=a.job_min_returns, job_stuck_sec=a.job_stuck_sec, job_stuck_lines=a.job_stuck_lines)
        show(R); out[p] = R
    if a.json:
        json.dump(out, open(a.json, 'w'), indent=1, default=str)
    return 0


if __name__ == '__main__':
    sys.exit(main())

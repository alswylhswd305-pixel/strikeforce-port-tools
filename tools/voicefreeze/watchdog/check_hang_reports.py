#!/usr/bin/env python3
"""Box-side checker for hang reports saved by sf_hang_watchdog.ps1 (stdlib only).

For each hang_* folder (or a parent folder holding several):
  - prints which signal fired, at which log line, and all signals seen
  - re-runs the detection rules (watchdog_logic.py) on last_2000.log as a cross-check
  - runs voice_freeze_analyzer.py on last_2000.log + post_close_tail.log (ranked candidates)
  - runs race_check.py on dumps/sfrace_*.log if the SF_RACE ring dump is there
  - reports the hottest spin locations: HLE call rates between the last two [hle-lrc] dumps,
    [spu-spin] lines, [pcsample] SPU pc histogram, [samp]/[samp-tid] PPU sampler tops, threads_cpu.txt
Writes <hang dir>/check.md and prints a summary.

  python3 check_hang_reports.py /workspace/sf-shared/testloop/hangwatch [more dirs...]
  python3 check_hang_reports.py --selftest
"""
import collections, glob, io, json, os, re, sys, contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import watchdog_logic as WL                      # noqa: E402
import voice_freeze_analyzer as VFA              # noqa: E402
import race_check as RC                          # noqa: E402

RX_PCS = re.compile(r'\[pcsample\] slot=(\d+) img=(-?\d+) spu=0x([0-9A-Fa-f]+) pc=0x([0-9A-Fa-f]+) lr=0x([0-9A-Fa-f]+)')
RX_SAMP_FN = re.compile(r'^\[samp\]\s+([\d.]+)%\s+((?:func_|spu_LS_)[0-9A-Fa-f]+)\s+\((\d+)\)')
RX_SAMP_TID = re.compile(r'^\[samp-tid\] tid=(\d+) (.*)$')
RX_THR = re.compile(r'(\d+):(\d+)ms')


def rd(p):
    with open(p, 'rb') as fh:
        return fh.read().replace(b'\x00', b'').decode('utf-8-sig', 'replace').splitlines()


def hang_dirs(paths):
    out = []
    for p in paths:
        if os.path.exists(os.path.join(p, 'hang_report.json')):
            out.append(p)
        else:
            out += sorted(os.path.dirname(x) for x in glob.glob(os.path.join(p, '**', 'hang_report.json'), recursive=True))
    return out


def spin_locations(d):
    R = {}
    lrc = os.path.join(d, 'hle_lrc_last2.log')
    if os.path.exists(lrc):
        D = WL.Detector(spin_calls_per_sec=10 ** 12)
        for i, l in enumerate(rd(lrc), 1):
            D.feed(i, l)
        D._lrc_close()
        R['hle_rates'] = D.spin_top
    lines = []
    for n in ('last_2000.log', 'post_close_tail.log'):
        if os.path.exists(os.path.join(d, n)):
            lines += rd(os.path.join(d, n))
    R['spu_spin'] = [l for l in lines if l.startswith('[spu-spin]')][-10:]
    pcs = collections.Counter()
    for l in lines:
        m = RX_PCS.search(l)
        if m:
            pcs[(m.group(2), '0x' + m.group(4).upper(), '0x' + m.group(5).upper())] += 1
    R['pcsample_top'] = [{'img': k[0], 'pc': k[1], 'lr': k[2], 'n': n} for k, n in pcs.most_common(10)]
    last = [i for i, l in enumerate(lines) if l.startswith('[samp] --- report')]
    blk = lines[last[-1]:] if last else []
    R['samp_top'] = [{'pct': m.group(1), 'fn': m.group(2), 'n': int(m.group(3))} for m in (RX_SAMP_FN.search(l) for l in blk) if m][:12]
    R['samp_tid'] = [l for l in blk if RX_SAMP_TID.search(l)][:20]
    thr = os.path.join(d, 'threads_cpu.txt')
    if os.path.exists(thr):
        tot = collections.Counter(); n = 0
        for l in rd(thr):
            n += 1
            for t, ms in RX_THR.findall(l):
                tot[t] += int(ms)
        R['threads_cpu_ms_per_s'] = [{'host_tid': t, 'ms_per_s': round(v / max(n, 1))} for t, v in tot.most_common(8)]
    return R


def check_one(d):
    try:
        rep = json.loads('\n'.join(rd(os.path.join(d, 'hang_report.json'))))
    except Exception as e:
        rep = {'error': str(e)}
    out = {'dir': d, 'report': rep}
    logs = [os.path.join(d, n) for n in ('last_2000.log', 'post_close_tail.log') if os.path.exists(os.path.join(d, n))]
    if logs:
        R = WL.replay(logs[0]); f = R['fired']
        out['recheck'] = {'fired': f and {k: f[k] for k in ('signal', 'line', 'text')},
                          'signals': sorted({s['signal'] for s in R['signals']})}
        with contextlib.redirect_stdout(io.StringIO()):
            VR, _ = VFA.run(logs, None, os.path.join(d, 'check_vf'), 128, 100, 7, 17)
        out['analyzer'] = [{'id': c['id'], 'points': c['points'], 'title': c['title'][:140], 'evidence': c['evidence'][:4]} for c in VR['candidates']]
    sf = sorted(glob.glob(os.path.join(d, 'dumps', '**', 'sfrace_*.log'), recursive=True))
    if sf:
        dma, ww, ef, halts = RC.load(sf)
        RR = RC.analyze(dma, ww, ef, halts)
        out['race'] = {'files': sf, 'verdict': RR.get('verdict'), 'n_dma': RR.get('n_dma'), 'n_ww': RR.get('n_ww')}
    ovl = sorted(glob.glob(os.path.join(d, 'dumps', '**', 'ovl_*.bin'), recursive=True))
    out['ovl_bins'] = [os.path.relpath(x, d) for x in ovl]
    out['spin'] = spin_locations(d)
    return out


def write_md(o):
    rep = o['report']; f = rep.get('fired') or {}
    L = [f"# hang check: {os.path.basename(o['dir'])}", '',
         f"- pid {rep.get('pid')}  exe {rep.get('exe')}  when {rep.get('when')}",
         f"- FIRED: **{f.get('signal')}** at log line {f.get('line')}: `{(f.get('text') or '')[:200]}`",
         f"- signals seen: {sorted({s.get('signal') for s in rep.get('signals', [])})}",
         f"- SPU jobs dispatched but not RETURNED (v2 report): {rep.get('jobs_open') or 'n/a'}",
         f"- actions: {rep.get('actions')}"]
    if 'recheck' in o:
        L.append(f"- re-check on last_2000.log: {o['recheck']['fired'] and o['recheck']['fired']['signal']} (signals {o['recheck']['signals']})")
    L += ['', '## where it spins']
    sp = o['spin']
    for x in sp.get('hle_rates', [])[:8]:
        L.append(f"- HLE {x['per_s']}/s {x['name']}({x['nid']}) lr={x['lr']} tid={x['tid']}")
    for x in sp.get('threads_cpu_ms_per_s', []):
        L.append(f"- host thread {x['host_tid']}: {x['ms_per_s']} ms CPU per s")
    for x in sp.get('pcsample_top', []):
        L.append(f"- SPU img {x['img']} pc {x['pc']} lr {x['lr']}: {x['n']} samples")
    for l in sp.get('spu_spin', []):
        L.append(f"- `{l[:200]}`")
    for x in sp.get('samp_top', []):
        L.append(f"- PPU sampler {x['fn']} {x['pct']}% ({x['n']})")
    for l in sp.get('samp_tid', []):
        L.append(f"- `{l[:200]}`")
    if not any(sp.get(k) for k in ('hle_rates', 'pcsample_top', 'spu_spin', 'samp_top', 'samp_tid')):
        L.append('- no sampler data in the saved lines (run with SF_HLE_LRLOG=1, SPU_PCSAMPLE=2, PS3_SAMPLE=5)')
    L += ['', '## analyzer candidates (points = evidence count, not a probability)']
    for c in o.get('analyzer', []):
        L.append(f"- {c['id']} ({c['points']}) {c['title']}")
        L += [f"  - {e}" for e in c['evidence']]
    if 'race' in o:
        L += ['', '## race_check (SF_RACE dump)'] + [f"- {v}" for v in (o['race']['verdict'] or [])]
    if o['ovl_bins']:
        L += ['', '## overlay dumps'] + [f"- {x}" for x in o['ovl_bins']]
    open(os.path.join(o['dir'], 'check.md'), 'w').write('\n'.join(L) + '\n')
    return L


def selftest():
    import tempfile, shutil
    src = '/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log'
    if not os.path.exists(src):
        print('SELFTEST SKIP (no saved log)'); return 0
    lines = rd(src)
    d = tempfile.mkdtemp(prefix='hang_selftest_')
    open(os.path.join(d, 'last_2000.log'), 'w').write('\n'.join(lines[76838 - 2000:76838]) + '\n')
    # two real consecutive [hle-lrc] dumps from the hung state
    hdr = [i for i, l in enumerate(lines) if l.startswith('[hle-lrc] dump=17 ') or l.startswith('[hle-lrc] dump=18 ')]
    blk = [l for l in lines[hdr[0]:] if l.startswith('[hle-lrc]')][:2 * 1182]
    open(os.path.join(d, 'hle_lrc_last2.log'), 'w').write('\n'.join(blk) + '\n')
    open(os.path.join(d, 'threads_cpu.txt'), 'w').write('sample 1: 42016:3ms 27184:719ms\nsample 2: 27184:812ms\n')
    json.dump({'pid': 1, 'fired': {'signal': 'ef_blocked', 'line': 76814, 'text': 'x'}, 'signals': [], 'actions': []}, open(os.path.join(d, 'hang_report.json'), 'w'))
    o = check_one(d); write_md(o)
    ok = o['recheck']['fired']['signal'] in ('spu_halt', 'ef_blocked')
    ok &= o['spin']['hle_rates'][0]['tid'] == 17 and o['spin']['hle_rates'][0]['per_s'] > 60000
    ok &= o['analyzer'][0]['id'] == 'C1'
    ok &= o['spin']['threads_cpu_ms_per_s'][0]['host_tid'] == '27184'
    print('SELFTEST', 'OK' if ok else 'FAIL', json.dumps({'recheck': o['recheck']['fired']['signal'], 'top': o['spin']['hle_rates'][0], 'c': o['analyzer'][0]['id']}))
    shutil.rmtree(d)
    return 0 if ok else 1


def main():
    a = sys.argv[1:]
    if not a or a[0] == '--selftest':
        return selftest()
    ds = hang_dirs(a)
    if not ds:
        print('no hang_report.json under', a); return 1
    for d in ds:
        o = check_one(d)
        print('\n'.join(write_md(o)[:14])); print(f'-> {d}/check.md\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())

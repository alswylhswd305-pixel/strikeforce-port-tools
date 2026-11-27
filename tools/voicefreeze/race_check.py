#!/usr/bin/env python3
"""race_check.py - checks the SF-RACE log-only run (see race_run_spec.md). Stdlib only.

Reads stderr (or the SF_RACE_LOG file) containing:
  [sfrace] q=<ns> img=<id> spu=<ctx> pc=0x<pc> dir=GET|PUT ea=0x<ea> lsa=0x<lsa> size=<n> tag=<t> h=<hash> [pre=<hash>] [sub=<hash>] [m358=<word>] [d=<hex bytes>]
  [sfww] r<i> 0x<addr> <old>-><new> w<n> fn=0x.. lr=0x.. tid=<tid> t=<ms> q=<ns> ch:...
  [sfrace-ef] q=<ns> who=SPU|PPU-WAKE flag=0x00DBA900 bits=0x.. tid=<tid>
  [sfrace-halt] q=<ns> img=.. pc=0x.. insn=<word> op=<name> ra=r<n> ra_val=<4 words> r89=.. r92=.. r93=.. src_get=<pc/ea/q/hash or none>
Checks (all read-only):
  L  lost update   : a PPU store to [rec+0x800, rec+0x930) between the record GET and its PUT (pre-PUT bytes != GET bytes)
  M  mismatch      : in one pass a voice is in snapshot group g while its live mask (param+0x358) lacks bit g  -> path-1 allocation (no de-dup)
  V  visits        : record GETs per pass, repeats, passes > 176 / >= 201 visits
  W  window        : tid-17 stores to masks / table / records landing inside a pass (between the pass's counts GET and the next one)
  E  flag order    : whether the SPU sets 0xDBA900 before or after the pass's last record PUT
Usage: python3 race_check.py LOG [LOG...] [--tid 17] [--json out.json]
       python3 race_check.py --selftest
"""
import argparse, collections, json, re, sys

REC_BASE, REC_SZ, NREC = 0x11136A80, 0x930, 180
PAR_LO, PAR_HI, PAR_SZ = 0x11103990, 0x11136A80, 0x490
SNAP_BM, SNAP_CNT = 0x111A2000, 0x111A2800
TAB_LO, TAB_HI = 0x111A1780, 0x111A2000

RX_RACE = re.compile(r'\[sfrace\] q=(\d+) img=(\d+) spu=(\w+) pc=0x([0-9A-Fa-f]+) dir=(GET|PUT) ea=0x([0-9A-Fa-f]+) '
                     r'lsa=0x([0-9A-Fa-f]+) size=(\d+) tag=(\d+) h=([0-9a-fA-F]+)(.*)$')
RX_WW = re.compile(r'\[sfww\] r(\d+) 0x([0-9A-F]+) ([0-9A-F]+)->([0-9A-F]+) w(\d) fn=0x([0-9A-F]+) lr=0x([0-9A-F]+) '
                   r'tid=(\d+) t=(\d+) q=(\d+)')
RX_EF = re.compile(r'\[sfrace-ef\] q=(\d+) who=(\S+) flag=0x([0-9A-F]+) bits=0x([0-9A-F]+)(?: tid=(\d+))?')
RX_HALT = re.compile(r'\[sfrace-halt\] q=(\d+) (.*)$')
RX_SPUHALT = re.compile(r'\[SPU-HALT\] img=(\d+) pc=0x([0-9A-F]+)(.*)$')


def kv(s):
    return dict(re.findall(r'(\w+)=([0-9A-Za-z_./:@-]+)', s))


def load(paths):
    dma, ww, ef, halts = [], [], [], []
    for p in paths:
        with open(p, 'rb') as fh:
            for ln, b in enumerate(fh, 1):
                line = b.replace(b'\x00', b'').decode('utf-8', 'replace').rstrip()
                ref = f'{p.split("/")[-1]}:{ln}'
                m = RX_RACE.search(line)
                if m:
                    g = m.groups(); ex = kv(g[10])
                    dma.append({'q': int(g[0]), 'img': g[1], 'spu': g[2], 'pc': int(g[3], 16), 'dir': g[4], 'ea': int(g[5], 16),
                                'lsa': int(g[6], 16), 'size': int(g[7]), 'tag': int(g[8]), 'h': g[9], 'pre': ex.get('pre'),
                                'sub': ex.get('sub'), 'm358': int(ex['m358'], 16) if 'm358' in ex else None,
                                'd': ex.get('d'), 'ref': ref})
                    continue
                m = RX_WW.search(line)
                if m:
                    g = m.groups()
                    ww.append({'addr': int(g[1], 16), 'old': int(g[2], 16), 'new': int(g[3], 16), 'w': int(g[4]), 'fn': int(g[5], 16),
                               'lr': int(g[6], 16), 'tid': int(g[7]), 'q': int(g[9]), 'ref': ref})
                    continue
                m = RX_EF.search(line)
                if m:
                    ef.append({'q': int(m.group(1)), 'who': m.group(2), 'flag': int(m.group(3), 16), 'bits': int(m.group(4), 16), 'ref': ref})
                    continue
                m = RX_HALT.search(line) or RX_SPUHALT.search(line)
                if m:
                    halts.append({'ref': ref, 'raw': line[:300], 'q': int(m.group(1)) if line.startswith('[sfrace-halt]') else None})
    dma.sort(key=lambda x: x['q']); ww.sort(key=lambda x: x['q']); ef.sort(key=lambda x: x['q'])
    return dma, ww, ef, halts


def rec_of(ea):
    k, off = divmod(ea - REC_BASE, REC_SZ)
    return (k, off) if 0 <= k < NREC else (None, None)


def analyze(dma, ww, ef, halts, tid=17):
    R = {'n_dma': len(dma), 'n_ww': len(ww), 'n_ef': len(ef), 'halts': halts[:4]}
    # ---- passes: start at each GET of the counts snapshot
    starts = [d for d in dma if d['dir'] == 'GET' and d['ea'] == SNAP_CNT]
    bounds = [s['q'] for s in starts] + [float('inf')]
    passes = []
    for i, s in enumerate(starts):
        q0, q1 = bounds[i], bounds[i + 1]
        passes.append({'i': i, 'q0': q0, 'q1': q1, 'ref': s['ref'], 'cnt': s.get('d')})
    def pass_of(q):
        lo, hi = 0, len(passes) - 1
        if not passes or q < passes[0]['q0']:
            return None
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if passes[mid]['q0'] <= q: lo = mid
            else: hi = mid - 1
        return lo
    # ---- V: visits per pass
    per = collections.defaultdict(list)
    for d in dma:
        if d['dir'] == 'GET' and d['size'] == REC_SZ:
            k, off = rec_of(d['ea'])
            if k is not None and off == 0:
                pi = pass_of(d['q'])
                if pi is not None: per[pi].append((k, d))
    vis = []
    for pi, L in per.items():
        ids = [k for k, _ in L]
        rep = len(ids) - len(set(ids))
        vis.append({'pass': pi, 'visits': len(ids), 'distinct': len(set(ids)), 'repeats': rep, 'first': L[0][1]['ref'], 'last': L[-1][1]['ref'],
                    'est_last_page': 7 + 2 * (len(ids) - 1) if ids else 0})
    vis.sort(key=lambda x: x['pass'])
    R['V_max_visits'] = max(vis, key=lambda x: x['visits']) if vis else None
    R['V_passes_over_176'] = [v for v in vis if v['visits'] > 176][:20]
    R['V_passes_with_repeats'] = [v for v in vis if v['repeats']][:20]
    # ---- M: mask vs snapshot bitmap mismatch, per pass
    mism = []
    for p in passes:
        bm = collections.defaultdict(dict)   # group -> {byteoff: byte}
        masks = {}
        for d in dma:
            if d['q'] < p['q0'] or d['q'] >= p['q1'] or d['dir'] != 'GET':
                continue
            if SNAP_BM <= d['ea'] < SNAP_CNT and d.get('d'):
                raw = bytes.fromhex(d['d'])
                for j, byte in enumerate(raw):
                    off = d['ea'] - SNAP_BM + j
                    bm[off // 64][off % 64] = byte
            elif PAR_LO <= d['ea'] < PAR_HI and d['m358'] is not None:
                masks[d['ea']] = d
        # pair param GETs with the next record GET to get the voice id
        recs = [x for x in per.get(p['i'], [])]
        pairs = {}
        par_sorted = sorted(masks.values(), key=lambda x: x['q'])
        ri = 0
        for pd in par_sorted:
            while ri < len(recs) and recs[ri][1]['q'] < pd['q']:
                ri += 1
            if ri < len(recs):
                pairs[recs[ri][0]] = pd
        for v, pd in pairs.items():
            groups = [g for g in bm if bm[g].get(v // 8, 0) >> (v % 8) & 1]
            missing = [g for g in groups if not (pd['m358'] >> g) & 1]
            if missing:
                mism.append({'pass': p['i'], 'voice': v, 'snap_groups': groups, 'mask': hex(pd['m358']), 'path1_groups': missing, 'ref': pd['ref']})
    R['M_mismatches'] = mism[:50]
    R['M_count'] = len(mism)
    # ---- L: lost update between record GET and record+0x800 PUT
    lost = []
    lastget = {}
    for d in dma:
        k, off = rec_of(d['ea'])
        if k is None:
            continue
        if d['dir'] == 'GET' and off == 0 and d['size'] == REC_SZ:
            lastget[(d['spu'], k)] = d
        elif d['dir'] == 'PUT' and off == 0x800:
            g = lastget.get((d['spu'], k))
            if not g:
                continue
            between = [w for w in ww if g['q'] < w['q'] < d['q'] and REC_BASE + k * REC_SZ + 0x800 <= w['addr'] < REC_BASE + (k + 1) * REC_SZ]
            if (g.get('sub') and d.get('pre') and g['sub'] != d['pre']) or between:
                lost.append({'voice': k, 'get': g['ref'], 'put': d['ref'], 'get_sub': g.get('sub'), 'put_pre': d.get('pre'),
                             'ppu_writes_between': [f"{w['ref']} tid{w['tid']} 0x{w['addr']:X} {w['old']:X}->{w['new']:X} lr=0x{w['lr']:X}" for w in between[:5]]})
    R['L_lost_updates'] = lost[:50]
    R['L_count'] = len(lost)
    # ---- W: tid stores inside passes
    win = collections.Counter(); ex = []
    for w in ww:
        if w['tid'] != tid:
            continue
        pi = pass_of(w['q'])
        if pi is None or w['q'] >= passes[pi]['q1']:
            continue
        a = w['addr']
        kind = 'param+0x358' if PAR_LO <= a < PAR_HI and (a - PAR_LO) % PAR_SZ in range(0x358, 0x35C) else \
               'param' if PAR_LO <= a < PAR_HI else 'record' if REC_BASE <= a < REC_BASE + NREC * REC_SZ else \
               'table' if TAB_LO <= a < TAB_HI else 'other'
        win[kind] += 1
        if kind in ('param+0x358', 'table') and len(ex) < 30:
            ex.append(f"{w['ref']} pass {pi} {kind} 0x{a:X} {w['old']:X}->{w['new']:X} lr=0x{w['lr']:X}")
    R['W_tid_stores_inside_passes'] = dict(win)
    R['W_examples'] = ex
    # ---- E: flag set vs last record PUT of the pass
    eo = collections.Counter(); eex = []
    for e in ef:
        if e['who'] != 'SPU' or e['flag'] != 0x00DBA900:
            continue
        pi = pass_of(e['q'])
        if pi is None:
            continue
        later = [d for d in dma if passes[pi]['q0'] <= d['q'] < passes[pi]['q1'] and d['dir'] == 'PUT' and d['q'] > e['q']]
        k = 'set_before_pass_end' if later else 'set_after_last_put'
        eo[k] += 1
        if later and len(eex) < 10:
            eex.append(f"{e['ref']} set while {len(later)} PUTs of pass {pi} still to come (first {later[0]['ref']})")
    R['E_flag_order'] = dict(eo); R['E_examples'] = eex
    # verdict
    v = []
    if R['M_count']: v.append(f"M: {R['M_count']} voice/pass cases where the live mask lacks a group the snapshot has (path-1 double allocation)")
    if R['L_count']: v.append(f"L: {R['L_count']} record PUTs overwrote PPU changes made after the GET (lost update)")
    if R['V_passes_over_176']: v.append(f"V: {len(R['V_passes_over_176'])} passes with > 176 visits (ring overflow)")
    if eo.get('set_before_pass_end'): v.append(f"E: SPU set 0xDBA900 before its pass ended {eo['set_before_pass_end']} times (tid 7 can run during a pass)")
    R['verdict'] = v or ['no race signature found in these logs']
    return R


def selftest():
    q = 1_000_000
    L = []
    def race(dirn, ea, size, pc=0x6BC0, extra=''):
        nonlocal q; q += 1000
        L.append(f"[sfrace] q={q} img=391227015 spu=0 pc=0x{pc:05X} dir={dirn} ea=0x{ea:08X} lsa=0x3C180 size={size} tag=1 h=aa{extra}")
    # pass 0: snapshot says voice 5 in groups 1,2,3 ; mask 0x8 (only g3) -> path1 in g1,g2
    race('GET', SNAP_CNT, 128, extra=' d=' + '00000003' * 32)
    bm = bytearray(64 * 4)
    for g in (1, 2, 3): bm[g * 64 + 0] = 1 << 5
    race('GET', SNAP_BM, 256, extra=' d=' + bm.hex())
    race('GET', PAR_LO + 5 * PAR_SZ, 1168, extra=' m358=00000008')
    race('GET', REC_BASE + 5 * REC_SZ, REC_SZ, extra=' sub=11')
    q += 10; L.append(f"[sfww] r1 0x{REC_BASE + 5 * REC_SZ + 0x804:08X} 2->3 w4 fn=0x5915C lr=0x59590 tid=17 t=1 q={q}")
    race('PUT', REC_BASE + 5 * REC_SZ + 0x800, 304, pc=0x71EC, extra=' pre=22')
    q += 10; L.append(f"[sfrace-ef] q={q} who=SPU flag=0x00DBA900 bits=0x0001")
    race('PUT', 0x111EF580, 4096, pc=0xA3A0)
    race('GET', SNAP_CNT, 128, extra=' d=' + '00000001' * 32)
    import tempfile, os
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 's.log'); open(p, 'w').write('\n'.join(L) + '\n')
        R = analyze(*load([p]))
    ok = R['M_count'] == 1 and R['M_mismatches'][0]['path1_groups'] == [1, 2] and R['L_count'] == 1 \
        and R['E_flag_order'].get('set_before_pass_end') == 1 and R['W_tid_stores_inside_passes'].get('record') == 1
    print(json.dumps({k: R[k] for k in ('M_count', 'L_count', 'E_flag_order', 'W_tid_stores_inside_passes', 'verdict')}, indent=1))
    print('SELFTEST', 'OK' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('logs', nargs='*'); ap.add_argument('--tid', type=int, default=17); ap.add_argument('--json')
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    if not a.logs: ap.error('give logs')
    R = analyze(*load(a.logs), tid=a.tid)
    if a.json: json.dump(R, open(a.json, 'w'), indent=1, default=str)
    for k in ('n_dma', 'n_ww', 'n_ef', 'V_max_visits', 'V_passes_over_176', 'V_passes_with_repeats', 'M_count', 'M_mismatches',
              'L_count', 'L_lost_updates', 'W_tid_stores_inside_passes', 'W_examples', 'E_flag_order', 'E_examples', 'halts', 'verdict'):
        v = R[k]
        if isinstance(v, list): v = v[:12]
        print(f'{k}: {json.dumps(v, default=str)}')

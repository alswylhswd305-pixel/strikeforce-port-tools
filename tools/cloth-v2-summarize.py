#!/usr/bin/env python3
"""Read-only: summarize a 1775_clothv2 extract (from extract_clothv2.ps1) into cloth-v2-logs.txt.
usage: cloth-v2-summarize.py <extract.txt> [out=/workspace/sf-shared/cloth-v2-logs.txt]"""
import sys, re, collections
src = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else '/workspace/sf-shared/cloth-v2-logs.txt'
L = open(src, errors='replace').read().splitlines()
hdr = L[0] if L else ''
def grab(pat, n=None):
    r = [l for l in L if pat in l]
    return r if n is None else r[:n]
cloth_q = {'0x14C02900', '0x14C02980'}
sec = grab('[clothv2] sec ')
o = [f'# Cloth V2 (build 1775_clothv2, SPURS_CLOTHV2=1) log extract', hdr, '']
def sect(t, rows, cap=200):
    o.append('-' * 79); o.append(f'{t}  (count={len(rows)}; showing up to {cap})')
    o.extend(rows[:cap]);
    if len(rows) > cap: o.append(f'... {len(rows)-cap} more; last 20:'); o.extend(rows[-20:])
    o.append('')
sect('Hooks banner', grab('[clothv2] SPURS_CLOTHV2=1'), 5)
sect('Init (item 3) + spurs wkl table (item 7)', grab('[clothv2] init') + grab('[clothv2] wkl '), 80)
sect('Attach (item 3)', grab('[clothv2] attach'), 40)
sect('Cloth task WAIT_SIGNAL entries (items 2/5)', [l for l in L if '[clothv2] wait' in l and ('CLOTH' in l or 'cloth-q' in l)], 120)
waits = grab('[clothv2] wait ts=')
sect('All WAIT_SIGNAL first-entry per task (item 2)', [l for l in waits if 'CLOTH' not in l], 120)
sect('waiter-in lines (which queue holds the token)', grab('waiter-in'), 120)
sect('PushBody dir!=2 (item 6)', grab('[clothv2] push-dir!=2') + grab('[clothv2] push-early'), 120)
sect('Wake attempts (items 1/5)', grab('[clothv2] wake '), 120)
sect('No-waiter pushes (item 1)', grab('[clothv2] nowaiter'), 60)
sect('SPU-side commits on dir!=2 queues', grab('[clothv2] spu-commit'), 120)
sect('Cloth signalled-line commits', grab('[clothv2] cloth-sigline'), 80)
sect('Per-second counters: cloth queues', [l for l in sec if any(q in l for q in cloth_q)], 200)
sect('Per-second counters: cloth taskset signalled word', [l for l in sec if 'sec cloth ts=' in l], 120)
sect('Per-second cloth PUTs (item 8)', [l for l in sec if 'cloth-put' in l], 200)
sect('Per-second counters: other queues (first 120)', [l for l in sec if 'sec q=' in l and not any(q in l for q in cloth_q)], 120)
sect('sig-stats lines naming the cloth taskset', [l for l in grab('[sig-stats]') if '14C02A80' in l], 60)
sect('Interpreter stats for cloth image (img=0x00002328)', grab('img=0x00002328'), 60)
sect('Legacy [spu_workload]/[taskset] cloth lines', [l for l in L if '14C02A80' in l and '[clothv2]' not in l], 80)
sect('VP_ATTRS lines (vertex attribute layouts; not bone constants)', grab('[VPATTR]'), 60)
# quick answers
tot = collections.Counter()
for l in sec:
    m = re.search(r'q=(0x[0-9A-F]+).*ppu_push=(\d+).*wake=(\d+).*nowaiter=(\d+).*spu_commit=(\d+) spu_h5adv=(\d+) spu_h1adv=(\d+)', l)
    if m and m.group(1) in cloth_q:
        q = m.group(1)
        for k, v in zip(('ppu_push', 'wake', 'nowaiter', 'spu_commit', 'spu_h5adv', 'spu_h1adv'), m.groups()[1:]): tot[(q, k)] += int(v)
o.append('=' * 79); o.append('Totals over the per-second counters for the cloth-adjacent queues:')
for q in sorted(cloth_q):
    o.append('  ' + q + ': ' + ', '.join(f'{k}={tot[(q,k)]}' for k in ('ppu_push', 'wake', 'nowaiter', 'spu_commit', 'spu_h5adv', 'spu_h1adv')))
open(out, 'w').write('\n'.join(o) + '\n'); print(out, len(o))

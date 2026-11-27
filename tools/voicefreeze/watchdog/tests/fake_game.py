#!/usr/bin/env python3
"""Box-only live test harness for sf_hang_watchdog.ps1 (pwsh on Linux): plays a real saved log into a new
log file like the game would, then hangs either by busy-spinning (CPU, heartbeat lines only) or by stopping
after the halt/EF lines. Usage: fake_game.py SRC_LOG OUT_LOG --upto N [--spin] [--hb-every 1.0] [--rate 20000]"""
import sys, time, argparse, os
ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('out'); ap.add_argument('--upto', type=int, required=True)
ap.add_argument('--spin', action='store_true'); ap.add_argument('--hb-every', type=float, default=1.0); ap.add_argument('--rate', type=int, default=20000)
ap.add_argument('--tail-from', type=int, default=0)
a = ap.parse_args()
src = open(a.src, 'rb').read().split(b'\n')
with open(a.out, 'wb', buffering=0) as o:
    for i, l in enumerate(src[:a.upto]):
        o.write(l + b'\n')
        if i % a.rate == 0: time.sleep(0.05)
    t = int(time.time() * 1000) % 1000000000
    k = 0; last = time.time()
    while True:                       # hung: only heartbeat lines from here on
        if a.spin:
            x = 0
            for _ in range(200000): x += 1     # burn CPU
        else:
            time.sleep(0.05)
        if time.time() - last >= a.hb_every:
            last = time.time(); k += 1
            o.write(b'[vm-sum] t=%d union=130 groups: g1=130 g2=121 g3=130 st7650_nonzero=130\n' % (148000000 + k * 1000))
            if a.tail_from:
                j = a.tail_from + k
                if j < len(src): o.write(src[j] + b'\n')

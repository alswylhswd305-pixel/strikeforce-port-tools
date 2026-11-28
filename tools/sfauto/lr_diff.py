#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""lr_diff.py -- first divergence between a WORKING and a FAILING run, from the "[hle-lr] new nid=.. lr=.. tid=.."
lines (SF_HLE_LRLOG=1: one line the first time a (import, call-site) pair is seen).

  python sfauto/tools/lr_diff.py WORKING_stderr.log FAILING_stderr.log [FAILING2.log ...] [--tid 1] [--after-line N]

Prints the call sites the working run reached that no failing run reached, in the order the working run
reached them.  The first rows are the earliest point where the failing runs left the working path.
Read only.
"""
import argparse, re

PAT = re.compile(r"\[hle-lr\] new nid=(0x[0-9A-Fa-f]+) lr=(0x[0-9A-Fa-f]+) tid=(\d+) r3=(0x[0-9A-Fa-f]+) r4=(0x[0-9A-Fa-f]+)")


def sites(path, tid):
    out = {}
    for i, ln in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
        if "[hle-lr] new" not in ln:
            continue
        m = PAT.search(ln)
        if m and (tid is None or int(m.group(3)) == tid):
            out.setdefault((m.group(1).upper(), int(m.group(2), 16)), (i, m.group(4), m.group(5)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("working"); ap.add_argument("failing", nargs="+")
    ap.add_argument("--tid", type=int, default=1)
    ap.add_argument("--after-line", type=int, default=0)
    ap.add_argument("--max", type=int, default=60)
    a = ap.parse_args()
    w = sites(a.working, a.tid)
    f = [sites(p, a.tid) for p in a.failing]
    missing = [(v[0], k, v) for k, v in w.items() if all(k not in s for s in f) and v[0] >= a.after_line]
    missing.sort()
    print("working run sites (tid %s): %d; missing from every failing run: %d" % (a.tid, len(w), len(missing)))
    for ln, k, v in missing[:a.max]:
        print("line %7d  nid=%s lr=0x%08X  r3=%s r4=%s" % (ln, k[0], k[1], v[1], v[2]))


if __name__ == "__main__":
    main()

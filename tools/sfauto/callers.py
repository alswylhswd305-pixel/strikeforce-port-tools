#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""callers.py -- who calls a recompiled function?  Static caller tree over port/recompiled/ppu_recomp_*.cpp.

  python sfauto/tools/callers.py 0x13350 [--depth 5] [--max 12]

Direct calls only (`ctx->lr = 0x..; func_XXXXXXXX(ctx);`).  Calls through function pointers (bctrl) are not
visible, and a function with no direct caller is usually reached that way (a vtable / callback table) --
the tool says so.  The graph is cached in sfauto/tools/out/callgraph.pkl (rebuilt when the sources change).
Read only.
"""
import argparse, glob, os, pickle, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("SF_TEST_ROOT") or os.path.join(HERE, "..", ".."))
CACHE = os.path.join(HERE, "out", "callgraph.pkl")
DEF = re.compile(r"^void func_([0-9A-Fa-f]+)\(ppu_context")
CALL = re.compile(r"ctx->lr = 0x([0-9A-Fa-f]+); func_([0-9A-Fa-f]+)\(ctx\)")


def build():
    files = sorted(glob.glob(os.path.join(ROOT, "port", "recompiled", "ppu_recomp_*.cpp")))
    newest = max(os.path.getmtime(f) for f in files)
    if os.path.exists(CACHE) and os.path.getmtime(CACHE) > newest:
        return pickle.load(open(CACHE, "rb"))
    callers = {}   # callee -> set((caller_func, call_site_lr))
    cur = None
    for f in files:
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                m = DEF.match(ln)
                if m:
                    cur = int(m.group(1), 16)
                    continue
                if "ctx->lr = 0x" in ln:
                    for c in CALL.finditer(ln):
                        callers.setdefault(int(c.group(2), 16), set()).add((cur, int(c.group(1), 16)))
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    pickle.dump(callers, open(CACHE, "wb"))
    return callers


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("func", help="function address, e.g. 0x13350")
    ap.add_argument("--depth", type=int, default=5)
    ap.add_argument("--max", type=int, default=12)
    a = ap.parse_args()
    t0 = time.time()
    g = build()
    print("graph: %d callees (%.1fs)" % (len(g), time.time() - t0))
    root = int(a.func, 16)

    def walk(fn, depth, seen):
        cs = sorted(g.get(fn, ()), key=lambda x: (x[0] or 0, x[1]))
        if not cs:
            print("%s0x%X  <- no direct caller (reached via a function pointer / vtable, or an entry point)" % ("  " * depth, fn))
            return
        for caller, lr in cs[:a.max]:
            tag = " (seen)" if caller in seen else ""
            print("%s0x%X  <- called from func_%08X at lr=0x%X%s" % ("  " * depth, fn, caller or 0, lr, tag))
            if depth < a.depth and caller and caller not in seen:
                walk(caller, depth + 1, seen | {caller})
        if len(cs) > a.max:
            print("%s... %d more callers" % ("  " * depth, len(cs) - a.max))

    walk(root, 0, {root})


if __name__ == "__main__":
    main()

#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""audit_handlers.py -- for every import the LAST RUN called, find its HLE handler in the sources and flag
handlers that look fake: body empty / only `return 0` / sets r3 without writing any output (vm_write*, memcpy, store).

  python sfauto/tools/audit_handlers.py [--all] [--min-calls N] [--out DIR]

Inputs : play_cwd/stubhit_table.tsv (what the game called, call counts, return values seen)
         live sources: sfauto/fix1807trace/src, sfauto/fix1806/src, sfauto/fix1804_sys/src, ps3recomp/runtime, ps3recomp/libs
Output : sfauto/tools/out/handler_audit.md / .json  (sorted by call count; ASSUMED classification, read the code)
Read only.  Heuristics, not proof: a handler flagged SUSPECT may be fine (nothing to write) and an OK one may be wrong.
"""
import argparse, glob, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("SF_TEST_ROOT") or os.path.join(HERE, "..", ".."))
SRC_DIRS = [os.path.join(ROOT, p) for p in ("sfauto/fix1807trace/src", "sfauto/fix1806/src", "sfauto/fix1804_sys/src",
                                            "ps3recomp/runtime", "ps3recomp/libs")]
EXT = (".c", ".cpp", ".inc", ".h")


def load_sources():
    files = []
    for d in SRC_DIRS:
        for dp, dn, fn in os.walk(d):
            dn[:] = [x for x in dn if x not in ("tests", "build", "bld")]
            for f in fn:
                if f.endswith(EXT):
                    files.append(os.path.join(dp, f))
    # newest copy of a file name wins (fix dirs are listed before ps3recomp)
    seen, out = set(), []
    for f in files:
        key = os.path.basename(f)
        if key in seen and "ps3recomp" in f:
            continue
        seen.add(key)
        out.append(f)
    return {f: open(f, encoding="utf-8", errors="replace").read() for f in out}


def body_at(text, idx):
    """text of the {...} block that starts at or after idx"""
    i = text.find("{", idx)
    if i < 0:
        return ""
    depth, j = 0, i
    while j < len(text):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1
    return text[i:i + 2000]


def find_handler(srcs, name):
    base = re.sub(r"\[[^\]]*\]$", "", name)
    pat = re.compile(r'"%s(\[[^\]]*\])?"' % re.escape(base))
    for f, t in srcs.items():
        for m in pat.finditer(t):
            line_start = t.rfind("\n", 0, m.start()) + 1
            line_end = t.find("\n", m.end()); line = t[line_start:line_end]
            ids = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", line[m.end() - line_start:])
            for sym in ids:
                if sym in ("ctx", "sizeof", "NULL", "nullptr"):
                    continue
                d = re.search(r"(?m)^\s*(?:static\s+)?(?:inline\s+)?void\s+%s\s*\(" % re.escape(sym), t)
                if d:
                    return f, sym, body_at(t, d.end())
                # definition in another file
                for f2, t2 in srcs.items():
                    d2 = re.search(r"(?m)^\s*(?:static\s+)?(?:inline\s+)?void\s+%s\s*\(" % re.escape(sym), t2)
                    if d2:
                        return f2, sym, body_at(t2, d2.end())
    # fallback: a function named like the import (void handler(ctx) or a plain C library function)
    d = re.compile(r"(?m)^[ \t]*(?:static\s+|inline\s+|extern\s+)*[A-Za-z_][A-Za-z0-9_ \t\*]*?\b%s\s*\([^;{]*\)\s*\{" % re.escape(base))
    for f, t in srcs.items():
        m = d.search(t)
        if m:
            return f, base, body_at(t, m.start())
    # handler named hle_<snake_case(name)> or h_<...>: try a loose match on the lower-cased name
    low = re.sub(r"[^a-z0-9]", "", base.lower())
    for f, t in srcs.items():
        for m in re.finditer(r"(?m)^[ \t]*(?:static\s+)?(?:inline\s+)?void\s+((?:hle_|h_|sf_)[A-Za-z0-9_]+)\s*\(\s*ppu_context", t):
            if re.sub(r"[^a-z0-9]", "", m.group(1).lower()).endswith(low[-14:]) and len(low) > 6:
                return f, m.group(1), body_at(t, m.end())
    return None, None, ""


WRITES = re.compile(r"vm_write(8|16|32|64)|wbe(16|32|64)|memcpy|memset|\*\s*\(|ps3_write|\bSTORE\w*\(|put_be|vm_store|vm_memcpy|vm_fill|\*\w+\s*=[^=]|->\w+\s*=[^=]|\]\s*=[^=]|be32\(|be16\(|\bwrite\w*\(")


def classify(body):
    b = re.sub(r"/\*.*?\*/|//[^\n]*", "", body, flags=re.S)
    stmts = [s.strip() for s in b.strip("{} \n").split(";") if s.strip()]
    only_ret = all(re.match(r"^(ctx->gpr\[3\]\s*=\s*(0|CELL_OK|0x0)|RET\(\s*(0|CELL_OK)\s*\)|return)", s) for s in stmts) if stmts else True
    writes = bool(WRITES.search(b))
    reads_args = bool(re.search(r"gpr\[(4|5|6|7)\]|gpr\[3\]\s*[^=]|ARG\d", b))
    if not stmts:
        return "EMPTY", len(stmts)
    if only_ret:
        return "RETURNS_OK_ONLY", len(stmts)
    if not writes and len(stmts) <= 3:
        return "NO_OUTPUT_WRITE (short)", len(stmts)
    return "has logic", len(stmts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="include handlers classified as having logic")
    ap.add_argument("--min-calls", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    srcs = load_sources()
    rows = []
    for ln in open(os.path.join(ROOT, "play_cwd", "stubhit_table.tsv"), encoding="utf-8", errors="replace").read().splitlines()[1:]:
        p = ln.split("\t")
        if len(p) < 14 or int(p[3] or 0) < a.min_calls:
            continue
        nid, name, calls, rets = p[0], p[1], int(p[3]), p[13]
        f, sym, body = find_handler(srcs, name)
        cls, n = classify(body) if body else ("NOT FOUND IN SOURCES", 0)
        rows.append(dict(nid=nid, name=name, calls=calls, rets=rets[:60], file=os.path.relpath(f, ROOT) if f else None,
                         handler=sym, stmts=n, cls=cls))
    rows.sort(key=lambda r: -r["calls"])
    bad = [r for r in rows if r["cls"] != "has logic"]
    os.makedirs(a.out, exist_ok=True)
    json.dump(rows, open(os.path.join(a.out, "handler_audit.json"), "w"), indent=1)
    md = ["# Handler audit (ASSUMED heuristics)", "", "Imports called in the last run: %d; flagged: %d" % (len(rows), len(bad)), "",
          "| calls | name | class | handler | file | returns seen |", "|---:|---|---|---|---|---|"]
    for r in (rows if a.all else bad):
        md.append("| %d | %s | %s | %s | %s | %s |" % (r["calls"], r["name"], r["cls"], r["handler"] or "-", r["file"] or "-", r["rets"]))
    open(os.path.join(a.out, "handler_audit.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()

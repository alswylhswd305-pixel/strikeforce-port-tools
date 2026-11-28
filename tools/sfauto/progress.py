#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""progress.py -- regenerate sfauto/tools/PROGRESS.md from REAL counts.

  python sfauto/tools/progress.py [--fast] [--no-coverage]

Counts are measured, never typed in:
  * recompiled functions  : `void func_XXXXXXXX(ppu_context` definitions in port/recompiled/ppu_recomp_*.cpp
  * system functions      : sfauto/tools/out/coverage/coverage_summary.json  (from sf_coverage.py)
  * RSX methods           : same file
  * unresolved NIDs       : play_cwd/unresolved_nids.txt (last run) and the union of the last 10 runs
  * issues                : sfauto/tools/progress_items.json (hand-maintained, each item needs evidence)
The overall index is the plain average of the four ratios printed under "Index" -- it is a status index,
NOT a schedule.  Read only: it starts no process except sf_coverage.py (which only reads sources/logs).
"""
import argparse, glob, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("SF_TEST_ROOT") or os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out", "coverage", "coverage_summary.json")
PATTERN = re.compile(rb"^void\s+func_[0-9A-Fa-f]+\(ppu_context", re.M)


def count_functions():
    """(manifest functions that have a recompiled definition, manifest size, all definitions, files).
    The manifest is out/EBOOT.functions.json (the game's detected functions, 6444 on 2026-11-28)."""
    files = sorted(glob.glob(os.path.join(ROOT, "port", "recompiled", "ppu_recomp_*.cpp")))
    defined = set()
    for f in files:
        with open(f, "rb") as fh:
            for m in re.finditer(rb"^void\s+func_([0-9A-Fa-f]+)\(ppu_context", fh.read(), re.M):
                defined.add(int(m.group(1), 16))
    mp = os.path.join(ROOT, "out", "EBOOT.functions.json")
    manifest = [int(e["start"], 16) for e in json.load(open(mp, encoding="utf-8"))] if os.path.exists(mp) else []
    return sum(1 for x in manifest if x in defined), len(manifest), len(defined), len(files)


def unresolved():
    last = os.path.join(ROOT, "play_cwd", "unresolved_nids.txt")
    rows = []
    if os.path.exists(last):
        rows = [l.split("\t") for l in open(last, encoding="utf-8", errors="replace") if l.strip() and not l.startswith("#")]
    union = {}
    runs = sorted(glob.glob(os.path.join(ROOT, "sfauto", "runs", "*", "cwd", "unresolved_nids.txt")), key=os.path.getmtime)[-10:]
    for f in runs + ([last] if os.path.exists(last) else []):
        for l in open(f, encoding="utf-8", errors="replace"):
            if l.strip() and not l.startswith("#"):
                p = l.rstrip("\n").split("\t")
                union[p[0]] = p[2] if len(p) > 2 else ""
    return rows, union


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast", action="store_true", help="coverage scan skips logs over 40 MB")
    ap.add_argument("--no-coverage", action="store_true", help="reuse the last coverage_summary.json")
    a = ap.parse_args()
    if not a.no_coverage:
        cmd = [sys.executable, "-I", os.path.join(HERE, "sf_coverage.py")] + (["--fast"] if a.fast else [])
        subprocess.run(cmd, cwd=ROOT, capture_output=True)
    cov = json.load(open(OUT, encoding="utf-8"))
    nfun, nman, ndef, nfiles = count_functions()
    last_rows, union = unresolved()
    sysc = cov["syscalls"]; rsx = cov["rsx"]
    impl = sysc["by_status"].get("implemented", 0); tot = sysc["total"]
    used_h = rsx["used_and_handled"]; used_bad = rsx["used_but_unhandled_or_unused"]
    items = json.load(open(os.path.join(HERE, "progress_items.json"), encoding="utf-8"))["items"]
    done = sum(1 for i in items if i["status"] == "done")
    r_fn = pct(nfun, nman)
    r_sys = pct(impl, tot)
    r_rsx = pct(used_h, used_h + used_bad)
    r_iss = pct(done, len(items))
    index = (r_fn + r_sys + r_rsx + r_iss) / 4.0

    L = ["# PROGRESS (generated %s by sfauto/tools/progress.py)" % time.strftime("%Y-%m-%d %H:%M"), "",
         "Test copy only. Numbers are measured by tools, not estimated. Rule: no claim without a measurement or a file.", "",
         "## Index", "",
         "| measure | value | how it is counted |", "|---|---|---|",
         "| Game functions recompiled | **%d / %d = %.1f%%** | functions in out/EBOOT.functions.json that have a definition in port/recompiled (%d definitions in total, %d files; the extra ones are additional entry points) |" % (nfun, nman, r_fn, ndef, nfiles),
         "| System functions implemented | **%d / %d = %.1f%%** | auto-classified NIDs (published baseline: %s) |" % (impl, tot, r_sys, sysc["published_baseline"].get("implemented")),
         "| RSX methods the game uses that are handled | **%d / %d = %.1f%%** | methods the game wrote at least once (all 798 known methods: %d handled = %.1f%%) |" % (
             used_h, used_h + used_bad, r_rsx, rsx["counts"]["handled"], rsx["counts"]["percent_handled"]),
         "| Tracked issues closed | **%d / %d = %.1f%%** | progress_items.json |" % (done, len(items), r_iss),
         "| **Status index** | **%.1f%%** | plain average of the four ratios above; NOT a schedule |" % index, "",
         "- Game functions: %d / %d have a recompiled definition (your note said 6444/6444: %s)." % (nfun, nman, "matches" if (nfun, nman) == (6444, 6444) else "DIFFERS"),
         "Differences from the numbers in your status note (VERIFIED by the tools; the published baselines used older sources/rules):",
         "",
         "- System functions: tool says %d implemented of %d (note says 268/346 = 77%%)." % (impl, tot),
         "- RSX: tool says %d of 798 methods handled overall = %.1f%% (note says ~80%%; the 'used by the game' ratio above is the closer measure)." % (rsx["counts"]["handled"], rsx["counts"]["percent_handled"]), "",
         "## System functions still fake or missing (used by the game, sorted by calls)", "",
         "| NID | module | status | calls |", "|---|---|---|---:|"]
    for x in cov["top_syscalls"]:
        L.append("| %s | %s | %s | %d |" % (x["nid"], x["module"], x["status"], x["calls"]))
    L += ["", "Other stubs never called in the logs: %d (status counts: %s)." % (sysc["by_status"].get("stub", 0), sysc["by_status"]), "",
          "## Unresolved NIDs seen at runtime", "",
          "- last run: %d  | union of the last 10 runs: %d" % (len(last_rows), len(union)), ""]
    for k, v in sorted(union.items()):
        L.append("- %s %s" % (k, v))
    L += ["", "## RSX methods used but not handled (top)", "", "| method | name | class | writes | draws affected |", "|---|---|---|---:|---:|"]
    for x in cov["top_rsx"]:
        L.append("| %s | %s | %s | %d | %d |" % (x["method"], x["name"], x["cls"], x["writes"], x["draws"]))
    L += ["", "## Issues", "", "| id | title | status | verified | next step |", "|---|---|---|---|---|"]
    for i in items:
        L.append("| %s | %s | %s | %s | %s |" % (i["id"], i["title"], i["status"], i["verified"] or "-", i["next"]))
    L += ["", "### Evidence", ""]
    for i in items:
        L.append("- **%s**: %s" % (i["id"], i["evidence"]))
    L += ["", "Next refresh: `python sfauto/tools/progress.py` (add `--fast` to skip the 100 MB logs; ~2 min otherwise)."]
    open(os.path.join(HERE, "PROGRESS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:22]))
    print("... written sfauto/tools/PROGRESS.md")


if __name__ == "__main__":
    main()

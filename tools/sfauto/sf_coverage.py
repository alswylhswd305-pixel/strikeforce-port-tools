#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""sf_coverage.py -- one command for the stub/coverage report: which system functions (NIDs) and which RSX
methods are still fake or missing, sorted by how much the game actually uses them.

  python tools/sfauto/sf_coverage.py [--fast] [--reuse HOURS] [--top 15]

It runs the existing tools/coverage_tools/syscall_coverage.py and rsx_coverage.py (read-only: they read
sources and logs, nothing is started or stopped) into tools/sfauto/out/coverage/, then merges them into
coverage_summary.json and coverage_summary.md (English, sorted by call count / writes).
--fast       skip logs over 40 MB (the full scan of 120 MB logs took ~170 s on 2026-11-28)
--reuse N    do not re-run when the previous output is younger than N hours
Classification is AUTOMATIC (ASSUMED) except where the underlying tool marks a row KNOWN.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("SF_TEST_ROOT") or os.path.join(HERE, "..", ".."))
CT = os.environ.get("SF_COVERAGE_TOOLS") or os.path.join(os.path.dirname(HERE), "coverage_tools")
OUT = os.path.join(HERE, "out", "coverage")


def run(script, extra):
    t0 = time.time()
    r = subprocess.run([sys.executable, "-I", os.path.join(CT, script), "--root", ROOT, "--out", OUT] + extra,
                       capture_output=True, text=True, cwd=ROOT)
    print("%s: %.1fs exit %d" % (script, time.time() - t0, r.returncode))
    if r.returncode not in (0, 1):
        print(r.stdout[-800:], r.stderr[-800:])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--reuse", type=float, default=0.0)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    sj, rj = os.path.join(OUT, "syscall_coverage.json"), os.path.join(OUT, "rsx_coverage.json")
    fresh = all(os.path.exists(p) and (time.time() - os.path.getmtime(p)) < a.reuse * 3600 for p in (sj, rj))
    if not fresh:
        extra = ["--max-log-mb", "40"] if a.fast else []
        run("rsx_coverage.py", [])
        run("syscall_coverage.py", extra)
    else:
        print("reusing outputs younger than %.1f h" % a.reuse)
    s = json.load(open(sj, encoding="utf-8")); r = json.load(open(rj, encoding="utf-8"))
    sc, rc = s["counts"], r["counts"]
    total_sys = sc["implemented"] + sc["stub"] + sc["partial"] + sc["uncertain"] + (s["counts"].get("missing", 0))
    allrows = s["all"]
    # Ground truth from the running game: play_cwd/stubhit_table.tsv lists every import the last run called and
    # the handler that answered it ("name[tag]" = a handler registered at run time, e.g. [sfm], [sf1804]).
    # The static scan does not see those tagged handlers, so it called 6 working functions "missing" on 2026-11-28.
    runtime = {}
    st = os.path.join(ROOT, "play_cwd", "stubhit_table.tsv")
    if os.path.exists(st):
        for ln in open(st, encoding="utf-8", errors="replace").read().splitlines()[1:]:
            p = ln.split("\t")
            if len(p) > 3 and p[2] == "handler":
                runtime[int(p[0], 16)] = (p[1], int(p[3] or 0))
    overridden = []
    for row in allrows:
        key = int(row["nid"], 16)
        if row["status"] != "implemented" and key in runtime:
            overridden.append(dict(nid=row["nid"], static_status=row["status"], runtime_name=runtime[key][0], calls=runtime[key][1]))
            row["static_status"] = row["status"]; row["status"] = "implemented"; row["runtime_override"] = True
    by_status = {}
    for row in allrows:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
    used_bad = sorted([x for x in allrows if x.get("used") and x["status"] != "implemented"], key=lambda x: -x.get("calls", 0))
    rsx_bad = sorted(r["unhandled_or_unused_but_used"], key=lambda x: -x.get("writes_total", 0))
    summary = dict(
        generated=time.strftime("%Y-%m-%d %H:%M:%S"),
        syscalls=dict(total=len(allrows), by_status=by_status, published_baseline=s["published_baseline"],
                      used_by_game_but_not_implemented=len(used_bad)),
        rsx=dict(counts=rc, published_baseline=r["published_baseline"], used_and_handled=r["used_and_handled_count"],
                 used_but_unhandled_or_unused=len(rsx_bad)),
        runtime_overrides=overridden,
        top_syscalls=[dict(nid=x["nid"], name=x["name"], module=x["module"], status=x["status"], calls=x.get("calls", 0)) for x in used_bad[:a.top]],
        top_rsx=[dict(method=x["method"], name=x["name"], cls=x["cls"], writes=x.get("writes_total", 0), draws=x.get("draws_nondef", 0)) for x in rsx_bad[:a.top]],
    )
    json.dump(summary, open(os.path.join(OUT, "coverage_summary.json"), "w"), indent=1)
    md = ["# Coverage summary (%s)" % summary["generated"], "",
          "## System functions (NIDs)", "",
          "- imports: %d  | by status: %s" % (len(allrows), by_status),
          "- published baseline: %s" % s["published_baseline"],
          "- used by the game (seen in logs) but not implemented: **%d**" % len(used_bad),
          "- reclassified from the last run's runtime handler table (static scan said stub/missing, but a tagged handler answered): **%d** %s" % (
              len(overridden), [(o["runtime_name"], o["calls"]) for o in overridden[:8]]), "",
          "| NID | name | module | status | calls |", "|---|---|---|---|---:|"]
    for x in summary["top_syscalls"]:
        md.append("| %s | %s | %s | %s | %d |" % (x["nid"], x["name"], x["module"], x["status"], x["calls"]))
    md += ["", "## RSX methods", "",
           "- counts: %s" % rc, "- published baseline: %s" % r["published_baseline"],
           "- used by the game and handled: **%s** | used but unhandled/unused: **%d**" % (r["used_and_handled_count"], len(rsx_bad)), "",
           "| method | name | class | writes | draws affected |", "|---|---|---|---:|---:|"]
    for x in summary["top_rsx"]:
        md.append("| %s | %s | %s | %d | %d |" % (x["method"], x["name"], x["cls"], x["writes"], x["draws"]))
    open(os.path.join(OUT, "coverage_summary.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()

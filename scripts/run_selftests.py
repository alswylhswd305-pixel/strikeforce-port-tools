#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Run every in-repo Python self-test. No game launch and no network needed.

Usage:
    python3 scripts/run_selftests.py
    python3 scripts/run_selftests.py /path/to/clone

Prints per-suite pass / skip / fail counts. Exit 1 if any suite failed.
Font and optional image tests are expected to skip when those files are absent.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    ROOT = Path(sys.argv[1]).resolve()

PY = sys.executable


def _scrub_env() -> dict:
    """Drop box-local /workspace overrides so a clone is tested as a stranger would see it."""
    env = os.environ.copy()
    for k, v in list(env.items()):
        if "/workspace/sf-shared" in v or (k.startswith("SF_") and v.startswith("/workspace/")):
            if k not in {"SF_ARABIC_FONT", "SF_AT_FONT"}:
                env.pop(k, None)
    # Never point tests at leftover box trees.
    env.pop("SF_SHOTS", None)
    env.pop("SF_TV_PHOTO", None)
    env.pop("SF_NID_REPORT_CSV", None)
    env.pop("SF_PSL1GHT", None)
    return env


ENV = _scrub_env()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, env=ENV)


def parse_unittest(out: str, code: int) -> tuple[int, int, int]:
    m = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    ran = int(m.group(1)) if m else 0
    skipped = int(m.group(1)) if (m := re.search(r"skipped=(\d+)", out)) else 0
    failed = 0
    if (m := re.search(r"failures=(\d+)", out)):
        failed += int(m.group(1))
    if (m := re.search(r"errors=(\d+)", out)):
        failed += int(m.group(1))
    if code != 0 and failed == 0:
        failed = max(1, ran - skipped) if ran else 1
    passed = max(0, ran - skipped - failed)
    if ran == 0 and code == 0:
        return 1, 0, 0
    return passed, skipped, failed


def parse_custom(name: str, out: str, code: int) -> tuple[int, int, int, str]:
    if "nid_autolink" in name:
        steps = len(re.findall(r"\[selftest\] \d+\.", out))
        if "ALL PASS" in out and code == 0:
            return (steps or 1), 0, 0, "ALL PASS"
        return 0, 0, (steps or 1), "FAILURES"
    if "auto_nid_wire" in name:
        skip = 1 if "skip PSL1GHT" in out else 0
        if code == 0 and "passed" in out.lower():
            return 1, skip, 0, "passed" + (" + skip PSL1GHT" if skip else "")
        return 0, skip, 1, "FAIL"
    if "atrac" in name:
        m = re.search(r"(\d+)\s+(?:of\s+\1\s+)?(?:passed|ok|OK)", out, re.I)
        n = int(m.group(1)) if m else 0
        if code == 0:
            return (n or 1), 0, 0, "pass"
        return n, 0, 1, "FAIL"
    if name == "autotester":
        oks = len(re.findall(r"^\s+OK\s+", out, re.M))
        fails = len(re.findall(r"^\s+FAIL\s+", out, re.M))
        skips = len(re.findall(r"^\s+SKIP\s+", out, re.M))
        if code != 0 and fails == 0:
            fails = 1
        if code == 0 and oks == 0:
            oks = 1
        return oks, skips, fails, f"ok={oks} skip={skips} fail={fails}"
    if name == "stubs48":
        if code == 0:
            skip = 1 if "skip full rebuild" in out else 0
            return 1, skip, 0, "selftest ok"
        return 0, 0, 1, "FAIL"
    if code == 0:
        skip = 1 if re.search(r"\bskip", out, re.I) else 0
        return 1, skip, 0, "ok" + (" (with skip)" if skip else "")
    return 0, 0, 1, "FAIL"


SUITES = [
    ("compile_all_py", "compile"),
    ("nid_autolink", [PY, "tools/nid-autolink/nid_autolink.py", "--selftest"]),
    ("auto_nid_wire", [PY, "tools/auto_nid_wire.py", "--self-test"]),
    ("atrac-validator", [PY, "tools/atrac-validator/atrac_validator.py", "selftest"]),
    ("replay", [PY, "tools/replay/selftest_padseq.py"]),
    ("voice_freeze_analyzer", [PY, "tools/voicefreeze/voice_freeze_analyzer.py", "--selftest"]),
    ("race_check", [PY, "tools/voicefreeze/race_check.py", "--selftest"]),
    ("watchdog_logic", [PY, "tools/voicefreeze/watchdog/watchdog_logic.py", "--selftest"]),
    ("check_hang_reports", [PY, "tools/voicefreeze/watchdog/check_hang_reports.py", "--selftest"]),
    ("sf_lifecycle", [PY, "tools/voicefreeze/lifecycle/sf_lifecycle.py", "--selftest"]),
    ("gfx_bisect", [PY, "tools/gfx_bisect/test_gfx_bisect.py", "-v"]),
    ("gfx_diagnose", [PY, "tools/gfx_bisect/test_diagnose.py", "-v"]),
    ("autotester", [PY, "autotester/selftest/run_selftest.py"]),
    ("npc_bot", [PY, "autotester/lib/npc_bot.py", "--selftest"]),
    ("stubs48", [PY, "tools/stubs48/build_stubs48.py", "--selftest"]),
]


def compile_all() -> dict:
    files = [
        p for p in sorted(ROOT.rglob("*.py"))
        if ".git" not in p.parts and "__pycache__" not in p.parts
    ]
    failed = []
    for p in files:
        r = subprocess.run([PY, "-m", "py_compile", str(p)], capture_output=True, text=True)
        if r.returncode != 0:
            failed.append((p, r.stderr))
    out = f"compiled {len(files)} python files, failed {len(failed)}\n"
    for p, err in failed:
        out += f"  FAIL {p}: {err}\n"
    return {
        "name": "compile_all_py",
        "code": 1 if failed else 0,
        "out": out,
        "passed": 0 if failed else len(files),
        "skipped": 0,
        "failed": len(failed),
        "note": f"{len(files)} files",
    }


def main() -> int:
    print(f"ROOT={ROOT}")
    print(f"PY={PY}")
    results = []
    for name, cmd in SUITES:
        if cmd == "compile":
            rec = compile_all()
            results.append(rec)
            print(f"[{rec['name']}] pass={rec['passed']} skip={rec['skipped']} fail={rec['failed']}  {rec['note']}")
            continue
        script = ROOT / cmd[1]
        if not script.is_file():
            rec = {
                "name": name, "code": 0, "out": f"missing {script}",
                "passed": 0, "skipped": 1, "failed": 0, "note": "entry missing",
            }
            results.append(rec)
            print(f"[{name}] SKIP (no {script})")
            continue
        proc = run([cmd[0], str(ROOT / cmd[1]), *cmd[2:]])
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        rec = {"name": name, "code": proc.returncode, "out": out}
        if "Ran " in out and "test" in out:
            p, s, f = parse_unittest(out, proc.returncode)
            note = "unittest"
        else:
            p, s, f, note = parse_custom(name, out, proc.returncode)
        rec.update(passed=p, skipped=s, failed=f, note=note)
        results.append(rec)
        print(f"[{name}] exit={rec['code']} pass={p} skip={s} fail={f}  {note}")
        if rec["code"] != 0:
            tail = "\n".join(out.strip().splitlines()[-25:])
            print("---- output (tail) ----")
            print(tail)
            print("-----------------------")

    print("\n======= SUMMARY =======")
    tp = ts = tf = 0
    for rec in results:
        tp += rec["passed"]
        ts += rec["skipped"]
        tf += rec["failed"]
        print(f"  {rec['name']:24}  pass={rec['passed']:4}  skip={rec['skipped']:3}  fail={rec['failed']:3}  {rec['note']}")
    print(f"  {'TOTAL':24}  pass={tp:4}  skip={ts:3}  fail={tf:3}")
    return 1 if tf else 0


if __name__ == "__main__":
    raise SystemExit(main())

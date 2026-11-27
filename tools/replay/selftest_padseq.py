#!/usr/bin/env python3
"""Parse .padseq files and check the movie-guard rules (no game required).

Also imported by the autotester selftest. Exit 0 if all checks pass.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEQ = HERE / "sequences"
BTN = json.load(open(HERE / "lib" / "buttons.json"))

CMDS = {"meta", "sleep", "press", "stick", "wait_movie_end", "wait_log", "wait_title"}
BUTTONS = {k for k in BTN if not k.startswith("_")}


def parse_seq(path: Path):
    rows = []
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        cmd = parts[0].lower()
        if cmd not in CMDS:
            raise ValueError(f"{path}:{i}: unknown command {cmd}")
        if cmd == "press":
            tok = parts[1]
            if not (tok.startswith("0x") or tok.upper() in BUTTONS):
                raise ValueError(f"{path}:{i}: bad mask {tok}")
        rows.append({"line": i, "cmd": cmd, "raw": line, "parts": parts})
    return rows


def movie_state(events: list[str]) -> dict:
    """Pure-Python twin of movie_guard.ps1 Update-SfMovieState."""
    st = {"Active": False, "Unsure": True, "Starts": 0, "Stops": 0, "SeenMovieLog": False, "Reason": "no-log-yet"}
    for line in events:
        if "[sf-movie]" in line:
            st["SeenMovieLog"] = True
        if "[sf-movie]" in line and "PlayerStart" in line:
            st["Starts"] += 1
            st["Active"] = True
            st["Unsure"] = False
            st["Reason"] = "PlayerStart"
        elif "[sf-movie]" in line and ("PlayerStop" in line or "PlayerFinalize" in line):
            st["Stops"] += 1
            st["Active"] = False
            st["Unsure"] = False
            st["Reason"] = "PlayerStop" if "PlayerStop" in line else "PlayerFinalize"
    if not st["SeenMovieLog"]:
        st["Unsure"] = True
        st["Reason"] = "no-sf-movie-lines"
    return st


def blocked(st: dict) -> bool:
    return bool(st["Active"] or st["Unsure"])


def main() -> int:
    fails = 0
    def ok(name, cond, detail=""):
        nonlocal fails
        print(("  OK  " if cond else "  FAIL ") + name + ((" " + str(detail)) if (not cond and detail) else ""))
        if not cond:
            fails += 1

    for p in sorted(SEQ.glob("*.padseq")):
        rows = parse_seq(p)
        ok(f"parse {p.name}", len(rows) > 0, rows)
        if p.name == "boot_to_start.padseq":
            cmds = [r["cmd"] for r in rows]
            ok("boot wait_movie_end before press", cmds.index("wait_movie_end") < cmds.index("press"))

    # Guard: no log lines => unsure => blocked
    st = movie_state([])
    ok("empty log is unsure+blocked", blocked(st) and st["Unsure"])

    st = movie_state(["[sf-movie] PlayerStart cmd start=1"])
    ok("PlayerStart is active+blocked", st["Active"] and blocked(st) and not st["Unsure"])

    st = movie_state([
        "[sf-movie] PlayerStart cmd start=1",
        "[sf-movie] PlayerStop at clock 8.00",
    ])
    ok("PlayerStop is idle, not blocked", st["Stops"] == 1 and not st["Active"] and not blocked(st))

    st = movie_state(["unrelated line", "hello"])
    ok("log without sf-movie is unsure+blocked", blocked(st) and st["Unsure"])

    # First press in boot_to_start is START — only after wait
    boot = parse_seq(SEQ / "boot_to_start.padseq")
    presses = [r for r in boot if r["cmd"] == "press"]
    ok("boot has exactly one press START", len(presses) == 1 and presses[0]["parts"][1].upper() == "START")

    print("fails", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

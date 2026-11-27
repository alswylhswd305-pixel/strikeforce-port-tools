#!/usr/bin/env python3
"""Parse a Strikeforce play stderr log for HLE NID / guest-fn coverage.

Understands:
  [hle-lr] new nid=0x........ lr=0x........ ...   (SF_HLE_LRLOG=1)
  [hle-lrc] DUMPNO NID LR COUNT ret=... tid=...
  [sf-movie] PlayerStart / PlayerStop / ...
  [cellPad] PAD_FILE press ...
  stub / missing import lines if present

Writes a JSON table plus 'new since last run' when --prev is given.
Movie v5 (27-Nov) does not emit [hle-lr] unless that hook is in the exe.
"""
from __future__ import annotations

import argparse, json, os, re, sys
from collections import defaultdict
from datetime import datetime

HLE_NEW = re.compile(
    r"\[hle-lr\]\s+new\s+nid=(0x[0-9A-Fa-f]+)\s+lr=(0x[0-9A-Fa-f]+)",
    re.I,
)
HLE_DUMP = re.compile(
    r"\[hle-lrc\]\s+\d+\s+(0x[0-9A-Fa-f]+)\s+(0x[0-9A-Fa-f]+)\s+(\d+)",
    re.I,
)
MOVIE = re.compile(r"\[sf-movie\]\s*(.*)")
PAD = re.compile(r"\[cellPad\]\s+PAD_FILE press\s+(0x[0-9A-Fa-f]+)", re.I)
STUB = re.compile(r"\[(?:stub|missing|sf-stub)\]\s+(\S+).*nid=(0x[0-9A-Fa-f]+)", re.I)
GUEST_FN = re.compile(r"\[(?:fn|call-trace|sf-fn)\]\s+(?:fn=)?(0x[0-9A-Fa-f]+)", re.I)


def load_names(path: str | None) -> dict[str, str]:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    for k, v in raw.items():
        key = k.upper() if k.upper().startswith("0X") else "0x" + k.upper()
        if not key.startswith("0X"):
            key = "0x" + key
        # normalize 0x + 8
        hx = key.replace("0X", "").replace("0x", "")
        out["0x" + hx.upper().zfill(8)] = v
    return out


def norm_nid(s: str) -> str:
    return "0x" + s.lower().replace("0x", "").upper().zfill(8)


def parse(log_path: str, names: dict[str, str]) -> dict:
    nids: dict[str, dict] = {}
    movies = []
    pads = []
    stubs = []
    fns: dict[str, int] = defaultdict(int)
    hle_lines = 0
    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = HLE_DUMP.search(line)
            if m:
                hle_lines += 1
                nid, lr, cnt = norm_nid(m.group(1)), norm_nid(m.group(2)), int(m.group(3))
                rec = nids.setdefault(nid, {"nid": nid, "name": names.get(nid, ""), "lrs": {}, "calls": 0})
                rec["lrs"][lr] = max(rec["lrs"].get(lr, 0), cnt)
                rec["calls"] = sum(rec["lrs"].values())
                continue
            m = HLE_NEW.search(line)
            if m:
                hle_lines += 1
                nid, lr = norm_nid(m.group(1)), norm_nid(m.group(2))
                rec = nids.setdefault(nid, {"nid": nid, "name": names.get(nid, ""), "lrs": {}, "calls": 0})
                rec["lrs"].setdefault(lr, 1)
                rec["calls"] = sum(rec["lrs"].values())
                continue
            m = MOVIE.search(line)
            if m:
                movies.append(m.group(1).strip())
                continue
            m = PAD.search(line)
            if m:
                pads.append(m.group(1))
                continue
            m = STUB.search(line)
            if m:
                stubs.append({"name": m.group(1), "nid": norm_nid(m.group(2))})
                continue
            m = GUEST_FN.search(line)
            if m:
                fns[norm_nid(m.group(1))] += 1

    table = sorted(nids.values(), key=lambda r: (-r["calls"], r["nid"]))
    return {
        "log": log_path,
        "parsed_at": datetime.now().isoformat(timespec="seconds"),
        "hle_log_lines": hle_lines,
        "unique_nids": len(nids),
        "unique_nid_lr_pairs": sum(len(r["lrs"]) for r in nids.values()),
        "nids": table,
        "guest_functions": [{"ea": k, "calls": v} for k, v in sorted(fns.items(), key=lambda kv: -kv[1])],
        "movies": movies,
        "pad_presses": pads,
        "stubs": stubs,
        "hle_hook_present": hle_lines > 0,
    }


def diff_prev(cur: dict, prev: dict) -> dict:
    prev_n = {r["nid"] for r in prev.get("nids", [])}
    new_nids = [r for r in cur.get("nids", []) if r["nid"] not in prev_n]
    prev_fn = {r["ea"] for r in prev.get("guest_functions", [])}
    new_fn = [r for r in cur.get("guest_functions", []) if r["ea"] not in prev_fn]
    return {"new_nids": new_nids, "new_guest_functions": new_fn, "prev_log": prev.get("log")}


def render_text(data: dict, diff: dict | None) -> str:
    lines = []
    lines.append(f"coverage from {data['log']}")
    lines.append(f"HLE hook lines={data['hle_log_lines']} unique NIDs={data['unique_nids']} nid+lr pairs={data['unique_nid_lr_pairs']}")
    if not data["hle_hook_present"]:
        lines.append("NOTE: no [hle-lr]/[hle-lrc] lines. This exe probably lacks SF_HLE_LRLOG (movie v5 did, on 27-Nov).")
    lines.append("NID\tNAME\tCALLS\tLR_COUNT")
    for r in data["nids"][:80]:
        lines.append(f"{r['nid']}\t{r['name'] or '?'}\t{r['calls']}\t{len(r['lrs'])}")
    if len(data["nids"]) > 80:
        lines.append(f"... {len(data['nids'])-80} more NIDs")
    if data["guest_functions"]:
        lines.append("guest functions: " + ", ".join(f"{r['ea']}x{r['calls']}" for r in data["guest_functions"][:20]))
    lines.append(f"movie log lines: {len(data['movies'])}  PAD_FILE presses: {len(data['pad_presses'])}  stubs: {len(data['stubs'])}")
    if diff is not None:
        lines.append(f"new NIDs since last run: {len(diff['new_nids'])}")
        for r in diff["new_nids"][:40]:
            lines.append(f"  NEW {r['nid']} {r['name'] or '?'} calls={r['calls']}")
        lines.append(f"new guest functions since last run: {len(diff['new_guest_functions'])}")
        for r in diff["new_guest_functions"][:40]:
            lines.append(f"  NEW {r['ea']} calls={r['calls']}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--names", default=os.path.join(os.path.dirname(__file__), "..", "data", "nid_names.json"))
    ap.add_argument("--prev", default=None, help="previous coverage JSON")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--txt", default=None)
    args = ap.parse_args(argv)
    names = load_names(args.names)
    data = parse(args.log, names)
    diff = None
    if args.prev and os.path.isfile(args.prev):
        with open(args.prev, encoding="utf-8") as f:
            diff = diff_prev(data, json.load(f))
        data["new_since_last_run"] = {
            "nids": [r["nid"] for r in diff["new_nids"]],
            "guest_functions": [r["ea"] for r in diff["new_guest_functions"]],
            "prev": diff["prev_log"],
        }
    else:
        data["new_since_last_run"] = {"nids": [], "guest_functions": [], "prev": None}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    text = render_text(data, diff)
    txt_path = args.txt or os.path.splitext(args.out)[0] + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

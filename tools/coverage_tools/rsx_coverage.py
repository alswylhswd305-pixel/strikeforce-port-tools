#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""rsx_coverage -- static + log coverage of NV4097/NV3089/NV406E methods.

Re-runnable after each build. Does not launch or close the game.
Reads sources and logs only; writes new files under --out (default
sfauto/coverage_tools/out/).

Counts use the same rule as tools/rsx_census/gen_coverage.py (2026-11-27):
  universe = NV method offsets 0x0000..0x1FFC step 4, plus driver flips
  0xE920/0xE924/0xE944; an offset is counted if it has a name or a handler.
  handled / stored-but-unused / unhandled as in that scanner (ASSUMED unless
  a KNOWN override is attached). Published headline was 376/798 handled.

Usage:
  python rsx_coverage.py [--root DIR] [--src DIR] [--backend FILE] [--out DIR]
                         [--max-log-mb N]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gen_coverage as gc  # noqa: E402
import nv4097_names  # noqa: E402
from common import (  # noqa: E402
    PUBLISHED_RSX,
    default_out,
    find_root,
    now_kwt,
    rel,
    render_top10_card,
    walk_files,
    write_json,
)

NEEDED = [
    "rsx_commands.c", "rsx_commands.h",
    "rsx_vertex_fetch.c", "rsx_texture_layout.c",
    "rsx_draw_engine.c", "rsx_dispatch.c",
    "cellGcmSys.c",
]
OPTIONAL_HDRS = ["rsx_draw_engine.h", "rsx_dispatch.h"]

# Visual impact groups (register meaning = KNOWN public NV40/RSX role;
# any link to a Strikeforce bug is ASSUMED).
GROUP_RANGES = [
    ((0x0A60, 0x0A7C), "ظل", "shadow", "إزاحة عمق المضلّع (تحيّز الظل/الشارات)"),
    ((0x1D78, 0x1D78), "عمق", "depth", "تحكم قصّ أقرب/أبعد مستوى (ZMIN_MAX)"),
    ((0x0394, 0x0398), "عمق", "depth", "حد القص الأدنى/الأقصى للعمق"),
    ((0x0380, 0x0388), "عمق", "depth", "اختبار حدود العمق"),
    ((0x0304, 0x0318), "عمق", "depth", "اختبار/كتابة العمق أو الستينسل"),
    ((0x034C, 0x0358), "ظل", "shadow", "ستينسل الوجه الخلفي (ظل حجمي مفترض)"),
    ((0x08CC, 0x08D4), "ضباب", "fog", "وضع ومعاملات الضباب"),
    ((0x0A20, 0x0A3C), "منظور", "viewport", "إزاحة/مقياس نافذة العرض"),
    ((0x08C0, 0x08C4), "منظور", "viewport", "مستطيل القص (scissor)"),
    ((0x031C, 0x031C), "مزج", "blend", "لون المزج الثابت"),
    ((0x036C, 0x037C), "مزج", "blend", "تمكين المزج / لون المزج 2"),
    ((0x0200, 0x02FC), "ملمس", "texture", "وحدات الملمس (إزاحة/صيغة/عنوان/مرشح)"),
    ((0x1A00, 0x1BFC), "ملمس", "texture", "حالة وحدة ملمس الشظايا"),
    ((0x0B00, 0x0B64), "ملمس", "texture", "تحكم إضافي للملمس/الإحداثيات"),
    ((0x0900, 0x097C), "ملمس", "texture", "ملمس برنامج الرؤوس"),
    ((0x1738, 0x173C), "رؤوس", "vertex", "أساس بيانات/فهارس الرؤوس"),
    ((0x1C00, 0x1CFC), "رؤوس", "vertex", "صفات رأس ثابتة"),
    ((0x1FF0, 0x1FF8), "رؤوس", "vertex", "أقنعة/بتات تفرع برنامج الرؤوس"),
    ((0x1800, 0x183C), "رسم", "raster", "وضع المضلع / تعبئة / تنعيم"),
    ((0x1D7C, 0x1D80), "رسم", "raster", "مكافحة التعرج / ضغط السطح"),
    ((0x0060, 0x007C), "مزامنة", "sync", "NV406E سيمافور/إشعار"),
    ((0xE900, 0xE9FF), "مزامنة", "sync", "قلب الإطار / أوامر السائق"),
]


def group_of(method: int, name: str = "") -> tuple[str, str, str]:
    for (a, b), ar, en, meaning in GROUP_RANGES:
        if a <= method <= b:
            return ar, en, meaning
    n = name or ""
    if "NV3089" in n or "BLIT" in n or "TRANSFER" in n:
        return "نقل", "transfer", "نقل/نسخ صورة (Blit)"
    if "NV406E" in n or "SEMAPHORE" in n or "NOTIFY" in n:
        return "مزامنة", "sync", "أوامر الصف/السيمافور"
    if "TEXTURE" in n or "TEX_" in n:
        return "ملمس", "texture", "حالة ملمس"
    if "BLEND" in n or "COLOR_MASK" in n or "LOGIC_OP" in n:
        return "مزج", "blend", "مزج أو قناع لون"
    if "DEPTH" in n or "ZMIN" in n or "ZMAX" in n or "ZETA" in n or "CLIP_MIN" in n or "CLIP_MAX" in n:
        return "عمق", "depth", "عمق/قص"
    if "FOG" in n:
        return "ضباب", "fog", "ضباب"
    if "VIEWPORT" in n or "SCISSOR" in n:
        return "منظور", "viewport", "نافذة عرض/قص"
    if "VERTEX" in n or "BRANCH" in n:
        return "رؤوس", "vertex", "بيانات أو برنامج رؤوس"
    return "أخرى", "other", ""


# Known open visual bugs we boost when ranking (ASSUMED link only).
BUG_BOOST = {
    "shadow": 40,
    "texture": 30,
    "depth": 25,
    "fog": 20,
    "viewport": 15,
    "blend": 12,
    "vertex": 12,
}


def find_file(name: str, *dirs: Path | None) -> Path | None:
    for d in dirs:
        if d is None:
            continue
        p = d / name
        if p.is_file():
            return p
    return None


def auto_sources(root: Path, src_arg=None, backend_arg=None):
    """Newest sfauto/*/src that has rsx_commands.c and/or a D3D12 backend.

    Isolated build trees are preferred over the older ps3recomp/libs/video
    copy. Missing supporting files are filled from libs/video.
    """
    fallback = root / "ps3recomp" / "libs" / "video"
    cmd = Path(src_arg) / "rsx_commands.c" if src_arg else None
    backend = Path(backend_arg) if backend_arg else None

    trees = []
    sfauto = root / "sfauto"
    if sfauto.is_dir():
        for child in sfauto.iterdir():
            if not child.is_dir():
                continue
            if child.name.lower() in ("backups", "exe_copies", "known_good"):
                continue
            src = child / "src"
            if not src.is_dir():
                continue
            c = src / "rsx_commands.c"
            b = src / "rsx_d3d12_backend.c"
            if not b.is_file():
                b2 = src / "sh_work.c"
                b = b2 if b2.is_file() else None
            if not c.is_file() and not (b and b.is_file()):
                continue
            mt = 0.0
            if c.is_file():
                mt = max(mt, c.stat().st_mtime)
            if b and b.is_file():
                mt = max(mt, b.stat().st_mtime)
            trees.append((mt, src, c if c.is_file() else None, b if b and b.is_file() else None))
    trees.sort(reverse=True)

    if not cmd:
        for _mt, _src, c, _b in trees:
            if c is not None:
                cmd = c
                break
        if cmd is None:
            cmd = fallback / "rsx_commands.c"
    src_dir = cmd.parent if cmd else fallback

    if not backend:
        for _mt, _src, _c, b in trees:
            if b is not None:
                backend = b
                break
        if backend is None:
            for name in ("rsx_d3d12_backend.c", "sh_work.c"):
                p = src_dir / name
                if p.is_file():
                    backend = p
                    break
            if backend is None:
                backend = fallback / "rsx_d3d12_backend.c"

    files = {}
    search = (src_dir, backend.parent if backend else None, fallback)
    files["rsx_commands.c"] = cmd
    files["backend"] = backend
    missing = []
    for n in NEEDED + OPTIONAL_HDRS:
        if n == "rsx_commands.c":
            continue
        p = find_file(n, *search)
        if p:
            files[n] = p
        elif n in NEEDED:
            missing.append(n)
    return files, missing, trees


def analyze(files: dict) -> tuple[dict, dict]:
    """Same classification loop as gen_coverage.main (counts stay comparable)."""
    cmd = gc.Src(str(files["rsx_commands.c"]))
    hdr = gc.Src(str(files["rsx_commands.h"]))
    backend = gc.Src(str(files["backend"]))
    vfetch = gc.Src(str(files["rsx_vertex_fetch.c"]))
    tlay = gc.Src(str(files["rsx_texture_layout.c"]))
    de = gc.Src(str(files["rsx_draw_engine.c"]))
    dsp = gc.Src(str(files["rsx_dispatch.c"]))
    extra_hdrs = [gc.Src(str(files[h])) for h in OPTIONAL_HDRS if h in files]
    defines, hdr_names = gc.load_defines([hdr, cmd] + extra_hdrs)
    an = gc.Analyzer(cmd, defines)
    consumers = [backend, vfetch, tlay]
    cmd_action_reads = set()
    for blk in an.main_ifs:
        if "s_backend->" in blk["body"] and "set_render_target" not in blk["body"]:
            cmd_action_reads |= set(re.findall(r"state->(\w+)", blk["body"]))
    internal_reads = {}
    init = an.funcs.get("rsx_state_init")
    for r in re.finditer(r"(?<!&)state->(\w+)", cmd.nolog):
        if init and init[1] <= r.start() <= init[2]:
            continue
        k = r.end()
        while k < len(cmd.nolog) and cmd.nolog[k] == "[":
            k = gc.match_close(cmd.nolog, k, "[", "]") + 1
        if re.match(r"\s*(?:\.\w+)?\s*(?:[-+|&^]?=(?!=))", cmd.nolog[k:k + 40]):
            continue
        internal_reads.setdefault(r.group(1), f"rsx_commands.c:{gc.line_of(cmd.nolog, r.start())} (internal read)")
    ovr = gc.overrides(backend)
    gcm = gc.Src(str(files["cellGcmSys.c"]))
    upstream = {}
    f3 = gc.find_function(gcm.code, "gcm_3d_method")
    if f3:
        for r in re.finditer(r"\bm\s*==\s*(0x[0-9A-Fa-f]+)u?", gcm.code[f3[1]:f3[2]]):
            upstream.setdefault(int(r.group(1), 16), f"cellGcmSys.c:{gc.line_of(gcm.code, f3[1] + r.start())} (gcm_3d_method)")
    for r in re.finditer(r"subch\s*==\s*0\s*&&\s*\(([^)]*)\)", gcm.code):
        for v in re.findall(r"method\s*==\s*(0x[0-9A-Fa-f]+)", r.group(1)):
            upstream.setdefault(int(v, 16), f"cellGcmSys.c:{gc.line_of(gcm.code, r.start())} (FIFO walker, before rsx_process_method)")
    de_refs = gc.draw_engine_refs([de, dsp], defines)

    methods = {}
    universe = list(range(0, 0x2000, 4)) + [0xE920, 0xE924, 0xE944]
    for m in universe:
        hname = hdr_names.get(m)
        pname, conf = nv4097_names.public_name(m)
        name = hname or pname
        name_src = "rsx_commands.h" if hname else ("public-list" + ("" if conf else " (VERIFY)") if pname else None)
        matches = an.classify_method(m)
        real = [x for x in matches if not x["diagnostic"]]
        fields, actions, captures, calls = set(), set(), set(), set()
        handler_lines = []
        conditional = False
        for x in real:
            if x["effects"] is None:
                continue
            handler_lines.append(x["line"])
            conditional |= x["conditional"]
            fields |= x["effects"]["fields"]
            actions |= x["effects"]["actions"]
            captures |= x["effects"]["captures"]
            calls |= x["effects"]["calls"]
        fields = {f for f in fields if not f.endswith(".dirty")}
        fields = {f for f in fields if not (f.endswith("[]") and any(g.startswith(f + ".") for g in fields))}
        has_handler = bool(handler_lines)
        consumed, unconsumed, evidence = [], [], {}
        for f in sorted(fields):
            refs = gc.consumer_refs(f, consumers)
            if f.split("[")[0] in cmd_action_reads:
                refs = ["rsx_commands.c(action)"] + refs
            elif not refs and "]." not in f and f.split("[")[0] in internal_reads:
                refs = [internal_reads[f.split("[")[0]]]
            evidence[f] = refs[:4]
            (consumed if refs else unconsumed).append(f)
        label = "ASSUMED"
        note = ""
        if not has_handler and m in upstream:
            cls = "handled"
            note = "handled in the FIFO walker, not rsx_process_method: " + upstream[m]
            evidence["upstream"] = [upstream[m]]
        elif not has_handler:
            cls = "unhandled"
        elif actions or (captures and not fields):
            cls = "handled"
            note = "acts directly: " + ", ".join(sorted(actions | {"capture:" + c for c in captures}))
        elif not fields:
            cls = "handled"
            note = "accepted as a no-op (returns 0, stores nothing)"
        elif consumed:
            cls = "handled"
            if unconsumed:
                note = "partial: not read by the D3D12 path: " + ", ".join(unconsumed)
        else:
            cls = "stored-but-unused"
        if m in ovr:
            o = ovr[m]
            cls, label, note = o["cls"], o["label"], o["note"]
            evidence["override"] = [o["evidence"]]
        if conditional:
            note = (note + "; " if note else "") + "handler condition also depends on runtime state"
        if not name and not has_handler and m not in de_refs and m not in upstream:
            continue
        methods[f"0x{m:04X}"] = dict(
            method=m, name=name or f"0x{m:04X}", name_source=name_src, cls=cls, label=label,
            handler_lines=[f"rsx_commands.c:{l}" for l in handler_lines],
            fields=sorted(fields), consumed=consumed, unconsumed=unconsumed,
            draw_engine=de_refs.get(m, []), note=note,
        )

    src_meta = {}
    for key, src in (("rsx_commands.c", cmd), ("rsx_commands.h", hdr),
                     ("backend", backend), ("rsx_vertex_fetch.c", vfetch),
                     ("rsx_texture_layout.c", tlay), ("rsx_draw_engine.c", de),
                     ("rsx_dispatch.c", dsp), ("cellGcmSys.c", gcm)):
        src_meta[key] = dict(path=src.path, md5=src.md5, mtime=src.mtime)
    counts = {c: sum(1 for v in methods.values() if v["cls"] == c)
              for c in ("handled", "stored-but-unused", "unhandled")}
    meta = dict(
        generated=now_kwt(),
        tool="rsx_coverage.py (static scan = gen_coverage.py rule; classes ASSUMED unless KNOWN)",
        sources=src_meta,
        set_viewport_noop=ovr.get("_set_viewport_noop"),
        counts=counts,
        total=sum(counts.values()),
    )
    return meta, methods


CENSUS_M = re.compile(
    r"^M,(0x[0-9A-Fa-f]+),(\d+),(\d+),(\d+),(\d+),(0x[0-9A-Fa-f]+),(0x[0-9A-Fa-f]+),"
    r"(0x[0-9A-Fa-f]+),([A-Za-z]),(0x[0-9A-Fa-f]+),(\d+),(\d+),"
)
METHLOG = re.compile(r"\[METHLOG\]\s+m=0x([0-9A-Fa-f]+)\s+d=0x([0-9A-Fa-f]+)")


def parse_census(path: Path) -> tuple[dict, dict]:
    meta, rows = {}, {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("# start_sec") or (line.startswith("#") and "window" in line):
                for kv in line.lstrip("#").split():
                    if "=" in kv:
                        k, _, v = kv.partition("=")
                        meta[k.strip()] = v.strip()
            elif line.startswith("M,"):
                m = CENSUS_M.match(line) or None
                parts = line.strip().split(",")
                if len(parts) < 13:
                    continue
                mid = int(parts[1], 16)
                rows[mid] = dict(
                    method=mid,
                    writes_win=int(parts[2]),
                    writes_total=int(parts[3]),
                    ndist=int(parts[4]),
                    draws_nondef=int(parts[11]) if parts[11] not in ("",) else None,
                    draws_seen=int(parts[12]) if parts[12] not in ("",) else None,
                    source="census",
                )
    return meta, rows


def parse_methlog(path: Path, rows: dict, max_bytes: int) -> int:
    n = 0
    size = path.stat().st_size
    if size > max_bytes:
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            mm = METHLOG.search(line)
            if not mm:
                continue
            n += 1
            mid = int(mm.group(1), 16)
            r = rows.setdefault(mid, dict(method=mid, writes_win=0, writes_total=0,
                                          ndist=0, draws_nondef=None, draws_seen=None,
                                          source="methlog"))
            if r.get("source") == "census":
                # Census already has exact totals; just note methlog also saw it.
                r["also_methlog"] = r.get("also_methlog", 0) + 1
            else:
                r["writes_total"] = r.get("writes_total", 0) + 1
                r["writes_win"] = r.get("writes_win", 0) + 1
                r["source"] = "methlog"
    return n


def collect_usage(root: Path, max_mb: float):
    max_bytes = int(max_mb * 1024 * 1024)
    census_files, log_files, skipped = [], [], []
    rows, census_meta = {}, {}
    # census first (authoritative totals)
    for p in walk_files(root, names={"rsx_census.txt"}):
        census_files.append(p)
        meta, got = parse_census(p)
        if got:
            census_meta[str(p)] = meta
        for mid, r in got.items():
            prev = rows.get(mid)
            if not prev or r["writes_total"] > prev.get("writes_total", 0):
                # keep the run with more writes (usually the longer play)
                merged = dict(r)
                if prev:
                    merged["writes_total"] = max(r["writes_total"], prev.get("writes_total", 0))
                    if r.get("draws_nondef") is not None or prev.get("draws_nondef") is not None:
                        merged["draws_nondef"] = max(r.get("draws_nondef") or 0, prev.get("draws_nondef") or 0)
                rows[mid] = merged
    # methlog in play_logs / play_cwd / logs, with a size cap
    search_roots = [root / "play_logs", root / "play_cwd", root / "logs"]
    for sr in search_roots:
        if not sr.is_dir():
            continue
        for p in sr.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".log", ".txt"}:
                continue
            if p.name.lower() == "rsx_census.txt":
                continue
            if p.stat().st_size > max_bytes:
                skipped.append({"path": str(p), "bytes": p.stat().st_size, "reason": "over --max-log-mb"})
                continue
            n = parse_methlog(p, rows, max_bytes)
            if n:
                log_files.append({"path": str(p), "methlog_lines": n})
    return rows, census_files, log_files, skipped, census_meta


def score(row, cls, group_en):
    writes = row.get("writes_total") or 0
    draws = row.get("draws_nondef") or 0
    s = writes + draws * 2
    if cls in ("unhandled", "stored-but-unused"):
        s += 1000
    s += BUG_BOOST.get(group_en, 0)
    return s


def arabic_cls(cls):
    return {
        "unhandled": "مو مدعوم",
        "stored-but-unused": "محفوظ وما ينستخدم",
        "handled": "مدعوم",
    }.get(cls, cls)


def reason_line(e) -> str:
    bits = []
    if (e.get("writes_total") or 0) > 0:
        bits.append(f"اللعبة كتبته {e['writes_total']:,} مرة")
    if e.get("draws_nondef"):
        bits.append(f"أثر على {e['draws_nondef']:,} رسمة")
    if e.get("group_meaning"):
        bits.append(e["group_meaning"])
    if e["cls"] == "unhandled":
        bits.append("ما فيه معالج في مسار الرسم")
    elif e["cls"] == "stored-but-unused":
        bits.append("ينحفظ وما يوصل لمسار D3D12")
    return " — ".join(bits) if bits else "غير مؤكد"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None)
    ap.add_argument("--src", default=None, help="Directory with rsx_commands.c (default: newest sfauto/*/src)")
    ap.add_argument("--backend", default=None, help="D3D12 backend .c (default: newest in sfauto/*/src)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-log-mb", type=float, default=120.0)
    a = ap.parse_args()

    root = find_root(a.root)
    out = Path(a.out).resolve() if a.out else default_out(root)
    out.mkdir(parents=True, exist_ok=True)

    files, missing, trees = auto_sources(root, a.src, a.backend)
    if missing:
        print("MISSING required sources:", missing, file=sys.stderr)
        raise SystemExit(2)
    print(f"[rsx] root={root}")
    print(f"[rsx] commands={files['rsx_commands.c']}")
    print(f"[rsx] backend={files['backend']}")
    print(f"[rsx] scanning methods…")
    meta, methods = analyze(files)
    print(f"[rsx] counts={meta['counts']} total={meta['total']}")

    print(f"[rsx] scanning logs (max {a.max_log_mb} MB)…")
    usage, census_files, meth_logs, skipped, census_meta = collect_usage(root, a.max_log_mb)
    print(f"[rsx] census files={len(census_files)} methlog files={len(meth_logs)} methods_seen={len(usage)} skipped={len(skipped)}")

    entries = []
    for key, e in methods.items():
        mid = e["method"]
        u = usage.get(mid, {})
        gar, gen, meaning = group_of(mid, e.get("name") or "")
        rec = dict(e)
        rec.update(
            writes_total=u.get("writes_total", 0),
            writes_win=u.get("writes_win", 0),
            draws_nondef=u.get("draws_nondef"),
            draws_seen=u.get("draws_seen"),
            usage_source=u.get("source"),
            group_ar=gar, group_en=gen, group_meaning=meaning,
            used=bool(u),
        )
        rec["score"] = score(rec, rec["cls"], gen)
        rec["reason_ar"] = reason_line(rec)
        entries.append(rec)

    used_unhandled = [e for e in entries if e["used"] and e["cls"] in ("unhandled", "stored-but-unused")]
    used_unhandled.sort(key=lambda e: (-e["score"], -e["writes_total"], e["method"]))
    handled_unused = [e for e in entries if (not e["used"]) and e["cls"] == "handled"]
    handled_unused.sort(key=lambda e: e["method"])
    used_handled = [e for e in entries if e["used"] and e["cls"] == "handled"]

    handled = meta["counts"]["handled"]
    total = meta["total"]
    pub_h, pub_t = PUBLISHED_RSX
    same = (handled == pub_h and total == pub_t)

    top10 = used_unhandled[:10]
    report = {
        "generated": now_kwt(),
        "tool": "rsx_coverage.py",
        "methodology": (
            "Same static rule as sf-shared/tools/rsx_census/gen_coverage.py "
            "(2026-11-27 coverage.md): named-or-handled offsets in 0x0000..0x1FFC+flips; "
            "handled if stored AND read by the D3D12 path, or acts directly. "
            "Classification is mechanical (ASSUMED) unless a KNOWN override applies. "
            "Usage from rsx_census.txt (authoritative write/draw counts) plus [METHLOG] in size-capped logs."
        ),
        "published_baseline": {"handled": pub_h, "total": pub_t, "date": "2026-11-27", "note": "faces/src + sh_work.c"},
        "counts": {
            "handled": handled,
            "stored_but_unused": meta["counts"]["stored-but-unused"],
            "unhandled": meta["counts"]["unhandled"],
            "total": total,
            "percent_handled": round(100.0 * handled / total, 1) if total else 0,
            "differs_from_published": not same,
        },
        "sources": {k: {"path": str(v), "md5": meta["sources"]["backend" if k == "backend" else k]["md5"]
                        if (k if k != "backend" else "backend") in meta["sources"] else None,
                        "mtime": meta["sources"].get("backend" if k == "backend" else k, {}).get("mtime")}
                    for k, v in files.items() if k in ("rsx_commands.c", "backend") or k in meta["sources"]},
        "set_viewport_noop": meta.get("set_viewport_noop"),
        "logs": {
            "census_files": [rel(root, p) for p in census_files],
            "methlog_files": meth_logs,
            "skipped": [{"path": rel(root, Path(s["path"])), "bytes": s["bytes"], "reason": s["reason"]} for s in skipped],
            "methods_seen": len(usage),
            "census_meta": {rel(root, Path(k)): v for k, v in census_meta.items()},
        },
        "unhandled_or_unused_but_used": [
            {
                "method": f"0x{e['method']:04X}",
                "name": e["name"],
                "cls": e["cls"],
                "label": e["label"],
                "group": e["group_en"],
                "group_ar": e["group_ar"],
                "writes_total": e["writes_total"],
                "draws_nondef": e["draws_nondef"],
                "note": e.get("note") or "",
                "reason_ar": e["reason_ar"],
                "score": e["score"],
            }
            for e in used_unhandled
        ],
        "top10_next": [
            {
                "rank": i,
                "method": f"0x{e['method']:04X}",
                "name": e["name"],
                "cls": e["cls"],
                "group": e["group_en"],
                "group_ar": e["group_ar"],
                "writes_total": e["writes_total"],
                "draws_nondef": e["draws_nondef"],
                "reason_ar": e["reason_ar"],
                "reason_en": (
                    f"{e['cls']}; {e['writes_total']} writes"
                    + (f"; {e['draws_nondef']} draws non-default" if e.get("draws_nondef") else "")
                    + (f"; {e['group_meaning']}" if e.get("group_meaning") else "")
                ),
            }
            for i, e in enumerate(top10, 1)
        ],
        "handled_never_used": [
            {"method": f"0x{e['method']:04X}", "name": e["name"]}
            for e in handled_unused
        ],
        "used_and_handled_count": len(used_handled),
        "caveats": [
            "Static classes are ASSUMED (regex scan) unless labeled KNOWN.",
            "Census write counts from the richest rsx_census.txt; METHLOG is changes-only and partial.",
            "Logs over --max-log-mb were skipped (listed).",
            "Vertex-program constant/microcode fast path may not appear in rsx_process_method counts.",
        ],
    }
    # compact source list
    report["sources"] = {
        k: {"path": rel(root, Path(v)) if Path(v).is_absolute() or True else str(v),
            "path_abs": str(v),
            "mtime": meta["sources"].get("backend" if k == "backend" else k, {}).get("mtime"),
            "md5": meta["sources"].get("backend" if k == "backend" else k, {}).get("md5")}
        for k, v in files.items()
        if k in meta["sources"] or k == "backend"
    }

    json_path = out / "rsx_coverage.json"
    write_json(json_path, report)

    # markdown
    L = []
    L.append("# تغطية أوامر الرسم (RSX)\n")
    L.append(f"توليد: {report['generated']}\n")
    L.append(f"- المدعوم: **{handled}** من **{total}** ({report['counts']['percent_handled']}%)")
    L.append(f"- محفوظ وما ينستخدم: {meta['counts']['stored-but-unused']}")
    L.append(f"- مو مدعوم: {meta['counts']['unhandled']}")
    if same:
        L.append(f"- يطابق الرقم المنشور سابقاً: {pub_h}/{pub_t}")
    else:
        L.append(f"- يختلف عن الرقم المنشور {pub_h}/{pub_t} (المصادر تغيّرت أو التصنيف اختلف).")
    L.append("\nالتصنيف آلي (غير مؤكد / ASSUMED) إلا إذا مكتوب KNOWN.\n")
    L.append("## أهم 10 أوامر نصلحها بعدها (تستخدمها اللعبة ومو مدعومة أو محفوظة بدون استخدام)\n")
    L.append("| # | الأمر | الاسم | الحالة | المجموعة | مرات الكتابة | رسمات متأثرة | السبب |")
    L.append("|---|---|---|---|---|---:|---:|---|")
    for t in report["top10_next"]:
        L.append(f"| {t['rank']} | {t['method']} | {t['name']} | {arabic_cls(t['cls'])} | {t['group_ar']} | "
                 f"{t['writes_total']} | {t['draws_nondef'] if t['draws_nondef'] is not None else '—'} | {t['reason_ar']} |")
    L.append(f"\nعدد الأوامر المدعومة اللي ما ظهرت في السجلات: {len(handled_unused)}")
    L.append(f"\nملفات التعداد: {len(census_files)} — سجلات METHLOG: {len(meth_logs)} — متجاوز حجمها: {len(skipped)}")
    md_path = out / "rsx_coverage.md"
    md_path.write_text("\n".join(L) + "\n", encoding="utf-8")

    # image
    img_items = []
    for t in report["top10_next"]:
        img_items.append({
            "rank": t["rank"],
            "name": f"{t['method']}  {t['name']}",
            "meta": f"{arabic_cls(t['cls'])} · {t['group_ar']} · كتابة {t['writes_total']:,}",
            "reason": t["reason_ar"],
        })
    if not img_items:
        img_items = [{"rank": 0, "name": "ما لقينا أوامر تستخدمها اللعبة ومو مدعومة في السجلات الحالية",
                      "meta": "غير مؤكد بدون سجل تعداد", "reason": "شغّل اللعبة مع RSX_CENSUS بعدين أعد الأداة"}]
    img_path = out / "rsx_coverage.png"
    badge = "تغيّر الرقم" if not same else None
    render_top10_card(
        img_path,
        title_ar="تغطية أوامر الرسم",
        subtitle_ar="الأوامر اللي اللعبة تستخدمها وما هي مدعومة — مرتبة حسب كثرة الكتابة والأثر",
        count_line_ar=f"وصلنا {handled} من {total} أمر رسم ({report['counts']['percent_handled']}٪)",
        count_detail_ar=(
            f"محفوظ بدون استخدام: {meta['counts']['stored-but-unused']}  ·  مو مدعوم: {meta['counts']['unhandled']}"
            + (f"  ·  نفس الرقم المنشور {pub_h}/{pub_t}" if same else f"  ·  الرقم المنشور كان {pub_h}/{pub_t}")
        ),
        items=img_items,
        footer_ar=f"توليد {report['generated']} · التصنيف آلي غير مؤكد إلا إذا مكتوب KNOWN\nالملف: {json_path.name} · ما تم تشغيل اللعبة",
        badge=badge,
    )

    print(f"[rsx] wrote {json_path}")
    print(f"[rsx] wrote {md_path}")
    print(f"[rsx] wrote {img_path}")
    print("TOP10:")
    for t in report["top10_next"]:
        print(f"  {t['rank']:2d}. {t['method']} {t['name']}  [{t['cls']}/{t['group']}]  "
              f"writes={t['writes_total']}  {t['reason_en']}")


if __name__ == "__main__":
    main()

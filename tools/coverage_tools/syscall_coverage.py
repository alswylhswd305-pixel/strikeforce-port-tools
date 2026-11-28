#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""syscall_coverage -- linked vs stub vs missing system functions (NIDs).

Re-runnable after each build. Does not launch or close the game.
Reads sources and logs only; writes new files under --out.

Count rule matches nid-coverage.md (2026-11-26, Asia/Kuwait):
  denominator = unique NIDs in out/EBOOT.imports.json (published 346)
  implemented = winning handler body is non-trivial (heuristic, ASSUMED)
  stub        = unused-arg casts / log / zero-fill / return CELL_OK or labeled stub
  missing     = no ps3_hle_register / register_ctx (unresolved path fakes CELL_OK)
  ctx handlers win over the generic table; within one table the first
  registration wins. Init order: ps3_load_prx_modules, ppu_hle_init,
  ppu_sysprx_register, ppu_fs_register.

The RPCS3 reference log is used as a behaviour reference only (which
functions that run named). No RPCS3 / GPL code is copied.

Usage:
  python syscall_coverage.py [--root DIR] [--out DIR] [--max-log-mb N]
                             [--rpcs3 PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from common import (  # noqa: E402
    PUBLISHED_NID,
    SKIP_DIR_NAMES,
    default_out,
    find_root,
    now_kwt,
    rel,
    render_top10_card,
    walk_files,
    write_json,
)

# Public NID formula (psdevwiki NID page / _sys_sprintf example).
NID_SUFFIX = bytes.fromhex("6759659904250490566427499489741A")


def nid_of(name: str) -> int:
    return struct.unpack("<I", hashlib.sha1(name.encode("utf-8") + NID_SUFFIX).digest()[:4])[0]


def nid_hex(v) -> str:
    if isinstance(v, int):
        return f"0x{v:08X}"
    s = str(v).strip()
    if s.lower().startswith("0x"):
        return "0x" + s[2:].upper()
    return "0x" + int(s, 0).to_string() if False else f"0x{int(s, 16):08X}"


REG_RX = re.compile(
    r"ps3_hle_register(?P<kind>_ctx|_fast)?\s*\(\s*"
    r"(?P<nid>0x[0-9A-Fa-f]+)[uUlL]*\s*"
    r"(?:,\s*\"(?P<name>[^\"]+)\")?\s*"
    r"(?:,\s*(?:\(void\s*\*\)\s*)?(?P<fn>[A-Za-z_:][\w:]*))?\s*\)",
)
COMPUTE_RX = re.compile(
    r"ps3_hle_register(?P<kind>_ctx|_fast)?\s*\(\s*"
    r"ps3_compute_nid\s*\(\s*\"(?P<cname>[^\"]+)\"\s*\)\s*"
    r"(?:,\s*\"(?P<name>[^\"]+)\")?\s*"
    r"(?:,\s*(?P<fn>[A-Za-z_:][\w:]*))?",
)
UNRES_LINE = re.compile(r"^(0x[0-9A-Fa-f]+)\s+(\d+)\s+(\S+)?")
HLE_UNRES = re.compile(r"\[hle\]\s+UNRESOLVED NID\s+(0x[0-9A-Fa-f]+)", re.I)
HLE_CALL = re.compile(r"\[HLE\]\s+([A-Za-z_][\w:]*)\s*\(")
STAGE_RX = [
    ("مقدمة الفيديو", "intro_movie", re.compile(r"movie00[0-9]\.pam|\[sf-movie\]", re.I)),
    ("الشاشة الرئيسية", "title", re.compile(r"title.?screen|cellGameBoot|START GAME", re.I)),
    ("تحميل", "load", re.compile(r"Voice\.bin|linkdata|USRDIR", re.I)),
    ("مهمة", "mission", re.compile(r"BLUS30471[/\\]\d+|quest|mission|stage-?\d", re.I)),
    ("لعب", "ingame", re.compile(r"\[sf-fps\]|FPS:|SetFlip|flip_request", re.I)),
]

# Impact groups (ASSUMED link to open bugs: voices, stutter).
def impact_of(module: str, name: str) -> tuple[str, str, int]:
    blob = f"{module or ''} {name or ''}"
    if re.search(r"Sail|Adec|Atrac|Audio|Pamf|Voice|Movie", blob, re.I):
        return "صوت/أصوات", "audio", 50
    if re.search(r"timer|usleep|lwcond|lwmutex|sys_time|cond_wait|sleep|sleep", blob, re.I):
        return "توقيت/ثقل", "timing", 40
    if re.search(r"Gcm|Resc|VideoOut|Rsx|Flip", blob, re.I):
        return "رسوم", "graphics", 15
    if re.search(r"cellFs|sys_fs|syscache", blob, re.I):
        return "ملفات", "fs", 10
    if re.search(r"Spurs|Sync|LFQueue|event_queue|mutex|cond", blob, re.I):
        return "مزامنة", "sync", 20
    if re.search(r"sceNp|sys_net|NetCtl", blob, re.I):
        return "شبكة", "net", 5
    if re.search(r"Osk|Sysutil|MsgDialog|Avc", blob, re.I):
        return "واجهة", "ui", 8
    return "أخرى", "other", 0


TRIVIAL = [
    re.compile(r"^$"),
    re.compile(r"^return\s+(?:CELL_OK|CELL_\w+|0|0x[0-9A-Fa-f]+|-?\d+)[uUlL]*$"),
    re.compile(r"^\(\s*void\s*\)\s*\w+"),
    re.compile(r"^[\w\s\*\->\.\[\]]+\s*=\s*(?:CELL_OK|0|0x0|nullptr|NULL|false|true|-1)\s*$"),
    re.compile(r"^(?:printf|fprintf|snprintf|sprintf|puts|fputs|OutputDebugStringA|LOG_\w+|SF_\w*LOG|fprintf_s)\s*\("),
    re.compile(r"^(?:std::)?memset\s*\("),
    re.compile(r"^(?:if|else if|else)\b"),
    re.compile(r"^ctx\s*->\s*gpr\s*\[\s*3\s*\]\s*="),
    re.compile(r"^r3\s*="),
    re.compile(r"^\w+\s*=\s*ctx\s*->\s*gpr"),
    re.compile(r"^const\s+"),
    re.compile(r"^(?:auto|int|u32|uint32_t|s32|bool|unsigned|long|size_t|char)\b"),
    re.compile(r"^/\*"),
]
LABEL_RX = re.compile(r"\b(TODO|FIXME|STUB|unimplemented|not implemented|dummy|no-op|noop)\b", re.I)


def strip_comments(s: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"//.*?$", " ", s, flags=re.M)
    return s


def classify_body(raw_body: str) -> tuple[str, str]:
    labeled = bool(LABEL_RX.search(raw_body))
    body = strip_comments(raw_body)
    flat = re.sub(r"[{}]", ";", body)
    stmts = [re.sub(r"\s+", " ", x).strip() for x in flat.split(";")]
    real = []
    for st in stmts:
        if not st:
            continue
        if any(rx.search(st) if rx.pattern.startswith(".") else rx.match(st) for rx in TRIVIAL):
            # still count non-trivial ifs that call something real — handled below
            if st.startswith("if") or st.startswith("else"):
                # keep if the condition or body (already split) isn't only a return/log
                inner = re.sub(r"^(?:else\s+)?if\s*\(.*\)\s*", "", st).strip()
                if not inner or any(rx.match(inner) for rx in TRIVIAL):
                    continue
            else:
                continue
        real.append(st)
    if not real:
        return "stub", "الجسم تقريباً فاضي أو يرجع نجاح بدون شغل حقيقي"
    if labeled and len(real) <= 2:
        return "stub", f"مكتوب عليها stub/TODO وفيها {len(real)} جملة شغل فقط"
    if labeled:
        return "partial", "فيها شغل بس مكتوب عليها TODO/stub (غير مؤكد)"
    return "implemented", f"فيها {len(real)} جملة شغل"


def find_body(text: str, fn: str) -> str | None:
    if not fn:
        return None
    short = fn.split("::")[-1]
    # common C/C++ definition
    rx = re.compile(
        r"(?:^|\n)[ \t]*(?:static\s+)?(?:inline\s+)?(?:extern\s+\"C\"\s+)?(?:[\w:<>\*&]+[ \t*]+)+"
        + re.escape(short) + r"\s*\([^;{]*\)\s*\{",
        re.M,
    )
    m = rx.search(text)
    if not m:
        # namespace method: void hle_foo(ppu_context* ctx) {
        rx2 = re.compile(r"(?:^|\n)[ \t]*(?:static\s+)?(?:void|int|s32|u32|uint32_t)\s+"
                         + re.escape(short) + r"\s*\([^;{]*\)\s*\{", re.M)
        m = rx2.search(text)
    if not m:
        return None
    brace = text.find("{", m.end() - 1)
    if brace < 0:
        return None
    depth, i, n = 0, brace, len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1:i]
        i += 1
    return None



def extract_body_at(text: str, brace: int) -> str | None:
    depth, i, n = 0, brace, len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1:i]
        i += 1
    return None


DEF_INDEX_RX = re.compile(
    r"(?:^|\n)[ \t]*(?:static\s+)?(?:inline\s+)?(?:extern\s+\"C\"\s+)?"
    r"(?:[\w:<>\*&]+[ \t*]+)+"
    r"(?P<name>[A-Za-z_]\w*)\s*\([^;{]*\)\s*\{",
    re.M,
)


def index_definitions(root: Path):
    """Map short function name -> list of (path, body) in source-walk order."""
    idx = {}
    for pth in iter_source_files(root):
        try:
            raw = pth.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "(" not in raw or "{" not in raw:
            continue
        for m in DEF_INDEX_RX.finditer(raw):
            name = m.group("name")
            brace = raw.find("{", m.end() - 1)
            if brace < 0:
                continue
            body = extract_body_at(raw, brace)
            if body is None:
                continue
            idx.setdefault(name, []).append((pth, body))
    return idx


def load_imports(path: Path) -> list[dict]:
    import json
    rows = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        nid = nid_hex(r["nid"])
        out.append({
            "nid": nid,
            "nid_int": int(nid, 16),
            "module": r.get("library") or r.get("module") or "",
            "stub_ea": r.get("stub"),
        })
    return out


def iter_source_files(root: Path):
    roots = [
        root / "port",
        root / "ps3recomp" / "runtime",
        root / "ps3recomp" / "libs",
        root / "ps3recomp" / "include",
    ]
    # Newest isolated 1801 trees (audio / lwcond / gamma / pacing) — read-only.
    sfauto = root / "sfauto"
    if sfauto.is_dir():
        for child in sorted(sfauto.iterdir()):
            if child.is_dir() and child.name.lower().startswith(("fix1801", "pacing1801")):
                src = child / "src"
                if src.is_dir():
                    roots.insert(0, src)
    suf = {".c", ".cpp", ".h", ".hpp", ".inc"}
    for r in roots:
        if not r.is_dir():
            continue
        for p in walk_files(r, suffixes=suf, extra_skip=("recompiled", "tests", "vulkan")):
            # skip backups next to sources
            if any(part.endswith(".bak") or part.startswith("bak_") for part in p.parts):
                continue
            if ".bak" in p.name or p.name.endswith(".orig"):
                continue
            yield p


def scan_registrations(root: Path, wanted: set[int]):
    """Return nid -> list of registration records, in file-walk order.

    Walk order approximates init order if we sort: port/strikeforce first,
    then port/bld, then runtime, then libs.
    """
    files = list(iter_source_files(root))

    def rank(p: Path):
        s = str(p).replace("\\", "/")
        if "/sfauto/fix1801" in s or "/sfauto/pacing1801" in s:
            return (-1, s)  # newest isolated trees win
        if "/port/" in s and "strikeforce" in p.name.lower():
            return (0, s)
        if "/port/bld/" in s or p.name.startswith("ppu_hle_nids"):
            return (1, s)
        if "/runtime/ppu/" in s:
            return (2, s)
        return (3, s)

    files.sort(key=rank)
    regs = defaultdict(list)
    bodies = {}  # (path, fn) cache of file text
    file_text = {}
    for p in files:
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "ps3_hle_register" not in raw and "ps3_compute_nid" not in raw:
            continue
        file_text[p] = raw
        rel_p = str(p)
        for m in REG_RX.finditer(raw):
            nid = int(m.group("nid"), 16)
            if wanted and nid not in wanted:
                # still keep — some handlers cover aliases — but we mainly care about imports
                pass
            kind = (m.group("kind") or "").lstrip("_") or "table"
            name = m.group("name") or ""
            fn = (m.group("fn") or "").strip()
            regs[nid].append({
                "kind": kind, "name": name, "fn": fn, "file": rel_p,
                "line": raw.count("\n", 0, m.start()) + 1,
            })
        for m in COMPUTE_RX.finditer(raw):
            name = (m.group("name") or m.group("cname") or "").strip()
            nid = nid_of(m.group("cname") or name)
            kind = (m.group("kind") or "").lstrip("_") or "table"
            fn = (m.group("fn") or "").strip()
            regs[nid].append({
                "kind": kind, "name": name, "fn": fn, "file": rel_p,
                "line": raw.count("\n", 0, m.start()) + 1,
                "via": "ps3_compute_nid",
            })

    # Resolve bodies for winning handlers later; keep file_text for those files.
    return regs, file_text


def winning_reg(recs: list[dict]) -> dict | None:
    if not recs:
        return None
    ctx = [r for r in recs if r.get("kind") == "ctx"]
    if ctx:
        return ctx[0]  # first ctx (port inc is sorted first)
    return recs[0]


def load_name_hints(root: Path, file_text: dict, regs: dict) -> dict[int, str]:
    names = {}
    # from registrations
    for nid, recs in regs.items():
        for r in recs:
            n = r.get("name") or ""
            # strip [sf] suffixes
            n = re.sub(r"\[.*?\]", "", n).strip()
            if n:
                names[nid] = n
                break
    # nid_from_protos / previous coverage lists if present
    for cand in [
        root / "out" / "nid_from_protos.json",
        Path(os.environ["SF_NID_PROTOS"]) if os.environ.get("SF_NID_PROTOS") else Path(),
        Path(os.environ["SF_NID_STUB_LIST"]) if os.environ.get("SF_NID_STUB_LIST") else Path(),
    ]:
        if not cand.is_file():
            continue
        try:
            import json
            d = json.loads(cand.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and "stubs" in d:
            for row in d.get("stubs", []) + d.get("missing", []):
                try:
                    nid = int(str(row["nid"]), 16)
                except Exception:
                    continue
                if nid not in names and row.get("name"):
                    names[nid] = row["name"]
        elif isinstance(d, dict):
            for k, v in d.items():
                if isinstance(k, str) and k.startswith("0x"):
                    continue
                if isinstance(v, str) and v.startswith("0x"):
                    try:
                        names[int(v, 16)] = k
                    except Exception:
                        pass
    return names


def collect_runtime(root: Path, max_mb: float):
    max_bytes = int(max_mb * 1024 * 1024)
    unres_files = []
    calls = defaultdict(lambda: {"unresolved_max": 0, "unresolved_files": 0,
                                 "unresolved_lines": 0, "hle_calls": 0,
                                 "stages": Counter(), "sources": []})
    skipped = []

    # unresolved_nids.txt (structured, authoritative for missing NIDs)
    for p in walk_files(root, names={"unresolved_nids.txt"}):
        unres_files.append(p)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hit = False
        for line in text.splitlines():
            m = UNRES_LINE.match(line.strip())
            if not m:
                continue
            nid = int(m.group(1), 16)
            n = int(m.group(2))
            rec = calls[nid]
            rec["unresolved_max"] = max(rec["unresolved_max"], n)
            rec["unresolved_files"] += 1
            rec["sources"].append(rel(root, p) if False else str(p))
            hit = True
        if hit:
            # file-level unique count already in unresolved_files
            pass

    # stderr/stdout for UNRESOLVED + [HLE] name(  and stages
    search = [root / "play_logs", root / "play_cwd", root / "logs"]
    hle_name_counts = Counter()
    hle_name_stages = defaultdict(Counter)
    for sr in search:
        if not sr.is_dir():
            continue
        for p in sr.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in {".log", ".txt"}:
                continue
            if p.name.lower() == "unresolved_nids.txt":
                continue
            if p.stat().st_size > max_bytes:
                skipped.append({"path": str(p), "bytes": p.stat().st_size, "reason": "over --max-log-mb"})
                continue
            stage = "غير محدد"
            stage_en = "unknown"
            try:
                f = p.open("r", encoding="utf-8", errors="replace")
            except OSError:
                continue
            with f:
                for line in f:
                    for ar, en, rx in STAGE_RX:
                        if rx.search(line):
                            stage, stage_en = ar, en
                            break
                    m = HLE_UNRES.search(line)
                    if m:
                        nid = int(m.group(1), 16)
                        rec = calls[nid]
                        rec["unresolved_lines"] += 1
                        rec["stages"][stage] += 1
                    m = HLE_CALL.search(line)
                    if m:
                        name = m.group(1)
                        hle_name_counts[name] += 1
                        hle_name_stages[name][stage] += 1
    return calls, hle_name_counts, hle_name_stages, unres_files, skipped


def parse_rpcs3(path: Path) -> dict:
    """Count function-like names in an RPCS3 log, skipping import tables and SPU TODO.

    Behaviour reference only.
    """
    names = Counter()
    rx = re.compile(
        r"\b(cell[A-Z][A-Za-z0-9_]+|sceNp[A-Za-z0-9_]+|_cell[A-Z][A-Za-z0-9_]+|"
        r"sys_[a-z][a-z0-9_]+|sysLw[A-Za-z0-9_]+)\b"
    )
    try:
        f = path.open("r", encoding="utf-8", errors="replace")
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(path), "counts": {}}
    nlines = 0
    with f:
        for line in f:
            nlines += 1
            if "import:" in line or "Imported module" in line or "ppu_loader" in line:
                continue
            if "SPU TODO" in line:
                continue
            for m in rx.findall(line):
                names[m] += 1
    return {
        "ok": True,
        "path": str(path),
        "lines": nlines,
        "counts": dict(names.most_common()),
        "note": "Behaviour reference only. Counts are name mentions in the log, not a precise call trace (غير مؤكد).",
    }


def find_rpcs3(root: Path, explicit=None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    cands = [
        root / "sfauto" / "testloop" / "mission1_20261126-2222" / "RPCS3_FINAL_20261126-223934.log",
        root / "sfauto" / "testloop" / "mission1_20261126-2222" / "RPCS3_FINAL_20261126-223848.log",
    ]
    for c in cands:
        if c.is_file():
            return c
    folder = root / "sfauto" / "testloop" / "mission1_20261126-2222"
    if folder.is_dir():
        finals = sorted(folder.glob("RPCS3_FINAL_*.log"))
        if finals:
            return finals[-1]
    return None


def status_ar(st: str) -> str:
    return {
        "implemented": "منفَّذة",
        "stub": "دمية (فاضية)",
        "partial": "جزئية",
        "missing": "ناقصة",
        "uncertain": "غير مؤكد",
    }.get(st, st)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-log-mb", type=float, default=120.0)
    ap.add_argument("--rpcs3", default=None)
    ap.add_argument("--imports", default=None)
    ap.add_argument("--skip-logs", action="store_true",
                    help="Classify sources only (fast counts); skip play_logs / RPCS3")
    a = ap.parse_args()

    root = find_root(a.root)
    out = Path(a.out).resolve() if a.out else default_out(root)
    out.mkdir(parents=True, exist_ok=True)

    imports_path = Path(a.imports) if a.imports else (root / "out" / "EBOOT.imports.json")
    if not imports_path.is_file():
        raise SystemExit(f"imports not found: {imports_path}")
    imports = load_imports(imports_path)
    wanted = {r["nid_int"] for r in imports}
    print(f"[nid] imports={len(imports)} from {imports_path}")

    print("[nid] scanning registrations…")
    regs, file_text = scan_registrations(root, wanted)
    print("[nid] indexing handler bodies…", flush=True)
    def_index = index_definitions(root)
    print(f"[nid] indexed {sum(len(v) for v in def_index.values())} definitions, {len(def_index)} names", flush=True)
    names = load_name_hints(root, file_text, regs)

    # classify each import
    rows = []
    for imp in imports:
        nid = imp["nid_int"]
        recs = regs.get(nid, [])
        win = winning_reg(recs)
        name = names.get(nid) or (win.get("name") if win else "") or ""
        name = re.sub(r"\[.*?\]", "", name).strip()
        module = imp["module"]
        if not win:
            status, why, handler = "missing", "ما في تسجيل HLE؛ الاستدعاء الفاضي يرجع CELL_OK", None
        else:
            handler = {"file": win["file"], "line": win["line"], "fn": win.get("fn") or "", "kind": win["kind"]}
            body = None
            fn = win.get("fn") or ""
            short = (fn or name or "").split("::")[-1]
            for cand in (short, fn, name):
                if not cand:
                    continue
                key = cand.split("::")[-1]
                for pth, b in def_index.get(key, []):
                    body = b
                    handler["body_file"] = str(pth)
                    handler["fn"] = handler["fn"] or key
                    break
                if body is not None:
                    break
            if body is None and fn and Path(win["file"]) in file_text:
                body = find_body(file_text[Path(win["file"])], fn)
            if body is None and not short:
                status, why = "uncertain", "التسجيل موجود بس ما لقينا جسم الدالة (غير مؤكد)"
            elif body is None:
                status, why = "uncertain", f"التسجيل موجود ({short}) بس ما لقينا الجسم (غير مؤكد)"
            else:
                status, why = classify_body(body)
        gar, gen, boost = impact_of(module, name)
        rows.append({
            "nid": imp["nid"],
            "name": name or imp["nid"],
            "module": module,
            "status": status,
            "why_ar": why,
            "handler": handler,
            "registrations": len(recs),
            "group_ar": gar,
            "group_en": gen,
            "impact_boost": boost,
        })

    # Preliminary counts (source classification only) — printed before the log scan.
    from collections import Counter as _C
    _pre = _C(r["status"] for r in rows)
    _impl, _tot = _pre.get("implemented", 0), len(rows)
    print(f"[nid] COUNTS_NOW implemented={_impl} total={_tot} "
          f"stub={_pre.get('stub',0)} missing={_pre.get('missing',0)} "
          f"partial={_pre.get('partial',0)} uncertain={_pre.get('uncertain',0)}",
          flush=True)
    (out / "_syscall_counts_preview.json").parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    (out / "_syscall_counts_preview.json").write_text(_json.dumps({
        "generated": now_kwt(),
        "implemented": _impl,
        "total": _tot,
        "by_status": dict(_pre),
        "includes_1801_trees": True,
        "logs_scanned": False,
    }, indent=2) + "\n", encoding="utf-8")

    if a.skip_logs:
        runtime, hle_names, hle_name_stages, unres_files, skipped = {}, _C(), {}, [], []
        print("[nid] --skip-logs: not reading play_logs / RPCS3")
    else:
        print("[nid] scanning logs…")
        runtime, hle_names, hle_name_stages, unres_files, skipped = collect_runtime(root, a.max_log_mb)

    # map HLE-call names onto rows
    name_to_nid = {}
    for r in rows:
        if r["name"] and r["name"] != r["nid"]:
            name_to_nid[r["name"]] = r["nid"]
            # also without module prefix variations
            short = r["name"].split("::")[-1]
            name_to_nid.setdefault(short, r["nid"])

    for r in rows:
        nid = int(r["nid"], 16)
        rt = runtime.get(nid, {})
        r["calls_unresolved_max"] = rt.get("unresolved_max", 0)
        r["calls_unresolved_files"] = rt.get("unresolved_files", 0)
        r["calls_unresolved_lines"] = rt.get("unresolved_lines", 0)
        # HLE named calls
        nm = r["name"]
        r["hle_log_calls"] = int(hle_names.get(nm, 0) + (hle_names.get(nm.split("::")[-1], 0) if nm else 0))
        if hle_names.get(nm) and hle_names.get(nm.split("::")[-1]) and nm != nm.split("::")[-1]:
            # avoid double-count when equal key
            r["hle_log_calls"] = hle_names.get(nm, 0)
        stages = Counter(rt.get("stages") or {})
        if nm in hle_name_stages:
            stages.update(hle_name_stages[nm])
        r["stages"] = dict(stages)
        r["stage_top"] = (stages.most_common(1)[0][0] if stages else "غير محدد")
        r["used"] = bool(r["calls_unresolved_max"] or r["calls_unresolved_lines"] or r["hle_log_calls"])
        r["calls"] = max(r["calls_unresolved_max"], r["hle_log_calls"], r["calls_unresolved_lines"])

    rpcs3_path = find_rpcs3(root, a.rpcs3)
    rpcs3 = parse_rpcs3(rpcs3_path) if rpcs3_path else {"ok": False, "error": "RPCS3 reference log not found"}
    rpcs3_counts = rpcs3.get("counts") or {}
    for r in rows:
        r["rpcs3_mentions"] = int(rpcs3_counts.get(r["name"], 0) or rpcs3_counts.get(r["name"].split("::")[-1], 0))

    def score(r):
        s = 0
        if r["status"] in ("missing", "stub"):
            s += 1000
        elif r["status"] == "partial":
            s += 600
        elif r["status"] == "uncertain":
            s += 200
        if r["used"]:
            s += 300 + min(r["calls"], 10_000)
        s += r["impact_boost"]
        if r["rpcs3_mentions"] and r["status"] in ("missing", "stub", "partial", "uncertain"):
            s += 80 + min(r["rpcs3_mentions"], 200)
        return s

    for r in rows:
        r["score"] = score(r)

    by_status = Counter(r["status"] for r in rows)
    implemented = by_status.get("implemented", 0)
    total = len(rows)
    pub_i, pub_t = PUBLISHED_NID
    # Headline comparable to 267/346: implemented only (stubs and missing excluded).
    # Uncertain is NOT counted as implemented.
    same = (implemented == pub_i and total == pub_t)

    fixable = [r for r in rows if r["status"] in ("missing", "stub", "partial", "uncertain")]
    fixable.sort(key=lambda r: (-r["score"], -r["calls"], r["nid"]))
    # Prefer actually-used first already via score; if top has unused, that's ok
    # after the used ones due to +300.
    top10 = fixable[:10]

    report = {
        "generated": now_kwt(),
        "tool": "syscall_coverage.py",
        "methodology": (
            "nid-coverage.md 2026-11-26 rule: unique imports in EBOOT.imports.json; "
            "implemented = non-trivial winning handler; stub = trivial/labeled; "
            "missing = unregistered. Classification is a body heuristic (ASSUMED). "
            "RPCS3 log is a behaviour reference only (name mentions, not a call trace)."
        ),
        "published_baseline": {"implemented": pub_i, "total": pub_t, "date": "2026-11-26 21:29 Asia/Kuwait",
                               "also": "32 stub + 47 missing at that count"},
        "counts": {
            "implemented": implemented,
            "stub": by_status.get("stub", 0),
            "partial": by_status.get("partial", 0),
            "uncertain": by_status.get("uncertain", 0),
            "missing": by_status.get("missing", 0),
            "total": total,
            "percent_implemented": round(100.0 * implemented / total, 1) if total else 0,
            "differs_from_published": not same,
        },
        "imports_path": rel(root, imports_path),
        "logs": {
            "unresolved_files": len(unres_files),
            "skipped": [{"path": rel(root, Path(s["path"])), "bytes": s["bytes"], "reason": s["reason"]} for s in skipped],
        },
        "rpcs3_reference": {
            "ok": rpcs3.get("ok"),
            "path": rel(root, Path(rpcs3["path"])) if rpcs3.get("path") else None,
            "lines": rpcs3.get("lines"),
            "note": rpcs3.get("note") or rpcs3.get("error"),
            "top_mentions": list(sorted(rpcs3_counts.items(), key=lambda kv: -kv[1]))[:25],
        },
        "top10_next": [
            {
                "rank": i,
                "nid": r["nid"],
                "name": r["name"],
                "module": r["module"],
                "status": r["status"],
                "group": r["group_en"],
                "group_ar": r["group_ar"],
                "calls": r["calls"],
                "used": r["used"],
                "stage_top": r["stage_top"],
                "rpcs3_mentions": r["rpcs3_mentions"],
                "reason_ar": (
                    f"{status_ar(r['status'])} · "
                    + (f"اللعبة نادتها حوالي {r['calls']:,} مرة" if r["used"] else "ما ظهرت في سجلات التشغيل")
                    + (f" · مرحلة: {r['stage_top']}" if r["used"] else "")
                    + (f" · في سجل RPCS3 ذُكرت {r['rpcs3_mentions']:,} مرة" if r["rpcs3_mentions"] else "")
                    + f" · {r['why_ar']}"
                ),
                "reason_en": (
                    f"{r['status']} {r['module']}::{r['name']}; calls={r['calls']}; "
                    f"stage={r['stage_top']}; rpcs3={r['rpcs3_mentions']}; {r['why_ar']}"
                ),
                "why_ar": r["why_ar"],
            }
            for i, r in enumerate(top10, 1)
        ],
        "used_stub_or_missing": [
            {
                "nid": r["nid"], "name": r["name"], "module": r["module"], "status": r["status"],
                "calls": r["calls"], "stage_top": r["stage_top"], "group": r["group_en"],
                "rpcs3_mentions": r["rpcs3_mentions"],
            }
            for r in fixable if r["used"]
        ],
        "by_module": {},
        "caveats": [
            "Body classification is a heuristic (ASSUMED); short real getters should count as implemented.",
            "Uncertain = registered but the body was not found by the scanner.",
            "HLE log call counts only see functions that print [HLE] name(.",
            "RPCS3 mentions are not exact call counts (غير مؤكد).",
            "Logs over --max-log-mb were skipped.",
        ],
        "all": [
            {k: r[k] for k in (
                "nid", "name", "module", "status", "why_ar", "group_en", "group_ar",
                "calls", "used", "stage_top", "rpcs3_mentions", "score",
            )}
            for r in rows
        ],
    }
    mods = defaultdict(lambda: Counter())
    for r in rows:
        mods[r["module"]][r["status"]] += 1
    report["by_module"] = {m: dict(c) for m, c in sorted(mods.items())}

    json_path = out / "syscall_coverage.json"
    write_json(json_path, report)

    L = []
    L.append("# تغطية دوال النظام\n")
    L.append(f"توليد: {report['generated']}\n")
    L.append(f"- منفَّذة: **{implemented}** من **{total}** ({report['counts']['percent_implemented']}%)")
    L.append(f"- دمية: {by_status.get('stub', 0)}  ·  جزئية: {by_status.get('partial', 0)}  ·  "
             f"ناقصة: {by_status.get('missing', 0)}  ·  غير مؤكد: {by_status.get('uncertain', 0)}")
    if same:
        L.append(f"- يطابق الرقم المنشور سابقاً: {pub_i}/{pub_t}")
    else:
        L.append(f"- يختلف عن الرقم المنشور {pub_i}/{pub_t} (التصنيف آلي غير مؤكد).")
    L.append("\n## أهم 10 دوال نصلحها بعدها (دمية أو ناقصة، مرتبة حسب استخدام اللعبة والأثر)\n")
    L.append("| # | NID | الاسم | المكتبة | الحالة | النداءات | المرحلة | السبب |")
    L.append("|---|---|---|---|---|---:|---|---|")
    for t in report["top10_next"]:
        L.append(f"| {t['rank']} | {t['nid']} | {t['name']} | {t['module']} | {status_ar(t['status'])} | "
                 f"{t['calls']} | {t['stage_top']} | {t['reason_ar']} |")
    md_path = out / "syscall_coverage.md"
    md_path.write_text("\n".join(L) + "\n", encoding="utf-8")

    img_items = []
    for t in report["top10_next"]:
        img_items.append({
            "rank": t["rank"],
            "name": f"{t['name']}  ({t['module']})",
            "meta": f"{status_ar(t['status'])} · {t['group_ar']} · نداءات {t['calls']:,} · {t['stage_top']}",
            "reason": t["reason_ar"],
        })
    img_path = out / "syscall_coverage.png"
    badge = "تغيّر الرقم" if not same else None
    render_top10_card(
        img_path,
        title_ar="تغطية دوال النظام",
        subtitle_ar="الدوال الناقصة أو الفاضية اللي اللعبة تناديها — مرتبة حسب الاستخدام والأثر",
        count_line_ar=f"وصلنا {implemented} من {total} دالة نظام ({report['counts']['percent_implemented']}٪)",
        count_detail_ar=(
            f"دمية: {by_status.get('stub', 0)}  ·  ناقصة: {by_status.get('missing', 0)}  ·  غير مؤكد: {by_status.get('uncertain', 0)}"
            + (f"  ·  نفس الرقم المنشور {pub_i}/{pub_t}" if same else f"  ·  الرقم المنشور كان {pub_i}/{pub_t}")
        ),
        items=img_items or [{"rank": 0, "name": "ما في دوال ناقصة في القائمة", "meta": "", "reason": ""}],
        footer_ar=f"توليد {report['generated']} · التصنيف آلي غير مؤكد\nمرجع RPCS3 للسلوك فقط · ما تم تشغيل اللعبة",
        badge=badge,
    )

    print(f"[nid] counts={report['counts']}")
    print(f"[nid] wrote {json_path}")
    print(f"[nid] wrote {md_path}")
    print(f"[nid] wrote {img_path}")
    print("TOP10:")
    for t in report["top10_next"]:
        print(f"  {t['rank']:2d}. {t['nid']} {t['name']}  [{t['status']}/{t['group']}]  "
              f"calls={t['calls']}  {t['reason_en'][:160]}")


if __name__ == "__main__":
    main()

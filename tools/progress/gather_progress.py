#!/usr/bin/env python3
"""Recompute the Strikeforce (BLUS30471) progress meter from counted sources.

Every number in the output is either counted from a file or copied from
sources.json with its citation. The script never invents an overall
"game done %" and marks missing measurements as uncertain.

Usage:
  python3 gather_progress.py
  python3 gather_progress.py --log /path/to/stderr.log --movie-dir /path/to/USRDIR/movie

Writes (next to this script, or --out-dir):
  progress.json
  progress.md
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KUWAIT = datetime.timezone(datetime.timedelta(hours=3), name="Asia/Kuwait")

MOVIE_RE = re.compile(r"movie/movie(\d+)\.pam")
CACHE_RE = re.compile(r"/cache/BLUS30471/(\w+)")
FS_OPEN_RE = re.compile(r"\[fs\] open '([^']+)'")
STORY_RE = re.compile(r"Story:\s*(.+?)(?:\"|$)", re.M)
AUTOLINK_COUNTS_RE = re.compile(
    r"conditional=(\d+),\s*linked=(\d+),\s*missing=(\d+),\s*partial=(\d+),\s*stub=(\d+)"
)
AUTOLINK_IMPORTS_RE = re.compile(r"imports:\s*(\d+)\s+unique NIDs")


def now_kuwait() -> datetime.datetime:
    return datetime.datetime.now(tz=KUWAIT)


def iso_kuwait(dt: datetime.datetime | None = None) -> str:
    d = dt or now_kuwait()
    return d.strftime("%Y-%m-%d %H:%M Asia/Kuwait (UTC+3)")


def load_sources(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def count_functions(path: Path) -> dict:
    if not path.is_file():
        return {
            "count": None,
            "status": "uncertain",
            "note_ar": "ملف قائمة الدوال غير موجود.",
            "source": str(path),
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    n = len(data) if isinstance(data, list) else None
    return {
        "count": n,
        "status": "counted" if n is not None else "uncertain",
        "source": str(path),
        "mtime_kuwait": iso_kuwait(datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=KUWAIT)),
        "bytes": path.stat().st_size,
    }


def parse_autolink(report_dir: Path, v2_dir: Path) -> dict:
    line_file = report_dir / "autolink_line.txt"
    summary = report_dir / "summary.md"
    result = {
        "linked": None,
        "stub": None,
        "missing": None,
        "conditional": None,
        "partial": None,
        "total": None,
        "source": str(line_file if line_file.is_file() else summary),
        "v2_present": v2_dir.is_dir(),
        "v2_changed_counts": False,
        "status": "uncertain",
    }
    text = ""
    if line_file.is_file():
        text = line_file.read_text(encoding="utf-8", errors="replace")
        result["source_mtime_kuwait"] = iso_kuwait(
            datetime.datetime.fromtimestamp(line_file.stat().st_mtime, tz=KUWAIT)
        )
    m = AUTOLINK_COUNTS_RE.search(text)
    imp = AUTOLINK_IMPORTS_RE.search(text)
    if m:
        result.update(
            {
                "conditional": int(m.group(1)),
                "linked": int(m.group(2)),
                "missing": int(m.group(3)),
                "partial": int(m.group(4)),
                "stub": int(m.group(5)),
                "status": "counted",
            }
        )
    if imp:
        result["total"] = int(imp.group(1))
    # Cross-check summary.md table if present
    if summary.is_file() and result["status"] == "counted":
        sm = summary.read_text(encoding="utf-8", errors="replace")
        table = {}
        for label in ("linked", "partial", "stub", "conditional", "missing"):
            tm = re.search(rf"\|\s*{label}\s*\|\s*(\d+)\s*\|", sm)
            if tm:
                table[label] = int(tm.group(1))
        tm = re.search(r"\|\s*\*\*total\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|", sm)
        if tm:
            table["total"] = int(tm.group(1))
        result["summary_crosscheck"] = table
        mismatch = [k for k in table if result.get(k) is not None and table[k] != result[k]]
        result["summary_matches"] = not mismatch
    # v2: record presence; do not invent new classification counts
    if v2_dir.is_dir():
        run_lines = v2_dir / "run_lines.txt"
        result["v2_files"] = sorted(p.name for p in v2_dir.iterdir() if p.is_file())
        if run_lines.is_file():
            rl = run_lines.read_text(encoding="utf-8", errors="replace")
            result["v2_run_lines_excerpt"] = rl.strip().splitlines()[:4]
            cm = re.search(r"callgraph:\s*(\d+)\s+imports.*?functions=(\d+)", rl)
            if cm:
                result["v2_callgraph_imports"] = int(cm.group(1))
                result["v2_callgraph_functions"] = int(cm.group(2))
        # If a newer report.csv appears under v2 with a status column, count it
        v2_csv = v2_dir / "report.csv"
        if v2_csv.is_file():
            counts = Counter()
            with v2_csv.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames and "status" in (reader.fieldnames or []):
                    for row in reader:
                        counts[row["status"].strip().lower()] += 1
            if counts:
                result["v2_csv_counts"] = dict(counts)
                result["v2_changed_counts"] = True
    if result["total"] and result["linked"] is not None:
        parts = ["linked", "stub", "missing", "conditional", "partial"]
        s = sum(result[k] or 0 for k in parts)
        result["parts_sum_equals_total"] = s == result["total"]
    return result


def count_movie_dir(movie_dir: Path | None) -> dict:
    if not movie_dir:
        return {"count": None, "status": "not_provided", "source": None}
    if not movie_dir.is_dir():
        return {"count": None, "status": "missing_dir", "source": str(movie_dir)}
    files = sorted(p.name for p in movie_dir.iterdir() if p.is_file() and re.fullmatch(r"movie\d+\.pam", p.name, re.I))
    nums = sorted(int(re.search(r"(\d+)", n).group(1)) for n in files)
    return {
        "count": len(files),
        "status": "counted",
        "source": str(movie_dir),
        "files": files,
        "min": nums[0] if nums else None,
        "max": nums[-1] if nums else None,
        "contiguous_000_to_045": nums == list(range(46)),
    }


def parse_play_log(path: Path) -> dict:
    out = {
        "path": str(path) if path else None,
        "exists": bool(path) and path.is_file(),
        "status": "missing_log",
    }
    if not out["exists"]:
        out["note_ar"] = "ملف اللوق غير موجود."
        return out

    movies: OrderedDict[int, dict] = OrderedDict()
    atrac = Counter()
    cellatrac = 0
    unresolved = Counter()
    story_hits = []
    player_hits = []
    fs_opens = 0
    unique_paths = set()
    cache_ids_last = []
    bursts = []
    cur = None
    last_fs = None
    line_no = 0
    trophy_threads = []
    voice_bin = []
    halt_lines = []

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_no += 1
            s = line.rstrip("\n")

            if "Story:" in s:
                story_hits.append({"line": line_no, "text": s.strip()[:400]})
            if "Player:" in s:
                player_hits.append({"line": line_no, "text": s.strip()[:400]})

            mm = MOVIE_RE.search(s)
            if mm:
                num = int(mm.group(1))
                rec = movies.setdefault(
                    num,
                    {
                        "id": f"movie{num:03d}",
                        "first_line": line_no,
                        "last_line": line_no,
                        "reports": [],
                    },
                )
                rec["last_line"] = line_no
                if "[sf-movie] REPORT" in s:
                    rec["reports"].append({"line": line_no, "text": s.strip()[:500]})

            if "[cellAtrac]" in s:
                cellatrac += 1
                if "Channel unit extension" in s:
                    atrac["channel_unit_extension"] += 1
                elif "Frame data doesn't match channel configuration" in s:
                    atrac["frame_ch_config"] += 1
                elif "Invalid start bit" in s:
                    atrac["invalid_start_bit"] += 1
                elif "Invalid number of transmitted units" in s:
                    atrac["invalid_units"] += 1
                elif "WL index out of range" in s:
                    atrac["wl_index"] += 1
                elif "Invalid gain location" in s:
                    atrac["invalid_gain"] += 1
                elif "Invalid number of quantization units" in s:
                    atrac["invalid_quant_units"] += 1
                elif "SetData" in s:
                    atrac["setdata"] += 1
                else:
                    atrac["other"] += 1

            if "UNRESOLVED NID" in s:
                nidm = re.search(r"UNRESOLVED NID\s+(0x[0-9A-Fa-f]+)", s)
                unresolved[nidm.group(1) if nidm else "unknown"] += 1

            if re.search(r"\bheqi\b|SPU halt|job halt", s, re.I):
                if len(halt_lines) < 20:
                    halt_lines.append({"line": line_no, "text": s.strip()[:300]})

            if "name=\"Trophy\"" in s or "name='Trophy'" in s:
                trophy_threads.append(line_no)
            if "Voice.bin" in s and "[fs] open" in s:
                voice_bin.append({"line": line_no, "text": s.strip()[:300]})

            if "[fs] open" in s:
                fs_opens += 1
                pm = FS_OPEN_RE.search(s)
                if pm:
                    unique_paths.add(pm.group(1))
                if "/cache/BLUS30471/" in s:
                    if last_fs is not None and line_no - last_fs > 500:
                        if cur:
                            bursts.append(cur)
                        cur = {"start": line_no, "end": line_no, "opens": 1, "ids": []}
                    elif cur is None:
                        cur = {"start": line_no, "end": line_no, "opens": 1, "ids": []}
                    else:
                        cur["end"] = line_no
                        cur["opens"] += 1
                    cm = CACHE_RE.search(s)
                    if cm:
                        cur["ids"].append(cm.group(1))
                        cache_ids_last.append(cm.group(1))
                    last_fs = line_no

    if cur:
        bursts.append(cur)

    compact_bursts = []
    for b in bursts:
        uniq = list(dict.fromkeys(b["ids"]))
        compact_bursts.append(
            {
                "start_line": b["start"],
                "end_line": b["end"],
                "opens": b["opens"],
                "unique_ids": len(uniq),
                "first_ids": uniq[:8],
                "last_ids": uniq[-8:],
                "kind": "area_load" if len(uniq) >= 20 else "small",
            }
        )

    movie_summaries = []
    for num, rec in movies.items():
        shown = decoded = None
        kind = None
        clock = None
        rms = None
        for r in rec["reports"]:
            m = re.search(
                r"\((end of stream|stop|close)\):\s*frames decoded\s+(\d+)\s+shown\s+(\d+).*?clock\s+([0-9.]+)\s*s",
                r["text"],
            )
            if m:
                kind, decoded, shown, clock = m.group(1), int(m.group(2)), int(m.group(3)), float(m.group(4))
            rm = re.search(r"rms\[([^\]]+)\]", r["text"])
            if rm:
                rms = rm.group(1)
        played_to_end = bool(rec["reports"]) and (shown or 0) > 0 and (
            any("end of stream" in r["text"] for r in rec["reports"])
            or (decoded is not None and shown is not None and shown >= max(decoded - 10, 1))
        )
        has_sound = False
        if rms:
            try:
                has_sound = any(float(x) > 0 for x in rms.split(","))
            except ValueError:
                has_sound = False
        movie_summaries.append(
            {
                "id": rec["id"],
                "first_line": rec["first_line"],
                "last_line": rec["last_line"],
                "frames_decoded": decoded,
                "frames_shown": shown,
                "clock_s": clock,
                "last_report_kind": kind,
                "rms": rms,
                "picture_shown": (shown or 0) > 0,
                "sound_nonzero_rms": has_sound,
                "played_through": played_to_end,
                "report_count": len(rec["reports"]),
            }
        )

    large = [b for b in compact_bursts if b["kind"] == "area_load"]
    last_ids = cache_ids_last[-2:] if cache_ids_last else []

    out.update(
        {
            "status": "counted",
            "mtime_kuwait": iso_kuwait(datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=KUWAIT)),
            "bytes": path.stat().st_size,
            "lines": line_no,
            "story_hits": story_hits,
            "player_hits": player_hits,
            "movies_opened": movie_summaries,
            "atrac": {
                "cellatrac_lines": cellatrac,
                "channel_unit_extension": atrac["channel_unit_extension"],
                "frame_ch_config": atrac["frame_ch_config"],
                "invalid_start_bit": atrac["invalid_start_bit"],
                "invalid_units": atrac["invalid_units"],
                "wl_index": atrac["wl_index"],
                "invalid_gain": atrac["invalid_gain"],
                "invalid_quant_units": atrac["invalid_quant_units"],
                "setdata": atrac["setdata"],
                "other": atrac["other"],
            },
            "unresolved_nids": dict(unresolved),
            "trophy_thread_lines": trophy_threads,
            "voice_bin_opens": voice_bin,
            "halt_lines": halt_lines,
            "fs_opens": fs_opens,
            "unique_paths": len(unique_paths),
            "cache_bursts": compact_bursts,
            "area_load_bursts": len(large),
            "last_cache_ids": last_ids,
            "last_area_load": large[-1] if large else None,
        }
    )
    return out


def build_report(sources: dict, functions: dict, hle: dict, movies_dir: dict, play: dict, generated: str) -> dict:
    q = sources["quests"]
    breakdown_sum = sum(x["count"] for x in q["breakdown"])
    movie_total = sources["movies"]["documented_total"]
    movie_total_source = sources["movies"]["documented_total_source_ar"]
    if movies_dir.get("status") == "counted" and movies_dir.get("count") is not None:
        movie_total = movies_dir["count"]
        movie_total_source = f"عدّ ملفات movie*.pam في {movies_dir['source']}"

    verified = sources["movies"]["verified_in_1786_movie_v5"]
    verified_n = len(verified)
    untested = movie_total - verified_n if movie_total is not None else None

    story_text = None
    if play.get("story_hits"):
        # Prefer the full "Story: ..." capture; the save string may span lines
        raw = " | ".join(h["text"] for h in play["story_hits"][:3])
        story_text = raw
        sm = re.search(r"Story:\s*([^\"|]+)", raw)
        if sm:
            story_text = sm.group(1).strip().rstrip('"')

    played_movies = [m for m in play.get("movies_opened") or [] if m.get("played_through")]
    opened_zero = [m for m in play.get("movies_opened") or [] if (m.get("frames_shown") or 0) == 0]

    fn_count = functions.get("count")
    hle_linked = hle.get("linked")
    hle_total = hle.get("total")

    report = {
        "generated_at": generated,
        "rule_ar": "ما فيه نسبة واحدة لـ«كم خلصت اللعبة». كل رقم إما معدود من مصدر، أو مكتوب غير مؤكد.",
        "game": sources["game"],
        "story": {
            "force_and_chapter": story_text,
            "force_and_chapter_source": (
                f"{play.get('path')} السطر {play['story_hits'][0]['line']}"
                if play.get("story_hits")
                else None
            ),
            "completed_mission_count": None,
            "completed_mission_count_status": "uncertain",
            "completed_mission_count_note_ar": "اللوق ما يكتب اسم المهمة ولا عدد المهام المكمّلة. ما نقدر نحول وصول سعود إلى نسبة من 272 أو من 7.",
            "all_quests_total": q["complete_all_quests_total"],
            "all_quests_total_checks_out": breakdown_sum == q["complete_all_quests_total"],
            "breakdown_sum": breakdown_sum,
            "breakdown": q["breakdown"],
            "chapter1_unique_for_one_force": q["chapter1_unique_for_one_force"]["count"],
            "quest_sources": q["chapter1_unique_for_one_force"]["sources"] + [q["source_url"]],
            "today_events_ar": [
                "عدا البوابة",
                "ذبح زعيم",
                "وصل القرية",
                "علّق التحميل بعد مهمة القرية (آخر شاشة سوداء)",
            ],
            "today_events_source_ar": "كلام سعود في جلسة اللعب، مع لوق الجلسة.",
            "likely_mission_ar": "فخ قطاع الطرق (Bandit Trap)",
            "likely_mission_status": "uncertain",
            "likely_mission_note_ar": q["chapter1_unique_for_one_force"]["first_request_note_ar"]
            + " تعليق البوابة السابق اتسمى على هالمهمة في findings.md. اللوق الحالي ما فيه اسم المهمة مكتوباً، وآخر ملفات الكاش كانت أرقاماً بدون خريطة أسماء.",
            "last_cache_ids": play.get("last_cache_ids"),
            "area_load_bursts": play.get("area_load_bursts"),
            "play_log": play.get("path"),
        },
        "movies": {
            "total": movie_total,
            "total_source_ar": movie_total_source,
            "verified_working": verified_n,
            "verified_ids": [v["id"] for v in verified],
            "verified_source": sources["movies"]["v5_evidence"],
            "verified_build": sources["movies"]["v5_build"],
            "untested": untested,
            "ratio_verified_over_total": f"{verified_n}/{movie_total}" if movie_total else None,
            "this_session_opened": play.get("movies_opened") or [],
            "this_session_played_through": [m["id"] for m in played_movies],
            "this_session_opened_zero_frames": [m["id"] for m in opened_zero],
        },
        "code": {
            "converted": fn_count,
            "converted_total": fn_count,
            "ratio": f"{fn_count}/{fn_count}" if fn_count else None,
            "source": functions.get("source"),
            "source_mtime_kuwait": functions.get("mtime_kuwait"),
            "executed_in_play": None,
            "executed_in_play_status": "uncertain",
            "executed_in_play_note_ar": sources["code"]["executed_coverage_note_ar"],
        },
        "hle": {
            "linked": hle_linked,
            "stub": hle.get("stub"),
            "missing": hle.get("missing"),
            "conditional": hle.get("conditional"),
            "partial": hle.get("partial"),
            "total": hle_total,
            "ratio_linked_over_total": f"{hle_linked}/{hle_total}" if hle_linked is not None and hle_total else None,
            "parts_sum_equals_total": hle.get("parts_sum_equals_total"),
            "source": hle.get("source"),
            "source_mtime_kuwait": hle.get("source_mtime_kuwait"),
            "v2_present": hle.get("v2_present"),
            "v2_changed_counts": hle.get("v2_changed_counts"),
            "v2_callgraph_imports": hle.get("v2_callgraph_imports"),
            "v2_callgraph_functions": hle.get("v2_callgraph_functions"),
            "note_ar": sources["hle"]["classification_source_note_ar"],
        },
        "audio_in_play_log": play.get("atrac"),
        "blockers": [
            {
                "id": "village_load_freeze",
                "title_ar": "تعليق التحميل بعد مهمة القرية",
                "status_ar": "مفتوح — هذه أهم عقبة الحين",
                "tone": "danger",
                "done": False,
                "source_ar": f"جلسة سعود ولوق {play.get('path')}. آخر ملفات الكاش: {', '.join(play.get('last_cache_ids') or [])}. ما فيه تقرير كراش من ويندوز.",
            },
            {
                "id": "gate_freeze_root",
                "title_ar": "سبب تعليق البوابة (الأصل)",
                "status_ar": "مفتوح — سعود عدا البوابة اليوم، بس الأصل ما تأكد. تجربة SF_RACE ما اكتملت",
                "tone": "warning",
                "done": False,
                "source_ar": "/workspace/sf-shared/voicefreeze/findings.md",
            },
            {
                "id": "atrac_extension",
                "title_ar": "فك الصوت ناقص (الصوت الخفيف)",
                "status_ar": "مفتوح — اللوق يسجّل ميزة ناقصة اسمها توسعة قناة الصوت",
                "tone": "warning",
                "done": False,
                "source_ar": f"نفس لوق الجلسة: رسالة Channel unit extension تكررت {((play.get('atrac') or {}).get('channel_unit_extension'))} مرة، مع أخطاء فك أخرى.",
            },
            {
                "id": "graphics",
                "title_ar": "الرسم: الوجوه والظلال والضباب",
                "status_ar": "مفتوح — مشاهد من اللعب والمقارنة مع المحاكي",
                "tone": "warning",
                "done": False,
                "source_ar": "ملاحظات الرسم السابقة (الوجوه، الظلال، الضباب) ما انحلّت بهالجلسة.",
            },
            {
                "id": "cloth",
                "title_ar": "القماش (الشال) ما يتحرك طبيعي",
                "status_ar": "مفتوح",
                "tone": "warning",
                "done": False,
                "source_ar": "قائمة مشاكل سعود السابقة، وصور الشال الثابت.",
            },
            {
                "id": "stutter",
                "title_ar": "تقطيع الحركة (تهنيق)",
                "status_ar": "مفتوح — سعود يحس فيه، والمتوسط ما يبيّن التقطيع القصير",
                "tone": "warning",
                "done": False,
                "source_ar": "ملاحظة سعود في جلسة اللعب. عداد النافذة متوسط، مو قياس تقطيع.",
            },
            {
                "id": "movies_untested",
                "title_ar": f"أفلام داخل المراحل ما تجرّبت ({untested} من {movie_total})" if untested is not None else "أفلام داخل المراحل ما تجرّبت",
                "status_ar": "مفتوح — الثلاث اللي بأول اللعبة انحلّت في نسخة 1786_movie_v5",
                "tone": "warning",
                "done": False,
                "source_ar": sources["movies"]["v5_evidence"],
            },
        ],
        "next_ar": [
            "حل تعليق التحميل بعد مهمة القرية، هذا اللي يمنع إكمال المرحلة.",
            "إكمال تجربة SF_RACE عشان يتأكد سبب تعليق البوابة، حتى لو انعدت اليوم.",
            "إصلاح فك الصوت الناقص (توسعة قناة الصوت) عشان كلام الشخصيات ما يبقى خفيف.",
            "متابعة الرسم: الوجوه والظلال والضباب.",
            "تحريك القماش.",
            "قياس التقطيع بعد ما يخف اللوق الثقيل.",
            "تجربة باقي الأفلام لما نقدر نلعب المراحل.",
            "تشغيل المختبر الآلي عشان يعدّ الدوال اللي اشتغلت فعلاً وقت اللعب.",
        ],
        "inputs": {
            "play_log": play,
            "functions": functions,
            "hle_raw": {k: v for k, v in hle.items() if k != "v2_run_lines_excerpt"},
            "movie_dir": movies_dir,
        },
    }
    return report


def render_md(report: dict) -> str:
    s = report["story"]
    m = report["movies"]
    c = report["code"]
    h = report["hle"]
    a = report.get("audio_in_play_log") or {}
    lines = [
        f"# مقياس تقدّم سترايك فورس (BLUS30471)",
        "",
        f"تاريخ التوليد: {report['generated_at']}",
        "",
        report["rule_ar"],
        "",
        "## القصة والمهام",
        "",
        f"- القوة والفصل (من اللوق): {s.get('force_and_chapter') or 'غير مؤكد'}",
        f"  المصدر: {s.get('force_and_chapter_source') or 'غير مؤكد'}",
        f"- عدد المهام المكمّلة: غير مؤكد. {s.get('completed_mission_count_note_ar')}",
        f"- إجمالي المهام لإكمال كل شيء (الثلاث قوى + الجانبية + الأساطير + التقاطع): {s.get('all_quests_total')} (مجموع الفروع {s.get('breakdown_sum')}، يتطابق: {s.get('all_quests_total_checks_out')})",
        f"- مهام الفصل 1 لقوة واحدة: {s.get('chapter1_unique_for_one_force')}",
        f"- مهمة اليوم (غير مؤكد): {s.get('likely_mission_ar')}",
        f"- آخر ملفات الكاش: {s.get('last_cache_ids')}",
        f"- عدد تحميلات المنطقة الكبيرة في اللوق: {s.get('area_load_bursts')}",
        "",
        "## الأفلام",
        "",
        f"- المتحقق إنها تشتغل (صورة + نهاية) في {m.get('verified_build')}: {m.get('verified_working')} من {m.get('total')} = {m.get('ratio_verified_over_total')}",
        f"- ما تجرّبت: {m.get('untested')}",
        f"- المصدر (الاختبار): {m.get('verified_source')}",
        f"- مصدر العدد الكلي: {m.get('total_source_ar')}",
        f"- في جلسة اللعب هذي اشتغلت لين النهاية: {', '.join(m.get('this_session_played_through') or []) or 'لا شيء'}",
        f"- انفتحت وصفر صور: {', '.join(m.get('this_session_opened_zero_frames') or []) or 'لا شيء'}",
        "",
        "## تحويل الدوال",
        "",
        f"- التحويل: {c.get('ratio')} المصدر: {c.get('source')} ({c.get('source_mtime_kuwait')})",
        f"- الدوال اللي اشتغلت فعلاً وقت اللعب: غير مؤكد. {c.get('executed_in_play_note_ar')}",
        "",
        "## دوال النظام",
        "",
        f"- مربوطة {h.get('linked')}، هيكل فارغ {h.get('stub')}، ناقصة {h.get('missing')}، مشروطة {h.get('conditional')}، ناقصة جزئياً {h.get('partial')}، المجموع {h.get('total')} (النسبة المربوطة {h.get('ratio_linked_over_total')})",
        f"- المصدر: {h.get('source')} ({h.get('source_mtime_kuwait')})",
        f"- v2 موجود: {h.get('v2_present')}، غيّر التصنيف: {h.get('v2_changed_counts')}",
        f"- {h.get('note_ar')}",
        "",
        "## فك الصوت في لوق الجلسة",
        "",
        f"- أسطر فك الصوت: {a.get('cellatrac_lines')}",
        f"- توسعة قناة الصوت ناقصة: {a.get('channel_unit_extension')}",
        f"- اختلاف إعداد القنوات: {a.get('frame_ch_config')}",
        f"- بداية إطار غير صحيحة: {a.get('invalid_start_bit')}",
        "",
        "## المشاكل المفتوحة",
        "",
    ]
    for b in report["blockers"]:
        lines.append(f"- {b['title_ar']}: {b['status_ar']} — {b['source_ar']}")
    lines += ["", "## الخطوة الجاية", ""]
    for i, step in enumerate(report["next_ar"], 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sources", type=Path, default=HERE / "sources.json")
    ap.add_argument("--log", type=Path, default=None, help="Play stderr log (defaults to sources.json default_play_log)")
    ap.add_argument("--functions", type=Path, default=None)
    ap.add_argument("--autolink-dir", type=Path, default=None)
    ap.add_argument("--autolink-v2-dir", type=Path, default=None)
    ap.add_argument("--movie-dir", type=Path, default=None, help="USRDIR/movie folder to recount movie*.pam")
    ap.add_argument("--out-dir", type=Path, default=HERE)
    args = ap.parse_args(argv)

    sources = load_sources(args.sources)
    functions = count_functions(args.functions or Path(sources["code"]["guest_functions_source"]))
    hle = parse_autolink(
        args.autolink_dir or Path(sources["hle"]["report_dir"]),
        args.autolink_v2_dir or Path(sources["hle"]["prefer_v2_dir"]),
    )
    movies_dir = count_movie_dir(args.movie_dir)
    play = parse_play_log(args.log or Path(sources["default_play_log"]))
    generated = iso_kuwait()
    report = build_report(sources, functions, hle, movies_dir, play, generated)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "progress.json"
    md_path = out_dir / "progress.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_md(report), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"generated {generated}")
    print(f"story: {report['story'].get('force_and_chapter')}")
    print(f"movies: {report['movies'].get('ratio_verified_over_total')} verified; session played {report['movies'].get('this_session_played_through')}")
    print(f"code: {report['code'].get('ratio')}; executed={report['code'].get('executed_in_play_status')}")
    print(f"hle: {report['hle'].get('ratio_linked_over_total')} linked; v2_changed={report['hle'].get('v2_changed_counts')}")
    print(f"atrac channel_unit_extension: {(report.get('audio_in_play_log') or {}).get('channel_unit_extension')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

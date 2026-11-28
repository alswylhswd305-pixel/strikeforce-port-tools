#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Shared helpers for rsx_coverage / syscall_coverage (no game launch)."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from arabic_shape import shape_visual

TZ_LABEL = "توقيت الكويت (UTC+3)"
TZ_LABEL_EN = "Asia/Kuwait (UTC+3)"

SKIP_DIR_NAMES = {
    "vfs", "firmware-local", "recompiled", ".git", "spu", "known_good",
    "__pycache__", "node_modules", "dev_hdd0", "dev_hdd1", "dev_flash",
    "dev_bdvd", ".venv", "vcpkg",
}

# Published counts this tool is meant to re-measure (gen_coverage 2026-11-27,
# nid-coverage 2026-11-26). Both are mechanical / heuristic (ASSUMED).
PUBLISHED_RSX = (376, 798)
PUBLISHED_NID = (267, 346)


def now_kwt() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + TZ_LABEL_EN


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def find_root(explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_dir():
            raise SystemExit(f"root not found: {p}")
        return p
    env = os.environ.get("SF_TEST_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = script_dir()
    # sfauto/coverage_tools/ -> test copy root
    for cand in (here.parent.parent, here.parent, Path.cwd()):
        if (cand / "port").is_dir() and (cand / "ps3recomp").is_dir():
            return cand.resolve()
    return Path.cwd().resolve()


def default_out(root: Path) -> Path:
    here = script_dir()
    # Prefer writing next to the tools (test copy or box mirror).
    if (here.parent / "exe_copies").is_dir() or here.parent.name.lower() == "sfauto":
        return here / "out"
    # Box mirror: still write beside the tools, and also under root if it is the test copy.
    if (root / "sfauto").is_dir():
        return root / "sfauto" / "coverage_tools" / "out"
    return here / "out"


def should_skip_dir(path: Path) -> bool:
    return path.name.lower() in SKIP_DIR_NAMES or path.name.endswith(".bak")


def walk_files(root: Path, names=None, suffixes=None, extra_skip=()):
    """Yield files under root, skipping bulky / irrelevant trees."""
    want_names = {n.lower() for n in names} if names else None
    want_suf = {s.lower() for s in suffixes} if suffixes else None
    skip = {s.lower() for s in extra_skip}
    for dirpath, dirnames, filenames in os.walk(root):
        p = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in SKIP_DIR_NAMES
            and d.lower() not in skip
            and not d.endswith(".bak")
            and not d.startswith(".")
        ]
        for fn in filenames:
            if want_names and fn.lower() not in want_names:
                continue
            if want_suf and not any(fn.lower().endswith(s) for s in want_suf):
                continue
            yield p / fn


def rel(root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_font() -> str:
    here = script_dir()
    env = os.environ.get("SF_ARABIC_FONT") or os.environ.get("SF_AT_FONT")
    cands = [
        Path(env) if env else None,
        here / "fonts" / "NotoNaskhArabic-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
        Path("/usr/share/fonts/truetype/sand-box/google/Noto Naskh Arabic/NotoNaskhArabic-VariableFont_wght.ttf"),
        Path(r"C:\Windows\Fonts\NotoNaskhArabic-Regular.ttf"),
        Path(r"C:\Windows\Fonts\trado.ttf"),
        Path(r"C:\Windows\Fonts\arabtype.ttf"),
    ]
    for c in cands:
        if c is not None and c.is_file():
            return str(c)
    fonts_root = Path("/usr/share/fonts")
    if fonts_root.is_dir():
        for p in fonts_root.rglob("*"):
            if p.suffix.lower() in {".ttf", ".otf", ".ttc"} and "arabic" in p.name.lower():
                return str(p)
    raise FileNotFoundError("No Arabic font found. Place NotoNaskhArabic-Regular.ttf in tools/coverage_tools/fonts/, or set SF_ARABIC_FONT.")


def render_top10_card(
    path: Path,
    *,
    title_ar: str,
    subtitle_ar: str,
    count_line_ar: str,
    count_detail_ar: str,
    items: list[dict],
    footer_ar: str,
    badge: str | None = None,
) -> None:
    """Arabic summary image. Top-10 rows are highlighted in red.

    Each item: {rank, name, meta, reason} (Arabic or mixed).
    """
    from PIL import Image, ImageDraw, ImageFont

    font_path = find_font()
    W, margin = 1400, 48
    title_f = ImageFont.truetype(font_path, 54)
    sub_f = ImageFont.truetype(font_path, 28)
    count_f = ImageFont.truetype(font_path, 40)
    detail_f = ImageFont.truetype(font_path, 24)
    row_name_f = ImageFont.truetype(font_path, 26)
    row_meta_f = ImageFont.truetype(font_path, 22)
    row_reason_f = ImageFont.truetype(font_path, 22)
    footer_f = ImageFont.truetype(font_path, 20)
    badge_f = ImageFont.truetype(font_path, 22)

    bg = (18, 18, 22)
    paper = (28, 28, 34)
    text = (236, 232, 224)
    muted = (176, 172, 164)
    red = (196, 48, 48)
    red_bg = (72, 22, 24)
    red_border = (210, 70, 70)
    line = (50, 50, 58)
    accent = (232, 196, 120)

    # Measure height
    row_h = 118
    header_h = 280
    footer_h = 90
    H = header_h + len(items) * row_h + footer_h + margin
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)

    def rtl(x_right, y, s, font, fill):
        vis = shape_visual(s)
        w = d.textlength(vis, font=font)
        d.text((x_right - w, y), vis, font=font, fill=fill)
        return w

    right = W - margin
    y = margin
    rtl(right, y, title_ar, title_f, text)
    y += 72
    rtl(right, y, subtitle_ar, sub_f, muted)
    y += 48
    # gold rule
    d.rectangle([margin, y, W - margin, y + 3], fill=accent)
    y += 20
    rtl(right, y, count_line_ar, count_f, accent)
    y += 52
    rtl(right, y, count_detail_ar, detail_f, muted)
    if badge:
        bw = d.textlength(shape_visual(badge), font=badge_f) + 28
        bx = margin
        d.rounded_rectangle([bx, y - 4, bx + bw, y + 36], 8, fill=red_bg, outline=red_border)
        # badge is short Arabic; draw inside, right-aligned in the pill
        rtl(bx + bw - 12, y, badge, badge_f, (255, 220, 220))
    y += 56

    for it in items:
        rank = it.get("rank", 0)
        name = it.get("name", "")
        meta = it.get("meta", "")
        reason = it.get("reason", "")
        box = [margin, y, W - margin, y + row_h - 10]
        d.rounded_rectangle(box, 12, fill=red_bg, outline=red_border, width=2)
        # rank circle
        cx, cy = margin + 36, y + (row_h - 10) // 2
        d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=red)
        num = str(rank)
        nw = d.textlength(num, font=row_name_f)
        d.text((cx - nw / 2, cy - 16), num, font=row_name_f, fill=(255, 255, 255))
        text_right = W - margin - 20
        rtl(text_right, y + 10, name, row_name_f, (255, 236, 236))
        if meta:
            rtl(text_right, y + 42, meta, row_meta_f, (255, 200, 200))
        if reason:
            rtl(text_right, y + 70, reason, row_reason_f, (230, 210, 210))
        y += row_h

    d.rectangle([margin, y, W - margin, y + 1], fill=line)
    y += 16
    for line_s in footer_ar.split("\n"):
        rtl(right, y, line_s, footer_f, muted)
        y += 26

    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG")

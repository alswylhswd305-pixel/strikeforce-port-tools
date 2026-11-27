#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Burn Arabic red-box labels onto a screenshot and write annotations JSON.

Uses arabic_reshaper + python-bidi (required). Default font is Noto Sans Arabic.
Input is a JSON list or a --box/--label invocation.
"""
from __future__ import annotations

import argparse, json, os, sys
from datetime import datetime

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from pathlib import Path

_FONT_CANDIDATES = [
    os.environ.get("SF_AT_FONT") or "",
    os.environ.get("SF_ARABIC_FONT") or "",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-VariableFont_wdth,wght.ttf",
    "/usr/share/fonts/truetype/sand-box/google/Noto Sans Arabic/NotoSansArabic-VariableFont_wdth,wght.ttf",
    "/usr/share/fonts/truetype/sand-box/google/Noto Naskh Arabic/NotoNaskhArabic-VariableFont_wght.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\NotoNaskhArabic-Regular.ttf",
    r"C:\Windows\Fonts\trado.ttf",
]


def find_font() -> str:
    for raw in _FONT_CANDIDATES:
        if raw and os.path.isfile(raw):
            return raw
    fonts_root = Path("/usr/share/fonts")
    if fonts_root.is_dir():
        for p in fonts_root.rglob("*"):
            if p.suffix.lower() in {".ttf", ".otf", ".ttc"} and "arabic" in p.name.lower():
                return str(p)
        dejavu = fonts_root / "truetype/dejavu/DejaVuSans-Bold.ttf"
        if dejavu.is_file():
            return str(dejavu)
    raise FileNotFoundError(
        "No label font found. Install Noto Naskh Arabic or DejaVu, or set SF_AT_FONT / SF_ARABIC_FONT."
    )


def shape_ar(s: str) -> str:
    return get_display(arabic_reshaper.reshape(s))


def font(size: int):
    return ImageFont.truetype(find_font(), size=size)


def draw_label(draw: ImageDraw.ImageDraw, cx: int, y: int, text: str, fill, fnt):
    shaped = shape_ar(text)
    # textbbox is LTR after bidi visual reorder
    box = draw.textbbox((0, 0), shaped, font=fnt)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = int(cx - tw / 2)
    pad = 8
    draw.rectangle([x - pad, y - 4, x + tw + pad, y + th + 8], fill=(0, 0, 0), outline=(255, 0, 0), width=3)
    draw.text((x, y), shaped, font=fnt, fill=fill)


def annotate(src: str, dst: str, boxes: list, labels: list[str], meta: dict | None = None) -> dict:
    im = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(im)
    f_big = font(28)
    f_s = font(22)
    for b in boxes:
        if len(b) != 4:
            raise ValueError(f"box must be [x1,y1,x2,y2], got {b}")
        x1, y1, x2, y2 = [int(v) for v in b]
        d.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=5)
    w, h = im.size
    for i, lab in enumerate(labels):
        col = (255, 255, 0) if i == 0 else (255, 255, 255)
        draw_label(d, w // 2, 16 + i * 46, lab, col, f_big if i == 0 else f_s)
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    im.save(dst)
    rec = {
        "image": dst,
        "source": src,
        "time": datetime.now().isoformat(timespec="seconds"),
        "boxes": [{"box_xyxy": boxes[i] if i < len(boxes) else boxes[-1], "label_ar": labels[i] if i < len(labels) else ""} for i in range(max(len(boxes), 1))],
        "labels_ar": labels,
    }
    if meta:
        rec.update(meta)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    ap.add_argument("--json", default=None, help="write / merge annotations JSON")
    ap.add_argument("--box", action="append", default=[], help="x1,y1,x2,y2 (repeatable)")
    ap.add_argument("--label", action="append", default=[], help="Arabic label (repeatable)")
    ap.add_argument("--spec", default=None, help="JSON file: {src,dst,boxes,labels,meta}")
    args = ap.parse_args(argv)
    if args.spec:
        spec = json.load(open(args.spec, encoding="utf-8"))
        rec = annotate(spec["src"], spec["dst"], spec["boxes"], spec["labels"], spec.get("meta"))
    else:
        boxes = [[int(x) for x in b.split(",")] for b in args.box] or [[40, 40, 200, 120]]
        labels = args.label or ["لقطة اختبار"]
        rec = annotate(args.src, args.dst, boxes, labels)
    if args.json:
        data = []
        if os.path.isfile(args.json):
            data = json.load(open(args.json, encoding="utf-8"))
            if isinstance(data, dict):
                data = [data]
        data.append(rec)
        json.dump(data, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

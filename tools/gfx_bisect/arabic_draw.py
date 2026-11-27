#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Draw Arabic labels correctly on PIL images.

Primary path: Pillow + RAQM (HarfBuzz / FriBidi) with the logical string
and direction='rtl'. That applies OpenType GSUB (lam-alef, joining).

Fallback when RAQM is missing: arabic-reshaper (MIT) plus python-bidi
(LGPL — imported as a package, not copied) to emit Presentation Forms,
then draw left-to-right. Join quality is weaker without GSUB.

Font: bundled Noto Naskh Arabic (SIL OFL 1.1) in fonts/.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, features

HERE = Path(__file__).resolve().parent

# Optional bundled font, then common system locations. Tests skip if none exist.
_FONT_CANDIDATES = [
    HERE / "fonts" / "NotoNaskhArabic-Regular.ttf",
    HERE / "fonts" / "NotoNaskhArabic-Bold.ttf",
    HERE / "fonts" / "NotoNaskhArabic-VariableFont_wght.ttf",
    Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-VariableFont_wght.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansArabic-VariableFont_wdth,wght.ttf"),
    Path("/usr/share/fonts/truetype/sand-box/google/Noto Naskh Arabic/NotoNaskhArabic-VariableFont_wght.ttf"),
    Path("/usr/share/fonts/truetype/sand-box/google/Noto Sans Arabic/NotoSansArabic-VariableFont_wdth,wght.ttf"),
    Path(r"C:\Windows\Fonts\NotoNaskhArabic-Regular.ttf"),
    Path(r"C:\Windows\Fonts\trado.ttf"),  # Traditional Arabic on many Windows locales
]

def has_raqm() -> bool:
    try:
        return bool(features.check("raqm"))
    except Exception:
        return False


def _fontconfig_arabic() -> Optional[str]:
    import shutil
    import subprocess
    fc = shutil.which("fc-list")
    if not fc:
        return None
    try:
        r = subprocess.run([fc, ":lang=ar", "file"], capture_output=True, text=True, timeout=5)
    except Exception:
        return None
    preferred, any_ar = None, None
    for line in r.stdout.splitlines():
        path = line.split(":")[0].strip()
        if not path.lower().endswith((".ttf", ".otf", ".ttc")):
            continue
        if not Path(path).is_file():
            continue
        low = path.lower()
        if any_ar is None:
            any_ar = path
        if "naskh" in low or "notosansarabic" in low or "noto sans arabic" in low:
            preferred = path
            break
    return preferred or any_ar


def find_arabic_font() -> str:
    env = os.environ.get("SF_ARABIC_FONT") or os.environ.get("SF_AT_FONT")
    if env and Path(env).is_file():
        return env
    for p in _FONT_CANDIDATES:
        if p.is_file():
            return str(p)
    for root in (Path("/usr/share/fonts"), Path("/usr/local/share/fonts")):
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.suffix.lower() in {".ttf", ".otf", ".ttc"} and "arabic" in p.name.lower():
                return str(p)
    found = _fontconfig_arabic()
    if found:
        return found
    raise FileNotFoundError(
        "No Arabic font found. Place NotoNaskhArabic-Regular.ttf in tools/gfx_bisect/fonts/, "
        "install Noto Naskh Arabic, or set SF_ARABIC_FONT. Tests skip when the font is absent."
    )


@lru_cache(maxsize=8)
def load_font(size: int = 22, path: Optional[str] = None) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path or find_arabic_font(), size=int(size))


def shape_arabic(text: str) -> str:
    """Reshape Arabic letters and apply bidi so PIL can draw left-to-right.

    Used only when RAQM is unavailable. Prefer draw_label(), which uses RAQM
    on the logical string when Pillow was built with libraqm.
    """
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError as e:
        raise ImportError(
            "Arabic labels need: pip install arabic-reshaper python-bidi"
        ) from e
    # python-bidi is LGPL; we only import the installed package (see README).
    try:
        cfg = dict(arabic_reshaper.config.default_config) if hasattr(arabic_reshaper, "config") else {}
        cfg["support_ligatures"] = True
        reshaper = arabic_reshaper.ArabicReshaper(configuration=cfg)
        reshaped = reshaper.reshape(text)
    except Exception:
        reshaped = arabic_reshaper.reshape(text)
    try:
        return get_display(reshaped, base_dir="R")
    except TypeError:
        return get_display(reshaped)


def _text_kwargs(use_raqm: bool) -> dict:
    if use_raqm:
        return {"language": "ar", "direction": "rtl"}
    return {}


def prepared_text(text: str, use_raqm: Optional[bool] = None) -> Tuple[str, dict]:
    """Return (string, draw kwargs) for a Pillow text call."""
    if use_raqm is None:
        use_raqm = has_raqm()
    if use_raqm:
        return text, _text_kwargs(True)
    return shape_arabic(text), {}


def text_bbox(font: ImageFont.ImageFont, text: str, use_raqm: Optional[bool] = None):
    visual, kwargs = prepared_text(text, use_raqm)
    return font.getbbox(visual, **kwargs), visual, kwargs


def text_size(font: ImageFont.ImageFont, text: str, use_raqm: Optional[bool] = None) -> Tuple[int, int]:
    bbox, _, _ = text_bbox(font, text, use_raqm)
    return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])


def draw_label(
    img: Image.Image,
    xy: Tuple[int, int],
    text: str,
    *,
    size: int = 22,
    fill=(255, 255, 255),
    bg=(180, 0, 0),
    pad: int = 4,
    anchor: str = "lt",
    max_width: Optional[int] = None,
) -> Tuple[int, int, int, int]:
    """Draw a shaped Arabic (or mixed) label with an opaque background.

    `anchor` is 'lt' (top-left of the box at xy) or 'lb' (bottom-left).
    If `max_width` is set, the font shrinks so the box fits that width.
    Returns the box (x0,y0,x1,y1) actually painted.
    """
    use_raqm = has_raqm()
    font = load_font(size)
    tw, th = text_size(font, text, use_raqm)
    if max_width is not None:
        while size > 11 and tw + 2 * pad > max_width:
            size -= 2
            font = load_font(size)
            tw, th = text_size(font, text, use_raqm)
        tw = min(tw, max(8, max_width - 2 * pad))
    x, y = int(xy[0]), int(xy[1])
    if anchor == "lb":
        y = y - th - 2 * pad
    elif anchor == "rt":
        x = x - tw - 2 * pad
    elif anchor == "rb":
        x = x - tw - 2 * pad
        y = y - th - 2 * pad
    x0, y0 = x, y
    x1, y1 = x + tw + 2 * pad, y + th + 2 * pad
    # Clamp into the image so a box at the edge stays readable.
    dx = 0 if x0 >= 0 else -x0
    dy = 0 if y0 >= 0 else -y0
    if x1 + dx > img.width:
        dx = img.width - x1
    if y1 + dy > img.height:
        dy = img.height - y1
    x0, x1, y0, y1 = x0 + dx, x1 + dx, y0 + dy, y1 + dy
    draw = ImageDraw.Draw(img, "RGBA" if img.mode == "RGBA" else "RGB")
    draw.rectangle([x0, y0, x1, y1], fill=bg)
    bbox, visual, kwargs = text_bbox(font, text, use_raqm)
    draw.text((x0 + pad - bbox[0], y0 + pad - bbox[1]), visual, font=font, fill=fill, **kwargs)
    return (x0, y0, x1, y1)

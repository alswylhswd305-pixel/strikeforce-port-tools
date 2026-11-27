#!/usr/bin/env python3
"""Draw Arabic labels correctly on PIL images.

Primary path: Pillow + RAQM (HarfBuzz / FriBidi) with the logical string
and direction='rtl'. That applies OpenType GSUB (lam-alef, joining).

Fallback when RAQM is missing: arabic-reshaper (MIT) plus python-bidi
(LGPL — imported as a package, not copied) to emit Presentation Forms,
then draw left-to-right. Join quality is weaker without GSUB.

Font: bundled Noto Naskh Arabic (SIL OFL 1.1) in fonts/.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, features

HERE = Path(__file__).resolve().parent

# Fallback search if the bundled font was deleted.
_FONT_CANDIDATES = [
    HERE / "fonts" / "NotoNaskhArabic-Regular.ttf",
    HERE / "fonts" / "NotoNaskhArabic-Bold.ttf",
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


def find_arabic_font() -> str:
    for p in _FONT_CANDIDATES:
        if p.is_file():
            return str(p)
    raise FileNotFoundError(
        "No Arabic font found. Keep fonts/NotoNaskhArabic-Regular.ttf next to "
        "this script, or install Noto Naskh Arabic."
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

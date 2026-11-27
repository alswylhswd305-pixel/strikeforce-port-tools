#!/usr/bin/env python3
"""Diagnose open Strikeforce graphics issues against an RPCS3 reference.

Clean-room measurements only (playbook: no guessed causes, no success rate).
Aligns a port screenshot to a reference (feature match + ECC), then scores:

  shadow_acne, dark_roofs, haze, faces, white_ground

Each finding is ours / ref / verdict, labelled a KNOWN measurement.
Arabic labels are drawn with arabic_draw.py (Noto Naskh Arabic, OFL).

    python diagnose.py compare ours.jpg ref.png --out outdir
    python diagnose.py batch --pairs pairs.json --out outdir
    python diagnose.py cutscene --ours frames_or_video --ref frames_or_video --out outdir

Also available as: python gfx_bisect.py diagnose|batch|cutscene ...
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arabic_draw as ad  # noqa: E402
import img_compare as ic  # noqa: E402

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

DEFAULT_SIZE = (1280, 720)
IM_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}

# Arabic + English names. Verdicts describe the NUMBER, never a cause.
ISSUE = {
    "shadow_acne":  {"ar": "حبوب الظل",       "en": "shadow acne"},
    "dark_roofs":   {"ar": "أسطح داكنة",      "en": "dark roofs"},
    "haze":         {"ar": "ضباب أو غشاوة",  "en": "haze/fog"},
    "faces":        {"ar": "الوجوه",           "en": "faces"},
    "face_dark":    {"ar": "وجه أسود",         "en": "dark/flat face"},
    "face_eyes":    {"ar": "عيون ناقصة",       "en": "missing eye detail"},
    "face_blue":    {"ar": "زرقة الوجه",       "en": "blue tint"},
    "white_ground": {"ar": "أرض بيضاء",        "en": "white ground"},
}

# Default measurement thresholds (documented; not "the bug is X").
THRESH = {
    "shadow_acne": 1.80,     # ours_hf / ref_hf
    "dark_roofs": 0.72,      # ours_luma / ref_luma  (below = darker)
    "haze": 0.35,            # abs log contrast-ratio of the far band
    "white_ground": 0.25,    # ours white_frac - ref white_frac
    "face_dark": 0.15,       # ours dark_hole - ref dark_hole
    "face_eyes": 0.55,       # ours eye_var / ref eye_var  (below = flatter)
    "face_blue": 0.06,       # ours (B-R) - ref (B-R) in 0..1
}


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _cv2():
    if cv2 is None:
        raise ImportError("pip install opencv-python-headless")
    return cv2


def to_rgb(im: Image.Image) -> Image.Image:
    return im.convert("RGB")


def load_image(path: str) -> Image.Image:
    """Open an image and honor EXIF orientation (phone photos are often tagged 6)."""
    im = Image.open(path)
    try:
        im = ImageOps.exif_transpose(im) or im
    except Exception:
        pass
    return to_rgb(im)


def pil_to_np(im: Image.Image) -> np.ndarray:
    return np.asarray(to_rgb(im), dtype=np.float32) / 255.0


def np_to_pil(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), "RGB")


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


# ---------------------------------------------------------------------------
# Auto-crop: window chrome, or a TV / phone photo of the screen
# ---------------------------------------------------------------------------

def crop_window_chrome(im: Image.Image) -> Tuple[Image.Image, Optional[Tuple[int, int, int, int]], str]:
    """Drop an obvious Windows title bar / taskbar. Conservative: no crop if unsure."""
    arr = np.asarray(to_rgb(im), dtype=np.float32) / 255.0
    h, w = arr.shape[:2]
    y_luma = luma(arr)
    # Per-row spatial energy (game content is busier than a title/taskbar).
    energy = np.abs(np.diff(y_luma, axis=1)).mean(axis=1)
    energy = energy / (float(np.median(energy)) + 1e-6)
    top = 0
    # Title bar: a low-energy strip at the top, 20–40 px, then a jump.
    max_top = min(48, h // 8)
    if max_top >= 16:
        for y in range(16, max_top + 1):
            if energy[:y].mean() < 0.55 and energy[y:min(h, y + 12)].mean() > 0.85:
                top = y
                break
    bottom = h
    max_bot = min(56, h // 7)
    if max_bot >= 24:
        for y in range(24, max_bot + 1):
            band = energy[h - y:]
            above = energy[max(0, h - y - 16):h - y]
            if band.mean() < 0.7 and above.mean() > 0.85:
                bottom = h - y
                break
    if top == 0 and bottom == h:
        return im, None, "no_chrome"
    if (bottom - top) < h * 0.7:
        return im, None, "no_chrome"
    box = (0, top, w, bottom)
    return im.crop(box), box, "chrome"


def _order_quad(pts: np.ndarray) -> np.ndarray:
    pts = np.array(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(4)
    tl, br = pts[np.argmin(s)], pts[np.argmax(s)]
    tr, bl = pts[np.argmin(d)], pts[np.argmax(d)]
    return np.stack([tl, tr, br, bl], axis=0)


def _quad_aspect_ok(pts: np.ndarray) -> Tuple[bool, float]:
    """Return (ok, long/short) for a 4-point quad. Game windows are ~16:9."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    # Use the two edge lengths from the ordered TL corner rather than the AABB,
    # which is misleading when the window is tilted in a portrait photo.
    d01 = float(np.linalg.norm(pts[1] - pts[0]))
    d03 = float(np.linalg.norm(pts[3] - pts[0]))
    long, short = max(d01, d03), min(d01, d03)
    if short < 8:
        return False, 0.0
    aspect = long / short
    return (1.20 <= aspect <= 2.40), aspect


def _score_screen_quad(gray: np.ndarray, pts: np.ndarray, area: float, img_area: float) -> float:
    cv = _cv2()
    ok, aspect = _quad_aspect_ok(pts)
    if not ok:
        return 0.0
    mask = np.zeros(gray.shape, np.uint8)
    cv.fillConvexPoly(mask, np.round(pts).astype(np.int32), 255)
    pix = gray[mask > 0]
    if pix.size == 0:
        return 0.0
    interior = float(pix.mean())
    # A full game window has both the bright ground and darker tents; a crop
    # of only the white ground has a low std and should score worse.
    std = float(pix.std())
    aspect_pref = 1.0 - min(abs(aspect - 16.0 / 9.0) / 0.55, 1.0)
    return aspect_pref * (0.25 + area / img_area) * (0.35 + interior / 255.0) * (0.35 + min(std, 80.0) / 80.0)


def _bright_minarea_quad(gray: np.ndarray, img_area: float) -> Optional[np.ndarray]:
    """Fallback when Canny + approxPolyDP never yields a clean 4-point quad.

    Phone photos of a TV rarely have perfectly straight edges. The game
    window is usually the largest bright region; its minAreaRect is a
    usable perspective quad (then chrome-crop the title/taskbar).
    """
    cv = _cv2()
    best, best_score = None, 0.0
    for t in (150, 160, 170, 180, 190, 200, 210):
        _, mask = cv.threshold(gray, t, 255, cv.THRESH_BINARY)
        mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
        mask = cv.morphologyEx(mask, cv.MORPH_OPEN, np.ones((5, 5), np.uint8))
        contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        c = max(contours, key=cv.contourArea)
        area = abs(cv.contourArea(c))
        if area < 0.10 * img_area or area > 0.80 * img_area:
            continue
        rect = cv.minAreaRect(c)
        (_cx, _cy), (rw, rh), _ang = rect
        if min(rw, rh) < 8:
            continue
        pts = _order_quad(cv.boxPoints(rect))
        score = _score_screen_quad(gray, pts, area, img_area)
        if score > best_score:
            best, best_score = pts, score
    return best


def crop_screen_quad(im: Image.Image, out_size: Tuple[int, int] = DEFAULT_SIZE
                     ) -> Tuple[Image.Image, Optional[np.ndarray], str]:
    """Perspective-crop a TV / phone photo onto a 16:9 game frame, if a quad is found."""
    cv = _cv2()
    rgb = np.asarray(to_rgb(im))
    h, w = rgb.shape[:2]
    # Only try this on large "photo of a room" images, not 1280x720 window grabs.
    # Portrait phone photos (EXIF-transposed) are taller than they are wide.
    if min(w, h) < 1000 or max(w, h) < 1600:
        return im, None, "not_a_photo"
    ar = w / float(h)
    if 1.9 < ar < 3.0 and h <= 1440:
        return im, None, "not_a_photo"
    scale = 1200.0 / max(w, h)
    small = cv.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv.INTER_AREA)
    gray = cv.cvtColor(small, cv.COLOR_RGB2GRAY)
    blur = cv.GaussianBlur(gray, (5, 5), 0)
    edges = cv.Canny(blur, 40, 120)
    edges = cv.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv.findContours(edges, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE)
    best, best_score = None, 0.0
    img_area = small.shape[0] * small.shape[1]
    method = "no_quad"
    for c in contours:
        peri = cv.arcLength(c, True)
        approx = cv.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) != 4 or not cv.isContourConvex(approx):
            continue
        area = abs(cv.contourArea(approx))
        if area < 0.12 * img_area or area > 0.95 * img_area:
            continue
        pts = _order_quad(approx)
        score = _score_screen_quad(gray, pts, area, img_area)
        if score > best_score:
            best, best_score, method = pts, score, "canny_quad"
    if best is None:
        best = _bright_minarea_quad(gray, img_area)
        if best is not None:
            method = "bright_rect"
    if best is None:
        return im, None, "no_quad"
    quad = best / scale
    dst = np.array([[0, 0], [out_size[0] - 1, 0],
                    [out_size[0] - 1, out_size[1] - 1], [0, out_size[1] - 1]], np.float32)
    M = cv.getPerspectiveTransform(quad.astype(np.float32), dst)
    warped = cv.warpPerspective(rgb, M, out_size, flags=cv.INTER_LINEAR)
    out = Image.fromarray(warped)
    # The TV often shows a desktop + a window. Try chrome crop on the result.
    out, _, why = crop_window_chrome(out)
    out = out.resize(out_size, Image.BILINEAR)
    return out, quad, "screen_quad+" + method + "+" + why


def prepare_image(im: Image.Image, size: Tuple[int, int], crop=None, photo: str = "auto"
                  ) -> Tuple[Image.Image, dict]:
    info = {"chrome": None, "screen_quad": None, "prep": []}
    if crop:
        im = im.crop(tuple(int(x) for x in crop))
        info["prep"].append("manual_crop")
    if photo == "auto":
        w, h = im.size
        ar = w / float(h) if h else 0.0
        # A raw 16:9 / 16:10 framebuffer (720p–4K) is not a photo of a room.
        looks_framebuffer = (
            (abs(ar - 16 / 9) < 0.08 or abs(ar - 16 / 10) < 0.08)
            and min(w, h) <= 2160 and max(w, h) <= 3840
        )
        if max(w, h) >= 1600 and min(w, h) >= 1000 and not looks_framebuffer:
            photo = "yes"
        else:
            photo = "no"
    if photo == "yes":
        im2, quad, why = crop_screen_quad(im, size)
        info["screen_quad"] = None if quad is None else quad.tolist()
        info["prep"].append(why)
        if why.startswith("screen_quad"):
            return im2, info
    im2, box, why = crop_window_chrome(im)
    info["chrome"] = box
    info["prep"].append(why)
    im2 = im2.resize(size, Image.BILINEAR)
    return im2, info


# ---------------------------------------------------------------------------
# Alignment: ORB / affine, then ECC. Reject wild warps.
# ---------------------------------------------------------------------------

def _warp_ok(M: np.ndarray, w: int, h: int, photo: bool = False) -> bool:
    """True if a 2x3 affine or 3x3 homography is a small correction, not a remix."""
    if M is None:
        return False
    if M.shape == (3, 3):
        A = M[:2, :]
    else:
        A = M
    sx = math.hypot(float(A[0, 0]), float(A[0, 1]))
    sy = math.hypot(float(A[1, 0]), float(A[1, 1]))
    lo, hi = (0.7, 1.4) if photo else (0.88, 1.14)
    if not (lo <= sx <= hi and lo <= sy <= hi):
        return False
    rot = abs(math.degrees(math.atan2(float(A[1, 0]), float(A[0, 0]))))
    if rot > (15 if photo else 6):
        return False
    tx, ty = abs(float(A[0, 2])), abs(float(A[1, 2]))
    if tx > 0.25 * w or ty > 0.25 * h:
        return False
    return True


def align_images(ours: Image.Image, ref: Image.Image, photo: bool = False) -> Tuple[Image.Image, dict]:
    """Warp `ours` into the reference's pixel frame. Both must already be the same size."""
    cv = _cv2()
    info = {"method": "resize_only", "inliers": 0, "ecc": None, "rejected": []}
    a = np.asarray(to_rgb(ours))
    b = np.asarray(to_rgb(ref))
    h, w = b.shape[:2]
    if a.shape[:2] != (h, w):
        a = cv.resize(a, (w, h), interpolation=cv.INTER_LINEAR)
    ga = cv.cvtColor(a, cv.COLOR_RGB2GRAY)
    gb = cv.cvtColor(b, cv.COLOR_RGB2GRAY)
    # 1) ORB + affine (same-size, so we expect near-identity).
    try:
        orb = cv.ORB_create(nfeatures=3000, scaleFactor=1.2, nlevels=8)
        k1, d1 = orb.detectAndCompute(ga, None)
        k2, d2 = orb.detectAndCompute(gb, None)
        if d1 is not None and d2 is not None and len(k1) >= 30 and len(k2) >= 30:
            bf = cv.BFMatcher(cv.NORM_HAMMING, crossCheck=False)
            raw = bf.knnMatch(d1, d2, k=2)
            good = [m for m, n in raw if m.distance < 0.75 * n.distance] if raw and len(raw[0]) == 2 else []
            if len(good) >= 12:
                p1 = np.float32([k1[m.queryIdx].pt for m in good])
                p2 = np.float32([k2[m.trainIdx].pt for m in good])
                M, mask = cv.estimateAffinePartial2D(p1, p2, method=cv.RANSAC, ransacReprojThreshold=3.0)
                inl = int(mask.sum()) if mask is not None else 0
                info["inliers"] = inl
                if M is not None and inl >= 10 and _warp_ok(M, w, h, photo):
                    a = cv.warpAffine(a, M, (w, h), flags=cv.INTER_LINEAR, borderMode=cv.BORDER_REPLICATE)
                    ga = cv.cvtColor(a, cv.COLOR_RGB2GRAY)
                    info["method"] = "orb_affine"
                else:
                    info["rejected"].append("orb_affine")
    except Exception as e:
        info["rejected"].append("orb:%s" % e.__class__.__name__)
    # 2) ECC affine refine (works well for a few pixels of leftover shift).
    try:
        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (cv.TERM_CRITERIA_EPS | cv.TERM_CRITERIA_COUNT, 80, 1e-5)
        cc, warp = cv.findTransformECC(
            gb.astype(np.float32) / 255.0,
            ga.astype(np.float32) / 255.0,
            warp, cv.MOTION_AFFINE, criteria, None, 5,
        )
        info["ecc"] = float(cc)
        if cc > 0.2 and _warp_ok(warp, w, h, photo=True):
            a = cv.warpAffine(a, warp, (w, h), flags=cv.INTER_LINEAR, borderMode=cv.BORDER_REPLICATE)
            info["method"] = info["method"] + "+ecc" if info["method"] != "resize_only" else "ecc"
        else:
            info["rejected"].append("ecc")
    except Exception as e:
        info["rejected"].append("ecc:%s" % e.__class__.__name__)
    return Image.fromarray(a), info


# ---------------------------------------------------------------------------
# Region / grid helpers
# ---------------------------------------------------------------------------

def frac_box(frac, w: int, h: int) -> Tuple[int, int, int, int]:
    x0, y0, x1, y1 = frac
    return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))


def clip_box(box, w, h):
    x0, y0, x1, y1 = [int(v) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def region(arr, box):
    x0, y0, x1, y1 = box
    return arr[y0:y1, x0:x1]


def tiles(h, w, gy=6, gx=8):
    out = []
    for iy in range(gy):
        for ix in range(gx):
            out.append((ix * w // gx, iy * h // gy, (ix + 1) * w // gx, (iy + 1) * h // gy))
    return out


# ---------------------------------------------------------------------------
# Detectors (KNOWN measurements)
# ---------------------------------------------------------------------------

def _hf_energy(gray: np.ndarray) -> float:
    """High-frequency energy: Laplacian variance + upper FFT ring. Scale-free-ish."""
    if gray.size < 16:
        return 0.0
    g = gray.astype(np.float32)
    g = g - g.mean()
    # Laplacian
    cv = _cv2()
    lap = cv.Laplacian(g, cv.CV_32F, ksize=3)
    lap_e = float(lap.var())
    # FFT high-band (skip DC and very low freqs)
    f = np.fft.rfft2(g)
    mag = np.abs(f)
    yy, xx = np.mgrid[0:mag.shape[0], 0:mag.shape[1]]
    cy, cx = mag.shape[0] / 2.0, 0  # rfft
    # radius in cycles; keep the upper half of frequencies
    ry = yy / max(mag.shape[0], 1)
    rx = xx / max(mag.shape[1], 1)
    r = np.sqrt(ry ** 2 + rx ** 2)
    mask = r > 0.25
    fft_e = float((mag[mask] ** 2).mean()) if mask.any() else 0.0
    return lap_e + 1e-6 * fft_e


def detect_shadow_acne(ours: np.ndarray, ref: np.ndarray) -> dict:
    """Striped / moiré energy on lit surfaces, ours vs ref."""
    h, w = ours.shape[:2]
    lo, ro = luma(ours), luma(ref)
    # Lit surfaces: mid luma in the reference, not the blown-out ground, not the sky.
    mid = (ro > 0.18) & (ro < 0.78)
    # Also drop a bottom band that is often ground.
    mid[int(h * 0.72):, :] = False
    # Tile scores.
    scored = []
    for box in tiles(h, w, 6, 8):
        m = region(mid, box)
        if m.mean() < 0.25:
            continue
        to, tr = region(lo, box).copy(), region(ro, box).copy()
        fill_o = float(to[m].mean()) if m.any() else 0.0
        fill_r = float(tr[m].mean()) if m.any() else 0.0
        to[~m] = fill_o
        tr[~m] = fill_r
        eo = _hf_energy(to)
        er = _hf_energy(tr)
        ratio = eo / max(er, 1e-6)
        scored.append((ratio, eo, er, box))
    scored.sort(key=lambda t: -t[0])
    if mid.mean() < 0.05:
        # Fallback: whole frame minus the ground band.
        box = (0, 0, w, int(h * 0.72))
        eo, er = _hf_energy(region(lo, box)), _hf_energy(region(ro, box))
        ratio = eo / max(er, 1e-6)
        boxes = [box] if ratio >= THRESH["shadow_acne"] else []
        return _finding("shadow_acne", eo, er, ratio, "ratio",
                        "higher" if ratio >= THRESH["shadow_acne"] else "similar",
                        [(b, "حبوب الظل") for b in boxes[:4]])
    eo = float(np.mean([t[1] for t in scored[:8]])) if scored else 0.0
    er = float(np.mean([t[2] for t in scored[:8]])) if scored else 0.0
    ratio = eo / max(er, 1e-6)
    boxes = [t[3] for t in scored if t[0] >= THRESH["shadow_acne"]][:5]
    if not boxes and scored and ratio >= THRESH["shadow_acne"]:
        boxes = [scored[0][3]]
    return _finding("shadow_acne", eo, er, ratio, "ratio",
                    "higher" if ratio >= THRESH["shadow_acne"] else "similar",
                    [(b, "حبوب الظل") for b in boxes])


def detect_dark_roofs(ours: np.ndarray, ref: np.ndarray, regions: Optional[dict] = None) -> dict:
    h, w = ours.shape[:2]
    lo, ro = luma(ours), luma(ref)
    specs = (regions or {}).get("dark_roofs") or [
        ("buildings_left", (0.00, 0.10, 0.32, 0.52)),
        ("buildings_right", (0.68, 0.08, 1.00, 0.55)),
        ("roof_band", (0.20, 0.08, 0.80, 0.36)),
    ]
    rows = []
    for name, fr in specs:
        if isinstance(fr, dict):
            fr = fr.get("frac") or fr.get("px")
        box = frac_box(fr, w, h) if max(fr) <= 1.5 else tuple(int(x) for x in fr)
        box = clip_box(box, w, h)
        if not box:
            continue
        o, r = float(region(lo, box).mean()), float(region(ro, box).mean())
        rows.append((name, box, o, r, o / max(r, 1e-6)))
    # Also hunt tiles in the upper 55% where the ref is a mid/dark structure
    # and ours is darker.
    extra = []
    for box in tiles(h, w, 6, 8):
        if box[1] > int(h * 0.55):
            continue
        o, r = float(region(lo, box).mean()), float(region(ro, box).mean())
        if r < 0.12 or r > 0.7:
            continue
        ratio = o / max(r, 1e-6)
        if ratio <= THRESH["dark_roofs"]:
            extra.append((ratio, box, o, r))
    extra.sort(key=lambda t: t[0])
    if rows:
        # Measurement = the darkest named region (min ours/ref). Other regions
        # stay in extra so a single bright wall cannot hide a dark roof.
        worst = min(rows, key=lambda t: t[4])
        o, r, ratio = worst[2], worst[3], worst[4]
    elif extra:
        o, r, ratio = extra[0][2], extra[0][3], extra[0][0]
    else:
        o = float(lo[: int(h * 0.5)].mean())
        r = float(ro[: int(h * 0.5)].mean())
        ratio = o / max(r, 1e-6)
    boxes = [(t[1], "أسطح داكنة") for t in rows if t[4] <= THRESH["dark_roofs"]]
    for ratio_t, box, _, _ in extra[:4]:
        if all(_iou(box, b[0]) < 0.4 for b in boxes):
            boxes.append((box, "أسطح داكنة"))
    key = "lower" if ratio <= THRESH["dark_roofs"] else "similar"
    f = _finding("dark_roofs", o, r, ratio, "ratio", key, boxes[:6])
    f["extra"] = {
        "regions": [{"name": n, "box": list(b), "ours": round(o_, 4), "ref": round(r_, 4),
                     "ratio": round(rat, 4)} for n, b, o_, r_, rat in rows],
    }
    return f


def detect_haze(ours: np.ndarray, ref: np.ndarray) -> dict:
    """Depth-ish contrast falloff and low-frequency veil, top (far) vs bottom (near)."""
    cv = _cv2()
    h, w = ours.shape[:2]
    lo, ro = luma(ours), luma(ref)
    # 5 horizontal bands, bottom = near, top = far (typical third-person view).
    n = 5
    contrast_o, contrast_r, veil_o, veil_r = [], [], [], []
    for i in range(n):
        y0, y1 = int(h * i / n), int(h * (i + 1) / n)
        band_o, band_r = lo[y0:y1], ro[y0:y1]
        # Local contrast: std after removing a heavy blur (the veil).
        def loc(band):
            blur = cv.GaussianBlur(band.astype(np.float32), (0, 0), sigmaX=max(8, band.shape[1] / 40.0))
            residual = band - blur
            return float(residual.std()), float(blur.mean())
        co, vo = loc(band_o)
        cr, vr = loc(band_r)
        contrast_o.append(co); contrast_r.append(cr)
        veil_o.append(vo); veil_r.append(vr)
    # Far = top two bands (0,1), near = bottom two (3,4).
    far_o, far_r = float(np.mean(contrast_o[:2])), float(np.mean(contrast_r[:2]))
    near_o, near_r = float(np.mean(contrast_o[3:])), float(np.mean(contrast_r[3:]))
    # Contrast ratio far/near, ours vs ref. Missing haze → ours keeps too much far contrast.
    fall_o = far_o / max(near_o, 1e-6)
    fall_r = far_r / max(near_r, 1e-6)
    # Log ratio of far contrast (ours/ref). >0 = sharper far (missing veil); <0 = softer far (excess veil).
    log_ratio = math.log(max(far_o, 1e-6) / max(far_r, 1e-6))
    veil_delta = float(np.mean(veil_o[:2]) - np.mean(veil_r[:2]))
    boxes = []
    if abs(log_ratio) >= THRESH["haze"]:
        boxes.append(((0, 0, w, int(h * 2 / n)), "ضباب أو غشاوة"))
    if abs(log_ratio) >= THRESH["haze"]:
        key = "higher" if log_ratio > 0 else "lower"
    else:
        key = "similar"
    f = _finding("haze", far_o, far_r, math.exp(log_ratio), "ratio", key, boxes)
    f["extra"] = {
        "far_contrast_ours": round(far_o, 4), "far_contrast_ref": round(far_r, 4),
        "near_contrast_ours": round(near_o, 4), "near_contrast_ref": round(near_r, 4),
        "falloff_ours": round(fall_o, 4), "falloff_ref": round(fall_r, 4),
        "log_far_contrast_ratio": round(log_ratio, 4),
        "far_veil_delta": round(veil_delta, 4),
        "band_contrast_ours": [round(x, 4) for x in contrast_o],
        "band_contrast_ref": [round(x, 4) for x in contrast_r],
    }
    return f


def detect_white_ground(ours: np.ndarray, ref: np.ndarray, regions: Optional[dict] = None) -> dict:
    h, w = ours.shape[:2]
    fr = ((regions or {}).get("white_ground") or (regions or {}).get("ground")
          or (0.0, 0.58, 1.0, 0.95))
    if isinstance(fr, dict):
        fr = fr.get("frac") or fr.get("px")
    box = frac_box(fr, w, h) if max(fr) <= 1.5 else tuple(int(x) for x in fr)
    box = clip_box(box, w, h) or (0, int(h * 0.58), w, int(h * 0.95))
    lo, ro = luma(ours), luma(ref)
    o = float((region(lo, box) >= 0.85).mean())
    r = float((region(ro, box) >= 0.85).mean())
    delta = o - r
    key = "higher" if delta >= THRESH["white_ground"] else "similar"
    boxes = [(box, "أرض بيضاء")] if key == "higher" else []
    return _finding("white_ground", o, r, delta, "delta", key, boxes)


# --- faces ------------------------------------------------------------------

# Game-skin in YCrCb / HSV. Broad on purpose; size/aspect filters do the rest.
def _skin_mask(rgb: np.ndarray) -> np.ndarray:
    cv = _cv2()
    u8 = np.clip(rgb * 255.0, 0, 255).astype(np.uint8)
    ycr = cv.cvtColor(u8, cv.COLOR_RGB2YCrCb)
    hsv = cv.cvtColor(u8, cv.COLOR_RGB2HSV)
    y, cr, cb = ycr[..., 0], ycr[..., 1], ycr[..., 2]
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m1 = (cr >= 133) & (cr <= 185) & (cb >= 77) & (cb <= 135) & (y >= 40)
    m2 = ((h <= 25) | (h >= 170)) & (s >= 20) & (s <= 200) & (v >= 40) & (v <= 245)
    mask = (m1 | m2).astype(np.uint8) * 255
    mask = cv.medianBlur(mask, 5)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mask


def _face_boxes_from_mask(mask: np.ndarray, max_n: int = 6) -> List[Tuple[int, int, int, int]]:
    cv = _cv2()
    h, w = mask.shape
    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    boxes = []
    img_a = h * w
    for c in contours:
        x, y, bw, bh = cv.boundingRect(c)
        a = bw * bh
        if a < 0.0015 * img_a or a > 0.18 * img_a:
            continue
        aspect = bw / max(bh, 1)
        if not (0.45 <= aspect <= 1.85):
            continue
        # Prefer mid-frame (characters), skip a thin HUD strip at the top.
        if y < 0.04 * h and bh < 0.12 * h:
            continue
        boxes.append((x, y, x + bw, y + bh, a))
    boxes.sort(key=lambda t: -t[4])
    # Grow a little so eyes/chin stay inside.
    out = []
    for x0, y0, x1, y1, _ in boxes[:max_n]:
        padx, pady = int(0.12 * (x1 - x0)), int(0.18 * (y1 - y0))
        out.append((max(0, x0 - padx), max(0, y0 - pady), min(w, x1 + padx), min(h, y1 + pady)))
    return out


def _face_metrics(rgb: np.ndarray, box) -> dict:
    patch = region(rgb, box)
    if patch.size == 0:
        return {"dark_hole": 0.0, "eye_var": 0.0, "blue": 0.0, "luma": 0.0}
    g = luma(patch)
    dark = float((g < 0.12).mean())
    # Eyes: upper 35% of the box.
    eye = g[: max(1, int(g.shape[0] * 0.35))]
    eye_var = float(eye.var())
    # Blue shift: mean (B - R) in 0..1. More positive = bluer.
    blue = float((patch[..., 2] - patch[..., 0]).mean())
    return {"dark_hole": dark, "eye_var": eye_var, "blue": blue, "luma": float(g.mean())}


def alignment_reliable(alin: dict) -> bool:
    """True only when a warp actually mapped ours onto the reference.

    resize_only (or a weak ECC) means a ref face box is not the same
    place on ours — do not project those boxes or treat the numbers as a hit.
    ECC alone can return cc around 0.25 on unrelated frames with a
    near-identity warp, so a modest ECC without ORB inliers is not enough.
    """
    method = (alin or {}).get("method") or "resize_only"
    ecc = (alin or {}).get("ecc")
    inl = int((alin or {}).get("inliers") or 0)
    if method == "resize_only":
        return False
    if "orb" in method and inl >= 40:
        if ecc is None or "ecc" not in method:
            return True
        return float(ecc) >= 0.22
    # ECC-only: demand a clearly high correlation.
    if "ecc" in method and ecc is not None and float(ecc) >= 0.50:
        return True
    return False


def detect_faces(ours: np.ndarray, ref: np.ndarray, face_boxes: Optional[list] = None,
                 alignment_ok: bool = True) -> dict:
    h, w = ours.shape[:2]
    boxes_cfg: List[Tuple[int, int, int, int]] = []
    source = "none"
    if face_boxes:
        for b in face_boxes:
            if isinstance(b, dict):
                b = b.get("frac") or b.get("px") or b.get("box")
            box = frac_box(b, w, h) if max(b) <= 1.5 else tuple(int(x) for x in b)
            box = clip_box(box, w, h)
            if box:
                boxes_cfg.append(box)
        source = "config"
    boxes_ref_auto = _face_boxes_from_mask(_skin_mask(ref))
    boxes_ours = _face_boxes_from_mask(_skin_mask(ours))
    unmatched = False
    if alignment_ok:
        boxes_ref = boxes_cfg or boxes_ref_auto
        if boxes_cfg:
            source = "config"
        elif boxes_ref_auto:
            source = "auto_ref"
        else:
            source = "none"
        if not boxes_ref and boxes_ours:
            boxes_ref = boxes_ours
            unmatched = True
            source = "auto_ours_only"
    else:
        # Weak alignment: measure each side on its own skin blobs. Never
        # project a ref/config box onto ours — that box is a different place.
        unmatched = True
        boxes_ref = boxes_ours
        source = "auto_ours_unaligned"
        if not boxes_ref and boxes_cfg:
            # Still record that a config box was ignored.
            source = "config_ignored_unaligned"
    if not boxes_ref:
        f = _finding("faces", 0.0, 0.0, 0.0, "delta", "no_region", [])
        f["extra"] = {"box_source": source, "n_faces": 0}
        f["scores"] = {"faces": 0.0, "face_dark": 0.0, "face_eyes": 1.0, "face_blue": 0.0}
        return f
    if unmatched:
        # Independent metrics: ours on ours blobs, ref on ref blobs (if any).
        mo = [_face_metrics(ours, b) for b in boxes_ours] if boxes_ours else []
        mr = [_face_metrics(ref, b) for b in boxes_ref_auto] if boxes_ref_auto else []
        labels_boxes = [(b, "وجه (قياس بلا تطابق)") for b in boxes_ours]
        draw_boxes = boxes_ours
    else:
        mo = [_face_metrics(ours, b) for b in boxes_ref]
        mr = [_face_metrics(ref, b) for b in boxes_ref]
        draw_boxes = boxes_ref
        labels_boxes = []
        for i, box in enumerate(boxes_ref):
            tags = []
            if mo[i]["dark_hole"] - mr[i]["dark_hole"] >= THRESH["face_dark"]:
                tags.append("وجه أسود")
            if (mo[i]["eye_var"] / max(mr[i]["eye_var"], 1e-6)) <= THRESH["face_eyes"]:
                tags.append("عيون ناقصة")
            if mo[i]["blue"] - mr[i]["blue"] >= THRESH["face_blue"]:
                tags.append("زرقة الوجه")
            if tags:
                labels_boxes.append((box, "، ".join(tags)))
    def _avg(rows, key, default=0.0):
        return float(np.mean([m[key] for m in rows])) if rows else default
    dark_o, dark_r = _avg(mo, "dark_hole"), _avg(mr, "dark_hole")
    eye_o, eye_r = _avg(mo, "eye_var"), _avg(mr, "eye_var")
    blue_o, blue_r = _avg(mo, "blue"), _avg(mr, "blue")
    dark_d = dark_o - dark_r
    eye_ratio = eye_o / max(eye_r, 1e-6) if mr else 1.0
    blue_d = blue_o - blue_r
    # Combined score for bisect: emphasize a black face, then missing eyes, then blue.
    # When unmatched, keep the score at 0 so a bisect does not treat a
    # different camera as a "face hit".
    if unmatched:
        combined = 0.0
        key = "unmatched"
    else:
        combined = max(0.0, dark_d) + max(0.0, (1.0 - min(eye_ratio, 1.0))) + max(0.0, blue_d)
        hit = (dark_d >= THRESH["face_dark"] or eye_ratio <= THRESH["face_eyes"]
               or blue_d >= THRESH["face_blue"])
        key = "higher" if hit else "similar"
    f = _finding("faces", dark_o, dark_r, dark_d, "delta", key, labels_boxes)
    per_face = []
    if unmatched:
        for i, b in enumerate(boxes_ours):
            per_face.append({"box": list(b), "side": "ours",
                             "ours": {k: round(v, 4) for k, v in mo[i].items()}})
        for i, b in enumerate(boxes_ref_auto):
            per_face.append({"box": list(b), "side": "ref",
                             "ref": {k: round(v, 4) for k, v in mr[i].items()}})
    else:
        for i in range(len(boxes_ref)):
            per_face.append({
                "box": list(boxes_ref[i]),
                "ours": {k: round(v, 4) for k, v in mo[i].items()},
                "ref": {k: round(v, 4) for k, v in mr[i].items()},
            })
    f["extra"] = {
        "box_source": source,
        "n_faces": len(draw_boxes),
        "n_faces_ours": len(boxes_ours),
        "n_faces_ref": len(boxes_ref_auto),
        "unmatched_pose": unmatched,
        "alignment_ok": bool(alignment_ok),
        "dark_hole_ours": round(dark_o, 4), "dark_hole_ref": round(dark_r, 4),
        "eye_var_ours": round(eye_o, 6), "eye_var_ref": round(eye_r, 6),
        "eye_var_ratio": round(eye_ratio, 4),
        "blue_minus_red_ours": round(blue_o, 4), "blue_minus_red_ref": round(blue_r, 4),
        "per_face": per_face,
    }
    if unmatched:
        # Raw measurements stay in extra / ours / ref; the bisect score stays
        # at zero so a different camera is not treated as a face hit.
        f["scores"] = {"faces": 0.0, "face_dark": 0.0, "face_eyes": 0.0, "face_blue": 0.0}
    else:
        f["scores"] = {
            "faces": combined,
            "face_dark": max(0.0, dark_d),
            "face_eyes": max(0.0, 1.0 - min(eye_ratio, 1.0)),
            "face_blue": max(0.0, blue_d),
        }
    return f


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    ua = max(0, ax1 - ax0) * max(0, ay1 - ay0) + max(0, bx1 - bx0) * max(0, by1 - by0) - inter
    return inter / ua if ua else 0.0


def _finding(issue: str, ours: float, refv: float, cmp: float, cmp_kind: str,
             key: str, boxes: list) -> dict:
    names = ISSUE[issue]
    if key == "higher":
        verd_ar, verd_en = "أعلى من المرجع", "higher than the reference"
    elif key == "lower":
        verd_ar, verd_en = "أقل من المرجع", "lower than the reference"
    elif key == "no_region":
        verd_ar, verd_en = "لا منطقة للقياس", "no region to measure"
    elif key == "unmatched":
        verd_ar, verd_en = "قياس بلا تطابق للكاميرا", "measured, unmatched pose/camera"
    else:
        verd_ar, verd_en = "قريب من المرجع", "close to the reference"
    return {
        "issue": issue,
        "label_ar": names["ar"],
        "label_en": names["en"],
        "ours": round(float(ours), 4),
        "ref": round(float(refv), 4),
        "compare": round(float(cmp), 4),
        "compare_kind": cmp_kind,   # "ratio" or "delta"
        "verdict_key": key,
        "verdict_ar": verd_ar,
        "verdict_en": verd_en,
        "kind": "KNOWN measurement",
        "boxes": [{"box": list(b), "label_ar": lab} for b, lab in boxes],
        "threshold": THRESH.get(issue),
        "extra": {},
        "scores": {},
    }


# ---------------------------------------------------------------------------
# Scoring for gfx_bisect (higher => more artefact)
# ---------------------------------------------------------------------------

def scores_from_findings(findings: List[dict]) -> Dict[str, float]:
    out = {}
    for f in findings:
        issue = f["issue"]
        if f.get("scores"):
            out.update(f["scores"])
        if issue == "shadow_acne":
            out[issue] = max(0.0, f["compare"] - 1.0)
        elif issue == "dark_roofs":
            out[issue] = max(0.0, 1.0 - f["compare"])
        elif issue == "haze":
            out[issue] = abs(math.log(max(f["compare"], 1e-6)))
        elif issue == "white_ground":
            out[issue] = max(0.0, f["compare"])
        elif issue == "faces" and "faces" not in out:
            out[issue] = max(0.0, f["compare"])
    return out


def artifact_from_score(scores: dict, metric: str, threshold: float, rule: str = "above") -> Tuple[bool, float]:
    aliases = {"haze_fog": "haze", "fog": "haze", "dark_buildings": "dark_roofs"}
    metric = aliases.get(metric, metric)
    if metric not in scores:
        raise KeyError("unknown detector metric %r (have %s)" % (metric, sorted(scores)))
    v = float(scores[metric])
    if rule in ("below", "close_to_bad", "under"):
        return v < threshold, v
    return v > threshold, v


# ---------------------------------------------------------------------------
# Annotation + side-by-side
# ---------------------------------------------------------------------------

def _worst_mae_boxes(ours: np.ndarray, ref: np.ndarray, n=4) -> list:
    h, w = ours.shape[:2]
    err = np.abs(ours - ref).mean(axis=2)
    scored = []
    for box in tiles(h, w, 6, 8):
        e = float(region(err, box).mean())
        scored.append((e, box))
    scored.sort(key=lambda t: -t[0])
    # skip almost-empty differences
    return [b for e, b in scored if e >= 0.12][:n]


def annotate_pair(ours: Image.Image, ref: Image.Image, findings: List[dict],
                  out_dir: str, title: str = "") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    A, B = pil_to_np(ours), pil_to_np(ref)
    err = np.abs(A - B).mean(axis=2)
    heat = ic._to_img(ic._heatmap(np.clip(err * 2.0, 0.0, 1.0)))
    # Collect boxes (detector + worst MAE tiles that are not already covered).
    boxes = []
    for f in findings:
        for b in f.get("boxes") or []:
            boxes.append((tuple(b["box"]), b["label_ar"], f["issue"]))
    for box in _worst_mae_boxes(A, B):
        if all(_iou(box, b[0]) < 0.45 for b in boxes):
            boxes.append((box, "أكبر اختلاف", "mae"))
    ann = ours.copy()
    draw = ImageDraw.Draw(ann)
    for box, label, issue in boxes:
        x0, y0, x1, y1 = box
        draw.rectangle([x0, y0, max(x0 + 1, x1 - 1), max(y0 + 1, y1 - 1)],
                       outline=(220, 0, 0), width=3)
        ad.draw_label(ann, (x0, y0), label, size=20, fill=(255, 255, 255),
                      bg=(180, 0, 0), anchor="lt")
    # Caption strip at the bottom with a short bilingual summary of hits.
    hits = [f for f in findings if f["verdict_key"] in ("higher", "lower", "unmatched") and f.get("boxes")]
    if not hits:
        hits = [f for f in findings if f["verdict_key"] in ("higher", "lower")]
    # Isolate Latin/numeric runs so RTL does not visually swap ours/ref.
    _LRI, _PDI = "⁦", "⁩"
    caption = "  |  ".join(
        "%s %s  %s  %s" % (
            f["label_ar"], f["verdict_ar"],
            _LRI + "%s / %s" % (f["ours"], f["ref"]) + _PDI,
            _LRI + "(%s)" % f["label_en"] + _PDI,
        )
        for f in hits[:5]
    ) or "لا اختلاف فوق العتبة  |  no finding above threshold"
    strip_h = 48
    canvas = Image.new("RGB", (ann.width, ann.height + strip_h), (20, 20, 20))
    canvas.paste(ann, (0, 0))
    ad.draw_label(canvas, (8, ann.height + 6), caption, size=18,
                  fill=(255, 255, 255), bg=(20, 20, 20), anchor="lt",
                  max_width=canvas.width - 16)
    ann_path = os.path.join(out_dir, "annotated.png")
    canvas.save(ann_path)
    # Side-by-side: ours | ref | heatmap  (all same height)
    def _fit(im):
        return im.resize((ours.width, ours.height), Image.BILINEAR) if im.size != ours.size else im
    sbs = Image.new("RGB", (ours.width * 3, ours.height + 28), (10, 10, 10))
    sbs.paste(_fit(ours), (0, 28))
    sbs.paste(_fit(ref), (ours.width, 28))
    sbs.paste(_fit(heat), (ours.width * 2, 28))
    for i, lab in enumerate(("الميناء  ours", "المرجع  RPCS3", "خريطة الاختلاف  diff")):
        ad.draw_label(sbs, (i * ours.width + 8, 2), lab, size=16,
                      fill=(255, 255, 255), bg=(10, 10, 10))
    sbs_path = os.path.join(out_dir, "side_by_side.png")
    sbs.save(sbs_path)
    heat_path = os.path.join(out_dir, "heatmap.png")
    heat.save(heat_path)
    return {"annotated": ann_path, "side_by_side": sbs_path, "heatmap": heat_path}


# ---------------------------------------------------------------------------
# One pair
# ---------------------------------------------------------------------------

def compare_pair(ours_path: str, ref_path: str, out_dir: str,
                 size: Tuple[int, int] = DEFAULT_SIZE,
                 crop_ours=None, crop_ref=None, face_boxes=None,
                 regions: Optional[dict] = None, photo: str = "auto",
                 name: str = "") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    ours_im, ours_prep = prepare_image(load_image(ours_path), size, crop=crop_ours, photo=photo)
    ref_im, ref_prep = prepare_image(load_image(ref_path), size, crop=crop_ref, photo="no")
    photo_flag = "screen_quad" in "".join(ours_prep.get("prep") or [])
    aligned, alin = align_images(ours_im, ref_im, photo=photo_flag)
    A, B = pil_to_np(aligned), pil_to_np(ref_im)
    findings = [
        detect_shadow_acne(A, B),
        detect_dark_roofs(A, B, regions),
        detect_haze(A, B),
        detect_faces(A, B, face_boxes, alignment_ok=alignment_reliable(alin)),
        detect_white_ground(A, B, regions),
    ]
    paths = annotate_pair(aligned, ref_im, findings, out_dir, title=name)
    scores = scores_from_findings(findings)
    err = np.abs(A - B).mean()
    result = {
        "name": name or Path(ours_path).stem,
        "ours": ours_path, "ref": ref_path,
        "size": list(size),
        "alignment": alin,
        "prep_ours": ours_prep, "prep_ref": ref_prep,
        "global_mae": round(float(err), 4),
        "findings": findings,
        "scores": {k: round(float(v), 4) for k, v in scores.items()},
        "paths": paths,
        "kind": "KNOWN measurement",
    }
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)
    return result


# ---------------------------------------------------------------------------
# Batch report
# ---------------------------------------------------------------------------

def load_pairs(spec: str) -> List[dict]:
    p = Path(spec)
    if p.is_file() and p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "pairs" in data:
            return data["pairs"]
        if isinstance(data, list):
            return data
        raise ValueError("pairs JSON must be a list or {pairs: [...]}")
    if p.is_dir():
        # name.ours.png + name.ref.png, or ours/ + ref/ with the same filename.
        pairs = []
        ours_dir, ref_dir = p / "ours", p / "ref"
        if ours_dir.is_dir() and ref_dir.is_dir():
            for f in sorted(ours_dir.iterdir()):
                r = ref_dir / f.name
                if r.is_file():
                    pairs.append({"name": f.stem, "ours": str(f), "ref": str(r)})
            return pairs
        by = {}
        for f in p.iterdir():
            name = f.name.lower()
            if f.suffix.lower() not in IM_EXTS:
                continue
            if ".ours." in name or name.endswith("_ours" + f.suffix.lower()):
                key = name.replace(".ours.", ".").replace("_ours" + f.suffix.lower(), "")
                by.setdefault(key, {})["ours"] = str(f)
            elif ".ref." in name or name.endswith("_ref" + f.suffix.lower()):
                key = name.replace(".ref.", ".").replace("_ref" + f.suffix.lower(), "")
                by.setdefault(key, {})["ref"] = str(f)
        for k, v in sorted(by.items()):
            if "ours" in v and "ref" in v:
                pairs.append({"name": Path(k).stem, **v})
        return pairs
    raise FileNotFoundError(spec)


def write_reports(results: List[dict], out_dir: str, title: str = "تشخيص الرسم  |  graphics diagnosis") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    md = []
    md.append("# %s" % title)
    md.append("")
    md.append("كل رقم هنا **قياس معروف** (KNOWN measurement) مقابل لقطة مرجع RPCS3 بعد المحاذاة. "
              "ليس سبباً متوقعاً، وليست نسبة نجاح.")
    md.append("")
    md.append("Every figure is a **KNOWN measurement** against an aligned RPCS3 reference. "
              "Not a guessed cause, and not a success rate.")
    md.append("")
    for r in results:
        md.append("## %s" % r["name"])
        md.append("")
        md.append("- ours: `%s`" % r["ours"])
        md.append("- ref: `%s`" % r["ref"])
        md.append("- alignment: `%s` (ORB inliers %s, ECC %s)" % (
            r["alignment"].get("method"), r["alignment"].get("inliers"), r["alignment"].get("ecc")))
        md.append("- prep ours: `%s`" % ",".join((r.get("prep_ours") or {}).get("prep") or []))
        md.append("- global MAE: **%s**" % r.get("global_mae"))
        if not alignment_reliable(r.get("alignment") or {}):
            md.append("")
            md.append("> محاذاة ضعيفة — قياسات الوجه والأسطح قد لا تطابق نفس المنطقة. "
                      "Weak alignment: face/roof numbers are not same-place comparisons.")
        md.append("")
        md.append("| القضية / issue | قياسنا / ours | المرجع / ref | مقارنة / compare | الحكم / verdict |")
        md.append("|---|---:|---:|---:|---|")
        for f in r["findings"]:
            cmp = f["compare"]
            kind = "×" if f["compare_kind"] == "ratio" else "Δ"
            md.append("| %s<br>%s | %s | %s | %s %s | %s — %s |" % (
                f["label_ar"], f["label_en"], f["ours"], f["ref"], kind, cmp,
                f["verdict_ar"], f["verdict_en"]))
            if f.get("extra") and f["issue"] in ("faces", "haze"):
                # short extras
                ex = f["extra"]
                if f["issue"] == "faces" and ex:
                    md.append("")
                    md.append("وجه: dark-hole %s / %s، تباين العين %s / %s، أزرق−أحمر %s / %s. المصدر: `%s`."
                              % (ex.get("dark_hole_ours"), ex.get("dark_hole_ref"),
                                 ex.get("eye_var_ours"), ex.get("eye_var_ref"),
                                 ex.get("blue_minus_red_ours"), ex.get("blue_minus_red_ref"),
                                 ex.get("box_source")))
                if f["issue"] == "haze" and ex:
                    md.append("")
                    md.append("تباين البعيد/القريب: ours falloff %s، ref falloff %s، log far-contrast %s."
                              % (ex.get("falloff_ours"), ex.get("falloff_ref"), ex.get("log_far_contrast_ratio")))
        md.append("")
        paths = r.get("paths") or {}
        if paths.get("annotated"):
            rel = os.path.relpath(paths["annotated"], out_dir)
            md.append("![annotated](%s)" % rel.replace("\\", "/"))
            md.append("")
        if paths.get("side_by_side"):
            rel = os.path.relpath(paths["side_by_side"], out_dir)
            md.append("![side by side](%s)" % rel.replace("\\", "/"))
            md.append("")
    md_path = os.path.join(out_dir, "report.md")
    Path(md_path).write_text("\n".join(md) + "\n", encoding="utf-8")

    # HTML
    html = []
    html.append("<!DOCTYPE html><html lang='ar'><head><meta charset='utf-8'>")
    html.append("<title>%s</title>" % title)
    html.append("<style>")
    html.append("body{font-family:Calibri,'Noto Naskh Arabic',Arial,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;background:#111;color:#eee;}")
    html.append("h1,h2{color:#fff} table{border-collapse:collapse;width:100%;margin:12px 0}")
    html.append("th,td{border:1px solid #444;padding:6px 8px;vertical-align:top}")
    html.append("th{background:#222} .hit{background:#3a1515} .ok{background:#152015} .warn{background:#3a3010}")
    html.append("img{max-width:100%;height:auto;border:1px solid #333;margin:8px 0}")
    html.append(".meta{color:#aaa;font-size:0.95em} .note{color:#ccc}")
    html.append("</style></head><body>")
    html.append("<h1>%s</h1>" % title)
    html.append("<p class='note'>كل رقم <strong>قياس معروف</strong> (KNOWN measurement) مقابل مرجع RPCS3 بعد المحاذاة. "
                "ليس سبباً متوقعاً، وليست نسبة نجاح.</p>")
    for r in results:
        html.append("<h2>%s</h2>" % r["name"])
        prep = ",".join((r.get("prep_ours") or {}).get("prep") or [])
        html.append("<p class='meta'>alignment: %s · MAE %s · prep: %s<br>ours: %s<br>ref: %s</p>" % (
            r["alignment"].get("method"), r.get("global_mae"), prep, r["ours"], r["ref"]))
        if not alignment_reliable(r.get("alignment") or {}):
            html.append("<p class='note'>محاذاة ضعيفة — قياسات الوجه والأسطح قد لا تطابق نفس المنطقة. "
                        "Weak alignment: face/roof numbers are not same-place comparisons.</p>")
        html.append("<table><tr><th>القضية / issue</th><th>ours</th><th>ref</th><th>compare</th><th>الحكم / verdict</th></tr>")
        for f in r["findings"]:
            cls = "hit" if f["verdict_key"] in ("higher", "lower") else (
                "warn" if f["verdict_key"] == "unmatched" else "ok")
            html.append("<tr class='%s'><td>%s<br><span class='meta'>%s</span></td><td>%s</td><td>%s</td><td>%s %s</td><td>%s<br>%s</td></tr>" % (
                cls, f["label_ar"], f["label_en"], f["ours"], f["ref"],
                "×" if f["compare_kind"] == "ratio" else "Δ", f["compare"],
                f["verdict_ar"], f["verdict_en"]))
        html.append("</table>")
        paths = r.get("paths") or {}
        for key in ("annotated", "side_by_side"):
            if paths.get(key):
                rel = os.path.relpath(paths[key], out_dir).replace("\\", "/")
                html.append("<p><img src='%s' alt='%s'></p>" % (rel, key))
    html.append("</body></html>")
    html_path = os.path.join(out_dir, "report.html")
    Path(html_path).write_text("\n".join(html), encoding="utf-8")
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    return {"markdown": md_path, "html": html_path}


def run_batch(pairs_spec: str, out_dir: str, size=DEFAULT_SIZE) -> dict:
    pairs = load_pairs(pairs_spec)
    if not pairs:
        raise SystemExit("no pairs in %s" % pairs_spec)
    results = []
    for i, p in enumerate(pairs):
        name = p.get("name") or Path(p["ours"]).stem
        dest = os.path.join(out_dir, "pairs", "%02d_%s" % (i + 1, _safe(name)))
        print("[diagnose] %s" % name, flush=True)
        results.append(compare_pair(
            p["ours"], p["ref"], dest, size=size,
            crop_ours=p.get("crop_ours"), crop_ref=p.get("crop_ref"),
            face_boxes=p.get("face_boxes"), regions=p.get("regions"),
            photo=p.get("photo", "auto"), name=name,
        ))
    paths = write_reports(results, out_dir)
    print("[diagnose] wrote %s and %s" % (paths["markdown"], paths["html"]), flush=True)
    return {"results": results, **paths}


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)[:80]


# ---------------------------------------------------------------------------
# Cutscene / frame-sequence mode
# ---------------------------------------------------------------------------

def iter_frames(source: str):
    """Yield (index, name, PIL.Image) from a folder or a video file."""
    p = Path(source)
    if p.is_dir():
        files = sorted(f for f in p.iterdir() if f.suffix.lower() in IM_EXTS)
        for i, f in enumerate(files):
            yield i, f.name, load_image(str(f))
        return
    cv = _cv2()
    cap = cv.VideoCapture(str(p))
    if not cap.isOpened():
        raise FileNotFoundError("cannot open video or folder: %s" % source)
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        yield i, "f%06d" % i, Image.fromarray(cv.cvtColor(fr, cv.COLOR_BGR2RGB))
        i += 1
    cap.release()


def _signature(im: Image.Image, size=32) -> np.ndarray:
    small = np.asarray(to_rgb(im).resize((size, size), Image.BILINEAR), dtype=np.float32) / 255.0
    g = luma(small).reshape(-1)
    hist, _ = np.histogram(g, bins=16, range=(0, 1), density=True)
    return np.concatenate([g, hist.astype(np.float32)])


def _cut_indices(sigs: List[np.ndarray], thresh: float = 0.18) -> List[int]:
    cuts = [0]
    for i in range(1, len(sigs)):
        # signature distance (luma thumb + hist)
        d = float(np.mean(np.abs(sigs[i] - sigs[i - 1])))
        if d >= thresh:
            cuts.append(i)
    return cuts


def sync_sequences(ours_sigs: List[np.ndarray], ref_sigs: List[np.ndarray],
                   window: int = 12) -> List[int]:
    """Greedy monotonic match: for each ours index, pick a nearby ref frame."""
    matches = []
    last = 0
    no, nr = len(ours_sigs), len(ref_sigs)
    # Scale the expected ref index if lengths differ.
    scale = (nr - 1) / max(no - 1, 1)
    for i, s in enumerate(ours_sigs):
        expect = int(round(i * scale))
        lo = max(last, expect - window, 0)
        hi = min(nr, max(lo + 1, expect + window + 1))
        best, bj = 1e9, lo
        for j in range(lo, hi):
            d = float(np.mean(np.abs(s - ref_sigs[j])))
            if d < best:
                best, bj = d, j
        matches.append(bj)
        last = bj
    return matches


def run_cutscene(ours_src: str, ref_src: str, out_dir: str,
                 size=DEFAULT_SIZE, every: int = 1, max_frames: int = 0) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    ours_frames = list(iter_frames(ours_src))
    ref_frames = list(iter_frames(ref_src))
    if max_frames:
        ours_frames = ours_frames[:max_frames]
        ref_frames = ref_frames[:max_frames]
    if every > 1:
        ours_frames = ours_frames[::every]
    if not ours_frames or not ref_frames:
        raise SystemExit("cutscene needs frames on both sides")
    # Signatures at a common thumbnail size (no full align yet).
    o_sigs = [_signature(im) for _, _, im in ours_frames]
    r_sigs = [_signature(im) for _, _, im in ref_frames]
    cuts_o = _cut_indices(o_sigs)
    cuts_r = _cut_indices(r_sigs)
    matches = sync_sequences(o_sigs, r_sigs)
    # Choose frames to fully diagnose: each ours cut and the midpoint of each shot, plus first/last.
    pick = set(cuts_o) | {0, len(ours_frames) - 1}
    for a, b in zip(cuts_o, cuts_o[1:] + [len(ours_frames)]):
        pick.add((a + b) // 2)
    pick = sorted(i for i in pick if 0 <= i < len(ours_frames))

    rows = []
    worst = []  # (combined_score, result, ours_idx)
    tmp_ours = Path(out_dir) / "_tmp_ours"
    tmp_ref = Path(out_dir) / "_tmp_ref"
    tmp_ours.mkdir(exist_ok=True)
    tmp_ref.mkdir(exist_ok=True)
    for i, (idx, name, im) in enumerate(ours_frames):
        j = matches[i]
        ridx, rname, rim = ref_frames[j]
        dist = float(np.mean(np.abs(o_sigs[i] - r_sigs[j])))
        rec = {
            "ours_idx": idx, "ours_name": name,
            "ref_idx": ridx, "ref_name": rname,
            "sync_distance": round(dist, 4),
            "is_cut": i in cuts_o,
            "diagnosed": False,
        }
        if i in pick:
            op = tmp_ours / ("o_%04d.png" % idx)
            rp = tmp_ref / ("r_%04d.png" % ridx)
            im.resize(size, Image.BILINEAR).save(op)
            rim.resize(size, Image.BILINEAR).save(rp)
            dest = os.path.join(out_dir, "frames", "%04d" % idx)
            result = compare_pair(str(op), str(rp), dest, size=size, name="ours_%d__ref_%d" % (idx, ridx), photo="no")
            rec["diagnosed"] = True
            rec["scores"] = result["scores"]
            rec["global_mae"] = result["global_mae"]
            rec["alignment"] = result["alignment"]["method"]
            rec["annotated"] = result["paths"]["annotated"]
            rec["findings"] = {f["issue"]: {"ours": f["ours"], "ref": f["ref"],
                                            "verdict": f["verdict_en"], "key": f["verdict_key"]}
                               for f in result["findings"]}
            # Combined "how wrong is this frame"
            comb = float(sum(result["scores"].values()))
            rec["combined"] = round(comb, 4)
            worst.append((comb, result, idx, rec))
        rows.append(rec)
    csv_path = os.path.join(out_dir, "timeline.csv")
    fields = ["ours_idx", "ours_name", "ref_idx", "ref_name", "sync_distance",
              "is_cut", "diagnosed", "global_mae", "combined", "alignment", "annotated"]
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for rec in rows:
            w.writerow(rec)
    worst.sort(key=lambda t: -t[0])
    top = [t[1] for t in worst[:5]]
    report_paths = write_reports(top, out_dir, title="قطع سينمائية  |  cutscene diagnosis")
    summary = {
        "n_ours": len(ours_frames), "n_ref": len(ref_frames),
        "n_cuts_ours": len(cuts_o), "n_cuts_ref": len(cuts_r),
        "n_diagnosed": sum(1 for r in rows if r["diagnosed"]),
        "timeline": csv_path,
        **report_paths,
        "worst_frames": [
            {"ours_idx": t[2], "combined": t[0], "annotated": t[3].get("annotated")}
            for t in worst[:5]
        ],
    }
    Path(os.path.join(out_dir, "cutscene.json")).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[diagnose] cutscene timeline %s  worst %s" % (csv_path, summary["worst_frames"]), flush=True)
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("compare", help="align one pair and run every detector")
    c.add_argument("ours"); c.add_argument("ref")
    c.add_argument("--out", default="diagnose_out")
    c.add_argument("--w", type=int, default=1280); c.add_argument("--h", type=int, default=720)
    c.add_argument("--crop-ours", default=""); c.add_argument("--crop-ref", default="")
    c.add_argument("--photo", default="auto", choices=["auto", "yes", "no"])
    c.add_argument("--name", default="")
    b = sp.add_parser("batch", help="folder of pairs or a pairs.json, then report.md + report.html")
    b.add_argument("--pairs", required=True)
    b.add_argument("--out", default="diagnose_batch")
    b.add_argument("--w", type=int, default=1280); b.add_argument("--h", type=int, default=720)
    u = sp.add_parser("cutscene", help="sync two videos or frame folders, diagnose matched frames")
    u.add_argument("--ours", required=True); u.add_argument("--ref", required=True)
    u.add_argument("--out", default="diagnose_cutscene")
    u.add_argument("--every", type=int, default=1)
    u.add_argument("--max-frames", type=int, default=0)
    u.add_argument("--w", type=int, default=1280); u.add_argument("--h", type=int, default=720)
    args = ap.parse_args(argv)
    size = (args.w, args.h)
    if args.cmd == "compare":
        crop_o = ic.parse_box(args.crop_ours) if args.crop_ours else None
        crop_r = ic.parse_box(args.crop_ref) if args.crop_ref else None
        r = compare_pair(args.ours, args.ref, args.out, size=size,
                         crop_ours=crop_o, crop_ref=crop_r, photo=args.photo, name=args.name)
        write_reports([r], args.out)
        print(json.dumps({"name": r["name"], "alignment": r["alignment"]["method"],
                          "mae": r["global_mae"], "scores": r["scores"],
                          "verdicts": {f["issue"]: f["verdict_en"] for f in r["findings"]},
                          "annotated": r["paths"]["annotated"]}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "batch":
        run_batch(args.pairs, args.out, size=size)
        return 0
    if args.cmd == "cutscene":
        run_cutscene(args.ours, args.ref, args.out, size=size, every=args.every, max_frames=args.max_frames)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

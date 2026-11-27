#!/usr/bin/env python3
"""Compare a port screenshot to an RPCS3 reference (or a known-bad frame).

Clean-room helper for the Strikeforce ps3recomp D3D12 port. No RPCS3 or GPL
code. Related box-side tool: ../sfdiff.py (global MAE + grid). This one adds
white/dark fractions, named bug regions, and a region overlay.

Usage:
    python img_compare.py ours.jpg ref.png --out outdir
    python img_compare.py ours.jpg ref.png --out outdir --w 1280 --h 720
    python img_compare.py ours.jpg ref.png --out outdir --crop-ours 0,32,1280,680
    python img_compare.py --split-stack cmp_ref_vs_p88.jpg --out outdir

Writes outdir/heatmap.png, side_by_side.png, regions_overlay.png, report.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Default compare size: the port window is typically 1280x720.
DEFAULT_W, DEFAULT_H = 1280, 720

# Named regions as fractions of (width, height): x0, y0, x1, y1 in 0..1.
# Tuned for the Lou Sang Village start camera (the giant top shape, the white
# ground, the dark buildings). Override on the command line or in a config.
DEFAULT_REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "top_band": (0.0, 0.0, 1.0, 0.33),
    "middle_band": (0.0, 0.33, 1.0, 0.66),
    "bottom_band_ground": (0.0, 0.66, 1.0, 1.0),
    "tent": (0.15, 0.06, 0.85, 0.48),
    "ground": (0.0, 0.58, 1.0, 0.95),
    "buildings_left": (0.0, 0.10, 0.28, 0.52),
    "buildings_right": (0.72, 0.10, 1.0, 0.55),
    "center": (0.25, 0.25, 0.75, 0.75),
}

LUMA_W = np.array([0.299, 0.587, 0.114], dtype=np.float32)
WHITE_LUMA = 0.85
DARK_LUMA = 0.18


# ---------------------------------------------------------------------------
# Loading / geometry
# ---------------------------------------------------------------------------

def parse_box(s: str) -> Tuple[int, int, int, int]:
    """Parse 'x0,y0,x1,y1' or 'x,y,w,h' is not accepted — always x0,y0,x1,y1."""
    parts = [int(x.strip()) for x in s.replace("x", ",").split(",") if x.strip()]
    if len(parts) != 4:
        raise ValueError("box must be x0,y0,x1,y1  (got %r)" % s)
    x0, y0, x1, y1 = parts
    if x1 <= x0 or y1 <= y0:
        raise ValueError("box must have x1>x0 and y1>y0: %r" % (parts,))
    return x0, y0, x1, y1


def _as_box(spec, w: int, h: int) -> Tuple[int, int, int, int]:
    """Accept [x0,y0,x1,y1] pixels, or a dict with 'frac' or 'px'."""
    if isinstance(spec, dict):
        if "frac" in spec:
            x0, y0, x1, y1 = spec["frac"]
            return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
        if "px" in spec:
            return tuple(int(v) for v in spec["px"])  # type: ignore[return-value]
        return tuple(int(spec[k]) for k in ("x0", "y0", "x1", "y1"))  # type: ignore[return-value]
    x0, y0, x1, y1 = spec
    # Fractions if every value is in 0..1 and not an obvious 1-pixel box.
    vals = [float(x0), float(y0), float(x1), float(y1)]
    if all(0.0 <= v <= 1.0 for v in vals) and (x1 <= 1 and y1 <= 1):
        return (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
    return (int(x0), int(y0), int(x1), int(y1))


def crop_rgb(im: Image.Image, box: Optional[Sequence[int]]) -> Image.Image:
    im = im.convert("RGB")
    if not box:
        return im
    x0, y0, x1, y1 = [int(v) for v in box]
    x0 = max(0, min(x0, im.width - 1))
    y0 = max(0, min(y0, im.height - 1))
    x1 = max(x0 + 1, min(x1, im.width))
    y1 = max(y0 + 1, min(y1, im.height))
    return im.crop((x0, y0, x1, y1))


def load_rgb(path: str, size: Tuple[int, int], crop: Optional[Sequence[int]] = None) -> np.ndarray:
    """Load an image, optional crop, resize with bilinear, return float32 HxWx3 in 0..1."""
    im = crop_rgb(Image.open(path), crop)
    im = im.resize(size, Image.BILINEAR)
    return np.asarray(im, dtype=np.float32) / 255.0


def luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ LUMA_W


def split_stack(path: str) -> Tuple[Image.Image, Image.Image]:
    """Split a vertically stacked A-over-B comparison image into two RGB frames."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    mid = h // 2
    return im.crop((0, 0, w, mid)), im.crop((0, mid, w, h))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def region_stats(ours: np.ndarray, ref: Optional[np.ndarray], box: Tuple[int, int, int, int],
                 white_luma: float = WHITE_LUMA, dark_luma: float = DARK_LUMA) -> dict:
    x0, y0, x1, y1 = box
    h, w = ours.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return {"empty": True}
    a = ours[y0:y1, x0:x1]
    la = luma(a)
    out = {
        "box_px": [x0, y0, x1, y1],
        "brightness": round(float(la.mean()), 4),
        "white_pixel_fraction": round(float((la >= white_luma).mean()), 4),
        "dark_pixel_fraction": round(float((la <= dark_luma).mean()), 4),
        "mean_rgb": [round(float(c), 4) for c in a.reshape(-1, 3).mean(axis=0)],
    }
    if ref is not None:
        b = ref[y0:y1, x0:x1]
        lb = luma(b)
        d = np.abs(a - b)
        e = d.mean(axis=2)
        out["brightness_ref"] = round(float(lb.mean()), 4)
        out["mae"] = round(float(e.mean()), 4)
        out["pct_px_err_gt_0.15"] = round(float((e > 0.15).mean() * 100.0), 2)
        out["histogram_l1"] = round(_hist_l1(la, lb), 4)
        out["white_pixel_fraction_ref"] = round(float((lb >= white_luma).mean()), 4)
        out["dark_pixel_fraction_ref"] = round(float((lb <= dark_luma).mean()), 4)
    return out


def _hist_l1(a: np.ndarray, b: np.ndarray, bins: int = 32) -> float:
    ha, _ = np.histogram(a, bins=bins, range=(0.0, 1.0), density=True)
    hb, _ = np.histogram(b, bins=bins, range=(0.0, 1.0), density=True)
    # density=True scales by bin width; L1 of two densities / 2 is in 0..1 roughly.
    return float(np.abs(ha - hb).sum() * (1.0 / bins))


def global_psnr(ours: np.ndarray, ref: np.ndarray) -> float:
    mse = float(((ours - ref) ** 2).mean())
    return round(float(10.0 * np.log10(1.0 / max(mse, 1e-12))), 2)


def metric_value(stats: dict, metric: str) -> float:
    """Pick a single scalar for the bisect oracle from a region-stats dict."""
    key = {
        "mae": "mae",
        "brightness": "brightness",
        "histogram": "histogram_l1",
        "white_frac": "white_pixel_fraction",
        "dark_frac": "dark_pixel_fraction",
        "mean_abs_diff": "mae",
        "colour_histogram": "histogram_l1",
        "mean_brightness": "brightness",
    }.get(metric, metric)
    if key not in stats:
        raise KeyError("metric %r not in stats (have %s)" % (metric, sorted(stats)))
    return float(stats[key])


def artifact_present(stats: dict, metric: str, threshold: float, rule: str) -> bool:
    """Decide whether the artefact is present from one region's stats.

    rule:
      above      — metric > threshold (MAE vs ref, white_frac, dark_frac, brightness)
      below      — metric < threshold (e.g. close-to-known-bad MAE)
      far_from_ref / close_to_bad — aliases of above / below
    """
    v = metric_value(stats, metric)
    rule = rule.replace("-", "_")
    if rule in ("below", "close_to_bad", "under"):
        return v < threshold
    return v > threshold  # above, far_from_ref, default


# ---------------------------------------------------------------------------
# Visuals
# ---------------------------------------------------------------------------

def _heatmap(err: np.ndarray) -> np.ndarray:
    """err in 0..1 -> RGB float heatmap, black-blue-red-yellow-white."""
    stops = np.array([[0, 0, 0], [0, 0, 1], [1, 0, 0], [1, 1, 0], [1, 1, 1]], dtype=np.float32)
    x = np.clip(err, 0.0, 1.0) * (len(stops) - 1)
    i = np.minimum(np.floor(x).astype(np.int32), len(stops) - 2)
    f = (x - i)[..., None]
    return stops[i] * (1.0 - f) + stops[i + 1] * f


def _to_img(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(rgb * 255.0, 0, 255).astype(np.uint8), "RGB")


def _font(size: int = 16):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
    ):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def write_visuals(ours: np.ndarray, ref: Optional[np.ndarray], regions: Dict[str, Tuple[int, int, int, int]],
                  out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    if ref is not None:
        err = np.abs(ours - ref).mean(axis=2)
        heat = _heatmap(np.clip(err * 2.0, 0.0, 1.0))
        hp = os.path.join(out_dir, "heatmap.png")
        _to_img(heat).save(hp)
        paths["heatmap"] = hp
        sbs = np.concatenate([ours, ref, heat], axis=1)
        sp = os.path.join(out_dir, "side_by_side.png")
        _to_img(sbs).save(sp)
        paths["side_by_side"] = sp
    # Region overlay on ours (and on the heatmap if we have one).
    ov = _to_img(ours).copy()
    draw = ImageDraw.Draw(ov)
    font = _font(16)
    colours = [
        (255, 64, 64), (64, 200, 64), (64, 128, 255), (255, 200, 0),
        (255, 0, 200), (0, 220, 220), (255, 128, 0), (180, 180, 255),
    ]
    i = 0
    for name, box in regions.items():
        if name == "full":
            continue
        x0, y0, x1, y1 = box
        c = colours[i % len(colours)]
        draw.rectangle([x0, y0, max(x0 + 1, x1 - 1), max(y0 + 1, y1 - 1)], outline=c, width=2)
        label = name
        # Anchor the label just inside the box.
        draw.rectangle([x0, y0, x0 + 8 * len(label) + 6, y0 + 18], fill=(0, 0, 0))
        draw.text((x0 + 3, y0 + 1), label, fill=c, font=font)
        i += 1
    op = os.path.join(out_dir, "regions_overlay.png")
    ov.save(op)
    paths["regions_overlay"] = op
    return paths


def compare(ours_path: str, ref_path: Optional[str], out_dir: str,
            size: Tuple[int, int] = (DEFAULT_W, DEFAULT_H),
            crop_ours: Optional[Sequence[int]] = None,
            crop_ref: Optional[Sequence[int]] = None,
            regions: Optional[dict] = None,
            white_luma: float = WHITE_LUMA,
            dark_luma: float = DARK_LUMA) -> dict:
    """Compare ours vs optional ref. Always writes visuals + report.json."""
    ours = load_rgb(ours_path, size, crop_ours)
    ref = load_rgb(ref_path, size, crop_ref) if ref_path else None
    region_specs = regions if regions is not None else DEFAULT_REGIONS
    boxes = {name: _as_box(spec, size[0], size[1]) for name, spec in region_specs.items()}
    stats = {name: region_stats(ours, ref, box, white_luma, dark_luma) for name, box in boxes.items()}
    paths = write_visuals(ours, ref, boxes, out_dir)
    report = {
        "ours": ours_path,
        "ref": ref_path,
        "size": list(size),
        "crop_ours": list(crop_ours) if crop_ours else None,
        "crop_ref": list(crop_ref) if crop_ref else None,
        "regions": stats,
        "paths": paths,
    }
    if ref is not None:
        err = np.abs(ours - ref).mean(axis=2)
        report["global_mae"] = round(float(err.mean()), 4)
        report["global_pct_px_err_gt_0.15"] = round(float((err > 0.15).mean() * 100.0), 2)
        report["psnr_db"] = global_psnr(ours, ref)
        report["worst_named"] = sorted(
            ((k, v.get("mae", 0.0)) for k, v in stats.items() if k != "full" and "mae" in v),
            key=lambda t: -t[1],
        )[:6]
    os.makedirs(out_dir, exist_ok=True)
    rp = os.path.join(out_dir, "report.json")
    with open(rp, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    report["paths"]["report"] = rp
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_region_args(items: Optional[List[str]]) -> Optional[dict]:
    if not items:
        return None
    out = {}
    for item in items:
        # name=x0,y0,x1,y1  (pixels or fractions)
        if "=" not in item:
            raise ValueError("region must be name=x0,y0,x1,y1, got %r" % item)
        name, box = item.split("=", 1)
        parts = [float(x) for x in box.split(",")]
        if len(parts) != 4:
            raise ValueError("region box must have 4 numbers: %r" % item)
        out[name] = parts
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ours", nargs="?", help="port screenshot (or the stacked image with --split-stack)")
    ap.add_argument("ref", nargs="?", help="RPCS3 reference or known-bad image")
    ap.add_argument("--out", default="compare_out", help="output folder")
    ap.add_argument("--w", type=int, default=DEFAULT_W)
    ap.add_argument("--h", type=int, default=DEFAULT_H)
    ap.add_argument("--crop-ours", default="", help="x0,y0,x1,y1 crop applied before resize")
    ap.add_argument("--crop-ref", default="", help="x0,y0,x1,y1 crop applied before resize")
    ap.add_argument("--region", action="append", default=[], help="name=x0,y0,x1,y1 (repeatable; fractions or pixels)")
    ap.add_argument("--white-luma", type=float, default=WHITE_LUMA)
    ap.add_argument("--dark-luma", type=float, default=DARK_LUMA)
    ap.add_argument("--split-stack", action="store_true",
                    help="treat OURS as a vertical A-over-B composite; top=ref, bottom=ours")
    ap.add_argument("--metric", default="", help="optional: print this region's metric (requires --oracle-region)")
    ap.add_argument("--oracle-region", default="tent")
    args = ap.parse_args(argv)

    if not args.ours:
        ap.error("ours image (or --split-stack file) is required")

    ours_path, ref_path = args.ours, args.ref
    tmp_dir = None
    if args.split_stack:
        top, bot = split_stack(args.ours)
        os.makedirs(args.out, exist_ok=True)
        ref_path = os.path.join(args.out, "_split_ref.png")
        ours_path = os.path.join(args.out, "_split_ours.png")
        top.save(ref_path)
        bot.save(ours_path)

    regions = _parse_region_args(args.region)
    crop_ours = parse_box(args.crop_ours) if args.crop_ours else None
    crop_ref = parse_box(args.crop_ref) if args.crop_ref else None
    report = compare(
        ours_path, ref_path, args.out,
        size=(args.w, args.h),
        crop_ours=crop_ours,
        crop_ref=crop_ref,
        regions=regions,
        white_luma=args.white_luma,
        dark_luma=args.dark_luma,
    )
    summary = {k: report[k] for k in report if k in ("global_mae", "psnr_db", "worst_named")}
    # Always print a short, useful table for the three bug regions.
    for name in ("tent", "ground", "buildings_left", "buildings_right", "full"):
        if name in report["regions"]:
            s = report["regions"][name]
            summary[name] = {k: s[k] for k in (
                "brightness", "white_pixel_fraction", "dark_pixel_fraction", "mae",
                "brightness_ref", "white_pixel_fraction_ref", "dark_pixel_fraction_ref",
            ) if k in s}
    print(json.dumps(summary, indent=2))
    if args.metric:
        s = report["regions"][args.oracle_region]
        print("oracle %s %s = %s" % (args.oracle_region, args.metric, metric_value(s, args.metric)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""imgdiff.py -- compare our frame with an RPCS3 reference frame and mark the differences with red boxes.

  python sfauto/tools/imgdiff.py OURS.png REF.png [--out DIR] [--size 1280x720] [--block 32]
         [--thr 0.10] [--ignore x0,y0,x1,y1 ...] [--no-gain]

* Both images are resized to --size, converted to luminance, mean-brightness matched (unless --no-gain)
  and slightly blurred so sharpness/filtering differences do not count.
* The frame is cut into --block pixel tiles; a tile is flagged when its mean |difference| exceeds --thr
  (fraction of full scale).  Flagged tiles that touch are merged into regions.
* Each region is labelled by sign: "ours BRIGHTER" (we are missing darkness, e.g. a missing shadow),
  "ours DARKER" (extra darkness / wrong lighting) or "mixed".
* --ignore takes pixel boxes in the resized frame (use it for the RPCS3 FPS overlay, HUD text, etc.).
  Several --ignore options are allowed.  Fractions are accepted too: 0.0,0.0,0.4,0.5

Output (DIR defaults to sfauto/tools/out/imgdiff): diff_boxes.png (ours with red boxes),
side_by_side.png (ref | ours | heat map), report.json, report.md.  Needs Pillow + numpy (already installed).
It only reads the two images; it never touches the game or project sources.
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path, size):
    im = Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    return im


def lum(im, blur):
    g = im.convert("L").filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(g, dtype=np.float32) / 255.0


def parse_box(s, size):
    v = [float(x) for x in s.split(",")]
    if max(v) <= 1.0:
        v = [v[0] * size[0], v[1] * size[1], v[2] * size[0], v[3] * size[1]]
    return [int(x) for x in v]


def regions_from_tiles(flag):
    h, w = flag.shape
    seen = np.zeros_like(flag, dtype=bool)
    out = []
    for y in range(h):
        for x in range(w):
            if flag[y, x] and not seen[y, x]:
                stack = [(y, x)]; seen[y, x] = True; cells = []
                while stack:
                    cy, cx = stack.pop(); cells.append((cy, cx))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < h and 0 <= nx < w and flag[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True; stack.append((ny, nx))
                out.append(cells)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ours"); ap.add_argument("ref")
    ap.add_argument("--out", default=os.path.join(HERE, "out", "imgdiff"))
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--block", type=int, default=32)
    ap.add_argument("--thr", type=float, default=0.10)
    ap.add_argument("--blur", type=float, default=2.0)
    ap.add_argument("--ignore", action="append", default=[])
    ap.add_argument("--no-gain", action="store_true")
    ap.add_argument("--min-tiles", type=int, default=2, help="drop regions smaller than this many tiles")
    a = ap.parse_args()
    W, H = (int(v) for v in a.size.lower().split("x"))
    ours, ref = load(a.ours, (W, H)), load(a.ref, (W, H))
    lo, lr = lum(ours, a.blur), lum(ref, a.blur)
    valid = np.ones((H, W), dtype=bool)
    for s in a.ignore:
        x0, y0, x1, y1 = parse_box(s, (W, H))
        valid[max(0, y0):y1, max(0, x0):x1] = False
    gain = 1.0
    if not a.no_gain:
        gain = float(lr[valid].mean() / max(1e-6, lo[valid].mean()))
        lo = np.clip(lo * gain, 0, 1)
    d = lo - lr                      # + = ours brighter than the reference
    d[~valid] = 0.0
    B = a.block
    gh, gw = H // B, W // B
    score = np.zeros((gh, gw), dtype=np.float32); sign = np.zeros((gh, gw), dtype=np.float32)
    for gy in range(gh):
        for gx in range(gw):
            blk = d[gy * B:(gy + 1) * B, gx * B:(gx + 1) * B]
            vb = valid[gy * B:(gy + 1) * B, gx * B:(gx + 1) * B]
            if vb.mean() < 0.5:
                continue
            score[gy, gx] = np.abs(blk).mean(); sign[gy, gx] = blk.mean()
    flag = score > a.thr
    regs = []
    for cells in regions_from_tiles(flag):
        if len(cells) < a.min_tiles:
            continue
        ys = [c[0] for c in cells]; xs = [c[1] for c in cells]
        mean_signed = float(np.mean([sign[c] for c in cells]))
        mean_abs = float(np.mean([score[c] for c in cells]))
        pos = sum(1 for c in cells if sign[c] > 0); neg = len(cells) - pos
        kind = "ours BRIGHTER (missing darkness/shadow?)" if pos >= 0.8 * len(cells) else "ours DARKER (extra darkness?)" if neg >= 0.8 * len(cells) else "mixed"
        regs.append(dict(box=[min(xs) * B, min(ys) * B, (max(xs) + 1) * B, (max(ys) + 1) * B], tiles=len(cells),
                         mean_abs_diff=round(mean_abs, 3), mean_signed=round(mean_signed, 3), kind=kind,
                         impact=round(len(cells) * mean_abs, 2)))
    regs.sort(key=lambda r: -r["impact"])
    os.makedirs(a.out, exist_ok=True)
    boxed = ours.copy(); dr = ImageDraw.Draw(boxed)
    for i, r in enumerate(regs):
        dr.rectangle(r["box"], outline=(255, 0, 0), width=3)
        dr.text((r["box"][0] + 4, r["box"][1] + 2), str(i + 1), fill=(255, 255, 0))
    for s in a.ignore:
        x0, y0, x1, y1 = parse_box(s, (W, H)); dr.rectangle([x0, y0, x1, y1], outline=(0, 128, 255), width=1)
    boxed.save(os.path.join(a.out, "diff_boxes.png"))
    heat = np.zeros((H, W, 3), dtype=np.uint8)
    heat[..., 0] = np.clip(np.maximum(d, 0) * 3 * 255, 0, 255)      # red = ours brighter
    heat[..., 2] = np.clip(np.maximum(-d, 0) * 3 * 255, 0, 255)     # blue = ours darker
    side = Image.new("RGB", (W * 3, H))
    side.paste(ref, (0, 0)); side.paste(boxed, (W, 0)); side.paste(Image.fromarray(heat), (2 * W, 0))
    side.resize((W * 3 // 2, H // 2)).save(os.path.join(a.out, "side_by_side.png"))
    total = float(np.abs(d[valid]).mean())
    rep = dict(ours=a.ours, ref=a.ref, size=[W, H], gain_applied=round(gain, 3), mean_abs_diff=round(total, 4),
               flagged_tiles=int(flag.sum()), tiles=int(gh * gw), regions=regs)
    json.dump(rep, open(os.path.join(a.out, "report.json"), "w"), indent=1)
    md = ["# Image diff", "", "ours: `%s`  ref: `%s`" % (a.ours, a.ref),
          "mean |diff| = %.4f, flagged %d of %d tiles, brightness gain on ours = %.3f" % (total, flag.sum(), gh * gw, gain), "",
          "| # | box (x0,y0,x1,y1) | tiles | mean diff | kind |", "|---|---|---:|---:|---|"]
    for i, r in enumerate(regs):
        md.append("| %d | %s | %d | %.3f | %s |" % (i + 1, tuple(r["box"]), r["tiles"], r["mean_abs_diff"], r["kind"]))
    open(os.path.join(a.out, "report.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    if gain < 0.6 or gain > 1.6 or total > 0.15:
        warn = ("WARNING: mean difference %.3f / brightness gain %.2f is large. The two frames probably show a different "
                "camera, time of day or scene, so the boxes are NOT trustworthy. Capture both at the same spot." % (total, gain))
        md.append(""); md.append(warn)
        open(os.path.join(a.out, "report.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))
    print("\nwrote", a.out)


if __name__ == "__main__":
    main()

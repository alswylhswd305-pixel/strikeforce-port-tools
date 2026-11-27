#!/usr/bin/env python3
"""Box-side screenshot diff: ours vs RPCS3 reference.
usage: sfdiff.py ours.png ref.png outdir [--w 1280 --h 720]
Writes outdir/heatmap.png, outdir/side_by_side.jpg, outdir/report.json.
Images should be client-area captures (game image only); both are resized to WxH."""
import sys, json, os, argparse
import numpy as np
from PIL import Image, ImageDraw

def load(p, w, h):
    return np.asarray(Image.open(p).convert('RGB').resize((w, h), Image.BILINEAR), dtype=np.float32) / 255.0

def heat(e):  # e in [0,1] -> RGB (black-blue-red-yellow-white)
    stops = np.array([[0,0,0],[0,0,1],[1,0,0],[1,1,0],[1,1,1]], np.float32)
    x = np.clip(e, 0, 1) * (len(stops) - 1); i = np.floor(x).astype(int); i = np.minimum(i, len(stops) - 2); f = (x - i)[..., None]
    return (stops[i] * (1 - f) + stops[i + 1] * f)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('ours'); ap.add_argument('ref'); ap.add_argument('out')
    ap.add_argument('--w', type=int, default=1280); ap.add_argument('--h', type=int, default=720)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    A, B = load(a.ours, a.w, a.h), load(a.ref, a.w, a.h)
    d = np.abs(A - B)                     # per-channel abs diff
    e = d.mean(axis=2)                    # per-pixel error 0..1
    la, lb = A @ [0.299, 0.587, 0.114], B @ [0.299, 0.587, 0.114]
    Image.fromarray((heat(e * 2.0) * 255).astype(np.uint8)).save(os.path.join(a.out, 'heatmap.png'))
    sbs = np.concatenate([A, B, heat(e * 2.0)], axis=1)
    Image.fromarray((sbs * 255).astype(np.uint8)).resize((a.w * 3 // 2, a.h // 2)).save(os.path.join(a.out, 'side_by_side.jpg'), quality=88)
    H, W = e.shape; regions = {}
    named = {'top_band': (0, 0, W, H // 3), 'middle_band': (0, H // 3, W, 2 * H // 3), 'bottom_band_ground': (0, 2 * H // 3, W, H),
             'center': (W // 4, H // 4, 3 * W // 4, 3 * H // 4)}
    for gy in range(4):
        for gx in range(4):
            named['grid_r%d_c%d' % (gy, gx)] = (gx * W // 4, gy * H // 4, (gx + 1) * W // 4, (gy + 1) * H // 4)
    for k, (x0, y0, x1, y1) in named.items():
        r = e[y0:y1, x0:x1]
        regions[k] = {'mae': round(float(r.mean()), 4), 'pct_px_err_gt_0.15': round(float((r > 0.15).mean() * 100), 2),
                      'luma_ours': round(float(la[y0:y1, x0:x1].mean()), 4), 'luma_ref': round(float(lb[y0:y1, x0:x1].mean()), 4)}
    rep = {'ours': a.ours, 'ref': a.ref, 'size': [a.w, a.h], 'global_mae': round(float(e.mean()), 4),
           'global_pct_px_err_gt_0.15': round(float((e > 0.15).mean() * 100), 2),
           'psnr_db': round(float(10 * np.log10(1.0 / max(float((d ** 2).mean()), 1e-12))), 2),
           'worst_regions': sorted(((k, v['mae']) for k, v in regions.items() if k.startswith('grid')), key=lambda t: -t[1])[:5],
           'regions': regions}
    json.dump(rep, open(os.path.join(a.out, 'report.json'), 'w'), indent=1)
    print(json.dumps({k: rep[k] for k in ('global_mae', 'psnr_db', 'worst_regions')}))

if __name__ == '__main__':
    main()

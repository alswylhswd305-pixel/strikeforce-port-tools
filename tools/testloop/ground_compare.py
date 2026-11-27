#!/usr/bin/env python3
"""ground_compare.py - side-by-side ground images: RPCS3 on the left, our build on the right.

  python ground_compare.py pairs.json <out folder>

pairs.json: [{"name": "village_spawn", "rpcs3": "path or null", "port": "path",
              "port_label": "1780_shadowfix", "rpcs3_label": "village_start",
              "boxes": [[x, y, w, h], ...]   (optional, 0..1 of the image)}]

Every number on the picture is measured on that box only:
  luma        mean brightness 0..255
  sat         mean HSV saturation 0..1
  detail      texture detail = standard deviation of the Laplacian of the grey image
              (a flat, untextured ground is near 0)
  dark %      share of pixels darker than 60 (shadows lying on the ground)
A port box turns RED when it is white and grey (luma > 200 and sat < 0.08), or when
RPCS3 is there and our detail or dark % is under 40% of RPCS3's. Without an RPCS3
picture the left half says so and only the white/grey test is applied.
Writes ground_compare_<name>.png and ground_compare.json.
"""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from mark import font, label, px, RED, GREEN, YELLOW
from arabic_shape import shape_visual

W = 1280
DEFAULT_BOXES = [[0.03, 0.80, 0.94, 0.18], [0.03, 0.60, 0.94, 0.18]]
BOX_AR = ["الأرض القريبة", "الأرض البعيدة شوي"]
BOX_EN = ["near ground", "mid ground"]


def load(p):
    im = Image.open(p).convert("RGB")
    return im.resize((W, int(im.size[1] * W / im.size[0])))


def stats(im, b):
    a = np.asarray(im.crop(b)).astype(np.float32)
    g = a @ np.array([0.299, 0.587, 0.114], np.float32)
    mx, mn = a.max(2), a.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return {"luma": round(float(g.mean()), 1), "sat": round(float(sat.mean()), 3),
            "detail": round(float(lap.std()), 1), "dark_pct": round(float((g < 60).mean() * 100), 1),
            "mean_rgb": [int(v) for v in a.reshape(-1, 3).mean(0)]}


def judge(p, r):
    why_ar, why_en = [], []
    if p["luma"] > 200 and p["sat"] < 0.08:
        why_ar.append("بيضاء ورمادية"); why_en.append("white/grey")
    if r:
        if r["detail"] > 0 and p["detail"] < 0.4 * r["detail"]:
            why_ar.append("نسيج أنعم بوايد من RPCS3"); why_en.append("much less texture detail")
        if r["dark_pct"] >= 2 and p["dark_pct"] < 0.4 * r["dark_pct"]:
            why_ar.append("ظلال الأرض أقل"); why_en.append("fewer shadows on ground")
        if abs(p["luma"] - r["luma"]) > 50:
            why_ar.append("الإضاءة أفتح" if p["luma"] > r["luma"] else "الإضاءة أغمق"); why_en.append("lighting brighter" if p["luma"] > r["luma"] else "lighting darker")
    return why_ar, why_en


def one(pair, out_dir):
    port = load(pair["port"]); H = port.size[1]
    ref = load(pair["rpcs3"]) if pair.get("rpcs3") and os.path.exists(pair["rpcs3"]) else None
    if ref is not None:
        ref = ref.resize((W, H))
    top = 96
    C = Image.new("RGB", (W * 2 + 12, H + top), (12, 12, 12))
    if ref is not None:
        C.paste(ref, (0, top))
    C.paste(port, (W + 12, top))
    d = ImageDraw.Draw(C, "RGBA")
    fb, fl, fs = font(30, True), font(22), font(19)
    hdr_l = "RPCS3 (%s)" % pair.get("rpcs3_label", "") if ref is not None else "RPCS3: no shot of this scene yet  |  " + shape_visual("ما عندنا صورة لنفس المشهد بعد")
    d.text((10, 8), hdr_l, font=fl, fill=(255, 255, 0))
    d.text((W + 22, 8), shape_visual("البورت") + " (%s)" % pair.get("port_label", ""), font=fl, fill=(255, 255, 0))
    d.text((10, 50), shape_visual(pair.get("title_ar", "")) + "   " + pair.get("title_en", ""), font=fs, fill=(220, 220, 220))
    if ref is None:
        msg = ["ما عندنا صورة RPCS3 لهذا المشهد", "No RPCS3 picture of this scene yet",
               "تحتاج تشغيل RPCS3 لنفس المرحلة", "needs an RPCS3 run of the same stage"]
        for i, m in enumerate(msg):
            t = shape_visual(m) if i % 2 == 0 else m
            d.text((W // 2 - d.textlength(t, font=fl) / 2, top + H // 2 - 60 + i * 34), t, font=fl, fill=(200, 200, 200))
    res = {"name": pair["name"], "port": pair["port"], "rpcs3": pair.get("rpcs3") if ref is not None else None, "boxes": []}
    placed_l, placed_r = [], []
    for k, nb in enumerate(pair.get("boxes") or DEFAULT_BOXES):
        b = px(nb, W, H)
        ps = stats(port, b); rs = stats(ref, b) if ref is not None else None
        wa, we = judge(ps, rs)
        col = RED if wa else GREEN
        if rs is None and ps["dark_pct"] < 0.5:
            wa_note = "ما فيه ظلال على الأرض (%.1f%%)، نحتاج RPCS3 نتأكد" % ps["dark_pct"]
            if not wa:
                col = YELLOW
            wa = wa + [wa_note]; we = we + ["no shadows on ground (%.1f%%), needs RPCS3 to confirm" % ps["dark_pct"]]
        nm_ar = BOX_AR[k] if k < len(BOX_AR) else "الأرض %d" % (k + 1)
        nm_en = BOX_EN[k] if k < len(BOX_EN) else "ground %d" % (k + 1)
        rb = [b[0] + W + 12, b[1] + top, b[2] + W + 12, b[3] + top]
        d.rectangle(rb, outline=col, width=5)
        txt_ar = "%s: %s" % (nm_ar, "، ".join(wa) if wa else "قريبة")
        txt_en = "%s: %s | luma %.0f sat %.2f detail %.1f dark %.1f%%" % (nm_en, ", ".join(we) if we else "close", ps["luma"], ps["sat"], ps["detail"], ps["dark_pct"])
        label(d, (rb[2] - 4, rb[1] + 4), [txt_ar, txt_en], col, fs, anchor_right=True, placed=placed_r, max_h=C.size[1])
        if ref is not None:
            lb = [b[0], b[1] + top, b[2], b[3] + top]
            d.rectangle(lb, outline=YELLOW, width=4)
            label(d, (lb[2] - 4, lb[1] + 4), ["%s (المرجع)" % nm_ar, "%s (reference) | luma %.0f sat %.2f detail %.1f dark %.1f%%" % (nm_en, rs["luma"], rs["sat"], rs["detail"], rs["dark_pct"])],
                  YELLOW, fs, anchor_right=True, placed=placed_l, max_h=C.size[1])
        res["boxes"].append({"box": nb, "name_ar": nm_ar, "name_en": nm_en, "port": ps, "rpcs3": rs,
                             "fail": col == RED, "unconfirmed": col == YELLOW, "reason_ar": wa, "reason_en": we})
    for i, line in enumerate(pair.get("notes", [])):
        label(d, (W * 2 + 12 - 6, top + 6 + i * 70), line, YELLOW, fs, anchor_right=True, placed=placed_r, max_h=C.size[1])
    op = os.path.join(out_dir, "ground_compare_%s.png" % pair["name"])
    C.save(op, optimize=True)
    res["image"] = op
    return res


def main():
    pairs = json.load(open(sys.argv[1], encoding="utf-8-sig"))
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    allr = [one(p, out) for p in pairs]
    json.dump({"metric": __doc__.split("Every number")[1].split("Writes")[0].strip(), "pairs": allr},
              open(os.path.join(out, "ground_compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for r in allr:
        print(r["name"], [("FAIL " if b["fail"] else "ok ") + "/".join(b["reason_en"]) + " port=%s rpcs3=%s" % (b["port"], b["rpcs3"]) for b in r["boxes"]])


if __name__ == "__main__":
    main()

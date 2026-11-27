#!/usr/bin/env python3
"""mark.py - red-box marks with Arabic + English labels, per checkpoint and per section.

  python mark.py <run folder>        (after analyze.py)

Writes shots/<cp>_marked.jpg, shots/<cp>_sec_<section>.jpg and annotations.json.
Red = a measured check failed or a box to look at, green = the check passed,
yellow = not measured. Arabic is shaped by arabic_shape.py (Pillow here has no raqm).
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont
from arabic_shape import shape_visual

HERE = os.path.dirname(os.path.abspath(__file__))
RED, GREEN, YELLOW = (230, 20, 20), (20, 200, 60), (240, 200, 0)
FONT_DIRS = [r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu"]


def font(size, bold=False):
    for d in FONT_DIRS:
        for n in (("tahomabd.ttf", "arialbd.ttf") if bold else ("tahoma.ttf", "arial.ttf")) + ("DejaVuSans.ttf",):
            p = os.path.join(d, n)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def label(draw, xy, lines, color, f, anchor_right=False, max_w=None, placed=None, max_h=None):
    """lines: list of str (Arabic ones get shaped). Draws a dark plate with the text.
    placed: list of rects already used; the plate moves down until it overlaps none."""
    vis = [shape_visual(l) for l in lines if l]
    w = max(draw.textlength(v, font=f) for v in vis) + 12
    lh = f.size + 6; h = lh * len(vis) + 6
    x, y = xy
    if anchor_right: x -= w
    if max_w: x = max(0, min(x, max_w - w))
    y = max(0, y)
    if placed is not None:
        def hit(yy):
            return any(not (x + w < a or x > c or yy + h < b or yy > d) for a, b, c, d in placed)
        y0 = y
        while hit(y) and (max_h is None or y + h < max_h):
            y += 4
        if max_h is not None and y + h >= max_h:
            y = y0
            while hit(y) and y > 0:
                y -= 4
        placed.append((x, y, x + w, y + h))
    draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 0, 190), outline=color, width=2)
    for i, v in enumerate(vis):
        tw = draw.textlength(v, font=f)
        draw.text((x + w - 6 - tw, y + 4 + i * lh), v, font=f, fill=(255, 255, 255))   # right-aligned
    return h


def px(norm, W, H):
    x, y, w, h = norm
    return [int(x * W), int(y * H), int((x + w) * W), int((y + h) * H)]


def mark_run(run_dir):
    an = json.load(open(os.path.join(run_dir, "analysis.json"), encoding="utf-8-sig"))
    meta = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8-sig"))
    tmpl_p = os.path.join(HERE, "annotations", an["route"] + ".json")
    tmpl = json.load(open(tmpl_p, encoding="utf-8-sig")) if os.path.exists(tmpl_p) else {}
    f_lab, f_ban, f_sec = font(20), font(26, True), font(22, True)
    ann = {"created": meta.get("finished"), "build": an["build"], "route": an["route"],
           "coordinate_space": "x,y,w,h are pixels in the client capture; norm = fractions 0..1",
           "colors": {"red": "check failed / look here", "green": "check passed", "yellow": "not measured"}, "images": {}}
    flag_ar = {"pass": "نجح", "changed": "تغيّر عن المرجع", "hang": "تعليق محتمل", "noref": "ما فيه صورة مرجعية", "noshot": "ما فيه صورة"}
    for c in an["checkpoints"]:
        p = os.path.join(run_dir, "shots", c["name"] + ".png")
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB"); W, H = im.size
        base = im.copy()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        boxes = []; placed = [(W - 700, H - 84, W, H)]
        # section checks with a region
        for s in c.get("sections", []):
            for chk in s["checks"]:
                if "norm" not in chk:
                    continue
                ok = chk.get("passed") if chk["measured"] else None
                col = GREEN if ok else (YELLOW if ok is None else RED)
                b = px(chk["norm"], W, H)
                d.rectangle(b, outline=col + (255,), width=4)
                ar = (chk["ar"] if ok else chk["fail_ar"]) + " (" + str(chk.get("value", "")) + ")"
                en = "%s: %s" % (s["en"], "OK" if ok else ("not measured" if ok is None else "FAIL"))
                label(d, (b[0] + 2, b[1] + 2), [ar, en], col, f_lab, max_w=W, placed=placed, max_h=H - 84)
                boxes.append({"id": s["id"] + "_" + chk["type"], "section": s["id"], "label_ar": ar, "label_en": en,
                              "result": "pass" if ok else ("not_measured" if ok is None else "fail"),
                              "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "norm": chk["norm"]})
        # template boxes
        for t in tmpl.get("default", []) + tmpl.get(c["name"], []):
            b = px(t["norm"], W, H)
            d.rectangle(b, outline=RED + (255,), width=4)
            label(d, (b[2], b[3] - 60), [t["label_ar"], t["label_en"]], RED, f_lab, anchor_right=True, max_w=W, placed=placed, max_h=H - 84)
            boxes.append({"id": t["id"], "issue": t.get("issue"), "label_ar": t["label_ar"], "label_en": t["label_en"],
                          "result": "look", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "norm": t["norm"]})
        # banner
        fl = c.get("flag", "")
        ban = ["%s — %s" % (c.get("title_ar", c["name"]), flag_ar.get(fl, fl)),
               "build %s | route %s | %s | %s" % (an["build"], an["route"], c["name"], (c.get("window_title") or "-")[-40:])]
        label(d, (W - 4, H - 80), ban, RED if fl in ("hang", "changed") else (255, 255, 255), f_ban, anchor_right=True, max_w=W)
        out = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
        mp = os.path.join(run_dir, "shots", c["name"] + "_marked.jpg")
        out.save(mp, quality=90)
        # section crops
        crops = {}
        for s in c.get("sections", []):
            b = px(s["crop"], W, H)
            cr = base.crop(b)
            scale = 640 / max(cr.size[0], 1)
            cr = cr.resize((640, max(1, int(cr.size[1] * scale))))
            cw, ch = cr.size
            refimg = None
            if s.get("ref_id"):
                rp = os.path.join(HERE, "reference", "rpcs3", s["ref_id"] + ".png")
                if os.path.exists(rp):
                    R = Image.open(rp).convert("RGB"); rb = px(s["crop"], R.size[0], R.size[1])
                    refimg = R.crop(rb).resize((cw, ch))
            canvas = Image.new("RGB", (cw * (2 if refimg else 1) + (8 if refimg else 0), ch + 70), (15, 15, 15)); canvas.paste(cr, (0, 70))
            if refimg:
                canvas.paste(refimg, (cw + 8, 70))
                ImageDraw.Draw(canvas).text((cw + 14, 80), "RPCS3 (%s)" % s["ref_id"], font=f_lab, fill=(255, 255, 0))
                ImageDraw.Draw(canvas).text((10, 80), shape_visual("البورت") + " (%s)" % an["build"], font=f_lab, fill=(255, 255, 0))
            cd = ImageDraw.Draw(canvas)
            col = GREEN if s["pass"] else RED
            cd.rectangle([0, 70, cw - 1, ch + 69], outline=col, width=5)
            pct = ("%d%%" % s["checks_pct"]) if s["checks_pct"] is not None else "ما ينقاس بعد"
            refp = ("، ألوان RPCS3 %s%%" % s["ref_match_pct"]) if s.get("ref_match_pct") is not None else ""
            label(cd, (canvas.size[0] - 2, 2), ["%s: %s — نجح %d من %d فحص%s" % (s["ar"], pct, s["checks_passed"], s["checks_measured"], refp),
                                    s["reason_ar"][:90]], col, f_sec if len(s["reason_ar"]) < 40 else f_lab, anchor_right=True, max_w=canvas.size[0])
            sp = os.path.join(run_dir, "shots", "%s_sec_%s.jpg" % (c["name"], s["id"]))
            canvas.save(sp, quality=88); crops[s["id"]] = os.path.relpath(sp, run_dir)
        ann["images"][c["name"]] = {"raw": "shots/%s.png" % c["name"], "marked": "shots/%s_marked.jpg" % c["name"],
                                     "section_crops": crops, "flag": fl, "boxes": boxes, "size": [W, H]}
    with open(os.path.join(run_dir, "annotations.json"), "w", encoding="utf-8") as f:
        json.dump(ann, f, ensure_ascii=False, indent=1)
    return ann


if __name__ == "__main__":
    mark_run(sys.argv[1])

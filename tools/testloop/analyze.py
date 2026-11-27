#!/usr/bin/env python3
"""analyze.py - everything that looks at a finished run (no game, no network).

  python analyze.py <run folder>      re-analyse a run (writes analysis.json)

Per checkpoint:
  * frozen check: the two burst shots taken ~1.2 s apart are identical -> possible hang
  * image match vs golden/<route>/<checkpoint>.png (if present): dod3-recomp rule
    (third_party/dod3-recomp/compare_frames.py: noise / close = >=99% of pixels within
    tol 8 / DIFF) on the full frame, plus a per-section match % = share of pixels within
    `match_tol` levels after scaling the crop to `match_scale` (animation-tolerant),
    and a heat-map image.
  * the same metrics against the previous run of the route (labelled as such, NOT a reference)
  * draws per section from the [FCL] frame list (sections.json rules)
  * section checks -> passed/total (only measured checks count) and an Arabic reason line
Run level: hang if the live samples stop changing for >= 60 s, or the process died.
"""
import json, os, re, sys, glob
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "third_party", "infamous2-recomp"))
import pngstat  # MIT, unmodified: stats(w, h, bpp, rows, box)

NOISE_PIXELS, NOISE_LEVELS = 16, 4     # same constants as dod3-recomp compare_frames.py
FCL_RX = re.compile(r"\[FCL\] #(\d+) (\w+) prim=(\d+) n=(\d+) fp=(\S+) vp=(\S+) rt=(\S+) z=(\S+) dt=(\d) df=(\S+) "
                    r"dm=(\d) cull=(\d) bl=(\d) at=(\d) am=(\S+)(.*)")


def load_json(p, default=None):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def img(p):
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.int16)


def box_px(norm, w, h):
    x, y, bw, bh = norm
    return int(x * w), int(y * h), int((x + bw) * w), int((y + bh) * h)


def region_stats(a, norm):
    h, w = a.shape[:2]
    x0, y0, x1, y1 = box_px(norm, w, h)
    sub = a[y0:y1, x0:x1].astype(np.uint8)
    if sub.size == 0:
        return None
    # pngstat.stats wants rows of bytes (bpp 3); crop first so the pure-Python loop stays small
    rows = [bytearray(r.tobytes()) for r in sub]
    st = pngstat.stats(sub.shape[1], sub.shape[0], 3, rows, (0, 0, sub.shape[1], sub.shape[0]))
    m = st["mean"]; mx, mn = max(m), min(m)
    st["sat"] = round((mx - mn) / mx, 3) if mx else 0.0
    q = (sub[::2, ::2] // 8).reshape(-1, 3)
    st["colors"] = int(len(np.unique(q[:, 0].astype(np.int32) * 1024 + q[:, 1] * 32 + q[:, 2])))
    return st


def dod3_compare(a, b, tol=8):
    """dod3-recomp compare_frames.py rule on two RGB arrays of the same size."""
    d = np.abs(a - b).max(axis=2)
    npx = d.size
    diff_px = int((d > 0).sum())
    if diff_px == 0:
        return {"kind": "identical", "diff_px": 0, "worst": 0, "mean": 0.0, "within_pct": 100.0}
    flat = np.sort(d.ravel())
    worst = int(flat[-2]) if flat.size > 1 else int(flat[-1])   # single worst pixel not counted
    within = float((d <= tol).sum()) / npx
    kind = "noise" if (diff_px <= NOISE_PIXELS and worst <= NOISE_LEVELS) else ("close" if within >= 0.99 else "DIFF")
    return {"kind": kind, "diff_px": diff_px, "worst": worst, "mean": round(float(np.abs(a - b).mean()), 3),
            "within_pct": round(within * 100, 2), "tol": tol}


def soft_match(a, b, tol, scale):
    """% of pixels within tol after down-scaling both crops (animation-tolerant)."""
    h, w = a.shape[:2]
    sw, sh = max(8, int(w * scale)), max(8, int(h * scale))
    A = np.asarray(Image.fromarray(a.astype(np.uint8)).resize((sw, sh), Image.BILINEAR), dtype=np.int16)
    B = np.asarray(Image.fromarray(b.astype(np.uint8)).resize((sw, sh), Image.BILINEAR), dtype=np.int16)
    return round(float((np.abs(A - B).max(axis=2) <= tol).mean()) * 100, 1)


def load_refs(route):
    """RPCS3 reference images valid for this route -> list of (manifest entry, array)."""
    man = load_json(os.path.join(HERE, "reference", "rpcs3", "manifest.json"), {})
    out = []
    for e in man.get("images", []):
        p = os.path.join(HERE, "reference", "rpcs3", e["file"])
        if route in e.get("routes", []) and os.path.exists(p):
            out.append((e, img(p)))
    return out


def hist_match(a, b):
    """HSV histogram intersection (9 hue x 3 sat x 3 value bins; two RPCS3 village shots score 86-99% against each other) in % - camera-independent colour match."""
    import cv2
    ha = cv2.calcHist([cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2HSV)], [0, 1, 2], None, [9, 3, 3], [0, 180, 0, 256, 0, 256])
    hb = cv2.calcHist([cv2.cvtColor(b.astype(np.uint8), cv2.COLOR_RGB2HSV)], [0, 1, 2], None, [9, 3, 3], [0, 180, 0, 256, 0, 256])
    ha /= max(ha.sum(), 1); hb /= max(hb.sum(), 1)
    return round(float(np.minimum(ha, hb).sum()) * 100, 1)


def crop(a, norm):
    h, w = a.shape[:2]
    x0, y0, x1, y1 = box_px(norm, w, h)
    return a[y0:y1, x0:x1]


def heatmap(a, b, out):
    import cv2
    d = np.abs(a - b).max(axis=2).astype(np.float32)
    d = np.clip(d * 3, 0, 255).astype(np.uint8)
    hm = cv2.applyColorMap(d, cv2.COLORMAP_JET)[:, :, ::-1]
    mix = (a.astype(np.float32) * 0.45 + hm.astype(np.float32) * 0.55).astype(np.uint8)
    Image.fromarray(mix).save(out, quality=88)


def parse_fcl(path):
    """-> list of draw dicts from the LAST complete '[FCL] ---- listing frame' block in path."""
    if not path or not os.path.exists(path):
        return None
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    start = None
    for i, l in enumerate(lines):
        if "[FCL] ---- listing frame" in l:
            start = i
    if start is None:
        return None
    draws = []
    for l in lines[start + 1:]:
        if "---- end of listed frame" in l or "---- listing frame" in l:
            break
        m = FCL_RX.search(l)
        if m:
            draws.append({"idx": int(m[1]), "kind": m[2], "n": int(m[4]), "fp": m[5].upper().replace("0X", "0x"),
                          "vp": m[6].split("/")[0].upper().replace("0X", "0x"), "rt": m[7].upper().replace("0X", "0x"),
                          "z": m[8].upper().replace("0X", "0x"), "dt": int(m[9]), "dm": int(m[11]), "bl": int(m[13]),
                          "tex": " ".join(t.split("/", 1)[1] if "/" in t else t for t in re.findall(r"t\d=(\S+)", m[16]))})
    return draws


def _hex_eq(a, b):
    try:
        return int(str(a), 16) == int(str(b), 16)
    except ValueError:
        return str(a).lower() == str(b).lower()


def rule_match(rule, d):
    for k, v in rule.items():
        if k in ("fp", "vp"):
            if not any(_hex_eq(d[k], x) for x in v): return False
        elif k in ("rt", "z"):
            if not _hex_eq(d[k], v): return False
        elif k in ("dt", "dm", "bl"):
            if d[k] != int(v): return False
        elif k == "idx":
            if not (v[0] <= d["idx"] <= v[1]): return False
        elif k == "tex":
            if v not in d["tex"]: return False
    return True


def classify(draws, sections):
    out = {s["id"]: [] for s in sections}; out["other"] = []
    for d in draws:
        for s in sections:
            if any(rule_match(r, d) for r in s.get("rules", [])):
                out[s["id"]].append(d["idx"]); break
        else:
            out["other"].append(d["idx"])
    return out


def run_checks(sec, shot_arr, draws, by_sec):
    res = []
    for c in sec.get("checks", []):
        t = c["type"]; r = {"type": t, "ar": c.get("ar", ""), "fail_ar": c.get("fail_ar", ""), "measured": True}
        if t == "draws_min":
            if draws is None:
                r.update(measured=False, value="ما فيه قائمة رسمات")
            else:
                n = len(by_sec.get(sec["id"], [])); r.update(value=n, passed=n >= c.get("n", 1))
        elif t == "uses_texture":
            if draws is None:
                r.update(measured=False, value="ما فيه قائمة رسمات")
            else:
                n = sum(1 for d in draws if c["tex"] in d["tex"] and not (_hex_eq(d["rt"], "0") and _hex_eq(d["z"], "0x003A0000")))
                r.update(value=n, passed=n >= c.get("n", 1))
        elif t in ("region_not_white", "region_not_dark", "region_content"):
            st = region_stats(shot_arr, c["norm"]) if shot_arr is not None else None
            if st is None:
                r.update(measured=False, value="ما فيه صورة")
            else:
                r["norm"] = c["norm"]; r["stats"] = {k: st[k] for k in ("mean", "l50", "l95", "sat", "colors", "hiPct")}
                if t == "region_not_white":
                    white = st["l50"] >= c["l50_min"] and st["sat"] <= c["sat_max"]
                    r.update(value="سطوع %d، تشبع %.2f" % (st["l50"], st["sat"]), passed=not white)
                elif t == "region_not_dark":
                    r.update(value="سطوع %d" % st["l50"], passed=st["l50"] > c["l50_max"])
                else:
                    r.update(value="%d لون" % st["colors"], passed=st["colors"] >= c["min_colors"])
        else:   # not_measured
            r.update(measured=False, value="ما ينقاس بعد")
        res.append(r)
    return res


def previous_run(run_dir, route):
    runs = sorted(d for d in glob.glob(os.path.join(os.path.dirname(run_dir), "*_%s" % route)) if os.path.isdir(d))
    runs = [d for d in runs if os.path.abspath(d) < os.path.abspath(run_dir) and os.path.exists(os.path.join(d, "analysis.json"))]
    return runs[-1] if runs else None


def analyze(run_dir):
    meta = load_json(os.path.join(run_dir, "run.json"), {})
    route = meta.get("route", "")
    secdef = load_json(os.path.join(HERE, "sections.json"))
    sections = secdef["sections"]; tol = secdef.get("match_tol", 12); scale = secdef.get("match_scale", 0.25)
    gold_dir = os.path.join(HERE, "golden", route)
    prev = previous_run(run_dir, route)
    refs = load_refs(route)
    out = {"run": os.path.basename(run_dir), "route": route, "build": meta.get("build"), "previous_run": os.path.basename(prev) if prev else None,
           "checkpoints": [], "refs": [e["id"] for e, _ in refs], "metric_note_ar": "تطابق الألوان مع RPCS3 = تقاطع توزيع الألوان (HSV) بين قسمنا ونفس القسم في صورة RPCS3 (زاوية كاميرا مختلفة، فهي مقارنة ألوان مو بكسلات؛ صورتين من RPCS3 للقرية تطلع بينهم 86–99%%). نسبة الفحوصات = عدد الفحوصات اللي نجحت ÷ الفحوصات اللي انقاست. تطابق الصورة = نسبة البكسلات اللي فرقها ≤ %d درجة بعد تصغير الصورة إلى %d%% (مع صورة مرجعية من golden فقط)." % (tol, int(scale * 100))}
    for cp in meta.get("checkpoints", []):
        name = cp["name"]; sd = os.path.join(run_dir, "shots")
        pa, pb = os.path.join(sd, name + ".png"), os.path.join(sd, name + "_b.png")
        c = {"name": name, "title_ar": cp.get("title_ar", name), "issues": cp.get("issues", []), "window_title": cp.get("window_title", ""), "t": cp.get("t")}
        if not os.path.exists(pa):
            c.update(flag="noshot"); out["checkpoints"].append(c); continue
        A = img(pa)
        if os.path.exists(pb):
            B = img(pb)
            if B.shape == A.shape:
                c["burst_mean_diff"] = round(float(np.abs(A - B).mean()), 3)
                c["frozen"] = c["burst_mean_diff"] < 0.05
        draws = parse_fcl(os.path.join(sd, name + "_fcl.txt"))
        by_sec = classify(draws, sections) if draws is not None else {}
        c["draws_total"] = len(draws) if draws is not None else None
        c["draws_other"] = len(by_sec.get("other", [])) if draws is not None else None
        g = os.path.join(gold_dir, name + ".png")
        G = img(g) if os.path.exists(g) else None
        if G is not None and G.shape != A.shape:
            G = np.asarray(Image.fromarray(G.astype(np.uint8)).resize((A.shape[1], A.shape[0])), dtype=np.int16)
        if G is not None:
            c["golden"] = os.path.relpath(g, run_dir); c["full_vs_golden"] = dod3_compare(A, G)
            heatmap(A, G, os.path.join(sd, name + "_heat_golden.jpg")); c["heat_golden"] = "shots/%s_heat_golden.jpg" % name
        P = None
        pp = os.path.join(prev, "shots", name + ".png") if prev else None
        if pp and os.path.exists(pp):
            P = img(pp)
            if P.shape == A.shape:
                c["full_vs_previous"] = dod3_compare(A, P)
                heatmap(A, P, os.path.join(sd, name + "_heat_prev.jpg")); c["heat_prev"] = "shots/%s_heat_prev.jpg" % name
            else:
                P = None
        prev_an = load_json(os.path.join(prev, "analysis.json")) if prev else None
        prev_cp = next((x for x in (prev_an or {}).get("checkpoints", []) if x["name"] == name), None)
        secs = []
        for s in sections:
            chk = run_checks(s, A, draws, by_sec)
            meas = [x for x in chk if x["measured"]]
            passed = [x for x in meas if x.get("passed")]
            fails = [x["fail_ar"] for x in meas if not x.get("passed")] + [x["fail_ar"] for x in chk if not x["measured"] and x["type"] == "not_measured"]
            e = {"id": s["id"], "ar": s["ar"], "en": s["en"], "crop": s["crop"], "checks": chk,
                 "checks_passed": len(passed), "checks_measured": len(meas),
                 "checks_pct": round(100.0 * len(passed) / len(meas)) if meas else None,
                 "draws": len(by_sec.get(s["id"], [])) if draws is not None else None,
                 "draw_idx": (by_sec.get(s["id"], [])[:1] + by_sec.get(s["id"], [])[-1:]) if draws is not None else None,
                 "match_golden_pct": soft_match(crop(A, s["crop"]), crop(G, s["crop"]), tol, scale) if G is not None else None,
                 "match_prev_pct": soft_match(crop(A, s["crop"]), crop(P, s["crop"]), tol, scale) if P is not None else None}
            # colour match with RPCS3 references (best of the refs valid for this section) + region stats there
            rr = [(e, R) for e, R in refs if s["id"] in e.get("sections", [])]
            if rr:
                scores = [(hist_match(crop(A, s["crop"]), crop(R, s["crop"])), e["id"]) for e, R in rr]
                e["ref_match_pct"], e["ref_id"] = max(scores)
                for ck in chk:
                    if "norm" in ck and ck.get("stats"):
                        rs = [region_stats(R, ck["norm"]) for _, R in rr]
                        ck["ref_stats"] = [{k: x[k] for k in ("mean", "l50", "sat", "colors")} for x in rs if x]
                if e["ref_match_pct"] < 60:
                    fails.append("ألوان %s بعيدة عن RPCS3 (%s%%)" % (s["ar"], e["ref_match_pct"]))
            else:
                e["ref_match_pct"], e["ref_id"] = None, None
            if prev_cp:
                ps = next((x for x in prev_cp.get("sections", []) if x["id"] == s["id"]), None)
                if ps and ps.get("draws") is not None and e["draws"] is not None:
                    e["draws_prev"] = ps["draws"]
                    if ps["draws"] > 0 and e["draws"] < ps["draws"] * 0.5:
                        fails.append("عدد الرسمات نزل من %d إلى %d مقارنة بالتشغيل السابق" % (ps["draws"], e["draws"]))
            e["reason_ar"] = "، ".join(fails) if fails else "كل الفحوصات المقاسة نجحت"
            e["pass"] = (len(meas) > 0 and len(passed) == len(meas) and (e["match_golden_pct"] is None or e["match_golden_pct"] >= 95))
            secs.append(e)
        c["sections"] = secs
        if c.get("frozen"):
            c["flag"] = "hang"
        elif G is not None:
            c["flag"] = "pass" if c["full_vs_golden"]["kind"] in ("identical", "noise", "close") or min(
                [x["match_golden_pct"] for x in secs]) >= 95 else "changed"
        else:
            c["flag"] = "noref"
        out["checkpoints"].append(c)
    # run-level hang from the live samples
    live = sorted(glob.glob(os.path.join(run_dir, "live", "live_*.png")))
    same_run, longest = 0, 0
    for x, y in zip(live, live[1:]):
        try:
            a, b = img(x), img(y)
            same = a.shape == b.shape and float(np.abs(a - b).mean()) < 0.05
        except Exception:
            same = False
        same_run = same_run + 1 if same else 0
        longest = max(longest, same_run)
    every = meta.get("live_every", 20)
    out["live_samples"] = len(live); out["longest_still_secs"] = longest * every
    out["process_died"] = bool(meta.get("process_died"))
    out["run_hang"] = out["process_died"] or longest * every >= 60
    with open(os.path.join(run_dir, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    r = analyze(sys.argv[1])
    for c in r["checkpoints"]:
        print(c["name"], c.get("flag"), [(s["id"], s.get("checks_pct"), s.get("draws")) for s in c.get("sections", [])])

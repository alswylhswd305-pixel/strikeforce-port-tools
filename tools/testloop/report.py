#!/usr/bin/env python3
"""report.py - Arabic report (report.md + report.html) for one run, and the project
status tracker (status.json + STATUS_AR.md + STATUS_AR.html).

  python report.py <run folder>       write the run report and update the status
  python report.py --status           rewrite STATUS_AR.md / .html from status.json
"""
import html, json, os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(HERE, "status.json")
FLAG = {"pass": ("✅", "نجح"), "changed": ("⚠️", "تغيّر عن المرجع"), "hang": ("⛔", "تعليق محتمل"),
        "noref": ("🔵", "ما فيه صورة مرجعية بعد"), "noshot": ("❌", "ما انأخذت صورة")}

DEFAULT_ISSUES = [
    {"id": "faces", "title_ar": "الوجوه الغامقة / المشوهة", "title_en": "Dark / broken faces", "state": "fixed",
     "state_ar": "مصلّح في 1760 (معتمد)", "section": "characters", "how_ar": "فحص سطوع وجه الحارس + صورة"},
    {"id": "shadows", "title_ar": "الظلال (خريطة الظل)", "title_en": "Shadows (1780 shadow-map depth compare)", "state": "testing",
     "state_ar": "إصلاح مبني في 1780، ينتظر اختبار", "section": "shadows", "build": "1780_shadowfix", "how_ar": "رسمات خريطة الظل + صورة تحتاج عين سعود"},
    {"id": "freeze", "title_ar": "تعليق شاشة Now Loading", "title_en": "Now Loading freeze (mixer halt)", "state": "cause",
     "state_ar": "السبب شبه معروف (أصوات ما تنحرر)، ما فيه إصلاح", "section": None, "how_ar": "مسار loading (تجريبي) + كشف تعليق"},
    {"id": "scarf", "title_ar": "الوشاح الممطوط", "title_en": "Stretched scarf / cloth", "state": "testing",
     "state_ar": "قيد الاختبار (1776)", "section": "characters", "build": "1776_clothv2_arl", "how_ar": "صورة تحتاج عين سعود"},
    {"id": "voices", "title_ar": "الأصوات", "title_en": "Voices (1773 ATRAC fix)", "state": "testing",
     "state_ar": "قيد الاختبار (1773)", "section": None, "build": "1773_atrac_fix", "how_ar": "يدوي: يحتاج سماع (الأداة ما تسمع)"},
    {"id": "white_ground", "title_ar": "الأرض البيضاء", "title_en": "White ground (terrain not drawn)", "state": "investigating",
     "state_ar": "قيد البحث: الأرض ما تنرسم والأبيض هو السماء", "section": "ground", "how_ar": "فحص سطوع وتشبع الأرض + رسمات 288-348"},
    {"id": "light_shaft", "title_ar": "عمود الضوء المعتم", "title_en": "Opaque light shaft", "state": "investigating",
     "state_ar": "عندنا خيط من لعبة ثانية، سجلات فقط", "section": "effects", "how_ar": "رسمات المؤثرات؛ عمود الضوء نفسه ما ينقاس بعد"},
]


def load_status():
    if os.path.exists(STATUS):
        with open(STATUS, encoding="utf-8-sig") as f:
            st = json.load(f)
        have = {i["id"] for i in st["issues"]}
        st["issues"] += [dict(i) for i in DEFAULT_ISSUES if i["id"] not in have]
        return st
    return {"_about": "Strikeforce project tracker. 'state'/'state_ar' are set by people (testloop.py status set ...); last_* are written by each test run.",
            "issues": [dict(i) for i in DEFAULT_ISSUES], "updated": None}


def save_status(st):
    st["updated"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M (توقيت الكويت)")
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    write_status_pages(st)


def write_status_pages(st):
    md = ["# حالة مشاكل Strikeforce", "", "آخر تحديث: %s" % st.get("updated"), "",
          "| المشكلة | الحالة | آخر نسخة | آخر اختبار | آخر نتيجة |", "|---|---|---|---|---|"]
    for i in st["issues"]:
        md.append("| %s | %s | %s | %s | %s |" % (i["title_ar"], i.get("state_ar", ""), i.get("last_build", "—"),
                                               i.get("last_test", "—"), i.get("last_result", "—")))
    md += ["", "الحالة يكتبها سالم أو سعود بيده. آخر نتيجة تكتبها الأداة بعد كل اختبار (أرقام مقاسة فقط)."]
    open(os.path.join(HERE, "STATUS_AR.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % tuple(
        html.escape(str(x)) for x in (i["title_ar"], i.get("state_ar", ""), i.get("last_build", "—"), i.get("last_test", "—"), i.get("last_result", "—")))
        for i in st["issues"])
    page = PAGE % ("حالة مشاكل Strikeforce", "<h1>حالة مشاكل Strikeforce</h1><p>آخر تحديث: %s</p><table><tr><th>المشكلة</th><th>الحالة</th><th>آخر نسخة</th><th>آخر اختبار</th><th>آخر نتيجة</th></tr>%s</table>" % (html.escape(str(st.get("updated"))), rows))
    open(os.path.join(HERE, "STATUS_AR.html"), "w", encoding="utf-8").write(page)


PAGE = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>%s</title>
<style>body{font-family:Tahoma,Arial,sans-serif;background:#111;color:#eee;margin:16px;font-size:20px}
h1{font-size:30px}h2{font-size:26px;margin-top:30px;border-top:2px solid #444;padding-top:12px}
table{border-collapse:collapse;width:100%%;margin:10px 0}td,th{border:1px solid #555;padding:8px;vertical-align:top}
th{background:#222}img{max-width:100%%;border:2px solid #333;margin:6px 0}.big{width:100%%}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:10px}.ok{color:#5f5}.bad{color:#f66}.na{color:#fd5}
.small{font-size:15px;color:#aaa}</style></head><body>%s</body></html>"""


def pct(v):
    return "ما ينقاس بعد" if v is None else "%s%%" % v


def write_report(run_dir):
    an = json.load(open(os.path.join(run_dir, "analysis.json"), encoding="utf-8-sig"))
    meta = json.load(open(os.path.join(run_dir, "run.json"), encoding="utf-8-sig"))
    flags = [c.get("flag") for c in an["checkpoints"]]
    if an.get("run_hang") or "hang" in flags: overall = "hang"
    elif "changed" in flags: overall = "changed"
    elif flags and all(f == "pass" for f in flags): overall = "pass"
    elif not flags or all(f == "noshot" for f in flags): overall = "noshot"
    else: overall = "noref"
    em, txt = FLAG[overall]
    md = ["# تقرير اختبار Strikeforce %s" % em, "",
          "- **النسخة:** %s" % an["build"], "- **المسار:** %s (%s)" % (meta.get("route_title_ar", an["route"]), an["route"]),
          "- **الوقت:** %s → %s (توقيت الكويت)" % (meta.get("started"), meta.get("finished")),
          "- **النتيجة:** %s %s" % (em, txt),
          "- **تعليق؟** %s" % ("نعم — الصورة وقفت %d ثانية%s" % (an["longest_still_secs"], "، واللعبة طاحت" if an.get("process_died") else "") if an.get("run_hang") else "لا (أطول وقوف للصورة %d ثانية)" % an["longest_still_secs"]),
          "", "> " + an["metric_note_ar"], ""]
    if meta.get("notes_ar"):
        md += ["**ملاحظات التشغيل:**"] + ["- " + n for n in meta["notes_ar"]] + [""]
    body = ["<h1>تقرير اختبار Strikeforce %s</h1><table>" % em,
            "<tr><th>النسخة</th><td>%s</td></tr><tr><th>المسار</th><td>%s</td></tr><tr><th>الوقت</th><td>%s → %s (توقيت الكويت)</td></tr><tr><th>النتيجة</th><td>%s %s</td></tr>" % (
                html.escape(an["build"]), html.escape(meta.get("route_title_ar", an["route"])), meta.get("started"), meta.get("finished"), em, txt),
            "<tr><th>تعليق؟</th><td>%s</td></tr></table><p class='small'>%s</p>" % (
                ("نعم — الصورة وقفت %d ثانية" % an["longest_still_secs"]) if an.get("run_hang") else "لا (أطول وقوف للصورة %d ثانية)" % an["longest_still_secs"], html.escape(an["metric_note_ar"]))]
    if meta.get("notes_ar"):
        body.append("<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(n) for n in meta["notes_ar"]))
    for c in an["checkpoints"]:
        e, t = FLAG.get(c.get("flag"), ("", c.get("flag")))
        md += ["## %s %s — %s" % (e, c.get("title_ar", c["name"]), t), ""]
        body.append("<h2>%s %s — %s</h2>" % (e, html.escape(c.get("title_ar", c["name"])), t))
        if c.get("flag") == "noshot":
            continue
        md += ["![%s](shots/%s_marked.jpg)" % (c["name"], c["name"]), ""]
        body.append("<img class='big' src='shots/%s_marked.jpg'>" % c["name"])
        md += ["| القسم | الفحوصات | تطابق الصورة مع المرجع | تطابق الألوان مع RPCS3 | مع التشغيل السابق | الرسمات | السبب |", "|---|---|---|---|---|---|---|"]
        rows = []
        for s in c.get("sections", []):
            chk = "%s (%d/%d)" % (pct(s["checks_pct"]), s["checks_passed"], s["checks_measured"]) if s["checks_measured"] else "ما ينقاس بعد"
            dr = "—" if s.get("draws") is None else str(s["draws"]) + (" (كانت %d)" % s["draws_prev"] if "draws_prev" in s else "")
            mark = "✅" if s["pass"] else "❌"
            refp = pct(s.get("ref_match_pct")) + ((" (%s)" % s["ref_id"]) if s.get("ref_id") else "")
            md.append("| %s %s | %s | %s | %s | %s | %s | %s |" % (mark, s["ar"], chk, pct(s["match_golden_pct"]), refp, pct(s["match_prev_pct"]), dr, s["reason_ar"]))
            cls = "ok" if s["pass"] else "bad"
            rows.append("<tr><td class='%s'>%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                cls, mark, html.escape(s["ar"]), chk, pct(s["match_golden_pct"]), html.escape(refp), pct(s["match_prev_pct"]), dr, html.escape(s["reason_ar"])))
        body.append("<table><tr><th>القسم</th><th>الفحوصات</th><th>تطابق الصورة مع المرجع</th><th>تطابق الألوان مع RPCS3</th><th>مع التشغيل السابق</th><th>الرسمات</th><th>السبب</th></tr>%s</table>" % "".join(rows))
        diffs = []
        for s in c.get("sections", []):
            for ck in s["checks"]:
                if ck.get("stats") and ck.get("ref_stats"):
                    o = ck["stats"]; rs = ck["ref_stats"]
                    diffs.append("%s — %s: عندنا سطوع %d، تشبع %.2f، لون متوسط %s | RPCS3: %s" % (
                        s["ar"], ck["ar"], o["l50"], o["sat"], o["mean"],
                        "؛ ".join("سطوع %d، تشبع %.2f، لون متوسط %s" % (x["l50"], x["sat"], x["mean"]) for x in rs)))
        if diffs:
            md += ["", "**الفرق المقاس مع RPCS3 (نفس المربع في الصورة):**"] + ["- " + x for x in diffs]
            body.append("<p><b>الفرق المقاس مع RPCS3 (نفس المربع في الصورة):</b></p><ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(x) for x in diffs))
        md += ["", "صور الأقسام: " + " ".join("[%s](shots/%s_sec_%s.jpg)" % (s["ar"], c["name"], s["id"]) for s in c.get("sections", [])), ""]
        body.append("<div class='grid'>%s</div>" % "".join("<img src='shots/%s_sec_%s.jpg'>" % (c["name"], s["id"]) for s in c.get("sections", [])))
        extra = []
        if c.get("heat_golden"): extra.append("<a href='%s'>خريطة الفرق مع المرجع</a>" % c["heat_golden"])
        if c.get("heat_prev"): extra.append("<a href='%s'>خريطة الفرق مع التشغيل السابق (%s)</a>" % (c["heat_prev"], html.escape(an.get("previous_run") or "")))
        if extra:
            body.append("<p>%s</p>" % " | ".join(extra))
            md += ["- " + x for x in extra] + [""]
        body.append("<p class='small'>%s | رسمات الإطار: %s (غير مصنفة: %s)</p>" % (html.escape(c.get("window_title", "")), c.get("draws_total"), c.get("draws_other")))
    md += ["", "---", "الملفات: run.json، analysis.json، annotations.json، stderr.log، env_used.txt، timeline.csv"]
    open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    open(os.path.join(run_dir, "report.html"), "w", encoding="utf-8").write(PAGE % ("تقرير " + an["build"], "".join(body)))
    update_status(run_dir, an, meta, overall)
    return overall


def update_status(run_dir, an, meta, overall):
    st = load_status()
    when = meta.get("finished") or ""
    for i in st["issues"]:
        cps = [c for c in an["checkpoints"] if i["id"] in c.get("issues", []) and c.get("flag") != "noshot"]
        if i["id"] == "freeze" and an["route"] == "loading":
            cps = cps or an["checkpoints"]
        if not cps:
            continue
        res = None
        if i["id"] == "freeze":
            reached = any(c["name"].startswith("loading_") and c.get("flag") != "noshot" for c in an["checkpoints"])
            res = ("تعليق: الصورة وقفت %d ثانية" % an["longest_still_secs"]) if an.get("run_hang") else (
                "ما علّق خلال الاختبار" if reached or an["route"] == "village" else "ما وصل Now Loading")
            if an["route"] == "village" and not an.get("run_hang"):
                res = "ما علّق في القرية (%d ثانية)" % (meta.get("duration_secs") or 0)
        elif i.get("section"):
            c = cps[0]
            s = next((x for x in c.get("sections", []) if x["id"] == i["section"]), None)
            if s:
                p = "%s (%d/%d)" % (pct(s["checks_pct"]), s["checks_passed"], s["checks_measured"]) if s["checks_measured"] else "ما ينقاس بعد"
                res = "%s: فحوصات %s — %s" % (s["ar"], p, s["reason_ar"])
                if i["id"] in ("scarf", "shadows"):
                    res += " — الصورة تحتاج عين سعود"
        if res:
            i.update(last_build=an["build"], last_test=when, last_result=res, last_run=os.path.basename(run_dir))
    save_status(st)


if __name__ == "__main__":
    if sys.argv[1:] == ["--status"]:
        st = load_status(); save_status(st)
    else:
        print(write_report(sys.argv[1]))

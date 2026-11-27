#!/usr/bin/env python3
"""testloop.py - Strikeforce one-click test loop (ONE entry point).

  python testloop.py                       Arabic menu
  python testloop.py all [--build B|latest] [--route village] [--env FILE]
                                           run + compare + mark + report + status, in one go
  python testloop.py run   ...             same as 'all'
  python testloop.py analyze <run folder>  redo compare/mark/report for an old run
  python testloop.py status                print the tracker
  python testloop.py status set <id> <state_ar...>   change an issue's state (people only)
  python testloop.py promote <run folder>  copy that run's shots to golden/<route>/ (needs Saud's OK)
  python testloop.py builds | routes

Rules built in: test copy only; waits until no other MyGameRecomp is running (never kills
another pid, never touches Saud's game); one window titled [TEST-SALEM], pushed to the
back (winplace.ps1); PAD_NO_XINPUT=1 so Saud's controller cannot drive it; input only
through PAD_FILE; no press while a movie (cellSail) is open or the frame is letterboxed;
PrintWindow captures only (sfauto/shot.ps1); closes only its own pid. No network, no
browser, no installs. FACES_CTL is used read-only for the draw list ('list' command).
"""
import argparse, ctypes, datetime, glob, json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
SF = os.path.dirname(HERE)                      # ...\sfauto
ROOT = os.path.dirname(SF)                      # ...\ps3recomp-v020-test
EXES = os.path.join(SF, "exe_copies")
RUNS = os.path.join(HERE, "runs")
ELF = r"<SF_ELF>"
DEV_FLASH = r"<PS3_DEV_FLASH>"   # read-only, same as every launcher
TITLE = "[TEST-SALEM] ps3recomp"
LIVE_EVERY = 20
NOWIN = 0x08000000                               # CREATE_NO_WINDOW for helper powershells
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SHAPE = os.environ.get("TESTLOOP_SHAPE", "1") == "1"   # pre-shape Arabic for consoles without bidi


def say(ar, en=""):
    from arabic_shape import shape_visual
    line = (shape_visual(ar) if SHAPE else ar) + (("   | " + en) if en else "")
    print(line, flush=True)
    if LOG:
        LOG.write("%s  %s | %s\n" % (time.strftime("%H:%M:%S"), ar, en)); LOG.flush()


LOG = None

# ---------------------------------------------------------------- windows helpers
if os.name == "nt":
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    _ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def window_titles():
    """pid -> longest visible top-level window title."""
    res = {}
    if os.name != "nt":
        return res

    def cb(h, l):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n > 0:
                p = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                b = ctypes.create_unicode_buffer(n + 1); user32.GetWindowTextW(h, b, n + 1)
                if len(b.value) > len(res.get(p.value, "")):
                    res[p.value] = b.value
        return True
    user32.EnumWindows(_ENUM(cb), 0)
    return res


def game_pids():
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq MyGameRecomp.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, errors="replace", creationflags=NOWIN).stdout
    except Exception:
        return []
    pids = []
    for l in out.splitlines():
        m = re.match(r'"MyGameRecomp\.exe","(\d+)"', l, re.I)
        if m:
            pids.append(int(m.group(1)))
    return pids


def others_running(alongside_saud, own=None):
    t = window_titles(); busy = []
    for p in game_pids():
        if p == own:
            continue
        title = t.get(p, "")
        is_test = "[TEST-SALEM]" in title or title == ""
        if is_test or not alongside_saud:
            busy.append((p, title or "(no window yet)"))
    return busy


def draws_of(title):
    m = re.search(r"draws: (\d+)", title or "")
    return int(m.group(1)) if m else None


def shot(pid, out_png):
    """PrintWindow via sfauto/shot.ps1 -> path of the client-area PNG, or None."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(SF, "shot.ps1"),
                            "-ProcId", str(pid), "-Out", out_png], capture_output=True, text=True, timeout=40, creationflags=NOWIN)
    except Exception:
        return None
    cp = out_png[:-4] + "_client.png"
    if os.path.exists(cp):
        try:
            os.replace(cp, out_png)          # keep the client area under the plain name (our own file)
        except OSError:
            return None
        return out_png
    return out_png if os.path.exists(out_png) and r.stdout.startswith("ok") else None


# ---------------------------------------------------------------- builds / routes
def builds():
    out = []
    for d in glob.glob(os.path.join(EXES, "*")):
        e = os.path.join(d, "MyGameRecomp.exe")
        if os.path.exists(e):
            out.append((os.path.getmtime(e), os.path.basename(d)))
    return [b for _, b in sorted(out, reverse=True)]


def routes():
    return sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(HERE, "routes", "*.json")))


def exe_supports(exe, keys):
    data = open(exe, "rb").read()
    return {k: k.encode() in data for k in keys}


# ---------------------------------------------------------------- the run
class Runner:
    def __init__(self, build, route, envfile=None, alongside=False, wait_max_min=90):
        self.build, self.route_name = build, route
        self.route = json.load(open(os.path.join(HERE, "routes", route + ".json"), encoding="utf-8-sig"))
        self.envfile, self.alongside, self.wait_max = envfile, alongside, wait_max_min * 60
        self.exe = os.path.join(EXES, build, "MyGameRecomp.exe")
        ts = time.strftime("%Y%m%d-%H%M%S")
        self.rd = os.path.join(RUNS, "%s_%s_%s" % (ts, build, route))
        for s in ("shots", "live", "cwd"):
            os.makedirs(os.path.join(self.rd, s), exist_ok=True)
        self.pad = os.path.join(self.rd, "pad.txt"); self.ctl = os.path.join(self.rd, "ctl.txt")
        self.p = None; self.t0 = None; self.notes = []; self.cps = []; self.died = False
        self.err_pos = 0; self.out_pos = 0; self.sail_open = 0; self.next_live = 0
        self.timeline = open(os.path.join(self.rd, "timeline.csv"), "w", encoding="utf-8")
        self.timeline.write("t_s,title,draws\n")

    # --- waiting for a quiet machine
    def wait_quiet(self):
        t_start = time.time(); quiet_since = None; shown = 0
        while True:
            busy = others_running(self.alongside)
            if busy:
                quiet_since = None
                if time.time() - shown > 60:
                    say("أنتظر: فيه نافذة لعبة ثانية شغالة (%s)" % ", ".join(str(p) for p, _ in busy),
                        "waiting for other game window(s): " + "; ".join("%d %s" % b for b in busy)); shown = time.time()
                if time.time() - t_start > self.wait_max:
                    return False
            else:
                quiet_since = quiet_since or time.time()
                if time.time() - quiet_since >= 30:   # longer than other workers' 12 s, so they go first
                    return True
            time.sleep(2)

    def prepare_state(self):
        tmpl_name = self.route.get("state_template", "state_faces")
        tmpl = os.path.join(HERE, "state_template")
        if not os.path.isdir(tmpl):
            say("أول مرة: أنسخ ملف الحفظ من %s" % tmpl_name, "first run: copying save state from sfauto\\" + tmpl_name)
            shutil.copytree(os.path.join(SF, tmpl_name), tmpl)
        work = os.path.join(HERE, "state_work")
        if os.path.isdir(work):
            shutil.rmtree(work)              # our own scratch copy, rebuilt every run so every run starts the same
        shutil.copytree(tmpl, work)
        return work

    def env(self, state):
        e = {k: v for k, v in os.environ.items() if not k.startswith(("PAD_", "FACES_CTL", "PS3_"))}
        e.update({"PS3_VFS_ROOT": os.path.join(ROOT, "vfs", "dev_bdvd"),
                  "PS3_HDD0_ROOT": os.path.join(state, "hdd0"), "PS3_HDD1_ROOT": os.path.join(state, "hdd1"),
                  "PS3_GAMEDATA_ROOT": os.path.join(state, "gamedata"), "PS3_DEV_FLASH": DEV_FLASH,
                  "PS3_HLE_TOP": "0", "PS3_TITLE": TITLE, "SPU_INTERP_UNLIFTED": "1", "SPU_INTERP_MISS": "1",
                  "OSK_AUTO_TEXT": "Saud", "SF_PADMAP": os.path.join(ROOT, "Strikeforce_buttons.ini"),
                  "PAD_NO_XINPUT": "1", "PAD_FILE": self.pad, "FACES_CTL": self.ctl,
                  "PS3_MILESTONE_OUT": os.path.join(self.rd, "milestones.txt")})
        extra = {}
        if self.envfile:
            for l in open(self.envfile, encoding="utf-8-sig"):
                l = l.strip()
                if l and not l.startswith("#") and "=" in l:
                    k, v = l.split("=", 1); extra[k.strip()] = v.strip()
            for k in ("PAD_NO_XINPUT", "PS3_TITLE", "PAD_FILE"):   # safety keys cannot be overridden
                extra.pop(k, None)
            e.update(extra)
        with open(os.path.join(self.rd, "env_used.txt"), "w", encoding="utf-8") as f:
            for k in sorted(set(e) - set(os.environ) | set(extra) | {"PS3_TITLE", "PAD_NO_XINPUT"}):
                f.write("%s=%s\n" % (k, e[k]))
        return e

    def launch(self, env):
        for f in (self.pad, self.ctl):
            open(f, "w").close()
        self.so = open(os.path.join(self.rd, "stdout.log"), "wb"); self.se = open(os.path.join(self.rd, "stderr.log"), "wb")
        self.p = subprocess.Popen([self.exe, ELF], cwd=os.path.join(self.rd, "cwd"), env=env, stdout=self.so, stderr=self.se)
        self.t0 = time.time()
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File",
                          os.path.join(SF, "winplace.ps1"), "-ProcId", str(self.p.pid)], creationflags=NOWIN)
        say("شغّلت نافذة الاختبار (رقم %d)" % self.p.pid, "launched [TEST-SALEM] pid %d" % self.p.pid)

    def close(self):
        if self.p and self.p.poll() is None:
            self.p.kill(); self.p.wait(timeout=30)        # our own pid only
            say("سكّرت نافذة الاختبار", "closed own pid %d" % self.p.pid)
        for f in ("so", "se"):
            try: getattr(self, f).close()
            except Exception: pass

    # --- monitoring
    def elapsed(self):
        return time.time() - self.t0

    def alive(self):
        if self.p.poll() is not None:
            if not self.died:
                self.died = True; self.notes.append("اللعبة طلعت/طاحت بعد %d ثانية (رمز %s)" % (self.elapsed(), self.p.returncode))
                say("اللعبة طاحت!", "process exited rc=%s" % self.p.returncode)
            return False
        return True

    def title(self):
        return window_titles().get(self.p.pid, "")

    def scan_stdout(self):
        try:
            with open(os.path.join(self.rd, "stdout.log"), "rb") as f:
                f.seek(self.out_pos); data = f.read(); self.out_pos += len(data)
        except OSError:
            return
        txt = data.decode("utf-8", "replace")
        self.sail_open += txt.count("[cellSail] PlayerStart(") - txt.count("[cellSail] PlayerFinalize(")
        self.sail_open = max(0, self.sail_open)

    def tick(self):
        """called often: live samples + timeline."""
        if self.elapsed() >= self.next_live and self.alive():
            self.next_live = self.elapsed() + LIVE_EVERY
            t = self.title(); self.timeline.write('%d,"%s",%s\n' % (self.elapsed(), t.replace('"', "'"), draws_of(t) or ""))
            self.timeline.flush()
            p = os.path.join(self.rd, "live", "live_%04d.png" % self.elapsed())
            if shot(self.p.pid, p):
                try:
                    from PIL import Image
                    im = Image.open(p).convert("RGB"); im.thumbnail((320, 320)); im.save(p)
                except Exception:
                    pass

    def sleep(self, secs):
        end = time.time() + secs
        while time.time() < end and self.alive():
            self.tick(); time.sleep(min(0.5, max(0, end - time.time())))

    def cutscene(self):
        """True if a movie is open or the current frame is letterboxed."""
        self.scan_stdout()
        if self.sail_open > 0:
            return "movie"
        p = os.path.join(self.rd, "guard.png")
        if shot(self.p.pid, p):
            try:
                import numpy as np
                from PIL import Image
                a = np.asarray(Image.open(p).convert("L"), dtype=np.float32); h = a.shape[0]; k = max(4, int(h * 0.07))
                top, bot, mid = a[:k], a[-k:], a[k:-k]
                if top.mean() < 6 and bot.mean() < 6 and top.std() < 3 and bot.std() < 3 and mid.mean() > 20:
                    return "letterbox"
            except Exception:
                pass
        return None

    def press(self, step):
        if step.get("guard", True):
            waited = 0
            while True:
                c = self.cutscene()
                if not c:
                    break
                if waited == 0:
                    say("فيه مشهد سينمائي، أنتظر بدون ضغط", "cutscene (%s): holding input" % c)
                if waited > step.get("guard_timeout", 300):
                    self.notes.append("ما ضغطت %s: المشهد ما خلص" % step.get("mask")); return False
                self.sleep(2); waited += 2
        line = "%s %d" % (step["mask"], step.get("n", 40))
        if "lx" in step:
            line += " %d %d" % (step["lx"], step["ly"])
        with open(self.pad, "w") as f:
            f.write(line)
        for _ in range(100):                       # the game empties the file when it takes the press
            if os.path.getsize(self.pad) == 0:
                break
            self.sleep(0.1)
        else:
            self.notes.append("الضغطة %s ما انقرت خلال 10 ثواني" % step["mask"])
        say("ضغطت %s — %s" % (step["mask"], step.get("why", "")), "press %s t=%ds %s" % (step["mask"], self.elapsed(), step.get("why", "")))
        return True

    def wait_draws(self, step, below=False):
        need = step.get("hold", 1); t_end = time.time() + step.get("timeout", 300); since = None
        while time.time() < t_end and self.alive():
            d = draws_of(self.title())
            ok = d is not None and ((d < step["max"]) if below else (d >= step["min"]))
            if ok:
                since = since or time.time()
                if time.time() - since >= need:
                    say("وصلنا (عدد الرسمات %s)" % d, "draws condition met: %s" % d); return True
            else:
                since = None
            self.sleep(1)
        self.notes.append("ما تحقق شرط الرسمات (%s)" % step.get("why", "")); return False

    def fcl_list(self, name):
        """ask the exe for one frame's draw list and cut it out of stderr."""
        with open(self.ctl, "w") as f:
            f.write("list\n")
        start = self.err_pos = os.path.getsize(os.path.join(self.rd, "stderr.log"))
        buf = b""; t_end = time.time() + 15
        while time.time() < t_end and self.alive():
            time.sleep(0.5)
            with open(os.path.join(self.rd, "stderr.log"), "rb") as f:
                f.seek(start); buf = f.read()
            if b"---- end of listed frame" in buf:
                break
        lines = [l for l in buf.decode("utf-8", "replace").splitlines() if l.startswith("[FCL]")]
        if lines:
            with open(os.path.join(self.rd, "shots", name + "_fcl.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        return len(lines)

    def checkpoint(self, step):
        name = step["name"]
        if not self.alive():
            self.cps.append({"name": name, "title_ar": step.get("title_ar", name), "issues": step.get("issues", [])}); return
        a = os.path.join(self.rd, "shots", name + ".png"); b = os.path.join(self.rd, "shots", name + "_b.png")
        t = self.title(); ok = shot(self.p.pid, a)
        time.sleep(1.2); shot(self.p.pid, b)
        n = self.fcl_list(name) if self.fcl_ok else 0
        self.cps.append({"name": name, "title_ar": step.get("title_ar", name), "issues": step.get("issues", []),
                         "window_title": t, "t": int(self.elapsed()), "fcl_lines": n})
        say("صورة: %s %s" % (step.get("title_ar", name), "" if ok else "(فشلت)"), "checkpoint %s t=%ds %s fcl=%d" % (name, self.elapsed(), t, n))

    def walk(self, step):
        for i in range(step.get("repeat", 1)):
            if not self.alive(): return
            self.press(dict(step, mask="0x10000"))
            self.sleep(step.get("n", 240) / 60.0 + 0.5)
            d = draws_of(self.title())
            if step.get("until_draws_below") and d is not None and d < step["until_draws_below"]:
                say("الرسمات نزلت (%d) — يمكن شاشة تحميل" % d, "draws dropped to %d" % d); return

    def run(self):
        global LOG
        LOG = open(os.path.join(self.rd, "run_log.txt"), "w", encoding="utf-8")
        sup = exe_supports(self.exe, ["PAD_NO_XINPUT", "PAD_FILE", "FACES_CTL", "PS3_TITLE"])
        if not (sup["PAD_NO_XINPUT"] and sup["PAD_FILE"] and sup["PS3_TITLE"]):
            say("هالنسخة ما تدعم التحكم الآمن (PAD_NO_XINPUT) — ما أشغلها", "exe lacks PAD_NO_XINPUT/PAD_FILE/PS3_TITLE: refusing")
            return None
        self.fcl_ok = sup["FACES_CTL"]
        if not self.fcl_ok:
            self.notes.append("هالنسخة ما فيها قائمة الرسمات (FACES_CTL): فحوصات الرسمات ما تنقاس")
        meta = {"build": self.build, "route": self.route_name, "route_title_ar": self.route.get("title_ar"), "exe": self.exe,
                "route_verified": self.route.get("verified"), "live_every": LIVE_EVERY,
                "queued": time.strftime("%Y-%m-%d %H:%M:%S")}
        say("أنتظر الجهاز يفضى من أي اختبار ثاني...", "waiting for a quiet machine")
        for attempt in range(3):
            if not self.wait_quiet():
                self.notes.append("انتهى وقت الانتظار: نافذة ثانية ظلت شغالة"); meta["aborted"] = "wait timeout"; break
            state = self.prepare_state(); env = self.env(state)
            if others_running(self.alongside):
                continue
            self.launch(env)
            time.sleep(6)
            clash = others_running(self.alongside, own=self.p.pid)
            if clash:
                say("نافذة ثانية بدت معانا — أسكّر نافذتي وأعيد الانتظار", "another window started with us: closing ours and re-queueing")
                self.close(); self.p = None; continue
            break
        if self.p:
            meta["started"] = time.strftime("%Y-%m-%d %H:%M:%S"); meta["pid"] = self.p.pid
            try:
                for st in self.route["steps"]:
                    if not self.alive() or self.elapsed() > self.route.get("max_secs", 900):
                        break
                    do = st["do"]
                    if do == "wait": self.sleep(max(0, st["secs"]))
                    elif do == "press": self.press(dict(st, guard=st.get("guard", True)))
                    elif do == "wait_draws": self.wait_draws(st)
                    elif do == "wait_draws_below": self.wait_draws(st, below=True)
                    elif do == "shot": self.checkpoint(st)
                    elif do == "walk": self.walk(st)
                # checkpoints the route never reached still get a row in the report
                done = {c["name"] for c in self.cps}
                for st in self.route["steps"]:
                    if st["do"] == "shot" and st["name"] not in done:
                        self.cps.append({"name": st["name"], "title_ar": st.get("title_ar", st["name"]), "issues": st.get("issues", [])})
            finally:
                meta["duration_secs"] = int(self.elapsed())
                self.close()
        meta.update(finished=time.strftime("%Y-%m-%d %H:%M:%S"), checkpoints=self.cps, notes_ar=self.notes,
                    process_died=self.died)
        try: os.remove(os.path.join(self.rd, "guard.png"))
        except OSError: pass
        with open(os.path.join(self.rd, "run.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        self.timeline.close()
        return self.rd if self.p else None


def milestone_diff(rd, route):
    """regress.py (ps3recomp tools, read-only import) diff vs golden/<route>/milestones.txt."""
    cur = os.path.join(rd, "milestones.txt"); gold = os.path.join(HERE, "golden", route, "milestones.txt")
    if not os.path.exists(cur):
        return None
    try:
        sys.path.insert(0, os.path.join(ROOT, "ps3recomp", "tools"))
        import regress
        c = regress.parse_log(cur)
        res = {"keys": len(c[0])}
        if os.path.exists(gold):
            fails, notes = regress.diff(regress.parse_log(gold), c)
            res.update(fails=fails[:40], notes=notes[:40])
        with open(os.path.join(rd, "milestones_diff.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        return res
    except Exception as ex:
        return {"error": str(ex)}


def analyze_all(rd):
    import analyze, mark, report
    an = analyze.analyze(rd)
    md = milestone_diff(rd, an["route"])
    if md and md.get("fails"):
        meta = json.load(open(os.path.join(rd, "run.json"), encoding="utf-8-sig"))
        meta.setdefault("notes_ar", []).append("سجل المراحل (regress.py): %d فرق عن المرجع" % len(md["fails"]))
        json.dump(meta, open(os.path.join(rd, "run.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mark.mark_run(rd)
    overall = report.write_report(rd)
    return an, overall


def cmd_all(build, route, envfile=None, alongside=False):
    if build in (None, "", "latest"):
        build = builds()[0]
    if build not in builds():
        say("النسخة مو موجودة: %s" % build, "unknown build"); return 2
    if route not in routes():
        say("المسار مو موجود: %s" % route, "unknown route"); return 2
    say("اختبار: النسخة %s، المسار %s" % (build, route), "test: build %s route %s" % (build, route))
    rd = Runner(build, route, envfile, alongside).run()
    if not rd:
        say("ما تم التشغيل", "run did not start"); return 1
    say("أحلل الصور وأكتب التقرير...", "analysing")
    an, overall = analyze_all(rd)
    for c in an["checkpoints"]:
        secs = " ".join("%s:%s" % (s["id"], ("%d%%" % s["checks_pct"]) if s["checks_pct"] is not None else "-") for s in c.get("sections", []))
        say("%s ← %s" % (c.get("title_ar", c["name"]), c.get("flag")), "%s %s %s" % (c["name"], c.get("flag"), secs))
    say("التقرير جاهز:", os.path.join(rd, "report.html"))
    print(os.path.join(rd, "report.html"))
    return 0


def cmd_status(args):
    import report
    st = report.load_status()
    if args and args[0] == "set" and len(args) >= 3:
        for i in st["issues"]:
            if i["id"] == args[1]:
                i["state_ar"] = " ".join(args[2:]); i["state_set"] = time.strftime("%Y-%m-%d %H:%M")
        report.save_status(st)
    else:
        report.save_status(st)
    for i in st["issues"]:
        say("• %s: %s — آخر نتيجة: %s" % (i["title_ar"], i.get("state_ar", ""), i.get("last_result", "—")), i["id"])


def cmd_promote(rd):
    meta = json.load(open(os.path.join(rd, "run.json"), encoding="utf-8-sig"))
    g = os.path.join(HERE, "golden", meta["route"]); os.makedirs(g, exist_ok=True)
    for c in meta["checkpoints"]:
        p = os.path.join(rd, "shots", c["name"] + ".png")
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(g, c["name"] + ".png"))
    if os.path.exists(os.path.join(rd, "milestones.txt")):
        shutil.copy2(os.path.join(rd, "milestones.txt"), os.path.join(g, "milestones.txt"))
    open(os.path.join(g, "SOURCE.txt"), "w", encoding="utf-8").write("promoted from %s on %s\n" % (rd, time.strftime("%Y-%m-%d %H:%M")))
    say("صارت صور هالتشغيل هي المرجع لمسار %s" % meta["route"], "promoted to golden")


def menu():
    bl, rl = builds(), routes()
    say("============ أداة اختبار Strikeforce ============")
    say("1) اختبار آخر نسخة (%s) في القرية" % bl[0])
    say("2) اختار النسخة والمسار")
    say("3) حالة المشاكل")
    say("0) خروج")
    ch = input("> ").strip()
    if ch == "1":
        return cmd_all("latest", "village")
    if ch == "2":
        for i, b in enumerate(bl[:15], 1):
            say("%d) %s" % (i, b))
        bi = input("رقم النسخة > ").strip()
        b = bl[int(bi) - 1] if bi.isdigit() and 0 < int(bi) <= len(bl) else bl[0]
        for i, r in enumerate(rl, 1):
            rt = json.load(open(os.path.join(HERE, "routes", r + ".json"), encoding="utf-8-sig"))
            say("%d) %s" % (i, rt.get("title_ar", r)), r)
        ri = input("رقم المسار > ").strip()
        r = rl[int(ri) - 1] if ri.isdigit() and 0 < int(ri) <= len(rl) else "village"
        return cmd_all(b, r)
    if ch == "3":
        return cmd_status([])
    return 0


def main():
    if len(sys.argv) == 1:
        return menu()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["all", "run", "analyze", "status", "promote", "builds", "routes"])
    ap.add_argument("rest", nargs="*")
    ap.add_argument("--build", default="latest"); ap.add_argument("--route", default="village")
    ap.add_argument("--env", default=None); ap.add_argument("--alongside-saud", action="store_true",
                                                            help="run even while Saud's own (non-test) game window is open")
    a = ap.parse_args()
    if a.cmd in ("all", "run"):
        return cmd_all(a.build, a.route, a.env, a.alongside_saud)
    if a.cmd == "analyze":
        an, overall = analyze_all(a.rest[0]); print(overall); return 0
    if a.cmd == "status":
        return cmd_status(a.rest)
    if a.cmd == "promote":
        return cmd_promote(a.rest[0])
    if a.cmd == "builds":
        print("\n".join(builds()))
    if a.cmd == "routes":
        print("\n".join(routes()))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)

# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
# rdc_capture_burst.py -- run the TEST COPY exe under RenderDoc (renderdoccmd capture), boot -> title -> load
# the save -> fire F12 repeatedly through the load->spawn window so one of the captures lands on the
# first frames of the stage.  Copy of the 2026-11-28 burst script (see PROGRESS.md "weaknesses": the
# F12 timing is still a guess -- the capture lands 1-2 frames after the key press).  Starts only its own
# game/renderdoccmd; closes only its own game pid.  Use via: python sfauto/tools/sf_pipeline.py capture
# 1807trace RenderDoc village capture (TEST COPY only).
# Launch via Invoke-CimMethod Win32_Process Create.
# Hooks MyGameRecomp.exe with renderdoccmd capture (D3D12). Does not open qrenderdoc.
# Closes only our own game pid.
import os, sys, time, json, re, shutil, subprocess, ctypes, ctypes.wintypes as wt

# Paths come from the environment or the current test-copy root. No personal defaults.
T = os.environ.get("SF_TEST_ROOT") or os.environ.get("SF_ROOT") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SF = os.path.join(T, "sfauto")
R = os.path.join(SF, os.environ.get("SF_FIX_DIR", "fix1807trace"))
PAD = os.path.join(SF, "ringwatch_work", "pad.txt")
EXE = os.environ.get("SF_TEST_EXE") or os.path.join(SF, "exe_copies", "1807trace", "MyGameRecomp.exe")
if not os.path.isfile(EXE):
    EXE = os.path.join(SF, "exe_copies", "1805", "MyGameRecomp.exe")
    BUILD = "1805"
else:
    BUILD = os.environ.get("SF_BUILD_NAME", "1807trace")
# User-supplied legal dump only. Never ship or default to a personal EBOOT path.
ELF = os.environ.get("SF_EBOOT_ELF") or os.environ.get("PS3_EBOOT") or ""
RDCMD = os.environ.get("SF_RENDERDOC_CMD") or os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "RenderDoc", "renderdoccmd.exe")
CAPDIR = os.path.join(SF, "captures")
os.makedirs(CAPDIR, exist_ok=True)
os.makedirs(R, exist_ok=True)

TS = time.strftime("%Y%m%d-%H%M%S")
RD = os.path.join(R, "run_" + TS + "_rdc")
os.makedirs(os.path.join(RD, "shots"), exist_ok=True)
TEMPLATE = os.path.join(CAPDIR, "shadowfp_%s_%s" % (BUILD, TS))
LAUNCH_LOG = TEMPLATE + "_launch.log"
LOGPREFIX = os.path.join(T, "play_logs", "b%s_rdc_%s" % (BUILD, TS))

NOWIN = 0x08000000
LOG = open(os.path.join(RD, "run_log.txt"), "a", encoding="utf-8")

def say(s):
    line = time.strftime("%H:%M:%S ") + s
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
_ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

def titles():
    res = {}
    def cb(h, l):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n > 0:
                p = wt.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, b, n + 1)
                if len(b.value) > len(res.get(p.value, "")):
                    res[p.value] = b.value
        return True
    user32.EnumWindows(_ENUM(cb), 0)
    return res

def hwnds_for(pid):
    found = []
    def cb(h, l):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            b = ctypes.create_unicode_buffer(n + 1)
            if n > 0:
                user32.GetWindowTextW(h, b, n + 1)
            found.append((h, b.value if n > 0 else ""))
        return True
    user32.EnumWindows(_ENUM(cb), 0)
    return found

def ps(cmd, timeout=60):
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, text=True, errors="replace", timeout=timeout,
        creationflags=NOWIN).stdout

def game_procs():
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='MyGameRecomp.exe'\" | % { \"$($_.ProcessId),$($_.ParentProcessId)\" }")
    return [tuple(int(x) for x in l.split(",")) for l in out.split() if "," in l]

def alive(pid):
    return any(p == pid for p, _ in game_procs())

def draws(pid):
    m = re.search(r"draws: (\d+)", titles().get(pid, ""))
    return int(m.group(1)) if m else None

def shot(pid, name):
    out = os.path.join(RD, "shots", name + ".png")
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         os.path.join(SF, "fix1803_scissor", "shot_pw.ps1"),
         "-ProcId", str(pid), "-Out", out],
        capture_output=True, text=True, timeout=40, creationflags=NOWIN)
    cp = out[:-4] + "_client.png"
    if os.path.exists(cp):
        os.replace(cp, out)
    ok = os.path.exists(out)
    say("shot %s %s (draws=%s)" % (name, "ok" if ok else "FAILED", draws(pid)))
    return out if ok else None

STDOUT = None
STDERR = None
F12_DONE = []  # list of (why, time, draws, frame)

def latest_frame():
    """Best-effort: last SHADOW_TRACE_FRAME in our stderr (may lag or be missing)."""
    path = STDERR
    if not path or not os.path.exists(path):
        return None, None
    try:
        # read only the tail
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 512000), os.SEEK_SET)
            txt = f.read().decode("utf-8", "replace")
    except OSError:
        return None, None
    fr = sfp = None
    for ln in txt.splitlines():
        if "SHADOW_TRACE_FRAME v1 frame=" not in ln:
            continue
        m = re.search(r"frame=(\d+).*shadow_fp_draws=(\d+)", ln)
        if m:
            fr, sfp = int(m.group(1)), int(m.group(2))
    return fr, sfp

def press_f12(pid, why):
    if len(F12_DONE) >= 36:
        say("F12 skipped (already 3): " + why)
        return False
    wins = hwnds_for(pid)
    hwnd = None
    for h, title in wins:
        if title:
            hwnd = h
            break
    if hwnd is None and wins:
        hwnd = wins[0][0]
    if hwnd:
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            fg = user32.GetForegroundWindow()
            pid_fg = wt.DWORD()
            tid_fg = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid_fg))
            tid_tg = user32.GetWindowThreadProcessId(hwnd, None)
            if tid_fg and tid_tg and tid_fg != tid_tg:
                user32.AttachThreadInput(tid_fg, tid_tg, True)
            user32.SetForegroundWindow(hwnd)
            if tid_fg and tid_tg and tid_fg != tid_tg:
                user32.AttachThreadInput(tid_fg, tid_tg, False)
        except Exception as e:
            say("F12 focus warn: %s" % e)
        time.sleep(0.05)
    VK_F12 = 0x7B
    user32.keybd_event(VK_F12, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(VK_F12, 0, 2, 0)
    fr, sfp = latest_frame()
    d = draws(pid)
    F12_DONE.append({"why": why, "t": time.strftime("%H:%M:%S"), "draws": d, "frame": fr, "sfp": sfp})
    say("F12 %s (draws=%s frame=%s sfp=%s n=%d)" % (why, d, fr, sfp, len(F12_DONE)))
    return True

def sail_open():
    if not STDOUT or not os.path.exists(STDOUT):
        return 0
    txt = open(STDOUT, "rb").read().decode("utf-8", "replace")
    return max(0, txt.count("[cellSail] PlayerStart(") - txt.count("[cellSail] PlayerFinalize("))

def letterbox(pid):
    p = shot(pid, "_guard")
    if not p:
        return False
    try:
        import numpy as np
        from PIL import Image
        a = np.asarray(Image.open(p).convert("L"), dtype=np.float32)
        k = max(4, int(a.shape[0] * 0.07))
        top, bot, mid = a[:k], a[-k:], a[k:-k]
        return top.mean() < 6 and bot.mean() < 6 and top.std() < 3 and bot.std() < 3 and mid.mean() > 20
    except Exception:
        return False

def press(pid, mask, n, why, lx=None, ly=None, guard=True):
    if guard:
        w = 0
        while sail_open() > 0 or letterbox(pid):
            if w == 0:
                say("cutscene/movie: holding input")
            if w > 300 or not alive(pid):
                say("guard timeout, skip " + why)
                return False
            time.sleep(2)
            w += 2
    line = "%s %d" % (mask, n) + ("" if lx is None else " %d %d" % (lx, ly))
    open(PAD, "w").write(line)
    for _ in range(100):
        if os.path.getsize(PAD) == 0:
            break
        time.sleep(0.1)
    else:
        say("press not consumed in 10 s: " + line)
    say("press %s (%s)" % (line, why))
    return True

def maybe_f12_from_frame(pid):
    """Fire at most one F12 per expected window, based on SHADOW_TRACE_FRAME if present."""
    return  # burst mode: handled in the loading loop
    fr, sfp = latest_frame()
    windows = [
        ("frame9682", 9660, 9750),
        ("frame10375", 10350, 10450),
        ("frame14513", 14480, 14600),
    ]
    already = {x["why"] for x in F12_DONE}
    for name, a, b in windows:
        if name in already:
            continue
        if a <= fr <= b:
            press_f12(pid, name)
            return

def wait_draws(pid, mn, hold, timeout):
    t_end = time.time() + timeout
    since = None
    t_high = None
    last_f12_poll = 0
    while time.time() < t_end and alive(pid):
        d = draws(pid)
        now = time.time()
        if now - last_f12_poll >= 0.25:
            maybe_f12_from_frame(pid)
            last_f12_poll = now
            # timing fallback if logs have no frame yet
            if d is not None and d >= mn:
                if t_high is None:
                    t_high = now
                elapsed = now - t_high
                already = {x["why"] for x in F12_DONE}
                pass
        if d is not None and d >= mn:
            since = since or time.time()
            if time.time() - since >= hold:
                say("draws >= %d held (%s)" % (mn, d))
                return True
        else:
            since = None
        time.sleep(0.25)
    say("wait_draws timed out (last %s)" % draws(pid))
    return False


# ---- gate
if not os.path.isfile(EXE):
    say("no 1807trace or 1805 exe"); sys.exit(2)
if not os.path.isfile(RDCMD):
    say("renderdoccmd missing"); sys.exit(2)
busy = game_procs()
if busy:
    say("another MyGameRecomp is running %s: NOT launching" % busy)
    sys.exit(3)

bk = os.path.join(R, "backup_rdc_" + TS)
os.makedirs(bk, exist_ok=True)
for sub in ("gamedata", "hdd0"):
    s = os.path.join(SF, "state_ringwatch", sub)
    if os.path.isdir(s):
        shutil.copytree(s, os.path.join(bk, "state_ringwatch", sub))
say("backup -> " + bk)
say("exe %s (%s)" % (EXE, BUILD))
say("capture template %s" % TEMPLATE)

before_logs = set(os.listdir(os.path.join(T, "play_logs")))
before_caps = set(os.listdir(CAPDIR)) if os.path.isdir(CAPDIR) else set()

# Same env as PLAY_Strikeforce_1807trace.bat (defaults included).
env = {
    "PAD_NO_XINPUT": "1",
    "PS3_VFS_ROOT": os.path.join(T, r"vfs\dev_bdvd"),
    "PS3_HDD0_ROOT": os.path.join(SF, r"state_ringwatch\hdd0"),
    "PS3_HDD1_ROOT": os.path.join(SF, r"state_ringwatch\hdd1"),
    "PS3_GAMEDATA_ROOT": os.path.join(SF, r"state_ringwatch\gamedata"),
    "PS3_DEV_FLASH": os.environ.get("PS3_DEV_FLASH") or os.environ.get("SF_DEV_FLASH") or "",
    "PS3_TITLE": "[TEST-1807trace] ps3recomp 1807trace RenderDoc",
    "PS3_HLE_TOP": "0",
    "SPU_INTERP_UNLIFTED": "1",
    "SPU_INTERP_MISS": "1",
    "OSK_AUTO_TEXT": "Saud",
    "SF_PADMAP": os.path.join(T, "Strikeforce_buttons.ini"),
    "PAD_FILE": PAD,
    "SF_HLE_LRLOG": "1",
    "SF_HLE_LRLOG_DUMP": "5",
    "PS3_FSLOG": "1",
    "SF_SPURSFIX": "1",
    "SF_GATEFIX": "1",
    "SF_HIDPI": "1",
    "D3D12_DROP_STATS_EVERY": "300",
    "RSX_CENSUS": "60,2",
    "FPS_CAP": "0",
    "SF_SHLOG": "1",
    "SF_LWCOND": "1",
    "SF_ATRAC_LOG": "0",
    "SF_FSTRACE": "1",
    "SF_STUBHIT": "1",
    "SF_SHADOW_TRACE": "1",
}
if not ELF or not os.path.isfile(ELF):
    say("set SF_EBOOT_ELF to your own legally dumped EBOOT.elf"); sys.exit(2)
if not env.get("PS3_DEV_FLASH"):
    say("set PS3_DEV_FLASH to your own firmware path (never commit it)"); sys.exit(2)
sets = "".join("set %s=%s&& " % (k, v) for k, v in env.items())
# -w keeps renderdoccmd (and this cmd's stdio redirect) alive until the game exits,
# so the hook stays on the real D3D12 exe and stderr is more likely to inherit.
# Do not put a bare "--" before the exe: renderdoccmd treats it as the executable name.
cl = (
    'cmd.exe /c %s"%s" capture --working-dir "%s" --capture-file "%s" '
    '--opt-hook-children --wait-for-exit "%s" "%s" 1>"%s_stdout.log" 2>"%s_stderr.log"'
    % (sets, RDCMD, os.path.join(T, "play_cwd"), TEMPLATE, EXE, ELF, LOGPREFIX, LOGPREFIX)
)
# Also tee renderdoccmd ident somewhere: the redirect above captures child+cmd together.
# Write the command line we used (no secrets) into the run folder.
open(os.path.join(RD, "cmdline.txt"), "w", encoding="utf-8").write(cl)
say("Win32_Process Create renderdoccmd capture " + BUILD)

# Avoid breaking the CIM PowerShell single-quoted command: cl has no single quotes.
cmd = (
    "$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly "
    "-Property @{ShowWindow=[uint16]0}; "
    "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
    "@{CommandLine='%s'; CurrentDirectory='%s'; ProcessStartupInformation=$si}; "
    "\"$($r.ReturnValue),$($r.ProcessId)\""
) % (cl.replace("'", "''"), T)
out = ps(cmd, timeout=90).strip()
say("Win32_Process Create -> " + out)
try:
    rv, cmdpid = (int(x) for x in out.split(",")[:2])
except Exception:
    say("bad CIM result"); sys.exit(4)
if rv != 0:
    say("Create failed return %s" % rv); sys.exit(4)

gpid = None
for _ in range(90):
    gp = game_procs()
    if gp:
        gpid = gp[0][0]
        break
    time.sleep(1)
if not gpid:
    say("game pid not found"); sys.exit(5)
say("our game pid %d (cmd %d)" % (gpid, cmdpid))
json.dump({"game_pid": gpid, "cmd_pid": cmdpid, "ts": TS, "build": BUILD, "template": TEMPLATE},
          open(os.path.join(RD, "pids.json"), "w"))

subprocess.Popen(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
     "-File", os.path.join(SF, "winplace.ps1"), "-ProcId", str(gpid)],
    creationflags=NOWIN)
time.sleep(2)

# Wait briefly for log files (redirect target or delayed).
for _ in range(20):
    new = sorted(set(os.listdir(os.path.join(T, "play_logs"))) - before_logs)
    for n in new:
        if n.endswith("_stdout.log"):
            STDOUT = os.path.join(T, "play_logs", n)
        if n.endswith("_stderr.log"):
            STDERR = os.path.join(T, "play_logs", n)
    if STDOUT or STDERR:
        break
    time.sleep(0.5)
say("logs stdout=%s stderr=%s" % (STDOUT, STDERR))

SECS = 118   # boot movies, no input (same as prior 1807trace run)
PLAY = 0     # burst run: stop right after spawn

t0 = time.time()
try:
    i = 0
    while time.time() - t0 < SECS and alive(gpid):
        maybe_f12_from_frame(gpid)
        if i % 4 == 0:
            shot(gpid, "fmv_%03d_t%03d" % (i, int(time.time() - t0)))
        i += 1
        time.sleep(2.0)
    if alive(gpid):
        wait_draws(gpid, 6, 5, 60)
        time.sleep(4)
        shot(gpid, "00_title")
        press(gpid, "0x0008", 40, "START title")
        time.sleep(8)
        shot(gpid, "00_menu")
        press(gpid, "0x4000", 40, "CROSS Continue")
        time.sleep(6)
        press(gpid, "0x4000", 40, "CROSS file 1")
        time.sleep(5)
        press(gpid, "0x4000", 40, "CROSS Yes load", guard=False)
        t_yes = time.time(); t_hi = None; nb = 0
        while time.time() - t_yes < 90 and alive(gpid):
            d = draws(gpid)
            if time.time() - t_yes >= 9 and len(F12_DONE) < 34 and (t_hi is None or time.time() - t_hi < 4):
                press_f12(gpid, "burst_%02d" % nb); nb += 1
            if d is not None and d >= 700 and t_hi is None:
                t_hi = time.time(); say("draws>=700 (spawn) seen")
            if t_hi is not None and time.time() - t_hi >= 4:
                break
            time.sleep(0.45)
        wait_draws(gpid, 150, 10, 300)
        time.sleep(2)
        maybe_f12_from_frame(gpid)
        shot(gpid, "01_spawn")
        press(gpid, "0x4000", 20, "dismiss tutorial text")
        time.sleep(5)
        shot(gpid, "02_after_text")
        for k in range(2):
            press(gpid, "0x10000", 120, "walk forward", 128, 0)
            time.sleep(1)
            shot(gpid, "03_fwd_%d" % k)
        for k in range(2):
            press(gpid, "0x10000", 120, "walk back", 128, 255)
            time.sleep(1)
            shot(gpid, "04_back_%d" % k)
        tp = time.time()
        j = 0
        while time.time() - tp < PLAY and alive(gpid):
            maybe_f12_from_frame(gpid)
            already = {x["why"] for x in F12_DONE}
            # fallback for the late village window (~70-90 s of play in the prior run)
            pass
            press(gpid, "0x10000", 90, "play walk", 128, 0 if j % 2 == 0 else 255, guard=False)
            time.sleep(2)
            if j % 8 == 0:
                shot(gpid, "05_play_%03d_t%04d" % (j, int(time.time() - tp)))
            j += 1
            time.sleep(3)
        say("play phase done %d s" % int(time.time() - tp))
        maybe_f12_from_frame(gpid)
finally:
    # list captures before close (files may flush on exit too)
    caps_mid = []
    if os.path.isdir(CAPDIR):
        caps_mid = [n for n in os.listdir(CAPDIR) if n not in before_caps]
    say("captures mid: %s" % caps_mid)
    json.dump({"f12": F12_DONE, "captures_mid": caps_mid, "template": TEMPLATE},
              open(os.path.join(RD, "f12.json"), "w"))
    if alive(gpid):
        ps("Stop-Process -Id %d -Force" % gpid)
        say("closed own pid %d" % gpid)
    time.sleep(4)
    say("still alive after close: %s" % alive(gpid))
    # do not kill other pids; if our cmd (renderdoccmd -w) is still around, give it a moment
    new = sorted(set(os.listdir(os.path.join(T, "play_logs"))) - before_logs)
    caps = []
    if os.path.isdir(CAPDIR):
        for n in sorted(os.listdir(CAPDIR)):
            if n in before_caps:
                continue
            caps.append(n)
    say("captures after: %s" % caps)
    json.dump({"logs": new, "captures": caps, "f12": F12_DONE, "template": TEMPLATE, "build": BUILD},
              open(os.path.join(RD, "logs.json"), "w"))
    for n in new:
        try:
            shutil.copy2(os.path.join(T, "play_logs", n), os.path.join(RD, n))
        except Exception as e:
            say("copy log failed %s" % e)
    for n in caps:
        # rdc can be huge; do not copy into the run folder, just record size
        p = os.path.join(CAPDIR, n)
        try:
            say("capture file %s bytes=%d" % (p, os.path.getsize(p)))
        except OSError as e:
            say("capture stat failed %s %s" % (p, e))
say("RUN_DONE " + RD)


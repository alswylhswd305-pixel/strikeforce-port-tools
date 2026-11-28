# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
# sf_voice_probe: 1807trace run whose play phase attacks/talks to trigger voice lines (TEST COPY only). Launch via Invoke-CimMethod Win32_Process Create, close only our pid.
import os, sys, time, json, re, shutil, subprocess, ctypes, ctypes.wintypes as wt
T = os.environ.get("SF_TEST_ROOT") or os.environ.get("SF_ROOT") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")); SF = os.path.join(T, "sfauto")
R = os.path.join(SF, "fix1807trace")
PAD = os.path.join(SF, "ringwatch_work", "pad.txt")
import argparse
AP = argparse.ArgumentParser(); AP.add_argument("--env", default=""); AP.add_argument("--mode", default="full"); AP.add_argument("--label", default="all_on"); AP.add_argument("--bat", default="PLAY_Strikeforce_SCISSOR1803.bat"); AP.add_argument("--secs", type=int, default=118); AP.add_argument("--load", type=int, default=0); AP.add_argument("--play", type=int, default=0)
ARGS = AP.parse_args(); BAT = os.path.join(T, ARGS.bat)
TS = time.strftime("%Y%m%d-%H%M%S"); RD = os.path.join(R, "run_" + TS + "_" + ARGS.label); os.makedirs(os.path.join(RD, "shots"))
NOWIN = 0x08000000
LOG = open(os.path.join(RD, "run_log.txt"), "a", encoding="utf-8")
def say(s):
    line = time.strftime("%H:%M:%S ") + s; print(line, flush=True); LOG.write(line + "\n"); LOG.flush()
user32 = ctypes.windll.user32
_ENUM = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
def titles():
    res = {}
    def cb(h, l):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n > 0:
                p = wt.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(p))
                b = ctypes.create_unicode_buffer(n + 1); user32.GetWindowTextW(h, b, n + 1)
                if len(b.value) > len(res.get(p.value, "")): res[p.value] = b.value
        return True
    user32.EnumWindows(_ENUM(cb), 0); return res
def ps(cmd, timeout=60):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                          capture_output=True, text=True, errors="replace", timeout=timeout, creationflags=NOWIN).stdout
def game_procs():
    out = ps("Get-CimInstance Win32_Process -Filter \"Name='MyGameRecomp.exe'\" | % { \"$($_.ProcessId),$($_.ParentProcessId)\" }")
    return [tuple(int(x) for x in l.split(",")) for l in out.split() if "," in l]
def alive(pid):
    return any(p == pid for p, _ in game_procs())
def draws(pid):
    m = re.search(r"draws: (\d+)", titles().get(pid, "")); return int(m.group(1)) if m else None
def shot(pid, name):
    out = os.path.join(RD, "shots", name + ".png")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(SF, "fix1803_scissor", "shot_pw.ps1"),
                    "-ProcId", str(pid), "-Out", out], capture_output=True, text=True, timeout=40, creationflags=NOWIN)
    cp = out[:-4] + "_client.png"
    if os.path.exists(cp): os.replace(cp, out)
    ok = os.path.exists(out); say("shot %s %s (draws=%s)" % (name, "ok" if ok else "FAILED", draws(pid))); return out if ok else None
STDOUT = None
def sail_open():
    if not STDOUT or not os.path.exists(STDOUT): return 0
    txt = open(STDOUT, "rb").read().decode("utf-8", "replace")
    return max(0, txt.count("[cellSail] PlayerStart(") - txt.count("[cellSail] PlayerFinalize("))
def letterbox(pid):
    p = shot(pid, "_guard")
    if not p: return False
    try:
        import numpy as np; from PIL import Image
        a = np.asarray(Image.open(p).convert("L"), dtype=np.float32); k = max(4, int(a.shape[0] * 0.07))
        top, bot, mid = a[:k], a[-k:], a[k:-k]
        return top.mean() < 6 and bot.mean() < 6 and top.std() < 3 and bot.std() < 3 and mid.mean() > 20
    except Exception: return False
def press(pid, mask, n, why, lx=None, ly=None, guard=True):
    if guard:
        w = 0
        while sail_open() > 0 or letterbox(pid):
            if w == 0: say("cutscene/movie: holding input")
            if w > 300 or not alive(pid): say("guard timeout, skip " + why); return False
            time.sleep(2); w += 2
    line = "%s %d" % (mask, n) + ("" if lx is None else " %d %d" % (lx, ly))
    open(PAD, "w").write(line)
    for _ in range(100):
        if os.path.getsize(PAD) == 0: break
        time.sleep(0.1)
    else: say("press not consumed in 10 s: " + line)
    say("press %s (%s)" % (line, why)); return True
def wait_draws(pid, mn, hold, timeout):
    t_end = time.time() + timeout; since = None
    while time.time() < t_end and alive(pid):
        d = draws(pid)
        if d is not None and d >= mn:
            since = since or time.time()
            if time.time() - since >= hold: say("draws >= %d held (%s)" % (mn, d)); return True
        else: since = None
        time.sleep(1)
    say("wait_draws timed out (last %s)" % draws(pid)); return False


# ---- gate
busy = game_procs()
if busy: say("another MyGameRecomp is running %s: NOT launching" % busy); sys.exit(3)
bk = os.path.join(R, "backup_" + TS); os.makedirs(bk)
for sub in ("gamedata", "hdd0"):
    s = os.path.join(SF, "state_ringwatch", sub)
    if os.path.isdir(s): shutil.copytree(s, os.path.join(bk, "state_ringwatch", sub))
say("backup -> " + bk)
before = set(os.listdir(os.path.join(T, "play_logs")))
wav = os.path.join(RD, "out.wav")
env = [kv for kv in ARGS.env.split(',') if kv] + ["AUDIO_WAV=" + wav]
sets = ''.join('set %s&& ' % kv for kv in env)
cl = 'cmd.exe /c set PAD_NO_XINPUT=1&& %scall %s' % (sets, BAT)
say('bat %s env %s' % (ARGS.bat, env))
cmd = ("$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}; "
       "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='%s'; CurrentDirectory='%s'; ProcessStartupInformation=$si}; "
       "\"$($r.ReturnValue),$($r.ProcessId)\"") % (cl.replace("'", "''"), T)
out = ps(cmd).strip(); say("Win32_Process Create -> " + out)
rv, cmdpid = (int(x) for x in out.split(",")[:2])
if rv != 0: sys.exit(4)
gpid = None
for _ in range(60):
    for p, pp in game_procs():
        if pp == cmdpid: gpid = p
    if gpid: break
    time.sleep(1)
if not gpid: say("game pid not found"); sys.exit(5)
say("our game pid %d (cmd %d)" % (gpid, cmdpid))
json.dump({"game_pid": gpid, "cmd_pid": cmdpid, "ts": TS}, open(os.path.join(RD, "pids.json"), "w"))
subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File",
                  os.path.join(SF, "winplace.ps1"), "-ProcId", str(gpid)], creationflags=NOWIN)
time.sleep(2)
new = sorted(set(os.listdir(os.path.join(T, "play_logs"))) - before)
for n in new:
    if n.endswith("_stdout.log"): STDOUT = os.path.join(T, "play_logs", n)
say("logs %s stdout %s" % (new, STDOUT))
t0 = time.time()
try:
    i = 0
    # NO input at all during the boot movies (the cutscene is never skipped)
    while time.time() - t0 < ARGS.secs and alive(gpid):
        shot(gpid, "fmv_%03d_t%03d" % (i, int(time.time() - t0))); i += 1; time.sleep(2.0)
    if ARGS.load and alive(gpid):
        wait_draws(gpid, 6, 5, 60); time.sleep(4); shot(gpid, "00_title")
        press(gpid, "0x0008", 40, "START title"); time.sleep(8); shot(gpid, "00_menu")
        press(gpid, "0x4000", 40, "CROSS Continue"); time.sleep(6)
        press(gpid, "0x4000", 40, "CROSS file 1"); time.sleep(5)
        press(gpid, "0x4000", 40, "CROSS Yes load", guard=False)
        for k in range(60):
            d = draws(gpid); shot(gpid, "09_loading_%02d" % k)
            if d is not None and d >= 150: break
            time.sleep(0.8)
        wait_draws(gpid, 150, 10, 300); time.sleep(6); shot(gpid, "01_spawn")
        press(gpid, "0x4000", 20, "dismiss tutorial text"); time.sleep(5); shot(gpid, "02_after_text")
        for k in range(2):
            press(gpid, "0x10000", 120, "walk forward", 128, 0); time.sleep(1); shot(gpid, "03_fwd_%d" % k)
        for k in range(2):
            press(gpid, "0x10000", 120, "walk back", 128, 255); time.sleep(1); shot(gpid, "04_back_%d" % k)
        tp = time.time(); j = 0
        while ARGS.play and time.time() - tp < ARGS.play and alive(gpid):
            # voice probe: walk, then attack (SQUARE), talk/confirm (CROSS), CIRCLE; voice lines are triggered by combat/dialogue
            seq = [("0x10000", 60, "walk", 128, 0), ("0x8000", 20, "SQUARE attack", None, None), ("0x8000", 20, "SQUARE attack", None, None), ("0x4000", 20, "CROSS talk/confirm", None, None), ("0x2000", 20, "CIRCLE", None, None), ("0x10000", 60, "walk back", 128, 255)]
            m, n_, why_, lx_, ly_ = seq[j % len(seq)]
            press(gpid, m, n_, "probe " + why_, lx_, ly_, guard=False); time.sleep(1)
            if j % 8 == 0: shot(gpid, "05_play_%03d_t%04d" % (j, int(time.time() - tp)))
            j += 1; time.sleep(3)
        say("play phase done %d s" % int(time.time() - tp))
finally:
    if alive(gpid):
        ps("Stop-Process -Id %d -Force" % gpid); say("closed own pid %d" % gpid)
    time.sleep(3)
    say("still alive after close: %s" % alive(gpid))
    json.dump({"logs": new, "wav": wav}, open(os.path.join(RD, "logs.json"), "w"))
    for n in new:
        try: shutil.copy2(os.path.join(T, "play_logs", n), os.path.join(RD, n))
        except Exception as e: say("copy log failed %s" % e)
say("RUN_DONE " + RD)


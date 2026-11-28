#!/usr/bin/env python
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""sf_pipeline.py -- one command for the test loop:  [build] -> run the TEST COPY -> capture a frame ->
screenshot -> compare with an RPCS3 reference.  Every step is optional and runs the existing harness
scripts (nothing is re-implemented), so the old behaviour is unchanged.

  python sfauto/tools/sf_pipeline.py status
  python sfauto/tools/sf_pipeline.py backup  [--build 1807trace]
  python sfauto/tools/sf_pipeline.py build   --script sfauto/fix1807trace/build_1807trace.ps1 --approve-build
  python sfauto/tools/sf_pipeline.py run     [--bat PLAY_Strikeforce_1807trace.bat] [--env SF_LWCOND=2,SF_LWCTRACE=1]
                                             [--secs 130] [--load] [--play 60] [--label NAME]
  python sfauto/tools/sf_pipeline.py capture                 # RenderDoc burst capture (rdc_capture_burst.py)
  python sfauto/tools/sf_pipeline.py compare --ref REF.png [--ours RUN_DIR/shots/05_play....png]
  python sfauto/tools/sf_pipeline.py all     --ref REF.png [--env ...] [--load] [--play 60]   # run -> compare
  python sfauto/tools/sf_pipeline.py passes  [CAPTURE.rdc]   # rdc_passes.py on the newest capture

Safety rules built in (they are the project rules):
  * test copy only: every path is under the test copy; no deploy step exists.
  * build needs --approve-build; before it the current exe is copied to sfauto/backups/ (the build script
    also moves the old exe aside by itself).  No build runs by default.
  * refuses to start the game when another MyGameRecomp.exe is already running, and never stops a process
    it did not start (the harness closes only its own game pid).
  * no installs: it needs only Python 3 with Pillow/numpy that are already present.
"""
import argparse, glob, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.environ.get("SF_TEST_ROOT") or os.path.join(HERE, "..", ".."))
SF = os.path.join(ROOT, "sfauto")
PY = sys.executable


def game_running():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-Process MyGameRecomp -ErrorAction SilentlyContinue | % { $_.Id }"],
                       capture_output=True, text=True)
    return [x for x in r.stdout.split() if x.isdigit()]


def newest(pattern):
    fs = glob.glob(pattern)
    return max(fs, key=os.path.getmtime) if fs else None


def sh(cmd, **kw):
    print(">", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, **kw)


def cmd_status(a):
    running = game_running()
    print("game running:", running or "no")
    exes = sorted(glob.glob(os.path.join(SF, "exe_copies", "*", "MyGameRecomp.exe")), key=os.path.getmtime)
    for e in exes[-4:]:
        print("exe  %s  %s" % (time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(e))), os.path.relpath(e, ROOT)))
    for pat, label in ((os.path.join(SF, "fix*", "run_*"), "run dir"), (os.path.join(SF, "captures", "*.rdc"), "capture"),
                       (os.path.join(ROOT, "play_logs", "*_stderr.log"), "stderr log")):
        n = newest(pat)
        print("newest %-10s %s" % (label, os.path.relpath(n, ROOT) if n else "none"))


def cmd_backup(a):
    src = os.path.join(SF, "exe_copies", a.build)
    if not os.path.isdir(src):
        sys.exit("no such build folder: %s" % src)
    dst = os.path.join(SF, "backups", "%s_%s" % (a.build, time.strftime("%Y%m%d-%H%M%S")))
    shutil.copytree(src, dst)
    print("backed up", os.path.relpath(src, ROOT), "->", os.path.relpath(dst, ROOT))


def cmd_build(a):
    if not a.approve_build:
        sys.exit("refusing to build: pass --approve-build only after the user approved this build.")
    script = os.path.abspath(a.script)
    if not script.startswith(SF):
        sys.exit("build script must live under the test copy (%s)" % SF)
    cmd_backup(argparse.Namespace(build=a.build))
    sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script])


def cmd_run(a):
    if game_running():
        sys.exit("another MyGameRecomp.exe is running %s: not launching." % game_running())
    harness = os.path.join(SF, "fix1807trace", "run_1807trace.py")
    cmd = [PY, "-I", harness, "--bat", a.bat, "--label", a.label, "--secs", str(a.secs)]
    if a.env:
        cmd += ["--env", a.env]
    if a.load:
        cmd += ["--load", "1", "--play", str(a.play)]
    r = sh(cmd)
    run_dir = newest(os.path.join(SF, "fix1807trace", "run_*_%s" % a.label))
    print("run dir:", run_dir)
    return run_dir


def pick_shot(run_dir):
    shots = os.path.join(run_dir, "shots")
    for pat in ("05_play_*", "04_back_*", "03_fwd_*", "01_spawn*"):
        f = sorted(glob.glob(os.path.join(shots, pat + ".png")))
        if f:
            return f[-1]
    return None


def cmd_compare(a):
    ours = a.ours
    if not ours:
        run_dir = newest(os.path.join(SF, "fix1807trace", "run_*"))
        ours = pick_shot(run_dir) if run_dir else None
    if not ours:
        sys.exit("no screenshot found; pass --ours")
    cmd = [PY, "-I", os.path.join(HERE, "imgdiff.py"), ours, a.ref]
    for ig in a.ignore:
        cmd += ["--ignore", ig]
    sh(cmd)


def cmd_capture(a):
    if game_running():
        sys.exit("another MyGameRecomp.exe is running: not launching.")
    sh([PY, "-I", os.path.join(HERE, "rdc_capture_burst.py")])


def cmd_passes(a):
    cap = a.capture or newest(os.path.join(SF, "captures", "*.rdc"))
    if not cap:
        sys.exit("no capture")
    sh([PY, "-I", os.path.join(HERE, "rdc_passes.py"), cap])


def cmd_all(a):
    run_dir = cmd_run(a)
    shot = pick_shot(run_dir) if run_dir else None
    if shot and a.ref:
        cmd_compare(argparse.Namespace(ours=shot, ref=a.ref, ignore=a.ignore))
    else:
        print("compare skipped (no shot or no --ref)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(f=cmd_status)
    p = sub.add_parser("backup"); p.add_argument("--build", default="1807trace"); p.set_defaults(f=cmd_backup)
    p = sub.add_parser("build"); p.add_argument("--script", required=True); p.add_argument("--build", default="1807trace")
    p.add_argument("--approve-build", action="store_true"); p.set_defaults(f=cmd_build)
    for name, fn in (("run", cmd_run), ("all", cmd_all)):
        p = sub.add_parser(name)
        p.add_argument("--bat", default="PLAY_Strikeforce_1807trace.bat"); p.add_argument("--env", default="")
        p.add_argument("--secs", type=int, default=130); p.add_argument("--load", action="store_true")
        p.add_argument("--play", type=int, default=60); p.add_argument("--label", default="pipe")
        p.add_argument("--ref", default=None); p.add_argument("--ignore", action="append", default=[])
        p.set_defaults(f=fn)
    p = sub.add_parser("capture"); p.set_defaults(f=cmd_capture)
    p = sub.add_parser("compare"); p.add_argument("--ref", required=True); p.add_argument("--ours", default=None)
    p.add_argument("--ignore", action="append", default=[]); p.set_defaults(f=cmd_compare)
    p = sub.add_parser("passes"); p.add_argument("capture", nargs="?"); p.set_defaults(f=cmd_passes)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()

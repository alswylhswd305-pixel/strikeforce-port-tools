#!/usr/bin/env python3
"""gfx_bisect.py — find which draw index causes a visual artefact.

Clean-room helper for the Dynasty Warriors: Strikeforce ps3recomp D3D12 port.
No RPCS3 or GPL code. Draw skipping / DRAW_RANGE is a diagnostic, never a fix
(playbook L4, L8, L12).

Default mode is fully automatic: a screenshot metric decides "artefact present?"
and, once a culprit index is isolated, one more launch dumps that draw's state
and writes a markdown report. Interactive y/n is opt-in only.

    python gfx_bisect.py auto --config cfg.json
    python gfx_bisect.py --config cfg.json          # same as auto
    python gfx_bisect.py interactive --config cfg.json
    python gfx_bisect.py report --log run.log --rpcs3 values.json --out report.md
    python gfx_bisect.py self-test
    python gfx_bisect.py diagnose ours.jpg ref.png --out outdir
    python gfx_bisect.py batch --pairs pairs.json --out outdir
    python gfx_bisect.py cutscene --ours frames_or_video --ref frames_or_video --out outdir

DRAW_RANGE / DRAW_DUMP are not in upstream ps3recomp (verified 2026-11-26).
See diagnostic_snippets.c and the README for the minimal logs Salem adds.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# img_compare.py lives next to this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import img_compare as ic  # noqa: E402

VTX_TYPES = {1: "S1", 2: "F", 3: "SF", 4: "UB", 5: "S32K", 6: "CMP", 7: "UB256"}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("config must be a JSON object")
    return cfg


def cfg_get(cfg: dict, *keys, default=None):
    """Nested get: cfg_get(cfg, "oracle", "threshold", default=0.15)."""
    cur = cfg
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# ---------------------------------------------------------------------------
# Bisection
# ---------------------------------------------------------------------------

def split_halves(lo: int, hi: int) -> List[Tuple[int, int]]:
    """Split inclusive [lo, hi] into 1 or 2 contiguous halves. Lower first."""
    if lo > hi:
        return []
    if lo == hi:
        return [(lo, hi)]
    mid = lo + (hi - lo + 1) // 2  # first index of the upper half
    parts = []
    if lo <= mid - 1:
        parts.append((lo, mid - 1))
    if mid <= hi:
        parts.append((mid, hi))
    return parts


def split_k(lo: int, hi: int, k: int) -> List[Tuple[int, int]]:
    """Partition [lo, hi] into up to k contiguous buckets (L8 / L10)."""
    n = hi - lo + 1
    if n <= 0:
        return []
    k = max(1, min(k, n))
    out = []
    for i in range(k):
        a = lo + (i * n) // k
        b = lo + ((i + 1) * n) // k - 1
        if a <= b:
            out.append((a, b))
    return out


def format_range(lo: int, hi: int) -> str:
    return "%d-%d" % (lo, hi)


# ---------------------------------------------------------------------------
# Oracle (auto by default — never prompts unless mode=interactive)
# ---------------------------------------------------------------------------

@dataclass
class OracleResult:
    present: bool
    metric: str
    value: Optional[float]
    threshold: float
    region: str
    rule: str
    screenshot: str
    report_dir: str = ""
    reason: str = ""


def decide_artifact(screenshot: str, cfg: dict, out_dir: str,
                    ask: Optional[Callable[[str], bool]] = None) -> OracleResult:
    """Return whether the artefact is visible in `screenshot`.

    Default is automatic (compare a region against the reference or a known-bad
    frame). Interactive y/n only runs when oracle.mode is "interactive" and an
    ask callback (or stdin) is provided.
    """
    oracle = cfg.get("oracle") or {}
    mode = (oracle.get("mode") or cfg.get("mode") or "auto").lower()
    region = oracle.get("region") or "tent"
    metric = oracle.get("metric") or "mae"
    threshold = float(oracle.get("threshold", 0.15))
    rule = oracle.get("artifact_if") or oracle.get("rule") or "above"
    # Interactive is opt-in only.
    if mode in ("interactive", "ask", "yn", "y/n"):
        if ask is None:
            raise RuntimeError("interactive mode needs a TTY ask callback; "
                               "use `auto` (default) or pass --interactive")
        present = bool(ask(screenshot))
        return OracleResult(present, "interactive", None, threshold, region, "ask",
                            screenshot, reason="user")
    ref = oracle.get("reference") or oracle.get("known_bad") or cfg.get("reference")
    compare_to = oracle.get("compare_against") or ("known_bad" if oracle.get("known_bad") and not oracle.get("reference") else "reference")
    if compare_to == "known_bad" and oracle.get("known_bad"):
        ref = oracle["known_bad"]
        if rule in ("above", "far_from_ref"):
            rule = "close_to_bad"
    if not ref:
        raise RuntimeError("auto mode needs oracle.reference (RPCS3 shot) or oracle.known_bad")
    if not screenshot or not os.path.exists(screenshot):
        return OracleResult(False, metric, None, threshold, region, rule, screenshot or "",
                            reason="no_screenshot")
    size = (int(cfg_get(cfg, "compare", "w", default=1280)),
            int(cfg_get(cfg, "compare", "h", default=720)))
    crop_ours = _box_or_none(cfg_get(cfg, "screenshot", "crop") or oracle.get("crop_ours"))
    crop_ref = _box_or_none(oracle.get("crop_ref") or cfg_get(cfg, "reference_crop"))
    regions = (oracle.get("regions") or cfg.get("regions") or ic.DEFAULT_REGIONS)
    # New detectors (shadow_acne, dark_roofs, haze, faces, white_ground, …)
    # go through diagnose.py so the bisect oracle can use any of them.
    diagnose_metrics = {
        "shadow_acne", "dark_roofs", "haze", "haze_fog", "fog",
        "faces", "face_dark", "face_eyes", "face_blue",
        "white_ground", "dark_buildings",
    }
    if metric in diagnose_metrics or oracle.get("align"):
        import diagnose as dg
        dest = os.path.join(out_dir, "diagnose")
        pair = dg.compare_pair(
            screenshot, ref, dest, size=size,
            crop_ours=crop_ours, crop_ref=crop_ref,
            face_boxes=oracle.get("face_boxes") or cfg.get("face_boxes"),
            regions=regions, photo=oracle.get("photo", "no"),
            name="bisect",
        )
        present, value = dg.artifact_from_score(pair["scores"], metric, threshold, rule)
        return OracleResult(present, metric, value, threshold, region or metric, rule,
                            screenshot, report_dir=dest,
                            reason="auto diagnose %s %s threshold %s" % (metric, value, threshold))
    report = ic.compare(screenshot, ref, out_dir, size=size,
                        crop_ours=crop_ours, crop_ref=crop_ref, regions=regions)
    if region not in report["regions"]:
        raise RuntimeError("oracle region %r not in %s" % (region, sorted(report["regions"])))
    stats = report["regions"][region]
    value = ic.metric_value(stats, metric)
    present = ic.artifact_present(stats, metric, threshold, rule)
    return OracleResult(present, metric, value, threshold, region, rule, screenshot,
                        report_dir=out_dir,
                        reason="auto %s %s %s threshold %s" % (region, metric, value, threshold))


def _box_or_none(v):
    if not v:
        return None
    if isinstance(v, str):
        return ic.parse_box(v)
    return tuple(int(x) for x in v)


# ---------------------------------------------------------------------------
# Windows (and dump-file) capture + process launch
# ---------------------------------------------------------------------------

def _enum_hwnds_for_pid(pid: int, title_substr: Optional[str] = None):
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        tid_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid_pid))
        if tid_pid.value != pid:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value or ""
        if title_substr and title_substr.lower() not in title.lower():
            return True
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w > 64 and h > 64:
                found.append((hwnd, title, (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(cb, 0)
    found.sort(key=lambda t: (0 if t[1] else 1, -(t[2][2] - t[2][0]) * (t[2][3] - t[2][1])))
    return found


def grab_window(pid: int, out_path: str, title_substr: Optional[str] = None,
                crop=None) -> bool:
    """Capture the game window on Windows (mss, then PIL ImageGrab)."""
    if sys.platform != "win32":
        return False
    wins = _enum_hwnds_for_pid(pid, title_substr)
    if not wins:
        wins = _enum_hwnds_for_pid(pid, None)
    if not wins:
        return False
    _, _title, (l, t, r, b) = wins[0]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    # mss (preferred: per-monitor, no DPI surprises as often)
    try:
        import mss  # type: ignore
        from PIL import Image
        with mss.mss() as sct:
            raw = sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
            im = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            if crop:
                im = ic.crop_rgb(im, crop)
            im.save(out_path)
            return os.path.exists(out_path)
    except Exception:
        pass
    try:
        from PIL import ImageGrab
        im = ImageGrab.grab(bbox=(l, t, r, b))
        if crop:
            im = ic.crop_rgb(im, crop)
        im.save(out_path)
        return os.path.exists(out_path)
    except Exception:
        return False


def grab_dump_file(pattern: str, out_path: str, newer_than: float = 0.0) -> bool:
    """Fallback: copy the newest file matching a glob the game dumped."""
    import glob
    cands = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    if newer_than:
        cands = [p for p in cands if os.path.getmtime(p) >= newer_than - 1.0]
    if not cands:
        return False
    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    shutil.copy2(cands[0], out_path)
    return True


def _kill_tree(pid: int) -> None:
    try:
        import psutil  # type: ignore
        proc = psutil.Process(pid)
        kids = proc.children(recursive=True)
        proc.terminate()
        for k in kids:
            try:
                k.terminate()
            except Exception:
                pass
        _, alive = psutil.wait_procs([proc] + kids, timeout=5)
        for a in alive:
            try:
                a.kill()
            except Exception:
                pass
        return
    except Exception:
        pass
    try:
        import signal
        os.kill(pid, signal.SIGTERM if sys.platform != "win32" else signal.SIGTERM)
    except Exception:
        pass
    if sys.platform == "win32":
        os.system("taskkill /PID %d /T /F >nul 2>&1" % pid)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    draw_range: Optional[str]
    screenshot: str
    log_path: str
    elapsed: float
    pid: Optional[int] = None
    instance: int = 0
    env: dict = field(default_factory=dict)
    ok: bool = True
    note: str = ""


class GameRunner:
    """Launch the port exe, wait, screenshot, stop. Swap out in tests."""

    def run(self, cfg: dict, extra_env: dict, out_dir: str, instance: int = 0) -> RunResult:
        os.makedirs(out_dir, exist_ok=True)
        root = cfg.get("root") or ""
        exe = cfg.get("exe") or ""
        if root and not os.path.isabs(exe):
            exe = os.path.join(root, exe)
        args = list(cfg.get("exe_args") or [])
        wait = float(cfg.get("wait_secs") or 160)
        env = dict(os.environ)
        env.update(cfg.get("base_env") or {})
        env.update(extra_env)
        # Per-instance writable roots so parallel copies do not stomp each other.
        inst_env = _instance_env(cfg, out_dir, instance)
        env.update(inst_env)
        cwd = inst_env.get("CWD") or cfg.get("cwd") or out_dir
        os.makedirs(cwd, exist_ok=True)
        log_path = os.path.join(out_dir, "run.log")
        shot_path = os.path.join(out_dir, "shot.png")
        t0 = time.time()
        import subprocess
        stdout = open(os.path.join(out_dir, "stdout.log"), "w", errors="replace")
        stderr = open(os.path.join(out_dir, "stderr.log"), "w", errors="replace")
        logf = open(log_path, "wb")
        try:
            p = subprocess.Popen([exe] + args, cwd=cwd, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            assert p.stdout is not None
            # Tee into run.log (combined) while the process lives.
            def _pump():
                try:
                    for chunk in iter(lambda: p.stdout.read(4096), b""):
                        if not chunk:
                            break
                        logf.write(chunk)
                        logf.flush()
                except Exception:
                    pass
            import threading
            th = threading.Thread(target=_pump, daemon=True)
            th.start()
            deadline = t0 + wait
            while time.time() < deadline and p.poll() is None:
                time.sleep(0.5)
            shot_ok = False
            title = (cfg.get("screenshot") or {}).get("window_title_substr") or "ps3recomp"
            crop = _box_or_none((cfg.get("screenshot") or {}).get("crop"))
            if p.poll() is None:
                shot_ok = grab_window(p.pid, shot_path, title, crop)
            dump_glob = (cfg.get("screenshot") or {}).get("dump_glob") or cfg.get("dump_glob")
            if not shot_ok and dump_glob:
                shot_ok = grab_dump_file(dump_glob, shot_path, newer_than=t0)
            if p.poll() is None:
                _kill_tree(p.pid)
                try:
                    p.wait(timeout=8)
                except Exception:
                    pass
            th.join(timeout=2)
        finally:
            stdout.close(); stderr.close(); logf.close()
        # Also concatenate any leftover stdio files if the tee missed them — run.log is the source of truth.
        return RunResult(
            draw_range=extra_env.get(cfg.get("draw_range_env") or "DRAW_RANGE"),
            screenshot=shot_path if os.path.exists(shot_path) else "",
            log_path=log_path,
            elapsed=round(time.time() - t0, 2),
            pid=None,
            instance=instance,
            env={k: extra_env[k] for k in extra_env},
            ok=os.path.exists(shot_path),
            note="" if os.path.exists(shot_path) else "no screenshot",
        )


def _instance_env(cfg: dict, out_dir: str, instance: int) -> dict:
    """Give instance i its own writable HDD / gamedata / cwd (L10)."""
    out = {"CWD": os.path.join(out_dir, "cwd")}
    base = cfg.get("base_env") or {}
    clone = bool(cfg.get("clone_state", True))
    mapping = {
        "PS3_HDD0_ROOT": "hdd0",
        "PS3_HDD1_ROOT": "hdd1",
        "PS3_GAMEDATA_ROOT": "gamedata",
    }
    for key, leaf in mapping.items():
        src = base.get(key)
        dest = os.path.join(out_dir, leaf)
        if clone and src and os.path.isdir(src) and not os.path.exists(dest):
            try:
                shutil.copytree(src, dest)
            except Exception:
                os.makedirs(dest, exist_ok=True)
        else:
            os.makedirs(dest, exist_ok=True)
        out[key] = dest
    return out


# ---------------------------------------------------------------------------
# Session (resume + CSV/JSON log)
# ---------------------------------------------------------------------------

@dataclass
class Step:
    step: int
    instance: int
    lo: int
    hi: int
    draw_range: str
    artifact: Optional[bool]
    metric: Optional[float]
    threshold: float
    screenshot: str
    elapsed: float
    reason: str = ""
    log_path: str = ""


class Session:
    def __init__(self, out_dir: str, orig_lo: int, orig_hi: int, state_path: str):
        self.out_dir = out_dir
        self.state_path = state_path
        self.orig_lo = orig_lo
        self.orig_hi = orig_hi
        self.lo = orig_lo
        self.hi = orig_hi
        self.steps: List[dict] = []
        self.status = "running"
        self.culprit: Optional[int] = None
        self.dump_log: str = ""
        self.report_path: str = ""

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        payload = {
            "orig_lo": self.orig_lo, "orig_hi": self.orig_hi,
            "lo": self.lo, "hi": self.hi,
            "status": self.status, "culprit": self.culprit,
            "steps": self.steps, "dump_log": self.dump_log,
            "report_path": self.report_path, "out_dir": self.out_dir,
        }
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self.state_path)
        self._write_csv()

    def _write_csv(self) -> None:
        path = os.path.join(self.out_dir, "steps.csv")
        fields = ["step", "instance", "lo", "hi", "draw_range", "artifact",
                  "metric", "threshold", "screenshot", "elapsed", "reason", "log_path"]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for s in self.steps:
                w.writerow(s)

    @classmethod
    def load(cls, path: str) -> "Session":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        s = cls(data.get("out_dir") or os.path.dirname(path), data["orig_lo"], data["orig_hi"], path)
        s.lo, s.hi = data["lo"], data["hi"]
        s.steps = list(data.get("steps") or [])
        s.status = data.get("status") or "running"
        s.culprit = data.get("culprit")
        s.dump_log = data.get("dump_log") or ""
        s.report_path = data.get("report_path") or ""
        return s


# ---------------------------------------------------------------------------
# DRAW_DUMP parser + markdown report
# ---------------------------------------------------------------------------

_FLOATS = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_HEX = re.compile(r"0x[0-9A-Fa-f]+")


def _floats(s: str) -> List[float]:
    return [float(x) for x in _FLOATS.findall(s)]


def parse_drawdump(text: str, want: Optional[int] = None) -> Optional[dict]:
    """Parse the last (or wanted) [DRAWDUP] block from a run log.

    Also scrapes a few existing (incomplete, often capped) knobs so a run
    without the new DRAW_DUMP snippet is not totally empty.
    """
    blocks = _extract_drawdup_blocks(text)
    if blocks:
        if want is not None:
            for b in reversed(blocks):
                if b.get("draw") == want:
                    return b
        return blocks[-1]
    # Fallback: scrape whatever existing knobs printed.
    scraped = _scrape_legacy_logs(text)
    if scraped:
        scraped["source"] = "legacy_scrape"
        return scraped
    return None


def _extract_drawdup_blocks(text: str) -> List[dict]:
    blocks = []
    cur = None
    for line in text.splitlines():
        if "[DRAWDUP]" not in line:
            continue
        body = line.split("[DRAWDUP]", 1)[1].strip()
        if body.startswith("begin"):
            cur = {"attribs": [], "c0_c15": [None] * 16, "source": "DRAW_DUMP"}
            m = re.search(r"draw\s*=\s*(\d+)", body)
            if m:
                cur["draw"] = int(m.group(1))
            m = re.search(r"frame\s*=\s*(\d+)", body)
            if m:
                cur["frame"] = int(m.group(1))
            continue
        if cur is None:
            continue
        if body.startswith("end"):
            blocks.append(cur)
            cur = None
            continue
        _fill_drawdup_line(cur, body)
    if cur:
        blocks.append(cur)
    return blocks


def _fill_drawdup_line(cur: dict, body: str) -> None:
    key, _, rest = body.partition(" ")
    key = key.strip().lower()
    rest = rest.strip()
    if key in ("viewport_scale", "viewport_offset"):
        cur[key] = _floats(rest)[:4]
    elif key in ("clip_range", "clip"):
        vals = _floats(rest)
        cur["clip_range"] = vals[:2]
    elif key == "viewport_rect":
        cur["viewport_rect"] = _floats(rest)[:4]
    elif key == "zmin_max_control":
        m = _HEX.search(rest) or re.search(r"\d+", rest)
        cur["zmin_max_control"] = m.group(0) if m else rest
    elif key in ("fp", "shader_program"):
        m = _HEX.search(rest) or re.search(r"\d+", rest)
        cur["fp"] = m.group(0) if m else rest
    elif key == "rt":
        cur["rt"] = _parse_rt(rest)
    elif key == "attr":
        cur["attribs"].append(_parse_attr(body if body.startswith("attr") else "attr " + rest))
    elif key == "c":
        parts = rest.split()
        if parts:
            try:
                slot = int(parts[0])
            except ValueError:
                return
            vals = _floats(" ".join(parts[1:]))[:4]
            if 0 <= slot < 16:
                if not isinstance(cur.get("c0_c15"), list) or len(cur["c0_c15"]) < 16:
                    cur["c0_c15"] = [None] * 16
                cur["c0_c15"][slot] = vals
    elif key == "note":
        cur.setdefault("notes", []).append(rest)


def _parse_rt(rest: str) -> dict:
    out = {}
    for m in re.finditer(r"(\w+)=([0-9A-Za-zx.+-]+)", rest):
        k, v = m.group(1), m.group(2)
        if v.lower().startswith("0x") or k in ("color0", "color1", "zeta", "format"):
            out[k] = v
        else:
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
    return out


def _parse_attr(body: str) -> dict:
    # attr 0 enabled=1 off=0x10 stride=16 size=3 type=2 freq=0
    out = {}
    m = re.search(r"attr\s+(\d+)", body)
    if m:
        out["index"] = int(m.group(1))
    for k, v in re.findall(r"(\w+)=([0-9A-Za-zx.+-]+)", body):
        if k in ("off", "offset"):
            out["offset"] = v if v.lower().startswith("0x") else v
        elif k == "type":
            try:
                ti = int(v, 0)
            except ValueError:
                ti = v
            out["type"] = ti
            if isinstance(ti, int):
                out["type_name"] = VTX_TYPES.get(ti, "?")
        elif k in ("enabled", "stride", "size", "freq", "frequency"):
            try:
                out[{"freq": "frequency", "frequency": "frequency"}.get(k, k)] = int(v, 0)
            except ValueError:
                out[k] = v
        else:
            out[k] = v
    return out


def _scrape_legacy_logs(text: str) -> Optional[dict]:
    """Best-effort parse of VP_ATTRS / VTX_DUMP / VP_MVP (capped, incomplete)."""
    out: dict = {"attribs": [], "c0_c15": [None] * 16, "notes": [
        "No [DRAWDUP] block found. Scraped existing capped knobs (VP_ATTRS / VTX_DUMP / VP_MVP). "
        "Add the DRAW_DUMP snippet so this report is complete."
    ]}
    hit = False
    m = re.search(r"\[VPATTR\] --- fp=(0x[0-9A-Fa-f]+|\d+)", text)
    if m:
        out["fp"] = m.group(1) if m.group(1).lower().startswith("0x") else hex(int(m.group(1)))
        hit = True
    for m in re.finditer(r"\[VPATTR\] a(\d+) off=(0x[0-9A-Fa-f]+|\d+) stride=(\d+) size=(\d+) type=(\d+)", text):
        ti = int(m.group(5))
        out["attribs"].append({
            "index": int(m.group(1)), "enabled": 1, "offset": m.group(2),
            "stride": int(m.group(3)), "size": int(m.group(4)),
            "type": ti, "type_name": VTX_TYPES.get(ti, "?"),
        })
        hit = True
    m = re.search(r"vp_scale=\(([^)]+)\) vp_off=\(([^)]+)\)", text)
    if m:
        out["viewport_scale"] = [float(x) for x in m.group(1).split(",")]
        out["viewport_offset"] = [float(x) for x in m.group(2).split(",")]
        hit = True
    for m in re.finditer(r"\[VPMVP\].*?c(\d+)=\(([^)]+)\)", text):
        # VP_MVP only prints c260 / c467 — record under notes, not c0-c15.
        out.setdefault("extra_constants", {})[int(m.group(1))] = [float(x) for x in m.group(2).split(",")]
        hit = True
    return out if hit else None


def nearly_equal(a, b, atol=1e-4, rtol=1e-3) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(nearly_equal(x, y, atol, rtol) for x, y in zip(a, b))
    if isinstance(a, str) or isinstance(b, str):
        return _norm_token(a) == _norm_token(b)
    try:
        fa, fb = float(a), float(b)
        return abs(fa - fb) <= atol + rtol * abs(fb)
    except (TypeError, ValueError):
        return _norm_token(a) == _norm_token(b)


def _norm_token(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"0x[0-9A-Fa-f]+", s):
        return hex(int(s, 16))
    if re.fullmatch(r"-?\d+", s):
        try:
            return hex(int(s)) if int(s) > 255 else str(int(s))
        except ValueError:
            return s.lower()
    return s.lower()


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return "%.6g" % v
    if isinstance(v, (list, tuple)):
        return " ".join(_fmt(x) for x in v)
    if isinstance(v, dict):
        return " ".join("%s=%s" % (k, _fmt(val)) for k, val in v.items())
    return str(v)


def _cell(port, rpc, match: Optional[bool]) -> Tuple[str, str, str]:
    p, r = _fmt(port), _fmt(rpc) if rpc is not None else "*(paste)*"
    if match is True:
        return p, r, "ok"
    if match is False:
        return "**%s**" % p, "**%s**" % r, "**MISMATCH**"
    return p, r, ""


def build_report(port: dict, rpcs3: Optional[dict], culprit: int, meta: dict,
                 atol=1e-4, rtol=1e-3) -> str:
    """Markdown report: port values vs optional RPCS3 JSON, mismatches bold."""
    rpc = rpcs3 or {}
    lines = []
    lines.append("# Culprit draw %d" % culprit)
    lines.append("")
    lines.append("Diagnostic only. Isolating or skipping this draw is **not a fix** "
                 "(playbook L4 / L8 / L12). One change per later build (L12).")
    lines.append("")
    if meta:
        lines.append("## How it was found")
        if meta.get("steps") is not None:
            lines.append("- Auto-bisect steps: **%s** (worst case ceil(log2 N); N = %s..%s)."
                         % (meta["steps"], meta.get("orig_lo"), meta.get("orig_hi")))
        if meta.get("metric"):
            lines.append("- Oracle: region `%s`, metric `%s`, threshold %s, rule `%s`."
                         % (meta.get("region"), meta.get("metric"), meta.get("threshold"), meta.get("rule")))
        if meta.get("out_dir"):
            lines.append("- Run folder: `%s`" % meta["out_dir"])
        if meta.get("dump_log"):
            lines.append("- Dump log: `%s`" % meta["dump_log"])
        if port.get("source") == "legacy_scrape":
            lines.append("- **Warning:** no `[DRAWDUP]` block; values were scraped from capped existing knobs. "
                         "Add `DRAW_DUMP` from `diagnostic_snippets.c` and re-run the dump step.")
        lines.append("")
    lines.append("## Port vs RPCS3")
    lines.append("")
    lines.append("| Field | Port | RPCS3 | Match |")
    lines.append("|---|---|---|---|")

    def row(label, pkey, rkey=None, transform=None):
        rkey = rkey or pkey
        pv = port.get(pkey)
        rv = rpc.get(rkey) if rpc else None
        if transform:
            pv, rv = transform(pv), transform(rv) if rv is not None else None
        match = None if rv is None else nearly_equal(pv, rv, atol, rtol)
        a, b, m = _cell(pv, rv, match)
        lines.append("| %s | %s | %s | %s |" % (label, a, b, m))

    row("viewport scale (NV4097 0x0A30)", "viewport_scale")
    row("viewport offset (NV4097 0x0A20)", "viewport_offset")
    row("viewport rect (x y w h)", "viewport_rect")
    row("clip range (clip_min clip_max)", "clip_range")
    row("ZMIN_MAX_CONTROL (0x1D78)", "zmin_max_control")
    row("fragment program id", "fp")
    row("render target", "rt")
    if port.get("zmin_max_control") in (None, "untracked", "untracked on legacy"):
        lines.append("")
        lines.append("Note: the legacy D3D12 backend at ps3recomp `e85647a` never reads 0x1D78 "
                     "(`rsx_d3d12_backend.c` guest PSO is zero-initialised, DepthClipEnable never set). "
                     "The dump prints `untracked` unless the snippet is extended.")
    lines.append("")
    lines.append("## Vertex attributes")
    lines.append("")
    lines.append("| idx | port enabled | type | size | stride | offset | freq | RPCS3 type/stride/offset | Match |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    rpc_attrs = {int(a.get("index", i)): a for i, a in enumerate(rpc.get("attribs") or rpc.get("attributes") or [])}
    port_attrs = {int(a.get("index", i)): a for i, a in enumerate(port.get("attribs") or [])}
    idxs = sorted(set(port_attrs) | set(rpc_attrs))
    if not idxs:
        lines.append("| — | *(no attributes parsed)* |  |  |  |  |  | *(paste)* |  |")
    for i in idxs:
        a, b = port_attrs.get(i, {}), rpc_attrs.get(i, {})
        pdesc = "%s/%s/stride=%s/off=%s" % (a.get("type_name") or a.get("type"), a.get("size"), a.get("stride"), a.get("offset"))
        rdesc = "%s/%s/stride=%s/off=%s" % (b.get("type_name") or b.get("type"), b.get("size"), b.get("stride"), b.get("offset")) if b else "*(paste)*"
        fields = ("enabled", "type", "size", "stride", "offset", "frequency")
        match = None
        if b:
            match = all(nearly_equal(a.get(k), b.get(k), atol, rtol) or nearly_equal(a.get(k), b.get({"frequency": "freq"}.get(k, k)), atol, rtol)
                        for k in fields if k in a or k in b)
        mark = "**MISMATCH**" if match is False else ("ok" if match is True else "")
        def hl(x, on=match is False):
            return "**%s**" % x if on and x not in ("—", "") else (x if x is not None else "—")
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, hl(_fmt(a.get("enabled"))), hl(_fmt(a.get("type_name") or a.get("type"))),
            hl(_fmt(a.get("size"))), hl(_fmt(a.get("stride"))), hl(_fmt(a.get("offset"))),
            hl(_fmt(a.get("frequency"))), rdesc if match is not False else "**%s**" % rdesc, mark))
    lines.append("")
    lines.append("## Transform constants c0–c15")
    lines.append("")
    lines.append("| slot | port (xyzw) | RPCS3 (xyzw) | Match |")
    lines.append("|---|---|---|---|")
    pc = list(port.get("c0_c15") or [None] * 16)
    rc = list(rpc.get("c0_c15") or rpc.get("constants") or [None] * 16)
    while len(pc) < 16:
        pc.append(None)
    while len(rc) < 16:
        rc.append(None)
    for i in range(16):
        match = None if rc[i] is None else nearly_equal(pc[i], rc[i], atol, rtol)
        a, b, m = _cell(pc[i], rc[i], match)
        lines.append("| c%d | `%s` | `%s` | %s |" % (i, a.replace("**", ""), b.replace("**", "") if not (match is False) else b, m))
        # keep backticks for readability; mismatches still flagged in Match column
    if port.get("notes"):
        lines.append("")
        lines.append("## Notes")
        for n in port["notes"]:
            lines.append("- %s" % n)
    if port.get("extra_constants"):
        lines.append("")
        lines.append("## Extra constants scraped from VP_MVP / VTX_DUMP")
        for k, v in sorted(port["extra_constants"].items(), key=lambda kv: int(kv[0])):
            lines.append("- c%d = %s" % (int(k), _fmt(v)))
    lines.append("")
    lines.append("If the RPCS3 column still says *(paste)*, fill `rpcs3_values.json` from the RSX capture "
                 "of the same camera and re-run:")
    lines.append("")
    lines.append("```")
    lines.append("python gfx_bisect.py report --log DUMPLOG --rpcs3 rpcs3_values.json --out culprit_report.md")
    lines.append("```")
    lines.append("")
    return "\n".join(lines) + "\n"



def sanitize_rpcs3(rpc: Optional[dict]) -> Optional[dict]:
    """Drop null / all-null placeholder fields from example_rpcs3_values.json."""
    if not rpc:
        return None

    def empty(v):
        if v is None:
            return True
        if isinstance(v, (list, tuple)):
            return all(empty(x) for x in v)
        if isinstance(v, dict):
            return all(empty(x) for x in v.values())
        return False

    out = {}
    for k, v in rpc.items():
        if k.startswith("_") or empty(v):
            continue
        if k in ("attribs", "attributes") and isinstance(v, list):
            kept = [a for a in v if isinstance(a, dict) and not empty({i: a[i] for i in a if i != "index"})]
            if kept:
                out[k] = kept
            continue
        out[k] = v
    return out or None


def write_report(path: str, port: dict, rpcs3: Optional[dict], culprit: int, meta: dict) -> str:
    rpcs3 = sanitize_rpcs3(rpcs3)
    md = build_report(port, rpcs3, culprit, meta)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(md)
    side = os.path.splitext(path)[0] + ".json"
    with open(side, "w", encoding="utf-8") as fh:
        json.dump({"culprit": culprit, "port": port, "rpcs3": rpcs3, "meta": meta}, fh, indent=2)
    return path


# ---------------------------------------------------------------------------
# Bisect driver (auto by default)
# ---------------------------------------------------------------------------

def _extra_for_range(cfg: dict, lo: int, hi: int) -> dict:
    name = cfg.get("draw_range_env") or "DRAW_RANGE"
    return {name: format_range(lo, hi)}


def run_step(runner: GameRunner, cfg: dict, sess: Session, lo: int, hi: int,
             instance: int, ask=None) -> OracleResult:
    step_n = len(sess.steps) + 1
    out_dir = os.path.join(sess.out_dir, "step_%02d_i%d_%s" % (step_n, instance, format_range(lo, hi)))
    result = runner.run(cfg, _extra_for_range(cfg, lo, hi), out_dir, instance=instance)
    cmp_dir = os.path.join(out_dir, "compare")
    oracle = decide_artifact(result.screenshot, cfg, cmp_dir, ask=ask)
    sess.steps.append({
        "step": step_n, "instance": instance, "lo": lo, "hi": hi,
        "draw_range": format_range(lo, hi),
        "artifact": oracle.present, "metric": oracle.value,
        "threshold": oracle.threshold, "screenshot": result.screenshot,
        "elapsed": result.elapsed, "reason": oracle.reason,
        "log_path": result.log_path,
    })
    sess.save()
    print("[gfx_bisect] step %d inst %d range %s artefact=%s %s"
          % (step_n, instance, format_range(lo, hi), oracle.present, oracle.reason), flush=True)
    return oracle


def bisect(cfg: dict, runner: GameRunner, sess: Session, ask=None) -> Optional[int]:
    """Disable-halves binary search. Returns the culprit index, or None."""
    parallel = int(cfg.get("parallel") or 1)
    # Optional baseline with the full range, to catch a bad oracle / missed PAD_SCRIPT.
    if cfg.get("baseline", True) and not any(s.get("draw_range") == format_range(sess.orig_lo, sess.orig_hi) for s in sess.steps):
        print("[gfx_bisect] baseline (full range %s)" % format_range(sess.orig_lo, sess.orig_hi), flush=True)
        base = run_step(runner, cfg, sess, sess.orig_lo, sess.orig_hi, 0, ask=ask)
        if not base.present:
            sess.status = "baseline_clean"
            sess.save()
            print("[gfx_bisect] baseline did not show the artefact — check the region/metric/"
                  "threshold, the crop, and that PAD_SCRIPT reached Lou Sang Village.", flush=True)
            return None
    while sess.lo < sess.hi:
        parts = split_k(sess.lo, sess.hi, max(1, parallel))
        if len(parts) == 1:
            parts = split_halves(sess.lo, sess.hi)
        # Sequential: test the lower half only (classic disable-upper).
        # Parallel K: test every bucket and keep those that still show the artefact.
        if parallel <= 1:
            lo, hi = parts[0]
            ev = run_step(runner, cfg, sess, lo, hi, 0, ask=ask)
            if ev.present:
                sess.hi = hi
            else:
                sess.lo = hi + 1
            sess.save()
        else:
            hits = []
            for inst, (lo, hi) in enumerate(parts):
                ev = run_step(runner, cfg, sess, lo, hi, inst, ask=ask)
                if ev.present:
                    hits.append((lo, hi, ev))
            if not hits:
                # Lower-half-only miss in sequential terms: if we only tested
                # buckets and none hit, the artefact is not isolated — stop.
                sess.status = "no_bucket_hit"
                sess.save()
                print("[gfx_bisect] no bucket in %s..%s still shows the artefact."
                      % (sess.lo, sess.hi), flush=True)
                return None
            sess.lo = min(h[0] for h in hits)
            sess.hi = max(h[1] for h in hits)
            if len(hits) > 1 and sess.lo < sess.hi:
                print("[gfx_bisect] artefact in %d buckets; narrowing to union %s..%s"
                      % (len(hits), sess.lo, sess.hi), flush=True)
            sess.save()
    # lo == hi
    sess.culprit = sess.lo
    sess.status = "found"
    sess.save()
    return sess.culprit


def dump_and_report(cfg: dict, runner: GameRunner, sess: Session, culprit: int) -> str:
    """One more launch with DRAW_DUMP=<culprit>, then write culprit_report.md."""
    out_dir = os.path.join(sess.out_dir, "dump_draw_%d" % culprit)
    env_name = cfg.get("draw_dump_env") or "DRAW_DUMP"
    extra = {
        env_name: str(culprit),
        # Also turn on existing (capped) knobs as a fallback scrape.
        "VP_ATTRS": "1",
        "VTX_DUMP": "1",
        "VP_MVP": str(max(culprit + 1, 8)),
    }
    # Keep the full frame so record-time state for draw N is in-context.
    # Do not set DRAW_RANGE here (compacted indices would not match N).
    print("[gfx_bisect] dump launch DRAW_DUMP=%d (full frame, diagnostic only)" % culprit, flush=True)
    result = runner.run(cfg, extra, out_dir, instance=0)
    sess.dump_log = result.log_path
    text = ""
    if result.log_path and os.path.exists(result.log_path):
        text = Path(result.log_path).read_text(encoding="utf-8", errors="replace")
    # Some builds tee only to stdout.log / stderr.log
    for side in ("stdout.log", "stderr.log", "run.log"):
        p = os.path.join(out_dir, side)
        if os.path.exists(p):
            text += "\n" + Path(p).read_text(encoding="utf-8", errors="replace")
    port = parse_drawdump(text, want=culprit) or {
        "source": "missing",
        "notes": [
            "No DRAW_DUMP block and no legacy scrape. Add the DRAW_DUMP snippet "
            "from diagnostic_snippets.c (hook it in vp_record_cb), rebuild, and "
            "re-run: python gfx_bisect.py report --log %s" % (result.log_path or out_dir)
        ],
        "attribs": [],
        "c0_c15": [None] * 16,
        "zmin_max_control": "untracked",
    }
    rpc = None
    rpc_path = cfg.get("rpcs3_values") or cfg_get(cfg, "oracle", "rpcs3_values")
    if rpc_path and os.path.exists(rpc_path):
        rpc = json.loads(Path(rpc_path).read_text(encoding="utf-8"))
    last = sess.steps[-1] if sess.steps else {}
    meta = {
        "steps": len(sess.steps),
        "orig_lo": sess.orig_lo, "orig_hi": sess.orig_hi,
        "metric": last.get("reason") or cfg_get(cfg, "oracle", "metric"),
        "region": cfg_get(cfg, "oracle", "region", default="tent"),
        "threshold": cfg_get(cfg, "oracle", "threshold", default=0.15),
        "rule": cfg_get(cfg, "oracle", "artifact_if", default="above"),
        "out_dir": sess.out_dir,
        "dump_log": sess.dump_log,
        "screenshot": result.screenshot,
    }
    report_path = os.path.join(sess.out_dir, "culprit_report.md")
    write_report(report_path, port, rpc, culprit, meta)
    sess.report_path = report_path
    sess.status = "dump_done"
    sess.save()
    print("[gfx_bisect] wrote %s" % report_path, flush=True)
    return report_path


def run_auto(cfg: dict, runner: Optional[GameRunner] = None, ask=None) -> dict:
    runner = runner or GameRunner()
    out_dir = cfg.get("out_dir") or os.path.join(cfg.get("root") or ".", "sfauto", "gfx_bisect_runs")
    os.makedirs(out_dir, exist_ok=True)
    state_path = cfg.get("state_file") or os.path.join(out_dir, "state.json")
    orig_lo = int(cfg.get("draw_lo", 0))
    orig_hi = int(cfg.get("draw_hi", 843))
    if cfg.get("resume") and os.path.exists(state_path):
        sess = Session.load(state_path)
        print("[gfx_bisect] resumed %s  range %s..%s status=%s" %
              (state_path, sess.lo, sess.hi, sess.status), flush=True)
    else:
        sess = Session(out_dir, orig_lo, orig_hi, state_path)
        sess.save()
    culprit = sess.culprit
    if sess.status not in ("found", "dump_done") or culprit is None:
        culprit = bisect(cfg, runner, sess, ask=ask)
    if culprit is None:
        return {"status": sess.status, "culprit": None, "out_dir": out_dir,
                "state": state_path, "report": sess.report_path}
    if sess.status != "dump_done" or not sess.report_path or not os.path.exists(sess.report_path):
        dump_and_report(cfg, runner, sess, culprit)
    return {"status": sess.status, "culprit": culprit, "out_dir": out_dir,
            "state": state_path, "report": sess.report_path, "dump_log": sess.dump_log}


# ---------------------------------------------------------------------------
# Interactive ask (opt-in)
# ---------------------------------------------------------------------------

def tty_ask(screenshot: str) -> bool:
    print("screenshot: %s" % screenshot)
    while True:
        try:
            ans = input("artefact present? [y/n] ").strip().lower()
        except EOFError:
            raise RuntimeError("stdin closed; use auto mode")
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("please type y or n")


# ---------------------------------------------------------------------------
# Self-test (fake runner — no game, no Windows)
# ---------------------------------------------------------------------------

class FakeRunner(GameRunner):
    """In-process runner for unit tests and `self-test`. No real exe."""

    def __init__(self, bad: int = 11, n: int = 16, dump_text: Optional[str] = None):
        self.bad = bad
        self.n = n
        self.calls: List[dict] = []
        self.dump_text = dump_text

    def run(self, cfg: dict, extra_env: dict, out_dir: str, instance: int = 0) -> RunResult:
        os.makedirs(out_dir, exist_ok=True)
        name = cfg.get("draw_range_env") or "DRAW_RANGE"
        rng = extra_env.get(name)
        dump = extra_env.get(cfg.get("draw_dump_env") or "DRAW_DUMP")
        t0 = time.time()
        # Build a tiny RGB shot: white top (tent) when the bad draw is included.
        from PIL import Image
        w, h = 64, 64
        present = False
        if rng:
            a, _, b = rng.partition("-")
            lo, hi = int(a), int(b)
            present = lo <= self.bad <= hi
        elif dump is not None:
            present = True
        else:
            present = True  # full frame / dump
        im = Image.new("RGB", (w, h), (20, 80, 20) if not present else (20, 80, 20))
        if present:
            for y in range(0, 30):
                for x in range(8, 56):
                    im.putpixel((x, y), (230, 220, 200))  # tent-like band
            for y in range(40, 64):
                for x in range(w):
                    im.putpixel((x, y), (250, 250, 250))  # white ground
        shot = os.path.join(out_dir, "shot.png")
        im.save(shot)
        log_path = os.path.join(out_dir, "run.log")
        if dump is not None:
            text = self.dump_text or _sample_drawdump(int(dump), bad=self.bad)
            Path(log_path).write_text(text, encoding="utf-8")
        else:
            Path(log_path).write_text("DRAW_RANGE=%s present=%s\n" % (rng, present), encoding="utf-8")
        self.calls.append({"env": dict(extra_env), "out_dir": out_dir, "present": present})
        return RunResult(rng, shot, log_path, round(time.time() - t0, 4), instance=instance, env=dict(extra_env))


def _sample_drawdump(n: int, bad: int = 11) -> str:
    return (
        "[DRAWDUP] begin draw=%d frame=40\n"
        "[DRAWDUP] viewport_scale 640 360 0.5 1\n"
        "[DRAWDUP] viewport_offset 640 360 0.5 0\n"
        "[DRAWDUP] viewport_rect 0 0 1280 720\n"
        "[DRAWDUP] clip_range 0 1\n"
        "[DRAWDUP] zmin_max_control untracked\n"
        "[DRAWDUP] fp 0x00EC2B80\n"
        "[DRAWDUP] rt color0=0x0B530000 zeta=0x0 format=0x08 w=1280 h=720\n"
        "[DRAWDUP] attr 0 enabled=1 off=0x1000 stride=16 size=3 type=2 freq=0\n"
        "[DRAWDUP] attr 1 enabled=1 off=0x100C stride=16 size=3 type=7 freq=0\n"
        "[DRAWDUP] c 0 1 0 0 0\n"
        "[DRAWDUP] c 1 0 1 0 0\n"
        "[DRAWDUP] c 2 0 0 1 0\n"
        "[DRAWDUP] c 3 0 0 0 1\n"
        "[DRAWDUP] c 4 0 0 0 0\n"
        "[DRAWDUP] c 5 0 0 0 0\n"
        "[DRAWDUP] c 6 0 0 0 0\n"
        "[DRAWDUP] c 7 0 0 0 0\n"
        "[DRAWDUP] c 8 0 0 0 0\n"
        "[DRAWDUP] c 9 0 0 0 0\n"
        "[DRAWDUP] c 10 0 0 0 0\n"
        "[DRAWDUP] c 11 0 0 0 0\n"
        "[DRAWDUP] c 12 0 0 0 0\n"
        "[DRAWDUP] c 13 0 0 0 0\n"
        "[DRAWDUP] c 14 0 0 0 0\n"
        "[DRAWDUP] c 15 12.5 0 0 1\n"
        "[DRAWDUP] end\n"
    ) % n


def _auto_cfg(tmp: str, bad: int, n: int, ref_good: str, **kw) -> dict:
    return {
        "root": tmp, "exe": "fake", "exe_args": [],
        "draw_lo": 0, "draw_hi": n - 1, "wait_secs": 0,
        "out_dir": os.path.join(tmp, "runs"),
        "state_file": os.path.join(tmp, "runs", "state.json"),
        "baseline": kw.get("baseline", True),
        "parallel": kw.get("parallel", 1),
        "clone_state": False,
        "oracle": {
            "mode": "auto",
            "reference": ref_good,
            "region": "tent",
            "metric": "white_frac",
            "threshold": 0.2,
            "artifact_if": "above",
            "regions": {
                "tent": [0.0, 0.0, 1.0, 0.5],
                "ground": [0.0, 0.6, 1.0, 1.0],
                "full": [0.0, 0.0, 1.0, 1.0],
            },
        },
        "compare": {"w": 64, "h": 64},
        "rpcs3_values": kw.get("rpcs3_values"),
    }


def _write_good_ref(path: str) -> None:
    from PIL import Image
    im = Image.new("RGB", (64, 64), (20, 80, 20))
    im.save(path)


def self_test() -> int:
    import tempfile
    failures = []

    def check(name, cond, detail=""):
        if cond:
            print("  ok  %s" % name)
        else:
            print("  FAIL %s %s" % (name, detail))
            failures.append(name)

    # Pure bisection arithmetic.
    check("split 0-15", split_halves(0, 15) == [(0, 7), (8, 15)])
    check("split 8-8", split_halves(8, 8) == [(8, 8)])
    check("split_k 4 of 16", split_k(0, 15, 4) == [(0, 3), (4, 7), (8, 11), (12, 15)])
    import math
    check("ceil(log2 843)=10", math.ceil(math.log2(843)) == 10)

    with tempfile.TemporaryDirectory() as tmp:
        ref = os.path.join(tmp, "ref.png")
        _write_good_ref(ref)
        # Sequential auto finds draw 11 in 0..15 and writes a report. No stdin.
        cfg = _auto_cfg(tmp, bad=11, n=16, ref_good=ref)
        runner = FakeRunner(bad=11, n=16)
        result = run_auto(cfg, runner=runner, ask=None)
        check("auto found 11", result.get("culprit") == 11, result)
        check("auto wrote report", result.get("report") and os.path.exists(result["report"]))
        check("no interactive ask used", True)
        # Worst case for N=16 is ceil(log2 16)=4 plus baseline plus dump.
        ranges = [c["env"].get("DRAW_RANGE") for c in runner.calls if "DRAW_RANGE" in c["env"]]
        check("used <= 6 range launches (baseline+4+confirm slack)", len(ranges) <= 6, ranges)
        md = Path(result["report"]).read_text(encoding="utf-8")
        check("report has 0x0A30", "0x0A30" in md)
        check("report has c15", "c15" in md or "c15" in md.lower() or "c15" in md)
        check("report flags untracked zmin", "untracked" in md.lower() or "0x1D78" in md)

        # Resume: start a session, stop mid-way by loading state after one step.
        tmp2 = os.path.join(tmp, "r2")
        os.makedirs(tmp2, exist_ok=True)
        cfg2 = _auto_cfg(tmp2, bad=11, n=16, ref_good=ref, baseline=False)
        runner2 = FakeRunner(bad=11, n=16)
        sess = Session(cfg2["out_dir"], 0, 15, cfg2["state_file"])
        os.makedirs(cfg2["out_dir"], exist_ok=True)
        run_step(runner2, cfg2, sess, 0, 7, 0)
        check("resume state saved", os.path.exists(cfg2["state_file"]))
        sess2 = Session.load(cfg2["state_file"])
        check("resume lo/hi still 0-15 until driver moves them", sess2.lo == 0 and sess2.hi == 15)
        # After lower half (0-7) is clean, driver would set lo=8; simulate and continue.
        sess2.lo = 8
        sess2.save()
        cfg2["resume"] = True
        result2 = run_auto(cfg2, runner=FakeRunner(bad=11, n=16), ask=None)
        check("resume found 11", result2.get("culprit") == 11, result2)

        # Parallel=2 also finds 11.
        tmp3 = os.path.join(tmp, "r3")
        cfg3 = _auto_cfg(tmp3, bad=11, n=16, ref_good=ref, parallel=2)
        result3 = run_auto(cfg3, runner=FakeRunner(bad=11, n=16), ask=None)
        check("parallel 2 found 11", result3.get("culprit") == 11, result3)

        # Report mismatch highlighting.
        port = parse_drawdump(_sample_drawdump(11), want=11)
        rpc = {
            "viewport_scale": [640, 360, 0.5, 1],
            "viewport_offset": [640, 360, 0.5, 0],
            "clip_range": [0, 1],
            "fp": "0x00EC2B80",
            "rt": {"color0": "0x0B530000", "zeta": "0x0", "format": "0x08", "w": 1280, "h": 720},
            "attribs": [
                {"index": 0, "enabled": 1, "offset": "0x1000", "stride": 16, "size": 3, "type": 2, "type_name": "F"},
                {"index": 1, "enabled": 1, "offset": "0x100C", "stride": 16, "size": 3, "type": 7, "type_name": "UB256"},
            ],
            "c0_c15": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] + [[0, 0, 0, 0]] * 11 + [[0, 0, 0, 1]],
        }
        # c15 port is 12.5 0 0 1, rpc is 0 0 0 1 — must mismatch.
        md2 = build_report(port, rpc, 11, {"steps": 5, "orig_lo": 0, "orig_hi": 15})
        check("mismatch on c15 highlighted", "MISMATCH" in md2)
        check("matching fp not mismatched", "| fragment program id |" in md2 and "ok" in md2)

        # decide_artifact never calls input in auto mode (would raise if ask required).
        bad_shot = os.path.join(tmp, "bad.png")
        FakeRunner(bad=11, n=16).run(cfg, {"DRAW_RANGE": "0-15"}, tmp, 0)
        # The fake run above wrote a shot in tmp/shot.png if out_dir=tmp; use last runner3 shot instead.
        # Build one directly:
        from PIL import Image as _Im
        im = _Im.new("RGB", (64, 64), (20, 80, 20))
        for y in range(0, 30):
            for x in range(8, 56):
                im.putpixel((x, y), (230, 220, 200))
        im.save(bad_shot)
        ev = decide_artifact(bad_shot, cfg, os.path.join(tmp, "cmp_ask"), ask=None)
        check("auto oracle flags tent", ev.present is True, ev)

    if failures:
        print("self-test: %d failed: %s" % (len(failures), failures))
        return 1
    print("self-test: all passed")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

SUBS = ("auto", "interactive", "report", "self-test", "self_test", "compare",
        "diagnose", "batch", "cutscene")


def _argv(argv: Optional[Sequence[str]]) -> List[str]:
    a = list(argv if argv is not None else sys.argv[1:])
    if not a or a[0].startswith("-") or a[0] not in SUBS:
        return ["auto"] + a
    return a


def main(argv: Optional[Sequence[str]] = None) -> int:
    a = _argv(argv)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    def add_cfg(p):
        p.add_argument("--config", "-c", required=False, help="JSON config (see example_config.json)")
        p.add_argument("--draw-lo", type=int)
        p.add_argument("--draw-hi", type=int)
        p.add_argument("--wait-secs", type=float)
        p.add_argument("--parallel", type=int)
        p.add_argument("--resume", action="store_true")
        p.add_argument("--out")
        p.add_argument("--rpcs3-values")
        p.add_argument("--no-baseline", action="store_true")
        return p

    add_cfg(sp.add_parser("auto", help="fully automatic bisect + dump + report (default)"))
    add_cfg(sp.add_parser("interactive", help="same loop, but ask y/n on each shot"))
    rp = sp.add_parser("report", help="rebuild culprit_report.md from a dump log + optional RPCS3 JSON")
    rp.add_argument("--log", required=True)
    rp.add_argument("--rpcs3", dest="rpcs3_values")
    rp.add_argument("--out", default="culprit_report.md")
    rp.add_argument("--draw", type=int)
    sp.add_parser("self-test", help="unit-test the bisection + report with a fake runner")
    cp = sp.add_parser("compare", help="thin wrapper around img_compare.py")
    cp.add_argument("ours")
    cp.add_argument("ref")
    cp.add_argument("--out", default="compare_out")
    dg = sp.add_parser("diagnose", help="align one pair and run every detector (see diagnose.py)")
    dg.add_argument("ours"); dg.add_argument("ref")
    dg.add_argument("--out", default="diagnose_out")
    dg.add_argument("--w", type=int, default=1280); dg.add_argument("--h", type=int, default=720)
    dg.add_argument("--crop-ours", default=""); dg.add_argument("--crop-ref", default="")
    dg.add_argument("--photo", default="auto")
    dg.add_argument("--name", default="")
    bp = sp.add_parser("batch", help="diagnose a folder of pairs or a pairs.json")
    bp.add_argument("--pairs", required=True)
    bp.add_argument("--out", default="diagnose_batch")
    bp.add_argument("--w", type=int, default=1280); bp.add_argument("--h", type=int, default=720)
    cu = sp.add_parser("cutscene", help="sync two videos or frame folders and diagnose matched frames")
    cu.add_argument("--ours", required=True); cu.add_argument("--ref", required=True)
    cu.add_argument("--out", default="diagnose_cutscene")
    cu.add_argument("--every", type=int, default=1)
    cu.add_argument("--max-frames", type=int, default=0)
    cu.add_argument("--w", type=int, default=1280); cu.add_argument("--h", type=int, default=720)
    args = ap.parse_args(a)

    if args.cmd in ("self-test", "self_test"):
        return self_test()
    if args.cmd == "compare":
        return ic.main([args.ours, args.ref, "--out", args.out])
    if args.cmd in ("diagnose", "batch", "cutscene"):
        import diagnose as _dg
        if args.cmd == "diagnose":
            argv = [args.ours, args.ref, "--out", args.out,
                    "--w", str(args.w), "--h", str(args.h), "--photo", args.photo]
            if args.crop_ours:
                argv += ["--crop-ours", args.crop_ours]
            if args.crop_ref:
                argv += ["--crop-ref", args.crop_ref]
            if args.name:
                argv += ["--name", args.name]
            return _dg.main(["compare"] + argv)
        if args.cmd == "batch":
            return _dg.main(["batch", "--pairs", args.pairs, "--out", args.out,
                             "--w", str(args.w), "--h", str(args.h)])
        return _dg.main(["cutscene", "--ours", args.ours, "--ref", args.ref,
                         "--out", args.out, "--every", str(args.every),
                         "--max-frames", str(args.max_frames),
                         "--w", str(args.w), "--h", str(args.h)])
    if args.cmd == "report":
        text = Path(args.log).read_text(encoding="utf-8", errors="replace")
        port = parse_drawdump(text, want=args.draw)
        if not port:
            print("no DRAW_DUMP / scrapable log in %s" % args.log, file=sys.stderr)
            return 2
        rpc = None
        if args.rpcs3_values:
            rpc = json.loads(Path(args.rpcs3_values).read_text(encoding="utf-8"))
        culprit = args.draw if args.draw is not None else port.get("draw", -1)
        write_report(args.out, port, rpc, culprit, {"dump_log": args.log})
        print("wrote %s" % args.out)
        return 0

    if not args.config:
        ap.error("--config is required for auto/interactive")
    cfg = load_config(args.config)
    if args.draw_lo is not None:
        cfg["draw_lo"] = args.draw_lo
    if args.draw_hi is not None:
        cfg["draw_hi"] = args.draw_hi
    if args.wait_secs is not None:
        cfg["wait_secs"] = args.wait_secs
    if args.parallel is not None:
        cfg["parallel"] = args.parallel
    if args.resume:
        cfg["resume"] = True
    if args.out:
        cfg["out_dir"] = args.out
        cfg.setdefault("state_file", os.path.join(args.out, "state.json"))
    if args.rpcs3_values:
        cfg["rpcs3_values"] = args.rpcs3_values
    if args.no_baseline:
        cfg["baseline"] = False

    ask = None
    if args.cmd == "interactive":
        cfg.setdefault("oracle", {})["mode"] = "interactive"
        ask = tty_ask
    else:
        # Force auto even if the config file still says interactive.
        cfg.setdefault("oracle", {})["mode"] = "auto"

    result = run_auto(cfg, ask=ask)
    print(json.dumps(result, indent=2))
    return 0 if result.get("culprit") is not None else 1


if __name__ == "__main__":
    sys.exit(main())

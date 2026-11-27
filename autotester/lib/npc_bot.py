#!/usr/bin/env python3
"""NPC-like tactics bot for the Strikeforce TEST COPY (new file; does not change tester.ps1).

Pipeline: compact state JSON -> hard movie/cutscene gate (outside the LLM) ->
reflex every tick + Ollama tactics every N seconds -> pad.txt line
`0xMASK HOLD [lx ly]` (same format as pad_driver.ps1).

Default Ollama: http://127.0.0.1:11434 model qwen3:14b, fallback qwen3.5:4b.
This module was self-tested on the box only. It has not been run against the
game or a real Ollama instance (those live on Saud's PC; Salem runs them).

Player XYZ at 0x008D3800 is the only confirmed gameplay memory value.
Do not invent HP / enemy / facing addresses.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

KUWAIT = timezone(timedelta(hours=3))

# cellPad masks, same as pad_driver.ps1 / buttons.json
MASK_START = 0x0008
MASK_TRIANGLE = 0x1000
MASK_CIRCLE = 0x2000
MASK_CROSS = 0x4000
MASK_SQUARE = 0x8000
MASK_STICK = 0x10000

BUTTON_MASKS = {
    "START": MASK_START,
    "TRIANGLE": MASK_TRIANGLE,
    "CIRCLE": MASK_CIRCLE,
    "CROSS": MASK_CROSS,
    "SQUARE": MASK_SQUARE,
    "STICK": MASK_STICK,
}

RINGWATCH_PAD_DENY = ("ringwatch_work/pad.txt", "ringwatch_work\\pad.txt")

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
DEFAULT_FALLBACK = os.environ.get("OLLAMA_FALLBACK", "qwen3.5:4b")
DEFAULT_TACTIC_SEC = float(os.environ.get("NPC_TACTIC_SEC", "2.5"))
DEFAULT_STUCK_SEC = float(os.environ.get("NPC_STUCK_SEC", "45"))
DEFAULT_POS_EPS = float(os.environ.get("NPC_STUCK_POS_EPS", "50"))

SYSTEM_PROMPT = """You are a tactics brain for a Dynasty Warriors: Strikeforce test bot.
You do NOT press during movies or cutscenes; that gate is enforced outside you.
Reply with ONE JSON object only, no markdown:
{"action":"move|attack|dodge|wait","lx":128,"ly":0,"buttons":[],"hold":12,"goal":"short","reason":"short"}
lx,ly are PS3 left-stick bytes (0-255). Forward is lx=128 ly=0. buttons is a list of names:
SQUARE, TRIANGLE, CROSS, CIRCLE, START. Prefer wait if unsure. Never ask to skip a cutscene.
Never invent enemy or HP values that are null/empty in the state. If enemies is [] and hp is null,
prefer move/wait in the village, not attack.
If stuck_in_respawn is true, action must be move or wait, never attack."""

SYSTEM_PROMPT_HERMES = SYSTEM_PROMPT + """
You are running as a Hermes/Nous-style model. Return ONLY one raw JSON object with the keys
action,lx,ly,buttons,hold,goal,reason. No markdown fences, no XML, no <tool_call> wrapper,
no function-call prose. The HTTP request already asks for JSON.
"""

def system_prompt_for(model: str, style: str = "auto", mission: dict | None = None) -> str:
    s = (style or "auto").lower()
    if s == "json":
        base = SYSTEM_PROMPT
    elif s == "hermes" or (s == "auto" and "hermes" in (model or "").lower()):
        base = SYSTEM_PROMPT_HERMES
    else:
        base = SYSTEM_PROMPT
    mid = None
    goal = None
    if isinstance(mission, dict):
        mid = mission.get("id")
        goal = mission.get("llm_goal") or mission.get("goal_ar")
    if mid or goal:
        base = base + (
            f"\nCurrent mission: {mid or '?'}. Goal: {goal or '?'}. "
            "Play until the goal is met, then stop. If stuck farming a respawn zone, move toward the goal. "
            "Stop BEFORE entering a gate when the mission says so. Never press during movies or cutscenes."
        )
    return base


@dataclass
class MovieState:
    active: bool = False
    unsure: bool = True
    reason: str = "no-log-yet"
    starts: int = 0
    stops: int = 0
    seen_movie_log: bool = False
    last_event: str = ""


@dataclass
class Tactic:
    action: str = "wait"
    lx: int = -1
    ly: int = -1
    buttons: list[str] = field(default_factory=list)
    hold: int = 12
    goal: str = ""
    reason: str = "default-wait"
    source: str = "default"


def kuwait_now() -> str:
    return datetime.now(KUWAIT).strftime("%Y-%m-%d %H:%M:%S") + " Asia/Kuwait (UTC+3)"


def pad_path_forbidden(path: str) -> bool:
    low = re.sub(r"[\\/]+", "/", path).lower()
    return "ringwatch_work/pad.txt" in low


def update_movie_state(state: MovieState, chunk: str | None, log_ok: bool) -> MovieState:
    """Mirror movie_guard.ps1 Update-SfMovieState (PAM movies via [sf-movie] lines)."""
    if not log_ok:
        state.unsure = True
        state.reason = "log-unreadable"
        return state
    if chunk:
        for raw in chunk.splitlines():
            line = raw.strip()
            if "[sf-movie]" in line:
                state.seen_movie_log = True
            if "[sf-movie]" in line and "PlayerStart" in line:
                state.starts += 1
                state.active = True
                state.unsure = False
                state.last_event = "PlayerStart"
                state.reason = "PlayerStart"
            elif "[sf-movie]" in line and ("PlayerStop" in line or "PlayerFinalize" in line):
                state.stops += 1
                state.active = False
                state.unsure = False
                ev = "PlayerFinalize" if "PlayerFinalize" in line else "PlayerStop"
                state.last_event = ev
                state.reason = ev
    if not state.seen_movie_log:
        state.unsure = True
        if not state.reason:
            state.reason = "no-sf-movie-lines"
        elif state.reason == "no-log-yet":
            state.reason = "no-sf-movie-lines"
    return state


def pad_blocked(movie: MovieState) -> tuple[bool, str]:
    """Hard gate: never press during a movie, or when movie state is unsure."""
    if movie.active:
        return True, f"movie-active:{movie.reason}"
    if movie.unsure:
        return True, f"unsure:{movie.reason}"
    return False, "idle"


def log_flags_from_text(text: str) -> dict[str, bool]:
    t = text or ""
    return {
        "loading": bool(re.search(r"Now Loading|/cache/BLUS30471/", t, re.I)),
        "halt": bool(re.search(r"SPU-HALT|0x31C20", t)),
        "eventflag_wait": bool(re.search(r"EventFlagWait", t)),
    }


def compact_state(
    movie: MovieState,
    player: dict[str, Any] | None = None,
    enemies: list | None = None,
    flags: dict[str, bool] | None = None,
    goal: str = "stay_village",
    last_tactic: dict | None = None,
) -> dict[str, Any]:
    p = player or {}
    return {
        "t": kuwait_now(),
        "movie": {
            "active": movie.active,
            "unsure": movie.unsure,
            "reason": movie.reason,
            "starts": movie.starts,
            "stops": movie.stops,
        },
        "player": {
            "x": p.get("x"),
            "y": p.get("y"),
            "z": p.get("z"),
            "hp": p.get("hp"),
            "hp_ea": p.get("hp_ea"),
            "hp_status": p.get("hp_status", "unconfirmed"),
        },
        "enemies": enemies if enemies is not None else [],
        "log_flags": flags or {"loading": False, "halt": False, "eventflag_wait": False},
        "goal": goal,
        "last_tactic": last_tactic,
    }


def parse_tactic(obj: Any, source: str) -> Tactic | None:
    if not isinstance(obj, dict):
        return None
    action = str(obj.get("action") or "wait").lower().strip()
    if action not in ("move", "attack", "dodge", "wait"):
        action = "wait"
    def as_int(v, default, lo, hi):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return default
        return max(lo, min(hi, n))
    buttons = obj.get("buttons") or []
    if not isinstance(buttons, list):
        buttons = []
    names = [str(b).upper() for b in buttons if str(b).upper() in BUTTON_MASKS and str(b).upper() != "STICK"]
    return Tactic(
        action=action,
        lx=as_int(obj.get("lx"), -1, 0, 255) if obj.get("lx") is not None else -1,
        ly=as_int(obj.get("ly"), -1, 0, 255) if obj.get("ly") is not None else -1,
        buttons=names,
        hold=as_int(obj.get("hold"), 12, 1, 180),
        goal=str(obj.get("goal") or ""),
        reason=str(obj.get("reason") or ""),
        source=source,
    )


def extract_json_object(text: str) -> Any:
    if not text:
        raise ValueError("empty")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def ollama_chat(
    state: dict,
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_MODEL,
    timeout: float = 8.0,
    opener=None,
    prompt_style: str = "auto",
) -> tuple[Tactic | None, str, dict]:
    """POST /api/chat. opener is urllib-like for tests.

    Returns (tactic, error_or_empty, meta) where meta has latency_ms and valid_json.
    """
    t0 = time.monotonic()
    meta = {"latency_ms": 0.0, "valid_json": False, "model": model, "prompt_style": prompt_style}
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": "15m",
        "options": {"temperature": 0.2, "num_predict": 128},
        "messages": [
            {"role": "system", "content": system_prompt_for(model, prompt_style, (state or {}).get("mission"))},
            {"role": "user", "content": json.dumps(state, ensure_ascii=False)},
        ],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        host.rstrip("/") + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        if opener is not None:
            raw = opener(req, timeout=timeout)
        else:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        payload = json.loads(raw.decode("utf-8"))
        content = ""
        if isinstance(payload, dict):
            msg = payload.get("message") or {}
            content = msg.get("content") or payload.get("response") or ""
        tactic = parse_tactic(extract_json_object(content), source=f"ollama:{model}")
        meta["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        if tactic is None:
            return None, "unparsed-tactic", meta
        meta["valid_json"] = True
        return tactic, "", meta
    except Exception as e:
        meta["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
        return None, f"{type(e).__name__}: {e}", meta


def reflex_command(tactic: Tactic, flags: dict[str, bool] | None = None) -> dict[str, Any]:
    """Per-tick command from the last tactic. No world-to-stick math (facing unknown)."""
    flags = flags or {}
    if flags.get("halt") or flags.get("eventflag_wait"):
        return {"ok": True, "blocked": False, "line": "", "why": "log-halt-or-wait", "action": "wait"}
    action = tactic.action
    if action == "wait":
        return {"ok": True, "blocked": False, "line": "", "why": tactic.reason or "wait", "action": "wait"}
    lx, ly = tactic.lx, tactic.ly
    hold = tactic.hold if tactic.hold > 0 else 12
    mask = 0
    if action == "move":
        if lx < 0 or ly < 0:
            lx, ly = 128, 0  # pad-forward, same as combat_step.padseq
        mask = MASK_STICK
        line = f"0x{mask:X} {hold} {lx} {ly}"
        return {"ok": True, "blocked": False, "line": line, "why": tactic.reason, "action": "move"}
    if action == "attack":
        names = tactic.buttons or ["SQUARE"]
        for n in names:
            mask |= BUTTON_MASKS.get(n, 0)
        if lx >= 0 and ly >= 0:
            mask |= MASK_STICK
            line = f"0x{mask:X} {hold} {lx} {ly}"
        else:
            line = f"0x{mask:X} {hold}"
        return {"ok": True, "blocked": False, "line": line, "why": tactic.reason, "action": "attack"}
    if action == "dodge":
        # Dodge button is VERIFY (not named in the kit). Strafe with stick only.
        if lx < 0 or ly < 0:
            lx, ly = 0, 128  # left, not inventing a face button
        mask = MASK_STICK
        line = f"0x{mask:X} {max(8, min(hold, 20))} {lx} {ly}"
        return {"ok": True, "blocked": False, "line": line, "why": tactic.reason or "dodge-stick", "action": "dodge"}
    return {"ok": True, "blocked": False, "line": "", "why": "unknown-action", "action": "wait"}


def write_pad(pad_file: str, line: str, dry: bool = False) -> None:
    if pad_path_forbidden(pad_file):
        raise RuntimeError(f"refusing to write ringwatch pad file: {pad_file}")
    if dry:
        return
    path = Path(pad_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(line or "", encoding="utf-8")



def _xyz_tuple(v):
    if v is None:
        return None
    if isinstance(v, dict):
        x, y, z = v.get("x"), v.get("y"), v.get("z")
    else:
        try:
            x, y, z = v[0], v[1], v[2]
        except (TypeError, IndexError, KeyError):
            return None
    if x is None or y is None or z is None:
        # X-only (village partial) can still measure X movement
        if x is None:
            return None
        y = 0.0 if y is None else y
        z = 0.0 if z is None else z
    try:
        return (float(x), float(y), float(z))
    except (TypeError, ValueError):
        return None


def xyz_dist(a, b) -> float | None:
    a, b = _xyz_tuple(a), _xyz_tuple(b)
    if a is None or b is None:
        return None
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def detect_stuck_in_respawn(watch: dict | None) -> dict:
    """KO count rising while objective/area/position progress is unchanged for N seconds.

    Does not invent KO/area/objective. If KO or all progress sensors are missing,
    stuck stays False and why explains the gap. Teleport is not performed here.
    """
    out = {
        "stuck": False,
        "why": "no-watch",
        "ko_rose": False,
        "progress": False,
        "sufficient_data": False,
        "elapsed_sec": 0.0,
        "n_seconds": DEFAULT_STUCK_SEC,
        "recommend": "continue",
    }
    if not watch:
        return out
    n = float(watch.get("n_seconds") or DEFAULT_STUCK_SEC)
    eps = float(watch.get("pos_eps") or DEFAULT_POS_EPS)
    elapsed = float(watch.get("elapsed_sec") or 0)
    out["elapsed_sec"] = elapsed
    out["n_seconds"] = n
    ko_start, ko_now = watch.get("ko_start"), watch.get("ko_now")
    if ko_start is None or ko_now is None:
        out["why"] = "ko-unconfirmed"
        return out
    try:
        ko_start_n, ko_now_n = int(ko_start), int(ko_now)
    except (TypeError, ValueError):
        out["why"] = "ko-unconfirmed"
        return out
    ko_rose = ko_now_n > ko_start_n
    out["ko_rose"] = ko_rose

    area_changed = (
        watch.get("area_start") is not None
        and watch.get("area_now") is not None
        and watch.get("area_start") != watch.get("area_now")
    )
    obj_changed = (
        watch.get("objective_start") is not None
        and watch.get("objective_now") is not None
        and watch.get("objective_start") != watch.get("objective_now")
    )
    dist = xyz_dist(watch.get("xyz_start"), watch.get("xyz_now"))
    pos_changed = dist is not None and dist >= eps
    progress = bool(area_changed or obj_changed or pos_changed)
    out["progress"] = progress
    out["dist"] = dist

    can_measure_progress = (
        dist is not None
        or (watch.get("area_start") is not None and watch.get("area_now") is not None)
        or (watch.get("objective_start") is not None and watch.get("objective_now") is not None)
    )
    if not can_measure_progress:
        out["why"] = "progress-sensors-missing"
        return out
    out["sufficient_data"] = True
    if elapsed < n:
        out["why"] = "watching"
        return out
    if ko_rose and not progress:
        out["stuck"] = True
        out["why"] = "stuck-in-respawn"
        out["recommend"] = "stop_fight_move_on"
        return out
    if not ko_rose:
        out["why"] = "ko-not-rising"
        return out
    out["why"] = "progress-made"
    return out



def default_missions_files() -> list[Path]:
    here = Path(__file__).resolve()
    return [
        Path("/workspace/sf-beta/missions.json"),
        here.parent.parent / "data" / "missions.json",
        Path("missions.json"),
    ]


def resolve_missions_file(path: str | None = None) -> Path:
    if path:
        pth = Path(path)
        if pth.is_file():
            return pth
        raise FileNotFoundError(f"missions file not found: {path}")
    for cand in default_missions_files():
        if cand.is_file():
            return cand
    raise FileNotFoundError("missions.json not found (tried /workspace/sf-beta/missions.json and kit data/)")


def load_missions_file(path: str | None = None) -> dict:
    pth = resolve_missions_file(path)
    data = json.loads(pth.read_text(encoding="utf-8"))
    data["_path"] = str(pth)
    return data


def load_mission(mission_id: str, path: str | None = None) -> dict:
    data = load_missions_file(path)
    mid = (mission_id or "").strip()
    for m in data.get("missions") or []:
        if m.get("id") == mid:
            m = dict(m)
            m["_file"] = data.get("_path")
            return m
    known = [m.get("id") for m in (data.get("missions") or [])]
    raise KeyError(f"unknown mission {mid!r}; known: {known}")


def mission_brief(mission: dict | None) -> dict | None:
    if not mission:
        return None
    return {
        "id": mission.get("id"),
        "name_ar": mission.get("name_ar"),
        "status": mission.get("status"),
        "goal_ar": mission.get("goal_ar"),
        "llm_goal": mission.get("llm_goal"),
        "timeout_sec": mission.get("timeout_sec"),
    }


def _log_blob(state: dict) -> str:
    parts = []
    if state.get("log_tail"):
        parts.append(str(state["log_tail"]))
    for h in state.get("log_hits") or []:
        parts.append(str(h))
    flags = state.get("log_flags") or {}
    if flags.get("halt"):
        parts.append("SPU-HALT 0x31C20")
    if flags.get("eventflag_wait"):
        parts.append("EventFlagWait BLOCKED")
    if flags.get("loading"):
        parts.append("/cache/BLUS30471/")
    return "\n".join(parts)


def _pattern_hit(patterns, blob: str, hits) -> str | None:
    for pat in patterns or []:
        if not pat:
            continue
        if pat in blob:
            return pat
        for h in hits or []:
            if pat in str(h):
                return pat
    return None


def _player_xyz(state: dict):
    p = (state or {}).get("player") or {}
    return _xyz_tuple([p.get("x"), p.get("y"), p.get("z")])


def _screenshot_req(reason: str, label_ar: str, name: str) -> dict:
    return {"needed": True, "reason": reason, "label_ar": label_ar, "suggested_name": name}


def evaluate_mission(mission: dict | None, state: dict, movie: MovieState) -> dict:
    """Check fail conditions first, then goal. Does not invent addresses."""
    out = {
        "status": "running",
        "reason": "",
        "condition_id": None,
        "stop": False,
        "action": None,
        "screenshot_request": None,
        "bug": None,
        "mission_id": (mission or {}).get("id") if mission else None,
    }
    if not mission:
        return out
    state = state or {}
    elapsed = float(state.get("elapsed_sec") or 0)
    blob = _log_blob(state)
    hits = state.get("log_hits") or []
    tstamp = state.get("t") or kuwait_now()

    def fail(cid, reason, shot_ar, shot_name, evidence=None):
        out["status"] = "failed"
        out["reason"] = reason
        out["condition_id"] = cid
        out["stop"] = True
        out["screenshot_request"] = _screenshot_req(reason, shot_ar, shot_name)
        out["bug"] = {
            "mission": mission.get("id"),
            "time_asia_kuwait": tstamp,
            "stage": mission.get("name_ar") or mission.get("id"),
            "reason": reason,
            "condition_id": cid,
            "evidence": evidence or reason,
        }
        return out

    for cond in mission.get("fail_conditions") or []:
        cid = cond.get("id") or cond.get("type")
        ctype = cond.get("type")
        ends = cond.get("ends_mission", True)
        if ctype == "movie_hang":
            sec = float(cond.get("seconds") or 180)
            active_for = float(state.get("movie_active_sec") or 0)
            if movie.active and active_for >= sec:
                if ends:
                    return fail(cid, f"movie-hang:{active_for:.0f}s>={sec:.0f}s", "تعليق فيلم/مقطع", "fail_movie_hang",
                                f"PlayerStart without Stop for {active_for:.0f}s")
        elif ctype == "log_pattern":
            hit = _pattern_hit(cond.get("patterns"), blob, hits)
            if hit:
                if ends:
                    return fail(cid, f"log:{hit}", "تعليق أو شاشة من اللوق", f"fail_{cid}", f"pattern {hit}")
        elif ctype == "hp_zero":
            pl = state.get("player") or {}
            if pl.get("hp_status") == "confirmed" and pl.get("hp") is not None:
                try:
                    if float(pl["hp"]) <= 0:
                        return fail(cid, "hp-zero", "الصحة وصلت صفر", "fail_hp_zero", f"hp={pl['hp']}")
                except (TypeError, ValueError):
                    pass
        elif ctype == "no_position_progress":
            sec = float(cond.get("seconds") or 120)
            eps = float(cond.get("pos_eps") or 50)
            watch = state.get("stuck_watch") or {}
            # Need an explicit start position from the host; do not compare the
            # current XYZ with itself (that would fire on every long tick).
            if watch.get("xyz_start") is None:
                continue
            dist = xyz_dist(watch.get("xyz_start"), watch.get("xyz_now") or _player_xyz(state))
            prog_elapsed = float(watch.get("progress_elapsed_sec") if watch.get("progress_elapsed_sec") is not None else elapsed)
            if dist is not None and prog_elapsed >= sec and dist < eps:
                if ends:
                    return fail(cid, f"no-position-progress:{dist:.1f}<{eps} for {prog_elapsed:.0f}s",
                                "الموضع ما تقدم", "fail_no_progress",
                                f"xyz dist={dist:.1f} eps={eps} elapsed={prog_elapsed:.0f}")
        elif ctype == "timeout":
            limit = float(mission.get("timeout_sec") or cond.get("seconds") or 0)
            if limit and elapsed >= limit:
                return fail(cid, f"timeout:{elapsed:.0f}>={limit:.0f}", "انتهى الوقت", "fail_timeout",
                            f"elapsed {elapsed:.0f}s")
        elif ctype == "stuck_in_respawn":
            stuck = detect_stuck_in_respawn(state.get("stuck_watch"))
            if stuck.get("stuck"):
                if ends:
                    return fail(cid, "stuck-in-respawn", "تعليق في منطقة إعادة ظهور", "fail_stuck_respawn", stuck)
                out["action"] = cond.get("action") or "move_on"
                out["reason"] = "stuck-in-respawn-move-on"
                out["condition_id"] = cid
                if cond.get("screenshot_request", True):
                    out["screenshot_request"] = _screenshot_req(
                        "stuck-in-respawn", "منطقة إعادة ظهور — البوت يوقف القتال ويتحرك", "stuck_respawn"
                    )

    # Goals
    for cond in mission.get("goal_conditions") or []:
        if cond.get("status") in ("draft_VERIFY",) and cond.get("type") not in ("xyz_radius", "log_pattern"):
            continue
        cid = cond.get("id") or cond.get("type")
        ctype = cond.get("type")
        if ctype == "log_pattern":
            pats = cond.get("patterns") or []
            if not pats:
                continue  # VERIFY empty list: cannot fire
            hit = _pattern_hit(pats, blob, hits)
            if hit:
                out["status"] = "goal_met"
                out["reason"] = f"goal-log:{hit}"
                out["condition_id"] = cid
                out["stop"] = True
                out["screenshot_request"] = _screenshot_req(
                    f"goal-log:{hit}", "وصل شرط اللوق — وقف قبل الدخول إن كان هذا عند البوابة", "goal_M_log"
                )
                return out
        elif ctype == "xyz_radius":
            point = cond.get("point")
            radius = cond.get("radius")
            if point is None or radius is None:
                continue  # VERIFY, not filled yet
            here = _player_xyz(state)
            there = _xyz_tuple(point)
            dist = xyz_dist(here, there)
            if dist is not None and dist <= float(radius):
                out["status"] = "goal_met"
                out["reason"] = f"goal-xyz-radius:{dist:.1f}<={radius}"
                out["condition_id"] = cid
                out["stop"] = True
                out["screenshot_request"] = _screenshot_req(
                    "goal-xyz", "وصل نقطة الهدف — حرر الأزرار", "goal_xyz"
                )
                return out
    return out


def tick(
    state: dict,
    movie: MovieState,
    tactic: Tactic,
    pad_file: str,
    dry: bool = False,
    mission: dict | None = None,
) -> dict[str, Any]:
    blocked, why = pad_blocked(movie)
    stuck = detect_stuck_in_respawn(state.get("stuck_watch") if isinstance(state, dict) else None)
    mission_rec = evaluate_mission(mission, state or {}, movie)
    rec = {
        "t": (state or {}).get("t") or kuwait_now(),
        "blocked": blocked,
        "why": why,
        "tactic": asdict(tactic),
        "line": "",
        "action": "wait",
        "stuck_in_respawn": stuck,
        "mission": mission_brief(mission),
        "mission_eval": mission_rec,
        "stop": bool(mission_rec.get("stop")),
        "screenshot_request": mission_rec.get("screenshot_request"),
        "bug": mission_rec.get("bug"),
    }
    # Goal or hard fail: release pads and do not issue a new press.
    if mission_rec.get("stop"):
        write_pad(pad_file, "", dry=dry)
        rec["line"] = ""
        rec["action"] = "goal_met" if mission_rec.get("status") == "goal_met" else "failed"
        rec["why"] = mission_rec.get("reason") or rec["why"]
        rec["blocked"] = False
        return rec
    if blocked:
        write_pad(pad_file, "", dry=dry)
        rec["line"] = ""
        rec["action"] = "gated"
        return rec
    if (stuck.get("stuck") or mission_rec.get("action") == "move_on") and tactic.action in ("attack", "dodge", "wait"):
        # leave farm / keep moving toward the goal
        if tactic.action != "move":
            tactic = Tactic(action="move", hold=45, reason="stuck-in-respawn", source="stuck-detector")
            rec["tactic"] = asdict(tactic)
            rec["why"] = "stuck-in-respawn"
    flags = (state or {}).get("log_flags") or {}
    cmd = reflex_command(tactic, flags)
    write_pad(pad_file, cmd.get("line") or "", dry=dry)
    rec.update({"line": cmd.get("line") or "", "why": cmd.get("why") or why, "action": cmd.get("action")})
    rec["blocked"] = False
    return rec


def maybe_refresh_tactic(
    state: dict,
    current: Tactic,
    last_ts: float,
    interval: float,
    host: str,
    model: str,
    fallback: str,
    opener=None,
    timeout: float = 8.0,
    prompt_style: str = "auto",
) -> tuple[Tactic, float, dict[str, Any]]:
    meta = {"called": False, "model": model, "error": "", "latency_ms": 0.0, "valid_json": False, "prompt_style": prompt_style}
    now = time.monotonic()
    if now - last_ts < interval:
        return current, last_ts, meta
    meta["called"] = True
    t, err, m1 = ollama_chat(state, host=host, model=model, timeout=timeout, opener=opener, prompt_style=prompt_style)
    meta["latency_ms"] = m1.get("latency_ms", 0)
    meta["valid_json"] = m1.get("valid_json", False)
    if t is None and fallback and fallback != model:
        t2, err2, m2 = ollama_chat(state, host=host, model=fallback, timeout=timeout, opener=opener, prompt_style=prompt_style)
        if t2 is not None:
            t, err = t2, ""
            meta["model"] = fallback
            meta["fell_back"] = True
            meta["latency_ms"] = m2.get("latency_ms", 0)
            meta["valid_json"] = m2.get("valid_json", False)
        else:
            err = err + " | fallback: " + err2
            meta["latency_ms"] = (meta["latency_ms"] or 0) + m2.get("latency_ms", 0)
    if t is None:
        meta["error"] = err
        return current, last_ts, meta
    return t, now, meta


# --- self-test (box, no game, no real Ollama) ---

class _FakeOllama:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0

    def __call__(self, req, timeout=8.0):
        self.calls += 1
        body = json.dumps({"message": {"content": json.dumps(self.payload)}}).encode()
        return body


def selftest() -> int:
    fails: list[str] = []

    def check(cond: bool, msg: str):
        if not cond:
            fails.append(msg)

    # Movie gate: no lines yet -> unsure -> no press
    m = MovieState()
    update_movie_state(m, "", True)
    check(m.unsure and not m.active, "empty log should be unsure")
    blk, why = pad_blocked(m)
    check(blk and why.startswith("unsure"), f"unsure gate, got {blk} {why}")

    # After PlayerStart -> blocked
    update_movie_state(m, "[sf-movie] PlayerStart cmd start=1\n", True)
    check(m.active and not m.unsure and m.starts == 1, "start should activate")
    blk, why = pad_blocked(m)
    check(blk and "movie-active" in why, f"active gate, got {why}")

    # After PlayerStop -> idle, presses allowed
    update_movie_state(m, "[sf-movie] PlayerStop at clock 2.02\n", True)
    check((not m.active) and (not m.unsure) and m.stops == 1, "stop should idle")
    blk, why = pad_blocked(m)
    check((not blk) and why == "idle", f"idle expected, got {blk} {why}")

    # In-engine: still idle only if we already saw PAM movies; unsure if never seen
    m2 = MovieState()
    update_movie_state(m2, "some other log\n", True)
    check(m2.unsure, "no [sf-movie] must stay unsure (in-engine cutscene safety)")

    unreadable = MovieState()
    update_movie_state(unreadable, "x", False)
    check(pad_blocked(unreadable)[0], "unreadable log blocks")

    tmp = Path("/tmp/sf-npc-bot-selftest")
    tmp.mkdir(parents=True, exist_ok=True)
    pad = str(tmp / "pad.txt")

    # Gate writes empty pad even if tactic wants a press
    Path(pad).write_text("0x8000 12", encoding="utf-8")
    active = MovieState(active=True, unsure=False, reason="PlayerStart", seen_movie_log=True, starts=1)
    tac = Tactic(action="attack", buttons=["SQUARE"], hold=12, reason="test")
    rec = tick(compact_state(active), active, tac, pad, dry=False)
    check(rec["action"] == "gated" and rec["blocked"], "tick must gate")
    check(Path(pad).read_text(encoding="utf-8") == "", f"pad should be cleared, got {Path(pad).read_text()!r}")

    # Reflex move default forward
    idle = MovieState(active=False, unsure=False, reason="PlayerStop", seen_movie_log=True, starts=1, stops=1)
    move = Tactic(action="move", hold=45, reason="wander")
    rec = tick(compact_state(idle), idle, move, pad)
    check(rec["line"] == "0x10000 45 128 0", f"forward stick, got {rec['line']!r}")

    # Attack square
    atk = Tactic(action="attack", buttons=["SQUARE"], hold=12, reason="hit")
    rec = tick(compact_state(idle), idle, atk, pad)
    check(rec["line"] == "0x8000 12", f"square, got {rec['line']!r}")

    # Halt flag forces wait
    st = compact_state(idle, flags={"loading": False, "halt": True, "eventflag_wait": False})
    rec = tick(st, idle, move, pad)
    check(rec["line"] == "" and rec["action"] == "wait", f"halt should wait, got {rec}")

    # Refuse ringwatch path
    try:
        write_pad("C:/x/sfauto/ringwatch_work/pad.txt", "0x1 1")
        check(False, "ringwatch write should throw")
    except RuntimeError:
        check(True, "ringwatch refused")

    # Fake Ollama
    fake = _FakeOllama({"action": "move", "lx": 200, "ly": 32, "buttons": [], "hold": 20, "goal": "g", "reason": "r"})
    st = compact_state(idle, player={"x": 6499.8, "y": None, "z": None, "hp_status": "unconfirmed"})
    t, ts, meta = maybe_refresh_tactic(st, Tactic(), 0.0, 0.0, "http://127.0.0.1:11434", "qwen3:14b", "qwen3.5:4b", opener=fake)
    check(meta["called"] and t.action == "move" and t.lx == 200 and t.ly == 32, f"ollama tactic {t} {meta}")
    check(fake.calls == 1, "one chat call")

    # Fallback on failure
    def boom(req, timeout=8.0):
        raise urllib.error.URLError("down")

    calls = {"n": 0}

    def once_fail_then_ok(req, timeout=8.0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("14b-oom")
        return json.dumps({"message": {"content": json.dumps({"action": "wait", "reason": "fb"})}}).encode()

    t, ts, meta = maybe_refresh_tactic(st, Tactic(action="move"), 0.0, 0.0, "http://127.0.0.1:11434", "qwen3:14b", "qwen3.5:4b", opener=once_fail_then_ok)
    check(meta.get("fell_back") and t.action == "wait" and t.source.endswith("qwen3.5:4b"), f"fallback {t} {meta}")

    # Keep last tactic when both fail
    prev = Tactic(action="move", lx=128, ly=0, hold=10, reason="kept")
    t, ts, meta = maybe_refresh_tactic(st, prev, 0.0, 0.0, "http://127.0.0.1:11434", "qwen3:14b", "qwen3.5:4b", opener=boom)
    check(t.reason == "kept" and meta["error"], f"keep last {t} {meta}")
    check(meta.get("latency_ms") is not None, "latency recorded on failure")
    check(meta.get("valid_json") is False, "invalid json on total failure")

    # stuck-in-respawn detector
    xyz = [100.0, 10.0, 20.0]
    r = detect_stuck_in_respawn({
        "ko_start": 300, "ko_now": 339,
        "xyz_start": xyz, "xyz_now": xyz,
        "elapsed_sec": 60, "n_seconds": 45, "pos_eps": 50,
    })
    check(r["stuck"] and r["why"] == "stuck-in-respawn" and r["sufficient_data"], f"stuck expected {r}")

    r = detect_stuck_in_respawn({
        "ko_start": 300, "ko_now": 339,
        "xyz_start": xyz, "xyz_now": [400.0, 10.0, 20.0],
        "elapsed_sec": 60, "n_seconds": 45, "pos_eps": 50,
    })
    check((not r["stuck"]) and r["progress"] and r["why"] == "progress-made", f"moved, not stuck {r}")

    r = detect_stuck_in_respawn({
        "ko_start": 339, "ko_now": 339,
        "xyz_start": xyz, "xyz_now": xyz,
        "elapsed_sec": 60, "n_seconds": 45,
    })
    check((not r["stuck"]) and r["why"] == "ko-not-rising", f"ko flat {r}")

    r = detect_stuck_in_respawn({
        "ko_start": None, "ko_now": None,
        "xyz_start": xyz, "xyz_now": xyz,
        "elapsed_sec": 60, "n_seconds": 45,
    })
    check((not r["stuck"]) and r["why"] == "ko-unconfirmed", f"no ko {r}")

    r = detect_stuck_in_respawn({
        "ko_start": 10, "ko_now": 20,
        "xyz_start": None, "xyz_now": None,
        "area_start": None, "area_now": None,
        "objective_start": None, "objective_now": None,
        "elapsed_sec": 60, "n_seconds": 45,
    })
    check((not r["stuck"]) and r["why"] == "progress-sensors-missing", f"no sensors {r}")

    r = detect_stuck_in_respawn({
        "ko_start": 10, "ko_now": 40,
        "xyz_start": xyz, "xyz_now": xyz,
        "area_start": "1", "area_now": "3",
        "elapsed_sec": 60, "n_seconds": 45,
    })
    check((not r["stuck"]) and r["progress"], f"area changed {r}")

    r = detect_stuck_in_respawn({
        "ko_start": 10, "ko_now": 40,
        "xyz_start": xyz, "xyz_now": xyz,
        "elapsed_sec": 20, "n_seconds": 45,
    })
    check((not r["stuck"]) and r["why"] == "watching", f"too early {r}")

    st_stuck = compact_state(idle)
    st_stuck["stuck_watch"] = {
        "ko_start": 300, "ko_now": 339,
        "xyz_start": [100, 10, 20], "xyz_now": [100, 10, 20],
        "elapsed_sec": 60, "n_seconds": 45, "pos_eps": 50,
    }
    rec = tick(st_stuck, idle, Tactic(action="attack", buttons=["SQUARE"], hold=12, reason="farm"), pad)
    check(rec["action"] == "move" and rec["stuck_in_respawn"]["stuck"], f"tick override {rec}")
    check(rec["line"].startswith("0x10000"), f"move line {rec['line']}")

    check("raw JSON" in system_prompt_for("hermes3:8b", "auto"), "auto hermes prompt")
    check("raw JSON" not in system_prompt_for("qwen3:14b", "json"), "qwen stays default")
    check("raw JSON" in system_prompt_for("qwen3:14b", "hermes"), "forced hermes style")

    evp = str(tmp / "events.jsonl")
    ev_lines = [
        {"ollama": {"model": "qwen3:14b", "latency_ms": 100, "valid_json": True}},
        {"ollama": {"model": "qwen3:14b", "latency_ms": 300, "valid_json": False, "error": "x"}},
        {"stuck_in_respawn": {"stuck": True}},
    ]
    Path(evp).write_text("\n".join(json.dumps(x) for x in ev_lines) + "\n", encoding="utf-8")
    summ = summarize_events(evp)
    check(summ["ollama_calls"] == 2 and summ["valid_json"] == 1, f"summarize counts {summ}")
    check(summ["valid_json_rate"] == "1/2" and summ["stuck_events"] == 1, f"summarize rate {summ}")
    check(summ["latency_ms"]["median"] == 200, f"median {summ}")

    # Missions: load, goal, timeout, fail paths
    m1 = load_mission("M1")
    check(m1["id"] == "M1" and "بوابة" in (m1.get("name_ar") or ""), f"load M1 {m1.get('id')}")
    check(any("5443" in str(c.get("patterns")) for c in m1["goal_conditions"] if c.get("type")=="log_pattern"), "M1 has 5443 pattern")
    draft = load_mission("M2")
    check(draft.get("status") == "draft_VERIFY", "M2 is draft")

    idle = MovieState(active=False, unsure=False, reason="PlayerStop", seen_movie_log=True, starts=1, stops=1)
    # goal met via log pattern
    st_g = compact_state(idle, player={"x": 100, "y": 10, "z": 20, "hp_status": "unconfirmed"})
    st_g["elapsed_sec"] = 30
    st_g["log_hits"] = ["[fs] open '/dev_hdd1/cache/BLUS30471/5443' -> fd 5"]
    rec = tick(st_g, idle, Tactic(action="move", hold=45), pad, mission=m1)
    check(rec["action"] == "goal_met" and rec.get("stop") and rec["line"] == "", f"goal log {rec}")
    check(Path(pad).read_text(encoding="utf-8") == "", "pads released on goal")
    check(rec.get("screenshot_request") and rec["screenshot_request"].get("needed"), "goal asks screenshot")

    # timeout fail
    st_t = compact_state(idle, player={"x": 100, "y": 10, "z": 20, "hp_status": "unconfirmed"})
    st_t["elapsed_sec"] = 500  # M1 timeout 480
    rec = tick(st_t, idle, Tactic(action="move"), pad, mission=m1)
    check(rec["action"] == "failed" and rec["mission_eval"]["condition_id"] == "timeout", f"timeout {rec['mission_eval']}")
    check(rec.get("bug") and rec["bug"].get("reason", "").startswith("timeout"), f"bug event {rec.get('bug')}")

    # SPU hang is fail, not goal, even if 5443 also present
    st_h = compact_state(idle, player={"x": 1, "y": 1, "z": 1, "hp_status": "unconfirmed"})
    st_h["elapsed_sec"] = 20
    st_h["log_hits"] = ["BLUS30471/5443", "SPU-HALT at LS 0x31C20"]
    rec = tick(st_h, idle, Tactic(action="move"), pad, mission=m1)
    check(rec["action"] == "failed" and "SPU-HALT" in (rec["mission_eval"].get("reason") or rec.get("why") or ""), f"halt wins {rec['mission_eval']}")

    # movie hang fail
    mv = MovieState(active=True, unsure=False, reason="PlayerStart", seen_movie_log=True, starts=1, stops=0)
    st_mv = compact_state(mv)
    st_mv["elapsed_sec"] = 10
    st_mv["movie_active_sec"] = 200
    rec = tick(st_mv, mv, Tactic(action="attack"), pad, mission=m1)
    check(rec["action"] == "failed" and rec["line"] == "" and "movie-hang" in (rec.get("why") or ""), f"movie hang {rec}")

    # hp 0 only if confirmed
    st_hp = compact_state(idle, player={"x": 1, "y": 1, "z": 1, "hp": 0, "hp_status": "unconfirmed"})
    st_hp["elapsed_sec"] = 10
    rec = tick(st_hp, idle, Tactic(action="move"), pad, mission=m1)
    check(rec["action"] != "failed" or rec["mission_eval"]["condition_id"] != "hp_zero", f"unconfirmed hp must not fail {rec['mission_eval']}")
    st_hp["player"]["hp_status"] = "confirmed"
    rec = tick(st_hp, idle, Tactic(action="move"), pad, mission=m1)
    check(rec["action"] == "failed" and rec["mission_eval"]["condition_id"] == "hp_zero", f"confirmed hp0 {rec['mission_eval']}")

    # xyz goal when point filled (synthetic mission)
    mxyz = {
        "id": "MX", "name_ar": "اختبار", "timeout_sec": 100,
        "goal_conditions": [{"id": "g", "type": "xyz_radius", "point": [100, 10, 20], "radius": 15}],
        "fail_conditions": [],
    }
    st_x = compact_state(idle, player={"x": 105, "y": 10, "z": 20, "hp_status": "unconfirmed"})
    st_x["elapsed_sec"] = 5
    rec = tick(st_x, idle, Tactic(action="move"), pad, mission=mxyz)
    check(rec["action"] == "goal_met", f"xyz goal {rec}")
    st_x["player"] = {"x": 500, "y": 10, "z": 20, "hp_status": "unconfirmed"}
    rec = tick(st_x, idle, Tactic(action="move"), pad, mission=mxyz)
    check(rec["action"] != "goal_met" and not rec.get("stop"), f"far from point {rec}")

    # no-position-progress fail
    st_n = compact_state(idle, player={"x": 10, "y": 1, "z": 1, "hp_status": "unconfirmed"})
    st_n["elapsed_sec"] = 130
    st_n["stuck_watch"] = {"xyz_start": [10, 1, 1], "xyz_now": [10, 1, 1], "progress_elapsed_sec": 130, "pos_eps": 50}
    rec = tick(st_n, idle, Tactic(action="move"), pad, mission=m1)
    check(rec["action"] == "failed" and rec["mission_eval"]["condition_id"] == "no_position_progress", f"no progress {rec['mission_eval']}")

    # existing usage: no mission -> no stop
    rec = tick(compact_state(idle), idle, Tactic(action="wait"), pad, mission=None)
    check(not rec.get("stop") and rec["action"] == "wait", f"no mission still works {rec}")

    if fails:
        print("SELFTEST FAIL:")
        for f in fails:
            print(" -", f)
        return 1
    print("npc_bot.py selftest: ok")
    print("  movie gate blocks Start/unsure/unreadable; idle after Stop")
    print("  pad format 0x10000 45 128 0 / 0x8000 12; ringwatch refused")
    print("  fake Ollama + fallback to qwen3.5:4b; last tactic kept on error")
    print("  stuck-in-respawn: KO rise + no progress -> stop fight; missing KO/sensors -> no fire")
    print("  missions: M1 load, goal log 5443, timeout/hang/hp/progress fails, pads released")
    print("  not tested on the game or a real Ollama host")
    return 0


def summarize_events(path: str) -> dict:
    """Bake-off helper: latency, valid-JSON counts, stuck events from npc_bot.jsonl."""
    lines = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    lat = []
    valid = 0
    calls = 0
    models = {}
    stuck_n = 0
    for rec in lines:
        om = rec.get("ollama") if isinstance(rec, dict) else None
        if isinstance(om, dict) and (om.get("model") or om.get("latency_ms") is not None or "valid_json" in om):
            calls += 1
            if om.get("valid_json"):
                valid += 1
            if om.get("latency_ms") is not None:
                try:
                    lat.append(float(om["latency_ms"]))
                except (TypeError, ValueError):
                    pass
            m = om.get("model")
            if m:
                models[str(m)] = models.get(str(m), 0) + 1
        st = rec.get("stuck_in_respawn") if isinstance(rec, dict) else None
        if isinstance(st, dict) and st.get("stuck"):
            stuck_n += 1
    lat_s = sorted(lat)

    def pct(ps):
        if not lat_s:
            return None
        i = min(len(lat_s) - 1, max(0, int(round((ps / 100) * (len(lat_s) - 1)))))
        return lat_s[i]

    median = None
    if lat_s:
        mid = len(lat_s) // 2
        median = lat_s[mid] if len(lat_s) % 2 else (lat_s[mid - 1] + lat_s[mid]) / 2
    return {
        "file": path,
        "events": len(lines),
        "ollama_calls": calls,
        "valid_json": valid,
        "valid_json_rate": f"{valid}/{calls}" if calls else "0/0",
        "models": models,
        "latency_ms": {
            "n": len(lat_s),
            "min": lat_s[0] if lat_s else None,
            "median": median,
            "max": lat_s[-1] if lat_s else None,
            "p95": pct(95),
        },
        "stuck_events": stuck_n,
        "note": "Rates are counts from this file only, not a success percentage of the port. In-game outcome (XYZ, shots) is recorded by the host run, not invented here.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Strikeforce NPC bot brain (test copy)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--tick", action="store_true", help="one tick: read --state JSON, write --pad")
    ap.add_argument("--state", help="state JSON path (or stdin if -)")
    ap.add_argument("--pad", help="pad.txt path")
    ap.add_argument("--tactic", help="optional tactic JSON path (else last_tactic in state, else wait)")
    ap.add_argument("--events", help="append JSONL decisions here")
    ap.add_argument("--summarize-events", help="print bake-off metrics from a npc_bot.jsonl file")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ollama", action="store_true", help="refresh tactic from Ollama before reflex")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--fallback", default=DEFAULT_FALLBACK)
    ap.add_argument("--prompt-style", default="auto", choices=["auto", "json", "hermes"],
                    help="auto uses the Hermes JSON-only addendum when the model name contains hermes")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--mission", default="", help="mission id from missions.json (e.g. M1)")
    ap.add_argument("--missions-file", default="", help="path to missions.json (default /workspace/sf-beta/missions.json)")
    ap.add_argument("--list-missions", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if getattr(args, "summarize_events", None):
        print(json.dumps(summarize_events(args.summarize_events), ensure_ascii=False, indent=2))
        return 0
    if args.list_missions:
        data = load_missions_file(args.missions_file or None)
        for m in data.get("missions") or []:
            print(f"{m.get('id')}\t{m.get('status')}\t{m.get('name_ar')}")
        return 0
    if not args.tick:
        print("usage: npc_bot.py --selftest | --tick --state FILE --pad FILE | --mission ID | --list-missions | --summarize-events FILE", file=sys.stderr)
        return 2
    if not args.state or not args.pad:
        print("--tick needs --state and --pad", file=sys.stderr)
        return 2
    raw = sys.stdin.read() if args.state == "-" else Path(args.state).read_text(encoding="utf-8")
    state = json.loads(raw)
    mission = None
    if args.mission:
        mission = load_mission(args.mission, args.missions_file or None)
        brief = mission_brief(mission)
        # Do not overwrite a richer mission already in state; fill if missing.
        if not state.get("mission"):
            state["mission"] = brief
        else:
            state["mission"] = {**brief, **(state.get("mission") or {})}
            state["mission"]["id"] = mission.get("id")
            if mission.get("llm_goal"):
                state["mission"]["llm_goal"] = mission.get("llm_goal")
    mv = state.get("movie") or {}
    movie = MovieState(
        active=bool(mv.get("active")),
        unsure=bool(mv.get("unsure", True)),
        reason=str(mv.get("reason") or "from-state"),
        starts=int(mv.get("starts") or 0),
        stops=int(mv.get("stops") or 0),
        seen_movie_log=not bool(mv.get("unsure", True)) or bool(mv.get("starts") or mv.get("stops")),
    )
    tac_obj = None
    if args.tactic:
        tac_obj = json.loads(Path(args.tactic).read_text(encoding="utf-8"))
    elif state.get("last_tactic"):
        tac_obj = state["last_tactic"]
    tactic = parse_tactic(tac_obj, "input") if tac_obj else Tactic()
    ollama_meta = None
    if args.ollama and not movie.active and not movie.unsure:
        new_t, err, m1 = ollama_chat(state, host=args.host, model=args.model, timeout=args.timeout, prompt_style=args.prompt_style)
        used = args.model
        meta = dict(m1)
        if new_t is None and args.fallback:
            new_t, err2, m2 = ollama_chat(state, host=args.host, model=args.fallback, timeout=args.timeout, prompt_style=args.prompt_style)
            if new_t is not None:
                used = args.fallback
                err = ""
                meta = dict(m2)
                meta["fell_back"] = True
            else:
                err = err + " | " + err2
                meta["fallback_error"] = err2
        ollama_meta = {
            "error": err,
            "model": used if new_t else None,
            "latency_ms": meta.get("latency_ms"),
            "valid_json": bool(meta.get("valid_json")),
            "prompt_style": args.prompt_style,
            "fell_back": bool(meta.get("fell_back")),
        }
        if new_t:
            tactic = new_t
    rec = tick(state, movie, tactic, args.pad, dry=args.dry_run, mission=mission)
    if ollama_meta:
        rec["ollama"] = ollama_meta
    rec["tactic"] = asdict(tactic)
    if args.events:
        ev = Path(args.events)
        ev.parent.mkdir(parents=True, exist_ok=True)
        with ev.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(rec, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

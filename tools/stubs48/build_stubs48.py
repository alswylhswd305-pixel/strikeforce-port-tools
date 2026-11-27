#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Build stubs48.md / stubs48.json from box-local sources only. Read-only on inputs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import datetime
from collections import defaultdict
from pathlib import Path

KUWAIT = datetime.timezone(datetime.timedelta(hours=3), name="Asia/Kuwait")


def repo_root() -> Path:
    """tools/stubs48/build_stubs48.py -> repository root."""
    return Path(__file__).resolve().parents[2]


def default_paths() -> dict:
    """Repo-relative defaults. Optional inputs may be absent on a fresh clone."""
    root = repo_root()
    nid = root / "tools" / "nid-autolink"
    progress = root / "tools" / "progress-src"
    return {
        "out": root / "stubs48-out",
        "report_csv": nid / "pc-results" / "report.csv",
        "autolink_line": nid / "pc-results" / "autolink_line.txt",
        "callgraph": nid / "pc-results" / "v2" / "callgraph.json",
        "imports": progress / "out" / "EBOOT.imports.json",
        "functions": progress / "out" / "EBOOT.functions.json",
        "ranked": nid / "v2-rank" / "master_ranked.csv",
        "spec_root": nid / "docs" / "hle_spec",
        "findings_dir": progress / "runs",
        "log_search": nid / "pc-results" / "v2" / "log_search.txt",
        "log_roots": [
            root / "tools" / "testloop",
            root / "tools" / "voicefreeze",
            root / "autotester",
        ],
    }


def _pick_path(cli: str | None, env: str, default: Path) -> Path:
    if cli:
        return Path(cli).expanduser()
    val = os.environ.get(env)
    if val:
        return Path(val).expanduser()
    return default


OUT = Path()
REPORT_CSV = Path()
AUTOLINK_LINE = Path()
CALLGRAPH = Path()
IMPORTS = Path()
FUNCTIONS = Path()
RANKED = Path()
SPEC_ROOT = Path()
FINDINGS_DIR = Path()
LOG_SEARCH = Path()
LOG_ROOTS: list[Path] = []


def apply_paths(args=None) -> None:
    """Fill path globals from CLI, then env, then repo-relative defaults."""
    global OUT, REPORT_CSV, AUTOLINK_LINE, CALLGRAPH, IMPORTS
    global FUNCTIONS, RANKED, SPEC_ROOT, FINDINGS_DIR, LOG_SEARCH, LOG_ROOTS
    d = default_paths()
    ns = args
    OUT = _pick_path(getattr(ns, "out", None), "SF_STUBS48_OUT", d["out"])
    REPORT_CSV = _pick_path(getattr(ns, "report_csv", None), "SF_NID_REPORT_CSV", d["report_csv"])
    AUTOLINK_LINE = _pick_path(getattr(ns, "autolink_line", None), "SF_AUTOLINK_LINE", d["autolink_line"])
    CALLGRAPH = _pick_path(getattr(ns, "callgraph", None), "SF_CALLGRAPH", d["callgraph"])
    IMPORTS = _pick_path(getattr(ns, "imports", None), "SF_IMPORTS_JSON", d["imports"])
    FUNCTIONS = _pick_path(getattr(ns, "functions", None), "SF_FUNCTIONS_JSON", d["functions"])
    RANKED = _pick_path(getattr(ns, "ranked", None), "SF_RANKED_CSV", d["ranked"])
    SPEC_ROOT = _pick_path(getattr(ns, "spec_root", None), "SF_SPEC_ROOT", d["spec_root"])
    FINDINGS_DIR = _pick_path(getattr(ns, "findings_dir", None), "SF_FINDINGS_DIR", d["findings_dir"])
    LOG_SEARCH = _pick_path(getattr(ns, "log_search", None), "SF_LOG_SEARCH", d["log_search"])
    roots: list[Path] = []
    cli_roots = list(getattr(ns, "log_root", None) or [])
    if cli_roots:
        roots.extend(Path(x).expanduser() for x in cli_roots)
    env_roots = os.environ.get("SF_STUBS48_LOG_ROOTS", "")
    if env_roots and not cli_roots:
        roots.extend(Path(x).expanduser() for x in env_roots.split(os.pathsep) if x)
    if not roots:
        roots = list(d["log_roots"])
    LOG_ROOTS = roots


apply_paths()

HLE_NEW = re.compile(
    r"\[hle-lr\]\s+new\s+nid=(0x[0-9A-Fa-f]+)\s+lr=(0x[0-9A-Fa-f]+)(?:.*?tid=(\d+))?(?:.*?ret=(0x[0-9A-Fa-f]+))?",
    re.I,
)
HLE_DUMP = re.compile(
    r"\[hle-lrc\]\s+\d+\s+(0x[0-9A-Fa-f]+)\s+(0x[0-9A-Fa-f]+)\s+(\d+)",
    re.I,
)
UNRESOLVED = re.compile(r"UNRESOLVED NID (0x[0-9A-Fa-f]+)", re.I)
FS_OPEN = re.compile(r"\[fs\] open '([^']+)'")
MOVIE_PAM = re.compile(r"movie/movie(\d+)\.pam", re.I)
STORY_RE = re.compile(r"Story:\s*(.+?)(?:\"|$)")
CACHE_RE = re.compile(r"/cache/BLUS30471/(\w+)")

# Lifecycle-inferred stages (ASSUMED labels; line ranges CONFIRMED from sf_lifecycle summaries)
STAGES = {
    "voicediag1786_saud_20261127-172741_stderr.log": [
        (1, 12232, "boot", "إقلاع/أفلام/قوائم", "lifecycle summary: boot L1-L12232"),
        (12233, 40514, "stage_A", "المرحلة أ (أول تحميل عالم، كاش 5050)", "lifecycle: A L12233-L40514, cache 5050"),
        (40515, 10**12, "stage_B", "المرحلة ب (تحميل تالي، كاش 5053؛ بعدها تعليق)", "lifecycle: B L40515-end, cache 5053"),
    ],
    "saud_blackhang_1817_stderr.log": [
        (1, 34750, "boot", "إقلاع/أفلام/قوائم (Story: Shu Chapter 1 عند L9613)", "lifecycle: boot L1-L34750; Story L9613"),
        (34751, 47343, "stage_A", "المرحلة أ (كاش 5050)", "lifecycle: A L34751-L47343"),
        (47344, 106821, "stage_B", "المرحلة ب (كاش 5053)", "lifecycle: B L47344-L106821"),
        (106822, 10**12, "stage_C", "المرحلة ج (كاش 4667؛ تعليق القرية)", "lifecycle: C L106822-end, cache 4667"),
    ],
    "sfrace1786_20261127-190111_stderr.log": [
        (1, 22363, "boot", "إقلاع/أفلام/قوائم", "lifecycle_39940: boot L1-L22363"),
        (22364, 175199, "stage_A", "المرحلة أ (كاش 5050)", "lifecycle_39940: A L22364-L175199, cache 5050"),
        (175200, 10**12, "stage_B", "المرحلة ب (كاش 5053؛ نهاية اللوق انتظار WAIT_SIGNAL)", "lifecycle_39940: B L175200-end, cache 5053"),
    ],
}

# Logs we scan but do not use for counts / first-hit / classification.
# diag_lines is a filtered extract of voicediag (different line numbers).
# selftest is a fixture. sfrace_39940.log is a DMA dump, no HLE.
SKIP_FOR_EVIDENCE = {
    "voicediag1786_diag_lines.txt",
    "diag_lines.txt",
    "sample_stderr.log",
    "mid_movie.log",
    "sfrace_39940.log",
    "coverage_out.json",
    "coverage_out2.json",
    "coverage_out3.json",
}

# Handler-log name patterns for each stub (stdout / sf-movie). Distinctive enough to avoid cousins.
NAME_PATTERNS = {
    "0x2E3CCB5E": [r"GraphicsAdapterSetPreferredFormat"],
    "0x7C8DFF3B": [r"\[cellSail\] AddDescriptor", r"PlayerAddDescriptor"],
    "0x0ABB318B": [r"DescriptorCreateDatabase", r"CreateDatabase\("],
    "0x28336E89": [r"DescriptorDestroyDatabase", r"DestroyDatabase\("],
    "0x76B1A425": [r"SetAutoSelection"],
    "0xC427890C": [r"SetInitialKeyLayout"],
    "0xF0EC3CCC": [r"SetLayoutMode"],
    "0x7F21C918": [r"AddSupportLanguage"],
    "0xB53C54FA": [r"SetKeyLayoutOption"],
    "0x41F20828": [r"DisableDimmer"],
    "0xF3B4B43E": [r"SetInitialInputDevice"],
    "0x53E39DF3": [r"SetSeparateWindowOption"],
    "0xE800F586": [r"RegisterForceFinishCallback"],
    "0x75370397": [r"SetInitialScale"],
    "0xFF0A21B7": [r"\[cellKb\] Read", r"cellKbRead"],
    "0xBE07F05E": [r"GetSecondBufferInfo"],
    "0x99EFE171": [r"IsSecondBufferNeeded"],
    "0x21397818": [r"SetFlipCommand"],
    "0x4692AB35": [r"AudioOutConfigure"],
    "0xC96E89E9": [r"AudioOutSetCopyControl"],
    "0xEF9D42D5": [r"GetSizeKB"],
    "0xCE4374F6": [r"PatchCheck"],
    "0x8107277C": [r"RescSetBufferAddress", r"SetBufferAddress"],
    "0xEDADD797": [r"SaveDataDelete2", r"cellSaveDataDelete2"],
    "0x2796FDF3": [r"cellFsRmdir", r"\[fs\] rmdir"],
    "0xBEF554A4": [r"cellFsUtime"],
    "0x89456724": [r"Avc2InitParam"],
    "0xCCF0AEFF": [r"Avc2SetAttribute"],
    "0x16FF9BA0": [r"StartVoiceDetection"],
    "0x178982D9": [r"StopVoiceDetection"],
    "0xE035F7D6": [r"sceNpBasicGetEvent", r"NpBasic\] GetEvent"],
    "0x04372385": [r"GetFriendListEntry"],
    "0x4026EAC5": [r"RegisterContextSensitiveHandler"],
    "0xEB7A3D84": [r"GetChatRestrictionFlag"],
    "0x19BCE18C": [r"TusPollAsync", r"sceNpTusPollAsync"],
    "0xB0A59804": [r"sys_net.*bind", r"\[sys_net\] bind"],
    "0x88F03575": [r"setsockopt"],
    "0x6DB6E8CD": [r"socketclose"],
    "0xFDB8F926": [r"sys_net_free_thread_context"],
    "0x139A9E9B": [r"sys_net_initialize_network_ex"],
    "0xEF87A695": [r"sys_lwcond_signal(?!_)"],
    "0xE9A1BD84": [r"sys_lwcond_signal_all"],
    "0x1C9A942C": [r"sys_lwcond_destroy"],
    "0xC3476D0C": [r"sys_lwmutex_destroy"],
    "0x96328741": [r"_sys_process_at_Exitspawn", r"at_Exitspawn"],
    "0x2C847572": [r"_sys_process_atexitspawn", r"atexitspawn"],
    "0xA2C7BA64": [r"sys_prx_exitspawn_with_level"],
    "0xE0DA8EFD": [r"sys_spu_image_close"],
}

# Risk notes (ASSUMED unless a researched spec says otherwise)
RISK_NOTES = {
    "0xEF87A695": {
        "risk": "high",
        "label": "ASSUMED",
        "why_en": "Winning handler classified stub (returns a constant). Voicediag SF_HLE_LRLOG shows tens of thousands of calls, including through stage changes. If the body does not actually wake waiters, stage teardown / village hang is a plausible victim. VERIFY by reading the winning handler on the test copy and checking whether a waiter is released.",
        "why_ar": "مصنّفة هيكل فارغ، وانطلبت 363392 مرة في جلسة SFRACE (23832 في voicediag). إذا ما توقّظ المنتظرين، تعليق القرية محتمل. يحتاج تحقق من جسم الدالة.",
        "bugs": ["village hang"],
    },
    "0xE9A1BD84": {
        "risk": "high",
        "label": "ASSUMED",
        "why_en": "Companion of sys_lwcond_signal (wake all). Same hang-risk if used at stage teardown and the body is a no-op.",
        "why_ar": "نفس عائلة إشارة الشرط. خطر على تعليق المرحلة إذا الجسم فاضي.",
        "bugs": ["village hang"],
    },
    "0x1C9A942C": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "Destroy of an lwcond. A no-op may leak waiters across stage re-creation (same EA reuse pattern already CONFIRMED for SPURS tasksets). Not shown as the root of the hang by itself.",
        "why_ar": "تدمير شرط خفيف: إذا فاضي، المنتظرين ممكن يبقون بعد إعادة استخدام العنوان.",
        "bugs": ["village hang"],
    },
    "0xC3476D0C": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "lwmutex destroy. Voicediag dump shows a handful of calls. A no-op can leave a mutex live at a reused address after a stage change.",
        "why_ar": "تدمير ميوتكس خفيف، وفي اللوق انطلبت مرات قليلة. خطر إعادة استخدام العنوان.",
        "bugs": ["village hang"],
    },
    "0xBE07F05E": {
        "risk": "high",
        "label": "ASSUMED",
        "why_en": "Second ATRAC buffer info. Game tests r3 at both call sites (callgraph CONFIRMED). A stub that returns 0 without filling the out-struct can skip or corrupt streaming. Linked in autolink notes to the mixer / 6ch AT3P path. VERIFY with SF_HLE_LRLOG + atrac-validator.",
        "why_ar": "معلومات المخزن الثاني للصوت. اللعبة تفحص الرجع، والجسم الفاضي ممكن يخرب الستريمنغ.",
        "bugs": ["audio"],
    },
    "0x99EFE171": {
        "risk": "high",
        "label": "ASSUMED",
        "why_en": "IsSecondBufferNeeded: game branches on r3>0 vs not (callgraph CONFIRMED). A constant 0 means 'not needed' and would skip the second buffer path. Candidate for thin/wrong BGM if a second buffer is required. VERIFY by logging r3 and whether the 6ch stream requests a second buffer.",
        "why_ar": "ترجع 0 يعني «ما يحتاج مخزن ثاني». إذا الأغنية تحتاجه، الصوت يخف أو يخرب.",
        "bugs": ["audio"],
    },
    "0x4692AB35": {
        "risk": "high",
        "label": "ASSUMED",
        "why_en": "Spec (researched 2026-11-27) verdict needs-real-impl: returning 0 is OK but the requested channel config is discarded; later GetConfiguration always reports 2ch LPCM. Candidate link to the 6ch mixer leak. VERIFY with a log of the config the game passes.",
        "why_ar": "المواصفة تقول لازم تتطبّق إعدادات القنوات؛ الحين ترجع نجاح وتتجاهل الطلب (مرشحة لصوت 6 قنوات).",
        "bugs": ["audio"],
    },
    "0xC96E89E9": {
        "risk": "low",
        "label": "ASSUMED",
        "why_en": "Spec verdict ok-setting-sink. Called once at boot (copy control=2). Unlikely to cause the thin-voice / BGM bugs by itself.",
        "why_ar": "إعداد نسخ الصوت؛ تنطلب مرة بالإقلاع. خطرها منخفض.",
        "bugs": [],
    },
    "0x2E3CCB5E": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "Called at every boot movie (movie000/001/007/013). Port logs the call; movies already play in v5 so a constant-success may be enough, but preferred format is ignored. Owned-by-salem (movies).",
        "why_ar": "تنطلب مع كل فيلم بالإقلاع. الأفلام تشتغل في v5، بس صيغة العرض تنتجاهل.",
        "bugs": ["graphics", "movies"],
    },
    "0x7C8DFF3B": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "AddDescriptor is logged next to every boot movie. v5 plays those movies, so a success return may be enough if the port tracks descriptors itself. Still a stub per the 17:19 scan. Owned-by-salem.",
        "why_ar": "تنطلب مع كل فيلم. الأفلام تشتغل، بس الدالة مصنّفة هيكل فارغ.",
        "bugs": ["movies"],
    },
    "0x0ABB318B": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "Sail descriptor database create. Call sites test r3<0 (callgraph). A success-with-no-database could break later in-stage movies (movie013 already opens and shows 0 frames in 1817 — not proven related).",
        "why_ar": "إنشاء قاعدة واصفات الفيلم. اللعبة تفحص الرجع. فيلم 013 طلع صفر صور (العلاقة غير مؤكدة).",
        "bugs": ["movies"],
    },
    "0x28336E89": {
        "risk": "low",
        "label": "ASSUMED",
        "why_en": "Destroy database. Failure to free is a leak, not a likely visible boot bug.",
        "why_ar": "تدمير قاعدة الواصفات. تسريب محتمل أكثر من عطل ظاهر.",
        "bugs": ["movies"],
    },
    "0x76B1A425": {
        "risk": "low",
        "label": "ASSUMED",
        "why_en": "SetAutoSelection. Setting sink unless the game later reads the flag back from a structure the stub does not write.",
        "why_ar": "إعداد اختيار تلقائي للأفلام. خطر منخفض إلا إذا اللعبة تقرأ القيمة لاحقاً.",
        "bugs": ["movies"],
    },
    "0x21397818": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "Low-level flip command. Called during boot in voicediag. Display still updates, so another flip path is likely live. A no-op here could still skip a barrier or cause a frame of stale data (tearing/hitch). VERIFY whether the port's flip is implemented only via a different NID.",
        "why_ar": "أمر قلب الإطار. الشاشة تتحرك، فغالباً في طريق ثاني. ممكن يسبب تقطيع إذا هالطريق هو المعتمد.",
        "bugs": ["graphics"],
    },
    "0x8107277C": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "cellRescSetBufferAddress. If the game uses RESC to scale and this stub ignores the address, output can be wrong size/offset (blue strip / edge). Not confirmed used at runtime.",
        "why_ar": "عنوان مخزن التحويل الرسومي. إذا اللعبة تستخدمه ويتجاهله البورت، الحواف أو الشريط الأزرق محتملة.",
        "bugs": ["graphics"],
    },
    "0xFF0A21B7": {
        "risk": "medium",
        "label": "ASSUMED",
        "why_en": "cellKbRead: game tests r3==0 (callgraph). A stub that returns 0 without writing key data looks like 'no keys'. Called in voicediag (boot). Keyboard init is logged. Unlikely to freeze the village; can break name entry.",
        "why_ar": "قراءة الكيبورد. ترجع نجاح فاضي = ما في مفاتيح. تنطلب بالإقلاع. تؤثر على إدخال الاسم أكثر من تعليق القرية.",
        "bugs": [],
    },
}

# default risk for the rest
DEFAULT_SINK = {
    "risk": "low",
    "label": "ASSUMED",
    "why_en": "Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.",
    "why_ar": "غالباً إعداد أو شبكة/أونلاين. ترجع 0 تكفي للعب بدون نت. نتحقق إذا اللعبة تقرأ مخرجات فاضي.",
    "bugs": [],
}
OSK_SINK = {
    "risk": "low",
    "label": "ASSUMED",
    "why_en": "OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.",
    "why_ar": "إعدادات لوحة المفاتيح على الشاشة؛ المواصفة تقول ترجع 0 كافية.",
    "bugs": [],
}
for nid in (
    "0x7F21C918", "0xC427890C", "0xB53C54FA", "0xF0EC3CCC",
    "0xE800F586", "0x75370397", "0x41F20828", "0xF3B4B43E", "0x53E39DF3",
):
    RISK_NOTES[nid] = dict(OSK_SINK)

# Teleport / exercise hints for IMPORTED-NOT-SEEN
EXERCISE = {
    "cellSail": "boot movies (movie000, 001, 007, 002/013). No teleport; start a tester run and let the intro play. Do not skip cutscenes.",
    "cellAtrac": "same boot movies (6ch on movie001/007) and then village BGM. Stay in the village / blacksmith after load; no teleport required.",
    "cellGcmSys": "any in-game frame (village or blacksmith). After the player is in the village, TELEPORT_SAVE to fill Y/Z, then stay put.",
    "cellResc": "same as graphics: title into village, then blacksmith camera. If still unseen, dump with SF_HLE_LRLOG through the first flip.",
    "cellSysutil": "OSK cluster: title / name-entry / options. 1817 already hit SetLayoutMode + SetInitialKeyLayout during boot. Re-run boot with SF_HLE_LRLOG to catch the rest (AddSupportLanguage, KeyLayoutOption, …).",
    "sys_io": "cellKbRead: boot + any text prompt. Already seen in voicediag; confirm poll rate with LRLOG.",
    "cellOskExtUtility": "same title / name-entry as OSK. Autolink first-hit LRs exist from older PC logs.",
    "cellGame": "boot (BootCheck path). GetSizeKB / PatchCheck may only run on install/patch or first-boot without a ready cache — try a tester state with empty game-data (copy, not Saud's save).",
    "sysPrxForUser": "lwcond/lwmutex: already called in voicediag if hooked. atexit/exitspawn/spu_image_close: end of process or SPU image unload — run until a clean quit, and also across a stage change (A→B).",
    "sys_fs": "Rmdir/Utime: likely save-delete or cache maintenance. Try a tester-only save delete in the in-game save menu (not Saud's real save). Do not delete his save.",
    "cellSaveData": "cellSaveDataDelete2: in-game save-delete on the tester profile only.",
    "cellSysutilAvc2": "PS3 voice-chat APIs. Probably never reached in offline play. Optional: open any in-game 'party / voice' menu if one exists; otherwise leave as IMPORTED-NOT-SEEN.",
    "sceNp": "PlayStation Network friends/events. Init already runs at boot; GetEvent / friend list may need the NP menus or a stub-online flag. Do not enable real PSN. Log-only run through the title's online/trophy menus.",
    "sceNpTus": "TUS (title user storage) poll — online. Same as sceNp.",
    "sys_net": "socket/bind/setsockopt/init: CELL_SYSMODULE_NET is already loaded at boot. These may run during sceNp Init. Catch with SF_HLE_LRLOG from process start. Conditional net NIDs (the other 7) are not in this stub list.",
}


def now_kw():
    return datetime.datetime.now(tz=KUWAIT).strftime("%Y-%m-%d %H:%M Asia/Kuwait (UTC+3)")


def nid_norm(s: str) -> str:
    h = s.lower().replace("0x", "")
    return "0x" + h.upper().zfill(8)


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_stubs():
    with REPORT_CSV.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["status"].strip().lower() == "stub"]
    assert len(rows) == 48, f"expected 48 stubs, got {len(rows)}"
    for r in rows:
        r["nid"] = nid_norm(r["nid_hex"])
    return rows


def load_callgraph():
    if not CALLGRAPH.is_file():
        return {}
    return json.loads(CALLGRAPH.read_text(encoding="utf-8"))


def load_functions_index():
    if not FUNCTIONS.is_file():
        return []
    data = json.loads(FUNCTIONS.read_text(encoding="utf-8"))
    ranges = []
    for item in data:
        a = int(item["start"], 16)
        b = int(item["end"], 16)
        ranges.append((a, b, item["start"], item["end"]))
    ranges.sort()
    return ranges


def fn_at(ranges, addr_hex: str):
    if not addr_hex:
        return None
    a = int(addr_hex, 16)
    # binary search
    lo, hi = 0, len(ranges)
    while lo < hi:
        mid = (lo + hi) // 2
        if ranges[mid][1] <= a:
            lo = mid + 1
        else:
            hi = mid
    if lo < len(ranges) and ranges[lo][0] <= a < ranges[lo][1]:
        s, e, sh, eh = ranges[lo]
        return {"fn_start": "0x%08X" % s, "fn_end": "0x%08X" % e, "label": "fn_%08X" % s}
    return None


def stage_for(log_name: str, line_no: int):
    # stdout line numbers do not match stderr lifecycle ranges.
    # Early 1817/gfx stdout (OSK, Sail, AudioOut) happens while the boot
    # taskset 0x00DB8F80 is still the one being signalled — ASSUMED boot.
    if log_name.endswith("stdout.log") and line_no < 8000:
        if "blackhang_1817" in log_name or "sf-gfx-runs" in log_name:
            return {
                "id": "boot",
                "ar": "إقلاع/أفلام/قوائم (من لوق stdout؛ رقم السطر مو نفس stderr)",
                "evidence": "ASSUMED boot: early stdout, boot taskset still active",
                "label": "ASSUMED",
            }
    rules = STAGES.get(log_name)
    if not rules:
        return None
    for a, b, sid, ar, ev in rules:
        if a <= line_no <= b:
            return {"id": sid, "ar": ar, "evidence": ev, "label": "ASSUMED"}
    return None


def iter_log_files():
    """Unique-by-md5 candidate logs on the box."""
    candidates = []
    roots = list(LOG_ROOTS) or default_paths()["log_roots"]
    skip_dir = {"node_modules", ".git", "__pycache__"}
    want_suffix = {".log", ".txt", ".json"}
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dir]
            for fn in filenames:
                p = Path(dirpath) / fn
                n = fn.lower()
                if p.suffix.lower() not in want_suffix:
                    continue
                if any(
                    k in n
                    for k in (
                        "stderr",
                        "stdout",
                        "unresolved",
                        "findings",
                        "diag_lines",
                        "hle",
                        "coverage",
                    )
                ) or n.endswith(".log"):
                    # skip RPCS3 logs — not the port
                    if "rpcs3" in n:
                        continue
                    # skip selftest tiny fixtures unless needed
                    candidates.append(p)
    # dedup by md5, prefer shorter path / canonical locations
    seen = {}
    order = []
    for p in candidates:
        try:
            digest = md5(p)
        except OSError:
            continue
        if digest not in seen:
            seen[digest] = p
            order.append((digest, p, p.stat().st_size))
        else:
            # keep the more canonical one
            old = seen[digest]
            score = (
                0 if "testloop" in str(p) else 1,
                0 if "_logs" not in str(p).replace("\\", "/") else 1,
                len(str(p)),
            )
            old_score = (
                0 if "testloop" in str(old) else 1,
                0 if "_logs" not in str(old).replace("\\", "/") else 1,
                len(str(old)),
            )
            if score < old_score:
                seen[digest] = p
    # refresh order paths
    out = []
    done = set()
    for digest, _, _ in order:
        p = seen[digest]
        if digest not in done:
            out.append((digest, p, p.stat().st_size))
            done.add(digest)
    return out


def compile_name_rx(stubs):
    per = {}
    for s in stubs:
        pats = NAME_PATTERNS.get(s["nid"], [])
        if pats:
            per[s["nid"]] = re.compile("|".join("(?:%s)" % p for p in pats))
    return per


def scan_logs(stubs, log_files):
    nid_set = {s["nid"] for s in stubs}
    name_rx = compile_name_rx(stubs)
    # also a combined NID regex
    nid_alt = {s["nid"]: re.compile(re.escape(s["nid"]) + r"|" + re.escape(s["nid"][2:]), re.I) for s in stubs}

    results = {s["nid"]: {
        "hits": [],  # compact records
        "count_by_log": {},
        "lrs": defaultdict(int),
        "first": None,
        "stages": set(),
        "movies": set(),
        "sources": set(),
    } for s in stubs}

    scanned = []
    hle_hook_logs = []

    for digest, path, size in log_files:
        rel = str(path)
        name = path.name
        kind = "json" if path.suffix.lower() == ".json" else "text"
        rec = {
            "path": rel,
            "name": name,
            "md5": digest,
            "bytes": size,
            "hle_lr_lines": 0,
            "hle_lrc_lines": 0,
            "used_for_evidence": name not in SKIP_FOR_EVIDENCE and not name.startswith("coverage_"),
        }
        if kind == "json" or not rec["used_for_evidence"]:
            # findings.json handled separately; extracts/fixtures listed only
            if kind != "json" and not rec["used_for_evidence"]:
                rec["skipped_reason"] = "extract/fixture/non-HLE dump; not used for counts or first-hit"
            scanned.append(rec)
            continue

        # For diag_lines extract of voicediag: still parse, but we'll mark as extract
        is_diag_extract = "diag_lines" in name
        current_movie = None
        # [hle-lrc] bursts. Later bursts can be fragmented (SFRACE gen 80/81);
        # use the block with the most NID+LR pairs (the last complete census).
        dump_blocks = []  # {start, n, data}
        cur_dump = None
        prev_lrc_line = None
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                m = MOVIE_PAM.search(line)
                if m:
                    current_movie = "movie%03d.pam" % int(m.group(1))
                m = HLE_DUMP.search(line)
                if m:
                    rec["hle_lrc_lines"] += 1
                    if cur_dump is None or prev_lrc_line is None or i > prev_lrc_line + 1:
                        if cur_dump is not None:
                            dump_blocks.append(cur_dump)
                        cur_dump = {"start": i, "n": 0, "data": {}}
                    prev_lrc_line = i
                    nid = nid_norm(m.group(1))
                    lr = nid_norm(m.group(2))
                    cnt = int(m.group(3))
                    cur_dump["data"].setdefault(nid, {})[lr] = cnt
                    cur_dump["n"] += 1
                    cur_dump["end"] = i
                    continue
                m = HLE_NEW.search(line)
                if m:
                    rec["hle_lr_lines"] += 1
                    nid = nid_norm(m.group(1))
                    if nid in nid_set:
                        lr = nid_norm(m.group(2))
                        slot = results[nid]
                        slot["lrs"][lr] = max(slot["lrs"].get(lr, 0), 1)
                        slot["sources"].add("hle-lr")
                        slot["count_by_log"][rel] = slot["count_by_log"].get(rel, 0) + 1
                        st = stage_for(name, i)
                        ev = {
                            "log": rel,
                            "line": i,
                            "kind": "hle-lr-new",
                            "lr": lr,
                            "tid": m.group(3),
                            "ret": m.group(4),
                            "text": line.strip()[:240],
                            "stage": st,
                            "movie": current_movie,
                        }
                        if slot["first"] is None or (
                            slot["first"].get("kind") == "hle-lrc"
                            and slot["first"]["line"] > i
                        ):
                            # prefer first new-line (earlier, has stage)
                            if slot["first"] is None or slot["first"].get("kind") != "hle-lr-new":
                                slot["first"] = ev
                            elif i < slot["first"]["line"]:
                                slot["first"] = ev
                        if slot["first"] and slot["first"].get("kind") == "hle-lr-new":
                            pass
                        # always keep a short list of first-new (one per lr)
                        if not any(h.get("lr") == lr and h.get("kind") == "hle-lr-new" for h in slot["hits"]):
                            slot["hits"].append(ev)
                        if st:
                            slot["stages"].add(st["id"])
                        if current_movie:
                            slot["movies"].add(current_movie)
                    continue
                m = UNRESOLVED.search(line)
                if m:
                    nid = nid_norm(m.group(1))
                    if nid in nid_set:
                        slot = results[nid]
                        slot["sources"].add("unresolved")
                        slot["count_by_log"][rel] = slot["count_by_log"].get(rel, 0) + 1
                        st = stage_for(name, i)
                        ev = {
                            "log": rel,
                            "line": i,
                            "kind": "unresolved",
                            "text": line.strip()[:240],
                            "stage": st,
                            "movie": current_movie,
                        }
                        if slot["first"] is None:
                            slot["first"] = ev
                        if not any(h.get("kind") == "unresolved" and h.get("log") == rel for h in slot["hits"]):
                            slot["hits"].append(ev)
                        if st:
                            slot["stages"].add(st["id"])
                    continue
                # name patterns (handlers / sf-movie)
                for nid, rx in name_rx.items():
                    if rx.search(line):
                        slot = results[nid]
                        slot["sources"].add("handler-log")
                        slot["count_by_log"][rel] = slot["count_by_log"].get(rel, 0) + 1
                        st = stage_for(name, i)
                        ev = {
                            "log": rel,
                            "line": i,
                            "kind": "handler-log",
                            "text": line.strip()[:240],
                            "stage": st,
                            "movie": current_movie,
                        }
                        if slot["first"] is None:
                            slot["first"] = ev
                        if len([h for h in slot["hits"] if h.get("kind") == "handler-log" and h.get("log") == rel]) < 3:
                            slot["hits"].append(ev)
                        if st:
                            slot["stages"].add(st["id"])
                        if current_movie:
                            slot["movies"].add(current_movie)
        if cur_dump is not None:
            dump_blocks.append(cur_dump)
        last_dump, last_dump_start, last_pairs = {}, None, 0
        if dump_blocks:
            best = max(dump_blocks, key=lambda b: (b["n"], b["start"]))
            last_dump, last_dump_start, last_pairs = best["data"], best["start"], best["n"]
        rec["hle_lrc_last_dump_start"] = last_dump_start
        rec["hle_lrc_last_dump_pairs"] = last_pairs
        rec["hle_lrc_dump_blocks"] = len(dump_blocks)
        for nid, lrmap in last_dump.items():
            if nid not in nid_set:
                continue
            slot = results[nid]
            slot["sources"].add("hle-lrc")
            slot.setdefault("lrc_by_log", {})[rel] = {
                "total": sum(lrmap.values()),
                "lrs": dict(lrmap),
                "dump_start_line": last_dump_start,
                "dump_pairs": last_pairs,
            }
            # Do not tag one-shot boot calls with the dump's later stage.
            # If the last complete census total is >10, the NID was still
            # live when that dump was taken (ASSUMED in-between stages too).
            total = sum(lrmap.values())
            if total > 10 and last_dump_start:
                st = stage_for(name, last_dump_start)
                if st:
                    slot["stages"].add(st["id"])
                    first_st = (slot.get("first") or {}).get("stage")
                    # fill A if we have boot..B
                    order = ["boot", "stage_A", "stage_B", "stage_C"]
                    ids = {st["id"]}
                    if first_st:
                        ids.add(first_st["id"])
                    if "boot" in ids and "stage_B" in ids:
                        slot["stages"].add("stage_A")
        if rec["hle_lr_lines"] or rec["hle_lrc_lines"]:
            hle_hook_logs.append(rel)
        scanned.append(rec)
    return results, scanned, hle_hook_logs


def parse_findings(stubs, results):
    names = {s["nid"]: s["name"] for s in stubs}
    # fuzzy: cellSail.GraphicsAdapterSetPreferredFormat <-> cellSailGraphicsAdapterSetPreferredFormat
    def match_func(func: str, name: str) -> bool:
        a = func.replace(".", "").lower().lstrip("_")
        b = name.replace(".", "").lower().lstrip("_")
        return a == b or a.endswith(b) or b.endswith(a)

    for p in sorted(FINDINGS_DIR.glob("*findings.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        funcs = d.get("hle_funcs") or []
        unresolved = [nid_norm(x) for x in (d.get("unresolved_nids") or [])]
        for s in stubs:
            nid = s["nid"]
            hit = [f for f in funcs if match_func(f, s["name"])]
            if hit:
                slot = results[nid]
                slot["sources"].add("findings.json hle_funcs")
                ev = {
                    "log": str(p),
                    "line": None,
                    "kind": "findings-hle_funcs",
                    "text": ", ".join(hit),
                    "stage": None,
                    "movie": None,
                }
                if slot["first"] is None:
                    slot["first"] = ev
                if not any(h.get("kind") == "findings-hle_funcs" for h in slot["hits"]):
                    slot["hits"].append(ev)
            if nid in unresolved:
                slot = results[nid]
                slot["sources"].add("findings.json unresolved")
                ev = {
                    "log": str(p),
                    "line": None,
                    "kind": "findings-unresolved",
                    "text": nid,
                    "stage": None,
                    "movie": None,
                }
                if not any(h.get("kind") == "findings-unresolved" for h in slot["hits"]):
                    slot["hits"].append(ev)


def attach_autolink(stubs, results):
    for s in stubs:
        nid = s["nid"]
        slot = results[nid]
        calls = (s.get("calls") or "").strip()
        src = (s.get("calls_src") or "").strip()
        lr = (s.get("lr") or "").strip()
        if calls and calls not in ("", "-"):
            slot["sources"].add("autolink-report-17:19")
            slot["autolink_calls"] = calls
            slot["autolink_calls_src"] = src
            slot["autolink_lr"] = lr or None
            ev = {
                "log": str(REPORT_CSV),
                "line": None,
                "kind": "autolink-report",
                "lr": lr or None,
                "text": f"calls={calls} src={src} lr={lr}",
                "stage": None,
                "movie": None,
                "note": "From nid_autolink 2026-11-27 17:19 scan of 241 PC logs; raw files not all on the box.",
            }
            if slot["first"] is None:
                slot["first"] = ev
            slot["hits"].append(ev)


def classify(stubs, results, cg, fn_ranges, ranked):
    imports = json.loads(IMPORTS.read_text(encoding="utf-8"))
    imp_nids = {nid_norm(x["nid"]) for x in imports}
    ranked_by = {}
    if RANKED.is_file():
        with RANKED.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                ranked_by[nid_norm(r["nid"])] = r

    out = []
    for s in stubs:
        nid = s["nid"]
        slot = results[nid]
        info = cg["imports"].get(s["nid_hex"]) or cg["imports"].get(nid) or {}
        if not info:
            # try any key
            for k, v in cg["imports"].items():
                if nid_norm(k) == nid:
                    info = v
                    break
        sites = []
        for site in info.get("sites") or []:
            caller = site.get("caller")
            fn = fn_at(fn_ranges, caller) if caller else None
            ret = site.get("ret_test")
            sites.append({
                "site": site.get("site"),
                "caller": caller,
                "caller_fn": fn,
                "depth": site.get("depth"),
                "ret_test": ret,
            })
        # counts: last [hle-lrc] dump per hooked log (cumulative). Prefer the
        # session with the largest last-dump total; never sum two sessions.
        lrc_by_log = slot.get("lrc_by_log") or {}
        handler_total = sum(slot["count_by_log"].values()) if slot["count_by_log"] else 0
        runtime_count = 0
        count_log = None
        last_lrs = {}
        if lrc_by_log:
            count_log, best = max(lrc_by_log.items(), key=lambda kv: kv[1]["total"])
            runtime_count = best["total"]
            last_lrs = best["lrs"]
        elif handler_total:
            runtime_count = handler_total
        slot["lrs"] = last_lrs or slot["lrs"]

        box_runtime = bool(slot["sources"] & {"hle-lr", "hle-lrc", "handler-log", "unresolved"})
        offbox_runtime = bool(slot["sources"] & {"autolink-report-17:19", "findings.json hle_funcs", "findings.json unresolved"})
        if box_runtime:
            klass = "CALLED"
            klass_label = "CONFIRMED"
        elif offbox_runtime:
            klass = "CALLED"
            klass_label = "CONFIRMED"
            # still CALLED; evidence is the 17:19 report / findings on the box, raw play log may be off-box
        else:
            klass = "IMPORTED-NOT-SEEN"
            klass_label = "CONFIRMED"  # confirmed not seen in available logs; not confirmed unused

        risk = RISK_NOTES.get(nid, DEFAULT_SINK)
        # bump if ret_tested and still default
        if risk is DEFAULT_SINK or risk.get("risk") == "low":
            if any((si.get("ret_test") or {}) for si in sites) and klass == "IMPORTED-NOT-SEEN":
                # keep low unless we have a stronger note
                pass

        rk = ranked_by.get(nid, {})
        first = slot["first"]
        stage_ids = sorted(slot["stages"])
        # If first is a dump at end-of-log, try to recover stage from first hle-lr-new hit
        first_stage = None
        if first and first.get("stage"):
            first_stage = first["stage"]
        else:
            for h in slot["hits"]:
                if h.get("stage"):
                    first_stage = h["stage"]
                    break

        rec = {
            "nid": nid,
            "name": s["name"],
            "module": s["lib"],
            "priority_in_report": s.get("priority"),
            "score_in_report": int(s["score"]) if s.get("score") else None,
            "handler": s.get("handler"),
            "handler_where": s.get("where"),
            "why_stub": s.get("why"),
            "imported": nid in imp_nids,
            "import_stub_addr": s.get("stub_addr"),
            "class": klass,
            "class_evidence_label": klass_label,
            "runtime_count_best": runtime_count,
            "runtime_count_note": (
                f"last cumulative [hle-lrc] dump of {count_log} (CONFIRMED); other hooked sessions listed in lrc_by_log"
                if count_log
                else (
                    "handler-log / first-hit counts; no [hle-lrc] dump for this NID (may under-count)"
                    if handler_total
                    else "no on-box count"
                )
            ),
            "lrs": {k: v for k, v in last_lrs.items()} if last_lrs else {k: v for k, v in slot["lrs"].items()},
            "lrc_by_log": lrc_by_log,
            "first_hit": first,
            "hits_sample": slot["hits"][:8],
            "stages_seen": stage_ids,
            "first_stage": first_stage,
            "movies_seen": sorted(slot["movies"]),
            "sources": sorted(slot["sources"]),
            "autolink_calls": slot.get("autolink_calls"),
            "autolink_calls_src": slot.get("autolink_calls_src"),
            "autolink_lr": slot.get("autolink_lr"),
            "static": {
                "call_sites": info.get("call_sites"),
                "distinct_callers": info.get("distinct_callers"),
                "min_depth_from_entry": info.get("min_depth_from_entry"),
                "callers_reachable_direct": info.get("callers_reachable_direct"),
                "ret_tested_sites": info.get("ret_tested_sites"),
                "context_hits": info.get("context_hits"),
                "sites": sites,
            },
            "ranked_verdict": rk.get("verdict"),
            "ranked_confidence": rk.get("confidence"),
            "spec_path": str(SPEC_ROOT / s["lib"] / f"{s['name']}.md")
            if (SPEC_ROOT / s["lib"] / f"{s['name']}.md").is_file()
            else None,
            "risk": risk["risk"],
            "risk_label": risk["label"],
            "risk_why_en": risk["why_en"],
            "risk_why_ar": risk["why_ar"],
            "risk_bugs": risk["bugs"],
        }
        out.append(rec)
    return out


def propose_plan(records, scanned, hle_hook_logs):
    unseen = [r for r in records if r["class"] == "IMPORTED-NOT-SEEN"]
    called = [r for r in records if r["class"] == "CALLED"]
    by_mod = defaultdict(list)
    for r in unseen:
        by_mod[r["module"]].append(r)

    steps = []
    steps.append({
        "id": 1,
        "title": "Log-only autotest exe with SF_HLE_LRLOG=1",
        "detail": (
            "Do not run until the gate/SFRACE window is finished and Saud is not playing. "
            "Build sfauto\\exe_copies\\1786_autotest\\ from movie v5 + the existing voicediag SF_HLE_LRLOG hook "
            "(hooks/BUILD_NOTES.md). Log-only, standing OK. Do not overwrite 1786_movie_v5 or PLAY_Strikeforce.bat. "
            "Optional bundle: census + lifecycle [sf-lc] + SF_ATRAC_LOG in the SAME log build (team rule 5). "
            "SF_AUTOLINK=1 skeletons are also log-only but need an include in port/stubs.cpp — only if that paste is already approved as diagnostic; otherwise LRLOG is enough."
        ),
    })
    steps.append({
        "id": 2,
        "title": "Run env and capture",
        "detail": (
            "On a [TEST-SALEM] window only, state under sfauto (not Saud's play save): "
            "SF_HLE_LRLOG=1. Keep stderr+stdout. After quit, run lib/coverage.py on the log and copy only "
            "numbers (unique NIDs, per-NID counts, LRs, first stage/movie) back to stubs48-out/pc-results/. "
            "Do not copy EBOOT or lifted code."
        ),
    })
    steps.append({
        "id": 3,
        "title": "Boot path (no teleport) — movies + title + OSK",
        "detail": (
            "Start the tester exe and do not skip cutscenes. This is the CONFIRMED home of "
            "cellSail GraphicsAdapterSetPreferredFormat / AddDescriptor, AudioOutSetCopyControl, cellKbRead, "
            "and (in 1817 stdout) OSK SetLayoutMode + SetInitialKeyLayout. "
            "Goal for IMPORTED-NOT-SEEN in cellSail, remaining OSK/OskExt, cellAudioOutConfigure, "
            "cellGame GetSizeKB/PatchCheck: see whether they fire before stage A. "
            "TELEPORT is not valid on the title screen (player XYZ is an in-world address)."
        ),
        "targets": [r["name"] for r in unseen if r["module"] in (
            "cellSail", "cellSysutil", "cellOskExtUtility", "cellGame", "cellAtrac", "sys_io"
        )],
    })
    steps.append({
        "id": 4,
        "title": "Enter Shu Chapter 1 village, then TELEPORT_SAVE",
        "detail": (
            "In-world stub traffic (lwcond_signal*, flip, KbRead) is already counted through SFRACE stage B. "
            "Known tester coordinates CONFIRMED in findings 19:31: start camp S = (6500, 4346, 7500), "
            "snow area 1 = (5960, 2494, 14983), written to all 8 position mirrors. "
            "checkpoints.json still has only village_x6499_partial (X only) — do not goto that one. "
            "If a later menus run needs the village/blacksmith, TELEPORT_SAVE a full XYZ once the player is standing "
            "(a write during knockdown is ignored; a single huge Z jump goes out of bounds). "
            "Do not teleport into an unloaded stage. Gate coords are still unknown."
        ),
        "targets": [r["name"] for r in unseen if r["module"] in (
            "sysPrxForUser", "cellGcmSys", "cellResc", "cellAtrac"
        )],
    })
    steps.append({
        "id": 5,
        "title": "Menus that may reach the leftover stubs",
        "detail": (
            "On the tester profile only: open save-data menu (cellSaveDataDelete2, cellFsRmdir/Utime — do not delete Saud's real save). "
            "Open options / name-entry if the remaining OSK stubs are still unseen. "
            "Title online/trophy/friends menus for sceNp* / sceNpTus / sys_net / cellSysutilAvc2 — no real PSN login. "
            "If they still never fire after one full boot+village+menus pass, leave them IMPORTED-NOT-SEEN and do not invent a teleport."
        ),
        "targets": [r["name"] for r in unseen if r["module"] in (
            "sys_fs", "cellSaveData", "sceNp", "sceNpTus", "sys_net", "cellSysutilAvc2"
        )],
    })
    steps.append({
        "id": 6,
        "title": "What this run will decide",
        "detail": (
            "For every IMPORTED-NOT-SEEN stub: first [hle-lr] line, LR, stage/movie, count from [hle-lrc]. "
            "For sys_lwcond_signal / destroy / lwmutex_destroy: counts in the 2000 lines before stage A→B and around the hang. "
            "For cellAtrac second-buffer pair and cellAudioOutConfigure: r3/r4 and whether a 6ch configure happens. "
            "Then re-run this census on the new numbers. No behaviour-change build in this plan."
        ),
    })
    return {
        "do_not_run_on_pc_now": True,
        "wait_for": "gate / SFRACE window to finish; Saud not playing; parent agent launches the PC run later",
        "hook": "SF_HLE_LRLOG=1 (already in 1786_voicediag / hooks/BUILD_NOTES.md). Movie v5 as of 27-Nov 18:09 does not contain this hook.",
        "tp_tool": "autotester/lib/tp_tool.ps1  (guest XYZ 0x008D3800, [TEST-SALEM] only)",
        "checkpoint_caveat": "data/checkpoints.json has only village_x6499_partial (X confirmed, Y/Z missing). Do not goto it.",
        "steps": steps,
        "unseen_by_module": {m: [r["name"] for r in rs] for m, rs in by_mod.items()},
        "exercise_hints": EXERCISE,
    }


def write_json(payload):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "stubs48.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def ar_risk(r):
    return {"high": "عالي", "medium": "متوسط", "low": "منخفض"}[r]


def ar_class(c):
    return "انطلبت" if c == "CALLED" else "مستوردة وما انشافت"


def stage_ar(rec):
    id_ar = {
        "boot": "إقلاع/أفلام/قوائم",
        "stage_A": "المرحلة أ (كاش 5050)",
        "stage_B": "المرحلة ب (كاش 5053)",
        "stage_C": "المرحلة ج (كاش 4667 / تعليق القرية)",
    }
    seen = rec.get("stages_seen") or []
    movies = "، ".join(rec["movies_seen"]) if rec["movies_seen"] else ""
    if seen:
        parts = [id_ar.get(s, s) for s in seen]
        text = " ← ".join(parts)
        if movies:
            text += " — " + movies
        return text
    if rec["movies_seen"]:
        return "أفلام: " + movies
    if rec["class"] == "CALLED" and rec.get("autolink_calls") and not rec.get("first_hit", {}).get("line"):
        return "انطلبت في لوقات الجهاز (تقرير 17:19) — المرحلة مو متعيّنة على الصندوق"
    if rec["class"] == "CALLED":
        st = rec.get("first_stage")
        if st and st.get("ar"):
            return st["ar"]
        return "انطلبت، المرحلة مو متعيّنة"
    return "ما انشافت في لوقات الصندوق"


def evid_short(rec):
    first = rec.get("first_hit") or {}
    if first.get("line"):
        p = first["log"]
        short = p.replace("\\", "/").split("/")[-1] if p else p
        return f"{short}:{first['line']} ({first.get('kind')})"
    if first.get("kind"):
        return f"{first.get('kind')}"
    sites = rec["static"].get("call_sites")
    return f"استيراد ثابت، مواقع استدعاء={sites}"


def write_md(payload):
    recs = payload["stubs"]
    called = [r for r in recs if r["class"] == "CALLED"]
    unseen = [r for r in recs if r["class"] == "IMPORTED-NOT-SEEN"]
    high = [r for r in recs if r["risk"] == "high"]
    # sort called by count desc
    called_sorted = sorted(called, key=lambda r: (-(r["runtime_count_best"] or 0), r["module"], r["name"]))
    unseen_sorted = sorted(unseen, key=lambda r: (r["module"], r["name"]))
    all_sorted = called_sorted + unseen_sorted

    lines = []
    a = lines.append
    a("# دوال النظام الفاضية الـ48 (STUB HLE) — سترايك فورس")
    a("")
    a(f"تاريخ الجرد: {payload['generated_at']}")
    a("")
    a("قراءة فقط من ملفات الصندوق. ما انبنى شيء وما لمسنا جهاز سعود.")
    a("")
    a("## خلاصة")
    a("")
    a(f"- المصدر: تقرير التصنيف 27 نوفمبر 2026 الساعة 17:19 بتوقيت الكويت (`nid_autolink.py` 1.0): **248 مربوطة، 48 هيكل فارغ، 40 ناقصة، 7 مشروطة، 3 ناقصة جزئياً، من 346**.")
    a(f"- من الـ48: **{len(called)} انطلبت** في لوق أو تقرير تشغيل (CONFIRMED)، و**{len(unseen)} مستوردة وما انشافت** في أي لوق موجود على الصندوق (CONFIRMED إنها ما انشافت؛ مو مؤكد إنها ما تنطلب أبد).")
    a("- خطاف `SF_HLE_LRLOG` موجود في لوقين: جلسة voicediag 17:27، وجلسة SFRACE 19:01–19:30 (804642 سطر). أرقام العدّ من آخر جرد كامل في SFRACE (السطر 789956، 1163 زوج NID+LR). نسخة movie v5 ولوق 18:17 ولوقات الرسم ما تكتب `[hle-lr]`. الدوال اللي ما انشافت في اللوقين المخطوفين أقوى دليل إنها ما تنطلب بهالمسار (إقلاع→أ→ب)، بس مو إثبات إنها ما تنطلب في قائمة أو شبكة.")
    a("- مراحل أ/ب/ج مأخوذة من ملخص `sf_lifecycle.py` (مستنتجة من تجمّعات التحميل). الوسم عليها ASSUMED.")
    a("")
    a("### اللي أغلبه يسبب عطل ظاهر (ASSUMED إلى أن يتحقق جسم الدالة)")
    a("")
    for r in high:
        a(f"- **`{r['name']}`** (`{r['nid']}`, {r['module']}, {ar_class(r['class'])}, العدّ {r['runtime_count_best']}): {r['risk_why_ar']}")
    a("")
    a("تعليق القرية لحد الحين مربوط بمهام SPURS اللي ما تتوقف (عالم الفيزياء، CONFIRMED في اللوق). `sys_lwcond_signal` / `signal_all` مرشّح إضافي إذا كان جسمها فاضي فعلاً، مو بديل عن ذاك التحليل. في جلسة SFRACE: `_cellGcmSetFlipCommand` 65157 مرة و`cellKbRead` 65149 مرة (تقريباً مرة لكل إطار، ~37 إطار/ثانية على ~29 دقيقة) — العدّ منطقي.")
    a("")
    a("## جدول الـ48")
    a("")
    a("| الدالة | NID | المكتبة | الحالة | المرحلة / اللحظة | العدّ | الخطورة | الدليل | الوسم |")
    a("|---|---|---|---|---|---:|---|---|---|")
    for r in all_sorted:
        ev = evid_short(r).replace("|", "/")
        a(
            f"| `{r['name']}` | `{r['nid']}` | {r['module']} | {ar_class(r['class'])} | {stage_ar(r)} | {r['runtime_count_best']} | {ar_risk(r['risk'])} | {ev} | {r['class_evidence_label']}/{r['risk_label']} |"
        )
    a("")
    a("## English details")
    a("")
    a("### Sources scanned (deduped by md5)")
    a("")
    for s in payload["scanned_logs"]:
        hook = ""
        if s.get("hle_lr_lines") or s.get("hle_lrc_lines"):
            hook = f" — SF_HLE_LRLOG present (`[hle-lr]` {s['hle_lr_lines']}, `[hle-lrc]` {s['hle_lrc_lines']})"
        a(f"- `{s['path']}` ({s['bytes']} bytes, md5 {s['md5'][:12]}…){hook}")
    a("")
    a("Also used (not play logs): `nid-autolink/pc-results/report.csv` + `v2/callgraph.json` (346 imports, 6444 functions), `progress-src/out/EBOOT.imports.json`, `EBOOT.functions.json`, `progress-src/runs/*findings.json`, `v2-rank/master_ranked.csv`, `docs/hle_spec/`, lifecycle summaries under `voicefreeze/lifecycle/results/`.")
    a("")
    a("Static callers come from the v2 callgraph (ELF scan on the PC, numbers-only JSON on the box) plus the import table. Lifted C was not re-walked here; the callgraph already lists every `bl` to each import stub.")
    a("")
    a("### CALLED")
    a("")
    for r in called_sorted:
        a(f"#### {r['name']} (`{r['nid']}`, {r['module']})")
        a("")
        a(f"- Class: CALLED ({r['class_evidence_label']}). Best count: {r['runtime_count_best']} — {r['runtime_count_note']}.")
        if r["lrs"]:
            lrs = ", ".join(f"{k}×{v}" for k, v in r["lrs"].items())
            a(f"- LRs: {lrs}")
        if r.get("first_hit"):
            fh = r["first_hit"]
            loc = f"{fh.get('log')}:{fh.get('line')}" if fh.get("line") else fh.get("log")
            a(f"- First evidence: `{loc}` kind={fh.get('kind')} lr={fh.get('lr')} ret={fh.get('ret')}")
            if fh.get("text"):
                a(f"  - `{fh['text'][:200]}`")
        if r.get("first_stage"):
            a(f"- Nearest stage (ASSUMED from lifecycle line ranges): {r['first_stage']['id']} — {r['first_stage']['ar']} ({r['first_stage']['evidence']})")
        if r["movies_seen"]:
            a(f"- Movies nearby: {', '.join(r['movies_seen'])}")
        if r.get("autolink_calls"):
            a(f"- Autolink 17:19: calls={r['autolink_calls']} src={r['autolink_calls_src']} lr={r['autolink_lr']}")
        st = r["static"]
        a(f"- Static: sites={st['call_sites']} callers={st['distinct_callers']} depth_from_entry={st['min_depth_from_entry']} reachable_callers={st['callers_reachable_direct']} ret_tested={st['ret_tested_sites']} context={st['context_hits']}")
        for si in st["sites"] or []:
            fn = (si.get("caller_fn") or {}).get("label")
            rt = si.get("ret_test")
            rts = ""
            if rt:
                rts = f" ret_test={rt.get('test')} branch_if={rt.get('branch_if')} error_side={rt.get('error_side')}"
            a(f"  - site {si.get('site')} caller {si.get('caller')} ({fn}) depth={si.get('depth')}{rts}")
        a(f"- Risk: {r['risk']} ({r['risk_label']}). {r['risk_why_en']}")
        if r.get("ranked_verdict"):
            a(f"- Ranked verdict: {r['ranked_verdict']} ({r.get('ranked_confidence')}).")
        a("")
    a("### IMPORTED-NOT-SEEN")
    a("")
    a("These functions are in `EBOOT.imports.json` (CONFIRMED) and have static `bl` sites in the callgraph (some have 0 sites and may be reached only via a function pointer — VERIFY). No runtime line in any box log, findings.json, or the 17:19 autolink call column. Absence in the two SF_HLE_LRLOG sessions (voicediag + SFRACE, hook on from boot through stage B) is stronger evidence they are not used on that path. They may still run in a menu, save-delete, or online path. Label: CONFIRMED not seen on those paths; VERIFY with the Phase 2 boot+menus log-only run.")
    a("")
    for r in unseen_sorted:
        a(f"#### {r['name']} (`{r['nid']}`, {r['module']})")
        a("")
        st = r["static"]
        reach = st["callers_reachable_direct"]
        depth = st["min_depth_from_entry"]
        a(f"- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites={st['call_sites']} callers={st['distinct_callers']} depth_from_entry={depth} reachable_from_entry={reach} ret_tested={st['ret_tested_sites']} context={st['context_hits']}")
        for si in st["sites"] or []:
            fn = (si.get("caller_fn") or {}).get("label")
            rt = si.get("ret_test")
            rts = ""
            if rt:
                rts = f" ret_test={rt.get('test')} branch_if={rt.get('branch_if')} error_side={rt.get('error_side')}"
            a(f"  - site {si.get('site')} caller {si.get('caller')} ({fn}) depth={si.get('depth')}{rts}")
        hint = EXERCISE.get(r["module"], "")
        a(f"- Proposed exercise (plan only): {hint}")
        a(f"- Risk: {r['risk']} ({r['risk_label']}). {r['risk_why_en']}")
        a("")
    a("## Phase 2 — plan only (do not run on the PC in this pass)")
    a("")
    plan = payload["phase2_plan"]
    a(f"- Wait for: {plan['wait_for']}")
    a(f"- Hook: {plan['hook']}")
    a(f"- Teleport tool: `{plan['tp_tool']}`")
    a(f"- Checkpoint caveat: {plan['checkpoint_caveat']}")
    a("")
    for st in plan["steps"]:
        a(f"### {st['id']}. {st['title']}")
        a("")
        a(st["detail"])
        if st.get("targets"):
            a("")
            a("Targets still unseen: " + ", ".join(f"`{t}`" for t in st["targets"]))
        a("")
    a("## Limits")
    a("")
    a("- Stub vs linked is a text heuristic on the winning handler (KNOWN rule, ASSUMED result) from the 17:19 report. Every high-risk item must be checked by eye on the test-copy source before a fix is proposed.")
    a("- Winner order (ctx before table, port before library) is ASSUMED in that report. A 'stub' in the generated table may be shadowed by a real ctx handler — VERIFY especially for `sys_lwcond_signal`.")
    a("- Stage names A/B/C are inferred by `sf_lifecycle.py` from dispatch clusters and cache opens, not from an official mission string (except `Story: Shu Chapter 1` at 1817 stderr L9613).")
    a("- stdout and stderr line numbers are not comparable across streams.")
    a("- No behaviour-change build and no PC action in this pass.")
    a("")
    path = OUT / "stubs48.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Classify the 48 stub NIDs from a nid-autolink report and optional logs. "
        "All input paths can be set by a flag, an env var, or a repo-relative default."
    )
    ap.add_argument("--out", help="output directory (env SF_STUBS48_OUT)")
    ap.add_argument("--report-csv", dest="report_csv", help="nid-autolink report.csv (env SF_NID_REPORT_CSV)")
    ap.add_argument("--autolink-line", dest="autolink_line", help="autolink_line.txt (env SF_AUTOLINK_LINE)")
    ap.add_argument("--callgraph", help="callgraph.json (env SF_CALLGRAPH)")
    ap.add_argument("--imports", help="EBOOT.imports.json (env SF_IMPORTS_JSON)")
    ap.add_argument("--functions", help="EBOOT.functions.json (env SF_FUNCTIONS_JSON)")
    ap.add_argument("--ranked", help="master_ranked.csv (env SF_RANKED_CSV)")
    ap.add_argument("--spec-root", dest="spec_root", help="hle_spec directory (env SF_SPEC_ROOT)")
    ap.add_argument("--findings-dir", dest="findings_dir", help="findings directory (env SF_FINDINGS_DIR)")
    ap.add_argument("--log-search", dest="log_search", help="log_search.txt (env SF_LOG_SEARCH)")
    ap.add_argument(
        "--log-root",
        action="append",
        default=[],
        help="directory to scan for logs (repeatable; env SF_STUBS48_LOG_ROOTS, path-separated)",
    )
    ap.add_argument("--selftest", action="store_true", help="check path defaults; do not need game logs")
    return ap


def missing_report_message(path: Path) -> str:
    return (
        f"stubs48: report.csv not found at {path}\n"
        "Set --report-csv or SF_NID_REPORT_CSV to your nid-autolink report. "
        "A fresh clone does not ship game-derived reports."
    )


def selftest() -> int:
    apply_paths(None)
    root = repo_root()
    d = default_paths()
    for key, val in d.items():
        paths = val if key == "log_roots" else [val]
        for p in paths:
            s = str(p)
            if "/workspace/sf-shared" in s or s.startswith("/workspace/sf-stubs48"):
                raise AssertionError(f"default {key} must not hardcode a box path: {p}")
            if not s.startswith(str(root)):
                raise AssertionError(f"default {key} is not repo-relative: {p}")
    # Clean error when the report is absent (fresh clone).
    missing = root / "this-file-does-not-exist-stubs48.csv"
    msg = missing_report_message(missing)
    if "--report-csv" not in msg or "SF_NID_REPORT_CSV" not in msg:
        raise AssertionError("missing-report message should name the flag and env var")
    print("stubs48 selftest: repo-relative defaults and clean missing-input message ok")
    if not REPORT_CSV.is_file():
        print("stubs48 selftest: skip full rebuild (no report.csv; set --report-csv to generate)")
    return 0


def main(argv=None):
    args = build_arg_parser().parse_args(argv)
    apply_paths(args)
    if args.selftest:
        return selftest()
    if not REPORT_CSV.is_file():
        print(missing_report_message(REPORT_CSV), file=sys.stderr)
        return 2
    stubs = load_stubs()
    cg = load_callgraph()
    fn_ranges = load_functions_index()
    log_files = iter_log_files()
    results, scanned, hle_hook_logs = scan_logs(stubs, log_files)
    parse_findings(stubs, results)
    attach_autolink(stubs, results)
    records = classify(stubs, results, cg, fn_ranges, None)
    # counts
    called = sum(1 for r in records if r["class"] == "CALLED")
    unseen = sum(1 for r in records if r["class"] == "IMPORTED-NOT-SEEN")
    by_mod_called = defaultdict(int)
    by_mod_unseen = defaultdict(int)
    for r in records:
        (by_mod_called if r["class"] == "CALLED" else by_mod_unseen)[r["module"]] += 1
    plan = propose_plan(records, scanned, hle_hook_logs)
    payload = {
        "generated_at": now_kw(),
        "classification_source": {
            "path": str(REPORT_CSV),
            "autolink_line": str(AUTOLINK_LINE),
            "as_of": "2026-11-27 17:19 Asia/Kuwait (UTC+3)",
            "counts": {"linked": 248, "stub": 48, "missing": 40, "conditional": 7, "partial": 3, "total": 346},
            "parts_sum_ok": True,
        },
        "counts": {
            "stubs": 48,
            "CALLED": called,
            "IMPORTED-NOT-SEEN": unseen,
            "called_by_module": dict(by_mod_called),
            "unseen_by_module": dict(by_mod_unseen),
            "risk": {
                "high": sum(1 for r in records if r["risk"] == "high"),
                "medium": sum(1 for r in records if r["risk"] == "medium"),
                "low": sum(1 for r in records if r["risk"] == "low"),
            },
        },
        "top_risk_for_visible_bugs": [r["nid"] for r in records if r["risk"] == "high"],
        "scanned_logs": scanned,
        "hle_hook_logs": hle_hook_logs,
        "stubs": records,
        "phase2_plan": plan,
        "labels": {
            "CONFIRMED": "backed by a log path:line, a findings file on the box, the 17:19 report call column, or a static import/callgraph field",
            "ASSUMED": "interpretation (stage name, hang/audio/graphics causal link, stub heuristic)",
            "VERIFY": "exact next check that would confirm or kill the claim",
        },
    }
    jp = write_json(payload)
    mp = write_md(payload)
    print("CALLED", called, "UNSEEN", unseen)
    print("wrote", jp, mp)
    print("high risk:")
    for r in records:
        if r["risk"] == "high":
            print(f"  {r['class']:20} {r['runtime_count_best']:7} {r['nid']} {r['name']} stages={r['stages_seen']} movies={r['movies_seen']} src={r['sources']}")
    print("called names:")
    for r in records:
        if r["class"] == "CALLED":
            print(f"  {r['runtime_count_best']:7} {r['name']} stage={r.get('first_stage',{}) and r['first_stage'].get('id')} src={r['sources']}")


if __name__ == "__main__":
    raise SystemExit(main())

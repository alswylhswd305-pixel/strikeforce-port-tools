#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nid_autolink.py -- classify, rank and skeleton the PS3 firmware imports of a
ps3recomp port (Dynasty Warriors: Strikeforce, BLUS30471).

Own code, Python 3 standard library only. No network, no installs.
READ-ONLY on every input (EBOOT, source tree, logs). Writes ONLY into --out.

What it does
  1. Import list  : EBOOT.imports.json (ps3recomp gen_imports / sfauto format)
                    or a decrypted EBOOT.elf (parsed here, read-only)
                    or a text file "<library> <nid>" per line.
  2. NID -> name  : SHA-1(name + 16-byte suffix), first 4 bytes little-endian.
                    Candidates: built-in list, names harvested from the source
                    tree, registration labels, --names files. Every name is
                    re-hashed; nothing is trusted unverified.
  3. Classify     : scans the ps3recomp/port sources for ps3_hle_register /
                    ps3_hle_register_ctx / table-driven registrations, finds
                    the winning handler body, and labels every import
                    linked | partial | stub | conditional | dead-reg | missing.
  4. Rank         : call counts from run logs (+ static call sites and
                    return-value checks when an ELF is given) and a module
                    weight; cellAtrac is always flagged.
  5. Skeletons    : a LOGGED stub .inc for missing NIDs (opt-in at runtime with
                    SF_AUTOLINK=1). These are diagnostics, not fixes.
  6. Reports      : report.csv + summary.md (+ report.json).

Run `python nid_autolink.py --selftest` first.
"""
import argparse, csv, glob, hashlib, json, os, re, struct, sys, time

VERSION = "2.0"

# ---------------------------------------------------------------------------
# 1. NID formula  (KNOWN: psdevwiki "NID" page, _sys_sprintf example;
#    ps3recomp tools/nid_database.py + include/ps3emu/nid.h)
# ---------------------------------------------------------------------------
NID_SUFFIX = bytes.fromhex("6759659904250490566427499489741A")

def nid_of(name):
    return struct.unpack("<I", hashlib.sha1(name.encode("utf-8") + NID_SUFFIX).digest()[:4])[0]

# Built-in candidate names: the stub/missing names already identified for
# Strikeforce (each one was verified by hash against EBOOT.imports.json on
# 2026-11-26), plus a few generic ones. Only NAMES are listed; the NID is
# always computed, never copied.
BUILTIN_NAMES = """
UCS2stoSJISs _cellGcmFunc15 _sys_process_at_Exitspawn _sys_process_atexitspawn
accept bind connect listen shutdown getsockname getpeername send recv sendto
recvfrom socket socketclose setsockopt getsockopt select poll
cellAudioOutConfigure cellAudioOutSetCopyControl cellFsRmdir cellFsSetIoBuffer
cellFsUtime cellGameGetDiscContentInfoUpdatePath cellMsgDialogOpenErrorCode
cellOskDialogAddSupportLanguage cellOskDialogDisableDimmer
cellOskDialogExtInputDeviceLock cellOskDialogExtInputDeviceUnlock
cellOskDialogExtRegisterConfirmWordFilterCallback
cellOskDialogExtRegisterForceFinishCallback
cellOskDialogExtRegisterKeyboardEventHookCallback cellOskDialogExtSetInitialScale
cellOskDialogSetInitialInputDevice cellOskDialogSetInitialKeyLayout
cellOskDialogSetKeyLayoutOption cellOskDialogSetLayoutMode
cellOskDialogSetSeparateWindowOption cellPamfReaderSetStreamWithTypeAndIndex
cellRescSetBufferAddress cellRescSetWaitFlip
cellSailAviMovieGetStreamByTypeAndIndex cellSailDescriptorClose
cellSailDescriptorOpen cellSailDescriptorSetEs cellSailGraphicsAdapterGetFormat
cellSailGraphicsAdapterGetFrame cellSailGraphicsAdapterPtsToTimePosition
cellSailGraphicsAdapterSetPreferredFormat cellSailGraphicsAdapterUpdateAvSync
cellSailPlayerSetPaused cellSailSoundAdapterGetFormat cellSailSoundAdapterGetFrame
cellSailSoundAdapterPtsToTimePosition cellSailSoundAdapterUpdateAvSync
cellSaveDataDelete2 cellSysutilAvc2InitParam cellSysutilAvc2SetAttribute
cellSysutilAvc2StartVoiceDetection cellSysutilAvc2StopVoiceDetection
cellSysutilAvc2StartStreaming2 cellSysutilAvc2StopStreaming2
sceNpBasicAddFriend sceNpBasicGetCustomInvitationEntryCount
sceNpBasicRecvMessageAttachmentLoad sceNpBasicRecvMessageCustom
sceNpBasicRegisterContextSensitiveHandler sceNpBasicSendMessageGui
sceNpManagerGetChatRestrictionFlag sceNpMatching2GetRoomDataExternalList
sceNpMatching2SignalingGetConnectionInfo sceNpTusCreateTitleCtx
sceNpTusCreateTransactionCtx sceNpTusDestroyTitleCtx sceNpTusDestroyTransactionCtx
sceNpTusGetMultiSlotVariableAsync sceNpTusPollAsync sceNpTusSetMultiSlotVariableAsync
sys_net_free_thread_context sys_net_initialize_network_ex
sys_prx_exitspawn_with_level sys_prx_register_library sys_spu_image_close
cellAtracGetStreamDataInfo cellAtracAddStreamData cellAtracSetSecondBuffer
cellAtracIsSecondBufferNeeded cellAtracGetBufferInfoForResetting
cellAtracGetSecondBufferInfo cellAtracGetVacantSize
cellSysmoduleLoadModule cellFsClose _sys_sprintf
""".split()

# Module weight for ranking. ASSUMED (our judgement for an offline,
# single-player title), override with --weight MODULE=N.
MODULE_WEIGHT = {
    "cellAtrac": 5, "cellSync": 5, "cellSpurs": 5, "sysPrxForUser": 4,
    "sys_fs": 4, "cellFs": 4, "cellGcmSys": 4, "cellAudio": 4, "cellSail": 4,
    "cellAdec": 4, "cellPamf": 4, "cellResc": 3, "cellSysutil": 3,
    "cellGame": 3, "cellL10n": 2, "sys_io": 3, "cellRtc": 2, "cellSysmodule": 3,
    "cellOvis": 3, "cellSysutilAvconfExt": 2, "cellOskExtUtility": 1,
    "sceNp": 1, "sceNp2": 1, "sceNpTus": 1, "sceNpTrophy": 2, "cellNetCtl": 1,
    "sys_net": 1, "cellSysutilAvc2": 1,
}
ATRAC_NOTE = ("cellAtrac: linked to the mixer voice leak; check behaviour, e.g. "
              "6-channel AT3P rejected with 0x80610315 (not only linkage)")

# ---------------------------------------------------------------------------
# 2. Import list readers
# ---------------------------------------------------------------------------
def read_imports_json(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("imports", data.get("entries", []))
    out = []
    for e in data:
        lib = e.get("library") or e.get("lib") or e.get("module") or "?"
        out.append({"lib": lib, "nid": int(str(e["nid"]), 16),
                    "stub": int(str(e.get("stub", "0")), 16),
                    "json_name": e.get("name", "")})
    return out

def read_imports_txt(path):
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.search(r"([A-Za-z_]\w*)\W+(0x[0-9A-Fa-f]{8})", line)
        if m:
            out.append({"lib": m.group(1), "nid": int(m.group(2), 16), "stub": 0, "json_name": ""})
    return out

class Elf:
    """Minimal read-only PS3 PPU ELF64 big-endian reader.
    Layout facts used (KNOWN, two independent public sources: ps3recomp
    tools/elf_parser.py and the mercs2_exemap prx.rs docs):
      PT 0x60000002 -> sys_process_prx_param {u32 size, u32 magic 0x1B434CEC,
        u32 version, u32, u32 libent_start, u32 libent_end,
        u32 libstub_start, u32 libstub_end, ...}
      libstub record: u8 size(0x2C), u8, u16 version, u16 attr, u16 nfunc,
        u16 nvar, u16 ntls, u8[4], u32 name, u32 fnid_table, u32 fstub_table,
        u32 vnid_table, u32 vstub_table, ...
    """
    def __init__(self, path):
        with open(path, "rb") as f:          # read-only
            self.d = f.read()
        d = self.d
        if d[:4] != b"\x7fELF":
            raise ValueError("not an ELF (is it still an encrypted SELF? decrypt first)")
        if d[4] != 2 or d[5] != 2:
            raise ValueError("expected ELF64 big-endian (PS3 PPU)")
        self.entry, = struct.unpack(">Q", d[0x18:0x20])
        self.phoff, = struct.unpack(">Q", d[0x20:0x28])
        self.phentsize, self.phnum = struct.unpack(">HH", d[0x36:0x3A])
        self.ph = []
        for i in range(self.phnum):
            o = self.phoff + i * self.phentsize
            p_type, p_flags, p_off, p_vaddr, _pa, p_filesz, p_memsz, _al = struct.unpack(">IIQQQQQQ", d[o:o + 56])
            self.ph.append((p_type, p_flags, p_off, p_vaddr, p_filesz, p_memsz))

    def v2o(self, va):
        for t, fl, off, vaddr, fsz, msz in self.ph:
            if t == 1 and vaddr <= va < vaddr + fsz:
                return off + (va - vaddr)
        return None

    def u32(self, va):
        o = self.v2o(va)
        return None if o is None else struct.unpack(">I", self.d[o:o + 4])[0]

    def cstr(self, va):
        o = self.v2o(va)
        if o is None:
            return ""
        e = self.d.find(b"\0", o, o + 256)
        return self.d[o:e].decode("latin1")

    def imports(self):
        out = []
        prm = [p for p in self.ph if p[0] == 0x60000002]
        if not prm:
            raise ValueError("no PT_PROC_PRX_PARAM (0x60000002) segment")
        o = prm[0][2]
        magic = struct.unpack(">I", self.d[o + 4:o + 8])[0]
        if magic != 0x1B434CEC:
            raise ValueError("sys_process_prx_param magic mismatch 0x%08X" % magic)
        start, end = struct.unpack(">II", self.d[o + 24:o + 32])
        va = start
        while va < end:
            ro = self.v2o(va)
            if ro is None:
                break
            size = self.d[ro]
            if size == 0:
                break
            nfunc, nvar = struct.unpack(">HH", self.d[ro + 6:ro + 10])
            name_p, fnid_p, fstub_p = struct.unpack(">III", self.d[ro + 16:ro + 28])
            lib = self.cstr(name_p) if name_p else "?"
            for j in range(nfunc):
                nid = self.u32(fnid_p + 4 * j)
                slot = fstub_p + 4 * j
                val = self.u32(slot)
                if nid is None:
                    continue
                out.append({"lib": lib, "nid": nid, "stub": val or 0, "slot": slot, "json_name": ""})
            va += size
        return out

    def text_words(self):
        for t, fl, off, vaddr, fsz, msz in self.ph:
            if t == 1 and (fl & 1):           # PF_X
                for i in range(0, fsz - 3, 4):
                    yield vaddr + i, struct.unpack(">I", self.d[off + i:off + i + 4])[0]

def _checks_r3(w):
    """True if PPC instruction w tests r3 (the return value). Own decode."""
    op = w >> 26
    ra = (w >> 16) & 31
    rs = (w >> 21) & 31
    rb = (w >> 11) & 31
    if op in (10, 11) and ra == 3:                      # cmplwi/cmpwi (cmpli/cmpi)
        return True
    if op == 31:
        xo = (w >> 1) & 0x3FF
        if xo in (0, 32) and (ra == 3 or rb == 3):      # cmp / cmpl
            return True
        if (w & 1) and rs == 3 and xo in (444, 986, 954, 922):   # or. extsw. extsb. extsh.
            return True
    if op in (21, 30) and (w & 1) and rs == 3:          # rlwinm. / rld*.
        return True
    return False

def elf_callsites(elf, imports):
    """Static 'bl' sites per import and how many test r3 in the next 4 insns."""
    targets = {}
    for e in imports:
        if e.get("stub"):
            targets[e["stub"]] = e["nid"]
    words = list(elf.text_words())
    idx = {a: i for i, (a, _) in enumerate(words)} if False else None
    res = {}
    for i, (addr, w) in enumerate(words):
        if (w >> 26) == 18 and (w & 3) == 1:            # bl (AA=0, LK=1)
            li = w & 0x03FFFFFC
            if li & 0x02000000:
                li -= 0x04000000
            tgt = (addr + li) & 0xFFFFFFFF
            nid = targets.get(tgt)
            if nid is None:
                continue
            r = res.setdefault(nid, [0, 0])
            r[0] += 1
            for k in range(1, 5):
                if i + k < len(words):
                    nw = words[i + k][1]
                    if _checks_r3(nw):
                        r[1] += 1
                        break
                    if (nw >> 26) == 18:                # another branch: stop
                        break
    return res

# ---------------------------------------------------------------------------
# 3. Source scanning
# ---------------------------------------------------------------------------
SRC_EXT = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".inc")
SKIP_DIR = re.compile(r"(^|[\\/])(\.git|tests?|third_party|build|_cache|__pycache__)([\\/]|$)", re.I)

def strip_c(txt):
    """Remove comments and blank out string/char contents. Keeps length and
    newlines so offsets and line numbers stay valid."""
    out = []
    i, n = 0, len(txt)
    while i < n:
        c = txt[i]
        if c == "/" and i + 1 < n and txt[i + 1] == "/":
            j = txt.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif c == "/" and i + 1 < n and txt[i + 1] == "*":
            j = txt.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", txt[i:j])); i = j
        elif c in "\"'":
            j = i + 1
            while j < n and txt[j] != c and txt[j] != "\n":
                j += 2 if txt[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(c + " " * max(0, j - i - 2) + (c if j - i >= 2 else "")); i = j
        else:
            out.append(c); i += 1
    return "".join(out)

class SrcFile:
    def __init__(self, path):
        self.path = path
        self.raw = open(path, encoding="latin1").read()
        self.s = strip_c(self.raw)
        self._nl = None
    def line(self, off):
        return self.raw.count("\n", 0, off) + 1

MAX_SRC_BYTES = 8 * 1024 * 1024      # skip huge generated/lifted files
EXCLUDE_RX = [re.compile(r"(^|[\\/])(recompiled|lifted|ppu_recomp\w*|spu_recomp\w*)([\\/.]|$)", re.I)]

def load_sources(roots):
    files = []
    seen = set()
    skipped = 0
    for r in roots:
        if os.path.isfile(r):
            cand = [r]
        else:
            cand = []
            for dp, dn, fn in os.walk(r):
                dn[:] = [d for d in dn if not SKIP_DIR.search(os.sep + d + os.sep)]
                for f in fn:
                    if f.lower().endswith(SRC_EXT):
                        cand.append(os.path.join(dp, f))
        for p in cand:
            ap = os.path.abspath(p)
            if ap in seen:
                continue
            seen.add(ap)
            if any(rx.search(ap) for rx in EXCLUDE_RX):
                skipped += 1; continue
            try:
                if os.path.getsize(ap) > MAX_SRC_BYTES:
                    skipped += 1; continue
            except OSError:
                continue
            try:
                files.append(SrcFile(p))
            except OSError:
                pass
    if skipped:
        print("[autolink] skipped %d lifted/huge source files (not needed, not read)" % skipped)
    return files

def match_paren(s, i):
    """s[i] == '(' -> index of matching ')'."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return j
    return -1

def match_brace(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1

def split_args(s):
    parts, depth, cur = [], 0, []
    for c in s:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur)); cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    return [p.strip() for p in parts]

REG_RE = re.compile(r"\b(ps3_hle_register_ctx|ps3_hle_register_fast|ps3_hle_register)\s*\(")
TABLE_ENTRY_RE = re.compile(r'\{\s*"([A-Za-z_]\w*)"\s*,\s*&?([A-Za-z_][\w:]*)\s*\}')

def enclosing_function(sf, off):
    """Name of the function whose body contains offset off (stripped text)."""
    s = sf.s
    depth, j = 0, off
    while j > 0:
        j -= 1
        if s[j] == "}":
            depth += 1
        elif s[j] == "{":
            if depth == 0:
                k = j - 1
                while k > 0 and s[k] in " \t\r\n":
                    k -= 1
                if s[k] == ")":
                    # find matching '('
                    d2, m = 0, k
                    while m >= 0:
                        if s[m] == ")":
                            d2 += 1
                        elif s[m] == "(":
                            d2 -= 1
                            if d2 == 0:
                                break
                        m -= 1
                    head = s[max(0, m - 120):m]
                    mm = re.search(r"([A-Za-z_]\w*)\s*$", head)
                    if mm and mm.group(1) not in ("if", "for", "while", "switch", "catch"):
                        return mm.group(1), j
                    # an if/for block: keep climbing
                    if mm and mm.group(1) == "if" and re.search(r"getenv|ENV|env", s[m:k]):
                        return "__cond__:" + re.sub(r"\s+", " ", s[m:k + 1])[:80], j
            else:
                depth -= 1
    return None, -1

def preproc_condition(sf, off):
    """Innermost non-guard #if/#ifdef active at off (or None)."""
    stack = []
    for m in re.finditer(r"^[ \t]*#[ \t]*(if|ifdef|ifndef|elif|else|endif)\b([^\n]*)", sf.raw[:off], re.M):
        kw, rest = m.group(1), m.group(2).strip()
        if kw in ("if", "ifdef", "ifndef"):
            stack.append((kw, rest))
        elif kw == "endif" and stack:
            stack.pop()
        elif kw in ("else", "elif") and stack:
            stack[-1] = (kw, rest)
    for kw, rest in reversed(stack):
        if kw == "ifndef" and re.search(r"_H_?\b|_INC|_INCLUDED", rest):
            continue
        if kw == "ifdef" and rest in ("__cplusplus",):
            continue
        return "#%s %s" % (kw, rest)
    return None

def parse_registrations(files):
    regs = []   # dict(nid, label, handler, kind, file, line, func, cond)
    for sf in files:
        s = sf.s
        for m in REG_RE.finditer(s):
            # skip declarations/definitions of the API itself
            pre = s[max(0, m.start() - 40):m.start()]
            if re.search(r"(void|extern\s+\"C\"|int)\s*$", pre):
                continue
            p = m.end() - 1
            q = match_paren(s, p)
            if q < 0:
                continue
            args_s = split_args(s[p + 1:q])
            args_r = split_args(sf.raw[p + 1:q])
            if len(args_s) < 2:
                continue
            kind = m.group(1)
            a0r = args_r[0]
            nid, label = None, ""
            mm = re.match(r"\(?\s*(?:\(\s*\w+\s*\))?\s*(0x[0-9A-Fa-f]{1,8})[uUlL]*\s*\)?$", a0r)
            if mm:
                nid = int(mm.group(1), 16)
            else:
                mm = re.search(r'ps3_compute_nid\s*\(\s*"([^"]+)"\s*\)', a0r)
                if mm:
                    nid = nid_of(mm.group(1)); label = mm.group(1)
            if nid is None:
                # loop variable (table-driven) -> handled by TABLE_ENTRY_RE below
                continue
            if kind == "ps3_hle_register_fast":
                handler = re.sub(r"^\(.*?\)\s*|&", "", args_r[1]).strip()
            else:
                mm = re.search(r'"([^"]*)"', args_r[1])
                if mm:
                    label = mm.group(1)
                handler = args_r[2] if len(args_r) > 2 else ""
                handler = re.sub(r"\(\s*void\s*\*\s*\)|\(\s*\w+\s*\*?\s*\)\s*(?=\w)|&", "", handler).strip()
            func, _ = enclosing_function(sf, m.start())
            regs.append({"nid": nid, "label": label, "handler": handler, "kind": kind,
                         "file": sf.path, "line": sf.line(m.start()), "func": func,
                         "pp": preproc_condition(sf, m.start())})
        # table-driven: { "name", handler } in a file that registers by computed NID
        if "ps3_compute_nid" in sf.raw and re.search(r"ps3_hle_register", sf.raw):
            for m in TABLE_ENTRY_RE.finditer(sf.raw):
                # the string must survive stripping as a string literal location
                func, _ = enclosing_function(sf, m.start())
                regs.append({"nid": nid_of(m.group(1)), "label": m.group(1), "handler": m.group(2),
                             "kind": "table(ps3_compute_nid)", "file": sf.path,
                             "line": sf.line(m.start()), "func": func,
                             "pp": preproc_condition(sf, m.start())})
    return regs

def call_sites_of(files, fname):
    """Places that CALL fname (not its definition). Returns list of
    (file, line, conditional_text_or_None)."""
    rx = re.compile(r"(?<![\w.>:])" + re.escape(fname) + r"\s*\(")
    out = []
    for sf in files:
        if fname not in sf.s:
            continue
        for m in rx.finditer(sf.s):
            q = match_paren(sf.s, m.end() - 1)
            k = q + 1
            while 0 <= k < len(sf.s) and sf.s[k] in " \t\r\n":
                k += 1
            if q < 0 or (k < len(sf.s) and sf.s[k] == "{"):
                continue                                 # definition
            pre = sf.s[max(0, m.start() - 60):m.start()]
            if re.search(r"\b(void|int|static|extern)\s*$", pre):
                continue                                 # declaration
            line_txt = sf.s[sf.s.rfind("\n", 0, m.start()) + 1:m.start()]
            cond = None
            mm = re.search(r"\bif\s*\((.*)\)\s*$", line_txt)
            if mm and re.search(r"getenv|env", mm.group(1)):
                cond = "if (" + mm.group(1).strip() + ")"
            else:
                f2, _ = enclosing_function(sf, m.start())
                if f2 and f2.startswith("__cond__:"):
                    cond = f2[9:]
            pp = preproc_condition(sf, m.start())
            if pp and not cond:
                cond = pp
            out.append((sf.path, sf.line(m.start()), cond))
    return out

ROOT_ENTRY = {"ppu_hle_register_all", "ps3_load_prx_modules", "main", "ppu_hle_init",
              "ppu_sysprx_register", "ppu_fs_register"}

def find_definition(files, name, cache):
    if name in cache:
        return cache[name]
    short = name.split("::")[-1]
    rx = re.compile(r"(?<![\w.>])(?:\w+::)*" + re.escape(short) + r"\s*\(")
    best = None
    for sf in files:
        if short not in sf.s:
            continue
        for m in rx.finditer(sf.s):
            p = sf.s.find("(", m.start() + len(short) - 1)
            q = match_paren(sf.s, p)
            if q < 0:
                continue
            k = q + 1
            while k < len(sf.s) and sf.s[k] in " \t\r\n":
                k += 1
            if k >= len(sf.s) or sf.s[k] != "{":
                continue
            j = m.start() - 1
            while j >= 0 and sf.s[j] in " \t\r\n":
                j -= 1
            if j >= 0 and not (sf.s[j].isalnum() or sf.s[j] in "_*&:"):
                continue
            pre_word = re.search(r"(\w+)\s*$", sf.s[max(0, m.start() - 20):m.start()])
            if pre_word and pre_word.group(1) in ("return", "else", "case"):
                continue
            e = match_brace(sf.s, k)
            if e < 0:
                continue
            best = (sf, m.start(), k, e)
            break
        if best:
            break
    cache[name] = best
    return best

LABEL_RX = re.compile(r"\b(TODO|FIXME|unimplemented|UNIMPLEMENTED|not implemented|unimpl|stubbed|STUB|stub)\b")
CONST = r"(?:\(\s*\w+\s*\)\s*)?(?:-?\s*(?:0x[0-9A-Fa-f]+|\d+)[uUlL]*|CELL_\w+|[A-Z][A-Z0-9_]*ERROR\w*|[A-Z][A-Z0-9_]+_OK|true|false|NULL|nullptr|0)"
TRIVIAL = [re.compile(x + r"$", re.S) for x in [
    r"",
    r"\(\s*void\s*\)\s*[\w\->\[\]\.\s]+",
    r"return\s*(?:\(\s*\w+\s*\)\s*)?(?:0[uUlL]*|0x0+|CELL_OK|CELL_\w*ERROR\w*|[A-Z][A-Z0-9_]*ERROR\w*|0x[89A-Fa-f][0-9A-Fa-f]{7}[uUlL]*|true|false|NULL|nullptr)",
    r"return",
    r"ctx\s*->\s*gpr\s*\[\s*3\s*\]\s*=\s*(?:\(\s*\w+\s*\)\s*)?(?:0[uUlL]*|0x0+|CELL_OK|CELL_\w*ERROR\w*|[A-Z][A-Z0-9_]*ERROR\w*|0x[89A-Fa-f][0-9A-Fa-f]{7}[uUlL]*)",
    r"(?:std::)?\w*(?:printf|puts|log|Log|LOG|trace|TRACE|warn|WARN|todo|TODO)\w*\s*\(.*\)",
    r"(?:std::)?memset\s*\(.*,\s*0\s*,.*\)",
    r"\w*(?:write|w)(?:8|16|32|64)\w*\s*\([^,]+,\s*(?:0|0u|0x0|0ull)\s*\)",
    r"(?:static\s+)?(?:const\s+)?(?:std::atomic<\w+>|unsigned|signed|long|int|u?int\d+_t|[us]\d+|auto|bool)(?:\s+(?:long|int))*\s+\w+\s*(?:=\s*(?:\(\s*\w+\s*\)\s*)*(?:ctx\s*->\s*gpr\s*\[\s*\d+\s*\]|\w+|0)|\{\s*0?\s*\})?",
    r"\+\+\s*_?n\w*|_?n\w*\s*\+\+",
    r"\*\s*\(?[\w\->\.\s\*\(\)]+\)?\s*=\s*0[uUlL]*",
]]

def _strip_if(st):
    """'if (cond) rest' -> rest ; 'else rest' -> rest ; bare 'if (cond)' -> ''."""
    while True:
        m = re.match(r"^(?:else\s+)?if\s*\(", st)
        if m:
            q = match_paren(st, m.end() - 1)
            if q < 0:
                return st
            st = st[q + 1:].strip()
            continue
        m = re.match(r"^else\b\s*", st)
        if m:
            st = st[m.end():].strip()
            continue
        return st

def classify_body(sf, def_off, b_open, b_close):
    body_s = sf.s[b_open + 1:b_close]
    body_raw = sf.raw[b_open + 1:b_close]
    head_raw = sf.raw[max(0, sf.raw.rfind("\n", 0, max(0, def_off - 200))):def_off]
    labeled = bool(LABEL_RX.search(body_raw) or LABEL_RX.search(head_raw[-300:]))
    flat = re.sub(r"[{}]", ";", body_s)
    stmts = [re.sub(r"\s+", " ", x).strip() for x in flat.split(";")]
    # re-join 'if (...)' split by braces, e.g. "if (x)" ; "return 0"
    real = []
    for st in stmts:
        if not st:
            continue
        st2 = _strip_if(st)
        if any(rx.match(st2) for rx in TRIVIAL):
            continue
        real.append(st)
    if not real:
        return "stub", labeled, "body only logs/zero-fills/returns a constant"
    if labeled and len(real) <= 2:
        return "stub", labeled, "labelled TODO/stub, %d real statement(s)" % len(real)
    if labeled:
        return "partial", labeled, "real code but labelled TODO/stub/unimplemented"
    return "linked", labeled, "%d real statement(s)" % len(real)

# ---------------------------------------------------------------------------
# 4. Names
# ---------------------------------------------------------------------------
IDENT_RX = re.compile(r"\b(_{0,2}[A-Za-z][A-Za-z0-9_]{2,80})\b")

def harvest_names(files, header_dirs, name_files, protos_json):
    names = set(BUILTIN_NAMES)
    for sf in files:
        names.update(IDENT_RX.findall(sf.raw))          # strings too (labels)
    for d in header_dirs:
        for p in glob.glob(os.path.join(d, "**", "*.h"), recursive=True):
            try:
                names.update(IDENT_RX.findall(open(p, encoding="latin1").read()))
            except OSError:
                pass
    for nf in name_files:
        for line in open(nf, encoding="utf-8", errors="replace"):
            for tok in re.findall(r"[A-Za-z_][\w@$.]*", line):
                names.add(tok)
    for pj in protos_json:
        try:
            d = json.load(open(pj, encoding="utf-8"))
            if isinstance(d, dict):
                names.update(k for k in d.keys() if isinstance(k, str))
        except (OSError, ValueError):
            pass
    return names

def build_name_map(names, wanted):
    out = {}
    for n in names:
        v = nid_of(n)
        if v in wanted and v not in out:
            out[v] = n
    return out

def harvest_protos(files, header_dirs, wanted_names):
    """name -> (prototype text, file:line) from declarations we can read."""
    protos = {}
    rx = re.compile(r"(?:^|[;}\n])\s*((?:extern\s+\"C\"\s+)?(?:static\s+)?[A-Za-z_][\w\s\*]*?\b(%s)\s*\(([^;{}()]*(?:\([^()]*\)[^;{}()]*)*)\))\s*[;{]" %
                    "|".join(re.escape(n) for n in sorted(wanted_names)) if wanted_names else r"(?!x)x")
    paths = [sf for sf in files]
    hdrs = []
    for d in header_dirs:
        hdrs += glob.glob(os.path.join(d, "**", "*.h"), recursive=True)
    for sf in paths:
        for m in rx.finditer(sf.s):
            nm = m.group(2)
            if nm not in protos:
                raw = re.sub(r"\s+", " ", sf.raw[m.start(1):m.end(1)]).strip()
                protos[nm] = (raw, "%s:%d" % (sf.path, sf.line(m.start(1))))
    for p in hdrs:
        try:
            sf = SrcFile(p)
        except OSError:
            continue
        for m in rx.finditer(sf.s):
            nm = m.group(2)
            if nm not in protos:
                raw = re.sub(r"\s+", " ", sf.raw[m.start(1):m.end(1)]).strip()
                protos[nm] = (raw, "%s:%d" % (sf.path, sf.line(m.start(1))))
    return protos

# ---------------------------------------------------------------------------
# 5. Logs -> call counts
# ---------------------------------------------------------------------------
def parse_logs(paths, name_to_nid):
    counts = {}      # nid -> [count, source, complete]
    lrs = {}
    def bump(nid, n, src, complete, mode="add"):
        c = counts.setdefault(nid, [0, src, complete])
        if mode == "max":
            c[0] = max(c[0], n)
        else:
            c[0] += n
        if complete:
            c[2] = True
        c[1] = src
    for p in paths:
        if p.lower().endswith(".json"):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for n in d.get("unresolved_nids", []):
                bump(int(n, 16), 1, "findings.json(first-hit)", False, "max")
            for n, lr in (d.get("unresolved_ctx") or {}).items():
                lrs.setdefault(int(n, 16), set()).add(lr)
            for hf in d.get("hle_funcs", []):
                a, _, b = hf.partition(".")
                for cand in (a + b, a + "_" + b):
                    v = name_to_nid.get(cand)
                    if v is not None:
                        bump(v, 1, "findings.json hle_funcs(seen)", False, "max")
            continue
        summary = {}
        callmax = {}
        calllines = {}
        first = set()
        top = {}
        for line in open(p, encoding="utf-8", errors="replace"):
            m = re.search(r"UNRESOLVED SUMMARY nid=(0x[0-9A-Fa-f]{8}) hits=(\d+)", line)
            if m:
                summary[int(m.group(1), 16)] = int(m.group(2)); continue
            m = re.search(r"UNRESOLVED CALL nid=(0x[0-9A-Fa-f]{8}).*?hits=(\d+)", line)
            if m:
                v = int(m.group(1), 16)
                callmax[v] = max(callmax.get(v, 0), int(m.group(2)))
                calllines[v] = calllines.get(v, 0) + 1
                mm = re.search(r"lr=(0x[0-9A-Fa-f]+)", line)
                if mm:
                    lrs.setdefault(v, set()).add(mm.group(1))
                continue
            m = re.search(r"\[sf-autolink\] STUB \S+ nid=(0x[0-9A-Fa-f]{8}) call#(\d+)", line)
            if m:
                v = int(m.group(1), 16)
                callmax[v] = max(callmax.get(v, 0), int(m.group(2)))
                calllines[v] = calllines.get(v, 0) + 1
                continue
            m = re.search(r"UNRESOLVED NID (0x[0-9A-Fa-f]{8})", line)
            if m:
                first.add(int(m.group(1), 16)); continue
            if os.path.basename(p).lower().startswith("unresolved"):   # unresolved_nids.txt (format VERIFY)
                toks = re.findall(r"0x([0-9A-Fa-f]{8})\b", line)
                if toks:
                    v = int(toks[0], 16)
                    mm = re.search(r"(?:hits|count|calls)\s*[=:]\s*(\d+)", line, re.I)
                    if mm:
                        callmax[v] = max(callmax.get(v, 0), int(mm.group(1)))
                        calllines[v] = calllines.get(v, 0) + 1
                    else:
                        first.add(v)
                    continue
            m = re.match(r"^\s+(\d+)\s+([A-Za-z_]\w*)\s+tid=", line)  # PS3_HLE_TOP window
            if m:
                v = name_to_nid.get(m.group(2))
                if v is not None:
                    top[v] = top.get(v, 0) + int(m.group(1))
                continue
            m = re.search(r"\[hle\]\s+(0x[0-9A-Fa-f]{8})\s+.*\blr\s*=\s*([0-9A-Fa-f]+)", line)
            if m:
                lrs.setdefault(int(m.group(1), 16), set()).add("0x%08X" % (int(m.group(2), 16) & 0xFFFFFFFF))
        for v, n in summary.items():
            bump(v, n, "SUMMARY", True)
        for v in callmax:
            if v in summary:
                continue
            n = callmax[v] if callmax[v] > 1 else calllines[v]
            bump(v, n, "CALL lines", True)
        for v in first:
            if v not in summary and v not in callmax:
                bump(v, 1, "first-hit only (>=1)", False, "max")
        for v, n in top.items():
            bump(v, n, "PS3_HLE_TOP windows", True)
    return counts, lrs

# ---------------------------------------------------------------------------
# 6. Skeletons
# ---------------------------------------------------------------------------
def c_ident(name):
    return re.sub(r"\W", "_", name)

def make_skeletons(rows, protos):
    L = []
    L.append("/* sf_autolink_stubs.inc -- GENERATED by nid_autolink.py v%s on %s." % (VERSION, time.strftime("%Y-%m-%d %H:%M")))
    L.append(" *")
    L.append(" * DIAGNOSTIC STUBS, NOT FIXES. Every handler below:")
    L.append(" *   - logs every call (first 8, then powers of two) with r3..r10 and lr,")
    L.append(" *   - returns the SAME value the unresolved path already fakes (CELL_OK),")
    L.append(" *     so enabling it changes visibility only, not game behaviour,")
    L.append(" *   - is registered ONLY when the env var SF_AUTOLINK=1 is set.")
    L.append(" * Labels end in [sf-autolink-STUB] so no log or report can mistake them")
    L.append(" * for real implementations. Replace each body with real behaviour written")
    L.append(" * from an observed call (register dump) -- never from GPL source.")
    L.append(" *")
    L.append(" * Use: #include \"sf_autolink_stubs.inc\" in port/stubs.cpp after the other")
    L.append(" * strikeforce_*.inc files, and call sf_register_autolink_stubs() LAST in")
    L.append(" * ps3_load_prx_modules() (ctx handlers win over the generic table). */")
    L.append("#include <atomic>")
    L.append("#include <cstdint>")
    L.append("#include <cstdio>")
    L.append("#include <cstdlib>")
    L.append("struct ppu_context;")
    L.append('extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));')
    L.append("namespace sf_autolink {")
    L.append("static inline bool want_log(unsigned n) { return n <= 8 || (n & (n - 1)) == 0; }")
    L.append("#define SF_AL_LOG(NAME, NID, N, ctx) do { if (want_log(N)) { const uint64_t* g = (ctx)->gpr; \\")
    L.append("    fprintf(stderr, \"[sf-autolink] STUB %s nid=0x%08X call#%u tid=%u lr=0x%08X \" \\")
    L.append("        \"r3=%016llX r4=%016llX r5=%016llX r6=%016llX r7=%016llX r8=%016llX r9=%016llX r10=%016llX\\n\", \\")
    L.append("        NAME, (unsigned)(NID), (unsigned)(N), (unsigned)(ctx)->thread_id, (unsigned)(ctx)->lr, \\")
    L.append("        (unsigned long long)g[3], (unsigned long long)g[4], (unsigned long long)g[5], (unsigned long long)g[6], \\")
    L.append("        (unsigned long long)g[7], (unsigned long long)g[8], (unsigned long long)g[9], (unsigned long long)g[10]); } } while (0)")
    regs = []
    for r in rows:
        nm = r["name"] or ("nid_%08X" % r["nid"])
        fn = "hle_" + c_ident(nm)
        L.append("")
        L.append("/* %s  NID 0x%08X  module %s  priority %s (score %s)" % (nm, r["nid"], r["lib"], r["priority"], r["score"]))
        pr = protos.get(r["name"])
        if pr:
            L.append(" * signature (from %s): %s   [KNOWN only if that header matches the SDK]" % (pr[1], pr[0]))
        else:
            L.append(" * signature: UNKNOWN -- read r3..r10 from the [sf-autolink] log line first.")
        L.append(" * TODO(real behaviour): write it from an observed call; then remove this stub. */")
        L.append("static std::atomic<unsigned> g_n_%s{0};" % c_ident(nm))
        L.append("static void %s(ppu_context* ctx)" % fn)
        L.append("{")
        L.append("    const unsigned n = ++g_n_%s;" % c_ident(nm))
        L.append("    SF_AL_LOG(\"%s\", 0x%08Xu, n, ctx);" % (nm, r["nid"]))
        L.append("    ctx->gpr[3] = 0; /* CELL_OK: same as the unresolved fake. STUB. */")
        L.append("}")
        regs.append("    ps3_hle_register_ctx(0x%08Xu, \"%s[sf-autolink-STUB]\", sf_autolink::%s);" % (r["nid"], nm, fn))
    L.append("#undef SF_AL_LOG")
    L.append("} /* namespace sf_autolink */")
    L.append("static void sf_register_autolink_stubs(void)")
    L.append("{")
    L.append("    const char* e = getenv(\"SF_AUTOLINK\");")
    L.append("    if (!e || e[0] != '1') return;   /* opt-in diagnostic only */")
    L.append("    fprintf(stderr, \"[sf-autolink] %d logged STUB handlers registered (diagnostic, not fixes)\\n\");" % len(regs))
    L.extend(regs)
    L.append("}")
    return "\n".join(L) + "\n"

# ---------------------------------------------------------------------------
# 7. Main pipeline
# ---------------------------------------------------------------------------
def run(args):
    t0 = time.time()
    # imports
    elf = None
    if args.elf:
        elf = Elf(args.elf)
        imports = elf.imports()
    elif args.imports.lower().endswith(".json"):
        imports = read_imports_json(args.imports)
    else:
        imports = read_imports_txt(args.imports)
    # de-dup by nid (first lib wins)
    seen, imp = set(), []
    for e in imports:
        if e["nid"] in seen:
            continue
        seen.add(e["nid"]); imp.append(e)
    wanted = {e["nid"] for e in imp}
    print("[autolink] imports: %d unique NIDs in %d modules" % (len(imp), len({e['lib'] for e in imp})))

    files = load_sources(args.src)
    print("[autolink] sources: %d files under %d root(s)" % (len(files), len(args.src)))
    protos_json = list(args.protos_json)
    for r in args.src:
        for p in glob.glob(os.path.join(r, "**", "nid_from_protos.json"), recursive=True):
            protos_json.append(p)
    names = harvest_names(files, args.headers, args.names, protos_json)
    for e in imp:
        if e.get("json_name"):
            names.add(e["json_name"])
    regs = parse_registrations(files)
    for r in regs:
        if r["label"]:
            names.add(re.sub(r"\[.*$", "", r["label"]).strip())
    nmap = build_name_map(names, wanted)
    name_to_nid = {v: k for k, v in nmap.items()}
    print("[autolink] names: %d candidates hashed, %d/%d imports named" % (len(names), len(nmap), len(wanted)))

    # registrations -> per-nid
    by_nid = {}
    for r in regs:
        if r["nid"] in wanted:
            by_nid.setdefault(r["nid"], []).append(r)

    # liveness of registering functions (one level)
    live_cache = {}
    def liveness(func):
        if not func:
            return "live", ""
        if func.startswith("__cond__:"):
            return "conditional", func[9:]
        if func in ROOT_ENTRY:
            return "live", ""
        if func in live_cache:
            return live_cache[func]
        sites = call_sites_of(files, func)
        if not sites:
            res = ("dead", "no call to %s() found in scanned sources" % func)
        elif all(c for _, _, c in sites):
            res = ("conditional", "; ".join(sorted({c for _, _, c in sites}))[:120])
        else:
            res = ("live", "")
        live_cache[func] = res
        return res

    def_cache = {}
    counts, lrs = parse_logs(args.log, name_to_nid)
    sites = elf_callsites(elf, imp) if elf else {}
    weights = dict(MODULE_WEIGHT)
    for w in args.weight:
        k, _, v = w.partition("=")
        weights[k] = int(v)

    rows = []
    for e in imp:
        nid = e["nid"]
        nm = nmap.get(nid, "")
        row = {"lib": e["lib"], "nid": nid, "nid_hex": "0x%08X" % nid, "stub_addr": "0x%08X" % e.get("stub", 0),
               "name": nm, "name_verified": "sha1" if nm else "",
               "status": "missing", "handler": "", "where": "", "n_regs": 0,
               "kind": "", "why": "", "calls": "", "calls_src": "", "lr": "",
               "static_sites": "", "ret_checked": "", "weight": weights.get(e["lib"], 2),
               "score": 0, "priority": "", "notes": []}
        rs = by_nid.get(nid, [])
        # liveness filter
        live_rs, cond_rs, dead_rs = [], [], []
        for r in rs:
            if r["kind"] == "ps3_hle_register_fast":
                continue
            lv, why = liveness(r["func"])
            if r["pp"] and lv == "live":
                lv, why = "conditional", r["pp"]
            r["live"], r["live_why"] = lv, why
            (live_rs if lv == "live" else cond_rs if lv == "conditional" else dead_rs).append(r)
        row["n_regs"] = len(rs)
        # winner: ctx before plain table (ps3_hle_call searches ctx first);
        # within a kind, port (strikeforce_*) before library -- ASSUMED order.
        def rank(r):
            return (0 if r["kind"] == "ps3_hle_register_ctx" else 1,
                    0 if re.search(r"strikeforce|[\\/]port[\\/]", r["file"], re.I) else 1)
        if live_rs:
            win = sorted(live_rs, key=rank)[0]
            row["handler"] = win["handler"]; row["kind"] = win["kind"]
            row["where"] = "%s:%d" % (win["file"], win["line"])
            d = find_definition(files, win["handler"], def_cache) if win["handler"] else None
            if d:
                st, labeled, why = classify_body(d[0], d[1], d[2], d[3])
                row["status"], row["why"] = st, why
                row["where"] += " -> body %s:%d" % (d[0].path, d[0].line(d[1]))
            else:
                row["status"], row["why"] = "uncertain", "registered, handler body not found in scanned sources"
            if len(live_rs) > 1:
                row["notes"].append("%d live registrations; winner ASSUMED by ctx>table, port>lib" % len(live_rs))
        elif cond_rs:
            row["status"] = "conditional"
            row["why"] = "only registered under: " + (cond_rs[0].get("live_why") or "?")
            row["where"] = "%s:%d" % (cond_rs[0]["file"], cond_rs[0]["line"])
        elif dead_rs:
            row["status"] = "dead-reg"
            row["why"] = dead_rs[0]["live_why"]
            row["where"] = "%s:%d" % (dead_rs[0]["file"], dead_rs[0]["line"])
        else:
            row["why"] = "no registration found; unresolved path fakes CELL_OK"
        if nid in counts:
            c = counts[nid]
            row["calls"] = c[0] if c[2] else ">=%d" % c[0]
            row["calls_src"] = c[1]
        if nid in lrs:
            row["lr"] = " ".join(sorted(lrs[nid]))[:60]
        if elf:
            s = sites.get(nid, [0, 0])
            row["static_sites"], row["ret_checked"] = s[0], s[1]
        if e["lib"] == "cellAtrac" or nm.startswith("cellAtrac"):
            row["notes"].append(ATRAC_NOTE)
            row["weight"] = max(row["weight"], 5)
        # score: only for things that are not really linked
        if row["status"] in ("missing", "stub", "conditional", "dead-reg", "partial", "uncertain"):
            ncalls = counts.get(nid, [0])[0]
            sc = row["weight"] * 10
            sc += min(40, 8 * (len(str(ncalls)) if ncalls else 0)) + (15 if ncalls else 0)
            if elf:
                sc += min(10, 2 * row["static_sites"] or 0) + (15 if row["ret_checked"] else 0)
            sc += {"missing": 10, "dead-reg": 10, "stub": 5, "conditional": 3, "partial": 2, "uncertain": 5}[row["status"]]
            row["score"] = sc
            row["priority"] = "P1" if sc >= 70 else "P2" if sc >= 45 else "P3"
        rows.append(row)

    os.makedirs(args.out, exist_ok=True)
    rows.sort(key=lambda r: (-r["score"], r["lib"], r["name"]))
    cols = ["priority", "score", "status", "lib", "nid_hex", "name", "name_verified", "calls", "calls_src",
            "static_sites", "ret_checked", "lr", "weight", "handler", "kind", "n_regs", "where", "why", "notes", "stub_addr"]
    with open(os.path.join(args.out, "report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([("; ".join(r[c]) if c == "notes" else r[c]) for c in cols])
    json.dump(rows, open(os.path.join(args.out, "report.json"), "w", encoding="utf-8"), indent=1)

    todo = [r for r in rows if r["status"] in ("missing", "dead-reg")]
    want_protos = {r["name"] for r in todo if r["name"]}
    protos = harvest_protos(files, args.headers, want_protos) if want_protos else {}
    with open(os.path.join(args.out, "sf_autolink_stubs.inc"), "w", encoding="utf-8") as f:
        f.write(make_skeletons(todo, protos))
    unnamed = [r for r in rows if not r["name"]]
    with open(os.path.join(args.out, "unnamed_nids.txt"), "w", encoding="utf-8") as f:
        for r in unnamed:
            f.write("%s %s\n" % (r["lib"], r["nid_hex"]))

    # summary
    from collections import Counter, defaultdict
    tot = Counter(r["status"] for r in rows)
    permod = defaultdict(Counter)
    for r in rows:
        permod[r["lib"]][r["status"]] += 1
    S = []
    S.append("# NID auto-link report (nid_autolink.py v%s)" % VERSION)
    S.append("")
    S.append("Generated %s (local time of the machine that ran it). Read-only scan; nothing outside this folder was written." % time.strftime("%Y-%m-%d %H:%M"))
    S.append("")
    S.append("Inputs: imports=`%s` | sources=%d files | logs=%d | ELF call-site scan=%s" %
             (args.elf or args.imports, len(files), len(args.log), "yes" if elf else "no"))
    S.append("")
    S.append("| status | count | meaning |")
    S.append("|---|---:|---|")
    meaning = {"linked": "registered, handler has real code",
               "partial": "registered, real code but labelled TODO/stub",
               "stub": "registered, body only logs/zero-fills/returns a constant",
               "conditional": "registered only under an env var / #if",
               "dead-reg": "registration exists but its register function is never called",
               "uncertain": "registered, handler body not found (check by hand)",
               "missing": "not registered: unresolved path fakes CELL_OK"}
    for k in ["linked", "partial", "stub", "uncertain", "conditional", "dead-reg", "missing"]:
        S.append("| %s | %d | %s |" % (k, tot.get(k, 0), meaning[k]))
    S.append("| **total** | **%d** | named: %d, unnamed: %d |" % (len(rows), len(rows) - len(unnamed), len(unnamed)))
    S.append("")
    S.append("## Work list (highest priority first)")
    S.append("")
    S.append("| P | score | status | module | NID | name | calls | sites/ret-checked | why |")
    S.append("|---|---:|---|---|---|---|---|---|---|")
    for r in rows:
        if not r["score"]:
            continue
        S.append("| %s | %d | %s | %s | `%s` | %s | %s | %s | %s |" % (
            r["priority"], r["score"], r["status"], r["lib"], r["nid_hex"], r["name"] or "?",
            r["calls"] or "-", ("%s/%s" % (r["static_sites"], r["ret_checked"])) if elf else "n/a",
            (r["why"] + ("; " + "; ".join(r["notes"]) if r["notes"] else "")).replace("|", "/")[:160]))
    S.append("")
    S.append("## cellAtrac (always flagged)")
    S.append("")
    for r in rows:
        if r["lib"] == "cellAtrac" or r["name"].startswith("cellAtrac"):
            S.append("- `%s` %s: **%s** (%s) %s" % (r["nid_hex"], r["name"] or "?", r["status"], r["why"], r["where"]))
    S.append("")
    S.append("ASSUMED link: the mixer voice leak may come from cellAtrac behaviour (e.g. 6-channel AT3P rejected with 0x80610315), not only from linkage. A `linked` status here proves registration, not correct behaviour.")
    S.append("")
    S.append("## Per module")
    S.append("")
    S.append("| module | total | linked | partial | stub | cond | dead | missing |")
    S.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for lib in sorted(permod):
        c = permod[lib]
        S.append("| %s | %d | %d | %d | %d | %d | %d | %d |" % (lib, sum(c.values()), c["linked"], c["partial"], c["stub"],
                                                          c["conditional"], c["dead-reg"], c["missing"]))
    S.append("")
    S.append("## Honest limits")
    S.append("")
    S.append("- Stub/linked is a text heuristic on the winning handler body (KNOWN rule, ASSUMED result). Check every P1 by eye.")
    S.append("- Winner order when several registrations exist is ASSUMED (ctx before table, port before library).")
    S.append("- 'dead-reg' / 'conditional' look one call level up only.")
    S.append("- Call counts are exact only from SUMMARY/CALL/[sf-autolink] lines; a first-hit log gives >=1.")
    S.append("- `sf_autolink_stubs.inc` contains LOGGED STUBS (opt-in with SF_AUTOLINK=1). They are diagnostics, not fixes.")
    S.append("")
    S.append("Runtime: %.1fs" % (time.time() - t0))
    open(os.path.join(args.out, "summary.md"), "w", encoding="utf-8").write("\n".join(S) + "\n")
    print("[autolink] " + ", ".join("%s=%d" % (k, tot[k]) for k in sorted(tot)))
    print("[autolink] wrote report.csv, report.json, summary.md, sf_autolink_stubs.inc (%d stubs), unnamed_nids.txt -> %s"
          % (len(todo), os.path.abspath(args.out)))
    return rows

# ===========================================================================
# v2: per-LR logs, static call graph, impact ranking, poison test, specs
# ===========================================================================
import bisect

# Context of a call, judged from which other imports the caller (and its
# callers) use. ASSUMED heuristic -- a hint for ranking, not proof.
NET_LIBS = {"sceNp", "sceNp2", "sceNpTus", "sys_net", "cellNetCtl", "cellSysutilAvc2",
            "sceNpCommerce2", "cellHttp", "cellHttps", "cellSsl"}
MEDIA_LIBS = {"cellSail", "cellPamf", "cellAdec", "cellVdec", "cellDmux", "cellAtrac", "cellVpost"}
CORE_LIBS = {"cellGcmSys", "cellAudio", "cellSpurs", "cellSync", "sys_fs", "sysPrxForUser",
             "cellResc", "sys_io", "cellSysmodule"}
UI_PREFIX = ("cellOskDialog", "cellMsgDialog", "cellSaveData", "cellGameContentPermit")
OWNED_BY_SALEM = ("cellSail",)            # movie functions: Salem owns them

def call_context(lib, name):
    if lib in NET_LIBS or name.startswith("sceNp"):
        return "net"
    if name.startswith(UI_PREFIX):
        return "ui"
    if lib in MEDIA_LIBS:
        return "media"
    if lib in CORE_LIBS:
        return "core"
    return "other"

class FuncMap:
    """Function boundaries from ps3recomp's EBOOT.functions.json
    ([{start,end,toc,opd}], KNOWN format, read on the box). Derived data only."""
    def __init__(self, funcs):
        funcs = sorted(funcs)
        self.starts = [f[0] for f in funcs]
        self.ends = [f[1] for f in funcs]
        self.opd = {f[0]: f[2] for f in funcs if f[2]}
    @classmethod
    def load(cls, path):
        d = json.load(open(path, encoding="utf-8"))
        out = []
        for e in d:
            try:
                out.append((int(str(e["start"]), 16), int(str(e["end"]), 16),
                            int(str(e.get("opd", "0") or "0"), 16)))
            except (KeyError, ValueError):
                pass
        return cls(out)
    def find(self, addr):
        i = bisect.bisect_right(self.starts, addr) - 1
        if i >= 0 and addr < self.ends[i]:
            return self.starts[i]
        return None
    def __len__(self):
        return len(self.starts)

def parse_lr_logs(paths, name_to_nid):
    """Per-NID, per-caller-LR evidence from every log format we know.
    Returns {nid: {"total": int, "exact": bool, "lrs": {lr: n}, "tids": set,
    "src": set}}. 'exact' is True only when a format gives real counts."""
    ev = {}
    def e(nid):
        return ev.setdefault(nid, {"total": 0, "exact": False, "lrs": {}, "tids": set(), "src": set()})
    hexlr = lambda x: "0x%08X" % (int(x, 16) & 0xFFFFFFFF)
    for p in paths:
        if p.lower().endswith(".json"):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for n in d.get("unresolved_nids", []):
                x = e(int(n, 16)); x["total"] = max(x["total"], 1); x["src"].add("findings.json")
            for n, lr in (d.get("unresolved_ctx") or {}).items():
                x = e(int(n, 16)); x["lrs"].setdefault(hexlr(lr), 1); x["src"].add("findings.json")
            continue
        pending = None            # NID whose first-hit dump lines follow
        per_line_max = {}
        for line in open(p, encoding="utf-8", errors="replace"):
            m = re.search(r"\[sf-(?:autolink|poison)\]\s+(?:STUB|POISON)\s+\S+\s+nid=(0x[0-9A-Fa-f]{8})\s+call#(\d+)(?:\s+tid=(\d+))?(?:\s+lr=(0x[0-9A-Fa-f]+))?", line)
            if m:
                v = int(m.group(1), 16); x = e(v)
                per_line_max[v] = max(per_line_max.get(v, 0), int(m.group(2)))
                if m.group(4):
                    lr = hexlr(m.group(4)); x["lrs"][lr] = x["lrs"].get(lr, 0) + 1
                if m.group(3):
                    x["tids"].add(int(m.group(3)))
                x["src"].add("sf-autolink/poison (sampled: first 8 then powers of 2)")
                continue
            m = re.search(r"UNRESOLVED CALL nid=(0x[0-9A-Fa-f]{8}).*?hits=(\d+)", line)
            if m:
                v = int(m.group(1), 16); x = e(v)
                per_line_max[v] = max(per_line_max.get(v, 0), int(m.group(2)))
                mm = re.search(r"lr=(0x[0-9A-Fa-f]+)", line)
                if mm:
                    lr = hexlr(mm.group(1)); x["lrs"][lr] = x["lrs"].get(lr, 0) + 1
                mm = re.search(r"tid=(\d+)", line)
                if mm:
                    x["tids"].add(int(mm.group(1)))
                x["src"].add("UNRESOLVED CALL"); x["exact"] = True
                continue
            m = re.search(r"UNRESOLVED SUMMARY nid=(0x[0-9A-Fa-f]{8}) hits=(\d+)", line)
            if m:
                v = int(m.group(1), 16); x = e(v)
                x["total"] = max(x["total"], int(m.group(2))); x["exact"] = True; x["src"].add("SUMMARY")
                continue
            m = re.search(r"UNRESOLVED NID (0x[0-9A-Fa-f]{8})", line)
            if m:
                pending = int(m.group(1), 16); x = e(pending)
                x["total"] = max(x["total"], 1); x["src"].add("first-hit")
                continue
            m = re.search(r"\[hle\]\s+(0x[0-9A-Fa-f]{8})\s.*?\btid=(\d+)", line)
            if m:
                e(int(m.group(1), 16))["tids"].add(int(m.group(2)))
            m = re.search(r"\[hle\]\s+(0x[0-9A-Fa-f]{8})\s.*\blr\s*=\s*([0-9A-Fa-f]+)", line)
            if m:
                v = int(m.group(1), 16); lr = hexlr(m.group(2))
                e(v)["lrs"].setdefault(lr, 1)
                continue
            m = re.match(r"^\s+(\d+)\s+([A-Za-z_]\w*)\s+tid=(\d+)\s+lr=(0x[0-9A-Fa-f]+)", line)   # PS3_HLE_TOP
            if m:
                v = name_to_nid.get(m.group(2))
                if v is not None:
                    x = e(v); x["total"] += int(m.group(1)); x["exact"] = True
                    lr = hexlr(m.group(4)); x["lrs"][lr] = x["lrs"].get(lr, 0) + int(m.group(1))
                    x["tids"].add(int(m.group(3))); x["src"].add("PS3_HLE_TOP (last lr per window)")
        for v, n in per_line_max.items():
            ev[v]["total"] = max(ev[v]["total"], n)
            if any("CALL" in s for s in ev[v]["src"]) or any("sf-" in s for s in ev[v]["src"]):
                ev[v]["exact"] = True
    return ev

# --- static call graph from the ELF -----------------------------------------
def _bc_cond(w):
    """Decode a PPC bc word -> (always, want_true, crbit) ; own decode (ISA facts)."""
    bo = (w >> 21) & 31
    bi = (w >> 16) & 31
    if bo & 0x10:
        return True, None, bi
    return False, bool(bo & 0x08), bi

def decode_ret_test(word_at, site, max_ahead=8):
    """After a `bl import` at site: does the game test the result, and where
    does each outcome go?  Tracks r3 and one `mr rX,r3` copy. Returns a dict
    or None (result not tested within max_ahead instructions -- it may still
    be tested later; this is a lower bound)."""
    tracked = {3}
    cmp = None            # (crfield, text, imm)
    for k in range(1, max_ahead + 1):
        a = site + 4 * k
        w = word_at(a)
        if w is None:
            return None
        op = w >> 26
        rt = (w >> 21) & 31; ra = (w >> 16) & 31; rb = (w >> 11) & 31
        if cmp is None:
            if op == 31 and ((w >> 1) & 0x3FF) == 444 and rt == rb and rt in tracked and not (w & 1):
                tracked.add(ra); continue                     # mr ra, rt
            if op in (10, 11) and ra in tracked:
                imm = w & 0xFFFF
                if op == 11 and imm & 0x8000:
                    imm -= 0x10000
                cmp = (rt >> 2, "%s r%d,%d" % ("cmpwi" if op == 11 else "cmplwi", ra, imm), imm, op == 11)
                continue
            if op == 31 and ((w >> 1) & 0x3FF) in (0, 32) and (ra in tracked or rb in tracked):
                cmp = (rt >> 2, "%s r%d,r%d" % ("cmpw" if ((w >> 1) & 0x3FF) == 0 else "cmplw", ra, rb), None, True)
                continue
            if (w & 1) and rt in tracked and (op in (21, 30) or (op == 31 and ((w >> 1) & 0x3FF) in (444, 986, 954, 922))):
                cmp = (0, "record-form test of r%d (cr0 vs 0)" % rt, 0, True)
                continue
            if op == 18 or op == 16 or (op == 19 and ((w >> 1) & 0x3FF) in (16, 528)):
                return None                                    # branch before any test
            # instruction overwriting all tracked regs ends tracking
            if rt in tracked and op not in (36, 37, 38, 39, 44, 45, 62):   # stores read rt
                tracked.discard(rt)
                if not tracked:
                    return None
            continue
        # have a compare: look for the conditional branch that uses its CR field
        if op == 16:
            always, want_true, bi = _bc_cond(w)
            if always or (bi >> 2) != cmp[0]:
                continue
            bd = w & 0xFFFC
            if bd & 0x8000:
                bd -= 0x10000
            tgt = (a + bd) & 0xFFFFFFFF if not (w & 2) else bd & 0xFFFFFFFF
            bit = bi & 3
            rel = {0: "<", 1: ">", 2: "==", 3: "SO"}[bit]
            imm = cmp[2] if cmp[2] is not None else "rB"
            cond_true = "r3 %s %s" % (rel, imm)
            cond = cond_true if want_true else "not(%s)" % cond_true
            # error path: CELL errors are negative s32 (0x8xxxxxxx) -- ASSUMED convention
            err_side = None
            if cmp[2] == 0 and cmp[3]:
                if bit == 0:            # r3 < 0
                    err_side = "taken" if want_true else "fallthrough"
                elif bit == 2:          # r3 == 0  (success == 0)
                    err_side = "fallthrough" if want_true else "taken"
            return {"test": cmp[1], "branch_if": cond, "taken": "0x%08X" % tgt,
                    "fallthrough": "0x%08X" % (a + 4), "error_side": err_side or "?",
                    "test_at": "+%d insn" % k}
        if op == 19 and ((w >> 1) & 0x3FF) == 16:             # bclr (e.g. beqlr)
            always, want_true, bi = _bc_cond(w)
            if not always and (bi >> 2) == cmp[0]:
                return {"test": cmp[1], "branch_if": "return-to-caller on cond bit %d=%s" % (bi & 3, want_true),
                        "taken": "return", "fallthrough": "0x%08X" % (a + 4), "error_side": "?", "test_at": "+%d insn" % k}
        if op == 18:
            return {"test": cmp[1], "branch_if": "no conditional branch found", "taken": "-", "fallthrough": "-",
                    "error_side": "?", "test_at": "+%d insn" % k}
    if cmp:
        return {"test": cmp[1], "branch_if": "branch beyond window", "taken": "-", "fallthrough": "-",
                "error_side": "?", "test_at": "-"}
    return None

def build_callgraph(elf, fmap, imports, names):
    """Read-only static analysis. Returns a JSON-able dict with derived
    numbers only (addresses, counts, decoded conditions) -- no code bytes."""
    words = {}
    for a, w in elf.text_words():
        words[a] = w
    word_at = words.get
    stub2nid = {e["stub"]: e["nid"] for e in imports if e.get("stub")}
    nid2lib = {e["nid"]: e["lib"] for e in imports}
    edges, redges = {}, {}
    imp_by_fn = {}
    sites = {}
    for a, w in words.items():
        op = w >> 26
        if op != 18:
            continue
        lk = w & 1
        li = w & 0x03FFFFFC
        if li & 0x02000000:
            li -= 0x04000000
        tgt = (li if (w & 2) else a + li) & 0xFFFFFFFF
        caller = fmap.find(a) if fmap else None
        nid = stub2nid.get(tgt)
        if nid is not None:
            sites.setdefault(nid, []).append((a, caller, bool(lk)))
            if caller is not None:
                imp_by_fn.setdefault(caller, set()).add(nid)
            continue
        if lk and fmap and caller is not None:
            callee = fmap.find(tgt)
            if callee is not None and callee != caller:
                edges.setdefault(caller, set()).add(callee)
                redges.setdefault(callee, set()).add(caller)
    # entry: PS3 ELF e_entry is an OPD (function descriptor) -- ASSUMED; we
    # accept either a code address or an OPD whose first word is code.
    entry_code = None
    if fmap:
        if fmap.find(elf.entry) is not None:
            entry_code = fmap.find(elf.entry)
        else:
            w0 = elf.u32(elf.entry)
            if w0 is not None and fmap.find(w0) is not None:
                entry_code = fmap.find(w0)
    depth = {}
    if entry_code is not None:
        depth[entry_code] = 0
        frontier = [entry_code]
        while frontier:
            nxt = []
            for f in frontier:
                for c in edges.get(f, ()):
                    if c not in depth:
                        depth[c] = depth[f] + 1
                        nxt.append(c)
            frontier = nxt
    out = {"tool": "nid_autolink %s callgraph" % VERSION, "functions": len(fmap) if fmap else 0,
           "entry": "0x%08X" % entry_code if entry_code is not None else None,
           "reachable_from_entry_direct": len(depth), "imports": {}}
    for e in imports:
        nid = e["nid"]
        ss = sites.get(nid, [])
        callers = sorted({c for _, c, _ in ss if c is not None})
        ctx_hits = {}
        for c in callers:
            seen = {c}
            frontier = [c]
            for _lvl in range(2):                      # caller + 2 levels of its callers
                nxt = []
                for f in frontier:
                    for g in redges.get(f, ()):
                        if g not in seen:
                            seen.add(g); nxt.append(g)
                frontier = nxt
            for f in seen:
                for other in imp_by_fn.get(f, ()):
                    if other == nid:
                        continue
                    tag = call_context(nid2lib.get(other, "?"), names.get(other, ""))
                    ctx_hits[tag] = ctx_hits.get(tag, 0) + 1
        rec = {"lib": e["lib"], "name": names.get(nid, ""), "nid": "0x%08X" % nid,
               "stub": "0x%08X" % e.get("stub", 0), "call_sites": len(ss),
               "tail_calls": sum(1 for _, _, lk in ss if not lk),
               "distinct_callers": len(callers),
               "min_depth_from_entry": min((depth[c] for c in callers if c in depth), default=None),
               "callers_reachable_direct": sum(1 for c in callers if c in depth),
               "context_hits": ctx_hits, "sites": []}
        for a, c, lk in sorted(ss)[:64]:
            rt = decode_ret_test(word_at, a) if lk else None
            rec["sites"].append({"site": "0x%08X" % a, "caller": "0x%08X" % c if c is not None else None,
                                 "depth": depth.get(c), "ret_test": rt})
        rec["ret_tested_sites"] = sum(1 for s in rec["sites"] if s["ret_test"])
        out["imports"]["0x%08X" % nid] = rec
    return out

def lifted_callgraph(lifted_dirs, imports, names):
    """Fallback when no ELF: read lifted C (ps3recomp ppu_lifter output) read-only.
    KNOWN lowering (ppu_lifter.py e85647a): a bl is `ctx->lr = 0xRET; func_T(ctx);`
    and an import stub body is `ps3_hle_call(0xNID, ctx)`. Only counts callers and
    whether r3 is compared soon after; no branch decode."""
    stub2nid = {e["stub"]: e["nid"] for e in imports if e.get("stub")}
    defrx = re.compile(r"^(?:static\s+)?void\s+\w*func_([0-9A-Fa-f]{8})\s*\(\s*ppu_context\s*\*\s*ctx\s*\)\s*\{", re.M)
    callrx = re.compile(r"ctx->lr\s*=\s*0x([0-9A-Fa-f]+);\s*\w*func_([0-9A-Fa-f]{8})\(ctx\);")
    res = {}
    for d in lifted_dirs:
        for p in glob.glob(os.path.join(d, "**", "*.c*"), recursive=True):
            try:
                txt = open(p, encoding="latin1").read()
            except OSError:
                continue
            defs = [(m.start(), int(m.group(1), 16)) for m in defrx.finditer(txt)]
            dpos = [x[0] for x in defs]
            for m in callrx.finditer(txt):
                tgt = int(m.group(2), 16)
                nid = stub2nid.get(tgt)
                if nid is None:
                    continue
                i = bisect.bisect_right(dpos, m.start()) - 1
                caller = defs[i][1] if i >= 0 else None
                after = txt[m.end():m.end() + 600]
                tested = bool(re.search(r"\(u?int(?:32|64)_t\)ctx->gpr\[3\]", after[:400]))
                r = res.setdefault(nid, {"call_sites": 0, "callers": set(), "ret_tested_sites": 0})
                r["call_sites"] += 1
                if caller is not None:
                    r["callers"].add(caller)
                r["ret_tested_sites"] += tested
    out = {"tool": "nid_autolink %s lifted-callgraph" % VERSION, "imports": {}}
    for e in imports:
        r = res.get(e["nid"], {"call_sites": 0, "callers": set(), "ret_tested_sites": 0})
        out["imports"]["0x%08X" % e["nid"]] = {
            "lib": e["lib"], "name": names.get(e["nid"], ""), "nid": "0x%08X" % e["nid"],
            "call_sites": r["call_sites"], "distinct_callers": len(r["callers"]),
            "ret_tested_sites": r["ret_tested_sites"], "min_depth_from_entry": None,
            "context_hits": {}, "sites": [{"caller": "0x%08X" % c} for c in sorted(r["callers"])[:64]]}
    return out

# --- spec files ---------------------------------------------------------------
def read_front_matter(path):
    """Tiny 'key: value' front-matter reader (between the first two '---')."""
    meta = {}
    try:
        txt = open(path, encoding="utf-8").read()
    except OSError:
        return meta
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", txt, re.S)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            meta[k.strip()] = v.split(" #")[0].strip()
    return meta

def load_specs(spec_dir):
    specs = {}
    for p in glob.glob(os.path.join(spec_dir, "**", "*.md"), recursive=True):
        meta = read_front_matter(p)
        if meta.get("nid"):
            try:
                specs[int(meta["nid"], 16)] = (p, meta)
            except ValueError:
                pass
    return specs

VERDICTS = {
    "needs-real-impl": "game uses real data/state from it",
    "correct-as-documented-error": "a documented error IS what real hardware returns in this situation (e.g. offline)",
    "ok-setting-sink": "documented as store-a-setting + CELL_OK; nothing in the API reads it back; PC has no visible equivalent",
    "owned-by-salem": "movie/cellSail work owned by Salem",
    "unresearched": "no verified spec yet",
}

NET_LIBS = ("sceNp", "sceNp2", "sceNpTus", "sys_net", "cellSysutilAvc2", "cellNetCtl", "sceNpTrophy")
def prelim_class(lib, name):
    """A hint only (ASSUMED). Never a verdict: an error return is acceptable only after
    the documented real-hardware result for that situation is found and written down."""
    if lib in NET_LIBS:
        return ("\nPreliminary class (ASSUMED, not a verdict): network/PSN feature. Offline single-player is "
                "probably served by the documented 'not signed in / not connected' result, BUT any output "
                "pointer must still be written. VERIFY the documented code and the game's branch before "
                "changing the verdict.\n")
    return ""

def write_template_spec(spec_dir, row):
    lib = row["lib"]; name = row["name"] or "nid_%s" % row["nid_hex"][2:]
    d = os.path.join(spec_dir, lib)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".md")
    if os.path.exists(p):
        return p, False
    owner = lib in OWNED_BY_SALEM or name.startswith(OWNED_BY_SALEM)
    verdict = "owned-by-salem" if owner else "unresearched"
    open(p, "w", encoding="utf-8").write(
        "---\nnid: %s\nlib: %s\nname: %s\nstatus_pc: %s\nverdict: %s\nsignature: UNKNOWN\noutputs: \npoison_ret: no\nconfidence: none\n---\n"
        "# %s (%s, %s)\n\n**UNRESEARCHED template generated by nid_autolink.py %s.** Nothing below is verified.\n\n"
        "- Prototype: VERIFY (public header / psdevwiki / observed registers)\n- Params & big-endian layouts: VERIFY\n"
        "- Return codes: VERIFY\n- Side effects: VERIFY\n- What the game does with the result: run `--mode callgraph` (ret_test per site)\n"
        "- Minimal correct PC behaviour: VERIFY\n- Acceptance test: VERIFY\n%s%s"
        % (row["nid_hex"], lib, name, row["status"], verdict, name, row["nid_hex"], lib, VERSION,
           "\nOwner: **Salem** (cellSail/movie). Listed here only for dependencies.\n" if owner else "",
           prelim_class(lib, name)))
    return p, True

# --- impact ranking -------------------------------------------------------------
def impact_score(row, ev, cg, spec_meta):
    """Documented, ASSUMED weights. Returns (score, parts list)."""
    parts = []
    sc = 0
    w = int(row.get("weight") or 2)
    sc += 2 * w; parts.append("module %d" % (2 * w))
    st = row["status"]
    b = {"missing": 10, "dead-reg": 10, "stub": 5, "partial": 3, "uncertain": 5, "conditional": 0}.get(st, 0)
    sc += b; parts.append("status %d" % b)
    if ev:
        tot = ev["total"] or 1
        r = min(30, int(8 * math.log10(tot + 1) + 6)) if tot else 0
        r += min(10, 2 * len(ev["lrs"]))
        sc += r; parts.append("runtime %d (%s%d calls, %d LRs)" % (r, "" if ev["exact"] else ">=", tot, len(ev["lrs"])))
    if cg:
        s = min(10, cg.get("call_sites", 0)) + min(10, 2 * cg.get("distinct_callers", 0))
        dpt = cg.get("min_depth_from_entry")
        if dpt is not None:
            s += 10 if dpt <= 6 else 5
        if cg.get("ret_tested_sites"):
            s += 10
        ctx = cg.get("context_hits") or {}
        if ctx:
            top = max(ctx, key=ctx.get)
            s += {"core": 8, "media": 4, "ui": 4, "other": 2, "net": -8}.get(top, 0)
        sc += s; parts.append("static %d" % s)
    v = (spec_meta or {}).get("verdict", "unresearched")
    if v in ("ok-setting-sink", "correct-as-documented-error"):
        parts.append("verdict says a small, documented change closes it")
    return sc, parts

import math

def rank_master(report_csv, ev, cg, specs, spec_dir, out_dir, make_templates=True):
    rows = list(csv.DictReader(open(report_csv, encoding="utf-8")))
    todo = [r for r in rows if r["status"] in ("missing", "stub", "partial", "dead-reg", "uncertain", "conditional")]
    out = []
    for r in todo:
        nid = int(r["nid_hex"], 16)
        sp = specs.get(nid)
        if sp is None and make_templates:
            p, _ = write_template_spec(spec_dir, r)
            sp = (p, read_front_matter(p))
            specs[nid] = sp
        meta = sp[1] if sp else {}
        cgi = (cg or {}).get("imports", {}).get(r["nid_hex"]) if cg else None
        sc, parts = impact_score(r, ev.get(nid), cgi, meta)
        owner = r["lib"] in OWNED_BY_SALEM
        out.append({"rank": 0, "score": sc, "lib": r["lib"], "nid": r["nid_hex"], "name": r["name"],
                    "status": r["status"], "verdict": meta.get("verdict", "unresearched"),
                    "confidence": meta.get("confidence", "none"),
                    "owner": "Salem (cellSail)" if owner else "math/HLE",
                    "calls": ("%s%d" % ("" if ev.get(nid, {}).get("exact") else ">=", ev[nid]["total"])) if nid in ev else "-",
                    "lrs": " ".join(sorted(ev[nid]["lrs"]))[:80] if nid in ev else "",
                    "caller_fns": " ".join(ev[nid].get("caller_fns", [])) if nid in ev else "",
                    "sites": cgi.get("call_sites") if cgi else "",
                    "callers": cgi.get("distinct_callers") if cgi else "",
                    "ret_tested": cgi.get("ret_tested_sites") if cgi else "",
                    "depth": cgi.get("min_depth_from_entry") if cgi else "",
                    "spec": os.path.relpath(sp[0], out_dir) if sp else "",
                    "why": "; ".join(parts)})
    out.sort(key=lambda x: (x["owner"] != "math/HLE", -x["score"], x["lib"], x["name"]))
    for i, x in enumerate(out, 1):
        x["rank"] = i
    os.makedirs(out_dir, exist_ok=True)
    cols = ["rank", "score", "verdict", "confidence", "status", "lib", "nid", "name", "owner", "calls", "lrs", "caller_fns",
            "sites", "callers", "ret_tested", "depth", "spec", "why"]
    with open(os.path.join(out_dir, "master_ranked.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f); wr.writerow(cols)
        for x in out:
            wr.writerow([x[c] for c in cols])
    L = ["# Master ranked list: missing/stub/partial/conditional imports",
         "", "Generated %s by nid_autolink.py %s. Inputs: report=`%s`, logs with LR evidence=%d NIDs, call graph=%s, specs=%d." %
         (time.strftime("%Y-%m-%d %H:%M"), VERSION, os.path.basename(report_csv), len(ev), "yes" if cg else "no (run --mode callgraph on the PC)", len(specs)),
         "", "Score = module weight + status + runtime evidence (calls, distinct LRs) + static evidence (sites, callers, depth from entry, return tested, caller context). Weights are ASSUMED; the evidence numbers are measured.",
         "", "Verdicts: " + "; ".join("`%s` = %s" % kv for kv in VERDICTS.items()), "",
         "| # | score | verdict | status | module | name | calls | LRs (caller fn) | sites/callers/ret-tested | spec |",
         "|---:|---:|---|---|---|---|---|---|---|---|"]
    for x in out:
        L.append("| %d | %d | %s | %s | %s | `%s` %s | %s | %s | %s | [spec](%s) |" % (
            x["rank"], x["score"], x["verdict"], x["status"], x["lib"], x["name"], x["nid"], x["calls"],
            ((x["lrs"][:40] + (" (fn %s)" % x["caller_fns"][:24] if x["caller_fns"] else "")) or "-"), ("%s/%s/%s" % (x["sites"], x["callers"], x["ret_tested"])) if x["sites"] != "" else "n/a",
            x["spec"].replace("\\", "/")))
    open(os.path.join(out_dir, "master_ranked.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return out

# --- poison (0xCD) diagnostic -----------------------------------------------------
def parse_outputs(s):
    """'r4:4, r5:16' -> [(4,4),(5,16)]  ;  '' -> []"""
    out = []
    for tok in re.findall(r"r(\d+)\s*:\s*(\d+)", s or ""):
        out.append((int(tok[0]), int(tok[1])))
    return out

def make_poison_inc(specs):
    """One handler per spec that lists outputs or poison_ret. Gated by
    SF_POISON=<name|0xNID> (exactly one per run). Registration must run FIRST
    (first matching ctx registration wins -- ppu_hle.cpp e85647a:70, VERIFY v020)."""
    L = ["/* sf_poison.inc -- GENERATED by nid_autolink.py %s on %s. DIAGNOSTIC ONLY, NOT A FIX." % (VERSION, time.strftime("%Y-%m-%d %H:%M")),
         " * Off by default. Enable ONE function per run: SF_POISON=<name or 0xNID>.",
         " * The chosen handler logs the call, fills the listed OUTPUT buffers with 0xCD bytes",
         " * (and r3=0xCDCDCDCD if the spec says poison_ret: yes), else returns CELL_OK.",
         " * If the game then behaves differently / crashes, it READS that output -> real impl needed.",
         " * The poison handler REPLACES the current handler for that NID for the whole run (it does not call it).",
         " * Call sf_register_poison() FIRST in ps3_load_prx_modules(): the first ctx registration wins. */",
         "#include <cstdint>", "#include <cstdio>", "#include <cstdlib>", "#include <cstring>",
         "struct ppu_context;",
         'extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));',
         "/* needs ppu_context (gpr/lr/thread_id) and vm_write32 from ppu_memory.h: include this file",
         "   in port/stubs.cpp AFTER the runtime headers, like the strikeforce_*.inc files. */",
         "namespace sf_poison {",
         "static unsigned g_n = 0;",
         "static void fill(uint32_t ea, uint32_t n) { if (!ea) return; uint32_t i = 0;",
         "    for (; i + 4 <= n; i += 4) vm_write32(ea + i, 0xCDCDCDCDu);",
         "    /* sizes are whole 4-byte words (spec sizes are multiples of 4) */ }"]
    regs = []
    for nid, (path, meta) in sorted(specs.items()):
        outs = parse_outputs(meta.get("outputs", ""))
        pret = meta.get("poison_ret", "no").lower().startswith("y")
        if not outs and not pret:
            continue
        name = meta.get("name", "nid_%08X" % nid)
        fn = "h_" + c_ident(name)
        L.append("static void %s(ppu_context* ctx)" % fn)
        L.append("{")
        L.append("    const unsigned n = ++g_n; const uint64_t* g = ctx->gpr;")
        L.append('    if (n <= 16 || (n & (n - 1)) == 0) fprintf(stderr, "[sf-poison] POISON %s nid=0x%08X call#%%u tid=%%u lr=0x%%08X r3=%%016llX r4=%%016llX r5=%%016llX r6=%%016llX\\n",' % (name, nid))
        L.append("        n, (unsigned)ctx->thread_id, (unsigned)ctx->lr, (unsigned long long)g[3], (unsigned long long)g[4], (unsigned long long)g[5], (unsigned long long)g[6]);")
        for reg, size in outs:
            L.append("    fill((uint32_t)ctx->gpr[%d], %du);   /* output r%d, %d bytes (from spec) */" % (reg, size, reg, size))
        L.append("    ctx->gpr[3] = %s;" % ("0xCDCDCDCDull" if pret else "0 /* CELL_OK */"))
        L.append("}")
        regs.append((nid, name, fn))
    L.append("} /* namespace sf_poison */")
    L.append("static void sf_register_poison(void)")
    L.append("{")
    L.append('    const char* e = getenv("SF_POISON"); if (!e || !*e) return;')
    L.append('    if (strchr(e, \',\')) { fprintf(stderr, "[sf-poison] refusing: one function per run (got \\"%s\\")\\n", e); return; }')
    for nid, name, fn in regs:
        L.append('    if (!strcmp(e, "%s") || !strcmp(e, "0x%08X")) { ps3_hle_register_ctx(0x%08Xu, "%s[sf-POISON-DIAG]", sf_poison::%s);'
                 ' fprintf(stderr, "[sf-poison] armed %s (diagnostic, not a fix)\\n"); return; }' % (name, nid, nid, name, fn, name))
    L.append('    fprintf(stderr, "[sf-poison] SF_POISON=%s matches no poison spec\\n", e);')
    L.append("}")
    return "\n".join(L) + "\n", len(regs)

# ---------------------------------------------------------------------------
# 8. Self-test
# ---------------------------------------------------------------------------
def selftest():
    import tempfile, shutil
    ok = True
    def check(cond, msg):
        nonlocal ok
        print(("  PASS " if cond else "  FAIL ") + msg)
        ok = ok and cond
    print("[selftest] 1. NID formula against published values")
    # psdevwiki NID page; mercs2_exemap tests (citing RPCS3 REG_FUNC); our 2026-11-26 import list
    for n, v in [("_sys_sprintf", 0xA1F9EAFE), ("_ZNKSt13runtime_error4whatEv", 0x5333BDC9),
                 ("cellSysmoduleLoadModule", 0x32267A31), ("cellFsClose", 0x2CB51F0D),
                 ("sceNpBasicGetCustomInvitationEntryCount", 0xA8AFA7D4),
                 ("UCS2stoUTF8s", 0x2AD091C6)]:
        check(nid_of(n) == v, "%s -> 0x%08X (expect 0x%08X)" % (n, nid_of(n), v))
    check(nid_of("module_start") != 0xBC9A0086, "module_start is a fixed NID, not its hash")

    tmp = tempfile.mkdtemp(prefix="autolink_st_")
    try:
        print("[selftest] 2. synthetic ELF import table + call-site scan")
        A, B = nid_of("cellFsClose"), nid_of("cellAtracGetVacantSize")
        base = 0x10000
        text_va, text_sz = base + 0x1000, 0x100
        data_va = base + 0x2000
        # data layout
        name_va = data_va + 0x00
        fnid_va = data_va + 0x20
        fstub_va = data_va + 0x30
        rec_va = data_va + 0x40
        prm_va = data_va + 0x80
        glue_a, glue_b = text_va + 0x80, text_va + 0xA0
        data = bytearray(0x100)
        data[0:12] = b"sys_fs\0\0\0\0\0\0"
        struct.pack_into(">II", data, 0x20, A, B)
        struct.pack_into(">II", data, 0x30, glue_a, glue_b)
        rec = struct.pack(">BBHHHHHBBBBIIIII", 0x2C, 0, 1, 0, 2, 0, 0, 0, 0, 0, 0, name_va, fnid_va, fstub_va, 0, 0) + b"\0" * 8
        data[0x40:0x40 + len(rec)] = rec
        struct.pack_into(">IIIIIIII", data, 0x80, 0x28, 0x1B434CEC, 2, 0, 0, 0, rec_va, rec_va + 0x2C)
        text = bytearray(text_sz)
        def bl(frm, to):
            return 0x48000001 | ((to - frm) & 0x03FFFFFC)
        struct.pack_into(">I", text, 0x00, bl(text_va + 0x00, glue_a))
        struct.pack_into(">I", text, 0x04, (11 << 26) | (7 << 23) | (3 << 16) | 0)   # cmpwi cr7,r3,0
        struct.pack_into(">I", text, 0x10, bl(text_va + 0x10, glue_a))
        struct.pack_into(">I", text, 0x14, 0x60000000)                               # nop, no check
        struct.pack_into(">I", text, 0x20, bl(text_va + 0x20, glue_b))
        struct.pack_into(">I", text, 0x24, (31 << 26) | (3 << 21) | (3 << 16) | (3 << 11) | (444 << 1) | 1)  # or. r3,r3,r3
        ehdr_sz, ph_sz, nph = 0x40, 0x38, 3
        off_text = 0x200; off_data = 0x400
        hdr = bytearray(ehdr_sz)
        hdr[0:6] = b"\x7fELF\x02\x02"; hdr[6] = 1
        struct.pack_into(">HHIQQQIHHHHHH", hdr, 0x10, 2, 21, 1, text_va, ehdr_sz, 0, 0, ehdr_sz, ph_sz, nph, 0, 0, 0)
        phs = b""
        phs += struct.pack(">IIQQQQQQ", 1, 5, off_text, text_va, text_va, text_sz, text_sz, 0x10)
        phs += struct.pack(">IIQQQQQQ", 1, 6, off_data, data_va, data_va, len(data), len(data), 0x10)
        phs += struct.pack(">IIQQQQQQ", 0x60000002, 4, off_data + 0x80, prm_va, prm_va, 0x28, 0x28, 4)
        img = bytearray(0x600)
        img[0:ehdr_sz] = hdr; img[ehdr_sz:ehdr_sz + len(phs)] = phs
        img[off_text:off_text + text_sz] = text; img[off_data:off_data + len(data)] = data
        elf_p = os.path.join(tmp, "EBOOT.elf"); open(elf_p, "wb").write(img)
        el = Elf(elf_p); im = el.imports()
        check(len(im) == 2 and im[0]["lib"] == "sys_fs" and im[0]["nid"] == A and im[1]["nid"] == B,
              "import table parsed: %s" % [(e["lib"], "0x%08X" % e["nid"], "0x%X" % e["stub"]) for e in im])
        cs = elf_callsites(el, im)
        check(cs.get(A) == [2, 1], "cellFsClose: 2 bl sites, 1 checks r3 (got %s)" % cs.get(A))
        check(cs.get(B) == [1, 1], "cellAtracGetVacantSize: 1 bl site, checks r3 via or. (got %s)" % cs.get(B))

        print("[selftest] 3. synthetic source tree classification")
        src = os.path.join(tmp, "src"); os.makedirs(os.path.join(src, "port"))
        os.makedirs(os.path.join(src, "runtime"))
        open(os.path.join(src, "runtime", "rt.cpp"), "w").write(r'''
extern "C" void ps3_hle_register(unsigned nid, const char* name, void* h);
extern "C" void ps3_hle_register_ctx(unsigned nid, const char* name, void (*fn)(ppu_context*));
extern "C" int cellFsClose(int fd) { if (fd < 0) return CELL_EBADF; host_close(fd); g_open--; return CELL_OK; }
extern "C" int cellGameBootCheck(unsigned a, unsigned b) { (void)a; (void)b; printf("x\n"); return CELL_OK; }
static void crt_ok(ppu_context* ctx) { ctx->gpr[3] = 0; }
/* TODO: implement */
static void hle_half(ppu_context* ctx) { do_a(); ctx->gpr[3] = 0; }
static void h_sock(ppu_context* ctx) { RET(real_socket(ctx)); }
static void net_register(void) {
    static const struct { const char* n; void (*f)(ppu_context*); } T[] = { { "getsockname", h_sock } };
    for (auto& t : T) ps3_hle_register_ctx(ps3_compute_nid(t.n), t.n, t.f);
}
void ppu_hle_register_all(void) {
    ps3_hle_register(0x2CB51F0Du, "cellFsClose", (void*)cellFsClose);
    ps3_hle_register(0xF52639EAu, "cellGameBootCheck", (void*)cellGameBootCheck);
    ps3_hle_register_ctx(ps3_compute_nid("_sys_process_atexitspawn"), "_sys_process_atexitspawn", crt_ok);
    ps3_hle_register_ctx(ps3_compute_nid("cellSailPlayerSetPaused"), "cellSailPlayerSetPaused", hle_half);
    if (getenv("PS3_NET_ONLINE")) net_register();
}
''')
        open(os.path.join(src, "port", "strikeforce_x.inc"), "w").write(r'''
static void hle_kb(ppu_context* ctx) /* comment between ) and { */
{
    uint32_t p = (uint32_t)ctx->gpr[3];
    vm_write32(p + 0, 1); vm_write32(p + 4, 2); fill_config(p);
    ctx->gpr[3] = 0;
}
static void sf_register_x(void) { ps3_hle_register_ctx(0x1F71ECBEu, "cellKbGetConfiguration[sf-kb]", hle_kb); }
static void sf_register_never(void) { ps3_hle_register_ctx(0xC9A95FCBu, "cellAtracGetVacantSize[sf]", hle_kb); }
void ps3_load_prx_modules(void) { sf_register_x(); }
''')
        names = ["cellFsClose", "cellGameBootCheck", "_sys_process_atexitspawn", "cellSailPlayerSetPaused",
                 "getsockname", "cellKbGetConfiguration", "cellAtracGetVacantSize", "sceNpBasicAddFriend"]
        imp_p = os.path.join(tmp, "EBOOT.imports.json")
        json.dump([{"library": "x", "nid": "0x%08x" % nid_of(n), "stub": "0x%x" % (0x5cbd14 + 0x20 * i)}
                   for i, n in enumerate(names)], open(imp_p, "w"))
        log_p = os.path.join(tmp, "stderr.log")
        open(log_p, "w").write(
            "[hle] UNRESOLVED NID 0x%08X -> faking CELL_OK (unregistered import)\n"
            "[hle]   0x%08X          sp =00000000D0000F00 lr =00000000004A1234\n"
            "[hle] UNRESOLVED SUMMARY nid=0x%08X hits=37 lib=cellAtrac\n"
            "  12345  cellGameBootCheck                    tid=1   lr=0x00012345\n"
            % (nid_of("sceNpBasicAddFriend"), nid_of("sceNpBasicAddFriend"), nid_of("cellAtracGetVacantSize")))
        out = os.path.join(tmp, "out")
        ns = argparse.Namespace(elf=None, imports=imp_p, src=[src], headers=[], names=[], protos_json=[],
                                log=[log_p], out=out, weight=[])
        rows = run(ns)
        st = {r["name"]: r for r in rows}
        exp = {"cellFsClose": "linked", "cellGameBootCheck": "stub", "_sys_process_atexitspawn": "stub",
               "cellSailPlayerSetPaused": "stub", "getsockname": "conditional",
               "cellKbGetConfiguration": "linked", "cellAtracGetVacantSize": "dead-reg",
               "sceNpBasicAddFriend": "missing"}
        for n, s in exp.items():
            got = st.get(n, {}).get("status")
            check(got == s, "%-28s -> %-11s (expect %s)" % (n, got, s))
        check(all(st[n]["name_verified"] == "sha1" for n in exp), "all names resolved by SHA-1 from candidates")
        check(st["cellAtracGetVacantSize"]["calls"] == 37, "SUMMARY count read (37)")
        check(st["sceNpBasicAddFriend"]["calls"] == ">=1", "first-hit log -> '>=1'")
        check(st["cellGameBootCheck"]["calls"] == 12345, "PS3_HLE_TOP window count read")
        check("0x004A1234" in st["sceNpBasicAddFriend"]["lr"], "caller lr kept")
        check(any("cellAtrac" in x for x in st["cellAtracGetVacantSize"]["notes"]), "cellAtrac flagged")
        check(rows[0]["name"] == "cellAtracGetVacantSize" and rows[0]["priority"] == "P1", "cellAtrac ranked first (P1)")
        inc = open(os.path.join(out, "sf_autolink_stubs.inc")).read()
        check("[sf-autolink-STUB]" in inc and "SF_AUTOLINK" in inc and "0x%08Xu" % nid_of("sceNpBasicAddFriend") in inc,
              "skeleton: labelled STUB, opt-in, NID present")
        check(all(os.path.exists(os.path.join(out, f)) for f in ("report.csv", "summary.md", "report.json")), "reports written")
        # read-only: inputs unchanged
        check(open(elf_p, "rb").read() == bytes(img), "ELF input unchanged (read-only)")
        # ------------------------------------------------------------------ v2
        print("[selftest] 4. v2: return-test decode + call graph (synthetic ELF)")
        def mk_elf(path, words, glue, nids, entry_off):
            base_text, text_sz = 0x20000, 0x200
            data_va = 0x30000
            data = bytearray(0x100)
            data[0:8] = b"cellX\0\0\0"
            for k, n in enumerate(nids):
                struct.pack_into(">I", data, 0x20 + 4 * k, n)
                struct.pack_into(">I", data, 0x40 + 4 * k, base_text + glue[k])
            rec = struct.pack(">BBHHHHHBBBBIIIII", 0x2C, 0, 1, 0, len(nids), 0, 0, 0, 0, 0, 0,
                              data_va, data_va + 0x20, data_va + 0x40, 0, 0) + b"\0" * 8
            data[0x60:0x60 + len(rec)] = rec
            struct.pack_into(">IIIIIIII", data, 0xA0, 0x28, 0x1B434CEC, 2, 0, 0, 0, data_va + 0x60, data_va + 0x8C)
            struct.pack_into(">I", data, 0xE0, base_text + entry_off)          # OPD of entry
            text = bytearray(text_sz)
            for off, w in words.items():
                struct.pack_into(">I", text, off, w(base_text + off) if callable(w) else w)
            hdr = bytearray(0x40); hdr[0:6] = b"\x7fELF\x02\x02"; hdr[6] = 1
            struct.pack_into(">HHIQQQIHHHHHH", hdr, 0x10, 2, 21, 1, data_va + 0xE0, 0x40, 0, 0, 0x40, 0x38, 3, 0, 0, 0)
            phs = struct.pack(">IIQQQQQQ", 1, 5, 0x200, base_text, base_text, text_sz, text_sz, 0x10)
            phs += struct.pack(">IIQQQQQQ", 1, 6, 0x400, data_va, data_va, len(data), len(data), 0x10)
            phs += struct.pack(">IIQQQQQQ", 0x60000002, 4, 0x400 + 0xA0, data_va + 0xA0, data_va + 0xA0, 0x28, 0x28, 4)
            img = bytearray(0x600); img[0:0x40] = hdr; img[0x40:0x40 + len(phs)] = phs
            img[0x200:0x200 + text_sz] = text; img[0x400:0x400 + len(data)] = data
            open(path, "wb").write(img)
            return base_text
        BL = lambda to: (lambda frm: 0x48000001 | ((to - frm) & 0x03FFFFFC))
        T = 0x20000
        N1, N2 = nid_of("cellAudioOutConfigure"), nid_of("sceNpBasicGetCustomInvitationEntryCount")
        words = {
            0x000: BL(T + 0x40),                                            # entry fn -> fn B
            0x040: BL(T + 0x180),                                           # fn B: bl Configure
            0x044: (11 << 26) | (7 << 23) | (3 << 16) | 0,                  # cmpwi cr7,r3,0
            0x048: (16 << 26) | (4 << 21) | (30 << 16) | 0x20,              # bne cr7,+0x20
            0x080: BL(T + 0x1A0),                                           # fn C (not reachable): bl NpCount
            0x084: (31 << 26) | (3 << 21) | (30 << 16) | (3 << 11) | (444 << 1),   # mr r30,r3
            0x088: (11 << 26) | (0 << 23) | (30 << 16) | 0,                 # cmpwi r30,0
            0x08C: (16 << 26) | (12 << 21) | (0 << 16) | 0x10,              # blt +0x10
        }
        elf2 = os.path.join(tmp, "E2.elf")
        mk_elf(elf2, words, [0x180, 0x1A0], [N1, N2], 0x000)
        e2 = Elf(elf2); im2 = e2.imports()
        fm = FuncMap([(T, T + 0x40, 0), (T + 0x40, T + 0x80, 0), (T + 0x80, T + 0xC0, 0)])
        cg = build_callgraph(e2, fm, im2, {N1: "cellAudioOutConfigure", N2: "sceNpBasicGetCustomInvitationEntryCount"})
        c1 = cg["imports"]["0x%08X" % N1]; c2 = cg["imports"]["0x%08X" % N2]
        check(cg["entry"] == "0x%08X" % T, "entry resolved through OPD (got %s)" % cg["entry"])
        check(c1["call_sites"] == 1 and c1["min_depth_from_entry"] == 1, "Configure: 1 site, depth 1 from entry")
        rt = c1["sites"][0]["ret_test"]
        check(rt and rt["branch_if"] == "not(r3 == 0)" and rt["taken"] == "0x%08X" % (T + 0x48 + 0x20) and rt["error_side"] == "taken",
              "Configure: bne after cmpwi decoded, error path = taken branch (%s)" % rt)
        rt2 = c2["sites"][0]["ret_test"]
        check(c2["min_depth_from_entry"] is None and rt2 and rt2["branch_if"] == "r3 < 0" and rt2["error_side"] == "taken",
              "NpCount: unreachable directly; mr r30,r3 tracked; blt = error path (%s)" % rt2)

        fj = os.path.join(tmp, "EBOOT.functions.json")
        json.dump([{"start": "0x%x" % a, "end": "0x%x" % b, "toc": "0x0", "opd": "0x0"} for a, b in
                   ((T, T + 0x40), (T + 0x40, T + 0x80), (T + 0x80, T + 0xC0))], open(fj, "w"))
        import subprocess
        cgo = os.path.join(tmp, "cg-out")
        pr = subprocess.run([sys.executable, os.path.abspath(__file__), "--mode", "callgraph", "--elf", elf2,
                             "--functions", fj, "--out", cgo], capture_output=True, text=True)
        cj = os.path.join(cgo, "callgraph.json")
        ok_cli = pr.returncode == 0 and os.path.exists(cj)
        if ok_cli:
            cjd = json.load(open(cj))
            ok_cli = cjd["imports"]["0x%08X" % N1]["min_depth_from_entry"] == 1 and cjd["functions"] == 3
        check(ok_cli, "CLI --mode callgraph writes callgraph.json (rc=%s %s)" % (pr.returncode, pr.stderr[-200:]))
        print("[selftest] 5. v2: per-LR log parse")
        lp = os.path.join(tmp, "run.log")
        open(lp, "w").write(
            "[sf-autolink] STUB sceNpBasicAddFriend nid=0x%08X call#1 tid=1 lr=0x00037924 r3=0\n"
            "[sf-autolink] STUB sceNpBasicAddFriend nid=0x%08X call#2 tid=1 lr=0x00037924 r3=0\n"
            "[sf-autolink] STUB sceNpBasicAddFriend nid=0x%08X call#8 tid=3 lr=0x00041000 r3=0\n"
            "[hle] UNRESOLVED NID 0x%08X -> faking CELL_OK (unregistered import)\n"
            "[hle]   0x%08X tid=1   r3 =0000000000000000 r4 =0\n"
            "[hle]   0x%08X          sp =00000000D0000F00 lr =0000000000037920\n"
            "  500  cellAudioOutConfigure                tid=1   lr=0x00012345\n"
            % ((nid_of("sceNpBasicAddFriend"),) * 3 + (N2,) * 3))
        ev = parse_lr_logs([lp], {"cellAudioOutConfigure": N1})
        a = ev[nid_of("sceNpBasicAddFriend")]
        check(a["total"] == 8 and a["exact"] and a["lrs"] == {"0x00037924": 2, "0x00041000": 1} and a["tids"] == {1, 3},
              "sf-autolink lines: total 8, 2 LRs, tids {1,3} (%s)" % {k: a[k] for k in ("total", "lrs", "tids")})
        b = ev[N2]
        check(b["total"] == 1 and not b["exact"] and "0x00037920" in b["lrs"], "first-hit dump: >=1 call, lr kept")
        check(ev[N1]["total"] == 500 and ev[N1]["lrs"].get("0x00012345") == 500, "PS3_HLE_TOP window parsed")

        print("[selftest] 6. v2: specs + master rank + poison .inc")
        sd = os.path.join(tmp, "docs", "hle_spec", "cellSysutil"); os.makedirs(sd)
        open(os.path.join(sd, "cellAudioOutConfigure.md"), "w").write(
            "---\nnid: 0x%08X\nlib: cellSysutil\nname: cellAudioOutConfigure\nverdict: needs-real-impl\n"
            "outputs: r5:12\npoison_ret: yes\nconfidence: KNOWN\n---\n# spec\n" % N1)
        rep = os.path.join(tmp, "report.csv")
        with open(rep, "w", newline="") as f:
            wr = csv.writer(f); wr.writerow(["status", "lib", "nid_hex", "name", "weight"])
            wr.writerow(["stub", "cellSysutil", "0x%08X" % N1, "cellAudioOutConfigure", "3"])
            wr.writerow(["missing", "sceNp", "0x%08X" % N2, "sceNpBasicGetCustomInvitationEntryCount", "1"])
            wr.writerow(["missing", "cellSail", "0x%08X" % nid_of("cellSailDescriptorOpen"), "cellSailDescriptorOpen", "4"])
            wr.writerow(["linked", "cellFs", "0x2CB51F0D", "cellFsClose", "4"])
        mo = os.path.join(tmp, "master")
        ml = rank_master(rep, ev, cg, load_specs(os.path.join(tmp, "docs", "hle_spec")), os.path.join(tmp, "docs", "hle_spec"), mo)
        check(len(ml) == 3, "linked rows excluded (3 left)")
        check(ml[-1]["owner"].startswith("Salem"), "cellSail sorted last, owner Salem")
        check(ml[0]["name"] == "cellAudioOutConfigure" and ml[0]["verdict"] == "needs-real-impl" and ml[0]["spec"].endswith("cellAudioOutConfigure.md"),
              "spec verdict + link merged (%s)" % ml[0]["spec"])
        tpl = os.path.join(tmp, "docs", "hle_spec", "sceNp", "sceNpBasicGetCustomInvitationEntryCount.md")
        check(os.path.exists(tpl) and read_front_matter(tpl).get("verdict") == "unresearched", "UNRESEARCHED template created")
        check(read_front_matter(os.path.join(tmp, "docs", "hle_spec", "cellSail", "cellSailDescriptorOpen.md")).get("verdict") == "owned-by-salem",
              "cellSail template marked owned-by-salem")
        check(os.path.exists(os.path.join(mo, "master_ranked.md")) and os.path.exists(os.path.join(mo, "master_ranked.csv")), "master md+csv written")
        inc, npz = make_poison_inc(load_specs(os.path.join(tmp, "docs", "hle_spec")))
        check(npz == 1 and "fill((uint32_t)ctx->gpr[5], 12u)" in inc and "0xCDCDCDCDull" in inc and "SF_POISON" in inc
              and "one function per run" in inc, "poison .inc: 1 handler, r5 12 bytes, r3 poison, one-per-run gate")
        check(parse_outputs("r4:4, r6:16") == [(4, 4), (6, 16)], "outputs spec parser")
        ld = os.path.join(tmp, "lifted"); os.makedirs(ld)
        open(os.path.join(ld, "ppu_recomp_0.cpp"), "w").write(
            "void func_00010000(ppu_context* ctx) {\n"
            "    ctx->lr = 0x00010008; func_005CBD14(ctx); DRAIN_TRAMPOLINE(ctx);\n"
            "    { int64_t a = (int32_t)ctx->gpr[3]; int64_t b = 0; }\n}\n"
            "void func_00010100(ppu_context* ctx) {\n"
            "    ctx->lr = 0x00010104; func_005CBD14(ctx); DRAIN_TRAMPOLINE(ctx);\n}\n")
        lc = lifted_callgraph([ld], [{"lib": "cellSysutilAvc2", "nid": 0x11F071CB, "stub": 0x5CBD14}], {})
        li = lc["imports"]["0x11F071CB"]
        check(li["call_sites"] == 2 and li["distinct_callers"] == 2 and li["ret_tested_sites"] == 1,
              "lifted C fallback: 2 sites, 2 callers, 1 tests r3 (%s)" % {k: li[k] for k in ("call_sites", "distinct_callers", "ret_tested_sites")})
        rep2 = os.path.join(tmp, "report2.csv")
        with open(rep2, "w", newline="") as f:
            wr = csv.writer(f); wr.writerow(["status", "lib", "nid_hex", "name", "calls", "lr"])
            wr.writerow(["stub", "cellSysutil", "0x7F21C918", "cellOskDialogAddSupportLanguage", ">=1", "0x0049FD9C"])
            wr.writerow(["stub", "cellSysutil", "0x4692AB35", "cellAudioOutConfigure", "", ""])
        mev = merge_report_evidence(rep2, {})
        check(0x7F21C918 in mev and mev[0x7F21C918]["lrs"] == {"0x0049FD9C": 1} and not mev[0x7F21C918]["exact"]
              and 0x4692AB35 not in mev, "PC report.csv calls/LR merged as runtime evidence")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("[selftest] RESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1

def merge_report_evidence(path, ev):
    """report.csv (from --mode scan on the PC) already carries per-NID call counts and LRs
    from the PC logs; use them where the box has no better evidence for that NID."""
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            nid = int(r["nid_hex"], 16)
        except (KeyError, ValueError):
            continue
        calls = (r.get("calls") or "").strip()
        lr = (r.get("lr") or "").strip()
        if not calls and not lr:
            continue
        m = re.match(r"(>=)?(\d+)", calls)
        n = int(m.group(2)) if m else 1
        e = ev.setdefault(nid, {"total": 0, "exact": True, "lrs": {}, "tids": set(), "src": set()})
        if n > e["total"]:
            e["total"] = n; e["exact"] = not (m and m.group(1)) and bool(m)
        for x in re.findall(r"0x[0-9A-Fa-f]+", lr):
            e["lrs"].setdefault("0x%08X" % int(x, 16), 1)
        e.setdefault("src", set()).add("report.csv")
    return ev

def names_from_report(path):
    names = {}
    if path and os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            try:
                names[int(r["nid_hex"], 16)] = r.get("name", "")
            except (KeyError, ValueError):
                pass
    return names

def main():
    ap = argparse.ArgumentParser(description="Classify/rank/spec PS3 imports for a ps3recomp port (read-only on inputs).")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mode", choices=["scan", "callgraph", "rank", "poison"], default="scan",
                    help="scan (PC: classify sources) | callgraph (PC: static callers from ELF or lifted C) | "
                         "rank (box: master list + specs) | poison (box: generate 0xCD diagnostic .inc from specs)")
    g = ap.add_argument_group("import list (one of)")
    g.add_argument("--imports", help="EBOOT.imports.json (gen_imports/sfauto) or text '<lib> <nid>' lines")
    g.add_argument("--elf", help="decrypted EBOOT.elf (read-only; enables call-site + return-check scan)")
    ap.add_argument("--src", action="append", default=[], help="source root to scan (repeat): ps3recomp, port, port/bld")
    ap.add_argument("--headers", action="append", default=[], help="extra header dir for names/prototypes (repeat)")
    ap.add_argument("--names", action="append", default=[], help="extra candidate-name file (repeat)")
    ap.add_argument("--protos-json", dest="protos_json", action="append", default=[], help="nid_from_protos.json (auto-found under --src)")
    ap.add_argument("--log", action="append", default=[], help="stderr log / unresolved_nids.txt / findings.json (repeat, globs ok)")
    ap.add_argument("--weight", action="append", default=[], help="MODULE=N override for ranking")
    ap.add_argument("--exclude", action="append", default=[], help="regex of source paths to skip (repeat)")
    ap.add_argument("--functions", help="EBOOT.functions.json (ps3recomp) -- maps call sites/LRs to functions")
    ap.add_argument("--lifted", action="append", default=[], help="(callgraph without ELF) lifted C dir, read-only")
    ap.add_argument("--report", help="(rank/callgraph) report.csv from --mode scan")
    ap.add_argument("--callgraph", help="(rank) callgraph.json from --mode callgraph")
    ap.add_argument("--specs", help="(rank/poison) docs/hle_spec dir")
    ap.add_argument("--no-templates", action="store_true", help="(rank) do not create UNRESEARCHED spec templates")
    ap.add_argument("--out", default="autolink-out", help="output folder (the ONLY place written)")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    EXCLUDE_RX.extend(re.compile(x, re.I) for x in a.exclude)
    outp = os.path.abspath(a.out)
    for p in a.src + a.lifted + [x for x in (a.imports, a.elf) if x]:
        rp = os.path.abspath(p)
        if outp == rp or outp.startswith(rp.rstrip(os.sep) + os.sep):
            ap.error("--out must be a NEW folder outside every input (%s)" % p)
    log_paths = []
    for p in a.log:
        log_paths += sorted(glob.glob(p, recursive=True)) or [p]
    a.log = [p for p in log_paths if os.path.isfile(p)]
    if a.mode == "scan":
        if not (a.imports or a.elf):
            ap.error("give --imports or --elf")
        if not a.src:
            ap.error("give at least one --src root")
        run(a)
    elif a.mode == "callgraph":
        names = names_from_report(a.report)
        fmap = FuncMap.load(a.functions) if a.functions else None
        if a.elf:
            elf = Elf(a.elf)
            imps = elf.imports()
            cg = build_callgraph(elf, fmap, imps, names)
        elif a.lifted and a.imports:
            imps = read_imports_json(a.imports)
            cg = lifted_callgraph(a.lifted, imps, names)
        else:
            ap.error("callgraph needs --elf (best) or --lifted DIR + --imports")
        os.makedirs(a.out, exist_ok=True)
        json.dump(cg, open(os.path.join(a.out, "callgraph.json"), "w", encoding="utf-8"), indent=1)
        n_called = sum(1 for v in cg["imports"].values() if v["call_sites"])
        print("[autolink] callgraph: %d imports, %d with static call sites, functions=%s, entry=%s -> %s"
              % (len(cg["imports"]), n_called, cg.get("functions", "-"), cg.get("entry"), os.path.join(a.out, "callgraph.json")))
        if a.elf and n_called == 0:
            print("[autolink] WARNING: no call site matched any stub address -- stub address meaning differs (VERIFY); send this line back")
    elif a.mode == "rank":
        if not a.report:
            ap.error("rank needs --report report.csv")
        spec_dir = a.specs or os.path.join(a.out, "docs", "hle_spec")
        names = names_from_report(a.report)
        ev = parse_lr_logs(a.log, {v: k for k, v in names.items() if v})
        ev = merge_report_evidence(a.report, ev)
        cg = json.load(open(a.callgraph, encoding="utf-8")) if a.callgraph else None
        if a.functions and ev:
            fmap = FuncMap.load(a.functions)
            for v in ev.values():
                v["caller_fns"] = sorted({"0x%08X" % f for f in (fmap.find(int(lr, 16) - 4) for lr in v["lrs"]) if f is not None})
        specs = load_specs(spec_dir)
        out = rank_master(a.report, ev, cg, specs, spec_dir, a.out, not a.no_templates)
        print("[autolink] master list: %d entries -> %s" % (len(out), os.path.join(a.out, "master_ranked.md")))
    elif a.mode == "poison":
        if not a.specs:
            ap.error("poison needs --specs DIR")
        txt, n = make_poison_inc(load_specs(a.specs))
        os.makedirs(a.out, exist_ok=True)
        open(os.path.join(a.out, "sf_poison.inc"), "w", encoding="utf-8").write(txt)
        print("[autolink] sf_poison.inc: %d poison handlers (off unless SF_POISON=<one name>)" % n)

if __name__ == "__main__":
    main()

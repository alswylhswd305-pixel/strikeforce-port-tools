#!/usr/bin/env python3
"""gen_coverage.py -- static NV4097 method coverage of the legacy D3D12 path.

Parses Salem's tree (rsx_commands.c/.h, the D3D12 backend, rsx_vertex_fetch.c,
rsx_texture_layout.c, rsx_draw_engine.c, rsx_dispatch.c) and classifies every
NV4097 method offset 0x0000..0x1FFC (plus driver flips) as:

  handled           state stored by rsx_process_method AND read by the D3D12
                    draw/PSO path (outside printf/fprintf), or the method acts
                    directly (backend call, guest write, label/semaphore).
  stored-but-unused rsx_process_method stores it, nothing in the legacy draw
                    path reads it (only logs, or nothing).
  unhandled         rsx_process_method has no branch for it (falls through to
                    "return -1"). Methods that only rsx_draw_engine.c knows
                    count as unhandled: draw_engine_enabled=0 on this path.

Labels: the classification is mechanical (regex + condition evaluation), so
each entry is ASSUMED unless an override with a file:line evidence string
makes it KNOWN. Evidence lines are written out so a human can VERIFY.

No emulator (GPL) code is used; method names come from Salem's headers first,
then from a public NV40/RSX name list (nv4097_names.py).

Usage:
  python3 gen_coverage.py [--src DIR] [--backend FILE] [--out DIR]
"""
import argparse, hashlib, json, os, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nv4097_names  # noqa: E402

# ----------------------------------------------------------------- text utils

def strip_comments(s):
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '/' and i + 1 < n and s[i + 1] == '*':
            j = s.find('*/', i + 2); j = n if j < 0 else j + 2
            out.append(re.sub(r'[^\n]', ' ', s[i:j])); i = j
        elif c == '/' and i + 1 < n and s[i + 1] == '/':
            j = s.find('\n', i); j = n if j < 0 else j
            out.append(' ' * (j - i)); i = j
        elif c in '"\'':
            j = i + 1
            while j < n and s[j] != c:
                j += 2 if s[j] == '\\' else 1
            out.append(s[i:j + 1]); i = j + 1
        else:
            out.append(c); i += 1
    return ''.join(out)


def match_close(s, i, o='(', c=')'):
    """s[i] == o; return index of the matching c."""
    d = 0
    k = i
    n = len(s)
    while k < n:
        ch = s[k]
        if ch in '"\'':
            q = ch; k += 1
            while k < n and s[k] != q:
                k += 2 if s[k] == '\\' else 1
        elif ch == o:
            d += 1
        elif ch == c:
            d -= 1
            if d == 0:
                return k
        k += 1
    return n - 1


LOG_CALL = re.compile(r'\b(fprintf|printf|snprintf|sprintf|puts|fputs|OutputDebugStringA|fflush)\s*\(')

def strip_logs(s):
    """Blank printf-family calls (keeps newlines so line numbers survive)."""
    out, pos = [], 0
    for m in LOG_CALL.finditer(s):
        if m.start() < pos:
            continue
        p = s.index('(', m.start())
        e = match_close(s, p)
        out.append(s[pos:m.start()]); out.append(re.sub(r'[^\n]', ' ', s[m.start():e + 1]))
        pos = e + 1
    out.append(s[pos:])
    return ''.join(out)


def line_of(s, idx):
    return s.count('\n', 0, idx) + 1


def find_function(s, name):
    m = re.search(r'^[\w \t\*]*\b' + re.escape(name) + r'\s*\([^;{]*\)\s*\{', s, re.M)
    if not m:
        return None
    b = s.index('{', m.end() - 1)
    e = match_close(s, b, '{', '}')
    return (m.start(), b + 1, e)

# ------------------------------------------------------- condition evaluation

class _Unk:
    used = False
    def _u(self, *a):
        _Unk.used = True
        return self
    __eq__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _u
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _u
    __floordiv__ = __rfloordiv__ = __mod__ = __rmod__ = _u
    __and__ = __rand__ = __or__ = __ror__ = __rshift__ = __rrshift__ = __lshift__ = __rlshift__ = _u
    __xor__ = __rxor__ = __invert__ = __neg__ = _u
    def __bool__(self):
        _Unk.used = True
        return True
    def __call__(self, *a, **k):
        _Unk.used = True
        return self
    def __getattr__(self, k):
        _Unk.used = True
        return self
    def __getitem__(self, k):
        _Unk.used = True
        return self
    __hash__ = object.__hash__

UNK = _Unk()


class Env(dict):
    def __missing__(self, k):
        _Unk.used = True
        return UNK


def c2py(e):
    e = re.sub(r'\(\s*(?:const\s+)?(?:u8|u16|u32|u64|int|unsigned|uint32_t|size_t|long)\s*\**\s*\)', ' ', e)
    e = re.sub(r'\b(0[xX][0-9A-Fa-f]+|\d+)[uUlL]+\b', r'\1', e)
    e = e.replace('&&', ' and ').replace('||', ' or ')
    e = re.sub(r'!(?!=)', ' not ', e)
    e = re.sub(r'(?<!/)/(?!/)', '//', e)
    e = re.sub(r'->', '.', e)
    if '?' in e:                      # a ? b : c  (only simple, non-nested)
        mm = re.match(r'(.*)\?(.*):(.*)', e, re.S)
        if mm:
            e = f'(({mm.group(2)}) if ({mm.group(1)}) else ({mm.group(3)}))'
    return e


def ceval(expr, env):
    """Evaluate a C expression; returns (value, uncertain)."""
    _Unk.used = False
    try:
        v = eval("(" + c2py(expr) + ")", {'__builtins__': {}}, env)
    except Exception:
        return UNK, True
    return v, _Unk.used or v is UNK

# ------------------------------------------------------------- source model

class Src:
    def __init__(self, path):
        self.path = path
        self.raw = open(path, encoding='utf-8', errors='replace').read()
        self.code = strip_comments(self.raw)
        self.nolog = strip_logs(self.code)
        self.md5 = hashlib.md5(open(path, 'rb').read()).hexdigest()
        self.mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec='seconds')


def load_defines(srcs):
    d = {}
    names = {}
    for s in srcs:
        for m in re.finditer(r'^\s*#define\s+(\w+)\s+\(?\s*(0[xX][0-9A-Fa-f]+|\d+)[uU]?\s*\)?\s*(?:/\*.*)?$', s.raw, re.M):
            v = int(m.group(2), 0)
            d.setdefault(m.group(1), v)
            if m.group(1).startswith(('NV4097_', 'NV406E_')) and v < 0x10000 and v % 4 == 0 and not m.group(1).endswith('_DWORDS'):
                names.setdefault(v, m.group(1))
    return d, names

# -------------------------------------------------------------- if scanning

IF_RE = re.compile(r'\bif\s*\(')

def scan_ifs(text, base_off, full):
    """All `if (cond) body` in text that mention `method`."""
    res = []
    for m in IF_RE.finditer(text):
        p = text.index('(', m.start())
        e = match_close(text, p)
        cond = text[p + 1:e]
        if not re.search(r'\bmethod\b', cond):
            continue
        k = e + 1
        while k < len(text) and text[k] in ' \t\r\n':
            k += 1
        if k < len(text) and text[k] == '{':
            be = match_close(text, k, '{', '}')
            body = text[k + 1:be]
        else:
            be = text.find(';', k)
            body = text[k:be + 1]
        res.append(dict(cond=cond, body=body, start=base_off + m.start(), end=base_off + be,
                        line=line_of(full, base_off + m.start())))
    return res


def is_diagnostic(body):
    b = body
    if re.search(r'state->|\breturn\b|vm_write32|s_backend|\bg_\w+\s*=|\bs_\w+\s*=\s*data|process_\w+\s*\(|rsx_vp_\w+\s*\(|\w+_hook\s*\(', b):
        return False
    return True


class Analyzer:
    def __init__(self, cmd: Src, defines):
        self.cmd = cmd
        self.defs = defines
        self.funcs = {}
        for name in re.findall(r'^\s*(?:static\s+)?(?:inline\s+)?(?:int|void|u32)\s+(\w+)\s*\(', cmd.code, re.M):
            f = find_function(cmd.nolog, name)
            if f:
                self.funcs[name] = f
        st, b, e = self.funcs['rsx_process_method']
        self.main_ifs = scan_ifs(cmd.nolog[b:e], b, cmd.nolog)

    # effects of one code fragment for method m ----------------------------
    def effects(self, text, m, env, depth=0):
        eff = dict(fields=set(), actions=set(), captures=set(), calls=set())
        aliases = {}
        for a in re.finditer(r'(\w+)\s*\*\s*(?:const\s+)?(\w+)\s*=\s*&state->(\w+)\[([^\]]*)\]', text):
            aliases[a.group(2)] = a.group(3)
        # pointer table:  u32* const back[] = { &state->a, ... };  *back[idx] = data;
        handled_tbl = set()
        for t in re.finditer(r'\*\s*const\s+(\w+)\[\]\s*=\s*\{([^}]*)\}', text):
            items = re.findall(r'&state->(\w+)', t.group(2))
            u = re.search(r'\*' + t.group(1) + r'\[([^\]]+)\]\s*=', text)
            if u:
                v, unc = ceval(u.group(1), env)
                if not unc and isinstance(v, int) and 0 <= v < len(items):
                    eff['fields'].add(items[v]); handled_tbl.update(items)
        for f in re.finditer(r'state->(\w+)((?:\[[^\]]*\])*)(?:\.(\w+))?', text):
            name, idx, sub = f.group(1), f.group(2), f.group(3)
            if name in handled_tbl or name.endswith('_dirty'):
                continue
            if sub:
                eff['fields'].add(f'{name}[].{sub}')
            elif idx and name in ('viewport_offset', 'viewport_scale'):
                v, unc = ceval(idx[1:-1], env)
                eff['fields'].add(f'{name}[{v}]' if not unc else f'{name}[]')
            else:
                eff['fields'].add(name + ('[]' if idx else ''))
        for al, fld in aliases.items():
            for f in re.finditer(r'\b' + al + r'->(\w+)', text):
                if f.group(1) not in ('dirty',):
                    eff['fields'].add(f'{fld}[].{f.group(1)}')
        for a in re.finditer(r's_backend->(\w+)\s*\(', text):
            eff['actions'].add('backend.' + a.group(1))
        if 'vm_write32' in text:
            eff['actions'].add('guest_write')
        for c in re.finditer(r'\b(g_\w+|s_\w+)\s*=\s*data\b', text):
            eff['captures'].add(c.group(1))
        if re.search(r'\w+_hook\s*\(', text):
            eff['actions'].add('hook_call')
        for c in re.finditer(r'\b(process_\w+|rsx_vp_\w+)\s*\(', text):
            fn = c.group(1)
            eff['calls'].add(fn)
            if fn in self.funcs and depth < 3:
                sub = self.helper(fn, m, depth + 1)
                if sub is None:
                    return None
                for k in eff:
                    eff[k] |= sub[k]
        return eff

    def helper(self, fn, m, depth):
        st, b, e = self.funcs[fn]
        body = self.cmd.nolog[b:e]
        env = Env(self.defs); env['method'] = m; env['data'] = UNK; env['state'] = UNK
        for a in re.finditer(r'^\s*u32\s+(\w+)\s*=\s*([^;]+);', body, re.M):
            v, unc = ceval(a.group(2), env)
            if not unc:
                env[a.group(1)] = v
        for g in re.finditer(r'\bif\s*\(([^;{]*)\)\s*return\s+-1\s*;', body):
            v, unc = ceval(g.group(1), env)
            if not unc and v:
                return None
        sw = re.search(r'\bswitch\s*\((\w+)\)\s*\{', body)
        if sw:
            sv = env.get(sw.group(1), UNK) if sw.group(1) != 'method' else m
            sb = sw.end() - 1
            se = match_close(body, sb, '{', '}')
            sbody = body[sb + 1:se]
            labels = list(re.finditer(r'\b(case\s+([^:]+)|default)\s*:', sbody))
            for i, lb in enumerate(labels):
                seg_end = labels[i + 1].start() if i + 1 < len(labels) else len(sbody)
                if lb.group(1) == 'default':
                    continue
                lv, unc = ceval(lb.group(2), env)
                if not unc and lv == sv:
                    # fall-through: extend until a break/return
                    j = i; seg = ''
                    while True:
                        e2 = labels[j + 1].start() if j + 1 < len(labels) else len(sbody)
                        seg += sbody[labels[j].end():e2]
                        if re.search(r'\b(break|return)\b', seg) or j + 1 >= len(labels):
                            break
                        j += 1
                    alias_txt = body[:sb]
                    return self.effects(alias_txt + '\n' + seg, m, env, depth)
            return None
        ifs = scan_ifs(body, 0, body)
        if ifs:
            for blk in ifs:
                v, unc = ceval(blk['cond'], env)
                if v and not unc:
                    return self.effects(blk['body'], m, env, depth)
            return None
        return self.effects(body, m, env, depth)

    def classify_method(self, m):
        env = Env(self.defs); env['method'] = m; env['data'] = UNK; env['state'] = UNK
        matches = []
        for blk in self.main_ifs:
            v, unc = ceval(blk['cond'], env)
            if not v:
                continue
            diag = is_diagnostic(blk['body'])
            if diag:
                matches.append(dict(line=blk['line'], diagnostic=True, conditional=unc))
                continue
            eff = self.effects(blk['body'], m, env)
            ret = bool(re.search(r'\breturn\b', blk['body']))
            matches.append(dict(line=blk['line'], diagnostic=False, conditional=unc, effects=eff, returns=ret))
            if ret and not unc:
                break
        return matches

# ------------------------------------------------------------- consumption

_REF_CACHE = {}

def consumer_refs(field, consumers):
    k = (field, id(consumers[0]))
    if k not in _REF_CACHE:
        _REF_CACHE[k] = _consumer_refs(field, consumers)
    return _REF_CACHE[k]


def _consumer_refs(field, consumers):
    """Lines in consumer sources (comments + printf stripped) that read `field`."""
    base = field.split('[')[0]
    sub = field.split('.', 1)[1] if '].' in field else None
    hits = []
    if sub:
        if base == 'vertex_textures':
            pats = [r'\bvertex_textures\b[^;\n]*' , ]
            need_struct = r'\bvertex_textures\b'
        else:
            need_struct = None
        for s in consumers:
            if need_struct and not re.search(need_struct, s.nolog):
                continue
            for mm in re.finditer(r'(->|\.)\s*' + re.escape(sub) + r'\b', s.nolog):
                ln = line_of(s.nolog, mm.start())
                hits.append(f'{os.path.basename(s.path)}:{ln}')
    else:
        for s in consumers:
            for mm in re.finditer(r'(->|\.)\s*' + re.escape(base) + r'\b', s.nolog):
                ln = line_of(s.nolog, mm.start())
                hits.append(f'{os.path.basename(s.path)}:{ln}')
    return hits


def draw_engine_refs(srcs, defines):
    """Methods the (disabled) draw engine / dispatcher names in code."""
    refs = {}
    for s in srcs:
        mdefs = {}
        for m in re.finditer(r'^\s*#define\s+(M_\w+)\s+(0x[0-9A-Fa-f]+)', s.raw, re.M):
            mdefs[m.group(1)] = int(m.group(2), 16)
        lines = s.raw.splitlines()
        for name, v in mdefs.items():
            uses = [line_of(s.code, x.start()) for x in re.finditer(r'\b' + name + r'\b', s.code)]
            uses = [u for u in uses if not lines[u - 1].lstrip().startswith('#define')]
            if uses:
                refs.setdefault(v, []).append(f'{os.path.basename(s.path)}:{uses[0]} ({name})')
        for m in re.finditer(r'regs\[\s*(0x[0-9A-Fa-f]+)\s*>>\s*2\s*\]', s.code):
            refs.setdefault(int(m.group(1), 16), []).append(f'{os.path.basename(s.path)}:{line_of(s.code, m.start())}')
    return refs

# --------------------------------------------------------------- overrides

def overrides(backend: Src):
    """Lane-level facts the generic scan cannot see. Each needs its evidence
    line to still exist in the scanned backend; otherwise it is dropped."""
    out = {}
    m1 = re.search(r'vpx\[0\]\s*=\s*vpx\[1\]\s*=\s*vpx\[3\]\s*=\s*1\.0f', backend.code)
    m2 = re.search(r'vpx\[2\]\s*=\s*vs_\[2\];\s*vpx\[6\]\s*=\s*vo_\[2\]', backend.code)
    if m1 and m2:
        ev = f'{os.path.basename(backend.path)}:{line_of(backend.code, m1.start())}-{line_of(backend.code, m2.start())}'
        for base in (0x0A20, 0x0A30):
            for lane, cls in ((0, 'stored-but-unused'), (1, 'stored-but-unused'), (2, 'handled'), (3, 'stored-but-unused')):
                out[base + lane * 4] = dict(cls=cls, label='KNOWN', evidence=ev,
                    note=('shader epilogue uses only the z lane (GL->[0,1] depth remap); '
                          'x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw')
                         if lane != 2 else 'z lane consumed by the shader epilogue (depth remap)')
    if 'rsx_vp_set_branch_bits' not in backend.code:
        out[0x1FF8] = dict(cls='stored-but-unused', label='KNOWN',
            evidence=f'{os.path.basename(backend.path)}: no call to rsx_vp_set_branch_bits; rsx_vp_decompiler.c:142-143 keeps s_vp_branch_bits=0; only rsx_draw_engine.c / rsx_live_draw.c set it',
            note='stored in rsx_state but never handed to the VP decompiler on the legacy path, so BRB/CLB static branches always see bits=0')
    sc = re.search(r'D3D12_RECT\s+scissor\s*=\s*\{\s*0\s*,\s*0\s*,\s*\(LONG\)s_d3d\.width', backend.code)
    if sc and not re.search(r'(->|\.)scissor_[xywh]\b', strip_logs(backend.code)):
        for mth in (0x08C0, 0x08C4):
            out[mth] = dict(cls='stored-but-unused', label='KNOWN',
                evidence=f'{os.path.basename(backend.path)}:{line_of(backend.code, sc.start())}',
                note='backend always sets a full-window scissor; the RSX scissor rect is never applied')
    m3 = re.search(r'static void d3d12_set_viewport\(.*?\{(.*?)\n\}', backend.code, re.S)
    if m3 and 'TODO' in backend.raw[m3.start():m3.end() + 200] and '(void)state' in m3.group(1):
        out['_set_viewport_noop'] = f'{os.path.basename(backend.path)}:{line_of(backend.code, m3.start())}'
    return out

# -------------------------------------------------------------------- main

KNOWN_GAPS = [0x0A68, 0x0A78, 0x0A7C, 0x08CC, 0x08D0, 0x08D4, 0x1D78, 0x1738, 0x173C,
              0x0A20, 0x0A24, 0x0A28, 0x0A2C, 0x0A30, 0x0A34, 0x0A38, 0x0A3C, 0x0394, 0x0398]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='/workspace/faces/src')
    ap.add_argument('--backend', default='/workspace/faces/sh_work.c',
                    help='D3D12 backend source to scan (default: newest working copy)')
    ap.add_argument('--out', default=HERE)
    a = ap.parse_args()

    P = lambda n: os.path.join(a.src, n)
    cmd = Src(P('rsx_commands.c'))
    hdr = Src(P('rsx_commands.h'))
    backend = Src(a.backend)
    vfetch = Src(P('rsx_vertex_fetch.c'))
    tlay = Src(P('rsx_texture_layout.c'))
    de = Src(P('rsx_draw_engine.c'))
    dsp = Src(P('rsx_dispatch.c'))
    extra_hdrs = [Src(P(h)) for h in ('rsx_draw_engine.h', 'rsx_dispatch.h') if os.path.exists(P(h))]
    defines, hdr_names = load_defines([hdr, cmd] + extra_hdrs)

    an = Analyzer(cmd, defines)
    consumers = [backend, vfetch, tlay]
    # reads done by rsx_commands.c itself on the way to a backend callback (clear values, primitive type)
    cmd_action_reads = set()
    for blk in an.main_ifs:
        if 's_backend->' in blk['body'] and 'set_render_target' not in blk['body']:
            cmd_action_reads |= set(re.findall(r'state->(\w+)', blk['body']))
    # fields rsx_commands.c itself reads to build other state (e.g. the constant
    # load slot, the microcode write cursor): consumed indirectly.
    internal_reads = {}
    init = an.funcs.get('rsx_state_init')
    for r in re.finditer(r'(?<!&)state->(\w+)', cmd.nolog):
        if init and init[1] <= r.start() <= init[2]:
            continue
        k = r.end()
        while k < len(cmd.nolog) and cmd.nolog[k] == '[':
            k = match_close(cmd.nolog, k, '[', ']') + 1
        if re.match(r'\s*(?:\.\w+)?\s*(?:[-+|&^]?=(?!=))', cmd.nolog[k:k + 40]):
            continue   # a write, not a read
        internal_reads.setdefault(r.group(1), f'rsx_commands.c:{line_of(cmd.nolog, r.start())} (internal read)')
    ovr = overrides(backend)
    gcm = Src(P('cellGcmSys.c'))
    upstream = {}
    f3 = find_function(gcm.code, 'gcm_3d_method')
    if f3:
        for r in re.finditer(r'\bm\s*==\s*(0x[0-9A-Fa-f]+)u?', gcm.code[f3[1]:f3[2]]):
            upstream.setdefault(int(r.group(1), 16), f'cellGcmSys.c:{line_of(gcm.code, f3[1] + r.start())} (gcm_3d_method)')
    for r in re.finditer(r'subch\s*==\s*0\s*&&\s*\(([^)]*)\)', gcm.code):
        for v in re.findall(r'method\s*==\s*(0x[0-9A-Fa-f]+)', r.group(1)):
            upstream.setdefault(int(v, 16), f'cellGcmSys.c:{line_of(gcm.code, r.start())} (FIFO walker, before rsx_process_method)')
    de_refs = draw_engine_refs([de, dsp], defines)

    methods = {}
    universe = list(range(0, 0x2000, 4)) + [0xE920, 0xE924, 0xE944]
    for m in universe:
        hname = hdr_names.get(m)
        pname, conf = nv4097_names.public_name(m)
        name = hname or pname
        name_src = 'rsx_commands.h' if hname else ('public-list' + ('' if conf else ' (VERIFY)') if pname else None)
        matches = an.classify_method(m)
        real = [x for x in matches if not x['diagnostic']]
        diag_lines = [x['line'] for x in matches if x['diagnostic']]
        fields, actions, captures, calls = set(), set(), set(), set()
        handler_lines = []
        conditional = False
        unh = False
        for x in real:
            if x['effects'] is None:
                unh = True
                continue
            handler_lines.append(x['line'])
            conditional |= x['conditional']
            fields |= x['effects']['fields']; actions |= x['effects']['actions']
            captures |= x['effects']['captures']; calls |= x['effects']['calls']
        fields = {f for f in fields if not f.endswith('.dirty')}
        fields = {f for f in fields if not (f.endswith('[]') and any(g.startswith(f + '.') for g in fields))}
        has_handler = bool(handler_lines)
        consumed, unconsumed, evidence = [], [], {}
        for f in sorted(fields):
            refs = consumer_refs(f, consumers)
            if f.split('[')[0] in cmd_action_reads:
                refs = ['rsx_commands.c(action)'] + refs
            elif not refs and '].' not in f and f.split('[')[0] in internal_reads:
                refs = [internal_reads[f.split('[')[0]]]
            evidence[f] = refs[:4]
            (consumed if refs else unconsumed).append(f)
        label = 'ASSUMED'
        note = ''
        if not has_handler and m in upstream:
            cls = 'handled'
            note = 'handled in the FIFO walker, not rsx_process_method: ' + upstream[m]
            evidence['upstream'] = [upstream[m]]
        elif not has_handler:
            cls = 'unhandled'
        elif actions or (captures and not fields):
            cls = 'handled'
            note = 'acts directly: ' + ', '.join(sorted(actions | {'capture:' + c for c in captures}))
        elif not fields:
            cls = 'handled'
            note = 'accepted as a no-op (returns 0, stores nothing)'
        elif consumed:
            cls = 'handled'
            if unconsumed:
                note = 'partial: not read by the D3D12 path: ' + ', '.join(unconsumed)
        else:
            cls = 'stored-but-unused'
        if m in ovr:
            o = ovr[m]; cls = o['cls']; label = o['label']; note = o['note']; evidence['override'] = [o['evidence']]
        if conditional:
            note = (note + '; ' if note else '') + 'handler condition also depends on runtime state'
        if not name and not has_handler and m not in de_refs and m not in upstream:
            continue
        methods[f'0x{m:04X}'] = dict(
            method=m, name=name, name_source=name_src, cls=cls, label=label,
            handler_lines=[f'rsx_commands.c:{l}' for l in handler_lines],
            diagnostic_only_lines=[f'rsx_commands.c:{l}' for l in diag_lines],
            fields=sorted(fields), consumed=consumed, unconsumed=unconsumed, evidence=evidence,
            draw_engine=de_refs.get(m, []), note=note)

    meta = dict(
        generated=datetime.datetime.now().isoformat(timespec='seconds'),
        tool='gen_coverage.py v1 (static scan; every class is ASSUMED unless label says KNOWN)',
        sources={os.path.basename(s.path) + ('' if s is not backend else ' (backend)'): dict(path=s.path, md5=s.md5, mtime=s.mtime)
                 for s in [cmd, hdr, backend, vfetch, tlay, de, dsp, gcm]},
        legacy_path='FIFO walker (cellGcmSys.c gcm_3d_method) -> rsx_process_method -> rsx_state -> D3D12 vtable; draw_engine_enabled=0',
        set_viewport_noop=ovr.get('_set_viewport_noop'),
        counts={c: sum(1 for v in methods.values() if v['cls'] == c) for c in ('handled', 'stored-but-unused', 'unhandled')},
    )
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'coverage.json'), 'w') as f:
        json.dump(dict(meta=meta, methods=methods), f, indent=1)
    write_md(os.path.join(a.out, 'coverage.md'), meta, methods)
    print(json.dumps(meta['counts']))
    for m in KNOWN_GAPS:
        e = methods.get(f'0x{m:04X}')
        print(f'0x{m:04X} {e["name"] if e else "?":40s} {e["cls"] if e else "?":18s} {e["label"] if e else ""} {e["note"][:70] if e else ""}')


def compress(entries):
    """Group consecutive same-family entries (texture units, constants...)."""
    groups = []
    for e in entries:
        fam = re.sub(r'\[\d+\]', '[n]', e['name'] or f"0x{e['method']:04X}")
        fam = re.sub(r'\.(x|y|z|w|pad|xy|zw)$', '.*', fam)
        fam = re.sub(r'^(NV4097_SET_(?:VERTEX_)?TEXTURE)_(OFFSET|FORMAT|ADDRESS|CONTROL0|CONTROL1|CONTROL3|FILTER|IMAGE_RECT|BORDER_COLOR)', r'\1_*', fam)
        fam = fam.replace('[n]', '') + '[n]' if '[n]' in fam or fam.endswith('_*') else fam
        key = (fam, e['cls'], e['note'])
        if groups and groups[-1]['key'] == key and e['method'] == groups[-1]['items'][-1]['method'] + 4:
            groups[-1]['items'].append(e)
        else:
            groups.append(dict(key=key, items=[e]))
    return groups


def write_md(path, meta, methods):
    L = []
    L.append('# RSX method coverage, legacy D3D12 path (static)\n')
    L.append(f"Generated {meta['generated']} by gen_coverage.py. Classes are mechanical (ASSUMED) unless marked KNOWN; "
             'evidence lines are in coverage.json so each one can be VERIFIED.\n')
    L.append('Sources scanned:\n')
    for k, v in meta['sources'].items():
        L.append(f"- `{v['path']}` ({k}), mtime {v['mtime']}, md5 {v['md5'][:8]}")
    L.append(f"\nPath: {meta['legacy_path']}.")
    if meta.get('set_viewport_noop'):
        L.append(f"\n`d3d12_set_viewport` is a TODO no-op at {meta['set_viewport_noop']} (KNOWN).")
    c = meta['counts']
    L.append(f"\nCounts over named or handled offsets: handled {c['handled']}, stored-but-unused {c['stored-but-unused']}, unhandled {c['unhandled']}.\n")
    L.append('## Spot check: known gaps\n')
    L.append('| method | name | class | label | note |\n|---|---|---|---|---|')
    for m in KNOWN_GAPS:
        e = methods.get(f'0x{m:04X}')
        if e:
            L.append(f"| 0x{m:04X} | {e['name']} | **{e['cls']}** | {e['label']} | {e['note']} |")
    for cls in ('unhandled', 'stored-but-unused', 'handled'):
        L.append(f'\n## {cls}\n')
        L.append('| method(s) | name | fields | draw engine knows it | note |\n|---|---|---|---|---|')
        ents = sorted((e for e in methods.values() if e['cls'] == cls), key=lambda e: e['method'])
        for g in compress(ents):
            it = g['items']
            rng = f"0x{it[0]['method']:04X}" + (f"..0x{it[-1]['method']:04X} ({len(it)})" if len(it) > 1 else '')
            nm = g['key'][0] if len(it) > 1 else (it[0]['name'] or '')
            if it[0]['name_source'] and 'VERIFY' in it[0]['name_source']:
                nm += ' (name VERIFY)'
            flds = ', '.join(sorted({f for e in it for f in e['fields']}))[:80]
            dek = 'yes' if any(e['draw_engine'] for e in it) else ''
            L.append(f"| {rng} | {nm} | {flds} | {dek} | {g['key'][2]} |")
    open(path, 'w').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()

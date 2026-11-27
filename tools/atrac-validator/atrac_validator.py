#!/usr/bin/env python3
"""
atrac_validator.py - ATRAC3plus stream validator for the Strikeforce (BLUS30471)
ps3recomp port. Python 3 standard library only. Own code; no GPL/RPCS3 code.

Sub-commands
  header   FILE                       print the container header (RIFF .at3 or OMA/EA3)
  hashfile FILE [--out TSV]           header + one line per frame: k, offset, fnv1a32, byte0
                                      (read-only; run on Saud's PC so raw bytes never leave it)
  hostcmp  --orig FILE --host BIN     compare a SF_ATRAC_DUMP host copy (clip*_host.bin) with the
           [--out CSV]                original track, frame by frame, and find where every bad frame's
                                      bytes really came from (read-only; numbers only in the output)
  analyze  --log LOG [--log LOG ...]  build report.md + CSVs from [cellAtrac] / [atrac-diag] /
           [--hashes TSV] [--file F]  [sf-atrac] lines, optional frame hashes, host-compare CSV and
           [--hostcmp CSV] [--pcm F]  PCM; writes into --out DIR
  selftest                            synthetic streams for every pattern; exits 1 on any failure

Labels used in the output: KNOWN (from the bytes / log in hand), ASSUMED, VERIFY.
"""
import argparse, collections, csv, io, math, os, random, re, struct, sys

AT3P_SAMPLES = 2048
AT3P_DELAY = 0x170
AT3P_GUID = bytes([0xBF, 0xAA, 0x23, 0xE9, 0x58, 0xCB, 0x71, 0x44,
                   0xA1, 0x19, 0xFF, 0xFA, 0x01, 0xE4, 0xCE, 0x62])
ERR_ADD_TOO_BIG = 0x80610342
ERR_NODATA = 0x80610332

# Expected channel-unit layout per channel count (unit tags: 0 mono, 1 stereo,
# 2 extension, 3 terminator). Paraphrased from the public decoder structure;
# the first tag sits in bits 6-5 of byte 0, bit 7 is the start bit (must be 0).
UNIT_LAYOUT = {1: [0], 2: [1], 3: [1, 0], 4: [1, 0, 0], 6: [1, 0, 1, 0],
               7: [1, 0, 1, 0, 0], 8: [1, 0, 1, 0, 1]}


def fnv1a32(b):
    h = 0x811C9DC5
    for x in b:
        h = ((h ^ x) * 0x01000193) & 0xFFFFFFFF
    return h


def frame_start_ok(byte0, ch):
    """byte0 of an ATRAC3plus frame: start bit 0, first unit tag == layout[0]."""
    if byte0 & 0x80:
        return False
    lay = UNIT_LAYOUT.get(ch)
    if not lay:
        return True
    return ((byte0 >> 5) & 3) == lay[0]


# ---------------------------------------------------------------- headers
def le16(b, o): return struct.unpack_from('<H', b, o)[0]
def le32(b, o): return struct.unpack_from('<I', b, o)[0]


def parse_header(buf):
    """Returns a dict. Raises ValueError if the container is unknown."""
    if len(buf) >= 12 and buf[:4] == b'RIFF' and buf[8:12] == b'WAVE':
        h = {'container': 'RIFF', 'chunks': []}
        o = 12
        while o + 8 <= len(buf):
            cid = buf[o:o + 4].decode('latin1')
            cs = le32(buf, o + 4)
            p = o + 8
            h['chunks'].append((cid, o, cs))
            if cid == 'fmt ':
                h['format_tag'] = le16(buf, p)
                h['channels'] = le16(buf, p + 2)
                h['rate'] = le32(buf, p + 4)
                h['avg_bytes'] = le32(buf, p + 8)
                h['block_align'] = le16(buf, p + 12)
                if h['format_tag'] == 0xFFFE and cs >= 40:
                    h['channel_mask'] = le32(buf, p + 20)
                    guid = bytes(buf[p + 24:p + 40])
                    h['codec'] = 'ATRAC3plus' if guid == AT3P_GUID else 'ext:' + guid.hex()
                elif h['format_tag'] == 0x0270:
                    h['codec'] = 'ATRAC3'
                else:
                    h['codec'] = 'tag:0x%04X' % h['format_tag']
            elif cid == 'fact':
                h['fact'] = [le32(buf, p + 4 * i) for i in range(min(cs // 4, 3)) if p + 4 * i + 4 <= len(buf)]
            elif cid == 'smpl' and cs >= 36:
                n = le32(buf, p + 28)
                h['smpl_loops'] = n
                if n and cs >= 60:
                    h['smpl_start'] = le32(buf, p + 36 + 8)
                    h['smpl_end'] = le32(buf, p + 36 + 12)
            elif cid == 'data':
                h['data_start'] = p
                h['data_bytes'] = cs
                break
            o = p + cs + (cs & 1 if cid not in ('fmt ', 'fact', 'smpl', 'data') else 0)
        if 'data_start' not in h or not h.get('block_align'):
            raise ValueError('RIFF without fmt/data')
        h['frame_bytes'] = h['block_align']
        h['frames'] = h['data_bytes'] // h['frame_bytes']
        h['tail_bytes'] = h['data_bytes'] % h['frame_bytes']
        return h
    # OMA: optional ID3v2-style 'ea3'/'ID3' tag then a 96-byte 'EA3' header.
    pos = 0
    if len(buf) >= 10 and buf[:3] in (b'ea3', b'ID3'):
        tl = ((buf[6] & 0x7F) << 21) | ((buf[7] & 0x7F) << 14) | ((buf[8] & 0x7F) << 7) | (buf[9] & 0x7F)
        pos = 10 + tl + (10 if buf[5] & 0x10 else 0)
    if len(buf) >= pos + 36 and buf[pos:pos + 3] == b'EA3':
        hs = (buf[pos + 4] << 8) | buf[pos + 5]
        codec = buf[pos + 32]
        params = (buf[pos + 33] << 16) | (buf[pos + 34] << 8) | buf[pos + 35]
        raw = params & 0x3FF
        h = {'container': 'OMA', 'ea3_pos': pos, 'ea3_size': hs, 'codec_id': codec,
             'codec_params': params, 'ch_code': (params >> 10) & 7,
             'rate_code': (params >> 13) & 7, 'joint_stereo': (params >> 17) & 1,
             'encryption_id': (buf[pos + 6] << 8) | buf[pos + 7]}
        h['codec'] = {0: 'ATRAC3', 1: 'ATRAC3plus'}.get(codec, 'id%d' % codec)
        h['frame_bytes'] = (raw + 1) * 8 if codec == 1 else raw * 8
        h['block_align'] = h['frame_bytes']
        h['data_start'] = pos + hs
        h['data_bytes'] = len(buf) - h['data_start']
        h['frames'] = h['data_bytes'] // h['frame_bytes'] if h['frame_bytes'] else 0
        h['tail_bytes'] = h['data_bytes'] % h['frame_bytes'] if h['frame_bytes'] else 0
        h['channels'] = None  # ch_code mapping: VERIFY
        return h
    raise ValueError('unknown container (not RIFF/WAVE, not OMA/EA3)')


def frame_table(buf, hdr):
    fb, ds = hdr['frame_bytes'], hdr['data_start']
    rows = []
    for k in range(hdr['frames']):
        off = ds + k * fb
        fr = buf[off:off + fb]
        rows.append((k, off, fnv1a32(fr), fr[0] if fr else -1))
    return rows


def log_ranges(logpath):
    """(off,len) of every logged add / recheck / decode, for hashfile --ranges."""
    rs = set()
    for e in parse_log(logpath, None):
        if e['fn'] in ('AddStreamData', 'AddRecheck') and 'off' in e and (e.get('add') or e.get('len')):
            rs.add((int(e['off']), int(e.get('add') or e.get('len'))))
    return sorted(rs)


def write_hashfile(path, buf, out, ranges=()):
    hdr = parse_header(buf)
    rows = frame_table(buf, hdr)
    ch = hdr.get('channels')
    bad0 = sum(1 for r in rows if ch and not frame_start_ok(r[3], ch))
    out.write('# atrac_validator hashfile v1\n')
    out.write('# source_bytes=%d source_fnv=%08x\n' % (len(buf), fnv1a32(buf[:hdr['data_start']])))
    for k in ('container', 'codec', 'channels', 'rate', 'block_align', 'frame_bytes', 'data_start',
              'data_bytes', 'frames', 'tail_bytes', 'fact', 'smpl_loops', 'smpl_start', 'smpl_end',
              'codec_params', 'ch_code'):
        if k in hdr:
            out.write('# %s=%s\n' % (k, hdr[k] if not isinstance(hdr[k], list) else ','.join(map(str, hdr[k]))))
    out.write('# chunks=%s\n' % ';'.join('%s@%d+%d' % c for c in hdr.get('chunks', [])))
    out.write('# frames_with_bad_byte0=%d zero_frame_fnv=%08x\n' % (bad0, fnv1a32(bytes(hdr['frame_bytes']))))
    out.write('k\toffset\tfnv1a32\tbyte0\n')
    for k, off, h, b0 in rows:
        out.write('%d\t%d\t%08x\t%02x\n' % (k, off, h, b0 & 0xFF))
    for off, ln in ranges:
        if off + ln <= len(buf):
            out.write('R\t%d\t%d\t%08x\n' % (off, ln, fnv1a32(buf[off:off + ln])))
    return hdr, rows


def read_hashfile(path):
    hdr, rows = {}, []
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('# ') and '=' in line:
                k, v = line[2:].split('=', 1)
                hdr[k.strip()] = v.strip()
            elif line and line[0].isdigit():
                p = line.split('\t')
                rows.append((int(p[0]), int(p[1]), int(p[2], 16), int(p[3], 16)))
            elif line.startswith('R\t'):
                p = line.split('\t')
                hdr.setdefault('ranges', {})[(int(p[1]), int(p[2]))] = int(p[3], 16)
    for k in ('channels', 'block_align', 'frame_bytes', 'data_start', 'data_bytes', 'frames', 'tail_bytes'):
        if k in hdr and hdr[k] not in ('None', ''):
            hdr[k] = int(hdr[k])
    return hdr, rows


# ---------------------------------------------------------------- host-copy compare (PC side)
def hostcmp(orig, host, probe=64):
    """Frame-by-frame compare of the decoder's linear host copy with the original.
    status: ok | zeros | moved (bytes found elsewhere in the file) | unknown."""
    hdr = parse_header(orig)
    fb, ds = hdr['frame_bytes'], hdr['data_start']
    rows = []
    for k in range(hdr['frames']):
        off = ds + k * fb
        a, b = orig[off:off + fb], host[off:off + fb]
        if len(b) < fb:
            rows.append((k, off, 'short', '', '', b[0] if b else -1)); continue
        if a == b:
            rows.append((k, off, 'ok', off, 0, b[0])); continue
        if not any(b):
            rows.append((k, off, 'zeros', '', '', 0)); continue
        # first differing byte, then locate the host bytes from there in the original
        d = next(i for i in range(fb) if a[i] != b[i])
        src = ''
        p = b[d:d + probe] if fb - d >= 16 else b[max(0, fb - probe):fb]
        pb = d if fb - d >= 16 else max(0, fb - probe)
        if any(p):
            i = orig.find(p)
            if i >= 0:
                src = i - pb
        rows.append((k, off, 'moved' if src != '' else 'unknown', src,
                     (src - off) if src != '' else '', b[0]))
    return hdr, rows


# ---------------------------------------------------------------- log parsing
KV = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|\[[^\]]*\)|[^\s]+)')
ALIAS = {'handle': 'h', 'function': 'fn', 'file_fed': 'fed', 'valid_off': 'voff', 'valid_bytes': 'vbytes',
         'write_given': 'wea_given', 'given': 'wea_given', 'wptr': 'wea_given', 'write_used': 'wea_used',
         'used': 'wea_used', 'add_bytes': 'add', 'hash': 'fnv', 'readpos': 'readpos', 'read_pos': 'readpos',
         'frame': 'k', 'offset': 'off', 'length': 'len', 'block_align': 'ba', 'frame_bytes': 'ba',
         'data_off': 'doff', 'data_start': 'doff', 'channels': 'ch', 'writebyte': 'wb', 'bufbytes': 'bufsz',
         'buf_size': 'bufsz', 'read': 'read', 'total': 'total', 'sample': 'sample'}
LEG_STREAM = re.compile(r'\[cellAtrac\] SetData: streaming (\d+) of (\d+) bytes, ring=(\d+)')
LEG_SET = re.compile(r'\[cellAtrac\] SetData handle=(0x[0-9A-Fa-f]+) ch=(\d+) frames=(\d+) first=(-?\d+) '
                     r'end=(-?\d+) loop=\[(-?\d+),(-?\d+)\) all_on_mem=(\d)')
LEG_ERR = re.compile(r'\[cellAtrac\] Atrac3/3\+: (.*)$')
DIAG = re.compile(r'\[atrac-diag\](?: t=([\d.]+))?(?: mix=[-\d.]+)? (?:CLIP-END )?#(-?\d+) (\w+)(.*)$')
SFA = re.compile(r'\[sf-atrac\](.*)$')
TICK_DEFAULT = r'^\[WAIT\] event_queue_receive\(q=1 .*tid=10 '


def num(v):
    v = v.strip('"')
    try:
        return int(v, 16) if v.lower().startswith('0x') else int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def err_kind(msg):
    m = re.search(r'ch_block (\d+) >= num_channel_blocks (\d+)', msg)
    if m:
        return 'unit_mismatch_b%s' % m.group(1)
    if 'Invalid start bit' in msg: return 'start_bit'
    if 'Channel unit extension' in msg: return 'extension'
    return re.sub(r'[^a-z]+', '_', re.sub(r'[:!].*', '', msg.lower())).strip('_')[:40]


def parse_log(path, tick_re=TICK_DEFAULT):
    ev = []
    tick = 0
    tre = re.compile(tick_re) if tick_re else None
    pend = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip('\n')
            line = re.sub(r'^\d+:', '', line)          # rg -n style prefixes
            if tre and tre.search(line):
                tick += 1
                continue
            if '[cellAtrac]' in line:
                m = LEG_STREAM.search(line)
                if m:
                    pend = dict(read=int(m.group(1)), total=int(m.group(2)), bufsz=int(m.group(3)), pline=n)
                    continue
                m = LEG_SET.search(line)
                if m:
                    e = dict(fn='SetData', src='legacy', line=n, tick=tick, h=int(m.group(1), 16),
                             ch=int(m.group(2)), frames=int(m.group(3)), first=int(m.group(4)),
                             end=int(m.group(5)), loop_start=int(m.group(6)), loop_end=int(m.group(7)),
                             aom=int(m.group(8)))
                    if pend and n - pend['pline'] <= 2:
                        e.update(read=pend['read'], total=pend['total'], bufsz=pend['bufsz'])
                    pend = None
                    ev.append(e)
                    continue
                m = LEG_ERR.search(line)
                if m:
                    ev.append(dict(fn='DecodeError', src='legacy', line=n, tick=tick, h=None,
                                   msg=m.group(1), kind=err_kind(m.group(1))))
                    continue
            m = DIAG.search(line)
            if m:
                e = dict(fn=m.group(3), src='diag', line=n, tick=tick, clip=int(m.group(2)))
                if m.group(1): e['t'] = float(m.group(1))
                for k, v in KV.findall(m.group(4)):
                    e[ALIAS.get(k, k)] = num(v)
                if e['fn'] == 'CreateDecoder': e['fn'] = 'CreateDecoder'
                e['fn'] = e['fn'].replace('cellAtrac', '')
                ev.append(e)
                continue
            m = SFA.search(line)
            if m:
                e = dict(src='sf', line=n, tick=tick)
                for k, v in KV.findall(m.group(1)):
                    e[ALIAS.get(k, k)] = num(v)
                e['fn'] = str(e.get('fn', '?')).replace('cellAtrac', '')
                if e['fn'] == 'DecodeError' and 'msg' in e:
                    e['kind'] = err_kind(str(e['msg']))
                ev.append(e)
    return ev


# ---------------------------------------------------------------- analyses
def classify_deltas(pairs, fb, other_fbs=()):
    """pairs: [(k, delta)] for decoder feeds, delta = actual_offset - (data_start + k*fb).
    Returns (pattern, detail)."""
    pairs = sorted(pairs)
    if not pairs:
        return 'none', 'no feeds'
    bad = [(k, d) for k, d in pairs if d != 0]
    if not bad:
        return 'ok', 'all %d feeds on the frame grid' % len(pairs)
    first_bad = bad[0]
    ds = set(d for _, d in pairs)
    if len(ds) == 1:
        return 'constant', 'every feed off by %+d bytes -> wrong data_start (by %+d)' % (first_bad[1], first_bad[1])
    # linear: delta = a + k*s for all
    if len(pairs) >= 3:
        (k0, d0), (k1, d1) = pairs[0], pairs[-1]
        if k1 != k0 and (d1 - d0) % (k1 - k0) == 0:
            s = (d1 - d0) // (k1 - k0)
            a = d0 - s * k0
            if s != 0 and all(d == a + s * k for k, d in pairs):
                used = fb + s
                why = ''
                for ch_a in (1, 2, 3, 4, 6, 8):
                    for ch_b in (1, 2, 3, 4, 6, 8):
                        if ch_a != ch_b and abs(used * ch_b - fb * ch_a) < 8 * ch_b:
                            why = ' = frame_bytes*%d/%d (channel-count/stride mixup %dch vs %dch)' % (ch_a, ch_b, ch_a, ch_b)
                if used in other_fbs:
                    why = ' = another stream\'s frame size %d (stride mixup)' % used
                pat = 'stride_mixup' if why else 'growing'
                return pat, ('delta grows %+d bytes per frame (offset %+d) -> stride used %d instead of %d%s'
                             % (s, a, used, fb, why))
    # step: zero before k0, constant after
    ks = [k for k, d in pairs if d != 0]
    k0 = ks[0]
    after = [d for k, d in pairs if k >= k0]
    if all(d == 0 for k, d in pairs if k < k0) and len(set(after)) == 1:
        c = after[0]
        return 'step', ('grid OK up to frame %d, then every feed off by %+d bytes (= %+.3f frames) -> a dropped/'
                        'duplicated add or a seek that kept the old base' % (k0, c, c / fb))
    return 'irregular', 'first bad feed frame %d delta %+d; %d distinct deltas' % (first_bad[0], first_bad[1], len(ds))


def header_inference(setdatas):
    """Legacy SetData lines give total=data_off+data_bytes and frames=data_bytes//ba.
    Find block_align values consistent with every track and a small data_off."""
    rows = []
    tr = {}
    for e in setdatas:
        if e.get('total') and e.get('frames'):
            tr[(e['h'], e['total'], e['frames'], e['loop_start'] >= 0, e['ch'])] = e
    if not tr:
        return rows, {}
    cand = collections.Counter()
    for (h, total, frames, loop, ch), e in tr.items():
        ok = set()
        for ba in range(64, 8192):
            hi = total - frames * ba              # data_off if data_bytes is an exact multiple
            lo = total - (frames + 1) * ba + 1    # smallest data_off allowed by floor()
            if hi >= 12 + 8 and lo <= 512:
                ok.add(ba)
        for ba in ok:
            cand[ba] += 1
        rows.append(dict(handle='0x%08X' % h, ch=ch, total=total, frames=frames, loop=int(loop),
                         first=e['first'], end=e['end'], line=e['line']))
    n = len(tr)
    common = sorted(ba for ba, c in cand.items() if c == n)
    # among the common values, the one giving identical exact-multiple data_off per loop class
    best = {}
    for ba in common:
        offs = collections.defaultdict(set)
        for (h, total, frames, loop, ch) in tr:
            offs[loop].add(total - frames * ba)
        if all(len(v) == 1 for v in offs.values()):
            best[ba] = {('loop' if k else 'noloop'): list(v)[0] for k, v in offs.items()}
    for r in rows:
        for ba in best:
            r['data_off_if_exact@%d' % ba] = r['total'] - r['frames'] * ba
    return rows, {'tracks': n, 'block_align_common': common[:20] if len(common) <= 20 else
                  '%d values (%d..%d)' % (len(common), common[0], common[-1]), 'consistent': best}


def error_epochs(ev, gap_ticks=160, gap_lines=4000, chunk=None):
    """Per 6ch (multichannel) SetData epoch: decoder-error counts, signature mix, episodes."""
    out = []
    cur = None
    for e in ev:
        if e['fn'] == 'SetData' and e.get('ch', 0) > 2:
            cur = dict(set=e, errs=[])
            out.append(cur)
        elif e['fn'] == 'DecodeError' and cur is not None:
            cur['errs'].append(e)
    res = []
    for ep in out:
        s = ep['set']
        ba = s.get('ba') or (1712 if s.get('ch') == 6 else None)
        eps = []
        for e in ep['errs']:
            if eps and ((e['tick'] - eps[-1][-1]['tick'] <= gap_ticks) if e['tick'] or eps[-1][-1]['tick']
                        else (e['line'] - eps[-1][-1]['line'] <= gap_lines)):
                eps[-1].append(e)
            else:
                eps.append([e])
        rd = s.get('read') or chunk
        chunk_frames = None
        if rd and ba:
            chunk_frames = (rd // ba, rd // ba + 1, rd // ba + 2)
        def chunk_mult(n):
            # n bad frames == the frames touched by m whole chunks of rd bytes (m*rd/ba .. +2)
            if not (rd and ba):
                return 0
            for m in range(1, 17):
                if m * rd // ba <= n <= m * rd // ba + 2:
                    return m
            return 0
        episodes = []
        for g in eps:
            kinds = collections.Counter(x['kind'] for x in g)
            n = len(g)
            z = kinds.get('unit_mismatch_b0', 0) / n
            sb = kinds.get('start_bit', 0) / n
            sig = 'zeros-like' if n >= 3 and z >= 0.9 else ('random-like' if n >= 8 and 0.3 <= sb <= 0.7 else 'mixed/small')
            episodes.append(dict(first_line=g[0]['line'], last_line=g[-1]['line'], n=n,
                                 ticks=g[-1]['tick'] - g[0]['tick'], sig=sig,
                                 chunk_sized=bool(chunk_frames and n in chunk_frames), chunks=chunk_mult(n) if n >= 3 else 0,
                                 kinds=dict(kinds.most_common())))
        res.append(dict(line=s['line'], h=s['h'], ch=s.get('ch'), frames=s.get('frames'), total=s.get('total'),
                        read=s.get('read'), errors=len(ep['errs']),
                        kinds=dict(collections.Counter(x['kind'] for x in ep['errs']).most_common()),
                        episodes=episodes, chunk_frames=chunk_frames))
    return res


class Stream:
    def __init__(self, h):
        self.h = h; self.ba = None; self.doff = None; self.first = None; self.ch = None
        self.buf = None; self.bufsz = None; self.fed = 0; self.woff = 0; self.vbytes = 0
        self.intervals = []          # fed file-byte intervals [a,b)
        self.given = None            # last GetStreamDataInfo (wea, readpos, line)
        self.seeks = []              # dicts
        self.next_k = None

    def add_interval(self, a, b):
        if b > a:
            self.intervals.append((a, b))

    def is_fed(self, a, b):
        iv = sorted(self.intervals)
        cur = a
        for x, y in iv:
            if x <= cur < y:
                cur = y
                if cur >= b:
                    return True
        return cur >= b


def stream_checks(ev, file_frames=None, file_hdr=None):
    """Per-call model (needs [atrac-diag] or [sf-atrac] lines)."""
    findings, feeds = [], []
    S = {}
    by_fnv = collections.defaultdict(list)
    zero_fnv = None
    if file_frames:
        for k, off, h, b0 in file_frames:
            by_fnv[h].append(k)
    fbs = set()
    for e in ev:
        h = e.get('h')
        fn = e['fn']
        if h is None or fn == 'DecodeError' and e['src'] == 'legacy':
            continue
        s = S.get(h)
        if fn == 'SetData':
            s = S[h] = Stream(h)
            s.ch = e.get('ch'); s.buf = e.get('buf'); s.bufsz = e.get('bufsz') or e.get('read')
            s.ba = e.get('ba'); s.doff = e.get('doff'); s.first = e.get('first')
            if file_hdr and s.ch and s.ch > 2:
                s.ba = s.ba or file_hdr.get('frame_bytes'); s.doff = s.doff if s.doff is not None else file_hdr.get('data_start')
            if s.ba: fbs.add(s.ba)
            rd = e.get('read') or 0
            s.fed = rd; s.vbytes = rd; s.woff = rd % s.bufsz if s.bufsz else 0
            s.add_interval(0, rd)
            if file_hdr and s.ba and file_hdr.get('frame_bytes') and s.ba != file_hdr['frame_bytes']:
                findings.append(dict(suspect='header', verdict='confirmed', line=e['line'],
                                     evidence='logged frame size %d != file block_align %d' % (s.ba, file_hdr['frame_bytes'])))
            if file_hdr and s.doff is not None and file_hdr.get('data_start') is not None and s.doff != file_hdr['data_start']:
                findings.append(dict(suspect='header', verdict='confirmed', line=e['line'],
                                     evidence='logged data_off %d != file data_start %d' % (s.doff, file_hdr['data_start'])))
            continue
        if s is None:
            continue
        if fn == 'GetStreamDataInfo':
            s.given = (e.get('wea_given'), e.get('readpos'), e['line'], e.get('writable'))
            if e.get('readpos') is not None and e.get('rc', 0) == 0 and e['readpos'] != s.fed:
                findings.append(dict(suspect='write_pointer', verdict='confirmed', line=e['line'],
                                     evidence='readpos given %d != running sum of adds %d' % (e['readpos'], s.fed)))
            if s.buf is not None and e.get('wea_given') is not None and e.get('rc', 0) == 0 and s.bufsz:
                exp = s.buf + s.woff
                if e['wea_given'] != exp:
                    findings.append(dict(suspect='write_pointer', verdict='confirmed', line=e['line'],
                                         evidence='write pointer given 0x%08X != ring start + running sum 0x%08X'
                                         % (e['wea_given'], exp)))
        elif fn == 'AddStreamData':
            n = e.get('add', e.get('len', 0)) or 0
            rc = e.get('rc', 0) or 0
            off = e.get('off', s.fed)
            used = e.get('wea_used')
            gv = s.given[0] if s.given else None
            row = dict(kind='add', line=e['line'], h='0x%08X' % h, off=off, len=n, rc='0x%08X' % rc,
                       wea_given=('0x%08X' % gv) if gv is not None else '', wea_used=('0x%08X' % used) if used is not None else '',
                       grid='', delta='', status='')
            if rc == ERR_ADD_TOO_BIG or (rc and rc & 0x80000000):
                findings.append(dict(suspect='rejected_add', verdict='confirmed', line=e['line'],
                                     evidence='AddStreamData(%d) rc=0x%08X: bytes the title wrote were not taken; if the '
                                     'title advanced its own read position, every later byte is shifted by %d' % (n, rc, n)))
                row['status'] = 'REJECTED'
                feeds.append(row)
                continue
            if used is not None and gv is not None and used != gv:
                findings.append(dict(suspect='write_pointer', verdict='confirmed', line=e['line'],
                                     evidence='AddStreamData copied from 0x%08X but the title was given 0x%08X (line %d)'
                                     % (used, gv, s.given[2])))
                row['status'] = 'WPTR_MISMATCH'
            if off != s.fed:
                findings.append(dict(suspect='write_pointer', verdict='confirmed', line=e['line'],
                                     evidence='add at file offset %d but running sum of adds is %d' % (off, s.fed)))
                row['status'] = (row['status'] + ' ' if row['status'] else '') + 'OFFSET_JUMP'
            rng = (file_hdr or {}).get('ranges') or {}
            if 'fnv' in e and (off, n) in rng and rng[(off, n)] != e['fnv']:
                findings.append(dict(suspect='late_ring_write', verdict='candidate', line=e['line'],
                                     evidence='bytes taken by AddStreamData(off=%d,len=%d) fnv %08x != file bytes %08x'
                                     % (off, n, e['fnv'], rng[(off, n)])))
                row['status'] = (row['status'] + ' ADD_BYTES_WRONG').strip()
            if 'fnv' in e:
                s.add_fnv = getattr(s, 'add_fnv', {}); s.add_fnv[(off, n)] = (e['fnv'], e['line'])
            s.add_interval(off, off + n)
            s.fed = off + n
            if s.bufsz:
                s.woff = (s.woff + n) % s.bufsz
            row['status'] = row['status'] or 'ok'
            feeds.append(row)
            s.given = None
        elif fn == 'AddRecheck':
            key = (e.get('off'), e.get('len'))
            prev = getattr(s, 'add_fnv', {}).get(key)
            rng = (file_hdr or {}).get('ranges') or {}
            if prev and 'fnv' in e and prev[0] != e['fnv']:
                good = rng.get(key)
                why = ''
                if good is not None:
                    why = ' (re-read %s the file, add-time copy %s)' % ('MATCHES' if e['fnv'] == good else 'differs from',
                                                                       'matches' if prev[0] == good else 'differs from the file')
                findings.append(dict(suspect='late_ring_write', verdict='confirmed', line=prev[1],
                                     evidence='ring bytes of add off=%d len=%d changed after AddStreamData (fnv %08x at '
                                     'add, %08x at line %d)%s: the title wrote them after the add, our copy is stale'
                                     % (key[0], key[1], prev[0], e['fnv'], e['line'], why)))
        elif fn == 'ResetPlayPosition':
            smp = e.get('sample', 0) or 0
            wb = e.get('wb', 0) or 0
            first = s.first if s.first is not None else AT3P_DELAY
            p = first + smp
            kp = p // AT3P_SAMPLES
            seek = dict(line=e['line'], kp=kp, old_fed=s.fed, used_stale=False, hole=None, flushed=e.get('flushed'))
            if s.ba is not None and s.doff is not None and wb:
                roff = s.doff + kp * s.ba
                n = min(wb, s.bufsz or wb)
                if roff > s.fed:
                    seek['hole'] = (s.fed, roff)
                s.add_interval(roff, roff + n)
                s.fed = roff + n
                s.woff = n % s.bufsz if s.bufsz else 0
            seek['prev_k'] = s.next_k
            s.seeks.append(seek)
        elif fn in ('DecodeFrame', 'DecodeError') and e['src'] != 'legacy':
            k = e.get('k')
            if k is None or not s.ba or s.doff is None:
                continue
            off = e.get('off', s.doff + k * s.ba)
            ln = e.get('len', s.ba)
            exp = s.doff + k * s.ba
            d = off - exp
            row = dict(kind='decode' if fn == 'DecodeFrame' else 'decode_error', line=e['line'], h='0x%08X' % h, off=off,
                       len=ln, rc='', wea_given='', wea_used='', grid='ok' if d == 0 and ln == s.ba else 'BAD',
                       delta=d, k=k, status='', match='')
            fed = s.is_fed(off, off + ln)
            if not fed:
                row['status'] = 'UNFED'
            if file_frames and 'fnv' in e:
                fv = e['fnv']
                if zero_fnv is None:
                    zero_fnv = fnv1a32(bytes(s.ba))
                fk = file_frames[k][2] if k < len(file_frames) else None
                if fv == fk:
                    row['match'] = 'file_frame_%d' % k
                elif fv == zero_fnv:
                    row['match'] = 'ZEROS'; row['status'] = (row['status'] + ' ZEROS').strip()
                elif by_fnv.get(fv):
                    j = by_fnv[fv][0]
                    row['match'] = 'file_frame_%d (delta %+d frames)' % (j, j - k)
                    row['status'] = (row['status'] + ' WRONG_FRAME').strip()
                else:
                    row['match'] = 'none'; row['status'] = (row['status'] + ' HASH_MISMATCH').strip()
            # seek staleness
            if s.seeks:
                sk = s.seeks[-1]
                if not sk.get('checked'):
                    sk['checked'] = True
                    sk['first_k'] = k
                    if k < sk['kp'] - 1 or (sk['hole'] and off < sk['hole'][1] and off + ln > sk['hole'][0]):
                        sk['used_stale'] = True
                        sk['why'] = 'first decode after seek is frame %d at offset %d; seek target frame %d%s' % (
                            k, off, sk['kp'], ', inside the never-fed hole [%d,%d)' % sk['hole'] if sk['hole'] else '')
                    if 'match' in row and row['match'].startswith('file_frame_') and '(delta' in row['match']:
                        sk['used_stale'] = True; sk['why'] = 'decoded bytes belong to %s' % row['match']
                if sk['hole'] and off < sk['hole'][1] and off + ln > sk['hole'][0]:
                    sk['used_stale'] = True
                    sk.setdefault('why', 'frame %d decoded from never-fed bytes [%d,%d)' % (k, off, off + ln))
            row['status'] = row['status'] or 'ok'
            s.next_k = k + 1
            feeds.append(row)
    seeks = []
    for s in S.values():
        for sk in s.seeks:
            seeks.append(sk)
            if sk['used_stale']:
                findings.append(dict(suspect='seek_no_flush', verdict='confirmed', line=sk['line'],
                                     evidence='ResetPlayPosition at line %d: %s' % (sk['line'], sk.get('why', ''))))
    # grid / delta classification per handle
    grid = {}
    for h, s in S.items():
        pairs = [(r['k'], r['delta']) for r in feeds if r['h'] == '0x%08X' % h and r['kind'].startswith('decode')]
        if pairs and s.ba:
            grid['0x%08X' % h] = classify_deltas(pairs, s.ba, tuple(x for x in fbs if x != s.ba))
    return findings, feeds, seeks, grid, S


def hostcmp_analysis(rows, ba, read=None, ring=None):
    """rows from hostcmp CSV. Bad runs, where they start relative to chunk / ring, delta pattern."""
    bad = [r for r in rows if r['status'] not in ('ok',)]
    runs = []
    for r in bad:
        k = int(r['k'])
        if runs and k == runs[-1]['k1'] + 1 and r['status'] == runs[-1]['status']:
            runs[-1]['k1'] = k; runs[-1]['deltas'].append(r['delta'])
        else:
            runs.append(dict(k0=k, k1=k, status=r['status'], off=int(r['offset']), deltas=[r['delta']]))
    for u in runs:
        u['n'] = u['k1'] - u['k0'] + 1
        u['bytes'] = u['n'] * ba
        ds = [int(d) for d in u['deltas'] if d not in ('', None)]
        u['delta_set'] = sorted(set(ds))[:6]
        u['off_mod_chunk'] = (u['off'] % read) if read else ''
        u['off_mod_ring'] = (u['off'] % ring) if ring else ''
        u['ring_wrap_near'] = bool(ring and min(u['off'] % ring, ring - u['off'] % ring) < ba)
    pairs = []
    for r in rows:
        if r['status'] == 'moved':
            pairs.append((int(r['k']), int(r['delta'])))
    return runs, pairs


# ---------------------------------------------------------------- PCM / RMS
def read_pcm(path, ch, fmt):
    data = open(path, 'rb').read()
    if path.lower().endswith('.wav') and data[:4] == b'RIFF':
        o = 12
        while o + 8 <= len(data):
            cid, cs = data[o:o + 4], le32(data, o + 4)
            if cid == b'fmt ':
                ch = le16(data, o + 10); bits = le16(data, o + 22); tag = le16(data, o + 8)
                fmt = 's16le' if bits == 16 else ('f32le' if tag == 3 else fmt)
            if cid == b'data':
                data = data[o + 8:o + 8 + cs]; break
            o += 8 + cs
    if fmt in ('f32be', 'f32le'):
        n = len(data) // 4
        vals = struct.unpack(('>' if fmt == 'f32be' else '<') + '%df' % n, data[:n * 4])
        full = 1.0
    else:
        n = len(data) // 2
        vals = struct.unpack('<%dh' % n, data[:n * 2])
        full = 32767.0
    return ch, vals, full


def rms_frames(vals, ch, full, frame=AT3P_SAMPLES):
    out = []
    per = frame * ch
    for f in range(len(vals) // per):
        seg = vals[f * per:(f + 1) * per]
        r, pk = [], []
        for c in range(ch):
            xs = seg[c::ch]
            r.append(math.sqrt(sum(x * x for x in xs) / len(xs)) / full)
            pk.append(max(abs(x) for x in xs) / full)
        out.append((r, pk))
    return out


def rms_checks(frames, ref=None, bad_frames=(), silent=1e-5, active=1e-3):
    fl = []
    if not frames:
        return fl
    ch = len(frames[0][0])
    for i, (r, pk) in enumerate(frames):
        for c in range(ch):
            if pk[c] >= 0.999:
                fl.append(dict(frame=i, ch=c, flag='clipped', value='%.4f' % pk[c]))
        mx = max(r)
        for c in range(ch):
            if r[c] < silent and mx > active:
                fl.append(dict(frame=i, ch=c, flag='silent', value='%.2e' % r[c]))
    tot = [sum(x * x for x in r) ** 0.5 for r, _ in frames]
    for i, t in enumerate(tot):
        nb = sorted(tot[max(0, i - 8):i] + tot[i + 1:i + 9])
        med = nb[len(nb) // 2] if nb else 0
        if med > 0 and t > 4 * med:
            near = any(abs(i - b) <= 2 for b in bad_frames)
            fl.append(dict(frame=i, ch='all', flag='burst' + ('_after_bad_feed' if near else ''),
                           value='%.1fx median' % (t / med)))
    if ref:
        n = min(len(ref), len(frames))
        rc = len(ref[0][0])
        def env(fr, c): return [math.log10(fr[i][0][c] + 1e-9) for i in range(n)]
        def corr(a, b):
            ma, mb = sum(a) / len(a), sum(b) / len(b)
            va = sum((x - ma) ** 2 for x in a) ** 0.5; vb = sum((y - mb) ** 2 for y in b) ** 0.5
            return 0 if va == 0 or vb == 0 else sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb)
        for c in range(ch):
            e = env(frames, c)
            sc = [(corr(e, env(ref, j)), j) for j in range(rc)]
            best = max(sc)
            if best[1] != c and best[0] > corr(e, env(ref, c)) + 0.2 and best[0] > 0.8:
                fl.append(dict(frame='all', ch=c, flag='swapped', value='energy follows ref ch %d (r=%.2f vs %.2f)'
                               % (best[1], best[0], corr(e, env(ref, c)))))
    else:
        # energy transfer without a reference: one channel drops >30 dB while another rises >30 dB at once
        for i in range(1, len(frames)):
            a, b = frames[i - 1][0], frames[i][0]
            down = [c for c in range(ch) if a[c] > active and b[c] < a[c] * 0.03]
            up = [c for c in range(ch) if b[c] > active and a[c] < b[c] * 0.03]
            if down and up:
                fl.append(dict(frame=i, ch='%s->%s' % (down, up), flag='energy_moved', value=''))
    return fl


# ---------------------------------------------------------------- report
def write_csv(path, rows, cols=None):
    if not rows:
        open(path, 'w').write('')
        return
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)


def analyze(args):
    os.makedirs(args.out, exist_ok=True)
    md = io.StringIO()
    P = lambda *a: md.write(' '.join(str(x) for x in a) + '\n')
    file_hdr = file_frames = None
    if args.file:
        buf = open(args.file, 'rb').read()
        file_hdr = parse_header(buf); file_frames = frame_table(buf, file_hdr)
    elif args.hashes:
        file_hdr, file_frames = read_hashfile(args.hashes)
    P('# ATRAC stream validator report\n')
    P('Inputs:', ', '.join(args.log), ('| frame hashes: ' + (args.file or args.hashes)) if file_frames else '| no file hashes',
      ('| hostcmp: ' + args.hostcmp) if args.hostcmp else '', ('| pcm: ' + args.pcm) if args.pcm else '')
    P('\nLabels: KNOWN = read from the log/bytes in hand; ASSUMED = inference; VERIFY = needs the PC run.\n')
    verdict = {k: ('unknown', []) for k in ('header (wrong data_start / frame size)', 'seek_no_flush (ResetPlayPosition, suspect a)',
                                           'write_pointer (AddStreamData recomputes, suspect b)',
                                           'rejected_add / ring wrap (old AddStreamData contiguous-room limit)',
                                           'late_ring_write (AddStreamData snapshots the ring before the title\'s read lands)')}
    vkey = {'header': 'header (wrong data_start / frame size)', 'seek_no_flush': 'seek_no_flush (ResetPlayPosition, suspect a)',
            'write_pointer': 'write_pointer (AddStreamData recomputes, suspect b)',
            'rejected_add': 'rejected_add / ring wrap (old AddStreamData contiguous-room limit)',
            'late_ring_write': 'late_ring_write (AddStreamData snapshots the ring before the title\'s read lands)'}
    all_epochs, all_feeds, all_findings, all_hdr = [], [], [], []
    have_calls = {'add': 0, 'seek': 0, 'decodeframe': 0, 'given': 0}
    for lp in args.log:
        ev = parse_log(lp, args.tick_re)
        name = os.path.basename(lp)
        sets = [e for e in ev if e['fn'] == 'SetData']
        nerr = sum(1 for e in ev if e['fn'] == 'DecodeError')
        fmts = collections.Counter(e['src'] for e in ev)
        P('\n## Log `%s`\n' % name)
        P('- parsed: %s; SetData %d; decoder-error lines %d; audio ticks (tid 10 WAIT lines) %d'
          % (dict(fmts), len(sets), nerr, ev[-1]['tick'] if ev else 0))
        for e in ev:
            if e['fn'] == 'AddStreamData': have_calls['add'] += 1
            if e['fn'] == 'ResetPlayPosition': have_calls['seek'] += 1
            if e['fn'] == 'DecodeFrame': have_calls['decodeframe'] += 1
            if e['fn'] == 'GetStreamDataInfo': have_calls['given'] += 1
            if e['fn'] == 'AddRecheck': have_calls['recheck'] = have_calls.get('recheck', 0) + 1
        rows, inf = header_inference([e for e in sets if e.get('ch', 0) > 2])
        if rows:
            for r in rows: r['log'] = name
            all_hdr += rows
            P('- header inference from SetData lines (KNOWN arithmetic, ASSUMES data_bytes is an exact multiple):',
              'tracks %d, block_align consistent with all: %s, consistent data_off per loop class: %s'
              % (inf['tracks'], inf['block_align_common'], inf['consistent']))
        eps = error_epochs(ev, args.gap_ticks)
        for ep in eps:
            ep['log'] = name
        all_epochs += eps
        if eps:
            P('\n| SetData line | handle | ch | frames | total | errors | kinds | episodes (first line: n, signature) |')
            P('|---|---|---|---|---|---|---|---|')
            for ep in eps:
                es = '; '.join('L%d: %d %s%s' % (x['first_line'], x['n'], x['sig'], (' = %d x %d-byte chunk' % (x['chunks'], ep['read'])) if x['chunks'] else '')
                               for x in ep['episodes'] if x['n'] >= 3)
                P('| %d | 0x%08X | %s | %s | %s | %d | %s | %s |' % (ep['line'], ep['h'], ep['ch'], ep['frames'], ep['total'],
                                                                ep['errors'], ep['kinds'], es or '-'))
        f, feeds, seeks, grid, S = stream_checks(ev, file_frames, file_hdr)
        for r in feeds: r['log'] = name
        for x in f: x['log'] = name
        all_feeds += feeds; all_findings += f
        if grid:
            P('\n- frame-grid check on decoder feeds:')
            for h, (pat, det) in grid.items():
                P('  - %s: **%s** - %s' % (h, pat, det))
                if pat in ('constant', 'growing', 'stride_mixup'):
                    all_findings.append(dict(suspect='header', verdict='confirmed', line='', log=name, evidence='%s %s' % (h, det)))
                elif pat == 'step':
                    all_findings.append(dict(suspect='rejected_add', verdict='confirmed', line='', log=name, evidence='%s %s' % (h, det)))
        if seeks:
            P('- seeks (ResetPlayPosition): %d, stale after seek: %d' % (len(seeks), sum(1 for s in seeks if s['used_stale'])))
    # signature summary over all episodes
    sig = collections.defaultdict(collections.Counter)
    for ep in all_epochs:
        for x in ep['episodes']:
            if x['sig'] in ('zeros-like', 'random-like'):
                sig[x['sig']].update(x['kinds']); sig[x['sig']]['_episodes'] += 1
    if sig:
        P('\n## Error signatures (decoder errors are one line per rejected frame)\n')
        P('Byte 0 of a 6ch frame: bit 7 = start bit (must be 0), bits 6-5 = first unit tag (must be 1 = stereo).')
        P('Uniformly random bytes would give: start_bit 50%, unit_mismatch_b0 (tag 0) 12.5%, extension (tag 2) 12.5%, '
          'tag 3 12.5%, valid 12.5% (then deeper errors). All-zero bytes give unit_mismatch_b0 100%. (derived, ASSUMES uniform bits)\n')
        P('| signature | episodes | errors | start_bit | unit_mismatch_b0 | extension | other |')
        P('|---|---|---|---|---|---|---|')
        for k, c in sig.items():
            n = sum(v for kk, v in c.items() if kk != '_episodes')
            o = n - c['start_bit'] - c['unit_mismatch_b0'] - c['extension']
            P('| %s | %d | %d | %.1f%% | %.1f%% | %.1f%% | %.1f%% |' % (k, c['_episodes'], n, 100 * c['start_bit'] / n,
              100 * c['unit_mismatch_b0'] / n, 100 * c['extension'] / n, 100 * o / n))
    # host compare
    if args.hostcmp:
        rows = list(csv.DictReader(l for l in open(args.hostcmp) if not l.startswith('#')))
        ba = int(args.ba or (file_hdr or {}).get('frame_bytes') or 1712)
        runs, pairs = hostcmp_analysis(rows, ba, args.chunk, args.ring)
        n_ok = sum(1 for r in rows if r['status'] == 'ok')
        P('\n## Host copy vs original (`%s`)\n' % os.path.basename(args.hostcmp))
        P('- frames %d: ok %d, bad %d in %d runs' % (len(rows), n_ok, len(rows) - n_ok, len(runs)))
        for u in runs[:40]:
            P('  - frames %d..%d (%d frames, %d bytes) %s, file offset %d, offset mod chunk %s, mod ring %s%s, deltas %s'
              % (u['k0'], u['k1'], u['n'], u['bytes'], u['status'], u['off'], u['off_mod_chunk'], u['off_mod_ring'],
                 ' NEAR RING WRAP' if u['ring_wrap_near'] else '', u['delta_set']))
        if pairs:
            pat, det = classify_deltas(pairs + [(int(r['k']), 0) for r in rows if r['status'] == 'ok'], ba)
            P('- delta pattern of moved frames: **%s** - %s' % (pat, det))
        if any(u['status'] == 'zeros' for u in runs):
            all_findings.append(dict(suspect='seek_no_flush', verdict='candidate', line='', log=args.hostcmp,
                                     evidence='host copy has never-written (zero) frames: %s' %
                                     ', '.join('%d..%d' % (u['k0'], u['k1']) for u in runs if u['status'] == 'zeros')[:300]))
        if any(u['status'] == 'zeros' for u in runs):
            all_findings.append(dict(suspect='late_ring_write', verdict='candidate', line='', log=args.hostcmp,
                                     evidence='zero frames in the host copy can also be ring bytes copied before the read landed'))
        if any(u['ring_wrap_near'] for u in runs):
            all_findings.append(dict(suspect='rejected_add', verdict='candidate', line='', log=args.hostcmp,
                                     evidence='bad run starts within one frame of a ring wrap'))
        write_csv(os.path.join(args.out, 'hostcmp_runs.csv'), [{k: v for k, v in u.items() if k != 'deltas'} for u in runs])
    # pcm
    rmsflags = []
    if args.pcm:
        ch, vals, full = read_pcm(args.pcm, args.pcm_ch, args.pcm_fmt)
        fr = rms_frames(vals, ch, full)
        ref = None
        if args.pcm_ref:
            rch, rv, rfull = read_pcm(args.pcm_ref, args.pcm_ch, args.pcm_fmt)
            ref = rms_frames(rv, rch, rfull)
        rmsflags = rms_checks(fr, ref)
        P('\n## Per-channel RMS (`%s`, %d ch, %d frames of 2048)\n' % (args.pcm, ch, len(fr)))
        c = collections.Counter(x['flag'] for x in rmsflags)
        P('- flags:', dict(c) or 'none')
        write_csv(os.path.join(args.out, 'rms_frames.csv'),
                  [dict(frame=i, **{'rms%d' % j: '%.6f' % v for j, v in enumerate(r)}) for i, (r, _) in enumerate(fr)])
        write_csv(os.path.join(args.out, 'rms_flags.csv'), rmsflags)
    else:
        P('\n## Per-channel RMS\n- skipped: no PCM given (see README for the input format).')
    # verdicts
    for x in all_findings:
        key = vkey.get(x['suspect'])
        if not key: continue
        v, ev_ = verdict[key]
        if x['verdict'] == 'confirmed':
            v = 'confirmed'
        elif v == 'unknown':
            v = 'candidate'
        verdict[key] = (v, ev_ + [x])
    # ruled-out logic needs positive coverage
    if have_calls['add'] and have_calls['given'] and verdict[vkey['write_pointer']][0] == 'unknown':
        verdict[vkey['write_pointer']] = ('ruled out', [dict(evidence='%d adds checked against given pointers, no mismatch' % have_calls['add'])])
    if have_calls['seek'] and have_calls['decodeframe'] and verdict[vkey['seek_no_flush']][0] == 'unknown':
        verdict[vkey['seek_no_flush']] = ('ruled out', [dict(evidence='%d seeks, decodes after each are on fed bytes' % have_calls['seek'])])
    if have_calls['add'] and verdict[vkey['rejected_add']][0] == 'unknown':
        verdict[vkey['rejected_add']] = ('ruled out', [dict(evidence='%d adds, none rejected' % have_calls['add'])])
    if have_calls.get('recheck') and verdict[vkey['late_ring_write']][0] == 'unknown':
        verdict[vkey['late_ring_write']] = ('ruled out', [dict(evidence='%d add re-checks, ring bytes unchanged after every add' % have_calls['recheck'])])
    if file_hdr and have_calls['decodeframe'] and verdict[vkey['header']][0] == 'unknown':
        verdict[vkey['header']] = ('ruled out', [dict(evidence='decoder feeds on the grid of the real header')])
    first = sorted([x for x in all_findings if x.get('line') != ''], key=lambda x: (str(x.get('log')), int(x['line'])))
    P('\n## First failure\n')
    if first:
        x = first[0]
        P('- %s line %s: %s -> %s' % (x.get('log'), x['line'], x['suspect'], x['evidence']))
    elif any(ep['errors'] for ep in all_epochs):
        ep = next(ep for ep in all_epochs if ep['errors'])
        P('- only decoder errors are available: first one in `%s` epoch SetData L%d (episode L%d). No per-call lines, so '
          'which byte range was wrong cannot be named from this log.' % (ep['log'], ep['line'], ep['episodes'][0]['first_line']))
    else:
        P('- none found')
    P('\n## Verdict per suspect\n')
    P('| suspect | verdict | evidence |')
    P('|---|---|---|')
    for k, (v, evs) in verdict.items():
        e = '<br>'.join(('%s L%s: ' % (x.get('log', ''), x.get('line', '')) if x.get('line') not in (None, '') else '') +
                        str(x['evidence']) for x in evs[:5])
        if v == 'unknown':
            e = 'no per-call lines for this check in the input (needs SF_ATRAC_LOG / [atrac-diag] lines)'
        P('| %s | **%s** | %s |' % (k, v, e))
    P('\nPer-call coverage: AddStreamData %d, GetStreamDataInfo %d, ResetPlayPosition %d, DecodeFrame %d'
      % (have_calls['add'], have_calls['given'], have_calls['seek'], have_calls['decodeframe']))
    # csv
    write_csv(os.path.join(args.out, 'feeds.csv'), all_feeds)
    write_csv(os.path.join(args.out, 'findings.csv'), all_findings)
    write_csv(os.path.join(args.out, 'header_inference.csv'), all_hdr)
    ep_rows = []
    for ep in all_epochs:
        for x in ep['episodes']:
            ep_rows.append(dict(log=ep['log'], setdata_line=ep['line'], handle='0x%08X' % ep['h'], frames=ep['frames'],
                                total=ep['total'], first_line=x['first_line'], last_line=x['last_line'], n=x['n'],
                                ticks=x['ticks'], signature=x['sig'], chunk_sized=x['chunk_sized'], chunks=x['chunks'],
                                kinds=';'.join('%s:%d' % kv for kv in x['kinds'].items())))
    write_csv(os.path.join(args.out, 'error_episodes.csv'), ep_rows)
    open(os.path.join(args.out, 'report.md'), 'w').write(md.getvalue())
    return md.getvalue(), verdict, all_epochs, all_findings


# ---------------------------------------------------------------- self-tests
def make_riff(ch=6, ba=1712, frames=40, loop=True, seed=1):
    rnd = random.Random(seed)
    fmt = struct.pack('<HHIIHHHHI', 0xFFFE, ch, 48000, ba * 48000 // 2048, ba, 0, 34, 2048, 0x3F) + AT3P_GUID + bytes(12)
    fact = struct.pack('<III', frames * 2048 - 2048, 2704, 2704)
    smpl = struct.pack('<9I', 0, 0, 0, 60, 0, 0, 0, 1, 0) + struct.pack('<6I', 0, 0, 2704, frames * 2048 - 1, 0, 0)
    data = bytearray()
    for k in range(frames):
        fr = bytearray(rnd.getrandbits(8) for _ in range(ba))
        fr[0] = 0x20 | (fr[0] & 0x1F)
        data += fr
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt + b'fact' + struct.pack('<I', 12) + fact
    if loop:
        body += b'smpl' + struct.pack('<I', len(smpl)) + smpl
    body += b'data' + struct.pack('<I', len(data)) + bytes(data)
    return b'RIFF' + struct.pack('<I', len(body)) + body


def make_oma(ba=1712, frames=5):
    tag = b'ea3\x03\x00\x00' + bytes([0, 0, 0, 22]) + bytes(22)
    raw = ba // 8 - 1
    params = (0 << 17) | (2 << 13) | (5 << 10) | raw
    ea3 = b'EA3\x02\x00\x60\xff\xff' + bytes(24) + bytes([1, (params >> 16) & 0xFF, (params >> 8) & 0xFF, params & 0xFF]) + bytes(60)
    return tag + ea3 + bytes(ba * frames)


def selftest():
    import tempfile
    T = []
    def check(name, cond, info=''):
        T.append((name, bool(cond), info))
    # header
    f = make_riff(); h = parse_header(f)
    check('riff header 6ch+smpl: ba 1712, data_start 168', h['frame_bytes'] == 1712 and h['data_start'] == 168
          and h['codec'] == 'ATRAC3plus' and h['channels'] == 6, (h['frame_bytes'], h['data_start']))
    h2 = parse_header(make_riff(loop=False))
    check('riff header no smpl: data_start 100', h2['data_start'] == 100, h2['data_start'])
    ho = parse_header(make_oma())
    check('oma header: frame bytes (raw+1)*8 = 1712, data after 96-byte EA3', ho['frame_bytes'] == 1712 and ho['data_start'] == 32 + 96,
          (ho['frame_bytes'], ho['data_start']))
    check('frame start byte check', frame_start_ok(0x2A, 6) and not frame_start_ok(0x00, 6) and not frame_start_ok(0xA0, 6))
    # delta patterns
    fb = 1712
    ok = [(k, 0) for k in range(20)]
    check('delta ok', classify_deltas(ok, fb)[0] == 'ok')
    check('delta constant -> wrong data_start', classify_deltas([(k, 8) for k in range(20)], fb)[0] == 'constant')
    check('delta growing -> wrong frame size', classify_deltas([(k, 16 * k) for k in range(20)], fb)[0] == 'growing')
    p2 = classify_deltas([(k, k * (1712 * 2 // 6 - 1712)) for k in range(1, 20)], fb)
    check('delta k*(frame_2ch-frame_6ch) -> stride mixup', p2[0] == 'stride_mixup', p2)
    p3 = classify_deltas([(k, k * (744 - 1712)) for k in range(1, 20)], fb, (744,))
    check('delta uses other stream frame size -> stride mixup', p3[0] == 'stride_mixup', p3)
    check('delta step -> dropped add', classify_deltas([(k, 0 if k < 7 else 131072 % fb) for k in range(20)], fb)[0] == 'step')
    # legacy parser + header inference
    tmp = tempfile.mkdtemp()
    lg = os.path.join(tmp, 'legacy.log')
    with open(lg, 'w') as w:
        for tot, fr, loop in ((3413896, 1994, 1), (2893448, 1690, 1), (315108, 184, 0), (5511096, 3219, 1)):
            w.write('[cellAtrac] SetData: streaming 131072 of %d bytes, ring=1048576\n' % tot)
            w.write('[cellAtrac] SetData handle=0x119FA1F0 ch=6 frames=%d first=3072 end=%d loop=[%s) all_on_mem=0\n'
                    % (fr, fr * 2048, '100,200' if loop else '-1,-1'))
            for i in range(400):
                w.write('[WAIT] event_queue_receive(q=1 timeout=9000000) tid=10 cia=0x0080FC68 lr=0x0004D510\n')
                if fr == 1690 and 100 <= i < 177:
                    w.write("[cellAtrac] Atrac3/3+: Frame data doesn't match channel configuration! ch_block 0 >= num_channel_blocks 4\n")
                if fr == 3219 and 50 <= i < 150 and i % 2 == 0:
                    w.write('[cellAtrac] Atrac3/3+: %s\n' % ('Invalid start bit!' if i % 4 == 0 else 'Missing atrac3p feature: Channel unit extension'))
    ev = parse_log(lg)
    rows, inf = header_inference([e for e in ev if e['fn'] == 'SetData'])
    check('legacy header inference -> 1712 with data_off 168/100', 1712 in inf['consistent'] and
          inf['consistent'][1712] == {'loop': 168, 'noloop': 100}, inf['consistent'])
    eps = error_epochs(ev, 160)
    e1690 = [x for x in eps if x['frames'] == 1690][0]['episodes']
    check('zero-fill signature + chunk-sized episode (77 frames)', e1690 and e1690[0]['sig'] == 'zeros-like'
          and e1690[0]['chunk_sized'], e1690[:1])
    e3219 = [x for x in eps if x['frames'] == 3219][0]['episodes']
    check('random-like signature', e3219 and e3219[0]['sig'] == 'random-like', e3219[:1])
    # per-call scenarios with a real synthetic file
    track = make_riff(frames=60, seed=7); th = parse_header(track); tf = frame_table(track, th)
    hp = os.path.join(tmp, 'h.tsv')
    with open(hp, 'w') as w:
        write_hashfile(None, track, w)
    rh, rr = read_hashfile(hp)
    check('hashfile round trip', rh['frame_bytes'] == 1712 and rh['data_start'] == 168 and rr == tf)
    def run(lines, name):
        p = os.path.join(tmp, name + '.log'); open(p, 'w').write('\n'.join(lines) + '\n')
        a = argparse.Namespace(log=[p], file=None, hashes=hp, hostcmp=None, pcm=None, pcm_ref=None, pcm_ch=6,
                               pcm_fmt='f32be', out=os.path.join(tmp, name), tick_re=TICK_DEFAULT, gap_ticks=160,
                               ba=None, chunk=131072, ring=1048576)
        return analyze(a)
    H = 'h=0x119FA1F0'
    def dec(k, data=None, off=None):
        o = 168 + k * 1712 if off is None else off
        b = track[o:o + 1712] if data is None else data
        return '[sf-atrac] fn=DecodeFrame %s k=%d off=%d len=1712 fnv=0x%08x' % (H, k, o, fnv1a32(b))
    base = ['[sf-atrac] fn=SetData %s ch=6 ba=1712 doff=168 first=3072 buf=0x30000000 bufsz=65536 read=20000 total=%d'
            % (H, len(track))]
    # clean
    L = base[:]
    fed = 20000
    for i in range(4):
        L.append('[sf-atrac] fn=GetStreamDataInfo %s wea_given=0x%08X readpos=%d writable=10000 rc=0' % (H, 0x30000000 + fed % 65536, fed))
        L.append('[sf-atrac] fn=AddStreamData %s add=20000 off=%d wea_used=0x%08X rc=0' % (H, fed, 0x30000000 + fed % 65536)); fed += 20000
    L += [dec(k) for k in range(40)]
    _, v, _, fnd = run(L, 'clean')
    check('clean stream: nothing confirmed', all(x[0] != 'confirmed' for x in v.values()) and not fnd, [(k, x[0]) for k, x in v.items()])
    # recomputed write pointer
    L2 = base[:] + ['[sf-atrac] fn=GetStreamDataInfo %s wea_given=0x%08X readpos=20000 writable=10000 rc=0' % (H, 0x30000000 + 20000),
                    '[sf-atrac] fn=AddStreamData %s add=20000 off=20000 wea_used=0x%08X rc=0' % (H, 0x30000000 + 20000 + 1712)]
    _, v, _, _ = run(L2, 'wptr')
    check('recomputed write pointer -> confirmed', v[[k for k in v if k.startswith('write_pointer')][0]][0] == 'confirmed')
    # rejected add (ring wrap)
    L3 = base[:] + ['[sf-atrac] fn=AddStreamData %s add=50000 off=20000 rc=0x80610342' % H]
    _, v, _, _ = run(L3, 'reject')
    check('rejected add -> confirmed', v[[k for k in v if k.startswith('rejected_add')][0]][0] == 'confirmed')
    # seek without flush: seek forward to sample 30*2048 with data written, decoder continues at old frame and walks the hole
    L4 = base[:] + [dec(k) for k in range(5)]
    L4.append('[sf-atrac] fn=ResetPlayPosition %s sample=%d wb=20000' % (H, 30 * 2048 - 3072))
    L4 += [dec(k, data=(track[168 + k * 1712:168 + (k + 1) * 1712] if k < 12 else bytes(1712))) for k in range(5, 32)]
    _, v, _, fnd = run(L4, 'seek')
    check('seek without flush -> confirmed', v[[k for k in v if k.startswith('seek_no_flush')][0]][0] == 'confirmed',
          [x['evidence'] for x in fnd if x['suspect'] == 'seek_no_flush'][:1])
    # seek with flush (clean)
    L5 = base[:] + [dec(k) for k in range(5)]
    L5.append('[sf-atrac] fn=ResetPlayPosition %s sample=%d wb=20000' % (H, 30 * 2048 - 3072))
    L5 += [dec(k) for k in range(30, 36)]
    _, v, _, _ = run(L5, 'seekok')
    check('seek with flush -> ruled out', v[[k for k in v if k.startswith('seek_no_flush')][0]][0] == 'ruled out')
    # late ring write: add-time hash = stale ring bytes, re-read later = real file bytes
    stale = bytes(20000); real = track[20000:40000]
    L8 = base[:] + ['[sf-atrac] fn=AddStreamData %s add=20000 off=20000 rc=0 fnv=0x%08x' % (H, fnv1a32(stale)),
                    '[sf-atrac] fn=AddRecheck %s off=20000 len=20000 fnv=0x%08x' % (H, fnv1a32(real))]
    lp = os.path.join(tmp, 'late_src.log'); open(lp, 'w').write('\n'.join(L8) + '\n')
    hp2 = os.path.join(tmp, 'h2.tsv')
    with open(hp2, 'w') as w:
        write_hashfile(None, track, w, log_ranges(lp))
    a8 = argparse.Namespace(log=[lp], file=None, hashes=hp2, hostcmp=None, pcm=None, pcm_ref=None, pcm_ch=6, pcm_fmt='f32be',
                            out=os.path.join(tmp, 'late'), tick_re=TICK_DEFAULT, gap_ticks=160, ba=None, chunk=131072, ring=1048576)
    _, v, _, fnd = analyze(a8)
    k8 = [k for k in v if k.startswith('late_ring_write')][0]
    check('late ring write (add snapshot before read lands) -> confirmed, re-read matches file', v[k8][0] == 'confirmed'
          and any('MATCHES the file' in x['evidence'] for x in fnd), [x['evidence'] for x in fnd][:2])
    # existing [atrac-diag] format (SF_ATRAC_DIAG=1 build): rejected add + readpos drift
    L9 = ['[atrac-diag] t=1.00 mix=0.50 #3 SetData h=0x119FA1F0 buf=0x30000000 read=131072 bufbytes=1048576 rc=0x00000000 ch=6 aom=0 total=2893448 work=4096',
          '[atrac-diag] #3 cellAtracGetStreamDataInfo h=0x119FA1F0 rc=0x00000000 wptr=0x30020000 writable=917504 readpos=131072',
          '[atrac-diag] #3 cellAtracAddStreamData h=0x119FA1F0 rc=0x00000000 add=131072',
          '[atrac-diag] #3 cellAtracGetStreamDataInfo h=0x119FA1F0 rc=0x00000000 wptr=0x30040000 writable=786432 readpos=262144',
          '[atrac-diag] #3 cellAtracAddStreamData h=0x119FA1F0 rc=0x80610342 add=900000']
    _, v, _, fnd = run(L9, 'diag')
    check('[atrac-diag] lines parsed: rejected add confirmed, pointers consistent', v[[k for k in v if k.startswith('rejected_add')][0]][0] == 'confirmed'
          and not any(x['suspect'] == 'write_pointer' for x in fnd), [x['evidence'] for x in fnd])
    # hash compare: decoder handed frame 9 when it wanted frame 12
    L6 = base[:] + [dec(k) for k in range(10)] + [dec(12, data=track[168 + 9 * 1712:168 + 10 * 1712])]
    _, v, _, _ = run(L6, 'hash')
    feeds = list(csv.DictReader(open(os.path.join(tmp, 'hash', 'feeds.csv'))))
    check('hash compare names the real source frame', any('file_frame_9 (delta -3 frames)' in r['match'] for r in feeds))
    # grid: decoder fed at wrong data_start
    L7 = base[:] + [dec(k, off=168 + 8 + k * 1712) for k in range(10)]
    _, v, _, _ = run(L7, 'grid')
    check('grid constant delta -> header confirmed', v[[k for k in v if k.startswith('header')][0]][0] == 'confirmed')
    # hostcmp: zero hole + chunk copied from wrong ring position
    host = bytearray(track)
    host[168 + 10 * 1712:168 + 15 * 1712] = bytes(5 * 1712)
    host[168 + 30 * 1712 + 100:168 + 36 * 1712] = track[168 + 20 * 1712 + 100 - 512:168 + 26 * 1712 - 512]
    th2, hr = hostcmp(track, bytes(host))
    st = collections.Counter(r[2] for r in hr)
    moved = [r for r in hr if r[2] == 'moved']
    check('hostcmp finds zeros + moved bytes with the true delta', st['zeros'] == 5 and moved and all(r[4] == -10 * 1712 - 512 for r in moved),
          (dict(st), moved[:1]))
    # RMS
    def pcm(nf, swap=False, silent=None, clip=None):
        v = []
        rnd = random.Random(3)
        amps = [0.1, 0.2, 0.05, 0.02, 0.3, 0.15]
        for f_ in range(nf):
            env = [a * (1 + 0.8 * math.sin(f_ * (c + 1) * 0.37)) for c, a in enumerate(amps)]
            if swap and f_ >= 0:
                env[0], env[4] = env[4], env[0]
            for i in range(2048):
                for c in range(6):
                    x = env[c] * (rnd.random() * 2 - 1)
                    if silent == c: x = 0.0
                    if clip == c and i == 5 and f_ == 3: x = 1.0
                    v.append(x)
        return v
    ref = rms_frames(pcm(24), 6, 1.0)
    fl = rms_checks(rms_frames(pcm(24, swap=True), 6, 1.0), ref)
    sw = [x for x in fl if x['flag'] == 'swapped']
    check('channel swap detected vs reference (ch0<->ch4)', sorted(x['ch'] for x in sw) == [0, 4], sw)
    fl = rms_checks(rms_frames(pcm(8, silent=3, clip=2), 6, 1.0))
    check('silent + clipped channels flagged', any(x['flag'] == 'silent' and x['ch'] == 3 for x in fl) and
          any(x['flag'] == 'clipped' and x['ch'] == 2 for x in fl))
    fl = rms_checks(rms_frames(pcm(24), 6, 1.0), ref)
    check('clean PCM vs reference: no flags', not fl, fl[:3])
    bad = 0
    for name, okk, info in T:
        print('%s  %s%s' % ('PASS' if okk else 'FAIL', name, '' if okk else '  -> %s' % (info,)))
        bad += not okk
    print('\n%d/%d passed' % (len(T) - bad, len(T)))
    return bad == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd')
    a = sp.add_parser('header'); a.add_argument('file')
    a = sp.add_parser('hashfile'); a.add_argument('file'); a.add_argument('--out')
    a.add_argument('--ranges', help='SF_ATRAC_LOG log: also hash every logged add range (off,len)')
    a = sp.add_parser('hostcmp'); a.add_argument('--orig', required=True); a.add_argument('--host', required=True); a.add_argument('--out')
    a = sp.add_parser('analyze')
    a.add_argument('--log', action='append', default=[]); a.add_argument('--hashes'); a.add_argument('--file')
    a.add_argument('--hostcmp'); a.add_argument('--pcm'); a.add_argument('--pcm-ref'); a.add_argument('--pcm-ch', type=int, default=6)
    a.add_argument('--pcm-fmt', default='f32be', choices=['f32be', 'f32le', 's16le'])
    a.add_argument('--out', default='atrac_report'); a.add_argument('--tick-re', default=TICK_DEFAULT)
    a.add_argument('--gap-ticks', type=int, default=160); a.add_argument('--ba', type=int)
    a.add_argument('--chunk', type=int, default=131072); a.add_argument('--ring', type=int, default=1048576)
    sp.add_parser('selftest')
    args = ap.parse_args()
    if args.cmd == 'header':
        h = parse_header(open(args.file, 'rb').read())
        for k, v in h.items(): print('%s=%s' % (k, v))
    elif args.cmd == 'hashfile':
        buf = open(args.file, 'rb').read()
        out = open(args.out, 'w') if args.out else sys.stdout
        write_hashfile(args.file, buf, out, log_ranges(args.ranges) if args.ranges else ())
    elif args.cmd == 'hostcmp':
        o = open(args.orig, 'rb').read(); hb = open(args.host, 'rb').read()
        hdr, rows = hostcmp(o, hb)
        out = open(args.out, 'w', newline='') if args.out else sys.stdout
        out.write('# orig_bytes=%d host_bytes=%d frame_bytes=%d data_start=%d frames=%d\n'
                  % (len(o), len(hb), hdr['frame_bytes'], hdr['data_start'], hdr['frames']))
        w = csv.writer(out); w.writerow(['k', 'offset', 'status', 'src_offset', 'delta', 'byte0'])
        for r in rows: w.writerow(r)
        st = collections.Counter(r[2] for r in rows)
        sys.stderr.write('frames=%d %s\n' % (len(rows), dict(st)))
    elif args.cmd == 'analyze':
        if not args.log: ap.error('--log needed')
        md, *_ = analyze(args)
        print(md)
    elif args.cmd == 'selftest':
        sys.exit(0 if selftest() else 1)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()

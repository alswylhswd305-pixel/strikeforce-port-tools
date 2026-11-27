#!/usr/bin/env python3
"""census_report.py -- rank RSX methods by draws affected (RSX_CENSUS output).

  python census_report.py rsx_census.txt [--coverage coverage.json] [--out DIR] [--title T]
  python census_report.py --methlog stderr.txt ...   (PARTIAL: [METHLOG] change log, no draw counts)

Writes report.md and report.html. "Likely visual impact" only states what the
register does (KNOWN register meaning from public NV40/RSX docs); any link to
an open Strikeforce bug is marked ASSUMED.
"""
import argparse, html, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))

FLOAT_METHODS = set([0x0A78, 0x0A7C, 0x0394, 0x0398, 0x08D0, 0x08D4, 0x0384, 0x0388, 0x1EE0])
FLOAT_METHODS |= set(range(0x0A20, 0x0A40, 4))
FLOAT_METHODS |= set(range(0x1C00, 0x1D00, 4)) | set(range(0x1F00, 0x1F80, 4))
FLOAT_METHODS |= set(range(0x1500, 0x1600, 4)) | set(range(0x1880, 0x1900, 4)) | set(range(0x1E40, 0x1E80, 4))

GL_ENUM = {0x2601: 'LINEAR', 0x0800: 'EXP', 0x0801: 'EXP2', 0x1B00: 'POINT', 0x1B01: 'LINE', 0x1B02: 'FILL',
           0x1D00: 'FLAT', 0x1D01: 'SMOOTH', 0x0200: 'NEVER', 0x0201: 'LESS', 0x0202: 'EQUAL', 0x0203: 'LEQUAL',
           0x0204: 'GREATER', 0x0205: 'NOTEQUAL', 0x0206: 'GEQUAL', 0x0207: 'ALWAYS', 0x0404: 'FRONT',
           0x0405: 'BACK', 0x0408: 'FRONT_AND_BACK', 0x0900: 'CW', 0x0901: 'CCW'}
ENUM_METHODS = {0x08CC, 0x1828, 0x182C, 0x0368, 0x0A6C, 0x0308, 0x0330, 0x0350, 0x1830, 0x1834}

# KNOWN register meaning (what the register does), never a claim about cause.
IMPACT = [
    ((0x0A60, 0x0A68), 'polygon offset enable (point/line/fill): turns on depth bias for coplanar geometry such as decals and the shadow-map pass',
     'shadow acne / decal z-fighting (ASSUMED link)'),
    ((0x0A78, 0x0A7C), 'polygon offset factor/bias: the depth bias amount (slope factor, constant units)',
     'shadow acne / decal z-fighting (ASSUMED link)'),
    ((0x08CC, 0x08D4), 'fog mode and fog params: how the fog factor is computed from the fog coordinate and handed to the fragment program',
     'haze / distance colour (ASSUMED link)'),
    ((0x1D78, 0x1D78), 'ZMIN_MAX_CONTROL: near/far plane clipping vs depth clamping',
     'geometry popping or cut at near/far, oversized shapes near camera (ASSUMED link)'),
    ((0x1738, 0x1738), 'vertex data base offset: added to every vertex array offset', 'wrong/garbage vertices (ASSUMED link)'),
    ((0x173C, 0x173C), 'vertex data base index: added to every index before fetch', 'wrong/garbage vertices (ASSUMED link)'),
    ((0x0A20, 0x0A3C), 'viewport offset/scale: maps clip space to window pixels (sub-viewports, y flip)',
     'stretched/flipped draws, the 2x wide shape case A (ASSUMED link)'),
    ((0x0394, 0x0398), 'clip min/max: depth range the viewport maps z into', 'depth precision / depth-test differences (ASSUMED link)'),
    ((0x08C0, 0x08C4), 'scissor rectangle: pixels outside are discarded', 'draws spilling outside their rect (ASSUMED link)'),
    ((0x034C, 0x0358), 'back-face stencil write mask / ref / mask (two-sided stencil)', 'stencil shadow volumes (ASSUMED link)'),
    ((0x031C, 0x031C), 'blend constant colour (used by CONSTANT_COLOR/ALPHA blend factors)', ''),
    ((0x037C, 0x037C), 'blend constant colour 2 (FP16 targets)', ''),
    ((0x036C, 0x036C), 'per-target blend enable for MRT 1-3', ''),
    ((0x0380, 0x0388), 'depth bounds test: discards pixels whose stored depth is outside [min,max]', ''),
    ((0x0300, 0x0300), 'dither enable', ''),
    ((0x0368, 0x0368), 'shade mode: flat vs smooth colour interpolation', ''),
    ((0x0374, 0x0378), 'logic op enable / op: raster operation instead of blending', ''),
    ((0x1828, 0x182C), 'front/back polygon mode: fill, line (wireframe) or point', ''),
    ((0x1838, 0x1838), 'polygon smooth (antialiased edges)', ''),
    ((0x1D7C, 0x1D7C), 'anti-aliasing control (multisample, alpha-to-coverage)', ''),
    ((0x1D80, 0x1D80), 'surface compression (memory format; no direct visual meaning expected)', ''),
    ((0x0900, 0x097C), 'vertex texture units: textures sampled by the vertex program', 'vertex-texture displacement / skinning data (ASSUMED link)'),
    ((0x1FF0, 0x1FF4), 'vertex program input / output masks: which attributes are read and which outputs are written', ''),
    ((0x1FF8, 0x1FF8), 'transform branch bits: static branch conditions of the vertex program', 'wrong vertex-program branch taken (ASSUMED link)'),
    ((0x1EE0, 0x1EE8), 'point size / point sprite control', ''),
    ((0x03B8, 0x03BC), 'line width / line smooth', ''),
    ((0x1478, 0x1478), 'user clip plane control: enables per-plane clipping by the VP clip outputs', ''),
    ((0x0B00, 0x0B3C), 'texture CONTROL2 per unit (VERIFY exact bits)', ''),
    ((0x0B40, 0x0B64), 'texture coordinate control per texcoord (VERIFY exact bits)', ''),
    ((0x1FEC, 0x1FEC), 'no-paranoid texture fetches (cache behaviour; no direct visual meaning expected)', ''),
    ((0x0238, 0x023C), 'cylindrical texture-coordinate wrap', ''),
    ((0x1DA4, 0x1DA4), 'clip-id test enable', ''),
    ((0x1A00, 0x1BFC), 'fragment texture unit state', ''),
    ((0x1C00, 0x1CFC), 'constant vertex attribute values (used when an array is disabled)', ''),
]


def impact(m):
    for (a, b), mean, bug in IMPACT:
        if a <= m <= b:
            return mean, bug
    return '', ''


def u2f(v):
    return struct.unpack('<f', struct.pack('<I', v & 0xFFFFFFFF))[0]


def decode(m, v):
    if m in FLOAT_METHODS:
        return f'{u2f(v):.6g}'
    if m in ENUM_METHODS and v in GL_ENUM:
        return f'0x{v:X} {GL_ENUM[v]}'
    if m == 0x1D78:
        bits = [n for b, n in ((0x1, 'clip'), (0x10, 'clamp'), (0x100, 'ignoreW')) if v & b]
        return f'0x{v:X} ({"+".join(bits) or "none"}; bit names VERIFY)'
    if m in (0x0A00, 0x0A04, 0x08C0, 0x08C4, 0x0200, 0x0204):
        return f'{v & 0xFFFF}+{v >> 16}'
    if m == 0x173C:
        return str(v)
    return f'0x{v:08X}'


def load_census(path):
    meta, rows, watch, draws = {}, {}, {}, []
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line.startswith('# start_sec'):
            for kv in line[2:].split():
                k, _, v = kv.partition('=')
                meta[k] = v
        elif line.startswith('M,'):
            p = line.split(',')
            m = int(p[1], 16)
            rows[m] = dict(method=m, writes_win=int(p[2]), writes_total=int(p[3]), ndist=int(p[4]), dist_over=int(p[5]),
                           first_ever=int(p[6], 16), first_win=int(p[7], 16), last=int(p[8], 16), ref_kind=p[9],
                           ref=int(p[10], 16), draws_nondef=int(p[11]), draws_seen=int(p[12]),
                           values=[int(x, 16) for x in p[13].split(';') if x])
        elif line.startswith('W,'):
            _, b, m = line.split(',')
            watch[int(b)] = int(m, 16)
        elif line.startswith('D,'):
            _, fr, idx, mask = line.split(',')
            draws.append((int(fr), int(idx), int(mask, 16)))
    return meta, rows, watch, draws


def load_methlog(path):
    """PARTIAL: [METHLOG] m=0x.... d=0x........ lines (value changes only, capped)."""
    rows = {}
    rx = re.compile(r'\[METHLOG\]\s+m=0x([0-9A-Fa-f]+)\s+d=0x([0-9A-Fa-f]+)')
    n = 0
    for line in open(path, encoding='utf-8', errors='replace'):
        mm = rx.search(line)
        if not mm:
            continue
        n += 1
        m, v = int(mm.group(1), 16), int(mm.group(2), 16)
        r = rows.setdefault(m, dict(method=m, writes_win=0, writes_total=0, ndist=0, dist_over=0, first_ever=v, first_win=v,
                                    last=v, ref_kind='F', ref=v, draws_nondef=None, draws_seen=None, values=[]))
        r['writes_total'] += 1; r['writes_win'] += 1; r['last'] = v
        if v not in r['values']:
            if len(r['values']) < 8:
                r['values'].append(v)
            else:
                r['dist_over'] = 1
        r['ndist'] = len(r['values'])
    return dict(source=path, methlog_lines=str(n)), rows


def ranges(idxs):
    idxs = sorted(set(idxs)); out = []
    for i in idxs:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return ', '.join(f'#{a}' if a == b else f'#{a}-{b}' for a, b in out)


def build(rows, cov, meta, watch, draws, partial):
    cm = cov.get('methods', {}) if cov else {}
    ents = []
    for m, r in rows.items():
        c = cm.get(f'0x{m:04X}', {})
        name = c.get('name') or ''
        if not name:
            sys.path.insert(0, HERE)
            try:
                import nv4097_names
                name = nv4097_names.public_name(m)[0] or ''
            except Exception:
                pass
        cls = c.get('cls', 'unhandled' if cm else 'unknown (no coverage.json)')
        mean, bug = impact(m)
        e = dict(r)
        e.update(name=name, cls=cls, label=c.get('label', ''), note=c.get('note', ''), meaning=mean, bug=bug,
                 samples=', '.join(decode(m, v) for v in r['values'][:4]) + (' ...' if r['dist_over'] or len(r['values']) > 4 else ''),
                 ref_dec=decode(m, r['ref']))
        ents.append(e)
    key = (lambda e: (-(e['writes_total'] or 0), e['method'])) if partial else \
          (lambda e: (-(e['draws_nondef'] or 0), -(e['draws_seen'] or 0), -e['writes_win'], e['method']))
    gaps = sorted([e for e in ents if e['cls'] in ('unhandled', 'stored-but-unused')], key=key)
    handled = sorted([e for e in ents if e['cls'] not in ('unhandled', 'stored-but-unused')], key=key)
    # per-draw view for watched methods (frame 0 of the window)
    per = {}
    if draws:
        f0 = min(d[0] for d in draws)
        for fr, idx, mask in draws:
            if fr != f0:
                continue
            for b, m in watch.items():
                if mask >> b & 1:
                    per.setdefault(m, []).append(idx)
    return gaps, handled, per


AR = {
    'title': 'تعداد أوامر RSX اللي ما نستعملها',
    'summary': 'الملخص',
    'gaps': 'الأوامر الناقصة مرتبة حسب عدد الرسومات المتأثرة',
    'handled': 'أوامر مدعومة (للمقارنة)',
    'perdraw': 'أي رسمة تأثرت بأي أمر (أول فريم)',
    'limits': 'حدود هذا التقرير',
}


def md_table(es, partial):
    h = ('| # | method | name | class | writes (window/total) | distinct | draws affected | draws after first write | reference | sample values (decoded) | register meaning (KNOWN) | open-bug link (ASSUMED) |\n'
         '|---|---|---|---|---|---|---|---|---|---|---|---|')
    L = [h]
    for i, e in enumerate(es, 1):
        da = 'n/a (partial)' if e['draws_nondef'] is None else str(e['draws_nondef'])
        ds = 'n/a' if e['draws_seen'] is None else str(e['draws_seen'])
        ref = f"{'reset' if e['ref_kind'] == 'D' else 'first value'} {e['ref_dec']}"
        L.append(f"| {i} | 0x{e['method']:04X} | {e['name']} | {e['cls']} | {e['writes_win']}/{e['writes_total']} | "
                 f"{e['ndist']}{'+' if e['dist_over'] else ''} | **{da}** | {ds} | {ref} | {e['samples']} | {e['meaning']} | {e['bug']} |")
    return '\n'.join(L)


def write_reports(out, title, meta, gaps, handled, per, partial, cov, src_label):
    os.makedirs(out, exist_ok=True)
    L = [f'# {AR["title"]}', f'## RSX method census: {title}', '']
    if partial:
        L.append(f'**PARTIAL.** Built from a `[METHLOG]` change log ({src_label}), not from RSX_CENSUS. It only sees the methods '
                 'that log watched, only value changes, and has no draw counts. Do not rank fixes from it.\n')
    L.append(f'## {AR["summary"]} / Summary\n')
    for k, v in meta.items():
        L.append(f'- {k}: {v}')
    if cov:
        L.append(f"- coverage.json generated {cov['meta']['generated']} from backend "
                 f"{[k for k in cov['meta']['sources'] if 'backend' in k][0]}")
    L.append(f'- methods seen: {len(gaps) + len(handled)}; not handled on the legacy D3D12 path: {len(gaps)}')
    L.append('\n"draws affected" = draws issued in the window while the method held a value different from its reference '
             '(the reset default when known, else the first value the game wrote). A method set once at boot to a '
             'non-default value and never changed shows 0 here when its default is unknown; check "draws after first write" and the reference column for those.\n')
    L.append(f'## {AR["gaps"]} / Gaps ranked by draws affected\n')
    L.append(md_table(gaps, partial) if gaps else '_none seen_')
    L.append(f'\n## {AR["perdraw"]} / Per-draw view (watched methods, first window frame)\n')
    if per:
        L.append('| method | name | draws (DRAW_LIST numbering) |\n|---|---|---|')
        names = {e['method']: e['name'] for e in gaps + handled}
        for m, idx in sorted(per.items(), key=lambda kv: -len(kv[1])):
            L.append(f'| 0x{m:04X} | {names.get(m, "")} | {len(idx)}: {ranges(idx)} |')
    else:
        L.append('_no per-draw records_' if not partial else '_not available in partial mode_')
    L.append(f'\n## {AR["handled"]} / Handled methods (context, top 40)\n')
    L.append(md_table(handled[:40], partial) if handled else '_none_')
    L.append(f'\n## {AR["limits"]} / Limits\n')
    L.append('- Classes come from a static scan (coverage.md); ASSUMED unless marked KNOWN.\n'
             '- Vertex-program microcode and constant runs that take the rsx_process_vp_run fast path never reach rsx_process_method, so their write counts are low or zero. They are handled methods; this does not affect the gap ranking.\n'
             '- "Register meaning" is what the register does. The open-bug link column is a hypothesis to test, not a cause.')
    md = '\n'.join(L) + '\n'
    open(os.path.join(out, 'report.md'), 'w', encoding='utf-8').write(md)
    # html
    def row(e, i):
        da = 'n/a' if e['draws_nondef'] is None else e['draws_nondef']
        cls_color = {'unhandled': '#c62828', 'stored-but-unused': '#ef6c00'}.get(e['cls'], '#2e7d32')
        cells = [i, f"0x{e['method']:04X}", e['name'], f'<span style="color:{cls_color};font-weight:600">{html.escape(e["cls"])}</span>',
                 f"{e['writes_win']}/{e['writes_total']}", f"{e['ndist']}{'+' if e['dist_over'] else ''}", f'<b>{da}</b>',
                 'n/a' if e['draws_seen'] is None else e['draws_seen'],
                 html.escape(('reset ' if e['ref_kind'] == 'D' else 'first ') + e['ref_dec']), html.escape(e['samples']),
                 html.escape(e['meaning']), html.escape(e['bug'])]
        return '<tr>' + ''.join(f'<td>{c if isinstance(c, str) and c.startswith("<") else html.escape(str(c))}</td>' for c in cells) + '</tr>'
    hdr = ''.join(f'<th>{h}</th>' for h in ['#', 'method', 'name', 'class', 'writes win/total', 'distinct', 'draws affected',
                                             'draws after first write', 'reference', 'sample values', 'register meaning (KNOWN)', 'open-bug link (ASSUMED)'])
    H = ['<!doctype html><html><head><meta charset="utf-8"><title>RSX census</title><style>',
         'body{font-family:system-ui,Segoe UI,Arial;margin:24px;color:#222}table{border-collapse:collapse;font-size:12px}',
         'td,th{border:1px solid #ccc;padding:3px 6px;vertical-align:top}th{background:#f3f3f3}h1,h2{margin-top:28px}',
         '.ar{direction:rtl;font-size:1.15em}.warn{background:#fff3e0;padding:8px;border-left:4px solid #ef6c00}</style></head><body>',
         f'<h1 class="ar">{AR["title"]}</h1><h2>RSX method census: {html.escape(title)}</h2>']
    if partial:
        H.append(f'<p class="warn"><b>PARTIAL.</b> From a [METHLOG] change log ({html.escape(src_label)}); value changes of the methods that log watched, no draw counts. Not for ranking fixes.</p>')
    H.append(f'<h2><span class="ar">{AR["summary"]}</span> / Summary</h2><ul>' + ''.join(f'<li>{html.escape(k)}: {html.escape(str(v))}</li>' for k, v in meta.items()) +
             f'<li>methods seen: {len(gaps) + len(handled)}; not handled on the legacy path: {len(gaps)}</li></ul>')
    H.append(f'<h2><span class="ar">{AR["gaps"]}</span> / Gaps ranked by draws affected</h2><table><tr>{hdr}</tr>' +
             ''.join(row(e, i) for i, e in enumerate(gaps, 1)) + '</table>')
    H.append(f'<h2><span class="ar">{AR["perdraw"]}</span> / Per-draw view</h2>')
    if per:
        names = {e['method']: e['name'] for e in gaps + handled}
        H.append('<table><tr><th>method</th><th>name</th><th>draws (DRAW_LIST numbering)</th></tr>' +
                 ''.join(f'<tr><td>0x{m:04X}</td><td>{html.escape(names.get(m, ""))}</td><td>{len(ix)}: {html.escape(ranges(ix))}</td></tr>'
                         for m, ix in sorted(per.items(), key=lambda kv: -len(kv[1]))) + '</table>')
    else:
        H.append('<p>none</p>')
    H.append(f'<h2><span class="ar">{AR["handled"]}</span> / Handled (context, top 40)</h2><table><tr>{hdr}</tr>' +
             ''.join(row(e, i) for i, e in enumerate(handled[:40], 1)) + '</table>')
    H.append(f'<h2><span class="ar">{AR["limits"]}</span> / Limits</h2><p>Classes are from a static scan (ASSUMED unless KNOWN). '
             'VP microcode/constant fast-path runs are not counted. Register meaning is what the register does; the bug link is a hypothesis.</p></body></html>')
    open(os.path.join(out, 'report.html'), 'w', encoding='utf-8').write('\n'.join(H))
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('census', nargs='?')
    ap.add_argument('--methlog')
    ap.add_argument('--coverage', default=os.path.join(HERE, 'coverage.json'))
    ap.add_argument('--out', default='.')
    ap.add_argument('--title', default='')
    a = ap.parse_args()
    cov = json.load(open(a.coverage)) if a.coverage and os.path.exists(a.coverage) else None
    if a.methlog:
        meta, rows = load_methlog(a.methlog); watch, draws = {}, []; partial = True; src = a.methlog
    else:
        meta, rows, watch, draws = load_census(a.census); partial = False; src = a.census
    gaps, handled, per = build(rows, cov, meta, watch, draws, partial)
    write_reports(a.out, a.title or os.path.basename(src), meta, gaps, handled, per, partial, cov, src)
    print(f'{len(gaps)} gap methods, {len(handled)} handled; wrote {a.out}/report.md and report.html')
    for e in gaps[:12]:
        print(f"  0x{e['method']:04X} {e['name']:40s} {e['cls']:18s} draws_affected={e['draws_nondef']} writes={e['writes_win']}/{e['writes_total']} [{e['samples']}]")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""apply_census.py -- insert the RSX_CENSUS log-only hook into Salem's tree.

Dry run by default (prints a unified diff). --write edits the files in place
and keeps a .census.bak copy next to each. Idempotent: lines already present
are not added twice. Run it on a TEST COPY of the tree, not the main one.

  python apply_census.py --video <tree>/ps3recomp/libs/video            (diff only)
  python apply_census.py --video <tree>/ps3recomp/libs/video --write    (apply)
  python apply_census.py --video <tree>/ps3recomp/libs/video --revert   (restore .census.bak)
"""
import argparse, difflib, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = 'RSX_CENSUS (log-only)'

EDITS = {
    'rsx_commands.c': [
        # (anchor regex, where, text)
        (r'^int rsx_process_method\(rsx_state\* state, u32 method, u32 data\)\s*$', 'before',
         '#include "rsx_census_hook.inc"   /* ' + TAG + ' */'),
        (r'^\s*\{ unsigned _p = g_sf_rsx_ring_pos\+\+ & 511u;.*$', 'after',
         '    if (s_rsxc_mode) rsx_census_method(method, data);   /* ' + TAG + ' */'),
    ],
    'rsx_d3d12_backend.c': [
        (r'^\s*u32 idx = s_sf_fdraw\+\+;\s*$', 'after',
         '    { extern void rsx_census_draw(unsigned); rsx_census_draw(idx); }   /* ' + TAG + ' */'),
        (r'^static void sf_draw_gate_frame\(void\)\s*$', 'after+1',
         '    { extern void rsx_census_frame(void); rsx_census_frame(); }   /* ' + TAG + ' */'),
    ],
}


def patch_text(src, edits):
    lines = src.splitlines(keepends=True)
    nl = '\r\n' if '\r\n' in src else '\n'
    for rx, where, text in edits:
        if any(text.strip() == l.strip() for l in lines):
            continue
        hits = [i for i, l in enumerate(lines) if re.match(rx, l.rstrip('\r\n'))]
        if len(hits) != 1:
            raise SystemExit(f'anchor {rx!r}: {len(hits)} matches (need exactly 1) -- paste by hand, see README')
        i = hits[0]
        if where == 'before':
            pos = i
        elif where == 'after':
            pos = i + 1
        else:  # after+1: after the opening brace line that follows the anchor
            if lines[i + 1].strip() != '{':
                raise SystemExit(f'expected "{{" after {lines[i].strip()}')
            pos = i + 2
        lines.insert(pos, text + nl)
    return ''.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', required=True, help='folder holding rsx_commands.c and rsx_d3d12_backend.c')
    ap.add_argument('--backend', default='rsx_d3d12_backend.c')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--revert', action='store_true')
    a = ap.parse_args()
    files = {'rsx_commands.c': 'rsx_commands.c', 'rsx_d3d12_backend.c': a.backend}
    if a.revert:
        for f in files.values():
            p = os.path.join(a.video, f)
            if os.path.exists(p + '.census.bak'):
                shutil.copy2(p + '.census.bak', p); print('restored', p)
        inc = os.path.join(a.video, 'rsx_census_hook.inc')
        if os.path.exists(inc):
            os.remove(inc); print('removed', inc)
        return
    for key, f in files.items():
        p = os.path.join(a.video, f)
        src = open(p, encoding='utf-8', errors='surrogateescape', newline='').read()
        new = patch_text(src, EDITS[key])
        if new == src:
            print(f'{p}: already patched'); continue
        sys.stdout.writelines(difflib.unified_diff(src.splitlines(True), new.splitlines(True), p, p + ' (census)'))
        if a.write:
            shutil.copy2(p, p + '.census.bak')
            open(p, 'w', encoding='utf-8', errors='surrogateescape', newline='').write(new)
            print(f'patched {p} (backup {p}.census.bak)')
    if a.write:
        shutil.copy2(os.path.join(HERE, 'census_hook.c'), os.path.join(a.video, 'rsx_census_hook.inc'))
        print('copied census_hook.c ->', os.path.join(a.video, 'rsx_census_hook.inc'))


if __name__ == '__main__':
    main()

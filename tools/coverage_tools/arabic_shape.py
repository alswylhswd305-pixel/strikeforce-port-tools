#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Minimal Arabic shaping + visual reordering (own code, no dependencies).

Pillow on this PC has no libraqm, so Arabic drawn as-is comes out as separate,
left-to-right letters. shape_visual(text) returns the text in Arabic
Presentation Forms, in visual (left-to-right) order, ready for ImageDraw.text()
or a console that does no bidi. Latin/digit runs keep their own order.
"""
# letter: (isolated, final, initial, medial); None = the letter does not join to the next one
_F = {
 'ء': (0xFE80, None, None, None),
 'آ': (0xFE81, 0xFE82, None, None), 'أ': (0xFE83, 0xFE84, None, None),
 'ؤ': (0xFE85, 0xFE86, None, None), 'إ': (0xFE87, 0xFE88, None, None),
 'ئ': (0xFE89, 0xFE8A, 0xFE8B, 0xFE8C), 'ا': (0xFE8D, 0xFE8E, None, None),
 'ب': (0xFE8F, 0xFE90, 0xFE91, 0xFE92), 'ة': (0xFE93, 0xFE94, None, None),
 'ت': (0xFE95, 0xFE96, 0xFE97, 0xFE98), 'ث': (0xFE99, 0xFE9A, 0xFE9B, 0xFE9C),
 'ج': (0xFE9D, 0xFE9E, 0xFE9F, 0xFEA0), 'ح': (0xFEA1, 0xFEA2, 0xFEA3, 0xFEA4),
 'خ': (0xFEA5, 0xFEA6, 0xFEA7, 0xFEA8), 'د': (0xFEA9, 0xFEAA, None, None),
 'ذ': (0xFEAB, 0xFEAC, None, None), 'ر': (0xFEAD, 0xFEAE, None, None),
 'ز': (0xFEAF, 0xFEB0, None, None), 'س': (0xFEB1, 0xFEB2, 0xFEB3, 0xFEB4),
 'ش': (0xFEB5, 0xFEB6, 0xFEB7, 0xFEB8), 'ص': (0xFEB9, 0xFEBA, 0xFEBB, 0xFEBC),
 'ض': (0xFEBD, 0xFEBE, 0xFEBF, 0xFEC0), 'ط': (0xFEC1, 0xFEC2, 0xFEC3, 0xFEC4),
 'ظ': (0xFEC5, 0xFEC6, 0xFEC7, 0xFEC8), 'ع': (0xFEC9, 0xFECA, 0xFECB, 0xFECC),
 'غ': (0xFECD, 0xFECE, 0xFECF, 0xFED0), 'ف': (0xFED1, 0xFED2, 0xFED3, 0xFED4),
 'ق': (0xFED5, 0xFED6, 0xFED7, 0xFED8), 'ك': (0xFED9, 0xFEDA, 0xFEDB, 0xFEDC),
 'ل': (0xFEDD, 0xFEDE, 0xFEDF, 0xFEE0), 'م': (0xFEE1, 0xFEE2, 0xFEE3, 0xFEE4),
 'ن': (0xFEE5, 0xFEE6, 0xFEE7, 0xFEE8), 'ه': (0xFEE9, 0xFEEA, 0xFEEB, 0xFEEC),
 'و': (0xFEED, 0xFEEE, None, None), 'ى': (0xFEEF, 0xFEF0, None, None),
 'ي': (0xFEF1, 0xFEF2, 0xFEF3, 0xFEF4),
 'پ': (0xFB56, 0xFB57, 0xFB58, 0xFB59), 'چ': (0xFB7A, 0xFB7B, 0xFB7C, 0xFB7D),
 'گ': (0xFB92, 0xFB93, 0xFB94, 0xFB95), 'ڤ': (0xFB6A, 0xFB6B, 0xFB6C, 0xFB6D),
}
_LAM_ALEF = {'ا': (0xFEFB, 0xFEFC), 'أ': (0xFEF7, 0xFEF8), 'إ': (0xFEF9, 0xFEFA), 'آ': (0xFEF5, 0xFEF6)}
_HARAKAT = set(chr(c) for c in range(0x064B, 0x0653)) | {'\u0670'}
_TATWEEL = '\u0640'


def _joins_next(ch):   # can this letter connect to the following letter?
    f = _F.get(ch)
    return ch == _TATWEEL or (f is not None and f[2] is not None)


def _joins_prev(ch):
    return ch == _TATWEEL or (ch in _F and _F[ch][1] is not None)


def shape(text):
    """Logical-order text -> logical-order presentation forms."""
    s = [c for c in text if c not in _HARAKAT]
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c not in _F:
            out.append(c); i += 1; continue
        prev = s[i - 1] if i > 0 else ''
        con_prev = bool(prev) and _joins_next(prev) and _joins_prev(c)
        if c == 'ل' and i + 1 < len(s) and s[i + 1] in _LAM_ALEF:
            iso, fin = _LAM_ALEF[s[i + 1]]
            out.append(chr(fin if con_prev else iso)); i += 2; continue
        nxt = s[i + 1] if i + 1 < len(s) else ''
        con_next = bool(nxt) and _joins_next(c) and _joins_prev(nxt)
        iso, fin, ini, med = _F[c]
        if con_prev and con_next: g = med
        elif con_prev: g = fin
        elif con_next: g = ini
        else: g = iso
        out.append(chr(g or iso)); i += 1
    return ''.join(out)


def _is_rtl(ch):
    o = ord(ch)
    return 0x0590 <= o <= 0x08FF or 0xFB1D <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF


def _is_ltr(ch):
    return ch.isascii() and (ch.isalnum() or ch in '%.')


_MIRROR = {'(': ')', ')': '(', '[': ']', ']': '[', '<': '>', '>': '<', '{': '}', '}': '{'}


def shape_visual(text):
    """Shape and put in visual order for a paragraph whose base direction is RTL
    (if the text has any Arabic letter) or LTR (otherwise: returned unchanged)."""
    if not any(_is_rtl(c) for c in text):
        return text
    t = shape(text)
    # split into runs: strong LTR runs (latin/digits plus the neutrals between them) vs everything else
    runs, cur, cur_ltr = [], '', None
    i = 0
    while i < len(t):
        c = t[i]
        if _is_ltr(c):
            kind = True
        elif _is_rtl(c):
            kind = False
        else:  # neutral: stays in an LTR run only if more LTR follows before any RTL char
            kind = False
            if cur_ltr:
                j = i
                while j < len(t) and not _is_ltr(t[j]) and not _is_rtl(t[j]):
                    j += 1
                if j < len(t) and _is_ltr(t[j]):
                    kind = True
        if cur_ltr is None or kind == cur_ltr:
            cur += c
        else:
            runs.append((cur_ltr, cur)); cur = c
        cur_ltr = kind
        i += 1
    if cur:
        runs.append((cur_ltr, cur))
    vis = []
    for ltr, r in reversed(runs):
        vis.append(r if ltr else ''.join(_MIRROR.get(ch, ch) for ch in reversed(r)))
    return ''.join(vis)


if __name__ == '__main__':
    import sys
    for a in sys.argv[1:] or ['الأرض بيضاء بدل تراب 238', 'لا يوجد', 'وجه الحارس غامق']:
        print(shape_visual(a))

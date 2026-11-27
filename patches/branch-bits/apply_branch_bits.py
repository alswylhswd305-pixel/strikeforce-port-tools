#!/usr/bin/env python3
"""Apply / revert the VP branch-bits root fix (proposal) on a TEST COPY of libs/video.

  python apply_branch_bits.py --video C:\\<test-copy>\\ps3recomp\\libs\\video            (dry run: prints the diff)
  python apply_branch_bits.py --video ... --write    (applies; keeps <file>.bb.bak)
  python apply_branch_bits.py --video ... --revert   (restores the .bb.bak copies)
  python apply_branch_bits.py --backend <file> ...   (patch a backend file with another name, e.g. sh_work.c)

Every anchor must match exactly once, or nothing is written. Line endings are kept
per anchor (the backend has mixed CRLF/LF). Re-running on a patched file is a no-op.
"""
import argparse, difflib, os, shutil, sys

DECOMP_C = [(
'''    return 0;
}

/* BRA BRI CAL CLI RET BRB CLB (scalar opcodes). */''',
'''    return 0;
}

/* The transform branch bits a program actually tests: bit D3[23:27] of every
 * BRB/CLB up to the end bit. A caller that bakes the outcomes (see BRB below)
 * keys the compiled program on (bits & mask), so a program with no BRB/CLB
 * keeps its old key and bits it never tests do not multiply variants. */
u32 rsx_vp_branch_bits_mask(const u8* ucode, u32 max_bytes)
{
    u32 mask = 0;
    if (!ucode) return 0;
    for (u32 off = 0; off + 16 <= max_bytes; off += 16) {
        const u32 sca_op = (rd_le(ucode + off + 4) >> 27) & 0x1Fu;
        const u32 d3 = rd_le(ucode + off + 12);
        if (sca_op == 0x11 || sca_op == 0x12) mask |= 1u << ((d3 >> 23) & 0x1Fu);   /* BRB, CLB */
        if (d3 & 1u) break;                                                        /* D3.end */
    }
    return mask;
}

/* BRA BRI CAL CLI RET BRB CLB (scalar opcodes). */''')]

DECOMP_H = [(
'''int rsx_vp_uses_branch_bits(const u8* ucode, u32 max_bytes);''',
'''int rsx_vp_uses_branch_bits(const u8* ucode, u32 max_bytes);
/* Mask of the branch bits the program's BRB/CLB test (0 = none). */
u32 rsx_vp_branch_bits_mask(const u8* ucode, u32 max_bytes);''')]

BACKEND = [(
'''static int vp_get_vs(const rsx_state* st)
{''',
'''/* SET_TRANSFORM_BRANCH_BITS (0x1FF8) for this program: the decompiler bakes
 * every BRB/CLB outcome into the HLSL (rsx_vp_decompiler.c s_vp_branch_bits),
 * so the bits the program tests are part of its identity. Only tested bits
 * count; a program with no BRB/CLB, or bits 0, keeps exactly the old key.
 * VP_BRANCH_BITS_OFF=1 restores the old behaviour (bits always 0). */
static u32 vp_branch_key_bits(const rsx_state* st, const u8* vuc, u32 vlen)
{
    extern u32 rsx_vp_branch_bits_mask(const u8*, u32);
    static int off = -1;
    if (off < 0) off = getenv("VP_BRANCH_BITS_OFF") ? 1 : 0;
    if (off || !st) return 0;
    return st->transform_branch_bits & rsx_vp_branch_bits_mask(vuc, vlen);
}

static int vp_get_vs(const rsx_state* st)
{'''), (
'''    u32 hash = vp_hash_ucode(vuc, vlen);
    for (int i = 0; i < s_d3d.vp_vs_n; i++)
        if (s_d3d.vp_vs[i].hash == hash) return i;

    static char hlsl[262144];
    int ni = rsx_vp_decompile(vuc, vlen, hlsl, sizeof hlsl);
    if (ni <= 0) return -1;''',
'''    u32 hash = vp_hash_ucode(vuc, vlen);
    const u32 ucode_hash = hash;
    const u32 vp_bb = vp_branch_key_bits(st, vuc, vlen);
    if (vp_bb) {   /* fold the tested bits into the cache key (and the PSO's vs_hash) */
        for (int k = 0; k < 4; k++) { hash ^= (vp_bb >> (8 * k)) & 0xFFu; hash *= 16777619u; }
        if (!hash) hash = 1u;
    }
    for (int i = 0; i < s_d3d.vp_vs_n; i++)
        if (s_d3d.vp_vs[i].hash == hash) return i;

    static char hlsl[262144];
    { extern void rsx_vp_set_branch_bits(u32); rsx_vp_set_branch_bits(vp_bb); }
    int ni = rsx_vp_decompile(vuc, vlen, hlsl, sizeof hlsl);
    { extern void rsx_vp_set_branch_bits(u32); rsx_vp_set_branch_bits(0); }   /* other callers stay at 0 */
    if (ni <= 0) return -1;
    if (vp_bb) { static int _b = 0; if (PS3_LOG_FIRST(_b, 16))
        fprintf(stderr, "[VPBB] vp 0x%08X branch bits 0x%08X -> key 0x%08X%c", ucode_hash, vp_bb, hash, 10); }'''), (
'''    const u32 h = vp_hash_ucode(vuc, vlen);
    char fn[64];
    snprintf(fn, sizeof fn, "faces_vp_%08X.hlsl", h);''',
'''    const u32 h = vp_hash_ucode(vuc, vlen);
    const u32 bb = vp_branch_key_bits(st, vuc, vlen);
    char fn[64];
    if (bb) snprintf(fn, sizeof fn, "faces_vp_%08X_b%X.hlsl", h, bb);
    else    snprintf(fn, sizeof fn, "faces_vp_%08X.hlsl", h);'''), (
'''        const int ni = rsx_vp_decompile(vuc, vlen, hl, sizeof hl);
        FILE* f = fopen(fn, "w");
        if (f) {
            fprintf(f, "/* vp hash 0x%08X start %u, %d instrs, raw ucode:\\n", h, st->transform_program_start, ni);''',
'''        { extern void rsx_vp_set_branch_bits(u32); rsx_vp_set_branch_bits(bb); }
        const int ni = rsx_vp_decompile(vuc, vlen, hl, sizeof hl);
        { extern void rsx_vp_set_branch_bits(u32); rsx_vp_set_branch_bits(0); }
        FILE* f = fopen(fn, "w");
        if (f) {
            fprintf(f, "/* vp hash 0x%08X start %u, %d instrs, branch bits 0x%08X (0x1FF8 = 0x%08X), raw ucode:\\n",
                    h, st->transform_program_start, ni, bb, st->transform_branch_bits);''')]

def MARK_OF(name):
    return 'static u32 vp_branch_key_bits(' if name not in ('rsx_vp_decompiler.c', 'rsx_vp_decompiler.h') \
        else 'u32 rsx_vp_branch_bits_mask(const u8* ucode, u32 max_bytes)'


def patch_text(src, pairs, name):
    if MARK_OF(name) in src:
        return src, 'already patched'
    out = src
    for old, new in pairs:
        hits = []
        for eol in (('\r\n', '\n') if '\n' in old else ('\n',)):
            o = old.replace('\n', eol)
            if out.count(o) == 1:
                hits.append((o, new.replace('\n', eol)))
            elif out.count(o) > 1:
                raise SystemExit(f'{name}: anchor matches {out.count(o)} times: {old.splitlines()[0]!r}')
        if len(hits) != 1:
            raise SystemExit(f'{name}: anchor not found exactly once: {old.splitlines()[0]!r}')
        out = out.replace(hits[0][0], hits[0][1])
    return out, 'patched'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--video', help='libs/video folder of a TEST COPY')
    ap.add_argument('--backend', help='backend file (default <video>/rsx_d3d12_backend.c)')
    ap.add_argument('--decomp', help='folder with rsx_vp_decompiler.c/.h (default <video>)')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--revert', action='store_true')
    a = ap.parse_args()
    dd = a.decomp or a.video
    be = a.backend or (a.video and os.path.join(a.video, 'rsx_d3d12_backend.c'))
    if not dd or not be:
        ap.error('need --video, or --decomp and --backend')
    jobs = [(os.path.join(dd, 'rsx_vp_decompiler.c'), DECOMP_C),
            (os.path.join(dd, 'rsx_vp_decompiler.h'), DECOMP_H),
            (be, BACKEND)]
    if a.revert:
        for p, _ in jobs:
            if os.path.exists(p + '.bb.bak'):
                shutil.copyfile(p + '.bb.bak', p); os.remove(p + '.bb.bak'); print('restored', p)
            else:
                print('no backup for', p)
        return
    results = []
    for p, pairs in jobs:
        src = open(p, 'rb').read().decode('utf-8', 'surrogateescape')
        new, st = patch_text(src, pairs, os.path.basename(p))
        results.append((p, src, new, st))
    for p, src, new, st in results:
        print(f'== {p}: {st}')
        if new != src:
            sys.stdout.writelines(difflib.unified_diff(src.replace('\r\n', '\n').splitlines(True),
                                  new.replace('\r\n', '\n').splitlines(True), 'a/' + os.path.basename(p), 'b/' + os.path.basename(p)))
    if a.write:
        for p, src, new, st in results:
            if new == src: continue
            if not os.path.exists(p + '.bb.bak'): shutil.copyfile(p, p + '.bb.bak')
            open(p, 'wb').write(new.encode('utf-8', 'surrogateescape'))
            print('wrote', p)
    else:
        print('(dry run: nothing written; add --write)')


if __name__ == '__main__':
    main()

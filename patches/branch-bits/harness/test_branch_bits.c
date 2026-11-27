/* Box harness for the branch-bits fix (log + decompiler only, no D3D12).
 * Builds the PATCHED rsx_vp_decompiler.c and the vp_branch_key_bits() /
 * key-fold logic copied verbatim from the patched backend (extracted by
 * run.sh into key_logic.inc), and checks:
 *   T1  mask of tested bits per dumped VP (6A46C9BA, D54F73A6, 3F083BFF)
 *   T2  bits=0 output == the 1776 dump's HLSL for 6A46C9BA (same decompiler)
 *   T3  bits=0: BRB @14 jumps to 29, block 15..28 (lighting) is unreachable
 *       bits=1: BRB @14 falls through to 15, the lighting block is reached
 *   T4  key: bits 0 or untested bits -> old hash; tested bit -> new key
 *   T5  polarity: synthetic BRB with D3[28]=1 is taken only when the bit is set
 *   T6  CLB: synthetic CLB follows the same bit test (call vs fall-through) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rsx_vp_decompiler.h"

typedef struct { u32 transform_branch_bits; } rsx_state;   /* stub: only the field used */
#include "key_logic.inc"   /* vp_hash_ucode + vp_branch_key_bits + fold, from the patched backend */

static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL: " __VA_ARGS__); printf("\n"); } else { printf("ok:   " __VA_ARGS__); printf("\n"); } } while (0)

static u32 load_dump(const char* path, u8* uc, u32 cap, char** hlsl_out)
{
    FILE* f = fopen(path, "rb"); if (!f) { printf("missing %s\n", path); exit(2); }
    static char buf[1 << 20]; size_t n = fread(buf, 1, sizeof buf - 1, f); buf[n] = 0; fclose(f);
    { size_t w = 0; for (size_t r = 0; r < n; r++) if (buf[r] != '\r') buf[w++] = buf[r]; buf[w] = 0; }   /* dumps are CRLF (Windows text mode) */
    u32 len = 0; char* p = strchr(buf, '\n') + 1;
    while (p && *p == ' ') {                 /* "  NN: XX XX ..." lines */
        char* c = strchr(p, ':'); if (!c) break; c++;
        for (int j = 0; j < 16 && len < cap; j++) uc[len++] = (u8)strtoul(c, &c, 16);
        p = strchr(p, '\n'); if (p) p++;
    }
    char* end = strstr(buf, "*/\n");
    if (!end) { printf("no HLSL body in %s\n", path); exit(2); }
    *hlsl_out = end + 3;
    return len;
}

static void put_le(u8* p, u32 v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

static char out[1 << 19];

int main(int argc, char** argv)
{
    const char* dir = argc > 1 ? argv[1] : ".";
    char path[512];
    static u8 uc[544 * 16];
    char* dumped;

    /* T1 */
    struct { const char* h; u32 want; } m[3] = { {"3F083BFF", 0x7}, {"6A46C9BA", 0x1}, {"D54F73A6", 0x6} };
    for (int i = 0; i < 3; i++) {
        snprintf(path, sizeof path, "%s/faces_vp_%s.hlsl", dir, m[i].h);
        u32 n = load_dump(path, uc, sizeof uc, &dumped);
        u32 got = rsx_vp_branch_bits_mask(uc, n);
        CHECK(got == m[i].want, "T1 %s tested-bit mask 0x%X (want 0x%X), %u instrs", m[i].h, got, m[i].want, n / 16);
    }

    /* T2 / T3 on the prop VP */
    snprintf(path, sizeof path, "%s/faces_vp_6A46C9BA.hlsl", dir);
    u32 n = load_dump(path, uc, sizeof uc, &dumped);
    rsx_vp_set_branch_bits(0);
    int ni = rsx_vp_decompile(uc, n, out, sizeof out);
    FILE* f0 = fopen("out_6A46C9BA_bits0.hlsl", "w"); fputs(out, f0); fclose(f0);
    { size_t a = strlen(out), b = strlen(dumped);   /* the dump adds one "\n" after the body: compare without trailing newlines */
      while (a && out[a-1] == '\n') a--;
      while (b && dumped[b-1] == '\n') b--;
      CHECK(ni == 46 && a == b && !memcmp(out, dumped, a), "T2 bits=0 HLSL identical to the 1776 dump (%d instrs, %zu bytes)", ni, a); }
    CHECK(strstr(out, "/* FLOW BRB @14 -> 29") != NULL, "T3 BRB @14 -> 29 present");
    {   const char* at = strstr(out, "/* FLOW BRB @14"); const char* t = strstr(at, "_pc = ");
        CHECK(t && !strncmp(t, "_pc = 29;", 9), "T3 bits=0: BRB @14 emits '_pc = 29;' (lighting block 15..28 skipped)"); }
    rsx_vp_set_branch_bits(1);
    ni = rsx_vp_decompile(uc, n, out, sizeof out);
    rsx_vp_set_branch_bits(0);
    FILE* f1 = fopen("out_6A46C9BA_bits1.hlsl", "w"); fputs(out, f1); fclose(f1);
    {   const char* at = strstr(out, "/* FLOW BRB @14"); const char* t = strstr(at, "_pc = ");
        CHECK(t && !strncmp(t, "_pc = 15;", 9), "T3 bits=1: BRB @14 emits '_pc = 15;' (falls into the lighting block)");
        CHECK(strstr(out, "if (_pc == 15)") != NULL && strstr(out, "vp_c[466]") != NULL && strstr(out, "vp_c[257]") != NULL,
              "T3 block 15 exists and reads vp_c[466] / vp_c[257]"); }

    /* T4 key logic, copied from the patched backend */
    const u32 base = vp_hash_ucode(uc, n);
    rsx_state st = {0};
    st.transform_branch_bits = 0;          CHECK(key_of(&st, uc, n) == base, "T4 bits=0 -> key == ucode hash 0x%08X (old behaviour)", base);
    st.transform_branch_bits = 0x100;      CHECK(key_of(&st, uc, n) == base, "T4 bits=0x100 (untested) -> key unchanged");
    st.transform_branch_bits = 0x1;        u32 k1 = key_of(&st, uc, n);
    CHECK(k1 != base, "T4 bits=0x1 -> new key 0x%08X", k1);
    st.transform_branch_bits = 0x101;      CHECK(key_of(&st, uc, n) == k1, "T4 bits=0x101 -> same key as 0x1 (only tested bits)");

    /* T5 / T6 synthetic: 0 MOV, 1 BRB/CLB bit 3 -> 3, 2 MOV, 3 MOV (end). D3[28] set. */
    for (int op = 0x11; op <= 0x12; op++) for (int pol = 0; pol <= 1; pol++) {
        static u8 s[4 * 16]; memset(s, 0, sizeof s);
        for (int i = 0; i < 4; i++) {           /* harmless VEC MOV r0 = c0 shape is not needed: */
            put_le(s + i * 16 + 0, 0); put_le(s + i * 16 + 4, 0);
            put_le(s + i * 16 + 8, 0); put_le(s + i * 16 + 12, 0);
        }
        /* flow instr at slot 1: sca_op in D1[27:31], target 3 = D3[29:31]=3, bit index 3 in D3[23:27], pol in D3[28] */
        put_le(s + 16 + 4, (u32)op << 27);
        put_le(s + 16 + 12, (3u << 29) | ((u32)pol << 28) | (3u << 23));
        put_le(s + 3 * 16 + 12, 1u);            /* end */
        for (u32 bits = 0; bits <= 8; bits += 8) {
            rsx_vp_set_branch_bits(bits);
            rsx_vp_decompile(s, sizeof s, out, sizeof out);
            rsx_vp_set_branch_bits(0);
            const char* at = strstr(out, "/* FLOW"); const char* t = at ? strstr(at, "_pc = ") : NULL;
            const char* tc = at ? strstr(at, "_cs[_csp] = ") : NULL;
            const int bit = bits ? 1 : 0, want_taken = (bit == pol);
            int taken = op == 0x11 ? (t && !strncmp(t, "_pc = 3;", 8))
                                   : (tc && tc < strstr(at, "\n    }") && strstr(tc, "_pc = 3;") != NULL);
            CHECK(taken == want_taken, "T%d %s pol(D3[28])=%d bit3=%d -> %s (want %s)", op == 0x11 ? 5 : 6,
                  op == 0x11 ? "BRB" : "CLB", pol, bit, taken ? "taken" : "fall-through", want_taken ? "taken" : "fall-through");
        }
    }
    printf("%s (%d failures)\n", fails ? "BRANCH-BITS HARNESS FAIL" : "BRANCH-BITS HARNESS PASS", fails);
    return fails ? 1 : 0;
}

/* Box-side harness: compiles census_hook.c with stub types and feeds a
 * synthetic NV4097 method stream; asserts the counts. Not part of the game. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned int u32;
typedef unsigned char u8;

static double g_now = 0.0;                       /* fake clock (seconds) */
#define RSX_CENSUS_NOW_SEC() (g_now)
#include "../census_hook.c"

/* Stub of the real entry point: PART B goes at the top, exactly as pasted. */
static int rsx_process_method_stub(u32 method, u32 data)
{
    if (s_rsxc_mode) rsx_census_method(method, data);   /* PART B */
    return 0;
}
static u32 f2u(float f) { u32 u; memcpy(&u, &f, 4); return u; }

/* Stub of sf_draw_gate's frame/draw bookkeeping (PART C sites). */
static unsigned s_fdraw = 0;
static void frame_end(void) { rsx_census_frame(); s_fdraw = 0; }
static void draw(void) { unsigned idx = s_fdraw++; rsx_census_draw(idx); }

static int fails = 0;
#define CHECK(c, ...) do { if (!(c)) { fails++; printf("FAIL: " __VA_ARGS__); printf("\n"); } } while (0)

int main(void)
{
    /* boot-time state, before the window */
    rsx_process_method_stub(0x08CC, 0x2601);           /* fog mode, set once, never again */
    rsx_process_method_stub(0x08D0, f2u(0.5f));
    rsx_process_method_stub(0x0A20, f2u(640.0f));      /* viewport offset x (no default -> first value) */
    rsx_process_method_stub(0x0A30, f2u(640.0f));
    rsx_process_method_stub(0x0A30, f2u(-640.0f));     /* changes before window: ref stays 640 */

    for (int frame = 0; frame < 6; frame++) {
        g_now = frame * 1.0;                           /* 1 s per frame */
        for (int d = 0; d < 10; d++) {
            rsx_process_method_stub(0x0A68, d < 5 ? 1 : 0);         /* poly offset fill on for draws 0-4 */
            rsx_process_method_stub(0x0A78, f2u(1.0f));             /* factor 1.0 always (default 0) */
            rsx_process_method_stub(0x0A7C, f2u(2.0f));
            rsx_process_method_stub(0x1D78, 1);                     /* == default: never counted */
            rsx_process_method_stub(0x1738, d == 7 ? 0x100 : 0);    /* base offset only on draw 7 */
            if (d == 3) rsx_process_method_stub(0x0A20, f2u(320.0f));
            if (d == 6) rsx_process_method_stub(0x0A20, f2u(640.0f));
            for (int k = 0; k < 12; k++) rsx_process_method_stub(0x1A00 + 4 * (k % 8), 0x1000 + k); /* distinct-cap test */
            if (frame == 5 && d == 0) rsx_process_method_stub(0x1EE0, f2u(4.0f)); /* first written inside window */
            if (frame >= 4) rsx_process_method_stub(0x0B00, 0x100u + (u32)(frame * 10 + d)); /* 20 distinct in window */
            rsx_process_method_stub(0xE920, 0);                     /* >= 0x2000 bucket */
            rsx_process_method_stub(0x1808, 5); rsx_process_method_stub(0x1814, 0x02000000);
            draw();
            rsx_process_method_stub(0x1808, 0);
        }
        frame_end();
    }

    /* window opens at the frame end at t=3.0 (RSX_CENSUS=3,2) -> frames 4 and 5 recorded */
    FILE* f = fopen(getenv("RSX_CENSUS_OUT"), "r");
    CHECK(f != NULL, "no output file");
    if (!f) return 1;
    char line[512]; int got = 0;
    unsigned draws = 0;
    while (fgets(line, sizeof line, f)) {
        unsigned m, ww, wt, nd, ov, fe, fw, last, ref, dn, ds; char rk;
        if (sscanf(line, "# start_sec=%*f window_begin_sec=%*f window_end_sec=%*f frames=%*u draws=%u", &draws) == 1) continue;
        if (sscanf(line, "M,0x%x,%u,%u,%u,%u,0x%x,0x%x,0x%x,%c,0x%x,%u,%u", &m, &ww, &wt, &nd, &ov, &fe, &fw, &last, &rk, &ref, &dn, &ds) != 12) continue;
        got++;
        switch (m) {
        case 0x0A68: CHECK(dn == 10 && ww == 20 && rk == 'D', "0A68 draws_nondef=%u writes=%u", dn, ww); break;
        case 0x0A78: CHECK(dn == 20 && nd == 1, "0A78 draws_nondef=%u ndist=%u", dn, nd); break;
        case 0x0A7C: CHECK(dn == 20, "0A7C draws_nondef=%u", dn); break;
        case 0x1D78: CHECK(dn == 0 && ww == 20, "1D78 draws_nondef=%u", dn); break;
        case 0x1738: CHECK(dn == 2 && nd == 2, "1738 draws_nondef=%u ndist=%u", dn, nd); break;
        case 0x08CC: CHECK(dn == 0 && ww == 0 && ds == 20 && rk == 'F' && fw == 0x2601, "08CC dn=%u ww=%u ds=%u", dn, ww, ds); break;
        case 0x0A20: CHECK(dn == 6 && rk == 'F' && nd == 2, "0A20 draws_nondef=%u ndist=%u", dn, nd); break;
        case 0x0A30: CHECK(dn == 20 && ww == 0 && ref == f2u(640.0f), "0A30 draws_nondef=%u (held -640 all window)", dn); break;
        case 0x0B00: CHECK(nd == 8 && ov == 1 && ww == 20, "0B00 ndist=%u overflow=%u", nd, ov); break;
        case 0x1A00: CHECK(nd == 2 && ov == 0, "1A00 ndist=%u", nd); break;
        case 0x1EE0: CHECK(ds == 10 && ww == 1 && dn == 0, "1EE0 draws_seen=%u writes_win=%u", ds, ww); break;
        default: break;
        }
    }
    fclose(f);
    CHECK(draws == 20, "window draws=%u (want 20)", draws);
    CHECK(got >= 10, "only %d M lines", got);
    printf("%s (%d M lines, %u window draws, %d failures)\n", fails ? "HARNESS FAIL" : "HARNESS PASS", got, draws, fails);
    return fails ? 1 : 0;
}

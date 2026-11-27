/* ==========================================================================
 * RSX_CENSUS v1 -- log-only census of NV4097 methods (Strikeforce port).
 *
 * PART A: paste this whole block into libs/video/rsx_commands.c directly
 *         ABOVE the line   int rsx_process_method(rsx_state* state, u32 method, u32 data)
 * PART B: one line inside rsx_process_method (see README).
 * PART C: two lines in rsx_d3d12_backend.c (sf_draw_gate / sf_draw_gate_frame).
 *
 * Env:  RSX_CENSUS=<start_sec>[,<frames>]   (frames default 2, max 600)
 *       RSX_CENSUS_OUT=<path>               (default rsx_census.txt in the cwd)
 * Off (no env): one predictable branch per method, no other work.
 *
 * It only READS (method, data) and writes its own static arrays: it never
 * touches rsx_state, the backend, or guest memory, so rendering is unchanged.
 * Fixed-size arrays only, no heap allocation. One fopen at the end of the window.
 *
 * Per method (0x0000..0x1FFC): writes in the window, writes since boot,
 * first value ever, first value in window, last value, up to 8 distinct values
 * in the window (value held at window start included), and the number of
 * window draws issued while the value != reference. Reference = reset default
 * from the small table below when known, else the first value ever written.
 * Also: draws issued after the method was first written (draws_seen), and a
 * per-draw 64-bit mask of which WATCHED methods were != reference.
 * ========================================================================== */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef RSX_CENSUS_NOW_SEC
/* Same clock DRAW_LIST uses (process age; wall time on Windows' CRT). */
#define RSX_CENSUS_NOW_SEC() ((double)clock() / (double)CLOCKS_PER_SEC)
#endif

#define RSXC_SLOTS      2048u    /* methods 0x0000..0x1FFC, one slot per word */
#define RSXC_NDIST      8u
#define RSXC_MAXDRAWS   16384u   /* per-draw mask records kept */
#define RSXC_NONE       0xFFFFFFFFu

typedef struct {
    unsigned writes_win, writes_total;
    unsigned first_ever, first_win, cur, ref;
    unsigned draws_nondef;   /* window draws while cur != ref                  */
    unsigned nd_since;       /* window draw count when cur last became != ref  */
    unsigned seen_at;        /* window draw count at first write (0 = before)  */
    unsigned dist[RSXC_NDIST];
    unsigned char ndist, dist_over, seen, has_default, nondef, watch_bit;
} rsxc_slot;

typedef struct { unsigned frame, idx; unsigned long long mask; } rsxc_draw_rec;

static rsxc_slot     s_rsxc[RSXC_SLOTS];
static rsxc_draw_rec s_rsxc_draw[RSXC_MAXDRAWS];
/* -1 = env not read yet, 0 = off, 1 = tracking values before the window,
 *  2 = recording, 3 = done (file written). */
static int      s_rsxc_mode = -1;
static double   s_rsxc_start_sec = 0.0, s_rsxc_t_begin = 0.0;
static unsigned s_rsxc_frames = 2, s_rsxc_frames_left = 0, s_rsxc_frame = 0;
static unsigned s_rsxc_wdraws = 0, s_rsxc_nrec = 0, s_rsxc_dropped = 0, s_rsxc_other = 0;
static unsigned long long s_rsxc_watch_now = 0;

/* Reset defaults. KNOWN = seeded the same way in this tree's rsx_dispatch.c
 * (rsx_dispatch_init); ASSUMED = documented NV40/GCM reset state, VERIFY. */
static const struct { unsigned short m; unsigned v; } k_rsxc_defaults[] = {
    { 0x0324, 0x01010101u },  /* COLOR_MASK all on          (KNOWN, rsx_dispatch.c) */
    { 0x1834, 0x00000901u },  /* FRONT_FACE CCW             (KNOWN, rsx_dispatch.c) */
    { 0x1D8C, 0xFFFFFF00u },  /* ZSTENCIL_CLEAR depth 1.0   (KNOWN, rsx_dispatch.c) */
    { 0x1D78, 0x00000001u },  /* ZMIN_MAX_CONTROL clip on   (KNOWN, rsx_dispatch.c) */
    { 0x0A60, 0 }, { 0x0A64, 0 }, { 0x0A68, 0 },   /* POLY_OFFSET_*_ENABLE off (ASSUMED) */
    { 0x0A78, 0 }, { 0x0A7C, 0 },                  /* polygon offset factor/bias 0.0f (ASSUMED) */
    { 0x1738, 0 }, { 0x173C, 0 },                  /* vertex base offset/index 0 (ASSUMED) */
    { 0x0394, 0x00000000u },  /* CLIP_MIN 0.0f (ASSUMED) */
    { 0x0398, 0x3F800000u },  /* CLIP_MAX 1.0f (ASSUMED) */
    { 0x0310, 0 }, { 0x0304, 0 }, { 0x0328, 0 }, { 0x0348, 0 }, { 0x0380, 0 },
    { 0x036C, 0 }, { 0x0374, 0 }, { 0x183C, 0 }, { 0x0A74, 0 }, { 0x1DAC, 0 },  /* enables off (ASSUMED) */
};

/* Methods that get a bit in the per-draw mask (max 64). The static scan
 * (coverage.json) lists these as unhandled or stored-but-unused on the
 * legacy D3D12 path. Bit i = k_rsxc_watch[i]. */
static const unsigned short k_rsxc_watch[] = {
    0x0A60, 0x0A64, 0x0A68, 0x0A78, 0x0A7C,             /* polygon offset            */
    0x08CC, 0x08D0, 0x08D4,                             /* fog mode / params         */
    0x1D78,                                             /* ZMIN_MAX_CONTROL          */
    0x1738, 0x173C,                                     /* vertex base offset/index  */
    0x0A20, 0x0A24, 0x0A30, 0x0A34, 0x0A2C, 0x0A3C,     /* viewport offset/scale x,y,w */
    0x0394, 0x0398,                                     /* clip min/max              */
    0x08C0, 0x08C4,                                     /* scissor                   */
    0x034C, 0x0354, 0x0358,                             /* back stencil wmask/ref/mask */
    0x031C, 0x037C, 0x036C,                             /* blend colour, colour2, MRT blend enable */
    0x0380, 0x0384, 0x0388,                             /* depth bounds              */
    0x0300, 0x0368, 0x0374, 0x0378,                     /* dither, shade mode, logic op */
    0x1828, 0x182C, 0x1838,                             /* polygon mode front/back, poly smooth */
    0x1D7C, 0x1D80,                                     /* anti-aliasing ctl, surface compression */
    0x0B00, 0x0B04, 0x0B40, 0x0B44,                     /* tex control2[0..1], tex coord ctl[0..1] */
    0x0900, 0x090C,                                     /* vertex texture 0 offset / control0 */
    0x1FF0, 0x1FF4, 0x1FF8,                             /* VP input/output mask, branch bits */
    0x1EE0, 0x1EE8, 0x03B8, 0x1478, 0x1FEC,             /* point size/sprite, line width, user clip, no-paranoid */
    0x0238, 0x1DA4,                                     /* cylindrical wrap, clip-id test */
};

static void rsxc_init(void)
{
    const char* e = getenv("RSX_CENSUS");
    unsigned i;
    if (!e || !*e) { s_rsxc_mode = 0; return; }
    s_rsxc_start_sec = atof(e);
    { const char* c = strchr(e, ','); int f = c ? atoi(c + 1) : 2;
      if (f <= 0) f = 2;
      if (f > 600) f = 600;
      s_rsxc_frames = (unsigned)f; }
    for (i = 0; i < RSXC_SLOTS; i++) { s_rsxc[i].watch_bit = 0xFF; s_rsxc[i].seen_at = RSXC_NONE; }
    for (i = 0; i < sizeof k_rsxc_defaults / sizeof k_rsxc_defaults[0]; i++) {
        rsxc_slot* s = &s_rsxc[k_rsxc_defaults[i].m >> 2];
        s->has_default = 1; s->ref = k_rsxc_defaults[i].v;
    }
    for (i = 0; i < sizeof k_rsxc_watch / sizeof k_rsxc_watch[0] && i < 64; i++)
        s_rsxc[k_rsxc_watch[i] >> 2].watch_bit = (unsigned char)i;
    s_rsxc_mode = 1;
    fprintf(stderr, "[CENSUS] armed: window opens at the first frame end after %.1f s, %u frames%c",
            s_rsxc_start_sec, s_rsxc_frames, 10);
}

static void rsxc_dist_add(rsxc_slot* s, unsigned v)
{
    unsigned k;
    for (k = 0; k < s->ndist; k++) if (s->dist[k] == v) return;
    if (s->ndist < RSXC_NDIST) s->dist[s->ndist++] = v; else s->dist_over = 1;
}

static void rsxc_set_nondef(rsxc_slot* s, int nd)
{
    if (nd == (int)s->nondef) return;
    if (s_rsxc_mode == 2) {
        if (nd) s->nd_since = s_rsxc_wdraws;
        else    s->draws_nondef += s_rsxc_wdraws - s->nd_since;
    }
    s->nondef = (unsigned char)nd;
    if (s->watch_bit != 0xFF) {
        const unsigned long long b = 1ull << s->watch_bit;
        s_rsxc_watch_now = nd ? (s_rsxc_watch_now | b) : (s_rsxc_watch_now & ~b);
    }
}

/* PART B calls this:  if (s_rsxc_mode) rsx_census_method(method, data); */
static void rsx_census_method(unsigned m, unsigned v)
{
    rsxc_slot* s;
    if (s_rsxc_mode < 0) rsxc_init();
    if (s_rsxc_mode == 0 || s_rsxc_mode == 3) return;
    if (m >= 0x2000u) { if (s_rsxc_mode == 2) s_rsxc_other++; return; }
    s = &s_rsxc[m >> 2];
    s->writes_total++;
    if (!s->seen) {
        s->seen = 1; s->first_ever = v;
        if (!s->has_default) s->ref = v;
        s->seen_at = (s_rsxc_mode == 2) ? s_rsxc_wdraws : 0;
    }
    s->cur = v;
    if (s_rsxc_mode == 2) {
        if (!s->writes_win) s->first_win = v;
        s->writes_win++;
        rsxc_dist_add(s, v);
    }
    rsxc_set_nondef(s, v != s->ref);
}

static void rsxc_dump(void)
{
    const char* path = getenv("RSX_CENSUS_OUT");
    FILE* f;
    unsigned i;
    if (!path || !*path) path = "rsx_census.txt";
    for (i = 0; i < RSXC_SLOTS; i++) {          /* close open non-default spans */
        rsxc_slot* s = &s_rsxc[i];
        if (s->nondef) { s->draws_nondef += s_rsxc_wdraws - s->nd_since; s->nd_since = s_rsxc_wdraws; }
    }
    f = fopen(path, "w");
    if (!f) { fprintf(stderr, "[CENSUS] cannot open %s%c", path, 10); return; }
    fprintf(f, "# rsx_census v1\n");
    fprintf(f, "# start_sec=%.1f window_begin_sec=%.1f window_end_sec=%.1f frames=%u draws=%u draw_records=%u draw_records_dropped=%u writes_ge_0x2000=%u\n",
            s_rsxc_start_sec, s_rsxc_t_begin, RSX_CENSUS_NOW_SEC(), s_rsxc_frame, s_rsxc_wdraws, s_rsxc_nrec, s_rsxc_dropped, s_rsxc_other);
    fprintf(f, "# M,method,writes_win,writes_total,ndist,dist_overflow,first_ever,first_win,last,ref_kind,ref,draws_nondef,draws_seen,values\n");
    for (i = 0; i < RSXC_SLOTS; i++) {
        const rsxc_slot* s = &s_rsxc[i];
        unsigned k, seen_draws;
        if (!s->seen) continue;
        seen_draws = (s->seen_at == RSXC_NONE) ? 0 : s_rsxc_wdraws - s->seen_at;
        fprintf(f, "M,0x%04X,%u,%u,%u,%u,0x%08X,0x%08X,0x%08X,%c,0x%08X,%u,%u,",
                i << 2, s->writes_win, s->writes_total, s->ndist, s->dist_over, s->first_ever,
                s->writes_win ? s->first_win : s->cur, s->cur, s->has_default ? 'D' : 'F', s->ref,
                s->draws_nondef, seen_draws);
        for (k = 0; k < s->ndist; k++) fprintf(f, "%s0x%08X", k ? ";" : "", s->dist[k]);
        fputc('\n', f);
    }
    for (i = 0; i < sizeof k_rsxc_watch / sizeof k_rsxc_watch[0] && i < 64; i++)
        fprintf(f, "W,%u,0x%04X\n", i, k_rsxc_watch[i]);
    for (i = 0; i < s_rsxc_nrec; i++)
        fprintf(f, "D,%u,%u,0x%016llX\n", s_rsxc_draw[i].frame, s_rsxc_draw[i].idx, s_rsxc_draw[i].mask);
    fprintf(f, "END\n");
    fclose(f);
    fprintf(stderr, "[CENSUS] wrote %s: %u frames, %u draws%c", path, s_rsxc_frame, s_rsxc_wdraws, 10);
}

/* PART C (draw site): call once per backend draw, after the frame check.
 * `idx` = the per-frame draw index (same numbering as DRAW_LIST / DRAW_RANGE). */
void rsx_census_draw(unsigned idx)
{
    if (s_rsxc_mode != 2) return;
    s_rsxc_wdraws++;
    if (s_rsxc_nrec < RSXC_MAXDRAWS) {
        s_rsxc_draw[s_rsxc_nrec].frame = s_rsxc_frame;
        s_rsxc_draw[s_rsxc_nrec].idx = idx;
        s_rsxc_draw[s_rsxc_nrec].mask = s_rsxc_watch_now;
        s_rsxc_nrec++;
    } else s_rsxc_dropped++;
}

/* PART C (frame end): call once per guest frame boundary. */
void rsx_census_frame(void)
{
    unsigned i;
    if (s_rsxc_mode < 0) rsxc_init();
    if (s_rsxc_mode == 1) {
        if (RSX_CENSUS_NOW_SEC() < s_rsxc_start_sec) return;
        for (i = 0; i < RSXC_SLOTS; i++) {           /* open the window */
            rsxc_slot* s = &s_rsxc[i];
            s->ndist = 0; s->dist_over = 0; s->draws_nondef = 0; s->nd_since = 0;
            if (s->seen) { s->seen_at = 0; rsxc_dist_add(s, s->cur); }
        }
        s_rsxc_wdraws = 0; s_rsxc_frame = 0; s_rsxc_frames_left = s_rsxc_frames;
        s_rsxc_t_begin = RSX_CENSUS_NOW_SEC();
        s_rsxc_mode = 2;
        fprintf(stderr, "[CENSUS] window open at %.1f s%c", s_rsxc_t_begin, 10);
        return;
    }
    if (s_rsxc_mode == 2) {
        s_rsxc_frame++;
        if (--s_rsxc_frames_left == 0) { rsxc_dump(); s_rsxc_mode = 3; }
    }
}
/* ======================= end RSX_CENSUS PART A ======================== */

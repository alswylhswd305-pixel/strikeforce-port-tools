/*
 * DIAGNOSTIC ONLY — not a fix (ps3-recomp-playbook L4 / L8 / L12).
 *
 * Neither DRAW_RANGE nor DRAW_DUMP exists in ps3recomp (box study copy of
 * master e85647a, also sf-planD and strikeforce-recomp-repo patches,
 * grepped 2026-11-26). Closest existing knob: DRAW_LIMIT=<N> keeps the
 * first N recorded ops (rsx_d3d12_backend.c:4775-4781). VP_ATTRS, VTX_DUMP
 * and VP_MVP print pieces of state but are capped / deduped and cannot
 * target one draw index with viewport 0x0A20/0x0A30, clip, attrs, fp, RT
 * and c0-c15 in one block.
 *
 * Add these two snippets to libs/video/rsx_d3d12_backend.c, rebuild one
 * diagnostic binary, then run:
 *     python gfx_bisect.py auto --config cfg.json
 * Do not land this in a "keep" build. One change per later real fix (L12).
 */

/* ------------------------------------------------------------------ */
/* 1. DRAW_RANGE=a-b  — insert immediately AFTER the DRAW_LIMIT block */
/*    at rsx_d3d12_backend.c:4775-4781 (study copy / e85647a).        */
/*    Clears are always kept so a mid-range window is not rejected    */
/*    by stale depth. Indices are the original recorded slots before  */
/*    this compact.                                                   */
/* ------------------------------------------------------------------ */

    /* DRAW_RANGE=a-b: keep only recorded ops whose original index is in
     * [a, b] inclusive, plus every clear. Diagnostic only — gfx_bisect.py.
     * Not a fix. */
    { static int rlo = -2, rhi = -2;
      if (rlo == -2) {
        const char* e = getenv("DRAW_RANGE");
        rlo = rhi = -1;
        if (e) {
          unsigned a = 0, b = 0;
          if (sscanf(e, "%u-%u", &a, &b) == 2) { rlo = (int)a; rhi = (int)b; }
        }
      }
      if (rlo >= 0 && rhi >= rlo && s_d3d.draw_count) {
        u32 keep = 0;
        for (u32 _d = 0; _d < s_d3d.draw_count && _d < MAX_DRAWS; _d++) {
            if (!s_d3d.draws[_d].is_clear &&
                ((int)_d < rlo || (int)_d > rhi))
                continue;
            if (keep != _d) s_d3d.draws[keep] = s_d3d.draws[_d];
            keep++;
        }
        s_d3d.draw_count = keep;
      } }

/* ------------------------------------------------------------------ */
/* 2. DRAW_DUMP=N — insert at the END of vp_record_cb()                */
/*    (rsx_d3d12_backend.c ~3499). That function already runs at      */
/*    record time with the live rsx_state and the per-draw constant    */
/*    bank, and `slot` is the original draw index. Do NOT dump from    */
/*    the pre-submit loop: current_rsx_state there is the last draw.   */
/*    Print a few in-stage frames (uncap if a log says "never").       */
/* ------------------------------------------------------------------ */

    /* DRAW_DUMP=<N>: machine-parseable state for recorded draw index N.
     * Diagnostic only — gfx_bisect.py. Not a fix. */
    { static int want = -2, dumped = 0;
      if (want == -2) {
        const char* e = getenv("DRAW_DUMP");
        want = e ? atoi(e) : -1;
      }
      if (want >= 0 && (int)slot == want && dumped < 4 && st) {
        dumped++;
        fprintf(stderr, "[DRAWDUP] begin draw=%u frame=%u\n",
                slot, s_d3d.frame_count);
        fprintf(stderr, "[DRAWDUP] viewport_scale %g %g %g %g\n",
                st->viewport_scale[0], st->viewport_scale[1],
                st->viewport_scale[2], st->viewport_scale[3]);
        fprintf(stderr, "[DRAWDUP] viewport_offset %g %g %g %g\n",
                st->viewport_offset[0], st->viewport_offset[1],
                st->viewport_offset[2], st->viewport_offset[3]);
        fprintf(stderr, "[DRAWDUP] viewport_rect %u %u %u %u\n",
                st->viewport_x, st->viewport_y, st->viewport_w, st->viewport_h);
        fprintf(stderr, "[DRAWDUP] clip_range %g %g\n",
                st->clip_min, st->clip_max);
        /* 0x1D78 is not stored on the legacy backend (PSO DepthClipEnable
         * is never set). Extend this line if you add a state field. */
        fprintf(stderr, "[DRAWDUP] zmin_max_control untracked\n");
        fprintf(stderr, "[DRAWDUP] fp 0x%08X\n",
                dr ? dr->fp_addr : st->shader_program);
        fprintf(stderr, "[DRAWDUP] rt color0=0x%08X zeta=0x%08X format=0x%X w=%u h=%u\n",
                dr ? dr->rt_off : st->surface_color_offset[0],
                dr ? dr->zeta_off : st->surface_zeta_offset,
                dr ? dr->rt_fmt : st->surface_format,
                dr ? dr->rt_w : st->surface_clip_w,
                dr ? dr->rt_h : st->surface_clip_h);
        for (int i = 0; i < 16; i++) {
            const rsx_vertex_attrib* a = &st->vertex_attribs[i];
            if (!a->enabled) continue;
            fprintf(stderr, "[DRAWDUP] attr %d enabled=1 off=0x%X stride=%u size=%u type=%u freq=%u\n",
                    i, a->offset, a->stride, a->size, a->type, a->frequency);
        }
        for (int i = 0; i < 16; i++)
            fprintf(stderr, "[DRAWDUP] c %d %g %g %g %g\n", i,
                    st->vertex_constants[i][0], st->vertex_constants[i][1],
                    st->vertex_constants[i][2], st->vertex_constants[i][3]);
        fprintf(stderr, "[DRAWDUP] end\n");
        fflush(stderr);
      } }

# RSX method coverage, legacy D3D12 path (static)

Generated 2026-11-27T18:52:45 by gen_coverage.py. Classes are mechanical (ASSUMED) unless marked KNOWN; evidence lines are in coverage.json so each one can be VERIFIED.

Sources scanned:

- `/workspace/faces/src/rsx_commands.c` (rsx_commands.c), mtime 2026-11-26T15:29:02, md5 3720caf7
- `/workspace/faces/src/rsx_commands.h` (rsx_commands.h), mtime 2026-11-26T14:14:54, md5 a201ae5f
- `/workspace/faces/sh_work.c` (sh_work.c (backend)), mtime 2026-11-26T20:38:21, md5 c66d52a1
- `/workspace/faces/src/rsx_vertex_fetch.c` (rsx_vertex_fetch.c), mtime 2026-11-25T00:54:10, md5 5bfd9a57
- `/workspace/faces/src/rsx_texture_layout.c` (rsx_texture_layout.c), mtime 2026-11-25T00:54:10, md5 f0abb0a2
- `/workspace/faces/src/rsx_draw_engine.c` (rsx_draw_engine.c), mtime 2026-11-25T00:54:10, md5 0089d181
- `/workspace/faces/src/rsx_dispatch.c` (rsx_dispatch.c), mtime 2026-11-25T00:54:10, md5 b1c5241f
- `/workspace/faces/src/cellGcmSys.c` (cellGcmSys.c), mtime 2026-11-26T12:14:44, md5 4637a727

Path: FIFO walker (cellGcmSys.c gcm_3d_method) -> rsx_process_method -> rsx_state -> D3D12 vtable; draw_engine_enabled=0.

`d3d12_set_viewport` is a TODO no-op at sh_work.c:6661 (KNOWN).

Counts over named or handled offsets: handled 376, stored-but-unused 51, unhandled 371.

## Spot check: known gaps

| method | name | class | label | note |
|---|---|---|---|---|
| 0x0A68 | NV4097_SET_POLY_OFFSET_FILL_ENABLE | **unhandled** | ASSUMED |  |
| 0x0A78 | NV4097_SET_POLYGON_OFFSET_SCALE_FACTOR | **unhandled** | ASSUMED |  |
| 0x0A7C | NV4097_SET_POLYGON_OFFSET_BIAS | **unhandled** | ASSUMED |  |
| 0x08CC | NV4097_SET_FOG_MODE | **unhandled** | ASSUMED |  |
| 0x08D0 | NV4097_SET_FOG_PARAMS[0] | **unhandled** | ASSUMED |  |
| 0x08D4 | NV4097_SET_FOG_PARAMS[1] | **unhandled** | ASSUMED |  |
| 0x1D78 | NV4097_SET_ZMIN_MAX_CONTROL | **unhandled** | ASSUMED |  |
| 0x1738 | NV4097_SET_VERTEX_DATA_BASE_OFFSET | **unhandled** | ASSUMED |  |
| 0x173C | NV4097_SET_VERTEX_DATA_BASE_INDEX | **unhandled** | ASSUMED |  |
| 0x0A20 | NV4097_SET_VIEWPORT_OFFSET.x | **stored-but-unused** | KNOWN | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A24 | NV4097_SET_VIEWPORT_OFFSET.y | **stored-but-unused** | KNOWN | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A28 | NV4097_SET_VIEWPORT_OFFSET.z | **handled** | KNOWN | z lane consumed by the shader epilogue (depth remap) |
| 0x0A2C | NV4097_SET_VIEWPORT_OFFSET.w | **stored-but-unused** | KNOWN | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A30 | NV4097_SET_VIEWPORT_SCALE.x | **stored-but-unused** | KNOWN | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A34 | NV4097_SET_VIEWPORT_SCALE.y | **stored-but-unused** | KNOWN | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A38 | NV4097_SET_VIEWPORT_SCALE.z | **handled** | KNOWN | z lane consumed by the shader epilogue (depth remap) |
| 0x0A3C | NV4097_SET_VIEWPORT_SCALE.w | **stored-but-unused** | KNOWN | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0394 | NV4097_SET_CLIP_MIN | **unhandled** | ASSUMED |  |
| 0x0398 | NV4097_SET_CLIP_MAX | **unhandled** | ASSUMED |  |

## unhandled

| method(s) | name | fields | draw engine knows it | note |
|---|---|---|---|---|
| 0x0000 | NV4097_SET_OBJECT |  |  |  |
| 0x0060 | NV406E_SET_CONTEXT_DMA_SEMAPHORE |  |  |  |
| 0x0100 | NV4097_NO_OPERATION |  | yes |  |
| 0x0110 | NV4097_WAIT_FOR_IDLE (name VERIFY) |  |  |  |
| 0x0184 | NV4097_SET_CONTEXT_DMA_A |  |  |  |
| 0x0188 | NV4097_SET_CONTEXT_DMA_B |  |  |  |
| 0x018C | NV4097_SET_CONTEXT_DMA_COLOR_B |  | yes |  |
| 0x0190 | NV4097_SET_CONTEXT_DMA_STATE (name VERIFY) |  |  |  |
| 0x0194 | NV4097_SET_CONTEXT_DMA_COLOR_A |  | yes |  |
| 0x0198 | NV4097_SET_CONTEXT_DMA_ZETA |  | yes |  |
| 0x019C | NV4097_SET_CONTEXT_DMA_VERTEX_A |  |  |  |
| 0x01A0 | NV4097_SET_CONTEXT_DMA_VERTEX_B |  |  |  |
| 0x01AC | NV4097_SET_CONTEXT_DMA_CLIP_ID |  |  |  |
| 0x01B0 | NV4097_SET_CONTEXT_DMA_CULL_DATA |  |  |  |
| 0x01B4 | NV4097_SET_CONTEXT_DMA_COLOR_C |  | yes |  |
| 0x01B8 | NV4097_SET_CONTEXT_DMA_COLOR_D |  | yes |  |
| 0x0234 | NV4097_INVALIDATE_ZCULL |  |  |  |
| 0x0238 | NV4097_SET_CYLINDRICAL_WRAP (name VERIFY) |  |  |  |
| 0x023C | NV4097_SET_CYLINDRICAL_WRAP1 (name VERIFY) |  |  |  |
| 0x02B8 | NV4097_SET_WINDOW_OFFSET (name VERIFY) |  |  |  |
| 0x02BC | NV4097_SET_WINDOW_CLIP_TYPE (name VERIFY) |  |  |  |
| 0x02C0..0x02FC (16) | NV4097_SET_WINDOW_CLIP_HORIZONTAL[n] (name VERIFY) |  |  |  |
| 0x0300 | NV4097_SET_DITHER_ENABLE |  |  |  |
| 0x031C | NV4097_SET_BLEND_COLOR |  | yes |  |
| 0x0368 | NV4097_SET_SHADE_MODE |  |  |  |
| 0x036C | NV4097_SET_BLEND_ENABLE_MRT |  |  |  |
| 0x0374 | NV4097_SET_LOGIC_OP_ENABLE |  |  |  |
| 0x0378 | NV4097_SET_LOGIC_OP |  |  |  |
| 0x037C | NV4097_SET_BLEND_COLOR2 |  | yes |  |
| 0x0380 | NV4097_SET_DEPTH_BOUNDS_TEST_ENABLE |  | yes |  |
| 0x0384 | NV4097_SET_DEPTH_BOUNDS_MIN |  | yes |  |
| 0x0388 | NV4097_SET_DEPTH_BOUNDS_MAX |  | yes |  |
| 0x0394 | NV4097_SET_CLIP_MIN |  |  |  |
| 0x0398 | NV4097_SET_CLIP_MAX |  |  |  |
| 0x03B0 | NV4097_SET_CONTROL0 (name VERIFY) |  |  |  |
| 0x03B8 | NV4097_SET_LINE_WIDTH |  |  |  |
| 0x03BC | NV4097_SET_LINE_SMOOTH_ENABLE |  |  |  |
| 0x08CC | NV4097_SET_FOG_MODE |  |  |  |
| 0x08D0..0x08D4 (2) | NV4097_SET_FOG_PARAMS[n] |  |  |  |
| 0x0A60 | NV4097_SET_POLY_OFFSET_POINT_ENABLE |  | yes |  |
| 0x0A64 | NV4097_SET_POLY_OFFSET_LINE_ENABLE |  | yes |  |
| 0x0A68 | NV4097_SET_POLY_OFFSET_FILL_ENABLE |  | yes |  |
| 0x0A78 | NV4097_SET_POLYGON_OFFSET_SCALE_FACTOR |  | yes |  |
| 0x0A7C | NV4097_SET_POLYGON_OFFSET_BIAS |  | yes |  |
| 0x0A80..0x0ABC (16) | NV4097_SET_VERTEX_DATA_SCALED4S_M[n] (name VERIFY) |  |  |  |
| 0x0B00..0x0B3C (16) | NV4097_SET_TEXTURE_CONTROL2[n] |  |  |  |
| 0x0B40..0x0B64 (10) | NV4097_SET_TEX_COORD_CONTROL[n] |  |  |  |
| 0x1428 | NV4097_SET_SPECULAR_ENABLE (name VERIFY) |  |  |  |
| 0x142C | NV4097_SET_TWO_SIDE_LIGHT_EN (name VERIFY) |  |  |  |
| 0x1478 | NV4097_SET_USER_CLIP_PLANE_CONTROL (name VERIFY) |  |  |  |
| 0x147C | NV4097_SET_POLYGON_STIPPLE (name VERIFY) |  |  |  |
| 0x1480..0x14FC (32) | NV4097_SET_POLYGON_STIPPLE_PATTERN[n] (name VERIFY) |  |  |  |
| 0x1500..0x15FC (64) | NV4097_SET_VERTEX_DATA3F_M.*[n] |  |  |  |
| 0x1710 | NV4097_INVALIDATE_VERTEX_CACHE_FILE |  |  |  |
| 0x1714 | NV4097_INVALIDATE_VERTEX_FILE |  | yes |  |
| 0x1718 | NV4097_PIPE_NOP (name VERIFY) |  |  |  |
| 0x1738 | NV4097_SET_VERTEX_DATA_BASE_OFFSET |  | yes |  |
| 0x173C | NV4097_SET_VERTEX_DATA_BASE_INDEX |  | yes |  |
| 0x17C8 | NV4097_CLEAR_REPORT_VALUE |  |  |  |
| 0x17CC | NV4097_SET_ZPASS_PIXEL_COUNT_ENABLE |  |  |  |
| 0x1804 | NV4097_SET_ZCULL_STATS_ENABLE |  |  |  |
| 0x180C | NV4097_ARRAY_ELEMENT16 |  |  |  |
| 0x1810 | NV4097_ARRAY_ELEMENT32 |  |  |  |
| 0x1818 | NV4097_INLINE_ARRAY |  | yes |  |
| 0x1828 | NV4097_SET_FRONT_POLYGON_MODE |  |  |  |
| 0x182C | NV4097_SET_BACK_POLYGON_MODE |  |  |  |
| 0x1838 | NV4097_SET_POLY_SMOOTH_ENABLE |  |  |  |
| 0x1880..0x18FC (32) | NV4097_SET_VERTEX_DATA2F_M.*[n] |  |  |  |
| 0x1900..0x193C (16) | NV4097_SET_VERTEX_DATA2S_M[n] (name VERIFY) |  |  |  |
| 0x1940..0x197C (16) | NV4097_SET_VERTEX_DATA4UB_M[n] (name VERIFY) |  |  |  |
| 0x1980..0x19FC (32) | NV4097_SET_VERTEX_DATA4S_M.*[n] (name VERIFY) |  |  |  |
| 0x1D00..0x1D3C (16) | NV4097_SET_COLOR_KEY_COLOR[n] (name VERIFY) |  |  |  |
| 0x1D78 | NV4097_SET_ZMIN_MAX_CONTROL |  | yes |  |
| 0x1D7C | NV4097_SET_ANTI_ALIASING_CONTROL |  |  |  |
| 0x1D80 | NV4097_SET_SURFACE_COMPRESSION |  |  |  |
| 0x1D84 | NV4097_SET_ZCULL_EN (name VERIFY) |  |  |  |
| 0x1D88 | NV4097_SET_SHADER_WINDOW (name VERIFY) |  |  |  |
| 0x1D98 | NV4097_SET_CLEAR_RECT_HORIZONTAL |  |  |  |
| 0x1D9C | NV4097_SET_CLEAR_RECT_VERTICAL |  |  |  |
| 0x1DA4 | NV4097_SET_CLIP_ID_TEST_ENABLE |  |  |  |
| 0x1DB4 | NV4097_SET_LINE_STIPPLE |  |  |  |
| 0x1DB8 | NV4097_SET_LINE_STIPPLE_PATTERN |  |  |  |
| 0x1E40..0x1E7C (16) | NV4097_SET_VERTEX_DATA1F_M[n] |  |  |  |
| 0x1E94 | NV4097_SET_TRANSFORM_EXECUTION_MODE (name VERIFY) |  |  |  |
| 0x1E98 | NV4097_SET_RENDER_ENABLE |  |  |  |
| 0x1EA4 | NV4097_SET_ZCULL_CONTROL0 |  |  |  |
| 0x1EA8 | NV4097_SET_ZCULL_CONTROL1 |  |  |  |
| 0x1EAC | NV4097_SET_SCULL_CONTROL |  |  |  |
| 0x1EE0 | NV4097_SET_POINT_SIZE |  | yes |  |
| 0x1EE4 | NV4097_SET_POINT_PARAMS_ENABLE |  |  |  |
| 0x1EE8 | NV4097_SET_POINT_SPRITE_CONTROL |  |  |  |
| 0x1EF8 | NV4097_SET_TRANSFORM_TIMEOUT (name VERIFY) |  |  |  |
| 0x1FC4 | NV4097_SET_ATTRIB_COLOR (name VERIFY) |  |  |  |
| 0x1FC8 | NV4097_SET_ATTRIB_TEX_COORD (name VERIFY) |  |  |  |
| 0x1FCC | NV4097_SET_ATTRIB_TEX_COORD_EX (name VERIFY) |  |  |  |
| 0x1FD0 | NV4097_SET_ATTRIB_UCLIP0 (name VERIFY) |  |  |  |
| 0x1FD4 | NV4097_SET_ATTRIB_UCLIP1 (name VERIFY) |  |  |  |
| 0x1FE0 | NV4097_SET_REDUCE_DST_COLOR (name VERIFY) |  |  |  |
| 0x1FEC | NV4097_SET_NO_PARANOID_TEXTURE_FETCHES |  |  |  |
| 0xE944 | GCM_DRIVER_FLIP |  | yes |  |

## stored-but-unused

| method(s) | name | fields | draw engine knows it | note |
|---|---|---|---|---|
| 0x020C | NV4097_SET_SURFACE_PITCH_A | surface_color_pitch[] | yes |  |
| 0x021C | NV4097_SET_SURFACE_PITCH_B | surface_color_pitch[] | yes |  |
| 0x022C | NV4097_SET_SURFACE_PITCH_Z | surface_zeta_pitch | yes |  |
| 0x0280 | NV4097_SET_SURFACE_PITCH_C | surface_color_pitch[] | yes |  |
| 0x0284 | NV4097_SET_SURFACE_PITCH_D | surface_color_pitch[] | yes |  |
| 0x034C | NV4097_SET_BACK_STENCIL_MASK | back_stencil_write_mask |  |  |
| 0x0354 | NV4097_SET_BACK_STENCIL_FUNC_REF | back_stencil_ref |  |  |
| 0x0358 | NV4097_SET_BACK_STENCIL_FUNC_MASK | back_stencil_mask |  |  |
| 0x08C0 | NV4097_SET_SCISSOR_HORIZONTAL | scissor_w, scissor_x | yes | backend always sets a full-window scissor; the RSX scissor rect is never applied |
| 0x08C4 | NV4097_SET_SCISSOR_VERTICAL | scissor_h, scissor_y | yes | backend always sets a full-window scissor; the RSX scissor rect is never applied |
| 0x0900..0x097C (32) | NV4097_SET_VERTEX_TEXTURE_*[n] | vertex_textures[].address, vertex_textures[].border_color, vertex_textures[].con | yes |  |
| 0x0A20..0x0A24 (2) | NV4097_SET_VIEWPORT_OFFSET.* | viewport_offset[0], viewport_offset[1] | yes | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A2C | NV4097_SET_VIEWPORT_OFFSET.w | viewport_offset[3] |  | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A30..0x0A34 (2) | NV4097_SET_VIEWPORT_SCALE.* | viewport_scale[0], viewport_scale[1] | yes | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x0A3C | NV4097_SET_VIEWPORT_SCALE.w | viewport_scale[3] |  | shader epilogue uses only the z lane (GL->[0,1] depth remap); x/y/w are forced to identity, so the RSX viewport scale/offset x,y never reach the draw |
| 0x1FF0 | NV4097_SET_VERTEX_ATTRIB_INPUT_MASK | vertex_attrib_input_mask | yes |  |
| 0x1FF4 | NV4097_SET_VERTEX_ATTRIB_OUTPUT_MASK | vertex_attrib_output_mask | yes |  |
| 0x1FF8 | NV4097_SET_TRANSFORM_BRANCH_BITS | transform_branch_bits |  | stored in rsx_state but never handed to the VP decompiler on the legacy path, so BRB/CLB static branches always see bits=0 |

## handled

| method(s) | name | fields | draw engine knows it | note |
|---|---|---|---|---|
| 0x0050 | NV406E_SET_REFERENCE |  |  | acts directly: capture:g_rsx_last_reference |
| 0x0064 | NV406E_SEMAPHORE_OFFSET |  |  | handled in the FIFO walker, not rsx_process_method: cellGcmSys.c:2849 (FIFO walker, before rsx_process_method) |
| 0x0068 | NV406E_SEMAPHORE_ACQUIRE |  |  | handled in the FIFO walker, not rsx_process_method: cellGcmSys.c:2849 (FIFO walker, before rsx_process_method) |
| 0x006C | NV406E_SEMAPHORE_RELEASE |  |  | handled in the FIFO walker, not rsx_process_method: cellGcmSys.c:2849 (FIFO walker, before rsx_process_method) |
| 0x0104 | NV4097_NOTIFY |  |  | acts directly: guest_write |
| 0x0180 | NV4097_SET_CONTEXT_DMA_NOTIFIES |  |  | acts directly: capture:s_notify_ctx |
| 0x01A4 | NV4097_SET_CONTEXT_DMA_SEMAPHORE |  |  | acts directly: capture:s_sem_ctx |
| 0x01A8 | NV4097_SET_CONTEXT_DMA_REPORT |  |  | handled in the FIFO walker, not rsx_process_method: cellGcmSys.c:2380 (gcm_3d_method) |
| 0x0200 | NV4097_SET_SURFACE_CLIP_HORIZONTAL | surface_clip_w, surface_clip_x | yes | partial: not read by the D3D12 path: surface_clip_x |
| 0x0204 | NV4097_SET_SURFACE_CLIP_VERTICAL | surface_clip_h, surface_clip_y | yes | partial: not read by the D3D12 path: surface_clip_y |
| 0x0208 | NV4097_SET_SURFACE_FORMAT | surface_format | yes |  |
| 0x0210 | NV4097_SET_SURFACE_COLOR_AOFFSET | surface_color_offset[] | yes |  |
| 0x0214 | NV4097_SET_SURFACE_ZETA_OFFSET | surface_zeta_offset | yes |  |
| 0x0218 | NV4097_SET_SURFACE_COLOR_BOFFSET | surface_color_offset[] | yes |  |
| 0x0220 | NV4097_SET_SURFACE_COLOR_TARGET | color_target | yes |  |
| 0x0288 | NV4097_SET_SURFACE_COLOR_COFFSET | surface_color_offset[] | yes |  |
| 0x028C | NV4097_SET_SURFACE_COLOR_DOFFSET | surface_color_offset[] | yes |  |
| 0x0304 | NV4097_SET_ALPHA_TEST_ENABLE | alpha_test_enable | yes |  |
| 0x0308 | NV4097_SET_ALPHA_FUNC | alpha_func | yes |  |
| 0x030C | NV4097_SET_ALPHA_REF | alpha_ref | yes |  |
| 0x0310 | NV4097_SET_BLEND_ENABLE | blend_enable | yes |  |
| 0x0314 | NV4097_SET_BLEND_FUNC_SFACTOR | blend_sfactor | yes |  |
| 0x0318 | NV4097_SET_BLEND_FUNC_DFACTOR | blend_dfactor | yes |  |
| 0x0320 | NV4097_SET_BLEND_EQUATION | blend_equation | yes |  |
| 0x0324 | NV4097_SET_COLOR_MASK | color_mask | yes |  |
| 0x0328 | NV4097_SET_STENCIL_TEST_ENABLE | stencil_test_enable | yes |  |
| 0x032C | NV4097_SET_STENCIL_MASK | stencil_write_mask | yes |  |
| 0x0330 | NV4097_SET_STENCIL_FUNC | stencil_func | yes |  |
| 0x0334 | NV4097_SET_STENCIL_FUNC_REF | stencil_ref | yes |  |
| 0x0338 | NV4097_SET_STENCIL_FUNC_MASK | stencil_mask | yes |  |
| 0x033C | NV4097_SET_STENCIL_OP_FAIL | stencil_op_fail | yes |  |
| 0x0340 | NV4097_SET_STENCIL_OP_ZFAIL | stencil_op_zfail | yes |  |
| 0x0344 | NV4097_SET_STENCIL_OP_ZPASS | stencil_op_zpass | yes |  |
| 0x0348 | NV4097_SET_TWO_SIDED_STENCIL_TEST_ENABLE | two_sided_stencil | yes |  |
| 0x0350 | NV4097_SET_BACK_STENCIL_FUNC | back_stencil_func | yes |  |
| 0x035C | NV4097_SET_BACK_STENCIL_OP_FAIL | back_stencil_op_fail | yes |  |
| 0x0360 | NV4097_SET_BACK_STENCIL_OP_ZFAIL | back_stencil_op_zfail | yes |  |
| 0x0364 | NV4097_SET_BACK_STENCIL_OP_ZPASS | back_stencil_op_zpass | yes |  |
| 0x0370 | NV4097_SET_COLOR_MASK_MRT | color_mask_mrt, color_mask_mrt_set | yes |  |
| 0x08E4 | NV4097_SET_SHADER_PROGRAM | fragment_program_addr, shader_program | yes | partial: not read by the D3D12 path: fragment_program_addr |
| 0x0A00 | NV4097_SET_VIEWPORT_HORIZONTAL | viewport_w, viewport_x | yes |  |
| 0x0A04 | NV4097_SET_VIEWPORT_VERTICAL | viewport_h, viewport_y | yes |  |
| 0x0A28 | NV4097_SET_VIEWPORT_OFFSET.z | viewport_offset[2] |  | z lane consumed by the shader epilogue (depth remap) |
| 0x0A38 | NV4097_SET_VIEWPORT_SCALE.z | viewport_scale[2] |  | z lane consumed by the shader epilogue (depth remap) |
| 0x0A6C | NV4097_SET_DEPTH_FUNC | depth_func | yes |  |
| 0x0A70 | NV4097_SET_DEPTH_MASK | depth_mask | yes |  |
| 0x0A74 | NV4097_SET_DEPTH_TEST_ENABLE | depth_test_enable | yes |  |
| 0x0B80 | NV4097_SET_TRANSFORM_PROGRAM | vp_ucode, vp_ucode[], vp_ucode_bytes, vp_ucode_write | yes |  |
| 0x0B84..0x0BFC (31) | NV4097_SET_TRANSFORM_PROGRAM[n] | vp_ucode, vp_ucode[], vp_ucode_bytes, vp_ucode_write |  |  |
| 0x1680 | NV4097_SET_VERTEX_DATA_ARRAY_OFFSET | vertex_attribs[].offset | yes |  |
| 0x1684..0x16BC (15) | NV4097_SET_VERTEX_DATA_ARRAY_OFFSET[n] | vertex_attribs[].offset |  |  |
| 0x1740 | NV4097_SET_VERTEX_DATA_ARRAY_FORMAT | vertex_attribs[].enabled, vertex_attribs[].format, vertex_attribs[].frequency, v | yes |  |
| 0x1744..0x177C (15) | NV4097_SET_VERTEX_DATA_ARRAY_FORMAT[n] | vertex_attribs[].enabled, vertex_attribs[].format, vertex_attribs[].frequency, v |  |  |
| 0x1800 | NV4097_GET_REPORT |  |  | handled in the FIFO walker, not rsx_process_method: cellGcmSys.c:2381 (gcm_3d_method) |
| 0x1808 | NV4097_SET_BEGIN_END | begin_epoch, in_begin_end, primitive_type, textures[] | yes | acts directly: backend.bind_texture, backend.set_alpha_test, backend.set_blend, backend.set_color_mask, backend.set_depth_stencil, backend.set_render_target, backend.set_shader, backend.set_vertex_attribs, backend.set_viewport |
| 0x1814 | NV4097_DRAW_ARRAYS | primitive_type, surface_color_offset[], vertex_constants[] | yes | acts directly: backend.draw_arrays |
| 0x181C | NV4097_SET_INDEX_ARRAY_ADDRESS | index_array_offset | yes |  |
| 0x1820 | NV4097_SET_INDEX_ARRAY_DMA | index_array_dma | yes |  |
| 0x1824 | NV4097_DRAW_INDEX_ARRAY | primitive_type | yes | acts directly: backend.draw_indexed |
| 0x1830 | NV4097_SET_CULL_FACE | cull_face | yes |  |
| 0x1834 | NV4097_SET_FRONT_FACE | front_face | yes |  |
| 0x183C | NV4097_SET_CULL_FACE_ENABLE | cull_face_enable | yes |  |
| 0x1840..0x187C (16) | NV4097_SET_TEXTURE_*[n] | textures[].control3 | yes |  |
| 0x1A00..0x1BFC (128) | NV4097_SET_TEXTURE_*[n] | textures[].address, textures[].border_color, textures[].control0, textures[].con | yes |  |
| 0x1C00..0x1CFC (64) | NV4097_SET_VERTEX_DATA4F_M.*[n] | vertex_data4f[] | yes |  |
| 0x1D60 | NV4097_SET_SHADER_CONTROL | shader_control | yes |  |
| 0x1D6C | NV4097_SET_SEMAPHORE_OFFSET |  |  | acts directly: capture:s_sem_off |
| 0x1D70 | NV4097_BACK_END_WRITE_SEMAPHORE_RELEASE |  |  | acts directly: guest_write, hook_call; handler condition also depends on runtime state |
| 0x1D74 | NV4097_TEXTURE_READ_SEMAPHORE_RELEASE |  |  | acts directly: guest_write, hook_call; handler condition also depends on runtime state |
| 0x1D8C | NV4097_SET_ZSTENCIL_CLEAR_VALUE | zstencil_clear_value | yes |  |
| 0x1D90 | NV4097_SET_COLOR_CLEAR_VALUE | color_clear_value | yes |  |
| 0x1D94 | NV4097_CLEAR_SURFACE | color_clear_value, surface_format, surface_zeta_offset, zstencil_clear_value | yes | acts directly: backend.clear |
| 0x1DAC | NV4097_SET_RESTART_INDEX_ENABLE | restart_index, restart_index_enable | yes |  |
| 0x1DB0 | NV4097_SET_RESTART_INDEX | restart_index, restart_index_enable | yes |  |
| 0x1E9C | NV4097_SET_TRANSFORM_PROGRAM_LOAD | transform_program_load, vp_ucode_write | yes | partial: not read by the D3D12 path: transform_program_load |
| 0x1EA0 | NV4097_SET_TRANSFORM_PROGRAM_START | transform_program_start | yes |  |
| 0x1EFC | NV4097_SET_TRANSFORM_CONSTANT_LOAD | transform_constant_load | yes |  |
| 0x1F00 | NV4097_SET_TRANSFORM_CONSTANT | transform_constant_load, vertex_constants[], vertex_constants_hi, vertex_constan | yes |  |
| 0x1F04..0x1F7C (31) | NV4097_SET_TRANSFORM_CONSTANT[n] | transform_constant_load, vertex_constants[], vertex_constants_hi, vertex_constan |  |  |
| 0x1FC0 | NV4097_SET_FREQUENCY_DIVIDER_OPERATION | frequency_divider_op |  |  |
| 0x1FD8 | NV4097_INVALIDATE_L2 |  |  | accepted as a no-op (returns 0, stores nothing) |
| 0xE920 | GCM_FLIP_HEAD0 |  | yes | accepted as a no-op (returns 0, stores nothing) |
| 0xE924 | GCM_FLIP_HEAD1 |  | yes | accepted as a no-op (returns 0, stores nothing) |

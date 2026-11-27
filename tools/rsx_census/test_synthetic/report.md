# تعداد أوامر RSX اللي ما نستعملها
## RSX method census: synthetic harness stream

## الملخص / Summary

- start_sec: 3.0
- window_begin_sec: 3.0
- window_end_sec: 5.0
- frames: 2
- draws: 20
- draw_records: 20
- draw_records_dropped: 0
- writes_ge_0x2000: 20
- coverage.json generated 2026-11-27T18:52:29 from backend sh_work.c (backend)
- methods seen: 21; not handled on the legacy D3D12 path: 11

"draws affected" = draws issued in the window while the method held a value different from its reference (the reset default when known, else the first value the game wrote). A method set once at boot to a non-default value and never changed shows 0 here when its default is unknown; check "draws after first write" and the reference column for those.

## الأوامر الناقصة مرتبة حسب عدد الرسومات المتأثرة / Gaps ranked by draws affected

| # | method | name | class | writes (window/total) | distinct | draws affected | draws after first write | reference | sample values (decoded) | register meaning (KNOWN) | open-bug link (ASSUMED) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0x0A78 | NV4097_SET_POLYGON_OFFSET_SCALE_FACTOR | unhandled | 20/60 | 1 | **20** | 20 | reset 0 | 1 | polygon offset factor/bias: the depth bias amount (slope factor, constant units) | shadow acne / decal z-fighting (ASSUMED link) |
| 2 | 0x0A7C | NV4097_SET_POLYGON_OFFSET_BIAS | unhandled | 20/60 | 1 | **20** | 20 | reset 0 | 2 | polygon offset factor/bias: the depth bias amount (slope factor, constant units) | shadow acne / decal z-fighting (ASSUMED link) |
| 3 | 0x0A30 | NV4097_SET_VIEWPORT_SCALE.x | stored-but-unused | 0/2 | 1 | **20** | 20 | first value 640 | -640 | viewport offset/scale: maps clip space to window pixels (sub-viewports, y flip) | stretched/flipped draws, the 2x wide shape case A (ASSUMED link) |
| 4 | 0x0B00 | NV4097_SET_TEXTURE_CONTROL2[0] | unhandled | 20/20 | 8+ | **19** | 20 | first value 0x00000128 | 0x00000128, 0x00000129, 0x0000012A, 0x0000012B ... | texture CONTROL2 per unit (VERIFY exact bits) |  |
| 5 | 0x0A68 | NV4097_SET_POLY_OFFSET_FILL_ENABLE | unhandled | 20/60 | 2 | **10** | 20 | reset 0x00000000 | 0x00000000, 0x00000001 | polygon offset enable (point/line/fill): turns on depth bias for coplanar geometry such as decals and the shadow-map pass | shadow acne / decal z-fighting (ASSUMED link) |
| 6 | 0x0A20 | NV4097_SET_VIEWPORT_OFFSET.x | stored-but-unused | 4/13 | 2 | **6** | 20 | first value 640 | 640, 320 | viewport offset/scale: maps clip space to window pixels (sub-viewports, y flip) | stretched/flipped draws, the 2x wide shape case A (ASSUMED link) |
| 7 | 0x1738 | NV4097_SET_VERTEX_DATA_BASE_OFFSET | unhandled | 20/60 | 2 | **2** | 20 | reset 0x00000000 | 0x00000000, 0x00000100 | vertex data base offset: added to every vertex array offset | wrong/garbage vertices (ASSUMED link) |
| 8 | 0x1D78 | NV4097_SET_ZMIN_MAX_CONTROL | unhandled | 20/60 | 1 | **0** | 20 | reset 0x1 (clip; bit names VERIFY) | 0x1 (clip; bit names VERIFY) | ZMIN_MAX_CONTROL: near/far plane clipping vs depth clamping | geometry popping or cut at near/far, oversized shapes near camera (ASSUMED link) |
| 9 | 0x08CC | NV4097_SET_FOG_MODE | unhandled | 0/1 | 1 | **0** | 20 | first value 0x2601 LINEAR | 0x2601 LINEAR | fog mode and fog params: how the fog factor is computed from the fog coordinate and handed to the fragment program | haze / distance colour (ASSUMED link) |
| 10 | 0x08D0 | NV4097_SET_FOG_PARAMS[0] | unhandled | 0/1 | 1 | **0** | 20 | first value 0.5 | 0.5 | fog mode and fog params: how the fog factor is computed from the fog coordinate and handed to the fragment program | haze / distance colour (ASSUMED link) |
| 11 | 0x1EE0 | NV4097_SET_POINT_SIZE | unhandled | 1/1 | 1 | **0** | 10 | first value 4 | 4 | point size / point sprite control |  |

## أي رسمة تأثرت بأي أمر (أول فريم) / Per-draw view (watched methods, first window frame)

| method | name | draws (DRAW_LIST numbering) |
|---|---|---|
| 0x0A78 | NV4097_SET_POLYGON_OFFSET_SCALE_FACTOR | 10: #0-9 |
| 0x0A7C | NV4097_SET_POLYGON_OFFSET_BIAS | 10: #0-9 |
| 0x0A30 | NV4097_SET_VIEWPORT_SCALE.x | 10: #0-9 |
| 0x0B00 | NV4097_SET_TEXTURE_CONTROL2[0] | 9: #1-9 |
| 0x0A68 | NV4097_SET_POLY_OFFSET_FILL_ENABLE | 5: #0-4 |
| 0x0A20 | NV4097_SET_VIEWPORT_OFFSET.x | 3: #3-5 |
| 0x1738 | NV4097_SET_VERTEX_DATA_BASE_OFFSET | 1: #7 |

## أوامر مدعومة (للمقارنة) / Handled methods (context, top 40)

| # | method | name | class | writes (window/total) | distinct | draws affected | draws after first write | reference | sample values (decoded) | register meaning (KNOWN) | open-bug link (ASSUMED) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0x1A00 | NV4097_SET_TEXTURE_OFFSET | handled | 40/120 | 2 | **20** | 20 | first value 0x00001000 | 0x00001008, 0x00001000 | fragment texture unit state |  |
| 2 | 0x1A04 | NV4097_SET_TEXTURE_FORMAT | handled | 40/120 | 2 | **20** | 20 | first value 0x00001001 | 0x00001009, 0x00001001 | fragment texture unit state |  |
| 3 | 0x1A08 | NV4097_SET_TEXTURE_ADDRESS | handled | 40/120 | 2 | **20** | 20 | first value 0x00001002 | 0x0000100A, 0x00001002 | fragment texture unit state |  |
| 4 | 0x1A0C | NV4097_SET_TEXTURE_CONTROL0 | handled | 40/120 | 2 | **20** | 20 | first value 0x00001003 | 0x0000100B, 0x00001003 | fragment texture unit state |  |
| 5 | 0x1808 | NV4097_SET_BEGIN_END | handled | 40/120 | 2 | **0** | 20 | first value 0x00000005 | 0x00000000, 0x00000005 |  |  |
| 6 | 0x1814 | NV4097_DRAW_ARRAYS | handled | 20/60 | 1 | **0** | 20 | first value 0x02000000 | 0x02000000 |  |  |
| 7 | 0x1A10 | NV4097_SET_TEXTURE_CONTROL1 | handled | 20/60 | 1 | **0** | 20 | first value 0x00001004 | 0x00001004 | fragment texture unit state |  |
| 8 | 0x1A14 | NV4097_SET_TEXTURE_FILTER | handled | 20/60 | 1 | **0** | 20 | first value 0x00001005 | 0x00001005 | fragment texture unit state |  |
| 9 | 0x1A18 | NV4097_SET_TEXTURE_IMAGE_RECT | handled | 20/60 | 1 | **0** | 20 | first value 0x00001006 | 0x00001006 | fragment texture unit state |  |
| 10 | 0x1A1C | NV4097_SET_TEXTURE_BORDER_COLOR | handled | 20/60 | 1 | **0** | 20 | first value 0x00001007 | 0x00001007 | fragment texture unit state |  |

## حدود هذا التقرير / Limits

- Classes come from a static scan (coverage.md); ASSUMED unless marked KNOWN.
- Vertex-program microcode and constant runs that take the rsx_process_vp_run fast path never reach rsx_process_method, so their write counts are low or zero. They are handled methods; this does not affect the gap ranking.
- "Register meaning" is what the register does. The open-bug link column is a hypothesis to test, not a cause.

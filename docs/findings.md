
## 2026-11-27 18:45 Kuwait — عالم الفيزياء (summary; details in linked files)
- CONFIRMED: Bandit Trap gate freeze = SPU heqi r100,0 at LS 0x31C20 (divide-by-zero guard); divisor table LS 0x1F760 zeroed by mixer ring overrun (page 408 of 360). Event flag 0x00DBA900 then never set. voicefreeze/findings.md
- ASSUMED: duplicate voice visits from mask/snapshot desync during tid17 stop-all/restore. Deciding test: SF_RACE run (voicefreeze/race_run_spec.md).
- CONFIRMED: 18:17 village black hang is a different family (no halt, no EF block). Old-stage SPURS tasks (img 361927206/433674278/9000) never return; taskset 0x16FA2000 re-created at same address L106846/7 while old runs open. 17:27 log: stage-A tasks still in WAIT_SIGNAL during stage B (L76789/90). voicefreeze/blackhang_1817.md §1,§5
- ASSUMED: root = our cellSpurs taskset shutdown/teardown + same-address re-creation. Deciding test: [sf-lc] lifecycle lines in next bundled log build.
- CONFIRMED: all atrac3p "Channel unit extension" errors come from the 6ch BGM handle (105/105, 384/384); not linked to the hangs. Suspects in cellAtrac.c seek/stream bookkeeping (ASSUMED). blackhang_1817.md §3

## 2026-11-27 18:45 Kuwait, خبير الرسم (graphics)
- CONFIRMED (gfx-faces-hypotheses-2.md; /workspace/faces/diag2611/meas_bs_1784.json): ARL fix holds for geometry. Pre-fix VP D5208C20 writes a0 but reads bones through a1. Zhao Yun's scarf and head, the merchant's body, and the soldier's helmet and body are fixed.
- CONFIRMED: soldier face (#4) is still a black oval with only the chin lit.
- CONFIRMED (blacksmith pair, 1784 vs RPCS3, align 0.89): roof 0.60x, sign 0.53x, noticeboard 0.59x; lit ground, sky and shadowed wall about 1.0x. Acne and haze close to RPCS3; no blue shift.
- ASSUMED: per-material loss means stale baked FP constants (H1) are the top lead. Shadow term is lower (forced=1 moved the roof 63.5 to 71.3, pre-cull).
- Next (sent to سالم): on 1786, FP_CONSTBUF=0, then TCONST_DBG=1, then VP_DUMP; same-spot port + RPCS3 captures.

## 2026-11-27 18:47 Kuwait — باحث الرياضيات
- CONFIRMED (psdevwiki NID page + ps3recomp nid_database.py): NID = first 4 bytes LE of SHA-1(name + suffix 67 59 65 99 04 25 04 90 56 64 27 49 94 89 74 1A). Byte 6 is 0x04.
- CONFIRMED (psdevwiki): PAMF error codes are 0x806105xx; ps3recomp cellPamf.h uses 0x806103xx (collides with ATRAC). OSK error codes are 0x8002B501-504; cellOskDialog.h and strikeforce_osk.inc use 0x8002B30x (msg-dialog range). Details: nid-autolink/docs/hle_spec/.
- CONFIRMED (Salem run B, mixer-halt-1/ringwatch-results.md §5): mixer SPU halt = its own 4 KB PUT overwrote the table because the per-pass page index has no bound; voice leak (6..127 voices) + double group walk (250 visits / 505 pages vs 360-page ring).
- CONFIRMED (coverage scan, nid-autolink box-dryrun): all 20 cellAtrac imports are registered via strikeforce_atrac.inc, so the earlier idea "streaming NIDs unregistered" is retracted. GetSecondBufferInfo and IsSecondBufferNeeded are still stubs.
- ASSUMED (needs a check on the v020 tree): upstream sys_lwcond_signal/signal_all are no-ops → a possible cause of the village lost wake.
- ASSUMED: cellAudioOutConfigure not storing the config (Get* always report 2ch) is linked to the 6ch BGM path.

## 2026-11-27 18:50 Kuwait — باحث الرياضيات (atrac-validator, out_existing_logs/report.md)
- CONFIRMED (box logs, 8 tracks): 6ch BGM block_align = 1712; data_off = 168 on the 7 looped tracks and 100 on the one unlooped track, which equals the RIFF chunk sizes exactly. The frame grid is right. VERIFY with hashfile on the real track.
- CONFIRMED (counts from the existing logs): zero-like error bursts (6 bursts, 771 errors, 99.2% ch_block 0) each cover exactly 1 or 5 chunks of 131072 bytes. Random-like bursts (10 bursts, 383 errors) match the random-byte pattern (56.9/14.9/11.5% vs 50/12.5/12.5). "Channel unit extension" is the 1-in-8 random case.
- ASSUMED: whole chunks arrive empty or wrong, so the fault is in the AddStreamData path, not the header. New suspect: AddStreamData copies the ring at call time (cellAtrac.c L485), which may be before the game's read lands; there is no lock between tid 51 (adds) and tid 15 (decode). Seek-without-flush is less likely for these bursts but not ruled out.

## 2026-11-27 18:48 Kuwait, خبير الرسم
- #4 (soldier face black oval): CLOSED as resolved in the current build. Saud looked at it in-game at 18:47 (relayed by عالم الفيزياء) and says it looks normal. My black-oval note came from older captures. The soldier close-up is now optional, not required.
- Graphics focus: dim lit props and buildings (about 0.53-0.60x RPCS3), with H1 (stale baked FP constants) as the lead. Next is the FP_CONSTBUF=0 run on 1786.

## 8. 6ch BGM corruption root (Salem, 2026-11-27 18:52 Kuwait)
CONFIRMED by atrac-validator hostcmp on 9 existing host.bin dumps: bad frames are whole 131072-byte chunks holding the previous ring lap/track bytes (delta = k*1048576) or zeros. AddStreamData copies the ring before the title's async read lands (cellAtrac.c L485). Details: atrac-validator/pc-results/SUMMARY_salem_1850.md. Candidate fix 1790_audio_lazyring (not shipped, needs Saud OK).

## 2026-11-27 18:55 Kuwait, خبير الرسم: rsx_census static scan (tools/rsx_census/coverage.md)
- Sources: faces/src rsx_commands.c (md5 3720caf7) and faces/sh_work.c (c66d52a1). Counts: 376 handled, 51 stored-but-unused, 371 unhandled. The classification comes from a regex scan, so it is ASSUMED; evidence lines are in coverage.json.
- CONFIRMED: 0x1FF8 TRANSFORM_BRANCH_BITS is never passed to the VP decompiler on the legacy path. sh_work.c:1773 calls rsx_vp_decompile with no rsx_vp_set_branch_bits; only draw_engine:2549 and live_draw:4984 call it. So BRB/CLB branches always see 0 (rsx_vp_decompiler.c:142, 524).
- ASSUMED: if the lighting VPs branch per light on those bits, this explains the dim lit props (0.53-0.60x). It is a new lead alongside H1. Check: VP_DUMP of 0x3F083BFF/0x6A46C9BA plus census values for 0x1FF8.
- CONFIRMED stored but unused: viewport scale/offset x/y/w (d3d12_set_viewport is an empty TODO, sh_work.c:6661); scissor (backend always sets full-window, :5273).
- Not handled on the legacy path: polygon offset 0x0A60-0x0A7C, fog 0x08CC-0x08D4, 0x1D78, 0x1738/0x173C, blend colour 0x031C/0x037C, depth bounds 0x0380-0x0388.

## 2026-11-27 19:00 Kuwait — سالم (1785 env-only gfx runs A/B, closed)

Details: `/workspace/sf-gfx-runs/REPORT.md`. Bisect: `/workspace/sf-gfx-runs/bisect/report.md`. Logs/shots: `/workspace/sf-gfx-runs/A/`, `B/`.

- CONFIRMED (1785_mixfix MD5 0315FD44BEF056A140D3C99AF92CA902; A 18:23:34–18:36:06, B 18:36:28–18:48:55 Kuwait; `[TEST-SALEM]`; CloseMainWindow): all 10 requested env strings already in the exe / test-copy sources. No code added.
- CONFIRMED (gfx_bisect, blacksmith prompt, RPCS3 `village_blacksmith.png`, orb_affine+ecc inliers 334–370, ECC 0.892–0.895): dark roofs remain lower than the ref — A ×0.682, A official ×0.677, B tour_now ×0.673. Shadow acne close to the ref (×1.124, ×0.959, ×1.116). Haze close. White ground near zero.
- CONFIRMED (A vs B at the same Blacksmith prompt, inliers 1715, ECC 0.9919, MAE 0.0153, dark roofs ×0.993): `FP_CONSTBUF=0` did not restore roof/sign brightness on this 1785 exe. FPLIST unique fp 39 (A) vs 5222 (B) shows the flag did change hashing. H1 (stale baked FP constants fixed by hashing inline constants) is not supported on 1785_mixfix. 1786 `FP_CONSTBUF=0` was not run here.
- CONFIRMED (A stdout DRAWLIST, two frames of 793 draws, lines ~60049–61644): shadow pass #0–#311, vp=1024×1024, rt=0, z=0x003A0000. After last scene-like #791, one fullscreen n=4 (#792, fp=0x0D3AF801, rt=0x0D3B0000). ff=0x901. TEXFMT_ALL=127; zero binds with off=0x00000000. TEXBIND lines=0. B dump is Gatekeeper (544 draws), not blacksmith.
- CONFIRMED (prior 1776 HLSL+ucode dumps of the same hashes, `clothv2/r1776/cwd_1776/faces_vp_*.hlsl`; 46/57 instrs match 1785 `[VP]` first-cache): prop VP 0x6A46C9BA has 1 BRB (bit 0), shadow VP 0xD54F73A6 has 3 BRB (bits 1,2), prop VP 0x3F083BFF has 4 BRB (bits 0,1,2). CLB=0 on all three. Polarity D3[28]=0, so bits=0 makes every BRB always taken. The 0x6A46C9BA fall-through (instr 15–28) is a lighting body (light vec vp_c[466], n·l, exp2 specular, × vp_c[257]). 0x3F083BFF was not in the 1785 first-cache `[VP]` lines. This session had no VP_DUMP. ASSUMED: the same bake is why lit props are dim on the current exe; needs a live VP_DUMP + 0x1FF8 census (owned by 8587ecb8; `tools/rsx_census/pc-results/` not present; not double-run).
- CONFIRMED (`ps3recomp\libs\video\rsx_commands.c:93` in the test-copy tree, mtime 2026-11-26 22:30:05): front_face=0x0901. v5 `link_movie.rsp` links `ps3recomp_runtime.lib` (22:30:24) which contains `rsx_commands.c.obj`, plus `rsx_d3d12_backend_v5.obj`.
- Village spawn vs RPCS3 instage_notut: inliers 193, ECC 0.579 — **not camera-matched** (ours behind Zhao Yun with fence, no tutorial; ref is “9 facilities”). Do not use that pair to confirm acne/haze/roofs. No RPCS3 Gatekeeper shot this session. Soldier face #4 is CLOSED (expert / Saud). Left-edge blue strip: not present in client-area columns (bluefrac ≈ 0); full-window PNGs not measured; cause unconfirmed.

## 2026-11-27 19:08 Kuwait, خبير الرسم: branch-bits root-fix diff (fixes/branch-bits/)
- CONFIRMED (harness, 1776 dumps): with bits=0 the 6A46C9BA output is byte-identical to today and BRB@14 jumps over the lighting body (15-28). With bit0 set, only `_pc=15` changes and the body runs. Polarity matches the ISA (taken when bit == D3[28]).
- Fix: bits are fixed when the shader is written, and only the tested bits are keyed into the VS hash/PSO, matching the draw_engine/live_draw paths. VP_BRANCH_BITS_OFF=1 is the A/B switch.
- ASSUMED: this brightens the dim props. It stays unconfirmed until the census shows 0x1FF8 bit0 set at the blacksmith and roof/sign/board move toward RPCS3.
- Status: diff only, waiting on Saud's OK for a test build (1788_bbits).

## 2026-11-27 19:22 Kuwait — سالم (1788_bbits build; tests waiting)

Saud approved the test-copy lighting fix at 19:09: "إي ابن تصليح الإضاءة وجربه بنسخة التجربة". Details: `/workspace/sf-shared/fixes/branch-bits/BUILD_1788.md`.

- CONFIRMED: new exe `sfauto\exe_copies\1788_bbits\MyGameRecomp.exe`, MD5 `0AA9D0B7F8F213D5E2AA09B300CD70E2`, 189,257,728 bytes, built 19:13:05 Kuwait. Isolated tree `sfauto\bbits1788\src\` only (census then branch-bits, anchors once; `.bak` kept). clang-cl compiled census steps 4-5 into the v5 backend copy (md5-before `2302fda0`) plus `rsx_commands.obj` and `rsx_vp_decompiler.obj`; linked ahead of the v5 runtime lib. Exe contains `VP_BRANCH_BITS_OFF`, `[VPBB]`, `[CENSUS]`, `RSX_CENSUS`.
- CONFIRMED: shared `ps3recomp\libs\video`, `1786_movie_v5` exe (MD5 `E41A5A94725045155439770EE70087C7`, mtime 17:56:10) and `PLAY_Strikeforce.bat` (mtime 18:08:37) were not modified (tree_md5 before == after).
- Census at blacksmith and A/B (`VP_BRANCH_BITS_OFF=1` vs default) have **not** been started. `1786_sfrace` pid 39940 (SFRACE window since 19:01:14) is still running; not touched. Launchers ready; wait for a 5-minute clear.

## 2026-11-27 19:31 Kuwait — سالم (SFRACE run pid 39940: infinite respawn zone; teleport notes)

- CONFIRMED (screens `sfauto\runs\sfrace\shots\z2_client.png`, tp3/w2): Bandit Trap, snowy rock area at the south entrance of map area **"1"** (minimap: corridor from start camp "S" north into area 1; exits north and east). Player XYZ at 0x008D3800 = **(5960, 2494, 14983)** while fighting; start camp S = (6500, 4346, 7500). Bandits kept coming; run passed 339+ KOs (Saud's count 19:21) with no objective change and no `BLUS30471/5443|5444` line. Area/stage name string was NOT read from memory (no address known).
- VERIFY: **infinite respawn zone** — may be normal game design until the area officer / objective is done (Dynasty Warriors-style squads respawn until the officer falls). Compare with RPCS3 or a walkthrough before treating as a port bug.
- CONFIRMED (teleport, 19:22–19:28): writing only 0x008D3800 is ignored while the player is knocked down; a single +2500 Z jump put the player out of bounds and the game respawned him at S (6500, 4346, 7500) — no freeze. Writing all 8 mirrors (0x008D3800/3860/38B0/38F0, 0x00905120, 0x14600080, 0x14800090, 0x16A1D9F0) in 250-unit steps every 350 ms works (S -> area 1 in ~12 s): `sfauto\runs\tpstep.ps1 -TX <x> -TZ <z>`.
- CONFIRMED (cellPad.c:1074ff): `PAD_FILE` ignores a mask of 0 (file is never emptied). Stick-only walking needs mask `0x10000` ("0x10000 60 128 0").
- Run ended 19:28:23 by the runner's 25-min cap (CloseMainWindow on my own pid 39940). Gate not reached; no freeze pattern; watchdog exited. Gate location still unknown (no coords in checkpoints.json). Next run should step-teleport north/east from area 1 to find the gate; not started because 1788_bbits tests are waiting for a clear slot.

## 2026-11-27 19:39 Kuwait — سالم (helper): 48 STUB HLE census

- Output: `/workspace/sf-stubs48/stubs48.md` and `stubs48.json`. Source classification: nid-autolink report 2026-11-27 17:19 Asia/Kuwait (248 linked, 48 stub, 40 missing, 7 conditional, 3 partial of 346).
- CONFIRMED: **20/48 CALLED**, **28/48 IMPORTED-NOT-SEEN** in all box logs + findings.json + the 17:19 call column.
- Hooked logs (SF_HLE_LRLOG): voicediag 17:27 and SFRACE 19:01–19:30. Counts are the last *complete* `[hle-lrc]` dump (SFRACE L789956, 1163 pairs). Later SFRACE bursts are fragmented and were not used.
- CONFIRMED hottest stubs in SFRACE: `sys_lwcond_signal_all` 4,039,883 calls (boot→A→B), `sys_lwcond_signal` 363,392, `_cellGcmSetFlipCommand` 65,157, `cellKbRead` 65,149 (≈1:1 with flips, ~37 fps over ~29 min). `sys_lwcond_destroy` first seen at SFRACE L804394 (stage B teardown).
- ASSUMED risk: if the winning `sys_lwcond_signal*` body is really a no-op, that is an extra hang candidate. It does **not** replace the SPURS old-stage leak (CONFIRMED separately). VERIFY the winning handler on the test copy (ctx vs table).
- IMPORTED-NOT-SEEN despite the hook being on from boot through stage B (stronger absence): `cellAtracGetSecondBufferInfo`, `cellAtracIsSecondBufferNeeded`, `cellAudioOutConfigure` (spec: needs-real-impl), Sail Create/DestroyDatabase, cellGame GetSizeKB/PatchCheck, cellRescSetBufferAddress, remaining OSK setters (two OSK setters *were* seen in 1817 stdout), NP/net/AVC2/fs/save-delete, `sys_prx_exitspawn_with_level`, `sys_spu_image_close`.
- Phase 2 is a plan only: no PC run in this pass. SFRACE already covered in-world LRLOG; leftover stubs need a later boot+menus log-only run.

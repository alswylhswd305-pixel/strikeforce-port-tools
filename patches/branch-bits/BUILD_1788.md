# 1788_bbits build — سالم — 2026-11-27 19:13 Asia/Kuwait (UTC+3)

Saud approved a test-copy lighting fix at 19:09: "إي ابن تصليح الإضاءة وجربه بنسخة التجربة".

## Build (CONFIRMED)

- Exe: `<TEST_COPY>\sfauto\exe_copies\1788_bbits\MyGameRecomp.exe`
- MD5: `0AA9D0B7F8F213D5E2AA09B300CD70E2`
- Size: 189,257,728 bytes
- Built: 2026-11-27 19:13:05 Kuwait
- Isolated sources + backups: `sfauto\bbits1788\src\` (`.orig`, `.census.bak`, `.bb.bak`)
- Shared `ps3recomp\libs\video`, `movie1786\build\rsx_d3d12_backend_v5.c`, `1786_movie_v5\MyGameRecomp.exe` (MD5 `E41A5A94725045155439770EE70087C7`, mtime 17:56:10) and `PLAY_Strikeforce.bat` (mtime 18:08:37) were **not** modified (tree_md5_before == tree_md5_after).
- Base: 1786_movie_v5 snapshot objs + stubs_movie + strikeforce_movie.inc + backend copy md5 `2302fda00a3f17ae13c5fed4c05930b2`.
- Patches (anchors matched once; second apply = already patched): `apply_census.py --write` then `apply_branch_bits.py --write` on the isolated tree only.
- Census steps 4-5 (draw + frame hooks) compiled into `rsx_d3d12_backend.obj` (426,820 bytes, 19:13:00) with clang-cl, same ninja FLAGS/INCLUDES as the runtime C files, `-I src` first.
- Also compiled: `rsx_commands.obj` (census hook), `rsx_vp_decompiler.obj` (branch-bits mask).
- Linked with lld-link ahead of `ps3recomp_runtime.lib` (same pattern as v5).
- Exe strings present: `VP_BRANCH_BITS_OFF`, `[VPBB]`, `[CENSUS]`, `RSX_CENSUS`.
- Claim: `/workspace/sf-shared/claims.md` (19:11). 8587ecb8 SFRACE (`1786_sfrace` pid 39940) was running during the build and was not touched.

## Tests (not started)

Waiting for no MyGameRecomp / RPCS3 / SFRACE window for 5 continuous minutes before the blacksmith census run (`RSX_CENSUS=<sec>,2` + `DRAW_LIST`). If 0x1FF8 bit0 is never set at that stop, A/B will be skipped.

## Tests still waiting (2026-11-27 19:22 Kuwait)

8587ecb8 (or Salem race) still holds the PC: `1786_sfrace\MyGameRecomp.exe` pid 39940 started 19:01:14, still running at 2026-11-27 19:22 (title `[TEST-SALEM]`, plus WindowsTerminal `[TEST-SALEM] Strikeforce SFRACE 1786` pid 41300). Not touched. Census + A/B launchers are written at `sfauto\bbits1788\launch_run.ps1` and will start only after no MyGameRecomp/RPCS3/SFRACE window for 5 continuous minutes.

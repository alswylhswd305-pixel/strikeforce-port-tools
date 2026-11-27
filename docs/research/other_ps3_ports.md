# Other people's PS3-to-PC ports — research notes

Date: 27 November 2026, evening, Asia/Kuwait (UTC+3). Web + box only. Saud's PC was not touched. No executables were run. No game files, ROMs, or firmware were kept. No RetroGems app was downloaded.

This document is for the team (English). Ideas only: no GPL and no RPCS3-derived code into the Strikeforce port. Paraphrase with a source link and, where we have a study clone, `file:line`.

Primary catalogue used at Saud's request: [RetroGems, PlayStation 3](https://retrogems.fr/en/ports-recomp-decomp/console/playstation-3/) (HTTP 200 on 27 Nov 2026). Cross-checked against [recomp.fyi / PS3 toolchains](https://recomp.fyi/toolchain/ps3) (HTTP 200) and each project's GitHub README / docs. Study clones of public source, where taken, live under `/workspace/sf-shared/ext/` with licenses in [`/workspace/sf-shared/ext/LICENSES.md`](/workspace/sf-shared/ext/LICENSES.md).

## Direct answers Saud asked about

**God of War (the name he used).** There is **no** public playable native PC recomp of the original *God of War* (2005) or of *God of War III* (PS3) that this pass could verify.

- *God of War: Ascension* (PS3) **does** have several unofficial ps3recomp ports. RetroGems' card points at [rigaz29/Ascension-R](https://github.com/rigaz29/Ascension-R) (HTTP 200). Other real trees include [otavix010/gow-ascension-pc](https://github.com/otavix010/gow-ascension-pc) and [bc160201983/GoW-Ascension-Recomp](https://github.com/bc160201983/GoW-Ascension-Recomp) (both HTTP 200). These are *Ascension*, not GoW 1/2/3.
- *God of War III* (PS3): [tbittech/gow3-nx](https://github.com/tbittech/gow3-nx) (HTTP 200) is a **Nintendo Switch** experiment on ps3recomp. Its README says **not playable yet**, work in progress, "overall progress: ~25%", no playable release. It is not a PC port.
- *God of War II HD* appears on recomp.fyi as a macOS / Metal kit ("gow2-recomp"), not a Windows port verified here. غير مؤكد beyond the board listing; that tree was not cloned in this pass.
- A *God of War III Remastered* unofficial PC effort (SpartanPort) is a **PS4** project, not a PS3 recomp, and was not used as a source here.

**inFamous.** Yes, public unofficial native PC recomps exist.

- RetroGems "InFamous Recompilation" → official repo [whompay/inFAMOUSreborn](https://github.com/whompay/inFAMOUSreborn) (HTTP 200). The README itself says this is the official repo and that forks are unsupported. European disc `BCES00220`, ps3recomp, D3D12, Setup builds from the player's own copy. Latest public release noted earlier: 1.1 (22 Oct 2026). Study copy: `ext/infamous-reborn` (firmware folder removed; see LICENSES.md).
- RetroGems "InFamous Enhanced Recompilation" → [ibrahimpuri/inFamous-PC-Enhanced](https://github.com/ibrahimpuri/inFamous-PC-Enhanced) is **HTTP 404**. The GitHub user exists; that repository does not. GitHub search for the name returned 0 repositories. The RetroGems card page itself is HTTP 200, but its GitHub button is a dead link. **There is no verified official "Enhanced" source to clone.** غير مؤكد what RetroGems intended.
- RetroGems "InFamous 2 PC Port" → [bhuiyah/infamous2-recomp](https://github.com/bhuiyah/infamous2-recomp) (HTTP 200). ps3recomp, D3D12. Target US `BCUS98125` update 1.04; European copies described as beta. Study copy: `ext/infamous2-recomp`. Other trees exist (erikomis, SamiEnazi); the RetroGems card is bhuiyah's.

---

## 1. Folklore — top item

Saud asked about this project specifically. RetroGems lists it as "Folklore Recompilation".

### Official source (vs mirrors)

| | |
|---|---|
| Official GitHub | https://github.com/Mava-b/folklore-decomp (HTTP 200) |
| RetroGems card | https://retrogems.fr/en/ports-recomp-decomp/folklore-recompilation/ (HTTP 200) — GitHub button matches the official repo |
| Author | GitHub user **Mava-b** (person). Ko-fi: https://ko-fi.com/mavab (HTTP 200). LICENSE copyright line: "Mava-b and the folklore-decomp contributors". |
| License | MIT (`LICENSE`). The GitHub API reports `NOASSERTION`, but the file in the tree is a standard MIT text plus a note that Folklore / Sony code is never in the repository. |
| Repo name vs README | The repository is named `folklore-decomp` and the GitHub description says "Folklore PS3 Decomp with AI". The **README title and body say it is a static recompilation** with ps3recomp, not a traditional source-code decompilation. Contributors listed by the API include `claude` (more commits than `Mava-b`), which matches "with AI". |
| Study copy | `/workspace/sf-shared/ext/folklore-decomp` at `20fbb08415f2` (17 Nov 2026, 9:00 PM Asia/Kuwait) |
| Latest public release (author's claim) | **v0.64** (published 12 Nov 2026, 11:59 PM Asia/Kuwait): HDR, keyboard and mouse. Release assets are zips named `Folklore-…zip`. **We did not download those zips.** The README, "Sharing what you built", says the binaries package contains `folklore.exe`, which *is* Folklore's code translated, and must not be given to other people. Point others at the repository instead. |

**Mirrors / lookalikes (not official):**

- [erikomis/folklore-decomp](https://github.com/erikomis/folklore-decomp) (HTTP 200) — a **fork** of Mava-b's repo (0 stars). Not the official tree.
- [ronvotri/PS3-folklore](https://github.com/ronvotri/PS3-folklore) (HTTP 200) — a **Vietnamese translation catalog** aimed at RPCS3, not a native PC recomp. Do not confuse it with Mava-b's port.

**Legit / safe, for our purposes:** the official source is the Mava-b git tree. It states it ships no game or Sony code; setup translates the player's own disc (`BCUS98147` or `BCES00050`) on their PC. MIT for the port's own scripts and patches. **Do not download or run the GitHub release zips** (author says they contain translated game code). **Do not run** `FolkloreLauncher.exe` / setup on the box. Setup also offers an optional path that lifts the player's own `libsre.prx` for comparison; we did not do that, and firmware must not be added to this tree.

### Toolchain and how playable

- **Toolchain:** [ps3recomp](https://github.com/sp00nznet/ps3recomp), vendored at commit `39a3629` with the port's patches in `patches/` (README, "Repository layout"). Graphics: Direct3D 12. Movies: FFmpeg, downloaded by setup, not vendored (LGPL, per the credits section).
- **Playable, according to the author, on the author's PC** (Windows 11, Ryzen 7 7800X3D): boots, completes the first-boot install, and plays, including capturing Folks with motion controls. "Expect rough edges." Full log: `folklore/docs/STATUS.md`.
- Caution: `folklore/docs/STATUS.md` still opens with a summary table dated **18 Oct 2026** that shows logo movies unfinished and title/gameplay blank. Later README text and GitHub release notes (v0.5 through v0.64, early–mid November) supersede that table. غير مؤكد from this pass whether anyone other than the author has finished the campaign; the public claim is "playable on the author's PC", not a third-party full playthrough.

### How they handled problems like ours

**SPURS (very relevant to our stage-change hang).** Folklore does **not** use SPURS tasksets. It uses **one job chain** on **one SPU** (`folklore/docs/SPURS.md` in the study copy, and the same file upstream).

From their traces of the real library (first golden trace 21 Oct 2026):

- During the first 1.2 seconds of boot the job chain is created, kicked, then `cellSpursShutdownJobChain` / `cellSpursJoinJobChain` **13 times**, then kept for the session.
- **Each area load tears the chain down and builds it again** (two-job form, then the seven-job loop).
- Shutdown is specified as: a chain waiting at its **guard** must end, and **Join waits for that**.
- Until October 2026 they ran Sony's `libsre` lifted from each player's firmware. They then wrote their own native replacement (`folklore/src/hle/spurs_native.cpp` and `spurs_native_job.c`) from those traces, and kept `-Libsre` only for comparison. First test (21 Oct 2026): Ellen's chapter 1 held a steady 60 fps, no chain errors or dropped events in the log.

That is the same *class* as our hang (teardown, then re-create work at the same addresses, while old work is still running), but a different SPURS API (job chain + guard, not taskset). **Do not copy their C.** The idea to take: Join/Shutdown must wait until the old workload has actually left before Destroy / re-Create; confirm with a trace of the real sequence.

Upstream ps3recomp [PR #809](https://github.com/sp00nznet/ps3recomp/pull/809) (open, not merged as of this check; HTTP 200) is the taskset form of the same idea: `cellSpursJoinTaskset` was a stub that returned at once, but titles do Shutdown → Join → Destroy → re-Create and need Join to wait until ENABLED bits are clear (they propose a 10 s bound, then BUSY). [PR #833](https://github.com/sp00nznet/ps3recomp/pull/833) (open) and closed [PR #711](https://github.com/sp00nznet/ps3recomp/pull/711) are about job-chain shutdown/join draining in-flight work (Deus Ex: Human Revolution, and earlier titles).

ps3recomp `docs/FIRMWARE_LLE.md` describes lifting the real SPURS kernel from the player's own `libsre.prx` as an alternative when HLE diverges. It is documented as proven on one title (Yakuza: Dead Souls) and "expected, not yet generalized." Folklore used that approach first, then replaced it with a title-specific native runner. Firmware LLE on our side would need Saud's OK and must stay on a test copy, never in a shared tree.

**Audio.** Folklore streams `.sgb_` files (STATUS.md, "The game, by the numbers"). This is not documented as the same ATRAC3 `AddStreamData` ring bug we have. Early log: a wrong job-context pointer at `+0x70` made an audio job DMA to address −1 and spin (black screen). Later patches include audio limiter / pacing and surround output (`patches/0047`, `patches/0110` in their tree). Surround 5.1/7.1 is a player-facing option. غير مؤكد that any of this is a drop-in fix for our ATRAC voices.

**Movies / cellVdec / MPEG-2 / SPU timing.** Cutscenes are MPEG-2 `.m2v_`, decoded with **cellVdec + FFmpeg** (STATUS.md). Concrete fixes in the October log, paraphrased:

- `cellFsAioRead` completed **inside the submit call**. The movie streamer submitted a read, then marked it outstanding and waited for the completion callback. The callback had already run, so the logo movie received no data (black screen). They moved completion onto a **worker thread**. Locally, movie_995 then decoded in full (StartSeq, about 290 pictures, EndSeq).
- That ordering bug is the **same class as our ATRAC issue**: the HLE consumed or finished a buffer before the guest's async fill was visible.
- A race in the game's own movie player threads (a "hold" flag and a condition wait that was never signalled) was given a 100 ms timeout via a **game patch**. After that, the movie completed in 14 of 14 local runs. We should not skip cutscenes; a timeout on a hung wait is a different, narrower idea and would need its own proof on Strikeforce.
- Other movie issues in that log: FFmpeg rejected some access units; a cellVdec crash when an AU-size table was overwritten by a concurrent loader (they reserved scratch with game patches); need to lift SPU jobs at every local-store address the job manager actually uses.

Upstream: [PR #215](https://github.com/sp00nznet/ps3recomp/pull/215) (merged) — H.264 and MPEG-2 through FFmpeg loaded at run time; [PR #380](https://github.com/sp00nznet/ps3recomp/pull/380) (merged) — MPEG-2 timestamps and frame rate; [PR #812](https://github.com/sp00nznet/ps3recomp/pull/812) (open) — write an RGB picture only after the FIFO walker has caught up (SPU/GPU timing).

**RSX / shaders.** D3D12. v0.62 notes: loading screen stays up until the new area's shaders are built, so half-drawn frames no longer flash after Load Game; a ~150 ms game-vs-renderer hold-up in heavy combat was removed. Soft shadows, SMAA/FXAA, HDR in v0.64 are enhancements, not the TRANSFORM_BRANCH_BITS fix. Upstream empty-scissor work mentioned Folklore and Guitar Hero 3 as motivation (already in the earlier community survey). غير مؤكد whether Folklore hit 0x1FF8 branch bits specifically.

**Testing approach.** Golden SPURS traces (`run.ps1 -TraceSpurs`), including a compact "shape" mode that can be compared between the native runner and `-Libsre`. Render capture for bug reports. "Motion watch" for capture mechanics. They explicitly compare their replacement against Sony's libsre when the player supplies it. No auto-play bot is described in the README sections checked.

---

## 2. Priority projects from the RetroGems list

All GitHub links below returned HTTP 200 on 27 Nov 2026 unless noted.

### InFamous Recompilation — [whompay/inFAMOUSreborn](https://github.com/whompay/inFAMOUSreborn)

- **Method:** ps3recomp, PPU/SPU to C/C++, D3D12, Windows. Official README. Setup builds from the player's European disc `BCES00220`.
- **Status (author):** unofficial native Windows port; Setup + updater. Playable is the status given on recomp.fyi and in third-party catalogues; this pass did not independently play it. غير مؤكد how far into the campaign third parties have gone.
- **License:** unspecified (no root LICENSE). Study only. Firmware PRXs that were in `ps3recomp/fw_spu/` were removed from our copy.
- **SPURS / audio / RSX / movies:** the public README is an install/play guide, not an engineering log of those subsystems. The tree vendors ps3recomp (MIT) and Windows installer binaries (do not run). No verified write-up in the README of JoinTaskset, ATRAC ring, or branch bits. Ideas would have to come from reading their patches later, still without copying.

### InFamous Enhanced Recompilation — link dead

- RetroGems: https://retrogems.fr/en/ports-recomp-decomp/infamous-enhanced-recompilation/ (page HTTP 200).
- Listed GitHub: https://github.com/ibrahimpuri/inFamous-PC-Enhanced — **404**. No clone.

### InFamous 2 PC Port — [bhuiyah/infamous2-recomp](https://github.com/bhuiyah/infamous2-recomp)

- **Method:** ps3recomp, D3D12, no emulator. US `BCUS98125` + 1.04; EU beta.
- **Status:** README presents a native Windows build with screenshots "from the port running on Windows". Extent of a full campaign: غير مؤكد from the sections checked (screenshots and a launcher are not a completion log).
- **License:** MIT. Study copy: `ext/infamous2-recomp`.
- **Testing:** this tree (and/or related forks) published `tools/ground_truth` helpers; `pngstat.py` / `targets.json` were already taken unmodified (MIT) into `testloop_src/third_party/infamous2-recomp/` on 26 Nov 2026.
- Earlier community survey (26 Nov 2026) noted inFamous 2 docs mentioning Edge geometry on SPU ("EG1") and FIFO holes reserved for SPU jobs — relevant to our SPU/SPURS lost-wake class, not proven for Strikeforce.

### God of War: Ascension Port — [rigaz29/Ascension-R](https://github.com/rigaz29/Ascension-R)

- **Method:** ps3recomp (submodule fork `rigaz29/ps3recomp`, branch `gowa`), D3D12, FFmpeg for movies. Kit builds from the player's copy (digital US NPUA80918 or discs + updates through 1.12, per README).
- **Status (README):** boots, plays cinematics, goes through menus into the levels. **Has not been played start to finish**, so later problems are expected. Multiplayer is a beta. Movies decoded with FFmpeg. SPURS is provided by the ps3recomp runtime (README "How it works").
- **License:** MIT. Study copy: `ext/Ascension-R` (submodule not initialized).
- Second tree, also MIT: [otavix010/gow-ascension-pc](https://github.com/otavix010/gow-ascension-pc), study copy `ext/gow-ascension-otavix`. README (Portuguese) claims the campaign was played through on the port (8 Nov 2026, engine 0.11.2), with videos, menus and saves working. That is the author's / named tester's report, not a measurement we repeated.
- Third tree: [bc160201983/GoW-Ascension-Recomp](https://github.com/bc160201983/GoW-Ascension-Recomp) — public beta, author said 0.1.31 was the last update (14 Nov 2026). README lists remaining movie issues: videos can show **black while sound plays** if "Skip cutscenes" is off; they recommend leaving skip on. **We must not adopt cutscene skipping.** Also: box-shaped patches in some floor lighting and shadows; blown-out lighting on AMD — similar *symptoms* to ours, no verified 0x1FF8 write-up in the README.

### Shaderscan — [miroslavdanutalexandru-alt/shaderscan](https://github.com/miroslavdanutalexandru-alt/shaderscan)

- **What it is:** a command-line tool that finds RSX vertex and fragment programs in **the player's own** game files and writes them into a renderer's shader cache so the game can compile them at start-up instead of stuttering mid-play. Described as usable by Resistance ports' launchers (not run here).
- **Back ends (README):** `rpcs3` (Vulkan cache: `raw\*.fp`, `raw\*.vp`, pipeline bins) for Resistance 2/3; `r1d3d12` (the port's own D3D12 cache: `<key>.hlsl` + `<key>.dxbc`) for Resistance: Fall of Man. Vertex analysis includes a **branch walk** to build the instruction mask and jump table.
- **License:** **GPL-2.0-only**, and the README says it **follows RPCS3's ProgramStateCache and is a derivative of it**. Study copy: `ext/shaderscan`. **Do not copy any of this into the port. Do not run the exe.** The idea we may paraphrase: scan the player's disc offline for VP/FP programs and pre-build *our own* D3D12 pipeline cache, written from scratch against our renderer, without RPCS3 hashes or cache layout.
- This does **not** by itself apply `TRANSFORM_BRANCH_BITS` at draw time. It is about cache seeding and stutter, not the dark-lighting uniform bug.

### Bleach: Soul Resurrección — [xPXavierx/bleach-soul-resurreccion-recomp](https://github.com/xPXavierx/bleach-soul-resurreccion-recomp)

- Koei Tecmo action game, same era as Strikeforce, US `BLUS30769`, ps3recomp, DirectX 12, Windows Setup that recompiles on the player's PC.
- RetroGems card URL in the catalogue HTML is double-encoded and 404'd when fetched directly; the GitHub URL in the page's JSON-LD is the working official link (HTTP 200).
- README offers 720p–4K, 30/60/120 fps, a launcher, and lists only ultrawide HUD issues as "known". It does not include a campaign-completion log. غير مؤكد how much of the game is cleared on the port.
- Movies: FFmpeg (README credits it as "GPL v3" — we should not take their FFmpeg build; prefer a shared LGPL build as other ports do). Setup uses RPCS3 only to decrypt EBOOT / read a PUP for fonts (author's claim); the game is not said to run on RPCS3.
- **License:** no root LICENSE. Study only. Clone: `ext/bleach-soul-resurreccion-recomp`.
- No public README section found in this pass that solves SPURS taskset teardown or ATRAC AddStreamData.

### Drakengard 3 — [soyjxck/dod3-recomp](https://github.com/soyjxck/dod3-recomp)

- ps3recomp, D3D12 / Metal / Vulkan. Study copy: `ext/dod3-recomp`, MIT.
- **Status (README):** Windows D3D12 **playable**; 60 fps at 4K on an RTX 4090 / i9-13900K in chapter 1 through a heavy destruction scene, open areas, and the village. macOS Metal playable at 60 fps 1080p battle on an M1 Pro. Linux Vulkan experimental.
- **Testing (high value):** `tools/replay_regress.sh` + `tools/compare_frames.py` — a golden-image render regression gate (`rsx_replay`). MIT copies of the compare helpers are already in `testloop_src/third_party/dod3-recomp/`. This is the clearest published auto-check pattern for "does this frame still look like the original."

### White Knight Chronicles II — [WK2D/White-Knight-Chronicles-2-Recomp](https://github.com/WK2D/White-Knight-Chronicles-2-Recomp)

- ps3recomp SDK, MIT. Study copy: `ext/White-Knight-Chronicles-2-Recomp`. Work starts with WKC1, which is on the disc.
- **Status (README):** early development. Native Windows build reaches the WKC1 starting town and can resume from a local save. Startup screens, title menus, **movie playback** and avatar creation are listed as working. A complete playthrough is not claimed.
- Docs pointer: `docs/SUBSYSTEMS.md` (renderer, movie decoding, early SPURS and RSX notes). Not fully extracted in this pass; read from the study copy if we need file:line later.

### Resistance 3

Two different projects:

- RetroGems "Resistance 3 Recompilation" → [n0madic/Resistance3-recomp](https://github.com/n0madic/Resistance3-recomp). ps3recomp, Windows / macOS Metal. README: playable in the opening chapters (Haven), single-player only, expect rough edges later. Patches grouped by subject including **SPURS**. **GPL-3.0-or-later.** Study copy: `ext/Resistance3-recomp`. **Do not copy code.**
- RetroGems "Resistance 3 PC Port" → [miroslavdanutalexandru-alt/Resistance3Port](https://github.com/miroslavdanutalexandru-alt/Resistance3Port) (HTTP 200). Shaderscan's README says this port's shader back end is **`rpcs3`** (RPCS3 Vulkan cache). Treat it as mixed with an RPCS3-derived renderer path. Not cloned in this pass (RPCS3-adjacent). Ideas only, no code.

Upstream [PR #757](https://github.com/sp00nznet/ps3recomp/pull/757) (open) was motivated by Resistance 3's effects uber-shader: BRB/CLB on `SET_TRANSFORM_BRANCH_BITS` (method **0x1FF8**), bits changing between draws, many shader variants, multi-second freezes. That PR is the closest published write-up of **our lighting issue (3)**.

### Gran Turismo 5 — [MormonFTP-hub/gt5-recomp](https://github.com/MormonFTP-hub/gt5-recomp)

- ps3recomp, MIT. Study copy: `ext/gt5-recomp`.
- **Status (README "Current state"):** **Playable.** Races 45–58 fps on the tested rig (i9-14900KF + RTX 4070 Ti SUPER). Most modes work; the full board is in their status doc.
- Movies: FFmpeg on Linux is listed as a requirement. The README says that since v0.1.21 a **frozen opening movie is skipped**. **Do not copy that behaviour** (cutscenes are never skipped on our port).
- Shader precompile: some pipelines are compiled during setup; special post-process / 2D shaders may still be found at run time.

### Sonic the Hedgehog (2006) — [DrummingBird1/sonic06-recomp](https://github.com/DrummingBird1/sonic06-recomp)

- This is the **PS3** version, statically recompiled with **ps3recomp** (D3D12), not XenonRecomp (Xbox 360). MIT. Study copy: `ext/sonic06-recomp`. Launcher name: Soleanna.
- **Status (README table):** menus, movies, story up to Soleanna's town, with **music and voices**. Badge: work in progress. Not a full-game claim.
- Movies: FFmpeg 8 (LGPL) downloaded by the launcher. 47 local ps3recomp patches in `patches/ps3recomp`.

---

## 3. Other real projects worth listing (shorter)

Verified as existing public trees in this pass (HTTP 200 unless noted). Not all were cloned.

| Project | Link | Method | Status as stated by the project | Notes for us |
|---|---|---|---|---|
| ps3recomp toolkit | https://github.com/sp00nznet/ps3recomp | Static recomp runtime (MIT). README forbids RPCS3/GPL code in that tree. | Toolkit, not a game. | Our port's foundation. PRs #809, #757, #485, #215, #812 are the shared fixes. |
| Guitar Hero III | https://github.com/sp00nznet/gh3 | ps3recomp, MIT. Clone: `ext/gh3`. | Boots through intro **movies**, menus, save load, into gameplay with song audio. The game's **own bot** completed **45 of 45** Quickplay songs, none failed (README Status, 2026-09). | Best published auto-play example. Song audio was starving until 27 Sep 2026 (fixed in ps3recomp). |
| The Simpsons Arcade | https://github.com/sp00nznet/simpsonsarcade-ps3 | ps3recomp | Playable, including online via a PSN stand-in, per the toolkit README / catalogues. | ATRAC3plus music mentioned in the toolkit README. Not cloned this pass. |
| Demon's Souls | https://github.com/timboat/demons-souls-recomp | ps3recomp, D3D12 | README: the whole game is playable, with sound, music and movies. 60 fps recommended; above 60, sound can drift. | Movie + audio sync at unlocked fps is a lesson, not a copyable patch. |
| Tokyo Jungle | https://github.com/sp00nznet/tokyojungle | ps3recomp | Not a finished playable game in the README; boot-blocker documented. | SGX audio thread deadlocked on SPURS finalize (queues cancelled so waiters get canceled); `cellSpursAttachLv2EventQueue` had been dropping the queue id. Same family as lost SPURS wakeups. |
| Tornado Outbreak | https://github.com/sp00nznet/tornado | ps3recomp | In-game, first level under stick control, no per-title overrides, per toolkit README. | Runtime fixes named there include **vertex-program flow control** (branch bits family). |
| Ratchet & Clank: Tools of Destruction | https://github.com/Re-TeRo17/ratchet-tod-recomp | ps3recomp, D3D12 | README claims every level loads; later planets less tested. | Not cloned this pass. |
| Qwark's Awakening (Ratchet series launcher) | RetroGems card + project page | ps3recomp (catalogue) | In progress on recomp.fyi. | Not cloned. |
| Sly Cooper: Thieves in Time | https://github.com/mvieira-hub/sly4-port | README: native Windows, static recomp of PPU/SPU, Vulkan | First level playable; not the full game, per README. | Not a decomp. Separate PS2-era Sly decomps (sly1, sly3-decomp, etc.) are not PS3 native ports. |
| XenonRecomp | https://github.com/hedge-dev/XenonRecomp | Xbox 360 XEX → C++ (not a runtime) | Tool only. | Hook style and PPC tests; not PS3. |
| UnleashedRecomp | https://github.com/hedge-dev/UnleashedRecomp | XenonRecomp + a runtime (Sonic Unleashed, 360) | Well-known playable 360 port. | Audio backend and test dumps are 360-specific. Comparable lesson: regression tests around the recompiler, not a copy of their APU code. |
| Killzone 3 / 2 (Project Helghast / Pyrrhus) | https://undecuple.github.io/project-helghast/site/ and pyrrhus site | ps3recomp (catalogues) | Early / in-progress in catalogues. | Long public gist of general runtime fixes: https://gist.github.com/undecuple/2845432bf13e485634de122084d3fd56 (HTTP 200) — SPURS taskset bitsets, Taskset2, create-vs-scan races. Ideas + file:line if we read it; no gist code into the port. |
| Yakuza: Dead Souls | listed on recomp.fyi | ps3recomp | In progress on the board. | Mentioned in `docs/FIRMWARE_LLE.md` as the title that validated lifted SPURS. |

`portedgames.com` and RetroGems also list other titles (Killzone HD, Bakugan, PES 2013, etc.). Those were not individually verified beyond the catalogue pages in this pass.

---

## 4. Mapping onto Strikeforce issues 1–5

### 1. Hang at stage change: old SPURS tasks never stop; taskset re-created at the same address

**What others actually did**

- **Folklore** (job chains, not tasksets): area load shuts the chain down and builds it again; Join must wait until a chain waiting at its guard has ended. They specified this from a golden trace of real libsre, then wrote a native runner. Source: `folklore/docs/SPURS.md` in `ext/folklore-decomp` (and the GitHub raw file, HTTP 200).
- **Upstream PR #809** (open): `cellSpursJoinTaskset` was a stub returning success immediately; firmware waits until the taskset is finished. Fix proposal: wait until the ENABLED bitset is zero, 10 s bound, then BUSY. This is the closest match to *our* API (taskset).
- **PR #833 / #711**: job-chain shutdown must not clear `running` until in-flight work has drained, or Join returns too early and the title reads garbage / hangs.
- **Tokyo Jungle**: finalize vs audio thread waiting on a completion that can never arrive; cancel the queues so waiters leave.
- **Killzone gist**: taskset bitset updates under the same lock-line lock the SPU uses; claim the slot before setting ready bits; mask `task_info.elf` flags.
- **Firmware LLE** (ps3recomp doc; Folklore's earlier path): run the real scheduler from the player's own `libsre.prx` when HLE is the suspect. Proven publicly on one title only. Needs Saud's OK; firmware stays off this tree.

**What we can apply (ideas only)**

1. Make Join/Shutdown/Destroy wait for the *old* taskset's tasks to actually exit before a new taskset is created at the same guest address. Log if bits remain set or if Join would have returned early. Align with the intent of PR #809, implemented in our own HLE, on the test copy only, after Saud's OK for a behaviour change.
2. Record a teardown trace at village / stage change (which NIDs, which addresses, whether ENABLED/running bits clear) and compare with Folklore's "shape trace" idea — our own log format, not their code.
3. Optional diagnosis only: firmware LLE comparison, if Saud approves, never checked into a shared folder.

### 2. ATRAC3 BGM garbage: AddStreamData copied the ring before the async fill; voices never decoded

**What others actually did**

- No public write-up was found that names `cellAtracAddStreamData` copying a still-empty ring on a ps3recomp port. غير مؤكد that any published port hit this exact function.
- **Folklore's movie AIO bug is the same producer/consumer mistake:** completion ran inside submit, so the guest's "data is now there" handshake was wrong, and the decoder saw no data. Fix: complete the async read on a worker, then let the guest observe the fill.
- GH3: song audio starving (fixed in ps3recomp, 27 Sep 2026); confirm by ear.
- Sonic 06 README claims music **and voices** work up to Soleanna town — useful as a target, not as a patch.
- ps3recomp module status still marks media decoders (cellVdec, cellAdec, cellAtrac, …) as partial. cellAtrac is described in the toolkit README as ATRAC3plus, all-in-memory, in that summary table — streaming rings may still be thin. غير مؤكد without a line-level read of our current `cellAtrac.c`.
- PSP / PPSSPP notes (different console) agree that `AddStreamData` only *notifies* that bytes were written at the `GetStreamDataInfo` pointer; it must not invent or copy unread data. Use as a behaviour reminder, not as code.

**What we can apply**

1. Treat AddStreamData as a notify, not as a copy of unread ring memory. Only advance after the guest's async fill is visible, or wait on that fill — same ordering Folklore used for `cellFsAioRead`.
2. Investigate voices as a separate path (silent vs quiet). Confirm whether they use cellAtrac, cellAdec, or another module. Do not assume the BGM ring fix unmutes speech until a log shows decode starting.
3. Do not copy PPSSPP, RPCS3, or `at3_standalone` unless that code is already in *our* MIT tree and already approved.

### 3. RSX vertex branch bits (`TRANSFORM_BRANCH_BITS` 0x1FF8) not applied → dark lighting; shadow acne

**What others actually did**

- **PR #485** (merged): vertex programs **branch on** the transform branch bits (BRB/CLB, leaders up to slot 544).
- **PR #757** (open): #485 **baked** the bit outcome into the program text and keyed the pipeline on the bits, so every new value was a new shader (Resistance 3 froze for seconds). The follow-up passes the bits **at run time** in the VP epilogue (a uniform test), one program for every value, on the engine, live-draw, and **D3D12 / Metal / Vulkan** paths. Tests check that bit 5 on/off changes the draw **without** compiling a new shader.
- This is exactly method **0x1FF8**. If our D3D12 path still uses a stale or default baked value, lighting can stay dark even when #485 is "in the tree."
- Shadow acne is a separate family: upstream `docs/SHADOW_COMPARISON.md` (compare on depth textures, PCF). The 26 Nov community survey found the compare path on the shared draw engine may not reach our D3D12 vtable path. Polygon-offset changes remain gated on Saud's OK.
- Shaderscan's branch walk is for **cache keys**, and the tool is GPL / RPCS3-derived — do not copy. Bilal's Ascension README mentions lighting/shadow artifacts but recommends skipping movies, which we will not do.

**What we can apply**

1. Verify, with a log, that every draw on **our D3D12 path** uploads the current `0x1FF8` bits into the vertex program. If they are baked once or left from a previous decompile, adopt the *idea* of PR #757 (bits as a per-draw uniform), written in our files, on the test copy, after approval.
2. Keep shadow acne on the shadow-compare / depth-bias track; do not assume branch bits fix stripes.
3. If we want less stutter while compiling variants, write our **own** D3D12 cache warmer from our renderer’s format. Do not import shaderscan.

### 4. Cutscene / movie (MPEG-2 / cellVdec) playback, SPU timing

**What others actually did**

- Common pattern: **cellVdec + FFmpeg loaded at run time** (PR #215, #380). Folklore, Ascension-R, Sonic 06, Bleach, and others document this. Keep FFmpeg as a shared LGPL build, not a GPL build.
- Folklore: MPEG-2 `.m2v_`; AIO-too-early fix; do not skip logos by default (they offer a skip-*after*-a-moment option in the menu — our rule is still: never skip cutscenes in tests).
- PR #812 (open): present a decoded picture only after the RSX FIFO walker has caught up.
- GT5 skipping a frozen opening movie: **do not copy**.
- Bilal Ascension: black video with audio; their workaround is skip — **do not copy**.
- GoW3-nx: "cellVdec without FFmpeg" on Switch; not playable; not a PC recipe.

**What we can apply**

1. Keep cutscenes running; fix ordering (AIO/AU availability, FIFO catch-up) rather than skipping.
2. Check SPU job placements during movies (Folklore had to lift the same job at several local-store addresses or the picture died when audio started).
3. Timestamp / frame-rate fields from PR #380's *behaviour*, if our cellVdec still lacks them.

### 5. Testing approach (auto-play, savestates, teleport, replay)

**What others actually did**

- **GH3:** the game's **own bot** cleared all 45 Quickplay songs — best published "let the game play itself" example (`ext/gh3`, README Status).
- **Drakengard 3:** `rsx_replay` + frame compare with a documented pixel tolerance (`ext/dod3-recomp/tools/`, already partially reused under MIT).
- **ps3recomp `tools/regress.py`:** milestone log vs golden, optional screenshot diff.
- **Folklore:** SPURS shape traces vs libsre; render capture; motion watch. Save-slot import/export with RPCS3 saves (their feature, not a request to run RPCS3).
- **inFamous 2:** ground-truth PNG stats (already on the box).
- **XenonRecomp / UnleashedRecomp:** recompiler unit tests and (for Unleashed) audio dumps — 360 only, conceptual.
- No well-documented **teleport** or **savestate** harness for ps3recomp ports was verified in this pass, beyond Folklore's save-slot UI and ordinary in-game saves. غير مؤكد.

**What we can apply**

1. Keep expanding our own log-gated runs and golden frames (dod3 tolerance rule, already in testloop).
2. For the 48 stubs: a teleport/debug jump is our own tool; other ports did not publish a ready-made one we can take.
3. If a title has an in-game bot or attract mode, use that before inventing pad scripts. Never inject pad presses during cutscenes.
4. A SPURS teardown "shape" log at stage change would pay for itself (issue 1).

---

## 5. What we can apply — short list

1. **Issue 1:** Implement Join/Shutdown wait-until-idle for tasksets before re-create at the same address (intent of open PR #809; Folklore's area-load teardown as the worked example, different API). Trace first, behaviour change only with Saud's OK, test copy only.
2. **Issue 2:** Do not let HLE consume a streaming buffer before the guest async fill is visible (Folklore `cellFsAioRead` / movie_995). Treat `AddStreamData` as notify-after-write. Investigate the voice path separately.
3. **Issue 3:** Confirm D3D12 uploads `TRANSFORM_BRANCH_BITS` (0x1FF8) **per draw** (intent of open PR #757, building on merged #485). Shadow acne stays on the compare/bias track.
4. **Issue 4:** cellVdec + LGPL FFmpeg, picture after FIFO catch-up (PR #812 idea), no skipped cutscenes, watch SPU job placements during movies.
5. **Issue 5:** dod3-style frame compare (already MIT-copied), GH3-style "use the game's own bot if any", Folklore-style SPURS traces. Write our own cache warmer if needed; never import shaderscan or RPCS3 caches.

---

## 6. Link check

Fetched 27 Nov 2026. HTTP 200 unless stated.

- RetroGems PS3 catalogue and the priority cards listed above: 200. Bleach's catalogue URL is double-encoded and 404'd; GitHub from JSON-LD is 200.
- All GitHub repos and PRs cited in this file: 200, except **ibrahimpuri/inFamous-PC-Enhanced = 404**.
- Raw docs used: Folklore README, `folklore/docs/SPURS.md`, `STATUS.md`, `LICENSE`; other project READMEs; ps3recomp PRs #809, #833, #757, #485, #215, #812, #380, #711; Killzone gist; recomp.fyi toolchain page.

## 7. What this pass did not do

- Did not touch Saud's PC, did not run any port's binary or Setup, did not download Folklore (or other) release zips, did not download the RetroGems app, did not copy GPL or RPCS3-derived code into the port, did not add a skill.
- Did not play any of these games to confirm the authors' status tables.
- Study clones: see `/workspace/sf-shared/ext/LICENSES.md`.

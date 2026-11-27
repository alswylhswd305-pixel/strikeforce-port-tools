# strikeforce-port-tools

**Author: Saud Alsuwailih (سعود الصويلح)**

Private collection of **tools, patches, and method docs** written while porting *Dynasty Warriors: Strikeforce* (PS3, BLUS30471) to a native Windows build with [ps3recomp](https://github.com/sp00nznet/ps3recomp).

The same tools and method are meant to be reused on **another PS3 game you legally own**.

> **Start here if you want to convert your own game:** [docs/GUIDE_A_TO_Z.md](docs/GUIDE_A_TO_Z.md) (English) · [docs/GUIDE_A_TO_Z_ar.md](docs/GUIDE_A_TO_Z_ar.md) (Arabic)

## Arabic summary / ملخص عربي

هذا المستودع خاص: فيه الأدوات والتصليحات والشرح اللي كتبناها وإحنا نحوّل اللعبة من PS3 إلى الحاسوب، **بدون أي ملف من اللعبة**. اللاعب لازم تكون عنده نسخته الأصلية القانونية، يحط ملف اللعبة (EBOOT) بنفسه، والأداة تحوّله على جهازه. الدليل الكامل من الألف إلى الياء: `docs/GUIDE_A_TO_Z_ar.md`.

ما فيه رخصة مفتوحة حالياً (كل الحقوق محفوظة).

## What is not in this repository

No disc files, no `EBOOT` / ELF / SELF, no ISO, no `PARAM.SFO`, no firmware / PRX / `dev_flash`, no keys, no recompiled or lifted game code, no exes / dlls / pdbs, no screenshots or recordings of the game, no memory dumps, no third-party clones (including GPL / RPCS3-derived source), and no secrets. Users must supply **their own legally dumped copy**.

## Status (2026-11-27, Asia/Kuwait)

The port boots natively (no emulator), plays movies, and reaches in-stage play. Remaining work includes character voice, lighting, and a stage-transition hang. This is a research tree, not a finished release. Do not invent a completion percentage.

An earlier writeup covered the first title-screen boot only; that text is kept in `docs/METHOD.md` with the later guide and playbook.

## Contents

| Path | What it is |
|---|---|
| `docs/GUIDE_A_TO_Z.md` | A-to-Z method: legal dump → toolchain → lift → boot → HLE/NID → movies, pad, ATRAC, RSX, SPURS, test loop |
| `docs/GUIDE_A_TO_Z_ar.md` | Same guide in simple Arabic |
| `docs/METHOD.md` | Early method writeup (title-screen era) plus pointers to later work |
| `docs/ps3_recomp_playbook.md` | Ordered playbook: symptoms, diagnostics, verified laws, flags |
| `docs/TEAM_RULES.md`, `docs/findings.md` | Team rules and dated findings |
| `docs/research/` | Research reports we wrote (layouts, audio, graphics, other ports, …) |
| `port/` | Our clean-room HLE includes (video out, LFQueue, l10n, knobs, movies, audio) |
| `patches/` | Our diffs / apply scripts against ps3recomp (boot, movies, audio, branch-bits, SPURS). Not a copy of upstream C files |
| `scripts/` | Windows setup / copy-disc / lift / build / run (parameterised; local paths stay in a git-ignored env file) |
| `tools/nid-autolink/` | Classify and probe imported NIDs |
| `tools/atrac-validator/` | Read-only ATRAC3plus header / frame / log checks |
| `tools/replay/` | Pad replay sequences |
| `tools/voicefreeze/` | Voice/hang analysis, lifecycle logger, hang watchdog |
| `tools/rsx_census/` | RSX method census hook + report |
| `tools/gfx_bisect/` | Align and compare port vs RPCS3 screenshots (you supply the shots) |
| `tools/testloop/` | One-click test loop (Arabic menu) |
| `tools/sfauto/` and `tools/pc-helpers/` | Run helpers: capture, hang report, window place, pack, step, … |
| `tools/movie/` | Movie/PAMF helpers and the latest movie `.inc` |
| `tools/stubs48/` | Census of still-stub HLE imports |
| `tools/progress/` | Progress counters (counts + sources, not a single %) |
| `autotester/` | Tester kit: pad driver, teleport, movie guard, npc bot, coverage |

## License

**No license file is included.** All rights reserved, unless the owner later publishes a license.

A November 2026 draft tree briefly carried an AGPL-3.0 text; **that license is not applied here.** Upstream ps3recomp and any third-party tools you clone yourself have their own terms. MIT comparison helpers used on the test loop (from other ports) are **not** copied into this repo; see `tools/testloop/third_party/SOURCES.md` for the upstream URLs if you want to fetch them yourself.

## Requirements (for someone converting their own game)

You supply, and never commit: your own dump, your decrypted `EBOOT.elf`, and official firmware in your own RPCS3 `dev_flash`. See the A-to-Z guide for the toolchain list (VS 2022 Build Tools, clang-cl, CMake, Ninja, Python, Git).

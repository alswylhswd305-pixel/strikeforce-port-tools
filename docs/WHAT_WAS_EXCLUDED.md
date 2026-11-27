# What was left out of this snapshot

This list is for the owner. It records classes of files that were intentionally not uploaded.

- Game data: EBOOT, ISO, PARAM.SFO, disc trees, caches, saves, textures, audio dumps, movies.
- Recompiled / lifted game code (including `sailwrap.txt` and `port/recompiled`).
- Firmware / PRX / `dev_flash` / SPRX.
- Memory dumps, exes, dlls, pdbs.
- Screenshots and recordings of the game (including the old title-screen image).
- Run logs, RPCS3 logs, guest-dump logs, `coverage.json` traces with local paths.
- `/workspace/sf-shared/ext` and other third-party clones (Folklore, inFamous, …).
- GPL / RPCS3 source copies that were on the research box for reading only.
- Full `base/` and `patched/` C copies of ps3recomp files; only our `.diff` / apply scripts are here.
- MIT comparison helpers from other ports (URLs recorded in `tools/testloop/third_party/SOURCES.md`).
- Noto Naskh Arabic font binary (OFL); download separately if needed.
- v58 Open Sesame patches (unrelated project).
- Launchers, test-loop scripts, and example configs were sanitized: absolute machine paths (home directory, EBOOT, dev_flash, local Python, portable LLVM) were replaced with placeholders such as `<TEST_COPY>`, `<SF_ELF>`, `<PS3_DEV_FLASH>`, `<LLVM_BIN>`.
- Secrets / keys / tokens: scanned before commit; none should be present.
- The repo is licensed AGPL-3.0 (`LICENSE`, `NOTICE`); ps3recomp-derived patches keep MIT.

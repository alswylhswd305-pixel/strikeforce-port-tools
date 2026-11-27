# Third-party code (MIT only) — copied unmodified

| Folder | Files | Source | Commit (last change of the file) | License |
|---|---|---|---|---|
| dod3-recomp/ | compare_frames.py, ppm.py | https://github.com/soyjxck/dod3-recomp/blob/main/tools/compare_frames.py , https://github.com/soyjxck/dod3-recomp/blob/main/tools/ppm.py | cd2dfd3ddb573932938000d30c6dd23d4103ef38 (2026-10-08) | MIT, dod3-recomp/LICENSE |
| infamous2-recomp/ | pngstat.py, targets.json | https://github.com/bhuiyah/infamous2-recomp/tree/main/tools/ground_truth | cc9e42f6c4f76c3f7fc4f498950092b9f2bac0c6 (2026-11-11) | MIT, infamous2-recomp/LICENSE |

Fetched 2026-11-26 ~21:00 Asia/Kuwait. Files are byte-for-byte as published.

How testloop uses them:
- `compare.py` applies the dod3 tolerance rule (noise = <=16 px off by <=4 levels; close = >=99% of pixels within --tol levels, worst pixel ignored) with numpy, and you can still run the original `compare_frames.py` on PPM folders.
- `compare.py` imports `pngstat.stats()` for per-region colour/luma stats (e.g. "is the ground still white").
- ps3recomp `tools/regress.py` (in our own tree, not copied) is imported read-only by `testloop.py` for its milestone-log `parse_log()` / `diff()`. `regress_strikeforce_entry.toml` here is a PROPOSED registry entry; it is NOT added to ps3recomp/tools/regress_ports.toml (no edits to the ps3recomp tree without Saud's OK).

No package was installed. Needs on the PC (already present): Python 3.12, Pillow, numpy, opencv (cv2). Not present and not needed: scikit-image, arabic_reshaper, python-bidi (Arabic shaping is done by our own arabic_shape.py).

# Code table (RPCS3 cache vs ps3recomp lift)


Built by `trace/build_table.py` from **read-only** RPCS3 cache files
(`cache/BLUS30471/ppu-fbQP…-EBOOT.BIN/`) and the v0.20.0 test folder. Full table: `code_table.csv`
(238,669 numbered rows: 2,071 SPU + 236,598 PPU). Totals: `summary.json`.

## SPU: what RPCS3 actually ran (spu-safe-v1-tane.dat), matched to the 41 SPU images in EBOOT
| status | programs |
|---|---|
| entry is a function ps3recomp lifted | 1,086 |
| inside a lifted image (not a listed function entry) | 483 |
| **inside the image v0.20.0 cannot lift (375200614, overlapping PT_LOAD)** | **226** |
| matches no EBOOT image (likely firmware SPURS/taskset kernel or SPU code loaded from data files) | 276 |

- 40 of 41 EBOOT SPU images ran in RPCS3. Only image 524173051 never appeared.
- The image v0.20.0 skips, 375200614, is the **2nd most-used** SPU image (226 programs, after 454077064 with 267). Lifting it is required, not optional.
- The graphics image 437063289, which our port runs today, accounts for 100 programs.

## PPU: RPCS3 labels vs ps3recomp lift
| | count |
|---|---|
| RPCS3 `__0x` labels (PPU LLVM cache) | 236,598 |
| that are exactly a ps3recomp lifted function entry | 17,806 |
| inside the lifted range (blocks, or entries ps3recomp merged into a bigger function) | 218,792 |
| outside the lifted range | 0 |
| ps3recomp lifted entries that RPCS3 has no label for | 5,853 |

Reading: RPCS3's labels are block-level (about 10 per function), so nothing of the EBOOT's code is outside our lift.
The 5,853 entries with no RPCS3 label are candidates for false function starts on our side (data misread as code, or split points).
They are worth checking, but they are not a gap. The PPU labels are static (precompiled), not proof the code ran.
Runtime PPU coverage comes from sfauto runs / lift_hooks instead.

The full CSV (238,669 rows of addresses) is generated locally by `tools/trace/build_table.py` and is not committed.

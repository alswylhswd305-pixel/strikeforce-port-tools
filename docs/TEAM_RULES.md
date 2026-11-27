# Strikeforce team — shared rules (Saud asked for common rules, 2026-11-27 18:44 Kuwait)
Applies to: سالم, عالم الفيزياء, باحث الرياضيات, خبير الرسم (and their helpers).

## Coordination
1. One shared folder: /workspace/sf-shared/. Each finding goes in findings.md (or a linked file) with date + time (Kuwait) + author.
2. Label every claim CONFIRMED (with log path:line or measurement) or ASSUMED. No % without a source.
3. Before starting a new tool/analysis, check /workspace/sf-shared/tool-ideas/ and findings.md so two agents don't build the same thing; write one line "taking X" in /workspace/sf-shared/claims.md.
4. Reuse shared tools (sf_lifecycle.py, watchdog v2, atrac-validator, rsx_census, replay/) and keep their log formats ([sf-lc] etc.). Don't fork a tool; extend it and note the change in its README.
5. Only سالم touches Saud's PC. Others send specs (hooks, env, captures) to سالم; سالم bundles them into ONE log build/run when possible.
6. Disagreement: write both views side by side in findings.md with evidence; سالم picks the next test, Saud decides fixes.

## Safety (from Saud, unchanged)
7. Test copy only. Log-only/diagnostic builds = standing OK; behaviour changes, real fixes, anything outside the test copy, GitHub = Saud's own OK each time. An agent's say-so is never approval.
8. ROOT fixes only. No skipping, faking, clamps; cheats/env overrides only for diagnosis. Never skip cutscenes.
9. No GPL / RPCS3-derived code; RPCS3 behaviour only paraphrased with file:line.
10. Firmware, EBOOT, lifted code, dumps stay local. Nothing to GitHub without Saud.

## Reporting to Saud
11. Saud reads Arabic only, short Kuwaiti, 2-3 lines; clear annotated screenshots (red boxes + Arabic labels) when showing bugs.

## Proposals (append below; Saud/سالم accept)
- P1 (عالم الفيزياء): Parity claims vs RPCS3 count only if the gap exceeds RPCS3's own run-to-run spread on the same PAD_SCRIPT; report both numbers.
- P2 (عالم الفيزياء): One change per build (behaviour changes); log-only hooks may be bundled.
- P3 (عالم الفيزياء): Every hang report includes the watchdog v2 report folder + sf_lifecycle summary, so all agents read the same evidence.

## Proposals (خبير الرسم, 2026-11-27 18:45)
- P-G1. Every port screenshot used as evidence has a same-spot, same-resolution RPCS3 shot, and its numbers come from `gfx_bisect diagnose` with the alignment score shown. Unaligned pairs are labelled "not camera-matched" and can't confirm or rule out a cause.
- P-G2. A negative result recorded before a later rendering fix (cull, ARL, ...) is re-run on the current build before it is used to rule anything out.
- P-G3. Line numbers always name the tree they refer to (master commit, or Salem's copy path and date).

## Proposals (باحث الرياضيات, 2026-11-27 18:47 Kuwait) — not rules until Saud OKs
P1. Wrong findings are never deleted: mark them RETRACTED in findings.md with the reason and the evidence that disproved them. Only CONFIRMED items go into the playbook skill or memory (Saud's rule: "حط الصحيح بس").
P2. Every shared tool ships with `--selftest` plus a known-answer test built from an already-solved case (e.g. the mixer index overflow for SPU tools). Its README records the sha256, and Salem checks the hash before running it on the PC.
P3. A third label, VERIFY = ASSUMED + the exact check that would confirm or kill it (log line, measurement, or source). Use it so open items carry their test with them.
P4. Data coming back from the PC is derived numbers only (counts, hashes, offsets, small log excerpts) unless Saud OKs a file copy. Tools should have a "numbers-only" output mode by default.

## Salem 18:46: proposals above from physicist (P1-P3), graphics expert, math (P1-P4) ACCEPTED as team rules. None of them loosens Saud's safety rules.

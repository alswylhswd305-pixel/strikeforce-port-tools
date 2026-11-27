# docs/hle_spec: one spec per import (`<lib>/<func>.md`)

Each file starts with YAML-like front matter that `nid_autolink.py --mode rank/poison` reads.
Hand-researched files are produced by `specgen/write_specs.py` (17 so far: cellPamf 1, cellAudioOut 2,
sceNp 1, OSK 13). Every other file is an UNRESEARCHED template; nothing in a template is verified.

Labels used: KNOWN = two independent sources or measured; ASSUMED = one source, or reasoning;
VERIFY = still to check. RPCS3 (GPL-2) was read only to describe behaviour; no code was copied.

Rule: a documented error return is acceptable ONLY when it is what real hardware returns in that
situation (for example offline / not signed in). An output pointer must still be written whenever
hardware writes it.

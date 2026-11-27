# nid_autolink.py — أداة ربط دوال النظام (NIDs) / NID auto-link helper

## بالعربي (مختصر)

**وش تسوي؟** تقرا قائمة دوال النظام اللي تطلبها اللعبة (346)، وتعرف اسم كل وحدة بنفسها (SHA-1)،
وتدوّر في سورس ps3recomp والبورت: مربوطة صح؟ دمية (stub)؟ ناقصة؟ بعدين ترتّبها بالأهمية
وتطلع ملف هياكل (skeletons) **يسجّل كل نداء** للدوال الناقصة.

**قواعد الأمان:**
- قراءة بس. ما تكتب إلا داخل مجلد `--out` الجديد (وترفض إذا كان داخل السورس).
- بايثون 3 عادي، بدون تنزيل ولا تثبيت، بدون إنترنت.
- ما تنسخ EBOOT ولا كود مرفوع (lifted) لأي مكان، وتتخطى ملفات الكود المرفوع الكبيرة.
- الهياكل **مو إصلاح**: ترجع نفس CELL_OK اللي يرجعه المسار الحالي، وتشتغل بس إذا `SF_AUTOLINK=1`،
  واسمها في اللوق `[sf-autolink-STUB]`. فايدتها نشوف مين ينادي ووش يرسل، عشان نكتب السلوك الصحيح.

**الخطوات:**
1. `python nid_autolink.py --selftest` ← لازم يطلع `ALL PASS`.
2. شغّل الأمر اللي تحت (قراءة بس).
3. أرسل `summary.md` و `report.csv` (أرقام وأسماء بس، ما فيها كود اللعبة).

## English

### Inputs (pick one import source)
| flag | what | status |
|---|---|---|
| `--imports out/EBOOT.imports.json` | ps3recomp `gen_imports.py` (`lib`) or sfauto (`library`) JSON: `nid`, `stub` | **KNOWN** format (read on the box from the 2026-11-26 copy) |
| `--elf EBOOT.elf` | decrypted ELF, parsed read-only here; also counts `bl` call sites and whether r3 is tested after the call | layout **KNOWN** (two public sources); stub-target meaning **VERIFY** on the real EBOOT — if every `static_sites` is 0, the address interpretation is wrong |
| `--imports list.txt` | lines `<library> 0xNNNNNNNN` | own format |

Other flags: `--src DIR|FILE` (repeat: `ps3recomp/runtime`, `ps3recomp/libs`, `port`, `port/bld/ppu_hle_nids.cpp`),
`--log` (repeat, globs ok: stderr logs, `unresolved_nids.txt`, `*findings.json`), `--names FILE`, `--headers DIR`,
`--weight MODULE=N`, `--exclude REGEX`, `--out NEWDIR`.

### NID formula — KNOWN
`NID = u32_le(SHA1(name || 67 59 65 99 04 25 04 90 56 64 27 49 94 89 74 1A)[0:4])`.
Sources: psdevwiki "NID" page (`_sys_sprintf` → `0xA1F9EAFE`), ps3recomp `tools/nid_database.py`,
mercs2_exemap docs (citing RPCS3 `ppu_generate_id`). Self-test checks 6 published/verified values.

### What is detected in the source tree
- `ps3_hle_register(0x…u, "name", (void*)fn)` — generated table (KNOWN, gen_hle_nids.py)
- `ps3_hle_register_ctx(0x…u | ps3_compute_nid("x"), "label", fn)` — ctx handlers, port `.inc` (KNOWN)
- `{ "name", handler }` tables in files that register by `ps3_compute_nid` (sysNet style) — ASSUMED pattern
- `ps3_hle_register_fast` is ignored (it falls back to the normal handler).
- Liveness one level up: a register function never called → `dead-reg`; only called under
  `if (getenv(...))` / `#if` → `conditional` (e.g. the 7 sys_net calls under `PS3_NET_ONLINE`).
- Winner when several registrations exist: ctx before table (KNOWN: `ps3_hle_call` searches ctx first),
  port before library (ASSUMED from init order).

### Status meanings
`linked` real code · `partial` real code but labelled TODO/stub · `stub` body only logs / zero-fills /
returns a constant · `uncertain` registered but body not found · `conditional` · `dead-reg` · `missing`.
Stub detection is a heuristic — every P1/P2 must be checked by eye.

### Ranking (ASSUMED weights, documented in the script)
score = module weight×10 + call evidence (log counts) + (ELF only) call sites + return-value checked
+ status bonus. cellAtrac is always weight 5 and carries the note about the mixer voice leak /
6-channel AT3P `0x80610315`: `linked` proves registration, not correct behaviour.

### Outputs (only in `--out`)
`summary.md`, `report.csv`, `report.json`, `unnamed_nids.txt`, `sf_autolink_stubs.inc`.

### Using the skeletons (only after Saud approves a build change)
`#include "sf_autolink_stubs.inc"` in `port/stubs.cpp`, call `sf_register_autolink_stubs()` last in
`ps3_load_prx_modules()`, run with `SF_AUTOLINK=1`. Every call logs
`[sf-autolink] STUB name nid=… call#N tid lr r3..r10` (first 8 calls, then powers of two). Feed that log
back with `--log` to get exact counts. Note: while enabled, `PS3_HLE_UNRESOLVED=fail` no longer applies to
these NIDs. One change per build; it is a diagnostic, not a fix.

### Not automatic
Real behaviour (write it from the logged registers, never from GPL source), prototypes that no readable
header declares, and deciding whether a `stub` is harmless.

---

# v2.0: impact ranking, specs, poison test (الإصدار 2)

## بالعربي (مختصر)
- `--mode scan`: هو نفسه v1 (تصنيف من السورس). يشتغل على جهاز سعود للقراءة فقط.
- `--mode callgraph`: للقراءة فقط على جهاز سعود. يقرأ الـ EBOOT المفكوك + `EBOOT.functions.json` ويطلّع `callgraph.json`، وفيه أرقام بس (عناوين، عدد المستدعين، العمق من الـ entry، وهل الدالة تفحص r3 وأي فرع هو الخطأ). ما فيه أي كود أو بايتات من اللعبة.
- `--mode rank`: يشتغل على الصندوق. يقرأ `report.csv` + اللوقات + `callgraph.json` + المواصفات، ويطلّع `master_ranked.md/.csv`، ويسوي قالب مواصفة UNRESEARCHED لكل دالة ما لها مواصفة.
- `--mode poison`: يطلّع `sf_poison.inc`. هذا للتشخيص بس، مطفي افتراضياً، ويشتغل بـ `SF_POISON=<اسم دالة وحدة>` لكل تشغيلة. يعبّي مخرجات الدالة بـ 0xCD عشان نعرف هل اللعبة تقرأها. **مو إصلاح**، وأي بناء فيه يحتاج موافقة سعود (تغيير واحد لكل بناء).

## English
| mode | where | reads | writes (only into --out) |
|---|---|---|---|
| `scan` (default) | Saud's PC, read-only | imports json/ELF, source roots, logs | report.csv/json, summary.md, skeleton .inc |
| `callgraph` | Saud's PC, read-only | decrypted ELF (or lifted C dir + imports json), functions.json, optional report.csv for names | callgraph.json (derived numbers only) |
| `rank` | box | report.csv, logs/findings.json, callgraph.json, docs/hle_spec | master_ranked.md/.csv, missing spec templates |
| `poison` | box | docs/hle_spec front matter (`outputs: r3:4`, `poison_ret: yes`) | sf_poison.inc |

Examples:
```
python nid_autolink.py --selftest
python nid_autolink.py --mode callgraph --elf <EBOOT.elf> --functions out\EBOOT.functions.json --report <pc-results>\report.csv --out callgraph-out
python nid_autolink.py --mode rank --report pc-results/report.csv --callgraph callgraph.json --log "runs/*.json" --functions EBOOT.functions.json --specs docs/hle_spec --out v2-rank
python nid_autolink.py --mode poison --specs docs/hle_spec --out v2-rank
```

**Spec front matter** (`docs/hle_spec/<lib>/<func>.md`):
- `nid`, `lib`, `name`, `status_pc`;
- `verdict` (needs-real-impl | correct-as-documented-error | ok-setting-sink | owned-by-salem | unresearched);
- `signature`;
- `outputs` (e.g. `r3:4, r5:16` = guest output pointer in r3 of 4 bytes; sizes are multiples of 4);
- `poison_ret` (yes = return 0xCDCDCDCD in the poison run);
- `confidence`.

Hand-researched specs are produced by `specgen/write_specs.py`. Behaviour is paraphrased; no GPL code is copied.

**Return-check decode (KNOWN PowerPC encodings).**
- After each `bl stub`, up to 12 instructions are scanned. The decoder tracks r3 and one `mr rX,r3` copy, and recognises cmpwi/cmplwi/cmpw/cmplw and the record forms (`.`).
- The first bc/bclr on that CR field is decoded into `branch_if` (a condition on r3), `taken` and `fallthrough`.
- `error_side` names the branch that runs when r3 < 0 or r3 ≠ 0 (the CELL error convention). ASSUMED: CELL errors are negative s32.

**Poison handlers.**
- A poison handler REPLACES the current handler for its NID for the whole run.
- Call `sf_register_poison()` FIRST: the first matching ctx registration wins (ppu_hle.cpp `hle_slot`, KNOWN in the progress-src copy).
- Include the file after the runtime headers (it needs `ppu_context` and `vm_write32`).

Self-test: 47 checks (29 v1 + 18 v2). It uses synthetic ELF/C/log data only.

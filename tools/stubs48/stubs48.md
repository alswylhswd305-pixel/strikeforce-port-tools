# دوال النظام الفاضية الـ48 (STUB HLE) — سترايك فورس

تاريخ الجرد: 2026-11-27 19:39 Asia/Kuwait (UTC+3)

قراءة فقط من ملفات الصندوق. ما انبنى شيء وما لمسنا جهاز سعود.

## خلاصة

- المصدر: تقرير التصنيف 27 نوفمبر 2026 الساعة 17:19 بتوقيت الكويت (`nid_autolink.py` 1.0): **248 مربوطة، 48 هيكل فارغ، 40 ناقصة، 7 مشروطة، 3 ناقصة جزئياً، من 346**.
- من الـ48: **20 انطلبت** في لوق أو تقرير تشغيل (CONFIRMED)، و**28 مستوردة وما انشافت** في أي لوق موجود على الصندوق (CONFIRMED إنها ما انشافت؛ مو مؤكد إنها ما تنطلب أبد).
- خطاف `SF_HLE_LRLOG` موجود في لوقين: جلسة voicediag 17:27، وجلسة SFRACE 19:01–19:30 (804642 سطر). أرقام العدّ من آخر جرد كامل في SFRACE (السطر 789956، 1163 زوج NID+LR). نسخة movie v5 ولوق 18:17 ولوقات الرسم ما تكتب `[hle-lr]`. الدوال اللي ما انشافت في اللوقين المخطوفين أقوى دليل إنها ما تنطلب بهالمسار (إقلاع→أ→ب)، بس مو إثبات إنها ما تنطلب في قائمة أو شبكة.
- مراحل أ/ب/ج مأخوذة من ملخص `sf_lifecycle.py` (مستنتجة من تجمّعات التحميل). الوسم عليها ASSUMED.

### اللي أغلبه يسبب عطل ظاهر (ASSUMED إلى أن يتحقق جسم الدالة)

- **`cellAtracGetSecondBufferInfo`** (`0xBE07F05E`, cellAtrac, مستوردة وما انشافت, العدّ 0): معلومات المخزن الثاني للصوت. اللعبة تفحص الرجع، والجسم الفاضي ممكن يخرب الستريمنغ.
- **`cellAtracIsSecondBufferNeeded`** (`0x99EFE171`, cellAtrac, مستوردة وما انشافت, العدّ 0): ترجع 0 يعني «ما يحتاج مخزن ثاني». إذا الأغنية تحتاجه، الصوت يخف أو يخرب.
- **`sys_lwcond_signal`** (`0xEF87A695`, sysPrxForUser, انطلبت, العدّ 363392): مصنّفة هيكل فارغ، وانطلبت 363392 مرة في جلسة SFRACE (23832 في voicediag). إذا ما توقّظ المنتظرين، تعليق القرية محتمل. يحتاج تحقق من جسم الدالة.
- **`sys_lwcond_signal_all`** (`0xE9A1BD84`, sysPrxForUser, انطلبت, العدّ 4039883): نفس عائلة إشارة الشرط. خطر على تعليق المرحلة إذا الجسم فاضي.
- **`cellAudioOutConfigure`** (`0x4692AB35`, cellSysutil, مستوردة وما انشافت, العدّ 0): المواصفة تقول لازم تتطبّق إعدادات القنوات؛ الحين ترجع نجاح وتتجاهل الطلب (مرشحة لصوت 6 قنوات).

تعليق القرية لحد الحين مربوط بمهام SPURS اللي ما تتوقف (عالم الفيزياء، CONFIRMED في اللوق). `sys_lwcond_signal` / `signal_all` مرشّح إضافي إذا كان جسمها فاضي فعلاً، مو بديل عن ذاك التحليل. في جلسة SFRACE: `_cellGcmSetFlipCommand` 65157 مرة و`cellKbRead` 65149 مرة (تقريباً مرة لكل إطار، ~37 إطار/ثانية على ~29 دقيقة) — العدّ منطقي.

## جدول الـ48

| الدالة | NID | المكتبة | الحالة | المرحلة / اللحظة | العدّ | الخطورة | الدليل | الوسم |
|---|---|---|---|---|---:|---|---|---|
| `sys_lwcond_signal_all` | `0xE9A1BD84` | sysPrxForUser | انطلبت | إقلاع/أفلام/قوائم ← المرحلة أ (كاش 5050) ← المرحلة ب (كاش 5053) | 4039883 | عالي | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1385 (hle-lr-new) | CONFIRMED/ASSUMED |
| `sys_lwcond_signal` | `0xEF87A695` | sysPrxForUser | انطلبت | إقلاع/أفلام/قوائم ← المرحلة أ (كاش 5050) ← المرحلة ب (كاش 5053) | 363392 | عالي | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:831 (hle-lr-new) | CONFIRMED/ASSUMED |
| `_cellGcmSetFlipCommand` | `0x21397818` | cellGcmSys | انطلبت | إقلاع/أفلام/قوائم ← المرحلة أ (كاش 5050) ← المرحلة ب (كاش 5053) | 65157 | متوسط | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:352 (hle-lr-new) | CONFIRMED/ASSUMED |
| `cellKbRead` | `0xFF0A21B7` | sys_io | انطلبت | إقلاع/أفلام/قوائم ← المرحلة أ (كاش 5050) ← المرحلة ب (كاش 5053) | 65149 | متوسط | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1754 (hle-lr-new) | CONFIRMED/ASSUMED |
| `sys_lwcond_destroy` | `0x1C9A942C` | sysPrxForUser | انطلبت | المرحلة ب (كاش 5053) | 10 | متوسط | sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log:804394 (hle-lr-new) | CONFIRMED/ASSUMED |
| `sys_lwmutex_destroy` | `0xC3476D0C` | sysPrxForUser | انطلبت | إقلاع/أفلام/قوائم ← المرحلة ب (كاش 5053) | 6 | متوسط | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:2348 (hle-lr-new) | CONFIRMED/ASSUMED |
| `cellSailDescriptorSetAutoSelection` | `0x76B1A425` | cellSail | انطلبت | إقلاع/أفلام/قوائم | 5 | منخفض | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:2299 (hle-lr-new) | CONFIRMED/ASSUMED |
| `cellSailGraphicsAdapterSetPreferredFormat` | `0x2E3CCB5E` | cellSail | انطلبت | إقلاع/أفلام/قوائم — movie000.pam، movie001.pam، movie002.pam، movie007.pam | 5 | متوسط | sf-shared/testloop/saud_blackhang_1817_stderr.log:933 (handler-log) | CONFIRMED/ASSUMED |
| `cellSailPlayerAddDescriptor` | `0x7C8DFF3B` | cellSail | انطلبت | إقلاع/أفلام/قوائم — movie000.pam، movie001.pam، movie002.pam، movie007.pam، movie013.pam | 5 | متوسط | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:2313 (hle-lr-new) | CONFIRMED/ASSUMED |
| `cellAudioOutSetCopyControl` | `0xC96E89E9` | cellSysutil | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/saud_blackhang_1817_stdout.log:66 (handler-log) | CONFIRMED/ASSUMED |
| `cellOskDialogSetInitialKeyLayout` | `0xC427890C` | cellSysutil | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/saud_blackhang_1817_stdout.log:2954 (handler-log) | CONFIRMED/ASSUMED |
| `cellOskDialogSetLayoutMode` | `0xF0EC3CCC` | cellSysutil | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/saud_blackhang_1817_stdout.log:2951 (handler-log) | CONFIRMED/ASSUMED |
| `sceNpBasicRegisterContextSensitiveHandler` | `0x4026EAC5` | sceNp | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1723 (hle-lr-new) | CONFIRMED/ASSUMED |
| `_sys_process_at_Exitspawn` | `0x96328741` | sysPrxForUser | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:39 (hle-lr-new) | CONFIRMED/ASSUMED |
| `_sys_process_atexitspawn` | `0x2C847572` | sysPrxForUser | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:38 (hle-lr-new) | CONFIRMED/ASSUMED |
| `sys_net_initialize_network_ex` | `0x139A9E9B` | sys_net | انطلبت | إقلاع/أفلام/قوائم | 1 | منخفض | sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1719 (hle-lr-new) | CONFIRMED/ASSUMED |
| `cellOskDialogExtRegisterForceFinishCallback` | `0xE800F586` | cellOskExtUtility | انطلبت | انطلبت في لوقات الجهاز (تقرير 17:19) — المرحلة مو متعيّنة على الصندوق | 0 | منخفض | autolink-report | CONFIRMED/ASSUMED |
| `cellOskDialogExtSetInitialScale` | `0x75370397` | cellOskExtUtility | انطلبت | انطلبت في لوقات الجهاز (تقرير 17:19) — المرحلة مو متعيّنة على الصندوق | 0 | منخفض | autolink-report | CONFIRMED/ASSUMED |
| `cellOskDialogAddSupportLanguage` | `0x7F21C918` | cellSysutil | انطلبت | انطلبت في لوقات الجهاز (تقرير 17:19) — المرحلة مو متعيّنة على الصندوق | 0 | منخفض | autolink-report | CONFIRMED/ASSUMED |
| `cellOskDialogSetKeyLayoutOption` | `0xB53C54FA` | cellSysutil | انطلبت | انطلبت في لوقات الجهاز (تقرير 17:19) — المرحلة مو متعيّنة على الصندوق | 0 | منخفض | autolink-report | CONFIRMED/ASSUMED |
| `cellAtracGetSecondBufferInfo` | `0xBE07F05E` | cellAtrac | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | عالي | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellAtracIsSecondBufferNeeded` | `0x99EFE171` | cellAtrac | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | عالي | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellGameGetSizeKB` | `0xEF9D42D5` | cellGame | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellGamePatchCheck` | `0xCE4374F6` | cellGame | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellRescSetBufferAddress` | `0x8107277C` | cellResc | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | متوسط | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellSailDescriptorCreateDatabase` | `0x0ABB318B` | cellSail | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | متوسط | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellSailDescriptorDestroyDatabase` | `0x28336E89` | cellSail | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellAudioOutConfigure` | `0x4692AB35` | cellSysutil | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | عالي | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellOskDialogDisableDimmer` | `0x41F20828` | cellSysutil | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellOskDialogSetInitialInputDevice` | `0xF3B4B43E` | cellSysutil | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellOskDialogSetSeparateWindowOption` | `0x53E39DF3` | cellSysutil | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `cellSaveDataDelete2` | `0xEDADD797` | cellSysutil | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellSysutilAvc2InitParam` | `0x89456724` | cellSysutilAvc2 | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellSysutilAvc2SetAttribute` | `0xCCF0AEFF` | cellSysutilAvc2 | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=5 | CONFIRMED/ASSUMED |
| `cellSysutilAvc2StartVoiceDetection` | `0x16FF9BA0` | cellSysutilAvc2 | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellSysutilAvc2StopVoiceDetection` | `0x178982D9` | cellSysutilAvc2 | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `sceNpBasicGetEvent` | `0xE035F7D6` | sceNp | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `sceNpBasicGetFriendListEntry` | `0x04372385` | sceNp | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `sceNpManagerGetChatRestrictionFlag` | `0xEB7A3D84` | sceNp | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=3 | CONFIRMED/ASSUMED |
| `sceNpTusPollAsync` | `0x19BCE18C` | sceNpTus | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `sys_prx_exitspawn_with_level` | `0xA2C7BA64` | sysPrxForUser | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `sys_spu_image_close` | `0xE0DA8EFD` | sysPrxForUser | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `cellFsRmdir` | `0x2796FDF3` | sys_fs | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=0 | CONFIRMED/ASSUMED |
| `cellFsUtime` | `0xBEF554A4` | sys_fs | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=0 | CONFIRMED/ASSUMED |
| `bind` | `0xB0A59804` | sys_net | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=2 | CONFIRMED/ASSUMED |
| `setsockopt` | `0x88F03575` | sys_net | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `socketclose` | `0x6DB6E8CD` | sys_net | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=1 | CONFIRMED/ASSUMED |
| `sys_net_free_thread_context` | `0xFDB8F926` | sys_net | مستوردة وما انشافت | ما انشافت في لوقات الصندوق | 0 | منخفض | استيراد ثابت، مواقع استدعاء=4 | CONFIRMED/ASSUMED |

## English details

### Sources scanned (deduped by md5)

- `/workspace/sf-shared/testloop/saud_blackhang_1817_stdout.log` (3696424 bytes, md5 c6d018548b60…)
- `/workspace/sf-shared/testloop/saud_blackhang_1817_stderr.log` (9584103 bytes, md5 90058808b215…)
- `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log` (7617900 bytes, md5 da4212cf8c37…) — SF_HLE_LRLOG present (`[hle-lr]` 1181, `[hle-lrc]` 20712)
- `/workspace/sf-shared/testloop/hangwatch/watchdog_20261127-181325.log` (210 bytes, md5 6d9d2a49a28a…)
- `/workspace/sf-shared/testloop/hangwatch/watchdog_20261127-190110.log` (324 bytes, md5 2b61af7993dc…)
- `/workspace/sf-shared/testloop/reports/voicediag1786_diag_lines.txt` (7413072 bytes, md5 52a0778d9b74…)
- `/workspace/sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log` (66816687 bytes, md5 817149997801…) — SF_HLE_LRLOG present (`[hle-lr]` 1353, `[hle-lrc]` 92174)
- `/workspace/sf-shared/testloop/sfrace/sfrace_39940.log` (62435688 bytes, md5 544c4cb73c32…)
- `/workspace/sf-gfx-runs/A/stderr.log` (7137894 bytes, md5 4ddc9f606b0f…)
- `/workspace/sf-gfx-runs/A/stdout.log` (5251814 bytes, md5 3c3dd4f3cefc…)
- `/workspace/sf-gfx-runs/B/stderr.log` (4951868 bytes, md5 ac864ead97ae…)
- `/workspace/sf-gfx-runs/B/stdout.log` (4708427 bytes, md5 10c8f36d568b…)
- `/workspace/sf-autotester/selftest/coverage_out.txt` (314 bytes, md5 f5965cf99ffd…)
- `/workspace/sf-autotester/selftest/coverage_out.json` (1298 bytes, md5 25b37a4d699f…)
- `/workspace/sf-autotester/selftest/mid_movie.log` (36 bytes, md5 dd5591195ab8…)
- `/workspace/sf-autotester/selftest/coverage_out2.json` (1347 bytes, md5 4c3655982998…)
- `/workspace/sf-autotester/selftest/coverage_out3.txt` (353 bytes, md5 fa0a5fb8a7e0…)
- `/workspace/sf-autotester/selftest/sample_stderr.log` (1093 bytes, md5 51881204c92b…)
- `/workspace/sf-autotester/selftest/coverage_out3.json` (1319 bytes, md5 39b960de1856…)
- `/workspace/sf-autotester/reports/run_20261127-190149/coverage.txt` (25 bytes, md5 325d5e817f58…)
- `/workspace/faces/sd/shadowdiag_stderr.txt` (4969888 bytes, md5 c6dd625edbad…)
- `/workspace/faces/sh/sh1780_stderr.txt` (5361122 bytes, md5 1767265f002d…)
- `/workspace/clothv2/r1776/cwd_1776/unresolved_nids.txt` (324 bytes, md5 2006e56c37ff…)
- `/workspace/clothv2/r1776/shots_1776/abtest.log` (478 bytes, md5 05afe827f87a…)
- `/workspace/sf-shared/progress-src/runs/20261126-084530-a64303-findings.json` (4790 bytes, md5 5b0caa7aa72d…)
- `/workspace/sf-shared/progress-src/runs/20261126-084039-09c828-findings.json` (5080 bytes, md5 d5dac0666c8c…)
- `/workspace/sf-shared/progress-src/runs/20261126-083638-39c869-findings.json` (4768 bytes, md5 c1767a1953d7…)
- `/workspace/sf-shared/progress-src/runs/20261126-085348-3a0f04-findings.json` (4887 bytes, md5 22c815f4a0ca…)

Also used (not play logs): `nid-autolink/pc-results/report.csv` + `v2/callgraph.json` (346 imports, 6444 functions), `progress-src/out/EBOOT.imports.json`, `EBOOT.functions.json`, `progress-src/runs/*findings.json`, `v2-rank/master_ranked.csv`, `docs/hle_spec/`, lifecycle summaries under `voicefreeze/lifecycle/results/`.

Static callers come from the v2 callgraph (ELF scan on the PC, numbers-only JSON on the box) plus the import table. Lifted C was not re-walked here; the callgraph already lists every `bl` to each import stub.

### CALLED

#### sys_lwcond_signal_all (`0xE9A1BD84`, sysPrxForUser)

- Class: CALLED (CONFIRMED). Best count: 4039883 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x000200AC×808492, 0x000285B0×401, 0x000237E4×37, 0x0002B8DC×793120, 0x0002B148×1628184, 0x00024034×808629, 0x0002B834×3, 0x00028CB0×43, 0x0002BAE4×974
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1385` kind=hle-lr-new lr=0x00024034 ret=0x00000000
  - `[hle-lr] new nid=0xE9A1BD84 lr=0x00024034 tid=16 r3=0x119FA678 r4=0x00000000 r5=0x00000000 r6=0x00000001 ret=0x00000000 t=147649597`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=14 callers=5 depth_from_entry=2 reachable_callers=5 ret_tested=0 context={'core': 661, 'other': 41, 'media': 119, 'net': 139}
  - site 0x000200A8 caller 0x0001E3E8 (fn_0001E3E8) depth=2
  - site 0x000201FC caller 0x00020164 (fn_00020164) depth=2
  - site 0x00020518 caller 0x00020164 (fn_00020164) depth=2
  - site 0x000208CC caller 0x00020164 (fn_00020164) depth=2
  - site 0x00022B14 caller 0x00020164 (fn_00020164) depth=2
  - site 0x000237E0 caller 0x00020164 (fn_00020164) depth=2
  - site 0x00024030 caller 0x00020164 (fn_00020164) depth=2
  - site 0x000285AC caller 0x000252AC (fn_000252AC) depth=2
  - site 0x00028BE0 caller 0x000252AC (fn_000252AC) depth=2
  - site 0x00028CAC caller 0x000252AC (fn_000252AC) depth=2
  - site 0x0002B144 caller 0x000252AC (fn_000252AC) depth=2
  - site 0x0002B830 caller 0x0002B24C (fn_0002B24C) depth=3
  - site 0x0002B8D8 caller 0x0002B24C (fn_0002B24C) depth=3
  - site 0x0002BAE0 caller 0x0002BA0C (fn_0002BA0C) depth=3
- Risk: high (ASSUMED). Companion of sys_lwcond_signal (wake all). Same hang-risk if used at stage teardown and the body is a no-op.
- Ranked verdict: unresearched (none).

#### sys_lwcond_signal (`0xEF87A695`, sysPrxForUser)

- Class: CALLED (CONFIRMED). Best count: 363392 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x0001A4FC×67250, 0x0001C168×296142
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:831` kind=hle-lr-new lr=0x0001A4FC ret=0x00000000
  - `[hle-lr] new nid=0xEF87A695 lr=0x0001A4FC tid=10 r3=0x11103350 r4=0x50014984 r5=0x50014980 r6=0x50014988 ret=0x00000000 t=147649410`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=3 callers=3 depth_from_entry=2 reachable_callers=3 ret_tested=0 context={'core': 226, 'other': 19, 'media': 90}
  - site 0x00019D10 caller 0x00017F64 (fn_00017F64) depth=3
  - site 0x0001A4F8 caller 0x0001A268 (fn_0001A268) depth=3
  - site 0x0001C164 caller 0x0001A504 (fn_0001A504) depth=2
- Risk: high (ASSUMED). Winning handler classified stub (returns a constant). Voicediag SF_HLE_LRLOG shows tens of thousands of calls, including through stage changes. If the body does not actually wake waiters, stage teardown / village hang is a plausible victim. VERIFY by reading the winning handler on the test copy and checking whether a waiter is released.
- Ranked verdict: unresearched (none).

#### _cellGcmSetFlipCommand (`0x21397818`, cellGcmSys)

- Class: CALLED (CONFIRMED). Best count: 65157 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x0004830C×65157
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:352` kind=hle-lr-new lr=0x0004830C ret=0x00000000
  - `[hle-lr] new nid=0x21397818 lr=0x0004830C tid=1 r3=0x11030E48 r4=0x00000001 r5=0x11030E64 r6=0x20002000 ret=0x00000000 t=147649202`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=1 callers=1 depth_from_entry=4 reachable_callers=1 ret_tested=0 context={'other': 4, 'core': 168, 'net': 47, 'media': 51}
  - site 0x00048308 caller 0x00044754 (fn_00044754) depth=4
- Risk: medium (ASSUMED). Low-level flip command. Called during boot in voicediag. Display still updates, so another flip path is likely live. A no-op here could still skip a barrier or cause a frame of stale data (tearing/hitch). VERIFY whether the port's flip is implemented only via a different NID.
- Ranked verdict: unresearched (none).

#### cellKbRead (`0xFF0A21B7`, sys_io)

- Class: CALLED (CONFIRMED). Best count: 65149 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x0049E1B0×65149
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1754` kind=hle-lr-new lr=0x0049E1B0 ret=0x00000000
  - `[hle-lr] new nid=0xFF0A21B7 lr=0x0049E1B0 tid=1 r3=0x00000000 r4=0x160001EC r5=0x00000000 r6=0x000003E9 ret=0x00000000 t=147649685`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Autolink 17:19: calls=>=1 src=findings.json(first-hit) lr=0x0049E1B0
- Static: sites=1 callers=1 depth_from_entry=4 reachable_callers=1 ret_tested=1 context={'core': 10, 'net': 4, 'other': 3}
  - site 0x0049E1AC caller 0x0049E038 (fn_0049E038) depth=4 ret_test=cmpwi r3,0 branch_if=r3 == 0 error_side=fallthrough
- Risk: medium (ASSUMED). cellKbRead: game tests r3==0 (callgraph). A stub that returns 0 without writing key data looks like 'no keys'. Called in voicediag (boot). Keyboard init is logged. Unlikely to freeze the village; can break name entry.
- Ranked verdict: unresearched (none).

#### sys_lwcond_destroy (`0x1C9A942C`, sysPrxForUser)

- Class: CALLED (CONFIRMED). Best count: 10 — handler-log / first-hit counts; no [hle-lrc] dump for this NID (may under-count).
- LRs: 0x0001C1BC×1, 0x000240A0×1, 0x000240C0×1, 0x00028A60×1, 0x00028A80×1, 0x0002BD54×1, 0x0002BD78×1, 0x000209BC×1, 0x000209DC×1, 0x0001AAA4×1
- First evidence: `/workspace/sf-shared/testloop/sfrace/sfrace1786_20261127-190111_stderr.log:804394` kind=hle-lr-new lr=0x0001C1BC ret=0x00000000
  - `[hle-lr] new nid=0x1C9A942C lr=0x0001C1BC tid=1 r3=0x11ADB158 r4=0x00000000 r5=0x00000000 r6=0x00000002 ret=0x00000000 t=154882650`
- Nearest stage (ASSUMED from lifecycle line ranges): stage_B — المرحلة ب (كاش 5053؛ نهاية اللوق انتظار WAIT_SIGNAL) (lifecycle_39940: B L175200-end, cache 5053)
- Static: sites=10 callers=5 depth_from_entry=2 reachable_callers=5 ret_tested=0 context={'core': 620, 'media': 189, 'other': 41, 'net': 70}
  - site 0x0001AAA0 caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x0001C1B8 caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x000209B8 caller 0x00020164 (fn_00020164) depth=2
  - site 0x000209D8 caller 0x00020164 (fn_00020164) depth=2
  - site 0x0002409C caller 0x00024048 (fn_00024048) depth=3
  - site 0x000240BC caller 0x00024048 (fn_00024048) depth=3
  - site 0x00028A5C caller 0x000252AC (fn_000252AC) depth=2
  - site 0x00028A7C caller 0x000252AC (fn_000252AC) depth=2
  - site 0x0002BD50 caller 0x0002BA0C (fn_0002BA0C) depth=3
  - site 0x0002BD74 caller 0x0002BA0C (fn_0002BA0C) depth=3
- Risk: medium (ASSUMED). Destroy of an lwcond. A no-op may leak waiters across stage re-creation (same EA reuse pattern already CONFIRMED for SPURS tasksets). Not shown as the root of the hang by itself.
- Ranked verdict: unresearched (none).

#### sys_lwmutex_destroy (`0xC3476D0C`, sysPrxForUser)

- Class: CALLED (CONFIRMED). Best count: 6 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x00540D34×6
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:2348` kind=hle-lr-new lr=0x00540D34 ret=0x00000000
  - `[hle-lr] new nid=0xC3476D0C lr=0x00540D34 tid=1 r3=0x120B9C88 r4=0x120B9C80 r5=0x120B9CA0 r6=0x02546280 ret=0x00000000 t=147650227`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=61 callers=21 depth_from_entry=1 reachable_callers=19 ret_tested=2 context={'core': 1922, 'other': 109, 'media': 415, 'net': 478, 'ui': 17}
  - site 0x00013898 caller 0x000102C8 (fn_000102C8) depth=1
  - site 0x00014C7C caller 0x000102C8 (fn_000102C8) depth=1
  - site 0x00014C90 caller 0x000102C8 (fn_000102C8) depth=1
  - site 0x000174AC caller 0x00016C98 (fn_00016C98) depth=3
  - site 0x000174C0 caller 0x00016C98 (fn_00016C98) depth=3
  - site 0x0001AA90 caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x0001AAB0 caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x0001AAD0 caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x0001AADC caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x0001C1CC caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x0001C1D8 caller 0x0001A504 (fn_0001A504) depth=2
  - site 0x000209C8 caller 0x00020164 (fn_00020164) depth=2
  - site 0x000209EC caller 0x00020164 (fn_00020164) depth=2
  - site 0x000209F8 caller 0x00020164 (fn_00020164) depth=2
  - site 0x00021340 caller 0x00020164 (fn_00020164) depth=2
  - site 0x000240AC caller 0x00024048 (fn_00024048) depth=3
  - site 0x000240CC caller 0x00024048 (fn_00024048) depth=3
  - site 0x000240DC caller 0x00024048 (fn_00024048) depth=3
  - site 0x00024DD0 caller 0x00024048 (fn_00024048) depth=3
  - site 0x00028A6C caller 0x000252AC (fn_000252AC) depth=2
  - site 0x00028A8C caller 0x000252AC (fn_000252AC) depth=2
  - site 0x00028A9C caller 0x000252AC (fn_000252AC) depth=2
  - site 0x0002BD60 caller 0x0002BA0C (fn_0002BA0C) depth=3
  - site 0x0002BD80 caller 0x0002BA0C (fn_0002BA0C) depth=3
  - site 0x0002F4F8 caller 0x0002F1AC (fn_0002F1AC) depth=4 ret_test=cmpwi r3,0 branch_if=not(r3 == 0) error_side=taken
  - site 0x00030D44 caller 0x0002F964 (fn_0002F964) depth=5
  - site 0x000319A4 caller 0x0002F964 (fn_0002F964) depth=5
  - site 0x00031B30 caller 0x0002F964 (fn_0002F964) depth=5
  - site 0x00031C44 caller 0x0002F964 (fn_0002F964) depth=5
  - site 0x00031F24 caller 0x0002F964 (fn_0002F964) depth=5
  - site 0x00032ECC caller 0x00032860 (fn_00032860) depth=6
  - site 0x00032F6C caller 0x00032860 (fn_00032860) depth=6
  - site 0x00032FA8 caller 0x00032860 (fn_00032860) depth=6
  - site 0x0004C120 caller 0x0004B44C (fn_0004B44C) depth=4
  - site 0x0004C12C caller 0x0004B44C (fn_0004B44C) depth=4
  - site 0x0004C138 caller 0x0004B44C (fn_0004B44C) depth=4
  - site 0x0004CA8C caller 0x0004C554 (fn_0004C554) depth=4
  - site 0x0004D7CC caller 0x0004D684 (fn_0004D684) depth=None
  - site 0x0004D804 caller 0x0004D684 (fn_0004D684) depth=None
  - site 0x0004DA20 caller 0x0004D8D8 (fn_0004D8D8) depth=5
  - site 0x0004DA54 caller 0x0004D8D8 (fn_0004D8D8) depth=5
  - site 0x0004F6E4 caller 0x0004D8D8 (fn_0004D8D8) depth=5
  - site 0x0004F72C caller 0x0004D8D8 (fn_0004D8D8) depth=5
  - site 0x0004F774 caller 0x0004D8D8 (fn_0004D8D8) depth=5
  - site 0x0004F7BC caller 0x0004D8D8 (fn_0004D8D8) depth=5
  - site 0x000529B4 caller 0x00051958 (fn_00051958) depth=4
  - site 0x00054E80 caller 0x0005346C (fn_0005346C) depth=3
  - site 0x000698D0 caller 0x00069338 (fn_00069338) depth=3
  - site 0x000698F8 caller 0x00069338 (fn_00069338) depth=3
  - site 0x0006CB28 caller 0x00069338 (fn_00069338) depth=3 ret_test=cmpwi r3,0 branch_if=not(r3 == 0) error_side=taken
  - site 0x00534794 caller 0x005332E0 (fn_005332E0) depth=5
  - site 0x005347A0 caller 0x005332E0 (fn_005332E0) depth=5
  - site 0x00534854 caller 0x005332E0 (fn_005332E0) depth=5
  - site 0x005348B4 caller 0x005332E0 (fn_005332E0) depth=5
  - site 0x005348F4 caller 0x005332E0 (fn_005332E0) depth=5
  - site 0x00534968 caller 0x005332E0 (fn_005332E0) depth=5
  - site 0x0053BA3C caller 0x0053BA2C (fn_0053BA2C) depth=6
  - site 0x0053E4A4 caller 0x0053BA2C (fn_0053BA2C) depth=6
  - site 0x00540D30 caller 0x00540B7C (fn_00540B7C) depth=None
  - site 0x00540E48 caller 0x00540D98 (fn_00540D98) depth=4
  - site 0x00540E58 caller 0x00540D98 (fn_00540D98) depth=4
- Risk: medium (ASSUMED). lwmutex destroy. Voicediag dump shows a handful of calls. A no-op can leave a mutex live at a reused address after a stage change.
- Ranked verdict: unresearched (none).

#### cellSailDescriptorSetAutoSelection (`0x76B1A425`, cellSail)

- Class: CALLED (CONFIRMED). Best count: 5 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x005C9B28×5
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:2299` kind=hle-lr-new lr=0x005C9B28 ret=0x00000000
  - `[hle-lr] new nid=0x76B1A425 lr=0x005C9B28 tid=1 r3=0x00000000 r4=0x00000000 r5=0x00000000 r6=0x120B9D18 ret=0x00000000 t=147650210`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=1 callers=1 depth_from_entry=None reachable_callers=0 ret_tested=1 context={'media': 30, 'core': 5}
  - site 0x005C9B24 caller 0x005C8A70 (fn_005C8A70) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Risk: low (ASSUMED). SetAutoSelection. Setting sink unless the game later reads the flag back from a structure the stub does not write.
- Ranked verdict: owned-by-salem (none).

#### cellSailGraphicsAdapterSetPreferredFormat (`0x2E3CCB5E`, cellSail)

- Class: CALLED (CONFIRMED). Best count: 5 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x005C93C0×5
- First evidence: `/workspace/sf-shared/testloop/saud_blackhang_1817_stderr.log:933` kind=handler-log lr=None ret=None
  - `[sf-movie] GraphicsAdapterSetPreferredFormat coding=0`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (Story: Shu Chapter 1 عند L9613) (lifecycle: boot L1-L34750; Story L9613)
- Movies nearby: movie000.pam, movie001.pam, movie002.pam, movie007.pam
- Autolink 17:19: calls=>=1 src=findings.json hle_funcs(seen) lr=None
- Static: sites=1 callers=1 depth_from_entry=None reachable_callers=0 ret_tested=1 context={'media': 30, 'core': 5}
  - site 0x005C93BC caller 0x005C8A70 (fn_005C8A70) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Risk: medium (ASSUMED). Called at every boot movie (movie000/001/007/013). Port logs the call; movies already play in v5 so a constant-success may be enough, but preferred format is ignored. Owned-by-salem (movies).
- Ranked verdict: owned-by-salem (none).

#### cellSailPlayerAddDescriptor (`0x7C8DFF3B`, cellSail)

- Class: CALLED (CONFIRMED). Best count: 5 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x005C9C6C×5
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:2313` kind=hle-lr-new lr=0x005C9C6C ret=0x00000000
  - `[hle-lr] new nid=0x7C8DFF3B lr=0x005C9C6C tid=1 r3=0x16900090 r4=0x00000000 r5=0x00000000 r6=0x00000001 ret=0x00000000 t=147650211`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Movies nearby: movie000.pam, movie001.pam, movie002.pam, movie007.pam, movie013.pam
- Static: sites=1 callers=1 depth_from_entry=None reachable_callers=0 ret_tested=1 context={'media': 30, 'core': 5}
  - site 0x005C9C68 caller 0x005C8A70 (fn_005C8A70) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Risk: medium (ASSUMED). AddDescriptor is logged next to every boot movie. v5 plays those movies, so a success return may be enough if the port tracks descriptors itself. Still a stub per the 17:19 scan. Owned-by-salem.
- Ranked verdict: owned-by-salem (none).

#### cellAudioOutSetCopyControl (`0xC96E89E9`, cellSysutil)

- Class: CALLED (CONFIRMED). Best count: 1 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x0001ADB4×1
- First evidence: `/workspace/sf-shared/testloop/saud_blackhang_1817_stdout.log:66` kind=handler-log lr=None ret=None
  - `[cellAvconfExt] AudioOutSetCopyControl(control=2)`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (من لوق stdout؛ رقم السطر مو نفس stderr) (ASSUMED boot: early stdout, boot taskset still active)
- Static: sites=1 callers=1 depth_from_entry=2 reachable_callers=1 ret_tested=1 context={'core': 110, 'media': 35, 'other': 10}
  - site 0x0001ADB0 caller 0x0001A504 (fn_0001A504) depth=2 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Risk: low (ASSUMED). Spec verdict ok-setting-sink. Called once at boot (copy control=2). Unlikely to cause the thin-voice / BGM bugs by itself.
- Ranked verdict: ok-setting-sink (KNOWN (codes) / ASSUMED (validation rules)).

#### cellOskDialogSetInitialKeyLayout (`0xC427890C`, cellSysutil)

- Class: CALLED (CONFIRMED). Best count: 1 — handler-log / first-hit counts; no [hle-lrc] dump for this NID (may under-count).
- First evidence: `/workspace/sf-shared/testloop/saud_blackhang_1817_stdout.log:2954` kind=handler-log lr=None ret=None
  - `[cellOskDialog] SetInitialKeyLayout(2)`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (من لوق stdout؛ رقم السطر مو نفس stderr) (ASSUMED boot: early stdout, boot taskset still active)
- Autolink 17:19: calls=>=1 src=findings.json hle_funcs(seen) lr=None
- Static: sites=1 callers=1 depth_from_entry=7 reachable_callers=1 ret_tested=0 context={'ui': 10, 'core': 1, 'other': 1}
  - site 0x0049FDB0 caller 0x0049FAA4 (fn_0049FAA4) depth=7
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.
- Ranked verdict: ok-setting-sink (KNOWN (prototype, codes) / ASSUMED (validation rules)).

#### cellOskDialogSetLayoutMode (`0xF0EC3CCC`, cellSysutil)

- Class: CALLED (CONFIRMED). Best count: 1 — handler-log / first-hit counts; no [hle-lrc] dump for this NID (may under-count).
- First evidence: `/workspace/sf-shared/testloop/saud_blackhang_1817_stdout.log:2951` kind=handler-log lr=None ret=None
  - `[cellOskDialog] SetLayoutMode(9216)`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (من لوق stdout؛ رقم السطر مو نفس stderr) (ASSUMED boot: early stdout, boot taskset still active)
- Autolink 17:19: calls=>=1 src=findings.json hle_funcs(seen) lr=None
- Static: sites=1 callers=1 depth_from_entry=3 reachable_callers=1 ret_tested=0 context={'net': 8, 'other': 6, 'ui': 6, 'core': 15}
  - site 0x004A0344 caller 0x004A0130 (fn_004A0130) depth=3
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.
- Ranked verdict: ok-setting-sink (KNOWN (prototype, codes) / ASSUMED (validation rules)).

#### sceNpBasicRegisterContextSensitiveHandler (`0x4026EAC5`, sceNp)

- Class: CALLED (CONFIRMED). Best count: 1 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x00037B58×1
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1723` kind=hle-lr-new lr=0x00037B58 ret=0x00000000
  - `[hle-lr] new nid=0x4026EAC5 lr=0x00037B58 tid=1 r3=0x006B6C28 r4=0x0080FB68 r5=0x00000000 r6=0x00000030 ret=0x00000000 t=147649685`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=1 callers=1 depth_from_entry=6 reachable_callers=1 ret_tested=1 context={'net': 51, 'core': 13}
  - site 0x00037B54 caller 0x00037090 (fn_00037090) depth=6 ret_test=cmpwi r31,0 branch_if=r3 < 0 error_side=taken
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.
- Ranked verdict: unresearched (none).

#### _sys_process_at_Exitspawn (`0x96328741`, sysPrxForUser)

- Class: CALLED (CONFIRMED). Best count: 1 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x000104AC×1
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:39` kind=hle-lr-new lr=0x000104AC ret=0x00000000
  - `[hle-lr] new nid=0x96328741 lr=0x000104AC tid=1 r3=0x008034D8 r4=0x0084DF18 r5=0x0084DF08 r6=0x0084DF14 ret=0x00000000 t=147648978`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=1 callers=1 depth_from_entry=1 reachable_callers=1 ret_tested=0 context={'core': 177, 'other': 17}
  - site 0x000104A8 caller 0x000102C8 (fn_000102C8) depth=1
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.
- Ranked verdict: unresearched (none).

#### _sys_process_atexitspawn (`0x2C847572`, sysPrxForUser)

- Class: CALLED (CONFIRMED). Best count: 1 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x000104A0×1
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:38` kind=hle-lr-new lr=0x000104A0 ret=0x00000000
  - `[hle-lr] new nid=0x2C847572 lr=0x000104A0 tid=1 r3=0x008034E0 r4=0x0084DF18 r5=0x0084DF08 r6=0x0084DF14 ret=0x00000000 t=147648978`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=1 callers=1 depth_from_entry=1 reachable_callers=1 ret_tested=0 context={'core': 177, 'other': 17}
  - site 0x0001049C caller 0x000102C8 (fn_000102C8) depth=1
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.
- Ranked verdict: unresearched (none).

#### sys_net_initialize_network_ex (`0x139A9E9B`, sys_net)

- Class: CALLED (CONFIRMED). Best count: 1 — last cumulative [hle-lrc] dump of /workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log (CONFIRMED); other hooked sessions listed in lrc_by_log.
- LRs: 0x001EFCD4×1
- First evidence: `/workspace/sf-shared/testloop/voicediag1786_saud_20261127-172741_stderr.log:1719` kind=hle-lr-new lr=0x001EFCD4 ret=0x00000000
  - `[hle-lr] new nid=0x139A9E9B lr=0x001EFCD4 tid=1 r3=0x0FEFFCA8 r4=0x00000000 r5=0x0000007F r6=0x00000090 ret=0x00000000 t=147649685`
- Nearest stage (ASSUMED from lifecycle line ranges): boot — إقلاع/أفلام/قوائم (lifecycle summary: boot L1-L12232)
- Static: sites=1 callers=1 depth_from_entry=4 reachable_callers=1 ret_tested=0 context={'net': 13, 'ui': 11, 'core': 2, 'other': 3}
  - site 0x001EFCD0 caller 0x001EE864 (fn_001EE864) depth=4
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.
- Ranked verdict: unresearched (none).

#### cellOskDialogExtRegisterForceFinishCallback (`0xE800F586`, cellOskExtUtility)

- Class: CALLED (CONFIRMED). Best count: 0 — no on-box count.
- First evidence: `/workspace/sf-shared/nid-autolink/pc-results/report.csv` kind=autolink-report lr=0x0049FDCC ret=None
  - `calls=>=1 src=findings.json(first-hit) lr=0x0049FDCC`
- Autolink 17:19: calls=>=1 src=findings.json(first-hit) lr=0x0049FDCC
- Static: sites=1 callers=1 depth_from_entry=7 reachable_callers=1 ret_tested=0 context={'ui': 10, 'core': 1, 'other': 1}
  - site 0x0049FDC8 caller 0x0049FAA4 (fn_0049FAA4) depth=7
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.
- Ranked verdict: ok-setting-sink (KNOWN (prototype, codes) / ASSUMED (validation rules)).

#### cellOskDialogExtSetInitialScale (`0x75370397`, cellOskExtUtility)

- Class: CALLED (CONFIRMED). Best count: 0 — no on-box count.
- First evidence: `/workspace/sf-shared/nid-autolink/pc-results/report.csv` kind=autolink-report lr=0x0049FDC0 ret=None
  - `calls=>=1 src=findings.json(first-hit) lr=0x0049FDC0`
- Autolink 17:19: calls=>=1 src=findings.json(first-hit) lr=0x0049FDC0
- Static: sites=1 callers=1 depth_from_entry=7 reachable_callers=1 ret_tested=0 context={'ui': 10, 'core': 1, 'other': 1}
  - site 0x0049FDBC caller 0x0049FAA4 (fn_0049FAA4) depth=7
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.
- Ranked verdict: ok-setting-sink (KNOWN (prototype, codes) / ASSUMED (validation rules)).

#### cellOskDialogAddSupportLanguage (`0x7F21C918`, cellSysutil)

- Class: CALLED (CONFIRMED). Best count: 0 — no on-box count.
- First evidence: `/workspace/sf-shared/nid-autolink/pc-results/report.csv` kind=autolink-report lr=0x0049FD9C ret=None
  - `calls=>=1 src=findings.json(first-hit) lr=0x0049FD9C`
- Autolink 17:19: calls=>=1 src=findings.json(first-hit) lr=0x0049FD9C
- Static: sites=1 callers=1 depth_from_entry=7 reachable_callers=1 ret_tested=0 context={'ui': 10, 'core': 1, 'other': 1}
  - site 0x0049FD98 caller 0x0049FAA4 (fn_0049FAA4) depth=7
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.
- Ranked verdict: ok-setting-sink (KNOWN (prototype, codes) / ASSUMED (validation rules)).

#### cellOskDialogSetKeyLayoutOption (`0xB53C54FA`, cellSysutil)

- Class: CALLED (CONFIRMED). Best count: 0 — no on-box count.
- First evidence: `/workspace/sf-shared/nid-autolink/pc-results/report.csv` kind=autolink-report lr=0x0049FDA8 ret=None
  - `calls=>=1 src=findings.json(first-hit) lr=0x0049FDA8`
- Autolink 17:19: calls=>=1 src=findings.json(first-hit) lr=0x0049FDA8
- Static: sites=1 callers=1 depth_from_entry=7 reachable_callers=1 ret_tested=0 context={'ui': 10, 'core': 1, 'other': 1}
  - site 0x0049FDA4 caller 0x0049FAA4 (fn_0049FAA4) depth=7
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.
- Ranked verdict: ok-setting-sink (KNOWN (prototype, codes) / ASSUMED (validation rules)).

### IMPORTED-NOT-SEEN

These functions are in `EBOOT.imports.json` (CONFIRMED) and have static `bl` sites in the callgraph (some have 0 sites and may be reached only via a function pointer — VERIFY). No runtime line in any box log, findings.json, or the 17:19 autolink call column. Absence in the two SF_HLE_LRLOG sessions (voicediag + SFRACE, hook on from boot through stage B) is stronger evidence they are not used on that path. They may still run in a menu, save-delete, or online path. Label: CONFIRMED not seen on those paths; VERIFY with the Phase 2 boot+menus log-only run.

#### cellAtracGetSecondBufferInfo (`0xBE07F05E`, cellAtrac)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=2 reachable_from_entry=1 ret_tested=2 context={'core': 166, 'media': 19, 'other': 11}
  - site 0x0002951C caller 0x000252AC (fn_000252AC) depth=2 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
  - site 0x000295AC caller 0x000252AC (fn_000252AC) depth=2 ret_test=cmpwi r3,0 branch_if=not(r3 < 0) error_side=fallthrough
- Proposed exercise (plan only): same boot movies (6ch on movie001/007) and then village BGM. Stay in the village / blacksmith after load; no teleport required.
- Risk: high (ASSUMED). Second ATRAC buffer info. Game tests r3 at both call sites (callgraph CONFIRMED). A stub that returns 0 without filling the out-struct can skip or corrupt streaming. Linked in autolink notes to the mixer / 6ch AT3P path. VERIFY with SF_HLE_LRLOG + atrac-validator.

#### cellAtracIsSecondBufferNeeded (`0x99EFE171`, cellAtrac)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=2 reachable_from_entry=1 ret_tested=2 context={'core': 166, 'media': 19, 'other': 11}
  - site 0x00029278 caller 0x000252AC (fn_000252AC) depth=2 ret_test=cmpwi r3,0 branch_if=not(r3 > 0) error_side=?
  - site 0x000292B4 caller 0x000252AC (fn_000252AC) depth=2 ret_test=cmpwi r3,0 branch_if=r3 > 0 error_side=?
- Proposed exercise (plan only): same boot movies (6ch on movie001/007) and then village BGM. Stay in the village / blacksmith after load; no teleport required.
- Risk: high (ASSUMED). IsSecondBufferNeeded: game branches on r3>0 vs not (callgraph CONFIRMED). A constant 0 means 'not needed' and would skip the second buffer path. Candidate for thin/wrong BGM if a second buffer is required. VERIFY by logging r3 and whether the 6ch stream requests a second buffer.

#### cellGameGetSizeKB (`0xEF9D42D5`, cellGame)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=None reachable_from_entry=0 ret_tested=2 context={'ui': 2, 'other': 10, 'core': 9}
  - site 0x0049D528 caller 0x0049CB88 (fn_0049CB88) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
  - site 0x0049D96C caller 0x0049CB88 (fn_0049CB88) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Proposed exercise (plan only): boot (BootCheck path). GetSizeKB / PatchCheck may only run on install/patch or first-boot without a ready cache — try a tester state with empty game-data (copy, not Saud's save).
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellGamePatchCheck (`0xCE4374F6`, cellGame)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=None reachable_from_entry=0 ret_tested=0 context={'ui': 2, 'other': 10, 'core': 9}
  - site 0x0049DBFC caller 0x0049CB88 (fn_0049CB88) depth=None
- Proposed exercise (plan only): boot (BootCheck path). GetSizeKB / PatchCheck may only run on install/patch or first-boot without a ready cache — try a tester state with empty game-data (copy, not Saud's save).
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellRescSetBufferAddress (`0x8107277C`, cellResc)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=0 context={'net': 4, 'core': 124, 'other': 18, 'ui': 12}
  - site 0x0052D3B8 caller 0x0051AAD4 (fn_0051AAD4) depth=4
- Proposed exercise (plan only): same as graphics: title into village, then blacksmith camera. If still unseen, dump with SF_HLE_LRLOG through the first flip.
- Risk: medium (ASSUMED). cellRescSetBufferAddress. If the game uses RESC to scale and this stub ignores the address, output can be wrong size/offset (blue strip / edge). Not confirmed used at runtime.

#### cellSailDescriptorCreateDatabase (`0x0ABB318B`, cellSail)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=None reachable_from_entry=0 ret_tested=2 context={'media': 30, 'core': 5}
  - site 0x005C9BC4 caller 0x005C8A70 (fn_005C8A70) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
  - site 0x005C9D74 caller 0x005C8A70 (fn_005C8A70) depth=None ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Proposed exercise (plan only): boot movies (movie000, 001, 007, 002/013). No teleport; start a tester run and let the intro play. Do not skip cutscenes.
- Risk: medium (ASSUMED). Sail descriptor database create. Call sites test r3<0 (callgraph). A success-with-no-database could break later in-stage movies (movie013 already opens and shows 0 frames in 1817 — not proven related).

#### cellSailDescriptorDestroyDatabase (`0x28336E89`, cellSail)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=None reachable_from_entry=0 ret_tested=0 context={'media': 30, 'core': 5}
  - site 0x005C9C50 caller 0x005C8A70 (fn_005C8A70) depth=None
  - site 0x005C9DB4 caller 0x005C8A70 (fn_005C8A70) depth=None
- Proposed exercise (plan only): boot movies (movie000, 001, 007, 002/013). No teleport; start a tester run and let the intro play. Do not skip cutscenes.
- Risk: low (ASSUMED). Destroy database. Failure to free is a leak, not a likely visible boot bug.

#### cellAudioOutConfigure (`0x4692AB35`, cellSysutil)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=2 reachable_from_entry=1 ret_tested=1 context={'core': 110, 'media': 35, 'other': 10}
  - site 0x0001AE9C caller 0x0001A504 (fn_0001A504) depth=2 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Proposed exercise (plan only): OSK cluster: title / name-entry / options. 1817 already hit SetLayoutMode + SetInitialKeyLayout during boot. Re-run boot with SF_HLE_LRLOG to catch the rest (AddSupportLanguage, KeyLayoutOption, …).
- Risk: high (ASSUMED). Spec (researched 2026-11-27) verdict needs-real-impl: returning 0 is OK but the requested channel config is discarded; later GetConfiguration always reports 2ch LPCM. Candidate link to the 6ch mixer leak. VERIFY with a log of the config the game passes.

#### cellOskDialogDisableDimmer (`0x41F20828`, cellSysutil)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=3 reachable_from_entry=1 ret_tested=0 context={'net': 8, 'other': 6, 'ui': 6, 'core': 15}
  - site 0x004A03AC caller 0x004A0130 (fn_004A0130) depth=3
  - site 0x004A0534 caller 0x004A0130 (fn_004A0130) depth=3
- Proposed exercise (plan only): OSK cluster: title / name-entry / options. 1817 already hit SetLayoutMode + SetInitialKeyLayout during boot. Re-run boot with SF_HLE_LRLOG to catch the rest (AddSupportLanguage, KeyLayoutOption, …).
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.

#### cellOskDialogSetInitialInputDevice (`0xF3B4B43E`, cellSysutil)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=3 reachable_from_entry=1 ret_tested=0 context={'net': 8, 'other': 6, 'ui': 6, 'core': 15}
  - site 0x004A03B8 caller 0x004A0130 (fn_004A0130) depth=3
  - site 0x004A0540 caller 0x004A0130 (fn_004A0130) depth=3
- Proposed exercise (plan only): OSK cluster: title / name-entry / options. 1817 already hit SetLayoutMode + SetInitialKeyLayout during boot. Re-run boot with SF_HLE_LRLOG to catch the rest (AddSupportLanguage, KeyLayoutOption, …).
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.

#### cellOskDialogSetSeparateWindowOption (`0x53E39DF3`, cellSysutil)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=3 reachable_from_entry=1 ret_tested=0 context={'net': 8, 'other': 6, 'ui': 6, 'core': 15}
  - site 0x004A0420 caller 0x004A0130 (fn_004A0130) depth=3
  - site 0x004A0594 caller 0x004A0130 (fn_004A0130) depth=3
- Proposed exercise (plan only): OSK cluster: title / name-entry / options. 1817 already hit SetLayoutMode + SetInitialKeyLayout during boot. Re-run boot with SF_HLE_LRLOG to catch the rest (AddSupportLanguage, KeyLayoutOption, …).
- Risk: low (ASSUMED). OSK setting-sink per researched specs (ok-setting-sink). Returning 0 is documented as acceptable for these option-setters.

#### cellSaveDataDelete2 (`0xEDADD797`, cellSysutil)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=0 context={'other': 3, 'ui': 3, 'core': 5}
  - site 0x004A31EC caller 0x004A2F90 (fn_004A2F90) depth=4
- Proposed exercise (plan only): OSK cluster: title / name-entry / options. 1817 already hit SetLayoutMode + SetInitialKeyLayout during boot. Re-run boot with SF_HLE_LRLOG to catch the rest (AddSupportLanguage, KeyLayoutOption, …).
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellSysutilAvc2InitParam (`0x89456724`, cellSysutilAvc2)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=5 reachable_from_entry=1 ret_tested=0 context={'net': 13, 'core': 10}
  - site 0x004CBCD4 caller 0x004CBAC8 (fn_004CBAC8) depth=5
- Proposed exercise (plan only): PS3 voice-chat APIs. Probably never reached in offline play. Optional: open any in-game 'party / voice' menu if one exists; otherwise leave as IMPORTED-NOT-SEEN.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellSysutilAvc2SetAttribute (`0xCCF0AEFF`, cellSysutilAvc2)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=5 callers=1 depth_from_entry=5 reachable_from_entry=1 ret_tested=0 context={'net': 13, 'core': 10}
  - site 0x004CBB58 caller 0x004CBAC8 (fn_004CBAC8) depth=5
  - site 0x004CBB88 caller 0x004CBAC8 (fn_004CBAC8) depth=5
  - site 0x004CBBB4 caller 0x004CBAC8 (fn_004CBAC8) depth=5
  - site 0x004CBBE4 caller 0x004CBAC8 (fn_004CBAC8) depth=5
  - site 0x004CBC10 caller 0x004CBAC8 (fn_004CBAC8) depth=5
- Proposed exercise (plan only): PS3 voice-chat APIs. Probably never reached in offline play. Optional: open any in-game 'party / voice' menu if one exists; otherwise leave as IMPORTED-NOT-SEEN.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellSysutilAvc2StartVoiceDetection (`0x16FF9BA0`, cellSysutilAvc2)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=0 context={'core': 28, 'net': 13, 'other': 2}
  - site 0x004CC458 caller 0x004CBEE4 (fn_004CBEE4) depth=4
- Proposed exercise (plan only): PS3 voice-chat APIs. Probably never reached in offline play. Optional: open any in-game 'party / voice' menu if one exists; otherwise leave as IMPORTED-NOT-SEEN.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellSysutilAvc2StopVoiceDetection (`0x178982D9`, cellSysutilAvc2)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=0 context={'core': 28, 'net': 13, 'other': 2}
  - site 0x004CC278 caller 0x004CBEE4 (fn_004CBEE4) depth=4
- Proposed exercise (plan only): PS3 voice-chat APIs. Probably never reached in offline play. Optional: open any in-game 'party / voice' menu if one exists; otherwise leave as IMPORTED-NOT-SEEN.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sceNpBasicGetEvent (`0xE035F7D6`, sceNp)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=5 reachable_from_entry=1 ret_tested=1 context={'net': 49, 'core': 53, 'media': 4}
  - site 0x00037DC4 caller 0x00037D14 (fn_00037D14) depth=5 ret_test=cmpw r3,r31 branch_if=r3 == rB error_side=?
- Proposed exercise (plan only): PlayStation Network friends/events. Init already runs at boot; GetEvent / friend list may need the NP menus or a stub-online flag. Do not enable real PSN. Log-only run through the title's online/trophy menus.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sceNpBasicGetFriendListEntry (`0x04372385`, sceNp)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=None reachable_from_entry=0 ret_tested=0 context={'net': 3}
  - site 0x003896C8 caller 0x00389008 (fn_00389008) depth=None
- Proposed exercise (plan only): PlayStation Network friends/events. Init already runs at boot; GetEvent / friend list may need the NP menus or a stub-online flag. Do not enable real PSN. Log-only run through the title's online/trophy menus.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sceNpManagerGetChatRestrictionFlag (`0xEB7A3D84`, sceNp)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=3 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=3 context={'net': 13, 'ui': 11, 'core': 2, 'other': 3}
  - site 0x001EEC94 caller 0x001EE864 (fn_001EE864) depth=4 ret_test=cmpwi r3,0 branch_if=not(r3 == 0) error_side=taken
  - site 0x001EF050 caller 0x001EE864 (fn_001EE864) depth=4 ret_test=cmpwi r3,0 branch_if=not(r3 == 0) error_side=taken
  - site 0x001EF78C caller 0x001EE864 (fn_001EE864) depth=4 ret_test=cmpwi r3,0 branch_if=not(r3 == 0) error_side=taken
- Proposed exercise (plan only): PlayStation Network friends/events. Init already runs at boot; GetEvent / friend list may need the NP menus or a stub-online flag. Do not enable real PSN. Log-only run through the title's online/trophy menus.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sceNpTusPollAsync (`0x19BCE18C`, sceNpTus)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=6 reachable_from_entry=1 ret_tested=1 context={'core': 2}
  - site 0x0003E110 caller 0x0003E0B4 (fn_0003E0B4) depth=6 ret_test=cmpwi r3,1 branch_if=r3 == 1 error_side=?
- Proposed exercise (plan only): TUS (title user storage) poll — online. Same as sceNp.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sys_prx_exitspawn_with_level (`0xA2C7BA64`, sysPrxForUser)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=0 reachable_from_entry=1 ret_tested=0 context={'core': 90, 'other': 11}
  - site 0x00010264 caller 0x00010230 (fn_00010230) depth=0
- Proposed exercise (plan only): lwcond/lwmutex: already called in voicediag if hooked. atexit/exitspawn/spu_image_close: end of process or SPU image unload — run until a clean quit, and also across a stage change (A→B).
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sys_spu_image_close (`0xE0DA8EFD`, sysPrxForUser)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=3 reachable_from_entry=1 ret_tested=0 context={'core': 218, 'net': 71, 'media': 24, 'other': 4}
  - site 0x00054F48 caller 0x0005346C (fn_0005346C) depth=3
- Proposed exercise (plan only): lwcond/lwmutex: already called in voicediag if hooked. atexit/exitspawn/spu_image_close: end of process or SPU image unload — run until a clean quit, and also across a stage change (A→B).
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellFsRmdir (`0x2796FDF3`, sys_fs)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=0 callers=0 depth_from_entry=None reachable_from_entry=0 ret_tested=0 context={}
- Proposed exercise (plan only): Rmdir/Utime: likely save-delete or cache maintenance. Try a tester-only save delete in the in-game save menu (not Saud's real save). Do not delete his save.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### cellFsUtime (`0xBEF554A4`, sys_fs)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=0 callers=0 depth_from_entry=None reachable_from_entry=0 ret_tested=0 context={}
- Proposed exercise (plan only): Rmdir/Utime: likely save-delete or cache maintenance. Try a tester-only save delete in the in-game save menu (not Saud's real save). Do not delete his save.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### bind (`0xB0A59804`, sys_net)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=2 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=2 context={'net': 69, 'core': 44, 'media': 20}
  - site 0x0002D904 caller 0x0002CE94 (fn_0002CE94) depth=4 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
  - site 0x0002D9A8 caller 0x0002CE94 (fn_0002CE94) depth=4 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Proposed exercise (plan only): socket/bind/setsockopt/init: CELL_SYSMODULE_NET is already loaded at boot. These may run during sceNp Init. Catch with SF_HLE_LRLOG from process start. Conditional net NIDs (the other 7) are not in this stub list.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### setsockopt (`0x88F03575`, sys_net)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=1 context={'net': 69, 'core': 44, 'media': 20}
  - site 0x0002D110 caller 0x0002CE94 (fn_0002CE94) depth=4 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Proposed exercise (plan only): socket/bind/setsockopt/init: CELL_SYSMODULE_NET is already loaded at boot. These may run during sceNp Init. Catch with SF_HLE_LRLOG from process start. Conditional net NIDs (the other 7) are not in this stub list.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### socketclose (`0x6DB6E8CD`, sys_net)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=1 callers=1 depth_from_entry=4 reachable_from_entry=1 ret_tested=1 context={'net': 69, 'core': 44, 'media': 20}
  - site 0x0002DC30 caller 0x0002CE94 (fn_0002CE94) depth=4 ret_test=cmpwi r3,0 branch_if=r3 < 0 error_side=taken
- Proposed exercise (plan only): socket/bind/setsockopt/init: CELL_SYSMODULE_NET is already loaded at boot. These may run during sceNp Init. Catch with SF_HLE_LRLOG from process start. Conditional net NIDs (the other 7) are not in this stub list.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

#### sys_net_free_thread_context (`0xFDB8F926`, sys_net)

- Class: IMPORTED-NOT-SEEN (CONFIRMED in available logs). Static sites=4 callers=2 depth_from_entry=4 reachable_from_entry=2 ret_tested=0 context={'net': 136, 'core': 63, 'media': 20}
  - site 0x0002DC24 caller 0x0002CE94 (fn_0002CE94) depth=4
  - site 0x0003289C caller 0x00032860 (fn_00032860) depth=6
  - site 0x000328E8 caller 0x00032860 (fn_00032860) depth=6
  - site 0x0003291C caller 0x00032860 (fn_00032860) depth=6
- Proposed exercise (plan only): socket/bind/setsockopt/init: CELL_SYSMODULE_NET is already loaded at boot. These may run during sceNp Init. Catch with SF_HLE_LRLOG from process start. Conditional net NIDs (the other 7) are not in this stub list.
- Risk: low (ASSUMED). Typical setting-sink or online/NP/AVC2/net/process-exit API. Returning 0 is often enough for offline play. VERIFY only if a log-only run shows the game reads an out-param the stub does not fill.

## Phase 2 — plan only (do not run on the PC in this pass)

- Wait for: the PC to be free and Saud not playing. SFRACE 19:01–19:30 already finished with SF_HLE_LRLOG; do not redo that in-world pass for stubs already counted. Parent agent launches any later PC run.
- Hook: SF_HLE_LRLOG=1 (already in 1786_voicediag / hooks/BUILD_NOTES.md). Movie v5 as of 27-Nov 18:09 does not contain this hook.
- Teleport tool: `/workspace/sf-autotester/lib/tp_tool.ps1  (guest XYZ 0x008D3800, [TEST-SALEM] only)`
- Checkpoint caveat: data/checkpoints.json has only village_x6499_partial (X confirmed, Y/Z missing). Do not goto it.

### 1. Log-only autotest exe with SF_HLE_LRLOG=1

SFRACE 19:01–19:30 already ran with SF_HLE_LRLOG (in-world stubs already counted). For the 28 still unseen: a shorter log-only boot+menus run, only when the PC is free and Saud is not playing. Use movie v5 + the existing voicediag SF_HLE_LRLOG hook (hooks/BUILD_NOTES.md), or any exe that already has that hook (1786_voicediag / SFRACE tree). Log-only, standing OK. Do not overwrite 1786_movie_v5 or PLAY_Strikeforce.bat. Optional bundle: census + lifecycle [sf-lc] + SF_ATRAC_LOG in the SAME log build (team rule 5). SF_AUTOLINK=1 skeletons are also log-only but need an include in port/stubs.cpp — only if that paste is already approved as diagnostic; otherwise LRLOG is enough.

### 2. Run env and capture

On a [TEST-SALEM] window only, state under sfauto (not Saud's play save): SF_HLE_LRLOG=1. Keep stderr+stdout. After quit, run lib/coverage.py on the log and copy only numbers (unique NIDs, per-NID counts, LRs, first stage/movie) back to /workspace/sf-stubs48/pc-results/. Do not copy EBOOT or lifted code.

### 3. Boot path (no teleport) — movies + title + OSK

Start the tester exe and do not skip cutscenes. This is the CONFIRMED home of cellSail GraphicsAdapterSetPreferredFormat / AddDescriptor, AudioOutSetCopyControl, cellKbRead, and (in 1817 stdout) OSK SetLayoutMode + SetInitialKeyLayout. Goal for IMPORTED-NOT-SEEN in cellSail, remaining OSK/OskExt, cellAudioOutConfigure, cellGame GetSizeKB/PatchCheck: see whether they fire before stage A. TELEPORT is not valid on the title screen (player XYZ is an in-world address).

Targets still unseen: `cellAtracGetSecondBufferInfo`, `cellAtracIsSecondBufferNeeded`, `cellSailDescriptorCreateDatabase`, `cellSailDescriptorDestroyDatabase`, `cellGameGetSizeKB`, `cellGamePatchCheck`, `cellAudioOutConfigure`, `cellOskDialogDisableDimmer`, `cellOskDialogSetInitialInputDevice`, `cellOskDialogSetSeparateWindowOption`, `cellSaveDataDelete2`

### 4. Enter Shu Chapter 1 village, then TELEPORT_SAVE

In-world stub traffic (lwcond_signal*, flip, KbRead) is already counted through SFRACE stage B. Known tester coordinates CONFIRMED in findings 19:31: start camp S = (6500, 4346, 7500), snow area 1 = (5960, 2494, 14983), written to all 8 position mirrors. checkpoints.json still has only village_x6499_partial (X only) — do not goto that one. If a later menus run needs the village/blacksmith, TELEPORT_SAVE a full XYZ once the player is standing (a write during knockdown is ignored; a single huge Z jump goes out of bounds). Do not teleport into an unloaded stage. Gate coords are still unknown.

Targets still unseen: `cellAtracGetSecondBufferInfo`, `cellAtracIsSecondBufferNeeded`, `sys_prx_exitspawn_with_level`, `sys_spu_image_close`, `cellRescSetBufferAddress`

### 5. Menus that may reach the leftover stubs

On the tester profile only: open save-data menu (cellSaveDataDelete2, cellFsRmdir/Utime — do not delete Saud's real save). Open options / name-entry if the remaining OSK stubs are still unseen. Title online/trophy/friends menus for sceNp* / sceNpTus / sys_net / cellSysutilAvc2 — no real PSN login. If they still never fire after one full boot+village+menus pass, leave them IMPORTED-NOT-SEEN and do not invent a teleport.

Targets still unseen: `cellFsRmdir`, `cellFsUtime`, `cellSysutilAvc2InitParam`, `cellSysutilAvc2SetAttribute`, `cellSysutilAvc2StartVoiceDetection`, `cellSysutilAvc2StopVoiceDetection`, `sceNpBasicGetEvent`, `sceNpBasicGetFriendListEntry`, `sceNpManagerGetChatRestrictionFlag`, `sceNpTusPollAsync`, `bind`, `setsockopt`, `socketclose`, `sys_net_free_thread_context`

### 6. What this run will decide

For every IMPORTED-NOT-SEEN stub: first [hle-lr] line, LR, stage/movie, count from [hle-lrc]. For sys_lwcond_signal / destroy / lwmutex_destroy: counts in the 2000 lines before stage A→B and around the hang. For cellAtrac second-buffer pair and cellAudioOutConfigure: r3/r4 and whether a 6ch configure happens. Then re-run this census on the new numbers. No behaviour-change build in this plan.

## Limits

- Stub vs linked is a text heuristic on the winning handler (KNOWN rule, ASSUMED result) from the 17:19 report. Every high-risk item must be checked by eye on the test-copy source before a fix is proposed.
- Winner order (ctx before table, port before library) is ASSUMED in that report. A 'stub' in the generated table may be shadowed by a real ctx handler — VERIFY especially for `sys_lwcond_signal`.
- Stage names A/B/C are inferred by `sf_lifecycle.py` from dispatch clusters and cache opens, not from an official mission string (except `Story: Shu Chapter 1` at 1817 stderr L9613).
- stdout and stderr line numbers are not comparable across streams.
- No behaviour-change build and no PC action in this pass.


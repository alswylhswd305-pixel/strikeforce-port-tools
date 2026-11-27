# تغطية دوال النظام (HLE) — Strikeforce BLUS30471

عدّ قراءة فقط من نسخة التجربة `ps3recomp-v020-test`. ما انبنى شيء وما تغيّر شيء.
وقت العد: 2026-11-26 21:29 (توقيت الكويت، UTC+3).

## خلاصة لسعود

اللعبة تستدعي **346** دالة من مكتبات النظام. في نسختنا الحين: **267** منفَّذة فعلًا، **32** دمية (ترجع نجاح فاضي أو مكتوبة كـ stub)، و**47** ناقصة (مو مسجّلة؛ إذا انطلبت ترجع CELL_OK فاضي).

من تشغيل اللعبة (كل ملفات `unresolved_nids.txt`، عددها 50): اللعبة **ضربت 6 دوال ناقصة**. الخمس الأهم للصوت/الفيديو هي دوال cellSail (فتح المشهد وأخذ إطار الصوت)، وفيها بعد دالة شبكة بلايستيشن واحدة (`sceNpBasicGetCustomInvitationEntryCount`). مكتبة الصوت العادية cellAtrac (20/20) و cellAudio (11/11) كلها مسجّلة؛ المشكلة مو إن دوال الستريمنغ ضايعة من التسجيل.

## Totals

| Category | Count | Notes |
|---|---:|---|
| Imported (unique NIDs in `out/EBOOT.imports.json`) | 346 | 26 modules; file mtime 2026-11-25 00:54 Kuwait |
| Registered (will dispatch to a handler) | 299 | generated table + port overrides + `ppu_sysprx_register` / `ppu_fs_register` |
| Implemented (non-trivial handler) | 267 | heuristic on the winning handler body |
| Stub (returns CELL_OK/0, or labeled stub/TODO, no real work) | 32 | see per-module table |
| Uncertain classification (registered, body not found) | 0 | none after manual review of the two keyboard handlers |
| Missing / unregistered | 47 | unresolved path fakes CELL_OK; includes 7 sys_net BSD calls that exist only under `PS3_NET_ONLINE` |

Sources used (all local, read-only):

- Import list: `out/EBOOT.imports.json` (346 entries, mtime 2026-11-25 00:54 Kuwait).
- Generated HLE table: `port/bld/ppu_hle_nids.cpp` (mtime 2026-11-26 21:21 Kuwait).
- Port overrides: `port/strikeforce_*.inc` via `ps3_load_prx_modules()` (these register first).
- Runtime extra regs: `runtime/ppu/ppu_sysprx.cpp` (`ps3_compute_nid` + literals), `runtime/ppu/ppu_fs.cpp`.
- Names: `ps3recomp/tools/nid_database.py`, `nid_from_protos.json`, SHA-1 `compute_nid`, plus the unresolved-name table in `ppu_hle.cpp`.
- Runtime hits: every `unresolved_nids.txt` under the test copy, plus `[hle] UNRESOLVED NID` lines in stderr logs.

Dispatch rule used: `ps3_hle_register_ctx` is searched before the generic table, so a ctx handler wins even if registered later. Within one table, the first registration wins (`ps3_nid_table_find`). Init order in `port/main.cpp`: `ps3_load_prx_modules` → `ppu_hle_init` → `ppu_sysprx_register` → `ppu_fs_register`.

A function is a **stub** only if the winning body is essentially unused-arg casts, an optional log, optional zero-fills / null checks, and `return CELL_OK` / `0` / a fixed error — or it is labeled stub/TODO/unimplemented with no real work. Short getters that read real decoder/FS/audio state count as implemented.

## Per-module table

| Module | Imported | Implemented | Stub | Uncertain | Missing | Runtime-hit missing |
|---|---:|---:|---:|---:|---:|---|
| cellSysutilAvc2 | 10 | 4 | 4 | 0 | 2 | — |
| sys_net | 18 | 6 | 5 | 0 | 7 | — |
| cellSysmodule | 3 | 3 | 0 | 0 | 0 | — |
| sys_io | 12 | 12 | 0 | 0 | 0 | — |
| cellGcmSys | 23 | 22 | 0 | 0 | 1 | — |
| sys_fs | 17 | 14 | 2 | 0 | 1 | — |
| cellSpurs | 17 | 17 | 0 | 0 | 0 | — |
| cellSysutil | 36 | 25 | 10 | 0 | 1 | — |
| cellL10n | 2 | 1 | 0 | 0 | 1 | — |
| sceNp | 29 | 22 | 2 | 0 | 5 | sceNpBasicGetCustomInvitationEntryCount |
| cellNetCtl | 4 | 4 | 0 | 0 | 0 | — |
| cellRtc | 3 | 3 | 0 | 0 | 0 | — |
| sceNpTrophy | 9 | 9 | 0 | 0 | 0 | — |
| cellOskExtUtility | 6 | 0 | 2 | 0 | 4 | — |
| cellGame | 10 | 9 | 0 | 0 | 1 | — |
| sceNpTus | 10 | 3 | 1 | 0 | 6 | — |
| sceNp2 | 26 | 24 | 0 | 0 | 2 | — |
| cellSync | 4 | 4 | 0 | 0 | 0 | — |
| cellOvis | 2 | 2 | 0 | 0 | 0 | — |
| cellResc | 12 | 10 | 1 | 0 | 1 | — |
| cellAtrac | 20 | 20 | 0 | 0 | 0 | — |
| cellAudio | 11 | 11 | 0 | 0 | 0 | — |
| cellSail | 34 | 20 | 1 | 0 | 13 | cellSailDescriptorSetEs, cellSailSoundAdapterGetFrame, cellSailDescriptorOpen, cellSailSoundAdapterUpdateAvSync, cellSailSoundAdapterGetFormat |
| cellPamf | 1 | 0 | 0 | 0 | 1 | — |
| cellSysutilAvconfExt | 1 | 1 | 0 | 0 | 0 | — |
| sysPrxForUser | 26 | 21 | 4 | 0 | 1 | — |
| **Total** | **346** | **267** | **32** | **0** | **47** | 6 distinct |

## Missing list (unregistered imports)

These NIDs have no always-on HLE registration. A call fakes `CELL_OK` and leaves out-params untouched (unless `PS3_HLE_UNRESOLVED=fail`).

| Module | NID | Name | Hit in runs? | Notes |
|---|---|---|---|---|
| cellSysutilAvc2 | `0x11F071CB` | `cellSysutilAvc2StopStreaming2` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSysutilAvc2 | `0xD42657DD` | `cellSysutilAvc2StartStreaming2` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sys_net | `0x13EFE7F5` | `getsockname` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| sys_net | `0x28E208BB` | `listen` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| sys_net | `0x64F66D35` | `connect` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| sys_net | `0xA50777C6` | `shutdown` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| sys_net | `0xC94F6939` | `accept` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| sys_net | `0xDC751B40` | `send` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| sys_net | `0xF9EC2DB6` | `getpeername` | not seen in unresolved_nids.txt | Not registered in the default test configuration. A real host-socket implementation exists in libs/network/sysNet.c but is only registered when PS3_NET_ONLINE is set; none of the PLAY_*.bat / sfauto launchers set that variable. |
| cellGcmSys | `0x3A33C1FD` | `_cellGcmFunc15` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sys_fs | `0x3140F6E1` | `cellFsSetIoBuffer` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSysutil | `0x3E22CB4B` | `cellMsgDialogOpenErrorCode` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellL10n | `0x0D90A48D` | `UCS2stoSJISs` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp | `0x27C69EBA` | `sceNpBasicAddFriend` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp | `0x01FBBC9B` | `sceNpBasicSendMessageGui` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp | `0x64A704CC` | `sceNpBasicRecvMessageAttachmentLoad` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp | `0x806960AB` | `sceNpBasicRecvMessageCustom` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp | `0xA8AFA7D4` | `sceNpBasicGetCustomInvitationEntryCount` | yes — max 2 calls, in 48/50 unresolved files | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellOskExtUtility | `0x09565B21` | `cellOskDialogExtInputDeviceUnlock` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellOskExtUtility | `0x1E1B4C97` | `cellOskDialogExtRegisterKeyboardEventHookCallback` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellOskExtUtility | `0x7C95FEB8` | `cellOskDialogExtInputDeviceLock` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellOskExtUtility | `0x8692FCD2` | `cellOskDialogExtRegisterConfirmWordFilterCallback` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellGame | `0x2A8E6B92` | `cellGameGetDiscContentInfoUpdatePath` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNpTus | `0x065B610D` | `sceNpTusSetMultiSlotVariableAsync` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNpTus | `0x1904435E` | `sceNpTusCreateTransactionCtx` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNpTus | `0x2E162A62` | `sceNpTusDestroyTitleCtx` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNpTus | `0x44ECA8B4` | `sceNpTusDestroyTransactionCtx` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNpTus | `0x7CAF58EE` | `sceNpTusCreateTitleCtx` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNpTus | `0xBB2877F2` | `sceNpTusGetMultiSlotVariableAsync` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp2 | `0x26AE9FF8` | `sceNpMatching2SignalingGetConnectionInfo` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sceNp2 | `0xE4AC32CA` | `sceNpMatching2GetRoomDataExternalList` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellResc | `0x0D3C22CE` | `cellRescSetWaitFlip` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x0247C69E` | `cellSailGraphicsAdapterGetFrame` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x0D0C2F0C` | `cellSailDescriptorSetEs` | yes — max 10 calls, in 50/50 unresolved files | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x15FD6A2A` | `cellSailDescriptorClose` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x1872331B` | `cellSailGraphicsAdapterPtsToTimePosition` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x44A20E79` | `cellSailGraphicsAdapterUpdateAvSync` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x4AE979DF` | `cellSailSoundAdapterPtsToTimePosition` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0x7EB8D6B5` | `cellSailSoundAdapterGetFrame` | yes — max 18 calls, in 50/50 unresolved files | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0xC044FAB1` | `cellSailDescriptorOpen` | yes — max 5 calls, in 50/50 unresolved files | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0xD1D55A90` | `cellSailPlayerSetPaused` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0xDDEBD2A5` | `cellSailAviMovieGetStreamByTypeAndIndex` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0xEEC22809` | `cellSailSoundAdapterUpdateAvSync` | yes — max 6 calls, in 34/50 unresolved files | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0xF25F197D` | `cellSailSoundAdapterGetFormat` | yes — max 5 calls, in 50/50 unresolved files | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellSail | `0xFFD58AA4` | `cellSailGraphicsAdapterGetFormat` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| cellPamf | `0x28B4E2C1` | `cellPamfReaderSetStreamWithTypeAndIndex` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |
| sysPrxForUser | `0x42B23552` | `sys_prx_register_library` | not seen in unresolved_nids.txt | No ps3_hle_register / ps3_hle_register_ctx for this NID. Unresolved calls fake CELL_OK. |

## Runtime: NIDs the game actually hits unregistered

Union of 50 `unresolved_nids.txt` files (play_cwd, play_cwd_clothv2/v3, and `sfauto/runs/*/cwd`). Newest file mtime is from the latest test run today.

| NID | Name | Max calls in one file | Files present | Still missing now? |
|---|---|---:|---:|---|
| `0x0D0C2F0C` | `cellSailDescriptorSetEs` | 10 | 50 | yes |
| `0x7EB8D6B5` | `cellSailSoundAdapterGetFrame` | 18 | 50 | yes |
| `0xC044FAB1` | `cellSailDescriptorOpen` | 5 | 50 | yes |
| `0xF25F197D` | `cellSailSoundAdapterGetFormat` | 5 | 50 | yes |
| `0xA8AFA7D4` | `sceNpBasicGetCustomInvitationEntryCount` | 2 | 48 | yes |
| `0xEEC22809` | `cellSailSoundAdapterUpdateAvSync` | 6 | 34 | yes |

The same six NIDs dominate stderr `[hle] UNRESOLVED NID` lines (100+ recent log files). Older logs from earlier today also reported NIDs that are **now registered** (they are no longer in `unresolved_nids.txt`):

| NID | Name | Status now |
|---|---|---|
| `0x15FD6A2A` | `cellSailDescriptorClose` | still missing |
| `0x18B4629D` | `cellSailPlayerFinalize` | registered (ctx in port\strikeforce_sail.inc) |
| `0x1F71ECBE` | `cellKbGetConfiguration` | registered (ctx in port\strikeforce_kb.inc) |
| `0x2AD091C6` | `UCS2stoUTF8s` | registered (ctx in port\strikeforce_l10n.inc) |
| `0x75370397` | `cellOskDialogExtSetInitialScale` | registered (ctx in port\strikeforce_osk.inc) |
| `0x76488BB1` | `cellSailGraphicsAdapterFinalize` | registered (ctx in port\strikeforce_sail.inc) |
| `0x7F21C918` | `cellOskDialogAddSupportLanguage` | registered (ctx in port\strikeforce_osk.inc) |
| `0x8A85674D` | `_cellSpursLFQueuePushBody` | registered (ctx in port\strikeforce_lfqueue.inc) |
| `0xA876C911` | `cellOvisInitializeOverlayTable` | registered (ctx in port\strikeforce_ovis.inc) |
| `0xB53C54FA` | `cellOskDialogSetKeyLayoutOption` | registered (ctx in port\strikeforce_osk.inc) |
| `0xD1462438` | `cellSailSoundAdapterFinalize` | registered (ctx in port\strikeforce_sail.inc) |
| `0xE800F586` | `cellOskDialogExtRegisterForceFinishCallback` | registered (ctx in port\strikeforce_osk.inc) |
| `0xFF0A21B7` | `cellKbRead` | registered (ctx in port\strikeforce_kb.inc) |

Notes on those historical hits: `cellSailPlayerFinalize` / `cellSailSoundAdapterFinalize` / `cellSailGraphicsAdapterFinalize` are registered by `port/strikeforce_sail.inc`. Several OSK Ext helpers are registered by `port/strikeforce_osk.inc`. `cellSailDescriptorClose` was seen in 2 early stderr logs only; it is still unregistered, but current play/test `unresolved_nids.txt` files do not list it.

## Sound-related coverage (what matters most)

### cellAtrac (in-game voices / streaming ATRAC)
Imported **20**, implemented **20**, stub **0**, missing **0**.

All 20 imports are registered. The seven streaming NIDs (`GetStreamDataInfo`, `AddStreamData`, `SetSecondBuffer`, `IsSecondBufferNeeded`, `GetBufferInfoForResetting`, `GetSecondBufferInfo`, `GetVacantSize`) are implemented in `libs/codec/cellAtrac.c` and also re-registered by `port/strikeforce_atrac.inc` as a safety net. They do **not** appear in current unresolved logs.

| NID | Name | Status |
|---|---|---|
| `0x006016DA` | `cellAtracGetBitrate` | implemented |
| `0x06DDB53E` | `cellAtracSetSecondBuffer` | implemented |
| `0x0F9667B6` | `cellAtracGetChannel` | implemented |
| `0x2642D4CC` | `cellAtracCreateDecoderExt` | implemented |
| `0x2BFFF084` | `cellAtracGetStreamDataInfo` | implemented |
| `0x46CFC013` | `cellAtracAddStreamData` | implemented |
| `0x5F62D546` | `cellAtracGetMaxSample` | implemented |
| `0x66AFC68E` | `cellAtracSetDataAndGetMemSize` | implemented |
| `0x761CB9BE` | `cellAtracDeleteDecoder` | implemented |
| `0x7772EB2B` | `cellAtracResetPlayPosition` | implemented |
| `0x78BA5C41` | `cellAtracSetLoopNum` | implemented |
| `0x8EB0E65F` | `cellAtracDecode` | implemented |
| `0x99EFE171` | `cellAtracIsSecondBufferNeeded` | implemented |
| `0x99FB73D1` | `cellAtracGetBufferInfoForResetting` | implemented |
| `0xAB6B6DBF` | `cellAtracGetLoopInfo` | implemented |
| `0xBE07F05E` | `cellAtracGetSecondBufferInfo` | implemented |
| `0xC9A95FCB` | `cellAtracGetVacantSize` | implemented |
| `0xCF01D5D4` | `cellAtracGetSoundInfo` | implemented |
| `0xDFAB73AA` | `cellAtracGetRemainFrame` | implemented |
| `0xFA293E88` | `cellAtracCreateDecoder` | implemented |

### cellAudio
Imported **11**, implemented **11**, stub **0**, missing **0**.

| NID | Name | Status | Detail |
|---|---|---|---|
| `0x0B168F92` | `cellAudioInit` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0x377E0CD9` | `cellAudioSetNotifyEventQueue` | implemented | non-trivial handler body (handler sf_an::hle_set_notify in port\strikeforce_audionotify.inc) |
| `0x4109D08C` | `cellAudioGetPortTimestamp` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0x4129FE2D` | `cellAudioPortClose` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0x5B1E2C73` | `cellAudioPortStop` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0x74A66AF0` | `cellAudioGetPortConfig` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0x89BE28F2` | `cellAudioPortStart` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0xCA5AC370` | `cellAudioQuit` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0xCD7BC431` | `cellAudioPortOpen` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0xE4046AFE` | `cellAudioGetPortBlockTag` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |
| `0xFF3626FD` | `cellAudioRemoveNotifyEventQueue` | implemented | non-trivial handler body (handler (void* in ps3recomp\libs\audio\cellAudio.c) |

### cellSail + cellPamf (cutscene / movie player — the functions the game actually misses)
cellSail imported **34** (registered 21, missing 13). cellPamf imported **1**, all missing.

| Module | NID | Name | Status | Hit in runs? |
|---|---|---|---|---|
| cellSail | `0x0247C69E` | `cellSailGraphicsAdapterGetFrame` | missing | — |
| cellSail | `0x0D0C2F0C` | `cellSailDescriptorSetEs` | missing | yes, max 10 |
| cellSail | `0x15FD6A2A` | `cellSailDescriptorClose` | missing | — |
| cellSail | `0x1872331B` | `cellSailGraphicsAdapterPtsToTimePosition` | missing | — |
| cellSail | `0x44A20E79` | `cellSailGraphicsAdapterUpdateAvSync` | missing | — |
| cellSail | `0x4AE979DF` | `cellSailSoundAdapterPtsToTimePosition` | missing | — |
| cellSail | `0x7EB8D6B5` | `cellSailSoundAdapterGetFrame` | missing | yes, max 18 |
| cellSail | `0xC044FAB1` | `cellSailDescriptorOpen` | missing | yes, max 5 |
| cellSail | `0xD1D55A90` | `cellSailPlayerSetPaused` | missing | — |
| cellSail | `0xDDEBD2A5` | `cellSailAviMovieGetStreamByTypeAndIndex` | missing | — |
| cellSail | `0xEEC22809` | `cellSailSoundAdapterUpdateAvSync` | missing | yes, max 6 |
| cellSail | `0xF25F197D` | `cellSailSoundAdapterGetFormat` | missing | yes, max 5 |
| cellSail | `0xFFD58AA4` | `cellSailGraphicsAdapterGetFormat` | missing | — |
| cellPamf | `0x28B4E2C1` | `cellPamfReaderSetStreamWithTypeAndIndex` | missing | — |

Registered cellSail functions (the other 21) are in `libs/codec/cellSail.c`, with Finalize overrides in `port/strikeforce_sail.inc`. The missing ones are **not** in that .c file at all — they were never implemented, not merely left unregistered.

## Stubs among imported, registered functions

32 imported functions are registered but classified as stubs:

| Module | NID | Name | Why |
|---|---|---|---|
| cellSysutilAvc2 | `0x16FF9BA0` | `cellSysutilAvc2StartVoiceDetection` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\cellSysutilAvc2.c) |
| cellSysutilAvc2 | `0x178982D9` | `cellSysutilAvc2StopVoiceDetection` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\cellSysutilAvc2.c) |
| cellSysutilAvc2 | `0x89456724` | `cellSysutilAvc2InitParam` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\cellSysutilAvc2.c) |
| cellSysutilAvc2 | `0xCCF0AEFF` | `cellSysutilAvc2SetAttribute` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\cellSysutilAvc2.c) |
| sys_net | `0x139A9E9B` | `sys_net_initialize_network_ex` | returns a constant (CELL_OK/0/error) with no real work (handler hle_net_zero in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sys_net | `0x6DB6E8CD` | `socketclose` | returns a constant (CELL_OK/0/error) with no real work (handler hle_net_zero in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sys_net | `0x88F03575` | `setsockopt` | returns a constant (CELL_OK/0/error) with no real work (handler hle_net_zero in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sys_net | `0xB0A59804` | `bind` | returns a constant (CELL_OK/0/error) with no real work (handler hle_net_zero in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sys_net | `0xFDB8F926` | `sys_net_free_thread_context` | returns a constant (CELL_OK/0/error) with no real work (handler hle_net_zero in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sys_fs | `0x2796FDF3` | `cellFsRmdir` | returns a constant (CELL_OK/0/error) with no real work (handler cellFsRmdir in ps3recomp\runtime\ppu\ppu_fs.cpp) |
| sys_fs | `0xBEF554A4` | `cellFsUtime` | returns a constant (CELL_OK/0/error) with no real work (handler cellFsUtime in ps3recomp\runtime\ppu\ppu_fs.cpp) |
| cellSysutil | `0x41F20828` | `cellOskDialogDisableDimmer` | returns a constant (CELL_OK/0/error) with no real work (handler sf_osk::hle_ok in port\strikeforce_osk.inc) |
| cellSysutil | `0x53E39DF3` | `cellOskDialogSetSeparateWindowOption` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\misc\cellOskDialog.c) |
| cellSysutil | `0x7F21C918` | `cellOskDialogAddSupportLanguage` | returns a constant (CELL_OK/0/error) with no real work (handler sf_osk::hle_ok in port\strikeforce_osk.inc) |
| cellSysutil | `0xB53C54FA` | `cellOskDialogSetKeyLayoutOption` | returns a constant (CELL_OK/0/error) with no real work (handler sf_osk::hle_ok in port\strikeforce_osk.inc) |
| cellSysutil | `0xC427890C` | `cellOskDialogSetInitialKeyLayout` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\misc\cellOskDialog.c) |
| cellSysutil | `0xEDADD797` | `cellSaveDataDelete2` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\system\cellSaveData.c) |
| cellSysutil | `0xF0EC3CCC` | `cellOskDialogSetLayoutMode` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\misc\cellOskDialog.c) |
| cellSysutil | `0xF3B4B43E` | `cellOskDialogSetInitialInputDevice` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\misc\cellOskDialog.c) |
| cellSysutil | `0x4692AB35` | `cellAudioOutConfigure` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\misc\cellAvconfExt.c) |
| cellSysutil | `0xC96E89E9` | `cellAudioOutSetCopyControl` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\misc\cellAvconfExt.c) |
| sceNp | `0xEB7A3D84` | `sceNpManagerGetChatRestrictionFlag` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\sceNp.c) |
| sceNp | `0x4026EAC5` | `sceNpBasicRegisterContextSensitiveHandler` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\sceNpBasic.c) |
| cellOskExtUtility | `0x75370397` | `cellOskDialogExtSetInitialScale` | returns a constant (CELL_OK/0/error) with no real work (handler sf_osk::hle_ok in port\strikeforce_osk.inc) |
| cellOskExtUtility | `0xE800F586` | `cellOskDialogExtRegisterForceFinishCallback` | returns a constant (CELL_OK/0/error) with no real work (handler sf_osk::hle_ok in port\strikeforce_osk.inc) |
| sceNpTus | `0x19BCE18C` | `sceNpTusPollAsync` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\network\sceNpTus.c) |
| cellResc | `0x8107277C` | `cellRescSetBufferAddress` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\video\cellResc.c) |
| cellSail | `0x2E3CCB5E` | `cellSailGraphicsAdapterSetPreferredFormat` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\codec\cellSail.c) |
| sysPrxForUser | `0x2C847572` | `_sys_process_atexitspawn` | returns a constant (CELL_OK/0/error) with no real work (handler crt_ok in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sysPrxForUser | `0x96328741` | `_sys_process_at_Exitspawn` | returns a constant (CELL_OK/0/error) with no real work (handler crt_ok in ps3recomp\runtime\ppu\ppu_sysprx.cpp) |
| sysPrxForUser | `0xA2C7BA64` | `sys_prx_exitspawn_with_level` | returns a constant (CELL_OK/0/error) with no real work (handler (void* in ps3recomp\libs\system\sysPrxForUser.c) |
| sysPrxForUser | `0xE0DA8EFD` | `sys_spu_image_close` | returns a constant (CELL_OK/0/error) with no real work (handler hle_spu_image_close in ps3recomp\runtime\spu\spu_raw.c) |

## Keyboard handlers (manual classification)

`cellKbRead` (`0xFF0A21B7`) and `cellKbGetConfiguration` (`0x1F71ECBE`) are registered by `port/strikeforce_kb.inc`. The automated body parser missed them because a comment sits between `)` and `{`. Both write a real output struct (no keys / US-101 config) and return `CELL_OK` or `CELL_KB_ERROR_INVALID_PARAMETER`. Counted as **implemented**, not stubs.

## Naming confidence

Every imported NID has a name. Names come from the generated/override registration string, `nid_from_protos.json`, the builtin NID database, or a SHA-1 `compute_nid` of a known SDK/RPCS3 symbol (verified to match the import NID). The four cellOskExtUtility names were confirmed by computing NIDs of the `cellOskDialogExt*` symbols listed in public RPCS3 `cellOskDialog.cpp`.

## What this count is not

- It is not a “percent of the game finished” figure.
- Registered + implemented does not mean the handler is complete or behaviour-identical to a real PS3 / RPCS3. Example: 6-channel ATRAC rejection would be an implementation bug, not a missing NID.
- LV2 syscalls used through a different path are outside this import-table count, except where a sysPrxForUser import is itself an HLE wrapper.
- Firmware, EBOOT, and lifted output were not copied off the PC.


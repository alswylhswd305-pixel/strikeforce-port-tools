# Port overrides

These files are added to a copy of ps3recomp's `templates/project/` (the port folder) and included from `stubs.cpp`
(patch `patches/0001-…`). Each one registers context handlers with `ps3_hle_register_ctx(NID, name, fn)` in
`ps3_load_prx_modules()`, replacing the v0.20.0 HLE for that NID. `strikeforce_lfqueue.inc` also defines the
`sf_lfq::` guest-memory helpers (`P`, `r16/r32`, `w16/w32/w64`) that the other three use, so keep the include order.

| File | NIDs | Log tag |
|---|---|---|
| strikeforce_lfqueue.inc | 0x011EE38B `_cellSpursLFQueueInitialize`, 0x8A85674D `_cellSpursLFQueuePushBody` | `[sf-lfq]` |
| strikeforce_l10n.inc | 0x2AD091C6 `UCS2stoUTF8s` | `[sf-l10n]` |
| strikeforce_knobs.inc | 0xF52639EA `cellGameBootCheck`, 0xDB9819F3 `cellGameDataCheck`, 0x370136FE `sceNpTrophyGetRequiredDiskSpace` | `[sf-knob]` |
| strikeforce_videoout.inc | 0x1E930EEF `cellVideoOutGetDeviceInfo` | `[sf-vo]` |

All are title-specific, minimal implementations (not general replacements) written from public struct layouts.

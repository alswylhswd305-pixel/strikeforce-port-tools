# Strikeforce audio fixes (box-only; not applied to the PC test folder)

Prepared 2026-11-26 ~08:20 Asia/Kuwait. No game launch, no test-folder rebuild, no sfauto/state touch.

Bundle: `/workspace/sf-shared/audio-fixes/`
(also copied under `/workspace/ps3recomp-study/saud-prior/port-overrides/`).

Unit checks run on the box:
- `test_audioout_layout` passed (DeviceInfo 136, State 20, modes at +8, soundMode at +12).
- `test_cellAtrac_stream` passed (prefix SetData, out-params filled, NODATA until a frame is fed, interleaved Add/Decode, then ALLDATA_IS_ONMEMORY).

---

## 1. Root cause

Saud heard audio once (low quality, stutter/echo) and later heard none. Those are two different failures, stacked.

### Silence

1. **`SPU_INTERP_UNLIFTED=1` and `PS3_DEV_FLASH` (flashATRAC.pic) are required.** MultiStream SPU image 391227015 jumps into firmware that is not in the EBOOT. Without the interpreter + dev_flash, KslMsUpdater does not cycle and there is no decoded audio. `PLAY_Strikeforce.bat` already sets both. A run started without that bat is silent.

2. **`cellAudioOutGetDeviceInfo` / `GetState` use the wrong struct layout** in v0.20 HLE (same class of bug as the video-out fix).
   - Official layout (Cell SDK / RPCS3): SoundMode is **8 bytes** (`layout` u32 at +4). DeviceInfo is **136 bytes**: latency **u16 at +6**, modes at **+8**, device **state=1 (AVAILABLE)**, latency **13**. GetState is **20 bytes**: downMixer at **+8**, soundMode at **+12**.
   - Current HLE: 4-byte SoundMode, no latency field, modes at +6, `memset` of the wrong size, device **state=2**, GetState writes downMixer at +4 and soundMode at +8.
   - The game reads soundMode at +12 and sees **type/channel/fs = 0**. That is a direct silence path. Device state 2 is not AVAILABLE.

### Stutter / echo

3. **cellAtrac streaming was unregistered.** The EBOOT imports 20 cellAtrac functions. These seven were missing and hit the generic unresolved stub (`r3 = CELL_OK`, out-params untouched):

   | NID        | Function                            |
   |------------|-------------------------------------|
   | 0x2BFFF084 | cellAtracGetStreamDataInfo          |
   | 0x46CFC013 | cellAtracAddStreamData              |
   | 0x06DDB53E | cellAtracSetSecondBuffer            |
   | 0x99EFE171 | cellAtracIsSecondBufferNeeded       |
   | 0x99FB73D1 | cellAtracGetBufferInfoForResetting  |
   | 0xBE07F05E | cellAtracGetSecondBufferInfo        |
   | 0xC9A95FCB | cellAtracGetVacantSize              |

   `SetDataAndGetMemSize` already logged "STREAMING is not implemented; this track will decode garbage" when only a prefix is in memory, then decoded past the fed bytes into whatever followed in guest RAM (garbage, repeats, echo). `GetRemainFrame` always wrote `-1` (ALLDATA_IS_ON_MEMORY), so the title had no reason to call GetStreamDataInfo / AddStreamData even if those had existed.

4. **Possible mixer underruns**, not patched here. The mixer already clears each consumed block (that kind of echo is handled). If the SPU interpreter cannot keep MultiStream on deadline, the mixer plays empty blocks (holes → stutter). Diagnose with `AUDIO_RATE=1`; do not change read-index or "wait for data" without a log — the title writes on the mix event, so holding a block would stall the producer.

---

## 2. Ready-to-apply files

All under `/workspace/sf-shared/audio-fixes/` (and the port-overrides copy).

| File | What it does |
|------|----------------|
| `cellAtrac.h.patch` / `cellAtrac.c.patch` | Streaming ring + host linear copy, the 7 functions, correct remain-frame / NODATA_IN_BUFFER. All-on-memory path unchanged. |
| `strikeforce_audioout.inc` | Overrides GetDeviceInfo (0x7663E368) and GetState (0xF4E3CAA0) with the SDK layout. |
| `strikeforce_atrac.inc` | Registers the 7 NIDs onto the patched C functions (needed if `gen_hle_nids` is not regenerated). |

### Apply steps (after the loading worker frees the PC)

Test folder: `<TEST_COPY>`

1. Copy the two `.inc` files into `port\` (same place as `strikeforce_videoout.inc`).

2. From the SDK copy root (the folder that contains `libs\codec\cellAtrac.c`, typically `ps3recomp\` inside the test folder):

   ```
   patch -p0 < cellAtrac.h.patch
   patch -p0 < cellAtrac.c.patch
   ```

   On Windows, from Git bash or apply the two files by hand. Back up `libs\codec\cellAtrac.c` and `.h` first.

3. In `port\stubs.cpp`, next to the other includes and `sf_register_*` calls:

   ```
   #include "strikeforce_audioout.inc"
   #include "strikeforce_atrac.inc"
   ```

   and inside `ps3_load_prx_modules()` (after `sf_register_videoout_overrides()`):

   ```
   sf_register_audioout_overrides();
   sf_register_atrac_overrides();
   ```

   `strikeforce_audioout.inc` uses `sf_lfq::P/w16/w32`, so it must be included **after** `strikeforce_lfqueue.inc`.

4. Rebuild the port executable (`port\bld\MyGameRecomp.exe`). Do **not** rebuild into a run that the loading worker is using.

5. Leave `PLAY_Strikeforce.bat` as it is (`SPU_INTERP_UNLIFTED=1`, `PS3_DEV_FLASH=...`). Do not clear `sfauto\state`.

Optional pre-rebuild checks on the box, already passed:

```
cc -std=c11 -o /tmp/test_audioout_layout saud-prior/port-overrides/test_audioout_layout.c
cc -std=gnu11 -Iinclude -o /tmp/test_cellAtrac_stream libs/codec/tests/test_cellAtrac_stream.c
```

---

## 3. Test run (schedule after the loading worker is done)

One short boot to the title screen (or character select / loading, wherever audio was heard before) with `PLAY_Strikeforce.bat`.

Add these for one diagnostic run only (stderr):

```
AUDIO_RATE=1
AUDIO_PEAK=1
```

Pass if:

- Title-screen / menu audio is audible (not silent).
- Stutter/echo is gone or clearly better.
- stderr contains `[sf-ao] GetDeviceInfo` and `[sf-ao] GetState`.
- stderr does **not** contain `UNRESOLVED NID 0x2BFFF084` (or the other six).
- If a track is streamed: `[cellAtrac] SetData: streaming N of M bytes` and later no "decode garbage" (that line was removed).
- `[cellAudio] Mixing thread started` is present.

If audio is good but still stutters and `AUDIO_RATE` shows many holes, that is MultiStream / SPU interpreter pace, not these HLE structs. Log the hole counts and leave the mixer alone until then.

If it is still silent with the bat env set, grab the first `[sf-ao]`, `[cellAtrac]`, `[cellAudio]`, and `[hle] UNRESOLVED` lines.

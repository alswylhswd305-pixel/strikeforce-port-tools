# play16 silence — cause and fixes

Run: sfauto `20261126-083638-39c869` (AUDIO_RATE=1 AUDIO_PEAK=1). Box-only analysis; nothing was applied to the PC.

## Confirmed cause: mix events never reach `_cellsurMixerMain`

The audio device and mixer thread are fine. The port is empty.

Evidence from the run:

- stdout: `cellAudio Init`, `Mixing thread started`, `PortOpen(nChannel=8, nBlock=8)`, `PortStart(port=0)`, **`SetNotifyEventQueue(key=0x0)`**.
- stderr: `_cellsurMixerMain` (tid 10) does `queue_create -> id=1 key=0x8000CAFE02460300 size=2`, then `event_queue_receive(q=1 timeout=9000000)`. That receive appears ~22 times over a long run — one wake per 9s timeout, not 187.5/s.
- `[audio-ring] port 0 ... ring=[........]` for the whole run; every `[audio-peak] peak=0.0000`; `silent 100%`, `underruns 0`, `holes 0`. The device is being fed silence on time. Nothing writes the port.
- `sys_event_find_queue_by_key(0)` in this runtime **returns 0**, so a registered key of 0 posts no events.

This is the same libmixer/`_mxr000` case RPCS3 handles explicitly in `cellAudio.cpp`: if `SetNotifyEventQueue` is called with key `0` or `0x8000CAFE02460300`, wait for `_cellsurMixerMain` to create the queue and **remap 0 to `0x8000CAFE02460300`**.

GetDeviceInfo was never called; GetState (ENABLED LPCM 2ch) succeeded and the port opened, so the AudioOut layout fix is not why this run is silent.

The title-screen path is statically linked libmixer + MultiStream (`KslMsUpdater`, SPU image 391227015, `flashATRAC.pic` opened and interpreted). cellSail GetFrame/GetFormat and the two unresolved Sail NIDs are for FMV (`movie000.pam` etc., `PlayerOpenStream` is already a stub). They do not explain title-screen silence. `sceNp 0xA8AFA7D4` is unrelated.

## Confirmed secondary: cellAtrac rejects 5.1 AT3P

`[cellAtrac] SetData: not an ATRAC3plus file (0x80610315)` twice, after `KslStrLoader` reads a 128 KB prefix of a RIFF from `BGMLink.g1l` (`/dev_bdvd/PS3_GAME/USRDIR/bgm/BGMLink.g1l`).

Those tracks are **ATRAC3plus, 6 channels, 48 kHz, block_align=1712** (WAVE_FORMAT_EXTENSIBLE, the AT3P GUID). `0x80610315` is `CELL_ATRAC_ERROR_ILLEGAL_DATA`, returned because `atrac_parse_riff` rejected `channels > 2`. The decoder already supports 6ch; the HLE and the 2-plane bridge did not.

This path is used later (after ~block 4200). Unblocking it matters once the mixer is waking, but it is not why the port was empty from the first block.

## Ready-to-apply files

All in `/workspace/sf-shared/audio-fixes/` (copies under `saud-prior/port-overrides/`).

| File | Role |
|------|------|
| **strikeforce_audionotify.inc** | **Primary silence fix.** Remaps `SetNotifyEventQueue(0)` (NID 0x377E0CD9) to `0x8000CAFE02460300`. |
| **cellAudio_notify.patch** | Same remap in `libs/audio/cellAudio.c`, plus a notify-loop fallback to the `_mxr000` key. Optional if the .inc is registered. |
| **cellAtrac_6ch.patch** | Incremental on the already-applied streaming `cellAtrac.c`: allow 1..8 channels, 8-plane PCM. |
| **at3_bridge.patch** | `at3p_decode` takes `float** planes` so 6ch frames can be written. Also updates `at3_stub.c`. Apply with `patch -p1` from the SDK root. |

### Apply (after the loading worker frees the PC)

Test folder: `<TEST_COPY>`

1. Copy `strikeforce_audionotify.inc` into `port\`. In `port\stubs.cpp`, include it after `strikeforce_lfqueue.inc` and call `sf_register_audionotify_overrides()` from `ps3_load_prx_modules()`.

2. From the SDK copy root (the tree that has `libs\codec\cellAtrac.c` and `third_party\`):

   ```
   patch -p0 < cellAtrac_6ch.patch
   patch -p1 < at3_bridge.patch
   ```

   Optional, if you prefer the SDK notify remap instead of or in addition to the .inc:

   ```
   patch -p0 < cellAudio_notify.patch
   ```

   Back up the touched files first. `cellAtrac_6ch.patch` is incremental on the previous streaming patch; do not re-apply the original `cellAtrac.c.patch`.

3. Rebuild `port\bld\MyGameRecomp.exe`. Do not rebuild over a live loading-worker run. Leave `PLAY_Strikeforce.bat` and `sfauto\state` alone.

Box check already passed: `test_cellAtrac_stream` (streaming bookkeeping + 6ch header parse).

### Test run

Same as play16: boot to the title screen with `PLAY_Strikeforce.bat`, `AUDIO_RATE=1 AUDIO_PEAK=1`.

Pass if:

- stderr has `[sf-an] SetNotifyEventQueue(0) remapped to 0x8000CAFE02460300` (or the `[cellAudio] ... remapped` line if only the SDK patch is used).
- `[audio-peak]` is not stuck at 0; `silent` is not 100%.
- `_cellsurMixerMain` no longer wakes only once per 9s (receives should track the 187.5 Hz mix).
- `[cellAtrac] SetData: parse failed ... ch=6` should be gone; a successful `SetData ... ch=6` line is expected if that path runs.

If the port now has data but it still stutters, look at `AUDIO_RATE` holes (SPU interpreter pace). If it is still silent, grab the first `[sf-an]` / `[cellAudio] SetNotify` line and whether `event_queue_receive(q=1` is still only on a 9s timeout.

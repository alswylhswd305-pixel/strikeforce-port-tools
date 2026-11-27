# Cutscene movies: licence-safe PAMF/AVC playback for cellSail (never skip a cutscene)

2026-11-26, ~13:15 UTC+3. Research only; nothing was installed or run on Saud's PC.

Pins:
- **P** = ps3recomp e85647a33ce5f9391788f0e3f52ab395a7fe6a89 (`P:` means https://github.com/sp00nznet/ps3recomp/blob/e85647a33ce5f9391788f0e3f52ab395a7fe6a89/)
- **R** = RPCS3 0ca5eb0efe50ec4e8aa07892ab86d57842246eb4 (`R:` means https://github.com/RPCS3/rpcs3/blob/0ca5eb0efe50ec4e8aa07892ab86d57842246eb4/rpcs3/)

## What Strikeforce uses

KNOWN, from `sf-shared/progress-src/out/EBOOT.imports.json` (names mapped with this port's `ppu_hle_nids.cpp` plus P's nid tables):
- **cellSail: 34 imports.** Of those:
  - player: `cellSailPlayerInitialize2`, `Boot`, `OpenStream`, `Start`, `Stop`, `CloseStream`, `Create`, `Add`, `DestroyDescriptor`;
  - descriptor: `cellSailDescriptorCreateDatabase`, `SetAutoSelection`;
  - graphics adapter: `cellSailGraphicsAdapterInitialize`, `SetPreferredFormat`, `GetFormat`, `GetFrame` (not GetFrame2), `UpdateAvSync`, `PtsToTimePosition`;
  - sound adapter: `cellSailSoundAdapterInitialize`, `GetFormat`, `GetFrame`, `UpdateAvSync`, `PtsToTimePosition`;
  - 5 NIDs still unnamed: 0x0D0C2F0C, 0x15FD6A2A, 0xC044FAB1, 0xD1D55A90, 0xDDEBD2A5 (VERIFY with `nid_database --lookup`).
- **cellPamf:** 1 import (0x28B4E2C1, unnamed).
- **No cellVdec, cellDmux or cellAdec imports.** The game hands the whole movie to cellSail, and the real libsail does the demux and decode internally.
- **cellAtrac: 20 imports**, used for game audio; that path already exists.

## What exists today

**In ps3recomp master (KNOWN):**
- `P:libs/codec/cellSail.c` is a lifecycle stub ("No actual media playback occurs", L1-L7). `cellSailPlayerStart` sets RUNNING, then FINISHED at once, and notifies STOP_TRANSITION then OPENED (L202-L219). That is the skip Saud doesn't accept.
- **cellVdec decodes H.264 and MPEG-2 through FFmpeg loaded at run time**, never linked: `P:libs/codec/ffmpeg_runtime.h#L1-L24` (`PS3RECOMP_FFMPEG_RUNTIME`, `avcodec-63.dll`, "FFmpeg stays a separate, user-supplied LGPL library"), and `P:libs/codec/vdec_ffmpeg.c#L98-L99` (`AV_CODEC_ID_H264`, `AV_CODEC_ID_MPEG2VIDEO`). It is tested against FFmpeg's own decode (`P:libs/codec/tests/test_vdec_decode.c#L1-L25`).
- **ATRAC3/ATRAC3plus decoder:** `P:third_party/at3_standalone/`. It is FFmpeg's decoder via PPSSPP, LGPL-2.1+, kept as a separable component, while the rest of ps3recomp is MIT (its README.txt). It is wired into `cellAtrac.c` (L25), but `cellAdecAtrac3p.c` is still a silence stub (L1-L7).
- `P:libs/codec/cellDmux.c` is a stub ("Without real MPEG-TS parsing", L1-L7).
- `P:libs/codec/cellPamf.c` uses a header layout that **disagrees with RPCS3's**:
  - P: stream table at 0x10, 24-byte descriptors, raw types 1-6 (L34-L58).
  - RPCS3: 0x10 is `psmf_marks_offset`, "always 0"; stream headers are 0x30 bytes from 0x88; coding types 0x1B AVC, 0x02 M2V, 0xDC ATRAC3plus, 0x80 LPCM, 0x81 AC3 (`R:Emu/Cell/Modules/cellPamf.h#L45-L50`, `#L284-L306`, `#L365-L433`).
  - ps3kit reads the header the RPCS3 way (data offset = `be32(8)*0x800`, PTS at 0x58/0x5E).
  - So treat P's cellPamf as **unverified** (VERIFY against a real .pam). Don't build on it.

**In RPCS3 (KNOWN):** RPCS3's HLE cellSail is unimplemented too:
- `cellSailPlayerStart` is `UNIMPLEMENTED_FUNC` (`R:Emu/Cell/Modules/cellSail.cpp#L985-L989`);
- `cellSailGraphicsAdapterGetFrame` is `todo` (#L336-L340).

RPCS3 has no HLE recipe to copy here. Movies there come from the firmware's libsail running as LLE over RPCS3's HLE cellVdec/cellDmux/cellAdec. ASSUMED; VERIFY in an RPCS3 log of a Strikeforce cutscene.

## Other ports that play movies (KNOWN, MIT unless stated)

| Port | Path | Codec | Notes |
|---|---|---|---|
| **ps3kit `runtime/sail.cpp`** (vs-sr-dev, MIT, 2026-10-23) https://github.com/vs-sr-dev/ps3kit/blob/38b0a12010b32fdd1e1bd4087d9be8579f39af01/runtime/sail.cpp | full **cellSail** state machine on a player thread: Boot, OpenStream, Start, EOS, Stop, CloseStream, with all the state and event callbacks (L1-L24). Graphics adapter frames come through the game's alloc callback and are shown at PTS. PAMF header parse at L181-L192; MPEG-PS reader in `runtime/mpegps.h` | MPEG-2 only, with its own decoder (`runtime/mpeg2.cpp`) | the closest template for Strikeforce. Its own ABI (not ps3recomp's), so port the logic. It uses GetFrame2; Strikeforce uses GetFrame |
| **Killzone 1 HD, project-vekta `port/kz1hd/sail.cpp`** (MIT) https://github.com/gustavomorinaga/project-vekta/blob/fd97c34f56541751058e7b3d17074a71d00bad3c/port/kz1hd/sail.cpp | cellSail over FFmpeg. The game-side protocol is documented in its header (L1-L27): call-completed callback (major 2), state-changed (major 3, needs RUNNING then OPENED at EOS); `GraphicsAdapterGetFrame` returns ≥0x100 for a new frame (info +0 buffer, +0x10 pts); `SoundAdapterGetFrame(adapter, 256, info)` gives 256 stereo float frames, big-endian | AVI (MPEG-4 Part 2 + MP3), via libavformat | the same **GetFrame / SoundAdapterGetFrame** calls Strikeforce imports. The struct offsets are KZ1's reading of firmware behaviour (ASSUMED to be the same for libsail generally; VERIFY) |
| **Killzone 2, project-pyrrhus** (MIT) https://github.com/undecuple/project-pyrrhus/blob/bc3301d2032da208ee0213289f305f5418fd327b/NOTICE.md (L51-L52) | the game's own player over P's **cellVdec + FFmpeg 9.0.1 LGPL DLLs** (`avcodec-63.dll`, `avutil-61.dll`, "LGPL-only … H.264, MPEG-2 and AC3 decoders only", loaded at run time, replaceable), plus `at3_standalone.dll` for ATRAC3+ | H.264 + AC3 + ATRAC3+ | a shipped, licence-documented precedent for exactly our decoder stack |

## Decoder options

| Option | Licence | H.264 profiles | Windows | Effort | Verdict |
|---|---|---|---|---|---|
| **FFmpeg via P's run-time loader** (`ffmpeg_runtime.h`) | LGPL-2.1+ when built without GPL/non-free parts. Dynamic loading plus replaceable DLLs plus source offer satisfies the LGPL (see https://ffmpeg.org/legal.html; KZ2 NOTICE.md shows the full compliance set) | all that FFmpeg's h264 decoder handles (Baseline/Main/High) | yes; KZ2 ships it | **S**: already wired into cellVdec | **recommended** |
| **Windows Media Foundation H.264 MFT** (`CLSID_CMSH264DecoderMFT`) | part of the OS, nothing to redistribute | "Baseline, Main, and High profiles, up to level 5.1" (https://learn.microsoft.com/en-us/windows/win32/medfound/h-264-video-decoder) | yes (Windows only; N editions need the Media Feature Pack, ASSUMED) | M: new back end beside `vdec_ffmpeg.c` | good **fallback**, or the default if Saud wants zero third-party DLLs |
| **Cisco openh264** | BSD-2-Clause source (https://github.com/cisco/openh264). Cisco's prebuilt binary carries their patent licence (https://www.openh264.org/BINARY_LICENSE.txt) | **decoder: "Constrained Baseline Profile up to Level 5.2"** (README, Decoder Features) | yes | M | **not suitable** if the movies are Main/High (VERIFY with pamf_probe below) |
| D3D12 Video Decode | OS API | hardware-dependent | yes | L | not worth it for a few cutscenes |
| ATRAC3plus audio: **P `third_party/at3_standalone`** | LGPL-2.1+ (separable, in tree) | n/a | yes | S-M (feed it the demuxed ATRAC3+ AUs, output PCM to the sound adapter) | **recommended** |

Patents (not legal advice): H.264 decoding can carry patent obligations that a code licence doesn't cover. Media Foundation is covered by the OS licence. For FFmpeg, see the patent section of ffmpeg.org/legal.html; Saud should decide. ASSUMED.

## Recommended path (KNOWN parts and ASSUMED effort marked)

**Step 0: VERIFY the codec, 5 minutes.**
- On Salem's PC, run `python sf-shared/tools/pamf_probe.py <USRDIR>/…/movie000.pam`. It prints each stream's coding type and, for AVC, `profile_idc`/`level_idc` (66 = Baseline, 77 = Main, 100 = High).
- It is pure Python, with offsets taken from RPCS3's cellPamf.h as facts. It was tested on the box with a synthetic header only.

**Step 1: port-local HLE cellSail that really plays (M, about 1-2 weeks, ASSUMED).** Take the state machine and adapter protocol from ps3kit `sail.cpp` and the KZ1 header notes (MIT, port the logic) and implement:
1. a player thread; every call returns at once and completes through the game's callback;
2. a PAMF header read (offsets as in pamf_probe), then an MPEG-PS PES reader (ps3kit `mpegps.h` as the model);
3. AVC elementary stream → P's FFmpeg back end (reuse `vdec_ffmpeg.c` and `vdec_store_picture` for I420 → the guest's requested format);
4. frames written into buffers from the graphics adapter's alloc callback, and handed out from `cellSailGraphicsAdapterGetFrame` at PTS on the host clock;
5. ATRAC3plus AUs (private stream 0xBD) → `at3_standalone` → PCM via `cellSailSoundAdapterGetFrame`;
6. state RUNNING → at EOS, the source-EOS event then OPENED; Stop → OPENED.

**Step 2:** keep the current skip behaviour only behind an explicit switch (e.g. `SF_SAIL_SKIP=1`) for debugging. The default must play, per Saud's rule.

**Step 3:** later, upstream the cellSail implementation to ps3recomp (needs Saud's or Salem's OK).

**Rejected path:** LLE of the firmware libsail through `docs/FIRMWARE_LLE.md` (the same pipeline as libsre). It would also need real cellDmux, cellAdec-ATRAC3+ and cellVpost HLE underneath, and P's are stubs (above). It is more unknowns than writing cellSail directly.

## How to verify

- `pamf_probe` gives the codec. Expected: AVC plus ATRAC3plus (ASSUMED until run).
- **First movie:** frames appear, the game advances only at EOS, audio stays in sync (`UpdateAvSync` gets called), and **no cutscene is skipped**.
- **Pixel check:** decode one frame with the `ffmpeg` CLI from the demuxed ES and compare it with our frame dump (FLIP or odiff, github-tools-researcher.md).

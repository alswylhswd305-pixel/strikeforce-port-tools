# atrac-validator: ATRAC3plus stream validator (Strikeforce BLUS30471, ps3recomp)

`atrac_validator.py` uses the Python 3 standard library only. It is our own code: no GPL/LGPL/RPCS3 code was copied, and public docs are paraphrased.
It reads logs and bytes and changes nothing.
On Saud's PC it is run read-only, and only derived numbers (hashes, offsets, counts) come back.

Labels: **KNOWN** means read from bytes/logs/public docs in hand. **ASSUMED** means inference. **VERIFY** means it needs the PC run.

## Files
| file | what |
|---|---|
| `atrac_validator.py` | the tool (sub-commands below) |
| `out_existing_logs/` | report.md + CSVs from the [cellAtrac] lines already on the box |
| `selftest.txt` | last self-test output |

## Sub-commands
```
python atrac_validator.py selftest
python atrac_validator.py header   TRACK.at3
python atrac_validator.py hashfile TRACK.at3 --out TRACK_frames.tsv [--ranges SF_ATRAC_LOG.txt]   # PC, read-only
python atrac_validator.py hostcmp  --orig TRACK.at3 --host clipNNNN_hXXXXXXXX_host.bin --out hostcmp.csv  # PC, read-only
python atrac_validator.py analyze  --log LOG [--log LOG2] [--hashes TRACK_frames.tsv] [--hostcmp hostcmp.csv]
                                   [--pcm dump.f32 --pcm-ch 6 --pcm-fmt f32be [--pcm-ref ref.f32]] --out DIR
```
- **hashfile** prints the header fields plus one line per frame: `k, offset, fnv1a32, byte0`. With `--ranges LOG` it also prints `R off len fnv` for every add range logged by SF_ATRAC_LOG. The raw track never leaves the PC; only this TSV does.
- **hostcmp** compares a host-copy dump against the original track, frame by frame. The dump is the linear copy the decoder actually read from, written by the existing `SF_ATRAC_DIAG=1 SF_ATRAC_DUMP=<dir>` build as `clip*_h*_host.bin` at clip end.
  - Each frame gets a status: `ok`, `zeros` (never written), `moved` (bytes found elsewhere in the file; `src_offset` and `delta` say where), or `unknown`.
  - Output is numbers only.
- **analyze** writes `report.md`, `feeds.csv`, `findings.csv`, `error_episodes.csv`, `header_inference.csv`, `hostcmp_runs.csv` and `rms_*.csv`.

## Inputs accepted (one parser, three formats)
1. **Existing `[cellAtrac]` lines:**
   - `SetData: streaming R of TOTAL bytes, ring=B`
   - `SetData handle=.. ch=.. frames=.. first=.. end=.. loop=[a,b) all_on_mem=..`
   - decoder errors `Atrac3/3+: ...` (one line per rejected frame)
   - The decoder-error lines carry no handle. They are attributed to the open 6ch epoch, and the physics agent confirmed they are all the 6ch handle.
2. **Existing `[atrac-diag]` lines** (`SF_ATRAC_DIAG=1` private build, `atrac/work/atrac_trace.c`): SetData `buf= read= bufbytes= rc= total=`, GetStreamDataInfo `wptr= writable= readpos=`, AddStreamData `add= rc=`, ResetPlayPosition `sample= writebyte=`, Decode, CLIP-END.
3. **Proposed `[sf-atrac]` lines** (SF_ATRAC_LOG=1, below): generic `key=value`. The §4 field names from `voicefreeze/blackhang_1817.md` are accepted as aliases (`handle`, `function`, `file_fed`, `valid_off`, `valid_bytes`, `write_given/used`, ...).
- Audio clock proxy: count of `[WAIT] event_queue_receive(q=1 ... tid=10` lines (`--tick-re`). It is used only to split error episodes and is never used as time (ASSUMED proxy).

## Checks
1. **Frame grid.** A decoder feed is valid iff `(offset - data_start) % frame_bytes == 0` and `len == frame_bytes`.
   - The delta patterns are classified as:
     - `constant`: wrong data_start.
     - `growing`: wrong frame size.
     - `stride_mixup`: the stride used = frame_bytes x ch_a/ch_b, or another stream's frame size.
     - `step`: on the grid, then a constant offset from frame k0 on, meaning a dropped or duplicated add, or a seek that kept the old base.
   - Ring *adds* do not need to be frame-aligned. The first SetData feed is 131072 bytes, and 131072 % 1712 = 960 (KNOWN). So adds are checked for continuity instead (check 3), not for the grid.
2. **Hash compare.** Every decoded frame's FNV-1a is compared against the file frame at that offset. A mismatch is named as `ZEROS`, `file_frame_j (delta ±n frames)` or `none`. hostcmp does the same at byte level on the PC and also finds non-aligned sources.
3. **Seek without flush.** After ResetPlayPosition, it flags any decode of a frame < target-1, or any decode of bytes in the never-fed hole `[old_fed, roff)`.
   - Write pointer: an AddStreamData whose `wea_used` differs from the `wea_given` returned by GetStreamDataInfo, an add offset different from the running sum of adds, a `readpos` drift, or a rejected add (`rc=0x80610342 ADD_DATA_IS_TOO_BIG`).
   - **Late ring write** (new suspect, ASSUMED): our AddStreamData copies the guest ring at call time (KNOWN, cellAtrac.c L485).
     - If the title calls it before its own read into the ring has landed, the host copy keeps zeros or the previous lap's bytes.
     - Test: an `AddRecheck` line re-hashes the same ring bytes later. If they changed, this is confirmed. If the re-read matches the file (`hashfile --ranges`), the fix is to copy later.
4. **Per-channel RMS.** Input is an interleaved PCM file: `f32be` (what cellAtracDecode writes), `f32le`, `s16le`, or a .wav. `--pcm-ch` channels, 2048 samples per frame.
   - It flags `silent` (rms < 1e-5 while another channel > 1e-3), `clipped` (peak ≥ 0.999 full scale), `burst` (frame energy > 4x the median of ±8 frames, marked `_after_bad_feed` when within 2 frames of one) and `swapped`.
   - `swapped` means a channel's log-RMS envelope correlates best with a different channel of `--pcm-ref`, such as an RPCS3 recording of the same track (r > 0.8 and 0.2 better than its own).
   - Without a reference it flags `energy_moved` instead: one channel drops 30 dB while another rises 30 dB in the same frame.
   - The check is skipped when no PCM is given.

## Header / frame math: what is KNOWN, ASSUMED or VERIFY
- KNOWN (public docs: MultimediaWiki ATRAC3plus, Imagisphere AT3 page, the Microsoft WAVEFORMATEXTENSIBLE layout, vgmstream riff.c):
  - An .at3 file is RIFF/WAVE.
  - The `fmt ` chunk is WAVE_FORMAT_EXTENSIBLE (0xFFFE) with SubFormat GUID E923AABF-CB58-4471-A119-FFFA01E4CE62.
  - `nBlockAlign` (fmt+12) is the size in bytes of one whole ATRAC3plus frame, all channels together.
  - Each frame decodes to 2048 samples per channel, and frames are contiguous from the first byte of the `data` chunk payload.
  - `fact` holds sample counts. `smpl` (optional) holds the loop, and when it is absent the data moves 0x44 earlier.
- KNOWN (OMA, from Rockbox oma.c, the MP3FM FORMAT.md and the MediaInfo OpenMG parser):
  - An optional ID3-style `ea3` tag (syncsafe size) is followed by a 96-byte `EA3` header.
  - The codec id is at +0x20 (0 = ATRAC3, 1 = ATRAC3plus), with 24-bit big-endian params at +0x21.
  - The low 10 bits are the frame size in 8-byte units. For ATRAC3plus, frame bytes = (raw+1)*8. The data starts right after the 96 bytes.
  - VERIFY: the meaning of the 3-bit channel code for 5.1 (the tool does not use it).
- KNOWN, derived from the logs on the box: for the 7 looped 6ch tracks, `total - frames*1712 = 168`, and for the one unlooped track it is 100.
  - 1712 is the only block_align in [64, 8192) consistent with all 8 tracks and a small data_off.
  - 168 = 12 (RIFF) + 60 (fmt 52) + 20 (fact 12) + 68 (smpl 60) + 8 (data header). Without smpl it is 100.
  - So the parsed header is self-consistent and the frame grid our HLE uses (`data_off + k*1712`) is right.
  - It ASSUMES data_bytes is an exact multiple of 1712. VERIFY with `hashfile` on the real track (`data_start`, `tail_bytes`).
- KNOWN, from the vendored decoder's structure (LGPL; read, not copied):
  - The 6ch layout is 4 channel units: stereo, mono, stereo, mono.
  - Byte 0 of a good 6ch frame has bit 7 = 0 (start bit), and bits 6-5 = 01, so 0x20..0x3F.
  - The decoder prints exactly one error line per rejected frame.
  - `ch_block 0 >= 4` means the first unit tag was 00 (mono).
  - VERIFY on the real track: `hashfile` prints `frames_with_bad_byte0`, which should be 0.

## Found on the existing box logs (no per-call lines exist yet)
Full table: `out_existing_logs/report.md`. Logs used: 18:17 blackhang, 17:27 voicediag, sh1780, shadowdiag, and the gE extract.
- KNOWN counts: 6ch decoder errors per track epoch: 18:17: 80/65/16/13/70; 17:27: 385 (one track, 1690 frames); sh1780: 232/139; shadowdiag: 77/89.
- **Two different error signatures (KNOWN counts):**
  - **zeros-like**: 6 episodes, 771 errors, 99.2% are `ch_block 0`. That is what all-zero frames give.
    - **All 6 are exactly whole 131072-byte chunks**: 78, 77, 77, 78 and 77 frames = 1 chunk, and 384 frames = 5 chunks (131072/1712 = 76.6, so a chunk touches 77-78 frames).
    - The SetData prefix is also 131072 bytes (KNOWN). The title's add size being 131072 is ASSUMED until SF_ATRAC_LOG shows it.
  - **random-like**: 10 episodes, 383 errors, split 56.9% start-bit / 14.9% ch_block 0 / 11.5% extension. Uniformly random bytes would give 50 / 12.5 / 12.5.
    - So these frames hold real-but-wrong bytes (misaligned or stale), not zeros.
    - The "Channel unit extension" message is just the 1-in-8 random case (consistent with blackhang §3).
- ASSUMED reading: the bad data arrives in whole add-sized chunks. Either a chunk was never written (zeros) or it holds bytes from somewhere else (random-like), and the frame grid itself is fine.
  - That points at the add path: a chunk taken before the title's read landed, from the wrong ring position, or rejected and shifted.
  - It does not point at the header or at decode_frame's offset math.
  - A forward seek that walks the calloc'd hole would also give zeros, but its size would be the seek distance, not whole chunks. That makes suspect (a) less likely for these episodes, though not ruled out.
- Verdicts on these logs: all 4+1 suspects are **unknown**, because the per-call lines are needed. Header is "not supported by evidence" (derived, VERIFY).

## Recommended SF_ATRAC_LOG=1 fields (addition to blackhang_1817.md §4; that file was not edited)
One line per call, prefix `[sf-atrac]`, `key=value`, hex with 0x:
```
[sf-atrac] fn=SetData           tid= h= ch= ba= doff= first= end= ls= le= buf= bufsz= read= total= rc=
[sf-atrac] fn=GetStreamDataInfo tid= h= wea_given= writable= readpos= voff= vbytes= fed= rc=
[sf-atrac] fn=AddStreamData     tid= h= add= off=<file offset = fed before the add> wea_given=<last GetStreamDataInfo> wea_used=<EA actually copied> voff= vbytes= fed_after= rc= fnv=<FNV-1a of the bytes copied>
[sf-atrac] fn=AddRecheck        tid= h= off= len= fnv=<FNV-1a of the SAME ring bytes re-read at the next call on this handle>
[sf-atrac] fn=GetBufferInfoForResetting tid= h= sample= info_wea= info_bytes= info_min= info_readpos= rc=
[sf-atrac] fn=ResetPlayPosition tid= h= sample= wb= roff= fed_before= fed_after= next_frame_before= flushed=<0/1> rc=
[sf-atrac] fn=DecodeFrame       tid= h= k= off=<data_off+k*ba actually passed> len= fnv=<FNV-1a of those len bytes> b0=<byte0> rc=<decoder rc>
[sf-atrac] fn=DecodeError       tid= h= k= off= len= fnv= first16=<hex> msg="..."
[sf-atrac] fn=Pcm               tid= h= k= rms=<r0,r1,..,r5> peak=<p0,..,p5>      (optional, per frame)
```
- FNV-1a 32-bit: h = 0x811C9DC5, then for each byte `h = (h ^ b) * 0x01000193 mod 2^32`.
- `tid` is required. AddStreamData (KslStrLoader) and Decode (KslAt3Decoder) run on different host threads, and our cellAtrac.c takes no lock (KNOWN: no mutex in the file).
- Uncapped for the 6ch handle only, and DecodeFrame lines only for the 6ch handle (about 23 per second).

## Run steps on Saud's PC (Salem; read-only; needs Saud's OK)
0. `python atrac_validator.py selftest` should print 27/27.
1. **Without a rebuild**, if the SF_ATRAC_DIAG build is there:
   - Run with `SF_ATRAC_DIAG=1 SF_ATRAC_DUMP=<dir>` until BGM errors appear and the track changes or is deleted, so the CLIP-END dump is written.
   - Then run `hostcmp --orig <original track> --host <dir>\clip*_h119FA1F0_host.bin --out hostcmp.csv`.
   - VERIFY: where the original track bytes are on the PC (inside the game's archive). hostcmp needs the original as a plain file. If it isn't one, `hashfile` on whatever plain copy exists is enough.
2. `hashfile <original track> --out frames.tsv`.
3. Send back only `hostcmp.csv`, `frames.tsv` and the stderr log. These are numbers only, no audio bytes.
4. With the SF_ATRAC_LOG build: run once, then run `hashfile <track> --ranges <log> --out frames.tsv`, and send back the log and the TSV.

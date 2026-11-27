#!/usr/bin/env python3
"""pamf_probe.py <file.pam> [...]: print each PAMF stream's coding type (and the AVC profile/level).

Layout read as facts from RPCS3 0ca5eb0 rpcs3/Emu/Cell/Modules/cellPamf.h
(PamfHeader L418-433, PamfSequenceInfo L394-414, PamfGroupingPeriod L377-390,
PamfGroup L365-373, PamfStreamHeader L284-306, coding types L45-50). No code copied.
  header_size at 0x08 (x2048 = data offset), start/end PTS at 0x58/0x5E,
  stream count at 0x87, stream headers from 0x88, 0x30 bytes each:
  +0 coding type, +4 stream_id, +5 private_stream_id, +0x10 AVC profileIdc, +0x11 levelIdc.
Pure Python, Windows OK. Tested on the box with a synthetic header only.
"""
import struct, sys
TYPES = {0x1B: "AVC (H.264)", 0x02: "M2V (MPEG-2)", 0xDC: "ATRAC3plus", 0x80: "LPCM", 0x81: "AC3", 0xDD: "user data"}
for p in sys.argv[1:]:
    h = open(p, "rb").read(0x800)
    if h[:4] != b"PAMF":
        print(p, "not PAMF"); continue
    hs, = struct.unpack_from(">I", h, 8)
    s0, e0 = struct.unpack_from(">I", h, 0x58)[0], struct.unpack_from(">I", h, 0x5E)[0]
    n = h[0x87]
    print(f"{p}: version={h[4:8].decode(errors='replace')} data_offset=0x{hs*0x800:X} "
          f"duration={(e0-s0)/90000:.2f}s streams={n}")
    for i in range(n):
        o = 0x88 + i * 0x30
        t, sid, psid = h[o], h[o + 4], h[o + 5]
        extra = f" profile_idc={h[o+0x10]} level_idc={h[o+0x11]}" if t == 0x1B else ""
        print(f"  stream {i}: type=0x{t:02X} {TYPES.get(t,'?')} stream_id=0x{sid:02X} private=0x{psid:02X}{extra}")

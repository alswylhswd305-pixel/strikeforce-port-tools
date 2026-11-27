#!/usr/bin/env python3
"""Tiny SPU instruction decoder (stdlib only, written from the public Cell BE
SPU ISA field layout; no emulator code used). Covers the forms needed to read
short LS dumps from [spu]/[SPU-HALT] log lines. Unknown words print as '?'.

Field layout (bit 0 = MSB of the 32-bit big-endian word):
  RRR : op[0:4]  rt[4:11]  rb[11:18] ra[18:25] rc[25:32]
  RR  : op[0:11] rb[11:18] ra[18:25] rt[25:32]
  RI7 : op[0:11] i7[11:18] ra[18:25] rt[25:32]
  RI10: op[0:8]  i10[8:18] ra[18:25] rt[25:32]
  RI16: op[0:9]  i16[9:25]           rt[25:32]
  RI18: op[0:7]  i18[7:25]           rt[25:32]
"""
import sys

RRR = {0x8: 'selb', 0xB: 'shufb', 0xC: 'mpya', 0xD: 'fnms', 0xE: 'fma', 0xF: 'fms'}
RI18 = {0x21: 'ila', 0x08: 'hbra', 0x09: 'hbrr'}
RI10 = {0x04: 'ori', 0x05: 'orhi', 0x06: 'orbi', 0x0C: 'sfi', 0x0D: 'sfhi',
        0x14: 'andi', 0x15: 'andhi', 0x16: 'andbi', 0x1C: 'ai', 0x1D: 'ahi',
        0x24: 'stqd', 0x34: 'lqd', 0x44: 'xori', 0x45: 'xorhi', 0x46: 'xorbi',
        0x4C: 'cgti', 0x4D: 'cgthi', 0x4E: 'cgtbi', 0x4F: 'hgti',
        0x5C: 'clgti', 0x5D: 'clgthi', 0x5E: 'clgtbi', 0x5F: 'hlgti',
        0x74: 'mpyi', 0x75: 'mpyui', 0x7C: 'ceqi', 0x7D: 'ceqhi', 0x7E: 'ceqbi',
        0x7F: 'heqi'}
RI16 = {0x040: 'brz', 0x041: 'stqa', 0x042: 'brnz', 0x044: 'brhz', 0x046: 'brhnz',
        0x047: 'stqr', 0x060: 'bra', 0x061: 'lqa', 0x062: 'brasl', 0x064: 'br',
        0x065: 'fsmbi', 0x066: 'brsl', 0x067: 'lqr', 0x081: 'il', 0x082: 'ilhu',
        0x083: 'ilh', 0x0C1: 'iohl'}
RR = {0x0C0: 'a', 0x0C8: 'ah', 0x040: 'sf', 0x048: 'sfh', 0x0C1: 'and', 0x041: 'or',
      0x241: 'xor', 0x0C9: 'nand', 0x049: 'nor', 0x2C1: 'andc', 0x2C9: 'orc',
      0x249: 'eqv', 0x3C0: 'ceq', 0x240: 'cgt', 0x2C0: 'clgt', 0x3C8: 'ceqh',
      0x248: 'cgth', 0x05B: 'shl', 0x058: 'rot', 0x059: 'rotm', 0x05A: 'rotma',
      0x1DC: 'rotqby', 0x1DF: 'shlqby', 0x1C4: 'lqx', 0x144: 'stqx', 0x1A8: 'bi',
      0x1A9: 'bisl', 0x128: 'biz', 0x129: 'binz', 0x12A: 'bihz', 0x12B: 'bihnz',
      0x3C4: 'mpy', 0x3CC: 'mpyu', 0x3C5: 'mpyh', 0x3C6: 'mpyhh', 0x2C4: 'fa',
      0x2C5: 'fs', 0x2C6: 'fm', 0x2B4: 'cntb', 0x2A5: 'clz', 0x1B0: 'gb', 0x1B4: 'fsm',
      0x3D8: 'heq', 0x258: 'hgt', 0x2D8: 'hlgt', 0x0C2: 'cg', 0x042: 'bg',
      0x201: 'nop', 0x001: 'lnop', 0x000: 'stop'}
RI7 = {0x07B: 'shli', 0x078: 'roti', 0x079: 'rotmi', 0x07A: 'rotmai',
       0x1FF: 'shlqbyi', 0x1FC: 'rotqbyi', 0x1FD: 'rotqmbyi', 0x1FB: 'shlqbii',
       0x1F8: 'rotqbii', 0x1F4: 'cbd', 0x1F5: 'chd', 0x1F6: 'cwd', 0x1F7: 'cdd'}

HALT_NOTE = {'heqi': 'halt if ra.word0 == imm', 'hgti': 'halt if ra.word0 > imm (signed)',
             'hlgti': 'halt if ra.word0 > imm (unsigned)', 'heq': 'halt if ra == rb',
             'hgt': 'halt if ra > rb (signed)', 'hlgt': 'halt if ra > rb (unsigned)'}


def bits(w, a, b):
    """bits a..b-1, bit 0 = MSB"""
    return (w >> (32 - b)) & ((1 << (b - a)) - 1)


def sx(v, n):
    return v - (1 << n) if v & (1 << (n - 1)) else v


def decode(w, pc=0):
    op4, op7, op8, op9, op11 = bits(w, 0, 4), bits(w, 0, 7), bits(w, 0, 8), bits(w, 0, 9), bits(w, 0, 11)
    if op4 in RRR:
        rt, rb, ra, rc = bits(w, 4, 11), bits(w, 11, 18), bits(w, 18, 25), bits(w, 25, 32)
        return f"{RRR[op4]} r{rt}, r{ra}, r{rb}, r{rc}"
    if op7 in RI18:
        i18, rt = bits(w, 7, 25), bits(w, 25, 32)
        n = RI18[op7]
        if n == 'ila':
            return f"ila r{rt}, 0x{i18:X}"
        return f"{n} (hint) raw=0x{w:08X}"
    if op8 in RI10:
        i10, ra, rt = sx(bits(w, 8, 18), 10), bits(w, 18, 25), bits(w, 25, 32)
        n = RI10[op8]
        if n in ('lqd', 'stqd'):
            return f"{n} r{rt}, {i10 * 16:#x}(r{ra})"
        if n in HALT_NOTE:
            return f"{n} r{ra}, {i10}    ; {HALT_NOTE[n]} (rt field={rt}, unused)"
        return f"{n} r{rt}, r{ra}, {i10}"
    if op9 in RI16:
        i16, rt = sx(bits(w, 9, 25), 16), bits(w, 25, 32)
        n = RI16[op9]
        if n.startswith('br') or n in ('lqr', 'stqr'):
            return f"{n} r{rt}, 0x{(pc + i16 * 4) & 0x3FFFF:05X}"
        if n in ('lqa', 'stqa', 'bra', 'brasl'):
            return f"{n} r{rt}, 0x{(i16 * 4) & 0x3FFFF:05X}"
        return f"{n} r{rt}, {i16 & 0xFFFF:#x}"
    if op11 in RI7:
        i7, ra, rt = sx(bits(w, 11, 18), 7), bits(w, 18, 25), bits(w, 25, 32)
        return f"{RI7[op11]} r{rt}, r{ra}, {i7}"
    if op11 in RR:
        rb, ra, rt = bits(w, 11, 18), bits(w, 18, 25), bits(w, 25, 32)
        n = RR[op11]
        if n in HALT_NOTE:
            return f"{n} r{ra}, r{rb}    ; {HALT_NOTE[n]}"
        return f"{n} r{rt}, r{ra}, r{rb}"
    return f"? 0x{w:08X} (op8=0x{op8:02X} op9=0x{op9:03X} op11=0x{op11:03X})"


def disasm(words, base):
    out = []
    for i, w in enumerate(words):
        pc = base + 4 * i
        out.append(f"0x{pc:05X}: {w:08X}  {decode(w, pc)}")
    return out


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("usage: spu_mini_decode.py BASE_HEX WORD [WORD...]"); sys.exit(1)
    base = int(sys.argv[1], 16)
    for l in disasm([int(x, 16) for x in sys.argv[2:]], base):
        print(l)

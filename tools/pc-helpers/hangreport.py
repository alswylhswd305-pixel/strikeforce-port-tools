# hangreport.py -- DIAGNOSE-ONLY analysis of 1..3 MyGameRecomp minidumps (stdlib + optional numpy).
# Reads dumps read-only, writes one markdown report. Never touches the game.
#   python hangreport.py --map <MyGameRecomp.map> --run <rundir> --cpu <threads_cpu.txt> --out report.md d1.dmp d2.dmp d3.dmp
import sys, os, re, struct, bisect, argparse, collections, mmap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mdread import MD
ap = argparse.ArgumentParser(); ap.add_argument("--map", required=True); ap.add_argument("--run", default="")
ap.add_argument("--cpu", default=""); ap.add_argument("--out", required=True); ap.add_argument("--watch", default="")
ap.add_argument("dumps", nargs="+"); A = ap.parse_args()
VMB_RVA = 0xB370320   # vm_base (main.cpp.obj) -- same in 1522/1545/1620 maps; re-read from the map below
syms = []
for l in open(A.map, errors="replace"):
    m = re.match(r"\s*([0-9a-fA-F]{4}):[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s+(.*)", l)
    if m:
        if m[2] == "vm_base": VMB_RVA = int(m[3], 16) - 0x140000000
        if m[1] == "0001": syms.append((int(m[3], 16) - 0x140000000, m[2], m[4].strip()))
syms.sort(); saddr = [s[0] for s in syms]
def sym(rva):
    i = bisect.bisect_right(saddr, rva) - 1
    if i < 0: return f"rva_{rva:#x}"
    n = syms[i][1]; m = re.match(r"\?(func_[0-9A-F]+)@@", n)
    if m: n = m[1]
    if len(n) > 70: n = n[:30] + "..." + n[-34:]
    return f"{n}+{rva - syms[i][0]:#x}"
def threads(md):
    out = []
    sig, ver, ns, sdir = struct.unpack_from("<IIII", md.m, 0)
    for i in range(ns):
        t, sz, rva = struct.unpack_from("<III", md.m, sdir + 12 * i)
        if t == 3:
            n = struct.unpack_from("<I", md.m, rva)[0]
            for k in range(n):
                e = rva + 4 + 48 * k; tid = struct.unpack_from("<I", md.m, e)[0]
                csz, crva = struct.unpack_from("<II", md.m, e + 40)
                rip = struct.unpack_from("<Q", md.m, crva + 0xF8)[0]; rsp = struct.unpack_from("<Q", md.m, crva + 0x98)[0]
                out.append((tid, rip, rsp))
    return out
def ppu_ctxs(md, path):
    try: import numpy as np
    except ImportError: return []
    res = []; seen = set()
    for K in range(8):   # Memory64 data can start at any byte (3 mod 8 seen): try every alignment
        sz = (os.path.getsize(path) - K) // 8
        a = np.memmap(path, dtype="<u8", mode="r", offset=K, shape=(sz,)); n = len(a); CH = 1 << 24
        for s in range(0, n, CH):
            blk = np.asarray(a[s:min(n, s + CH + 300)])
            idx = np.nonzero((blk[:CH] == 0x817e20) | (blk[:CH] == 0x827da4))[0]
            for i in idx:
                b = i - 2
                if b < 0 or b + 0x90 > len(blk): continue
                g = blk[b:b + 0x90]; lr = int(g[0x81])
                if not (0x10000 <= lr < 0x900000) or (lr & 3): continue
                if not (0xD0000000 <= int(g[1]) < 0xD1000000 or 0x0F000000 <= int(g[1]) < 0x10000000): continue
                key = (int(g[0x86]), lr)
                if key in seen: continue
                seen.add(key)
                res.append(dict(tid=int(g[0x86]), lr=lr, cia=int(g[0x85]), r1=int(g[1]), r3=int(g[3]), r4=int(g[4]), r11=int(g[11]),
                                r29=int(g[29]), r30=int(g[30]), r31=int(g[31])))
    return res
def spu_ctxs(md):
    try: import numpy as np
    except ImportError: return []
    out = []
    for st, ds, off in md.rng:
        if ds < 0x41000: continue
        a = np.frombuffer(md.m, dtype="<u8", count=ds // 8, offset=off)
        va = st + np.arange(len(a), dtype=np.uint64) * 8
        for h in np.nonzero(a == va - np.uint64(0x40000))[0]:
            f = st + int(h) * 8; ctx = f - 0x40800
            pc, status = struct.unpack("<II", md.read(f + 8, 8))
            if pc < 0x40000: out.append((ctx, pc, status))
    return out
cpu = {}
if A.cpu and os.path.exists(A.cpu):
    for l in open(A.cpu):
        for m in re.finditer(r"(\d+):(\d+)", l): cpu.setdefault(int(m[1]), []).append(int(m[2]))
L = []; P = L.append
per = []
for d in A.dumps:
    md = MD(d); base = md.mods["mygamerecomp.exe"][0]; vmb = md.q(base + VMB_RVA)
    def g32(ea): b = md.read(vmb + ea, 4); return struct.unpack(">I", b)[0] if b else None
    def g16(ea): b = md.read(vmb + ea, 2); return struct.unpack(">H", b)[0] if b else None
    th = []
    for tid, rip, rsp in threads(md):
        loc = sym(rip - base) if base <= rip < base + md.mods["mygamerecomp.exe"][1] else next((f"{n}+{rip-b:#x}" for n, (b, s) in md.mods.items() if b <= rip < b + s), hex(rip))
        stack = []
        data = None
        for n in (0x4000, 0x1000, 0x400):
            data = md.read(rsp, n)
            if data: break
        if data:
            for i in range(0, len(data) - 8, 8):
                v = struct.unpack_from("<Q", data, i)[0]
                if base + 0x1000 <= v < base + md.mods["mygamerecomp.exe"][1]:
                    stack.append(sym(v - base))
                if len(stack) >= 16: break
        th.append((tid, loc, stack))
    ppu = ppu_ctxs(md, d); spu = spu_ctxs(md)
    put, get = g32(0x20002000), g32(0x20002004)
    per.append(dict(path=d, vmb=vmb, th=th, ppu=ppu, spu=spu, put=put, get=get, g32=g32, g16=g16, md=md))
# functions in all dumps
sets = []
for p in per:
    s = set()
    for tid, loc, st in p["th"]: s.add(re.sub(r"\+0x[0-9a-f]+$", "", loc)); s.update(re.sub(r"\+0x[0-9a-f]+$", "", x) for x in st[:6])
    for c in p["ppu"]: s.add(f"guest lr {c['lr']:#x}")
    for c in p["spu"]: s.add(f"spu pc {c[1]:#x}")
    sets.append(s)
common = set.intersection(*sets) if sets else set()
hot = sorted(((sum(v) / len(v), t) for t, v in cpu.items()), reverse=True)
spinning = [t for avg, t in hot if avg >= 1500]
log = os.path.join(A.run, "stderr.log") if A.run else ""
cnt = collections.Counter(); last_diag = ""; stall = []; why = []
if log and os.path.exists(log):
    with open(log, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        for pat, key in ((rb"0x80410901", "EAGAIN 0x80410901"), (rb"full, blocking", "LFQueue push full/blocking"), (rb"BUSY", "BUSY"),
                         (rb"sleeping \d+s in WAIT_SIGNAL", "WAIT_SIGNAL sleeping"), (rb"\[putllc-why\]", "putllc-why lines")):
            cnt[key] = len(re.findall(pat, mm))
        for m in re.finditer(rb"\[sfdiag\] t=[^\n]*", mm): last_diag = m.group(0).decode(errors="replace")
        i = mm.rfind(b"[sfdiag] STALL")
        if i >= 0: stall = mm[i:i + 40000].decode(errors="replace").splitlines()[:260]
        why = [m.group(0).decode(errors="replace") for m in re.finditer(rb"\[putllc-why\][^\n]*", mm)][-3:]
unres = os.path.join(A.run, "cwd", "unresolved_nids.txt") if A.run else ""
P("# Hang report (auto, diagnose-only)\n")
P("Dumps: " + ", ".join(os.path.basename(p["path"]) for p in per) + "\n")
p0 = per[0]
cls = "Freeze with threads at 100% CPU (spin/livelock)" if spinning else "Freeze with all threads idle (deadlock / unsignalled wait)"
P("## Failure class\n" + cls + (f" -- hot host threads: {', '.join(map(str, spinning))}" if spinning else "") + "\n")
P("## Evidence\n")
P("### RSX (VERIFIED, read from dumps)")
for p in per: P(f"- {os.path.basename(p['path'])}: put=0x{p['put'] or 0:08X} get=0x{p['get'] or 0:08X} -> " + ("put==get: PPU stopped submitting" if p['put'] == p['get'] else "put!=get: backend did not drain"))
P("\n### Host threads (VERIFIED: CPU ms per sample window; location from dump 1)")
loc0 = {t: (l, s) for t, l, s in p0["th"]}
for avg, t in hot[:8]:
    l, s = loc0.get(t, ("?", []))
    kind = "SPU interpreter" if "spu_step" in l or any("spu_interp" in x for x in s[:4]) else ("SPU lifted" if "spu_" in l or any(x.startswith("spu_") for x in s[:4]) else ("PPU (guest code)" if l.startswith("func_") or "sys_ppu_thread_yield" in l or any(x.startswith("func_") for x in s[:4]) else "host/other"))
    P(f"- tid {t}: avg {avg:.0f} ms CPU; {kind}; rip {l}; stack {' < '.join(s[:6])}")
P("\n### Guest PPU contexts (VERIFIED from dump 1; r11=0x2B = sys_ppu_thread_yield)")
for c in sorted(p0["ppu"], key=lambda c: c["tid"]):
    flag = "  <-- yield loop" if c["r11"] == 0x2B else ""
    if c["tid"] > 0xFFFF: continue
    P(f"- guest tid {c['tid']}: lr=0x{c['lr']:X} cia=0x{c['cia']:X} r3=0x{c['r3']:X} r29=0x{c['r29']:X} r30=0x{c['r30']:X} r31=0x{c['r31']:X} r11=0x{c['r11']:X}{flag}")
P("\n### SPU contexts (VERIFIED from dump 1)")
for ctx, pc, stt in p0["spu"]: P(f"- ctx 0x{ctx:X} pc=0x{pc:05X} status={stt}")
P("\n### Present in all dumps (VERIFIED: candidate loop)")
for x in sorted(common)[:40]: P(f"- {x}")
if A.watch:
    P("\n### Watched guest words (VERIFIED, per dump)")
    for w in A.watch.split(","):
        ea = int(w, 16)
        P(f"- 0x{ea:08X}: " + "  ".join(f"{(p['g32'](ea) or 0):08X}" for p in per))
P("\n### Log counters (VERIFIED from stderr.log)")
for k, v in cnt.items(): P(f"- {k}: {v}")
if last_diag: P(f"- last [sfdiag] status: `{last_diag}`")
for w in why: P(f"- `{w}`")
if os.path.exists(unres or "-"):
    P("\n### Unresolved NIDs called (VERIFIED: fake-OK suspects)")
    for l in open(unres): P("- " + l.strip())
if stall:
    P("\n### [sfdiag] STALL ring (VERIFIED)\n```"); P("\n".join(stall)); P("```")
P("\n## Ranked hypotheses\nAuto report: none ranked. The agent ranks them from the evidence above (VERIFIED / LIKELY / UNKNOWN).\n")
P("## The single next action\nRead the yield-loop PPU context and the STALL ring first.\n")
P("RPCS3 diff: skipped (no RPCS3 call logs available).")
open(A.out, "w", encoding="utf-8").write("\n".join(L)); print("wrote", A.out)

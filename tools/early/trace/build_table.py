"""Step 1 of tracing-plan: numbered code table from RPCS3 caches (read-only) vs ps3recomp."""
import struct, json, gzip, glob, os, re, bisect, csv, collections, hashlib
import sys
T = os.environ.get("SF_ROOT", os.getcwd())          # work folder (port/spu/inventory.json, out/)
# RPCS3 per-game cache folder, e.g. <rpcs3>/cache/BLUS30471/ppu-<hash>-EBOOT.BIN (read only)
CACHE = os.environ.get("SF_RPCS3_CACHE") or sys.exit("set SF_RPCS3_CACHE to your RPCS3 cache/BLUS30471/ppu-...-EBOOT.BIN folder")
OUT = os.path.join(T, "trace"); os.makedirs(OUT, exist_ok=True)
inv = json.load(open(os.path.join(T, r"port\spu\inventory.json")))
elf_path = inv["inputs"][0]["path"]; elf = open(elf_path, "rb").read()

def ls_image(off):
    ls = bytearray(256 * 1024); b = elf[off:]
    phoff, = struct.unpack(">I", b[0x1C:0x20]); phnum, = struct.unpack(">H", b[0x2C:0x2E])
    for i in range(phnum):
        t, o, va, pa, fs, ms = struct.unpack(">6I", b[phoff + 32 * i: phoff + 32 * i + 24])
        if t == 1 and va + fs <= len(ls): ls[va:va + fs] = b[o:o + fs]
    return bytes(ls)

imgs = []
for p in inv["programs"]:
    off = p["occurrences"][0]["offset"]
    funcs = sorted(f[0] for f in p.get("diagnostics", {}).get("functions", []))
    imgs.append(dict(id=p["image_id"], sha=p["sha256"][:12], status=p["status"], ls=ls_image(off), funcs=set(funcs),
                     ranges=p.get("executable_ranges", [])))

# ---- SPU cache
d = open(os.path.join(CACHE, "spu-safe-v1-tane.dat"), "rb").read(); o = 0; spu = []
while o + 8 <= len(d):
    sz, addr = struct.unpack(">II", d[o:o + 8]); n = sz & 0xFFFF
    if not n or o + 8 + n * 4 > len(d): break
    spu.append((addr, d[o + 8:o + 8 + n * 4])); o += 8 + n * 4

rows = []; spu_stats = collections.Counter(); per_img = collections.Counter()
for addr, code in spu:
    words = [code[i:i + 4] for i in range(0, len(code), 4)]
    nz = [(i, w) for i, w in enumerate(words) if w != b"\0\0\0\0"]
    best = None
    for im in imgs:
        seg = im["ls"][addr:addr + len(code)]
        m = sum(1 for i, w in nz if seg[4 * i:4 * i + 4] == w)
        fr = m / max(1, len(nz))
        if best is None or fr > best[0]: best = (fr, im)
    fr, im = best
    if fr >= 0.98:
        st = ("in_unsupported_image" if im["status"] != "registered" else
              ("lifted_fn_entry" if addr in im["funcs"] else "inside_lifted_image"))
        mod = f"SPU image {im['id']}"; iid = im["id"]; sha = im["sha"]
    else:
        st = "no_eboot_image_match(firmware/data SPU code?)"; mod = "SPU other"; iid = ""; sha = ""
    spu_stats[st] += 1; per_img[mod] += 1
    rows.append(["SPU", mod, iid, sha, f"0x{addr:05X}", f"0x{addr + len(code):05X}", len(words), f"{fr:.3f}", st])

# ---- PPU: RPCS3 labels vs ps3recomp lift
hdr = open(os.path.join(T, r"port\recompiled\ppu_recomp.h"), encoding="utf-8", errors="ignore").read()
lifted = sorted({int(x, 16) for x in re.findall(r"void func_([0-9A-F]{8})\(", hdr)})
opd = json.load(open(os.path.join(T, r"out\EBOOT.functions.json")))
labels = set()
for f in glob.glob(os.path.join(CACHE, "*.obj.gz")):
    for m in re.finditer(rb"__0x([0-9a-f]{1,8})\x00", gzip.open(f).read()): labels.add(int(m.group(1), 16))
lift_set = set(lifted); lo, hi = lifted[0], lifted[-1]
ppu_stats = collections.Counter()
for a in sorted(labels):
    if a in lift_set: st = "lifted_fn_entry"
    elif lo <= a <= hi + 0x10000: st = "inside_lifted_fn(block or merged entry)"
    else: st = "outside_lift_range"
    ppu_stats[st] += 1
    rows.append(["PPU", "EBOOT", "", "", f"0x{a:08X}", "", "", "", st])
not_seen = len(lift_set - labels)

with open(os.path.join(OUT, "code_table.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["id", "kind", "module", "image_id", "image_sha", "addr", "end", "words", "match", "status"])
    for i, r in enumerate(rows, 1): w.writerow([i] + r)
summ = dict(spu_cache_programs=len(spu), spu_status=spu_stats, spu_by_module=per_img.most_common(),
            eboot_spu_images=len(imgs), eboot_images_seen_in_cache=sum(1 for im in imgs if per_img[f"SPU image {im['id']}"]),
            images_never_seen=[im["id"] for im in imgs if not per_img[f"SPU image {im['id']}"]],
            unsupported_image=[(im["id"], per_img[f"SPU image {im['id']}"]) for im in imgs if im["status"] != "registered"],
            rpcs3_ppu_labels=len(labels), ppu_status=ppu_stats, ps3recomp_lifted_functions=len(lifted),
            lifted_entries_not_labelled_by_rpcs3=not_seen, opd_functions=len(opd),
            outside_samples=[hex(a) for a in sorted(labels) if not (lo <= a <= hi + 0x10000)][:20])
json.dump(summ, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=dict)
print(json.dumps(summ, indent=1, default=dict))

#!/usr/bin/env python3
"""auto_convert_loop.py -- capture misses while the port runs, lift them, rebuild, repeat.

SKELETON, UNTESTED. Written on 2026-11-26 against ps3recomp master
e85647a33ce5f9391788f0e3f52ab395a7fe6a89. It has never been run against
Strikeforce or any other title. Read every TODO before the first real run.

Every env var set below exists in that commit (file:line in
sf-shared/auto-convert-loop-researcher.md, section 2). Any name that does NOT
exist there is marked "port-local".

Loop:
    run (watchdog) -> parse logs -> lift new SPU dumps -> report -> rebuild -> rerun
Stops when no run in a row of N runs finds anything new (--stable N), or after
--max-iter iterations.

What it fixes on its own:  SPU images/jobs that were dumped (lift + register).
What it only REPORTS:      unresolved NIDs (someone has to write the HLE), PPU
                           indirect-call targets (seeds for an opt-in re-lift),
                           RSX drops/fallback shaders, null calls, hangs, crashes,
                           and frames that look different from RPCS3.

Usage (Windows, from the port root):
    py auto_convert_loop.py --ps3recomp C:/src/ps3recomp --exe build/strikeforce.exe \
        --exe-args "vfs/PS3_GAME/USRDIR/EBOOT.BIN" \
        --build "cmake --build build -j 8" \
        --pad-script "20:0x0008,35:0x4000,50:0x4000" --timeout 600 --stall 90 \
        --rpcs3-ref refs/  --stable 2
"""
import argparse, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

# ---------------------------------------------------------------- log patterns
# Each regex matches a line printed by e85647a (source location in the doc).
RX = {
    # runtime/spu/spu_workload.c L364-385, message at L379 (once per fingerprint)
    "spu_drop": re.compile(r"\[spu_workload\] ERROR: (.+?) dispatch of an SPU program with no lifted image "
                           r"\(fp=0x([0-9A-Fa-f]{16}) size=(\d+) owner=0x([0-9A-Fa-f]{8})\)"),
    # libs/spurs/cellSpurs.c L2057
    "spu_pm_unlifted": re.compile(r"wid=(\d+) PM NOT LIFTED \(fp=0x([0-9A-Fa-f]{16}) size=(\d+)\)"),
    # runtime/spu/spu_channels.c L2931 -- a lifted image jumped to an address with no lifted function
    "spu_unlifted_pc": re.compile(r"\[spu\] img=(-?\d+) branched into unlifted LS 0x([0-9A-Fa-f]{5})"),
    # runtime/ppu/ppu_hle.cpp L233 (first call of each unregistered NID)
    "nid": re.compile(r"\[hle\] UNRESOLVED NID 0x([0-9A-Fa-f]{8})"),
    # runtime/ppu/ppu_loader.cpp L3176
    "ppu_icall": re.compile(r"\[ppu\] unresolved indirect call -> 0x([0-9A-Fa-f]{8}) \(tid=(\d+) lr=0x([0-9A-Fa-f]{8})\)"),
    # runtime/ppu/ppu_loader.cpp L3152 (then exit(3))
    "ppu_stuck": re.compile(r"\[ppu\] FATAL: stuck calling 0x([0-9A-Fa-f]{8})"),
    # runtime/ppu/ppu_loader.cpp L2952
    "null_call": re.compile(r"\[null-call\] guest called a NULL function pointer \(near lr=0x([0-9A-Fa-f]{8}), tid=(\d+)\)"),
    # libs/video/rsx_d3d12_backend.c L4579 (D3D12_DROP_STATS_EVERY)
    "d3d12": re.compile(r"\[D3D12 drops\] (.*)"),
    # libs/video/rsx_d3d12_backend.c L2762 (printf to stdout, not flushed: may be lost on a crash)
    "pso_fail": re.compile(r"\[FP\] PSO FAIL \(fp=0x([0-9A-Fa-f]{8})"),
}
KV = re.compile(r"(\w+)=(0x[0-9A-Fa-f]+|\d+)")


def fnv1a64(b):  # identical to tools/build_spu_workloads.py fnv1a64 (L57-61)
    h = 1469598103934665603
    for x in b:
        h = ((h ^ x) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


# ---------------------------------------------------------------- one run
def run_once(a, it_dir):
    it_dir.mkdir(parents=True, exist_ok=True)
    shots = it_dir / "frames"; shots.mkdir(exist_ok=True)
    miss = Path(a.miss_dir); miss.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({
        "SPU_DUMP_MISS": str(miss),                  # cellSpurs.c L2062, spu_workload.c L1085/L1623
        "PS3_MILESTONE_OUT": str(it_dir / "milestones.txt"),  # runtime/milestone.c L104
        "D3D12_DROP_STATS_EVERY": "60",              # rsx_d3d12_backend.c L4574
        "CELLMARK_DUMP": str(a.frames),              # rsx_d3d12_backend.c L7960 (BMP dumps)
        "CELLMARK_DUMP_DIR": str(shots),             # L1495
        "CELLMARK_DUMP_EVERY": str(a.frame_every),   # L5828
        "CELLMARK_DUMP_MINDRAWS": "5",               # L5807
        "BCTRL_RING": str(it_dir / "bctrl.txt"),     # ppu_loader.cpp L2676 (ring printed on stuck/watchdog)
        "PS3_VERBOSE": "0",                          # regress.py sets the same for timing reasons
    })
    if a.pad_script:
        env["PAD_SCRIPT"] = a.pad_script             # libs/input/cellPad.c L1021
    if a.pad_file:
        env["PAD_FILE"] = a.pad_file                 # cellPad.c L1073 (closed loop; drive it from --pad-driver)
    if a.extra_env:
        for kv in a.extra_env:
            k, _, v = kv.partition("="); env[k] = v
    log_path = it_dir / "run.log"
    t0 = time.time(); status = "timeout"; rc = None
    with open(log_path, "wb") as log:
        p = subprocess.Popen([a.exe] + a.exe_args.split(), cwd=a.port_dir, env=env,
                             stdout=log, stderr=subprocess.STDOUT)
        last_size, last_change = -1, time.time()
        while True:
            rc = p.poll()
            if rc is not None:
                status = "exit0" if rc == 0 else "crash"; break
            if time.time() - t0 > a.timeout:
                status = "timeout"; break
            # Hang = neither the log nor the milestone file grew for --stall seconds.
            # ASSUMED heuristic: a title idling legitimately on a static screen also
            # stops logging; milestone counts are re-appended every ~2 s, so this
            # only fires if the counts block stops too (runtime/milestone.c header).
            sz = log_path.stat().st_size + _size(it_dir / "milestones.txt")
            if sz != last_size:
                last_size, last_change = sz, time.time()
            elif time.time() - last_change > a.stall:
                status = "hang"; break
            time.sleep(2)
        if p.poll() is None:
            p.kill(); p.wait()
    return {"status": status, "rc": rc, "seconds": round(time.time() - t0, 1),
            "log": str(log_path), "frames": str(shots)}


def _size(p):
    try: return p.stat().st_size
    except OSError: return 0


# ---------------------------------------------------------------- parsing
def parse(run):
    text = Path(run["log"]).read_text(errors="replace")
    f = {"spu_fp": {}, "spu_unlifted_pc": set(), "nids": set(), "ppu_icall": set(),
         "ppu_stuck": set(), "null_call": set(), "pso_fail": set(), "d3d12_last": None}
    for line in text.splitlines():
        if m := RX["spu_drop"].search(line):   f["spu_fp"][m[2].upper()] = int(m[3])
        elif m := RX["spu_pm_unlifted"].search(line): f["spu_fp"][m[2].upper()] = int(m[3])
        elif m := RX["spu_unlifted_pc"].search(line): f["spu_unlifted_pc"].add(f"{m[1]}:0x{m[2].upper()}")
        elif m := RX["nid"].search(line):      f["nids"].add("0x" + m[1].upper())
        elif m := RX["ppu_icall"].search(line): f["ppu_icall"].add("0x" + m[1].upper())
        elif m := RX["ppu_stuck"].search(line): f["ppu_stuck"].add("0x" + m[1].upper())
        elif m := RX["null_call"].search(line): f["null_call"].add("lr=0x" + m[1].upper())
        elif m := RX["pso_fail"].search(line):  f["pso_fail"].add("0x" + m[1].upper())
        elif m := RX["d3d12"].search(line):     f["d3d12_last"] = dict(KV.findall(m[1]))
    # Unresolved-NID hit counts: the milestone log keeps hle:unresolved:<nid> with a
    # BUCKETED count ("10-99"), not an exact one (runtime/milestone.c L248-252).
    f["nid_buckets"] = {}
    ms = Path(run["log"]).with_name("milestones.txt")
    if ms.exists():
        for line in ms.read_text(errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0] == "count" and parts[1].startswith("hle:unresolved:"):
                f["nid_buckets"][parts[1].split(":")[2].upper().replace("0X", "0x")] = parts[2]  # last block wins
        f["last_milestone"] = next((l.split("\t", 1)[1] for l in reversed(ms.read_text(errors="replace").splitlines())
                                    if l[:1].isdigit()), None)
    f["tail"] = text.splitlines()[-25:]
    return f


# ---------------------------------------------------------------- lifting
def lift_new_spu(a, state):
    """Lift every dumped spujob_<fp>_<size>.bin not lifted before.
    ELF dumps -> build_spu_workloads.py --images (registers by the same FNV, L16-23).
    Raw job blobs -> find_spu_functions --raw + spu_lifter, registered like
    tornado tools/relift.sh L43-74. Raw base 0 is ASSUMED (GT5 needed 0xA00 for one blob)."""
    tools = Path(a.ps3recomp) / "tools"; py = sys.executable
    out = {"lifted": [], "failed": []}
    elf_dir = Path(a.spu_elf_dir); elf_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(a.spu_raw_out); raw_dir.mkdir(parents=True, exist_ok=True)
    new_elf = False
    for blob in sorted(Path(a.miss_dir).glob("spujob_*.bin")):
        m = re.fullmatch(r"spujob_([0-9A-Fa-f]{16})_(\d+)\.bin", blob.name)
        if not m or m[1].upper() in state["lifted_fp"]:
            continue
        b = blob.read_bytes()
        if len(b) != int(m[2]) or fnv1a64(b) != int(m[1], 16):
            out["failed"].append({"fp": m[1], "why": "size/fingerprint mismatch"}); continue
        if b[:4] == b"\x7fELF":
            shutil.copyfile(blob, elf_dir / f"dump_{m[1].lower()}.elf"); new_elf = True
            out["lifted"].append({"fp": m[1], "kind": "elf"})
            state["lifted_fp"].append(m[1].upper()); continue
        pre = f"sfjob_{m[1].lower()}_"; d = raw_dir / pre.rstrip("_"); d.mkdir(exist_ok=True)
        funcs = d / "functions.json"; rep = d / "generation.json"
        base = a.raw_base.get(m[1].upper(), "0")
        r1 = subprocess.run([py, str(tools / "find_spu_functions.py"), str(blob), "--raw", "--base", base,
                             "--out", str(funcs)], capture_output=True, text=True)
        r2 = r1.returncode == 0 and subprocess.run(
            [py, str(tools / "spu_lifter.py"), str(blob), "--base", base, "--functions", str(funcs),
             "--symbol-prefix", pre, "-o", str(d), "--report", str(rep)], capture_output=True, text=True)
        if not r2 or r2.returncode != 0:
            out["failed"].append({"fp": m[1], "why": (r1.stderr or getattr(r2, "stderr", ""))[-400:]}); continue
        unsup = json.loads(rep.read_text()).get("unsupported", []) if rep.exists() else []
        out["lifted"].append({"fp": m[1], "kind": "raw", "base": base, "unsupported": len(unsup)})
        state["lifted_fp"].append(m[1].upper()); state["raw_jobs"].append({"fp": m[1].upper(), "prefix": pre})
    if new_elf:
        r = subprocess.run([py, str(tools / "build_spu_workloads.py"), "--images", str(elf_dir),
                            "--lifted", str(Path(a.spu_elf_out)), "--out", str(Path(a.spu_elf_out) / "spu_dumped_workloads.c"),
                            "--register-fn", "sf_dumped_spu_register_all", "--constructor", "--title", "strikeforce"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            out["failed"].append({"fp": "build_spu_workloads", "why": r.stderr[-400:]})
    write_raw_registration(a, state)
    return out


def write_raw_registration(a, state):
    """Registration TU for raw jobs, same shape as tornado tools/relift.sh L43-74.
    TODO: image ids must not collide with the port's existing registrations; set --first-image-id."""
    L = ['/* GENERATED by auto_convert_loop.py */', '#include "spu_workload.h"',
         'extern void spu_begin_image(int image_id);']
    reg = []
    for i, j in enumerate(state["raw_jobs"]):
        p = j["prefix"]; img = a.first_image_id + i
        L.append(f"extern void {p}spu_func_00000000(spu_context*); extern void {p}spu_recomp_register(void);")
        reg.append(f"    spu_begin_image({img}); {p}spu_recomp_register();\n"
                   f"    spu_workload_register_img(0x{j['fp']}ULL, {p}spu_func_00000000, {img}, \"{p.rstrip('_')}\");")
    L += ["__attribute__((constructor)) static void sf_dumped_jobs_register(void)", "{"] + reg + ["    spu_begin_image(0);", "}"]
    Path(a.spu_raw_out, "spu_dumped_jobs.c").write_text("\n".join(L) + "\n")


def name_nids(a, nids):
    """NID -> name via tools/nid_database.py --lookup (exists at e85647a, L639)."""
    names = {}
    for n in sorted(nids):
        r = subprocess.run([sys.executable, str(Path(a.ps3recomp) / "tools" / "nid_database.py"), "--lookup", n],
                           capture_output=True, text=True)
        names[n] = (r.stdout.strip().splitlines() or ["?"])[0][:120]
    return names


# ---------------------------------------------------------------- frame diff
def frame_check(a, run):
    """Compare dumped frames with RPCS3 reference screenshots.
    ASSUMED method: timing differs between the port and RPCS3, so for each reference
    take the BEST-matching port frame (min distance). Distance = mean abs diff of
    64x36 greyscale thumbnails (0-255). Also flag flat frames (few unique colours),
    the check tools/regress.py report_shots uses (L186-215). Thresholds need tuning."""
    try:
        from PIL import Image
    except ImportError:
        return {"skipped": "pip install pillow"}
    frames = sorted(Path(run["frames"]).glob("*.bmp"))
    res = {"frames": len(frames), "flat": 0, "refs": {}}
    def thumb(p):
        return list(Image.open(p).convert("L").resize((64, 36)).getdata())
    th = []
    for f in frames:
        im = Image.open(f).convert("RGB")
        if len(set(im.resize((160, 90)).getdata())) < a.flat_colours:
            res["flat"] += 1
        th.append((f.name, thumb(f)))
    if a.rpcs3_ref and th:
        for ref in sorted(Path(a.rpcs3_ref).glob("*.png")):
            r = thumb(ref)
            best = min(th, key=lambda t: sum(abs(x - y) for x, y in zip(t[1], r)))
            d = sum(abs(x - y) for x, y in zip(best[1], r)) / len(r)
            res["refs"][ref.name] = {"best_frame": best[0], "mad": round(d, 1), "mismatch": d > a.diff_threshold}
    return res


# ---------------------------------------------------------------- main loop
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ps3recomp", required=True); ap.add_argument("--exe", required=True)
    ap.add_argument("--exe-args", default=""); ap.add_argument("--port-dir", default=".")
    ap.add_argument("--build", required=True, help="incremental build command, e.g. cmake --build build -j 8")
    ap.add_argument("--runs-dir", default="autoloop/runs"); ap.add_argument("--miss-dir", default="autoloop/spu_miss")
    ap.add_argument("--spu-elf-dir", default="autoloop/spu_elf_dumps")
    ap.add_argument("--spu-elf-out", default="src/spu_dumped", help="must be in the port's CMake sources (TODO)")
    ap.add_argument("--spu-raw-out", default="src/spu_dumped_jobs", help="must be in the port's CMake sources (TODO)")
    ap.add_argument("--first-image-id", type=int, default=200, help="TODO: pick ids your port does not use")
    ap.add_argument("--raw-base", type=json.loads, default={}, help='JSON {"FP16HEX":"0xA00"} overrides')
    ap.add_argument("--pad-script"); ap.add_argument("--pad-file")
    ap.add_argument("--extra-env", action="append", help="K=V, repeatable (e.g. SPU_INTERP_UNLIFTED=1)")
    ap.add_argument("--timeout", type=float, default=600); ap.add_argument("--stall", type=float, default=90)
    ap.add_argument("--frames", type=int, default=24); ap.add_argument("--frame-every", type=int, default=120)
    ap.add_argument("--rpcs3-ref"); ap.add_argument("--diff-threshold", type=float, default=40.0)
    ap.add_argument("--flat-colours", type=int, default=16)
    ap.add_argument("--stable", type=int, default=2, help="stop after N runs in a row with nothing new")
    ap.add_argument("--max-iter", type=int, default=20)
    a = ap.parse_args()

    root = Path(a.runs_dir); root.mkdir(parents=True, exist_ok=True)
    sp = root / "state.json"
    state = json.loads(sp.read_text()) if sp.exists() else {
        "lifted_fp": [], "raw_jobs": [], "seen": {}, "history": []}
    quiet = 0
    for it in range(1, a.max_iter + 1):
        it_dir = root / f"run_{len(state['history']) + 1:03d}"
        run = run_once(a, it_dir)
        f = parse(run)
        keys = {"spu_fp": set(f["spu_fp"]), "spu_unlifted_pc": f["spu_unlifted_pc"], "nids": f["nids"],
                "ppu_icall": f["ppu_icall"], "null_call": f["null_call"], "pso_fail": f["pso_fail"],
                "ppu_stuck": f["ppu_stuck"]}
        new = {k: sorted(v - set(state["seen"].get(k, []))) for k, v in keys.items()}
        for k, v in keys.items():
            state["seen"][k] = sorted(set(state["seen"].get(k, [])) | v)
        lift = lift_new_spu(a, state)
        # PPU indirect-call targets -> seed file for find_functions.py --seed-json (L849,
        # load_external_seeds keeps only 4-aligned in-exec addresses). Re-lifting the PPU
        # is NOT automatic here: it is slow and a target can be a garbage OPD. TODO opt-in.
        (root / "ppu_seed_candidates.json").write_text(json.dumps(state["seen"].get("ppu_icall", [])))
        frames = frame_check(a, run)
        n_new = sum(len(v) for v in new.values())
        rep = {"run": it_dir.name, "status": run["status"], "seconds": run["seconds"],
               "last_milestone": f.get("last_milestone"),
               "new": new, "new_total": n_new,
               "totals_seen": {k: len(v) for k, v in state["seen"].items()},
               "spu_lifted_this_run": len(lift["lifted"]), "spu_lift_failed": lift["failed"],
               "spu_lifted_total": len(state["lifted_fp"]),
               "spu_still_missing": sorted(set(state["seen"].get("spu_fp", [])) - set(state["lifted_fp"])),
               "nid_buckets": f["nid_buckets"], "nid_names": name_nids(a, new["nids"]),
               "d3d12": f["d3d12_last"], "frames": frames,
               "tail": f["tail"] if run["status"] in ("crash", "hang") else []}
        (it_dir / "report.json").write_text(json.dumps(rep, indent=2))
        state["history"].append({k: rep[k] for k in ("run", "status", "new_total", "spu_lifted_total")})
        sp.write_text(json.dumps(state, indent=2))
        print(f"[{rep['run']}] {run['status']} new={n_new} spu_lifted={len(lift['lifted'])} "
              f"still_missing_spu={len(rep['spu_still_missing'])} nids={len(state['seen'].get('nids', []))}")
        quiet = quiet + 1 if (n_new == 0 and not lift["lifted"]) else 0
        if quiet >= a.stable:
            print(f"stop: {a.stable} run(s) in a row with nothing new"); break
        if lift["lifted"]:
            b = subprocess.run(a.build, shell=True, cwd=a.port_dir)
            if b.returncode != 0:
                print("stop: build failed -- needs a person"); break
    return 0


if __name__ == "__main__":
    sys.exit(main())

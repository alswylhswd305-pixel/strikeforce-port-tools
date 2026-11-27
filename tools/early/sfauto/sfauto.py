#!/usr/bin/env python3
"""sfauto - Strikeforce automated explore -> feedback loop for ps3recomp (v0.1, stdlib only).

  python sfauto.py harvest              RPCS3 cache vs ps3recomp table   (../trace/build_table.py)
  python sfauto.py run  [--secs N] [--env K=V ...]   one run -> runs/<id>/findings.json
  python sfauto.py explore [--rounds 4] [--secs N]   doubling rounds 1,2,4,8 (AFL-style corpus)
  python sfauto.py feedback             corpus -> feedback/ (functions_add.json, overrides_todo.md, ...)
  python sfauto.py ai [--url URL]       optional: ask a local OpenAI-compatible server (LM Studio)
                                        for next knob mutations; skipped if unreachable

Everything stays in the test folder. It never edits RPCS3 or anything outside ROOT.
"""
import argparse, json, os, random, re, subprocess, sys, time, hashlib, itertools, urllib.request

# Paths come from the environment (see scripts/env.example.ps1). Nothing game-specific ships with this tool.
ROOT = os.environ.get("SF_ROOT", os.getcwd())                      # your work folder (port/, vfs/, out/, sfauto/)
EXE = os.environ.get("SF_EXE", os.path.join(ROOT, "port", "bld", "MyGameRecomp.exe"))
ELF = os.environ.get("SF_ELF", "")      # YOUR decrypted EBOOT.elf (made from your own disc; never commit it)
BASE_ENV = {"PS3_VFS_ROOT": os.path.join(ROOT, "vfs", "dev_bdvd"),   # /dev_bdvd/X -> <root>/X (ppu_fs host_path)
            "PS3_HDD0_ROOT": os.path.join(ROOT, "sfauto", "state", "hdd0"),   # writable /dev_hdd0 (game data, saves)
            "PS3_HDD1_ROOT": os.path.join(ROOT, "sfauto", "state", "hdd1"),   # writable /dev_hdd1 (cellSysCache)
            "PS3_DEV_FLASH": os.environ.get("SF_DEV_FLASH", ""),   # dev_flash of YOUR RPCS3 install (official firmware)
            "PS3_HLE_TOP": "0",
            # persistent per-game state (trophies, game data) so installs survive between runs
            "PS3_GAMEDATA_ROOT": os.path.join(ROOT, "sfauto", "state", "gamedata")}
HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(ROOT, "sfauto", "runs"); CORPUS = os.path.join(ROOT, "sfauto", "corpus.json")
FEED = os.path.join(ROOT, "sfauto", "feedback")

# Knob space: (name, values). None = unset. Port knobs come from port/strikeforce_knobs.inc,
# the rest are runtime env vars that already exist in ps3recomp v0.20.0.
KNOBS = {
    "SF_FREE_KB": [None, "1048576", "4194304", "2000000", "41943040"],
    "SF_TROPHY_REQ": [None, "0"],
    "PS3_GAME_FREE_SPACE_RAW": [None, "1"],
    "MSGDIALOG_ANSWER": [None, "yes", "no"],
    "MSGDIALOG_AUTODISMISS_MS": [None, "500"],
    "PS3_HLE_UNRESOLVED": [None, "fail"],
}

LOOP_NOISE = re.compile(r"CreateTask\(|dispatch HIT|built SpursTasksetContext|RETURNED rc=0|sf-lfq\] push#|SEMA-REL|"
                        r"taskset syscall|CLEAR_SURFACE|GetResolution|null-read|null-write")

def parse(out_txt, err_txt):
    txt = out_txt + "\n" + err_txt
    f = {}
    f["hle_funcs"] = sorted({"%s.%s" % m for m in re.findall(r"^\[(cell\w+|sce\w+)\] (\w+)\(", out_txt, re.M)})
    f["unresolved_nids"] = sorted(set(re.findall(r"UNRESOLVED NID (0x[0-9A-F]{8})", txt)))
    f["unresolved_ctx"] = {}
    for m in re.finditer(r"UNRESOLVED NID (0x[0-9A-F]{8}).*\n(?:.*\n){0,2}.*lr =([0-9A-F]+)", txt):
        f["unresolved_ctx"].setdefault(m.group(1), "0x%08X" % (int(m.group(2), 16) & 0xFFFFFFFF))
    f["unlifted_calls"] = sorted(set(re.findall(r"call to unlifted function (0x[0-9A-F]{8})", txt)))
    f["unresolved_icalls"] = sorted(set(re.findall(r"unresolved indirect call -> (0x[0-9A-F]{8})", txt)))
    f["spu_miss"] = sorted(set(re.findall(r"dispatch MISS[^\n]*", txt)))[:50]
    f["null_bctr"] = sorted(set(re.findall(r"bctr to NULL from (func_[0-9A-F]{8}\+0x[0-9A-F]+) r12\(opd\)=(0x[0-9A-F]+)", txt)))[:30]
    f["dialogs"] = sorted(set(re.findall(r"^\[DIALOG\] (.*)$", out_txt, re.M)))
    f["threads"] = sorted(set(re.findall(r'sys_ppu_thread_create tid=\d+ name="([^"]*)"', txt)))
    f["knob_lines"] = sorted(set(re.findall(r"^\[sf-knob\] (.*)$", err_txt, re.M)))[:20]
    f["files"] = sorted(set(re.findall(r"\[cellFs\] Open\(path='([^']+)'", out_txt)))[:400]
    f["flip_requests"] = len(re.findall(r"^\[flip\] \d+ at|^\[flipword\]|SetConvertAndFlip", txt, re.M))
    f["draws_max"] = max([int(x) for x in re.findall(r"draws[=:] ?(\d+)", txt)] or [0])
    f["clears"] = txt.count("CLEAR_SURFACE"); f["sema"] = txt.count("SEMA-REL")
    f["tasks"] = txt.count("CreateTask(")
    f["crash"] = bool(re.search(r"EXCEPTION|access violation|FATAL|abort\(", txt))
    tail = [l for l in out_txt.splitlines() if l.strip() and not LOOP_NOISE.search(l)][-15:]
    f["last_lines"] = tail
    return f

def signature(f):
    b = lambda n: 0 if n == 0 else len(bin(n))          # AFL-style log2 hit buckets
    s = set("hle:" + x for x in f["hle_funcs"]) | set("nid:" + x for x in f["unresolved_nids"])
    s |= set("dlg:" + x[:80] for x in f["dialogs"]) | set("thr:" + x for x in f["threads"])
    s |= set("ul:" + x for x in f["unlifted_calls"] + f["unresolved_icalls"]) | set("file:" + x for x in f["files"]) | set("nb:%s@%s" % t for t in f.get("null_bctr", []))
    s |= {"flip:%d" % b(f["flip_requests"]), "clr:%d" % b(f["clears"]), "crash:%d" % f["crash"]}
    return s

def screenshot(pid, path):
    """Window capture via shot.ps1 (Windows only). Returns the window title (has FPS/draws) or None."""
    if os.name != "nt": return None
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "shot.ps1"),
                            "-ProcId", str(pid), "-Out", path], capture_output=True, text=True, timeout=40)
        out = r.stdout.strip()
        return out[3:] if out.startswith("ok") and os.path.exists(path) else None
    except Exception: return None

def run_once(knobs, secs=60, tag=None):
    if not ELF or not os.path.exists(ELF): sys.exit("[sfauto] set SF_ELF to your own decrypted EBOOT.elf")
    for k in ("PS3_HDD0_ROOT", "PS3_HDD1_ROOT", "PS3_GAMEDATA_ROOT"): os.makedirs(BASE_ENV[k], exist_ok=True)
    rid = tag or time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha1(json.dumps(knobs, sort_keys=True).encode()).hexdigest()[:6]
    rd = os.path.join(RUNS, rid); os.makedirs(os.path.join(rd, "cwd"), exist_ok=True)
    os.makedirs(BASE_ENV["PS3_GAMEDATA_ROOT"], exist_ok=True)
    env = dict(os.environ); env.update(BASE_ENV); env.update({k: v for k, v in knobs.items() if v is not None})
    o = open(os.path.join(rd, "stdout.log"), "w", errors="replace"); e = open(os.path.join(rd, "stderr.log"), "w", errors="replace")
    t0 = time.time(); p = subprocess.Popen([EXE, ELF], cwd=os.path.join(rd, "cwd"), env=env, stdout=o, stderr=e)
    shots = []
    for t in (secs // 2, secs - 3):
        while time.time() - t0 < t and p.poll() is None: time.sleep(0.5)
        if p.poll() is not None: break
        sp = os.path.join(rd, "shot_%02ds.png" % t)
        title = screenshot(p.pid, sp)
        if title is not None: shots.append({"path": sp, "title": title})
    while time.time() - t0 < secs and p.poll() is None: time.sleep(0.5)
    alive = p.poll() is None
    if alive: p.kill(); p.wait()
    o.close(); e.close()
    rd_ = lambda n: open(os.path.join(rd, n), errors="replace").read()
    f = parse(rd_("stdout.log"), rd_("stderr.log"))
    tdraws = [int(m) for sh in shots for m in re.findall(r"draws: (\d+)", sh["title"])]
    f["draws_max"] = max([f.get("draws_max", 0)] + tdraws)
    f.update(run_id=rid, knobs=knobs, secs=secs, alive_at_end=alive, exit_code=None if alive else p.returncode, shots=shots)
    json.dump(f, open(os.path.join(rd, "findings.json"), "w"), indent=1)
    return f

def load_corpus():
    return json.load(open(CORPUS)) if os.path.exists(CORPUS) else {"seen": [], "seeds": [], "runs": []}

def mutate(seed, rng):
    k = dict(seed)
    for name in rng.sample(sorted(KNOBS), rng.choice([1, 1, 2])):
        k[name] = rng.choice([v for v in KNOBS[name] if v != k.get(name)] or KNOBS[name])
    return k

def explore(rounds, secs, seed_rng=1):
    rng = random.Random(seed_rng); c = load_corpus(); seen = set(c["seen"])
    seeds = c["seeds"] or [{}]; tried = {json.dumps(r["knobs"], sort_keys=True) for r in c["runs"]}
    for r in range(rounds):
        n = 2 ** r; batch = []
        while len(batch) < n:
            cand = {} if (r == 0 and not c["runs"]) else mutate(rng.choice(seeds), rng)
            key = json.dumps(cand, sort_keys=True)
            if key in tried and len(tried) < 400: continue
            tried.add(key); batch.append(cand)
        print(f"[sfauto] round {r}: {n} run(s)", flush=True)
        for kn in batch:
            f = run_once(kn, secs); sig = signature(f); new = sorted(sig - seen)
            seen |= sig
            entry = {"run_id": f["run_id"], "knobs": kn, "new": new[:40], "n_new": len(new),
                     "dialogs": f["dialogs"], "flips": f["flip_requests"], "unresolved": f["unresolved_nids"]}
            c["runs"].append(entry)
            if new: seeds.append(kn)
            print(f"[sfauto]   {f['run_id']} knobs={kn} new={len(new)} dialogs={[d[:60] for d in f['dialogs']]} flips={f['flip_requests']}", flush=True)
            c["seen"] = sorted(seen); c["seeds"] = seeds; json.dump(c, open(CORPUS, "w"), indent=1)
    return c

def feedback():
    os.makedirs(FEED, exist_ok=True); allf = []
    for rid in sorted(os.listdir(RUNS)) if os.path.isdir(RUNS) else []:
        p = os.path.join(RUNS, rid, "findings.json")
        if os.path.exists(p): allf.append(json.load(open(p)))
    starts = sorted({a for f in allf for a in f["unlifted_calls"] + f["unresolved_icalls"]})
    nb = sorted({tuple(t) for f in allf for t in f.get("null_bctr", [])})
    # --functions entries: ppu_lifter wants [{start,end}]; end unknown -> lifter's own boundary scan decides (end=0 placeholder)
    json.dump([{"start": a, "end": "0x0", "source": "sfauto-runtime"} for a in starts],
              open(os.path.join(FEED, "functions_add.json"), "w"), indent=1)
    json.dump([], open(os.path.join(FEED, "insn_patches.json"), "w"))   # filled by hand/AI: {addr,orig,new,guard}
    nids = {}
    for f in allf:
        for n in f["unresolved_nids"]: nids.setdefault(n, set()).add(f["unresolved_ctx"].get(n, "?"))
    names = {}
    imp = os.path.join(ROOT, "out", "EBOOT.imports.json")
    if os.path.exists(imp):
        for e in json.load(open(imp)): names["0x%08X" % int(e["nid"], 16)] = e["library"]
    with open(os.path.join(FEED, "overrides_todo.md"), "w") as fh:
        fh.write("# Overrides to write (port/stubs.cpp ctx handlers)\n\n| NID | library | caller LR |\n|---|---|---|\n")
        for n, lrs in sorted(nids.items()): fh.write(f"| {n} | {names.get(n, '?')} | {', '.join(sorted(lrs))} |\n")
        fh.write("\n## Dialogs seen\n" + "\n".join(sorted({"- " + d for f in allf for d in f["dialogs"]})) + "\n")
        fh.write("\n## Indirect calls through NULL (object/vtable never filled)\n" + "\n".join("- %s via opd %s" % t for t in nb) + "\n")
        best = max(allf, key=lambda f: (f["flip_requests"], len(f["hle_funcs"])), default=None)
        if best: fh.write(f"\n## Furthest run\n{best['run_id']} knobs={best['knobs']} flips={best['flip_requests']}\n")
    print(f"[sfauto] feedback: {len(starts)} function starts, {len(nids)} unresolved NIDs -> {FEED}")

def ai(url):
    c = load_corpus(); prompt = ("You tune env knobs for a PS3 static-recompilation boot. Knob space: " + json.dumps(KNOBS) +
        ". Recent runs: " + json.dumps(c["runs"][-12:])[:6000] + ". Reply ONLY with a JSON list of up to 4 knob dicts to try next.")
    body = json.dumps({"model": "local", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}).encode()
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, body, {"Content-Type": "application/json"}), timeout=60)
        txt = json.load(r)["choices"][0]["message"]["content"]; sug = json.loads(re.search(r"\[.*\]", txt, re.S).group(0))
    except Exception as ex:
        print(f"[sfauto] ai: no local model reachable at {url} ({ex.__class__.__name__}); skipped"); return
    c["seeds"] += [s for s in sug if isinstance(s, dict)]; json.dump(c, open(CORPUS, "w"), indent=1)
    print(f"[sfauto] ai: added {len(sug)} seeds")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("harvest"); r = sp.add_parser("run"); r.add_argument("--secs", type=int, default=60); r.add_argument("--env", nargs="*", action="extend", default=[])
    x = sp.add_parser("explore"); x.add_argument("--rounds", type=int, default=4); x.add_argument("--secs", type=int, default=50)
    sp.add_parser("feedback"); a = sp.add_parser("ai"); a.add_argument("--url", default="http://127.0.0.1:1234/v1/chat/completions")
    args = ap.parse_args(); os.makedirs(RUNS, exist_ok=True)
    if args.cmd == "harvest": subprocess.run([sys.executable, os.path.join(HERE, "..", "trace", "build_table.py")])
    elif args.cmd == "run": print(json.dumps(run_once(dict(e.split("=", 1) for e in args.env), args.secs), indent=1)[:4000])
    elif args.cmd == "explore": explore(args.rounds, args.secs); feedback()
    elif args.cmd == "feedback": feedback()
    elif args.cmd == "ai": ai(args.url)

#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Box-side self-tests. No game, no PC launch."""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails = []

def check(name, cond, detail=""):
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name} {detail}")
        fails.append(name)

def test_json():
    for rel in ["data/route_mission1.json", "data/checkpoints.json", "data/godmode_addrs.json", "lib/buttons.json", "data/nid_names.json"]:
        p = ROOT / rel
        json.load(open(p, encoding="utf-8"))
        check(f"json {rel}", True)
    names = json.load(open(ROOT / "data/nid_names.json"))
    check("nid_names size", len(names) >= 1000, len(names))
    ck = json.load(open(ROOT / "data/checkpoints.json"))
    xyz = ck["checkpoints"][0]["xyz"]
    check("partial checkpoint does not invent Y/Z", xyz[1] is None and xyz[2] is None)
    check("godmode unconfirmed", json.load(open(ROOT/"data/godmode_addrs.json"))["status"] == "unconfirmed")
    check("confirmed_hp empty", json.load(open(ROOT/"data/godmode_addrs.json"))["confirmed_hp"] == [])

def test_coverage():
    out = ROOT / "selftest" / "coverage_out.json"
    txt = ROOT / "selftest" / "coverage_out.txt"
    cmd = [sys.executable, str(ROOT/"lib/coverage.py"), str(ROOT/"selftest/sample_stderr.log"),
           "--names", str(ROOT/"data/nid_names.json"), "--out", str(out), "--txt", str(txt)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    check("coverage exit 0", r.returncode == 0, r.stderr)
    d = json.load(open(out, encoding="utf-8"))
    check("hle hook present", d["hle_hook_present"] is True)
    check("two unique nids", d["unique_nids"] == 2, d["unique_nids"])
    # dump counts should win: 5 and 3, not 1+5
    by = {x["nid"]: x["calls"] for x in d["nids"]}
    check("cellAdecQueryAttr calls=5", by.get("0x7E4A4A49") == 5, by)
    check("named cellAdecQueryAttr", any(x.get("name")=="cellAdecQueryAttr" for x in d["nids"]))
    # second run: no new nids
    out2 = ROOT / "selftest" / "coverage_out2.json"
    cmd2 = cmd + ["--prev", str(out), "--out", str(out2)]
    r2 = subprocess.run(cmd2, capture_output=True, text=True)
    d2 = json.load(open(out2, encoding="utf-8"))
    check("new since last is empty", d2["new_since_last_run"]["nids"] == [])
    # previous with only first nid
    prev = {"log": "fake", "nids": [{"nid": "0x7E4A4A49", "name": "", "lrs": {}, "calls": 1}], "guest_functions": []}
    prevp = ROOT / "selftest" / "prev.json"
    json.dump(prev, open(prevp, "w"))
    out3 = ROOT / "selftest" / "coverage_out3.json"
    subprocess.run([sys.executable, str(ROOT/"lib/coverage.py"), str(ROOT/"selftest/sample_stderr.log"),
                    "--names", str(ROOT/"data/nid_names.json"), "--prev", str(prevp), "--out", str(out3)],
                   check=True, capture_output=True)
    d3 = json.load(open(out3))
    check("new nid detected", d3["new_since_last_run"]["nids"] == ["0x847D2380"], d3["new_since_last_run"])

def test_annotate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sf_annotate", ROOT / "lib" / "annotate.py")
    ann = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(ann)
        ann.find_font()
    except FileNotFoundError as e:
        print(f"  SKIP annotate (no font): {e}")
        return
    except Exception as e:
        # Missing arabic_reshaper / python-bidi etc.
        print(f"  SKIP annotate (dependency missing): {e}")
        return
    from PIL import Image
    src = ROOT / "selftest" / "blank.png"
    Image.new("RGB", (1280, 720), (30, 60, 90)).save(src)
    dst = ROOT / "selftest" / "blank_annotated.png"
    js = ROOT / "selftest" / "blank_annotations.json"
    if js.exists(): js.unlink()
    py = sys.executable
    r = subprocess.run([py, str(ROOT/"lib/annotate.py"),
                        "--src", str(src), "--dst", str(dst), "--json", str(js),
                        "--box", "100,80,500,400",
                        "--label", "اختبار المختبر: صورة مو سوداء",
                        "--label", "المربع الأحمر يعلّم المنطقة"],
                       capture_output=True, text=True)
    check("annotate exit 0", r.returncode == 0, r.stderr)
    check("annotated png exists", dst.is_file() and dst.stat().st_size > 1000)
    rec = json.load(open(js, encoding="utf-8"))
    check("annotations json written", isinstance(rec, list) and rec[0]["labels_ar"][0].startswith("اختبار"))
    # not a flat black image
    im = Image.open(dst)
    extrema = im.convert("L").getextrema()
    check("annotated image not flat black", extrema[1] > 10, extrema)

def test_padseq_parse():
    # Import the shared python selftest logic inline
    sys.path.insert(0, str(ROOT))
    from collections import namedtuple
    # local parse
    def parse(path):
        cmds=[]
        for i, raw in enumerate(open(path, encoding="utf-8"), 1):
            line=raw.strip()
            if not line or line.startswith("#"): continue
            cmds.append((i, line.split()[0], line))
        return cmds
    for rel in ["sequences/boot_to_start.padseq", "sequences/menu_cross.padseq", "sequences/combat_step.padseq"]:
        cmds = parse(ROOT/rel)
        check(f"seq {rel} has commands", len(cmds) > 0)
    boot = parse(ROOT/"sequences/boot_to_start.padseq")
    kinds = [c[1] for c in boot]
    check("boot starts with wait_movie_end", "wait_movie_end" in kinds)
    check("boot does not press before wait", kinds.index("wait_movie_end") < kinds.index("press"))

def main():
    print("sf-autotester selftest")
    test_json()
    test_coverage()
    test_annotate()
    test_padseq_parse()
    # shared replay parser / guard tests
    replay = ROOT.parent / "tools" / "replay" / "selftest_padseq.py"
    r = subprocess.run([sys.executable, str(replay)], capture_output=True, text=True)
    print(r.stdout)
    check("replay selftest_padseq.py", r.returncode == 0, r.stderr)
    print("fails:", len(fails))
    if fails:
        print(fails)
        return 1
    Path(ROOT/"selftest/TEST_DONE.txt").write_text("ok\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

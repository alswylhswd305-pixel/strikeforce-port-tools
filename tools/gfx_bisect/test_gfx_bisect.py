#!/usr/bin/env python3
"""Unit tests for gfx_bisect / img_compare. No game launch, no Windows needed."""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gfx_bisect as gb
import img_compare as ic
from PIL import Image


SHOTS = Path("/workspace/sf-shots")
TEST_OUT = HERE / "test_out"


class TestBisection(unittest.TestCase):
    def test_split_halves(self):
        self.assertEqual(gb.split_halves(0, 15), [(0, 7), (8, 15)])
        self.assertEqual(gb.split_halves(8, 11), [(8, 9), (10, 11)])
        self.assertEqual(gb.split_halves(11, 11), [(11, 11)])
        self.assertEqual(gb.split_k(0, 15, 4), [(0, 3), (4, 7), (8, 11), (12, 15)])
        self.assertEqual(math.ceil(math.log2(843)), 10)

    def test_auto_finds_draw_no_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            gb._write_good_ref(ref)
            cfg = gb._auto_cfg(tmp, bad=11, n=16, ref_good=ref)
            runner = gb.FakeRunner(bad=11, n=16)
            result = gb.run_auto(cfg, runner=runner, ask=None)
            self.assertEqual(result["culprit"], 11)
            self.assertTrue(result["report"] and os.path.exists(result["report"]))
            md = Path(result["report"]).read_text(encoding="utf-8")
            self.assertIn("0x0A30", md)
            self.assertIn("0x0A20", md)
            self.assertIn("c15", md)
            # Never required a y/n callback.
            ranges = [c["env"].get("DRAW_RANGE") for c in runner.calls if "DRAW_RANGE" in c["env"]]
            self.assertTrue(ranges)
            self.assertLessEqual(len(ranges), 6)  # baseline + ceil(log2 16)

    def test_resume_and_parallel(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            gb._write_good_ref(ref)
            t2 = os.path.join(tmp, "r2")
            cfg = gb._auto_cfg(t2, bad=11, n=16, ref_good=ref, baseline=False)
            sess = gb.Session(cfg["out_dir"], 0, 15, cfg["state_file"])
            os.makedirs(cfg["out_dir"], exist_ok=True)
            gb.run_step(gb.FakeRunner(bad=11, n=16), cfg, sess, 0, 7, 0)
            sess = gb.Session.load(cfg["state_file"])
            sess.lo = 8
            sess.save()
            cfg["resume"] = True
            result = gb.run_auto(cfg, runner=gb.FakeRunner(bad=11, n=16), ask=None)
            self.assertEqual(result["culprit"], 11)

            t3 = os.path.join(tmp, "r3")
            cfg3 = gb._auto_cfg(t3, bad=11, n=16, ref_good=ref, parallel=2)
            result3 = gb.run_auto(cfg3, runner=gb.FakeRunner(bad=11, n=16), ask=None)
            self.assertEqual(result3["culprit"], 11)

    def test_cli_auto_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            gb._write_good_ref(ref)
            cfg = gb._auto_cfg(tmp, bad=5, n=8, ref_good=ref)
            cfg_path = os.path.join(tmp, "cfg.json")
            Path(cfg_path).write_text(json.dumps(cfg), encoding="utf-8")
            # Inject FakeRunner via a tiny monkeypatch of GameRunner used by main? 
            # run_auto is already tested; here we only check argv routing.
            self.assertEqual(gb._argv(["--config", cfg_path])[0], "auto")
            self.assertEqual(gb._argv(["auto", "--config", cfg_path])[0], "auto")


class TestReport(unittest.TestCase):
    def test_parse_and_mismatch(self):
        port = gb.parse_drawdump(gb._sample_drawdump(11), want=11)
        self.assertIsNotNone(port)
        self.assertEqual(port["draw"], 11)
        self.assertEqual(port["viewport_scale"][0], 640)
        self.assertEqual(port["attribs"][1]["type_name"], "UB256")
        self.assertEqual(port["c0_c15"][15][0], 12.5)
        rpc = {
            "viewport_scale": [640, 360, 0.5, 1],
            "viewport_offset": [640, 360, 0.5, 0],
            "clip_range": [0, 1],
            "fp": "0x00EC2B80",
            "rt": {"color0": "0x0B530000", "zeta": "0x0", "format": "0x08", "w": 1280, "h": 720},
            "attribs": [
                {"index": 0, "enabled": 1, "offset": "0x1000", "stride": 16, "size": 3, "type": 2, "type_name": "F"},
                {"index": 1, "enabled": 1, "offset": "0x100C", "stride": 16, "size": 3, "type": 7, "type_name": "UB256"},
            ],
            "c0_c15": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]] + [[0, 0, 0, 0]] * 11 + [[0, 0, 0, 1]],
        }
        md = gb.build_report(port, rpc, 11, {"steps": 5, "orig_lo": 0, "orig_hi": 15})
        self.assertIn("MISMATCH", md)
        self.assertIn("0x0A30", md)
        self.assertIn("fragment program id", md)

    def test_legacy_scrape(self):
        text = (
            "[VPATTR] --- fp=0xABCDE00 ---\n"
            "[VPATTR] a0 off=0x1000 stride=16 size=3 type=2 freq=0\n"
            "iq01 vp_scale=(640.0,360.0,0.500) vp_off=(640.0,360.0,0.500)\n"
        )
        d = gb.parse_drawdump(text)
        self.assertEqual(d["source"], "legacy_scrape")
        self.assertTrue(d["fp"].lower().endswith("abcde00") or "abcde00" in d["fp"].lower())
        self.assertEqual(d["attribs"][0]["stride"], 16)
        self.assertAlmostEqual(d["viewport_scale"][0], 640.0)


class TestImgCompare(unittest.TestCase):
    def test_synthetic_white_ground(self):
        with tempfile.TemporaryDirectory() as tmp:
            ours = Image.new("RGB", (100, 100), (10, 10, 10))
            for y in range(60, 100):
                for x in range(100):
                    ours.putpixel((x, y), (250, 250, 250))
            ref = Image.new("RGB", (100, 100), (80, 90, 40))
            op = os.path.join(tmp, "ours.png")
            rp = os.path.join(tmp, "ref.png")
            ours.save(op); ref.save(rp)
            regions = {"ground": [0.0, 0.6, 1.0, 1.0], "tent": [0.0, 0.0, 1.0, 0.4], "full": [0.0, 0.0, 1.0, 1.0]}
            report = ic.compare(op, rp, os.path.join(tmp, "out"), size=(100, 100), regions=regions)
            self.assertGreater(report["regions"]["ground"]["white_pixel_fraction"], 0.9)
            self.assertLess(report["regions"]["tent"]["white_pixel_fraction"], 0.1)
            self.assertGreater(report["regions"]["ground"]["mae"], 0.3)
            self.assertTrue(os.path.exists(os.path.join(tmp, "out", "heatmap.png")))
            self.assertTrue(ic.artifact_present(report["regions"]["ground"], "white_frac", 0.5, "above"))

    def test_p88_vs_ref_and_stack(self):
        TEST_OUT.mkdir(parents=True, exist_ok=True)
        ours = SHOTS / "p88_restart_150s.jpg"
        ref = SHOTS / "rpcs3" / "ref_instage_start_130501.png"
        stack = SHOTS / "cmp_ref_vs_p88.jpg"
        self.assertTrue(ours.is_file() and ref.is_file())
        out = TEST_OUT / "p88_vs_ref"
        report = ic.compare(str(ours), str(ref), str(out), size=(1280, 720))
        Path(out / "summary.json").write_text(json.dumps({
            k: report[k] for k in report if k in ("global_mae", "psnr_db", "worst_named")
        } | {"tent": report["regions"].get("tent"), "ground": report["regions"].get("ground"),
             "buildings_left": report["regions"].get("buildings_left"),
             "buildings_right": report["regions"].get("buildings_right")}, indent=2), encoding="utf-8")
        self.assertGreater(report["global_mae"], 0.05)
        # White ground should stand out against the RPCS3 dirt path.
        self.assertGreater(report["regions"]["ground"]["white_pixel_fraction"], 0.2)
        self.assertLess(report["regions"]["ground"]["white_pixel_fraction_ref"], 0.15)
        self.assertTrue((out / "heatmap.png").is_file())
        self.assertTrue((out / "side_by_side.png").is_file())

        if stack.is_file():
            out2 = TEST_OUT / "stack_p88"
            out2.mkdir(parents=True, exist_ok=True)
            top, bot = ic.split_stack(str(stack))
            top.save(out2 / "_split_ref.png")
            bot.save(out2 / "_split_ours.png")
            r2 = ic.compare(str(out2 / "_split_ours.png"), str(out2 / "_split_ref.png"),
                            str(out2), size=(960, 540))
            self.assertGreater(r2["global_mae"], 0.05)
            self.assertTrue((out2 / "heatmap.png").is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)

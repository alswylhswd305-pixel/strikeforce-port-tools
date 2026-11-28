#!/usr/bin/env python3
# Copyright (c) 2026 Saud Hamad Alsuwailih
# SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
"""Self-tests for diagnose.py / arabic_draw.py. No game, no Windows needed."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from PIL import Image, ImageDraw

import arabic_draw as ad
import diagnose as dg
import gfx_bisect as gb


def _require_arabic_font():
    try:
        return ad.find_arabic_font()
    except FileNotFoundError as e:
        raise unittest.SkipTest(f"Arabic font not found: {e}")


def _require_cv2():
    if getattr(dg, "cv2", None) is None:
        raise unittest.SkipTest("opencv-python-headless is not installed")


def _solid(w, h, rgb):
    return Image.new("RGB", (w, h), rgb)


def _save(im, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


class TestArabic(unittest.TestCase):
    def setUp(self):
        _require_arabic_font()

    def test_reshapes_and_paints(self):
        im = _solid(400, 80, (255, 255, 255))
        box = ad.draw_label(im, (10, 10), "أسطح داكنة", size=28, bg=(180, 0, 0), fill=(255, 255, 255))
        arr = np.asarray(im)
        # The label box must contain red background pixels.
        region = arr[box[1]:box[3], box[0]:box[2]]
        self.assertGreater(region[..., 0].mean(), 80)
        self.assertTrue((region[..., 0] > region[..., 1]).mean() > 0.5)
        # And must not be a blank white strip (glyphs or background filled it).
        self.assertLess(region.mean(), 250)


class TestAlign(unittest.TestCase):
    def setUp(self):
        _require_cv2()

    def test_recovers_small_shift(self):
        # A textured image, shift by 12 px, ECC/ORB should pull it back.
        rng = np.random.default_rng(0)
        base = (rng.random((180, 240, 3)) * 0.4 + 0.3).astype(np.float32)
        # Add a few high-contrast blobs so ORB has corners.
        for x, y in ((40, 40), (160, 50), (80, 120), (200, 140), (30, 150)):
            base[y:y+18, x:x+18] = (0.9, 0.2, 0.1)
            base[y+6:y+12, x+6:x+12] = (0.1, 0.9, 0.2)
        ref = dg.np_to_pil(base)
        # Shift ours right and down by 12.
        ours_arr = np.zeros_like(base)
        ours_arr[12:, 12:] = base[:-12, :-12]
        ours = dg.np_to_pil(ours_arr)
        aligned, info = dg.align_images(ours, ref, photo=False)
        self.assertNotEqual(info["method"], "need_crash")
        A, B = dg.pil_to_np(aligned), dg.pil_to_np(ref)
        # Centre crop MAE should drop a lot vs the unaligned pair.
        mae_raw = float(np.abs(dg.pil_to_np(ours) - B)[20:160, 20:220].mean())
        mae_al = float(np.abs(A - B)[20:160, 20:220].mean())
        self.assertLess(mae_al, mae_raw * 0.45)
        self.assertLess(mae_al, 0.08)


class TestDetectors(unittest.TestCase):
    def setUp(self):
        _require_cv2()

    def test_shadow_acne_stripes(self):
        rng = np.random.default_rng(1)
        ref = np.clip(rng.random((240, 320, 3)) * 0.15 + 0.4, 0, 1).astype(np.float32)
        ours = ref.copy()
        # High-frequency vertical stripes on the mid band (lit surface).
        x = np.arange(320)
        stripe = (np.sin(x * 1.8) > 0).astype(np.float32) * 0.45
        ours[40:160, :, :] = np.clip(ours[40:160] + stripe[None, :, None], 0, 1)
        f = dg.detect_shadow_acne(ours, ref)
        self.assertGreater(f["compare"], 1.8)
        self.assertEqual(f["verdict_key"], "higher")
        self.assertGreater(dg.scores_from_findings([f])["shadow_acne"], 0.5)

    def test_dark_roofs(self):
        ref = np.full((240, 320, 3), 0.45, np.float32)
        ours = ref.copy()
        ours[20:90, 0:100] = 0.12  # left building darkened
        f = dg.detect_dark_roofs(ours, ref)
        self.assertLess(f["compare"], 0.72)
        self.assertEqual(f["verdict_key"], "lower")

    def test_haze_veil(self):
        # Ref: far (top) is contrast-poor (haze); ours: far stays sharp (missing haze).
        yy, xx = np.mgrid[0:240, 0:320]
        texture = ((np.sin(xx / 3.0) * np.sin(yy / 3.0)) * 0.5 + 0.5).astype(np.float32)
        tex = np.stack([texture, texture * 0.95, texture * 0.8], axis=2)
        ours = tex.copy()
        ref = tex.copy()
        # Fade ref contrast toward the top by blending with a grey veil.
        veil = np.linspace(0.65, 0.0, 240).astype(np.float32)[:, None, None]
        ref = np.clip(ref * (1 - veil) + 0.7 * veil, 0, 1)
        f = dg.detect_haze(ours, ref)
        # ours far contrast should be higher than ref → compare (far_o/far_r) > 1, log > 0
        self.assertGreater(f["compare"], 1.0)
        self.assertIn(f["verdict_key"], ("higher", "similar"))  # threshold may or may not trip
        # The log far-contrast ratio must be clearly positive (missing veil).
        self.assertGreater(f["extra"]["log_far_contrast_ratio"], 0.3)

    def test_white_ground(self):
        ref = np.full((240, 320, 3), 0.35, np.float32)
        ours = ref.copy()
        ours[150:230, :, :] = 0.95
        f = dg.detect_white_ground(ours, ref)
        self.assertGreater(f["ours"], 0.7)
        self.assertLess(f["ref"], 0.1)
        self.assertEqual(f["verdict_key"], "higher")

    def test_faces_black_hole_and_blue(self):
        ref = np.full((240, 320, 3), 0.2, np.float32)
        ours = ref.copy()
        # A skin-tone face in the ref with some eye detail.
        def paint_face(img, x0, y0, hole=False, blue=False):
            img[y0:y0+70, x0:x0+55] = (0.80, 0.62, 0.50)
            # eyes
            if blue:
                img[y0:y0+70, x0:x0+55] = (0.25, 0.45, 0.85)
            if hole:
                # Flat dark eye-band + a dark hole (matches the in-game "black face"
                # / "missing eyes" look). A bright rim in the eye band would
                # inflate variance and hide the measurement.
                img[y0:y0+28, x0:x0+55] = (0.04, 0.04, 0.04)
                img[y0+28:y0+62, x0+6:x0+49] = (0.02, 0.02, 0.02)
            else:
                img[y0+16:y0+24, x0+14:x0+22] = (0.1, 0.08, 0.07)
                img[y0+16:y0+24, x0+32:x0+40] = (0.1, 0.08, 0.07)
                img[y0+18:y0+22, x0+16:x0+20] = (0.9, 0.9, 0.9)
        paint_face(ref, 80, 50, hole=False)
        paint_face(ours, 80, 50, hole=True, blue=True)
        # Force the box so the test is about the metrics, not the blob detector.
        f = dg.detect_faces(ours, ref, face_boxes=[[80, 50, 135, 120]])
        self.assertGreater(f["extra"]["dark_hole_ours"], f["extra"]["dark_hole_ref"] + 0.15)
        self.assertGreater(f["extra"]["blue_minus_red_ours"], f["extra"]["blue_minus_red_ref"] + 0.05)
        self.assertLess(f["extra"]["eye_var_ratio"], 0.7)
        self.assertEqual(f["verdict_key"], "higher")
        scores = f["scores"]
        self.assertGreater(scores["face_dark"], 0.15)
        self.assertGreater(scores["face_blue"], 0.05)


class TestCutscene(unittest.TestCase):
    def setUp(self):
        _require_cv2()

    def test_syncs_shifted_sequences(self):
        with tempfile.TemporaryDirectory() as tmp:
            ours_d = Path(tmp) / "ours"
            ref_d = Path(tmp) / "ref"
            ours_d.mkdir(); ref_d.mkdir()
            # Two shots: red then blue. Ref has 3 extra lead-in frames of green,
            # then the same red/blue shots.
            def frame(color, tick=0):
                im = Image.new("RGB", (160, 90), color)
                d = ImageDraw.Draw(im)
                d.rectangle([10 + tick, 20, 40 + tick, 60], fill=(255, 255, 0))
                return im
            # ours: 6 red (tick 0..5), 6 blue
            for i in range(6):
                frame((180, 40, 40), i).save(ours_d / ("o_%02d.png" % i))
            for i in range(6):
                frame((40, 40, 180), i).save(ours_d / ("o_%02d.png" % (i + 6)))
            # ref: 3 green lead-in, then 6 red, 6 blue
            for i in range(3):
                frame((40, 180, 40), 0).save(ref_d / ("r_%02d.png" % i))
            for i in range(6):
                frame((180, 40, 40), i).save(ref_d / ("r_%02d.png" % (i + 3)))
            for i in range(6):
                frame((40, 40, 180), i).save(ref_d / ("r_%02d.png" % (i + 9)))
            out = Path(tmp) / "out"
            summary = dg.run_cutscene(str(ours_d), str(ref_d), str(out), size=(160, 90))
            self.assertTrue((out / "timeline.csv").is_file())
            self.assertGreaterEqual(summary["n_diagnosed"], 1)
            # First ours frame (red tick 0) should map near ref index 3, not 0 (green).
            rows = list(csv_rows(out / "timeline.csv"))
            self.assertGreaterEqual(int(rows[0]["ref_idx"]), 2)


def csv_rows(path):
    import csv
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TestPairAndBisectHook(unittest.TestCase):
    def setUp(self):
        _require_cv2()

    def test_compare_pair_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = _solid(320, 180, (80, 90, 40))
            ours = _solid(320, 180, (80, 90, 40))
            # White ground in the bottom.
            d = ImageDraw.Draw(ours)
            d.rectangle([0, 110, 319, 179], fill=(250, 250, 250))
            op = _save(ours, Path(tmp) / "ours.png")
            rp = _save(ref, Path(tmp) / "ref.png")
            dest = Path(tmp) / "pair"
            r = dg.compare_pair(str(op), str(rp), str(dest), size=(320, 180), photo="no")
            self.assertTrue(Path(r["paths"]["annotated"]).is_file())
            self.assertTrue(Path(r["paths"]["side_by_side"]).is_file())
            self.assertEqual(
                [f["issue"] for f in r["findings"]],
                ["shadow_acne", "dark_roofs", "haze", "faces", "white_ground"],
            )
            wg = next(f for f in r["findings"] if f["issue"] == "white_ground")
            self.assertEqual(wg["verdict_key"], "higher")
            self.assertGreater(r["scores"]["white_ground"], 0.2)

    def test_bisect_accepts_white_ground_metric(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A "good" ref (green, no white ground) and a FakeRunner that paints
            # a white ground whenever the bad draw is in range.
            ref = _solid(64, 64, (20, 80, 20))
            rp = _save(ref, Path(tmp) / "ref.png")
            cfg = gb._auto_cfg(tmp, bad=5, n=8, ref_good=str(rp), baseline=True)
            cfg["oracle"]["metric"] = "white_ground"
            cfg["oracle"]["threshold"] = 0.2
            cfg["oracle"]["region"] = "ground"
            cfg["compare"] = {"w": 64, "h": 64}
            runner = gb.FakeRunner(bad=5, n=8)
            result = gb.run_auto(cfg, runner=runner, ask=None)
            self.assertEqual(result["culprit"], 5)



class TestArabicRaqm(unittest.TestCase):
    def test_connected_arabic_not_blank(self):
        _require_arabic_font()
        im = _solid(500, 90, (255, 255, 255))
        box = ad.draw_label(im, (12, 16), "حبوب الظل", size=36,
                            bg=(255, 255, 255), fill=(0, 0, 0))
        region = np.asarray(im)[box[1]:box[3], box[0]:box[2]]
        # Ink must be present (not an empty white box).
        self.assertLess(float(region.mean()), 245)
        # And must occupy more than a few pixels.
        ink = (region.mean(axis=2) < 200).mean()
        self.assertGreater(ink, 0.05)
        # Save a fixture so a human can confirm joining.
        out = HERE / "test_out" / "arabic_label.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out)

    def test_raqm_preferred_when_available(self):
        # If this Pillow has RAQM, draw_label must use it (logical string).
        # We only assert the helper reports the same as Pillow.
        from PIL import features as pil_features
        self.assertEqual(bool(ad.has_raqm()), bool(pil_features.check("raqm")))


class TestFaceAlignmentGuard(unittest.TestCase):
    def test_unaligned_does_not_project_ref_box(self):
        ref = np.full((240, 320, 3), 0.2, np.float32)
        ours = np.full((240, 320, 3), 0.2, np.float32)
        # Skin-tone face with eyes only in the REF, at (80,50).
        ref[50:120, 80:135] = (0.80, 0.62, 0.50)
        ref[66:74, 94:102] = (0.1, 0.08, 0.07)
        ref[66:74, 112:120] = (0.1, 0.08, 0.07)
        # Ours has a skin-tone face with a dark hole in a *different* place.
        # The ref-box region on ours stays the background 0.2 — not a face.
        ours[140:210, 200:255] = (0.80, 0.62, 0.50)
        ours[140:168, 200:255] = (0.04, 0.04, 0.04)
        ours[168:202, 206:249] = (0.02, 0.02, 0.02)
        # With alignment_ok, a forced ref box would compare the background to the face.
        f_ok = dg.detect_faces(ours, ref, face_boxes=[[80, 50, 135, 120]], alignment_ok=True)
        # With weak alignment the config/ref box must not be projected: verdict unmatched,
        # bisect score stays 0.
        f_bad = dg.detect_faces(ours, ref, face_boxes=[[80, 50, 135, 120]], alignment_ok=False)
        self.assertEqual(f_bad["verdict_key"], "unmatched")
        self.assertEqual(f_bad["scores"]["faces"], 0.0)
        self.assertEqual(f_bad["scores"]["face_dark"], 0.0)
        self.assertTrue(f_bad["extra"]["unmatched_pose"])
        self.assertFalse(f_bad["extra"]["alignment_ok"])
        # And alignment_reliable rejects resize_only.
        self.assertFalse(dg.alignment_reliable({"method": "resize_only", "ecc": 0.1, "inliers": 3}))
        self.assertFalse(dg.alignment_reliable({"method": "ecc", "ecc": 0.26, "inliers": 6}))
        self.assertTrue(dg.alignment_reliable({"method": "orb_affine+ecc", "ecc": 0.32, "inliers": 200}))


class TestPhotoCrop(unittest.TestCase):
    def setUp(self):
        _require_cv2()

    def test_exif_transpose_and_bright_rect(self):
        # A portrait "room" photo: dark walls, a bright 16:9 "screen" in the middle.
        # Saved with EXIF orientation 6 so the raw pixels are rotated.
        w, h = 1600, 900  # the visual game window, landscape
        screen = Image.new("RGB", (w, h), (40, 40, 40))
        d = ImageDraw.Draw(screen)
        # Bright "game" content with some structure so std is not ~0.
        # Whole window brighter than the room so a bright-threshold crop
        # finds the window, not only the ground (which would be too wide).
        screen.paste(Image.new("RGB", (w, h), (170, 160, 140)))
        d = ImageDraw.Draw(screen)
        d.rectangle([0, 400, 1599, 899], fill=(240, 236, 230))
        d.rectangle([80, 60, 500, 280], fill=(155, 140, 100))
        d.rectangle([1000, 80, 1500, 360], fill=(150, 160, 130))
        d.rectangle([700, 200, 860, 700], fill=(140, 145, 165))
        # Place that screen on a larger portrait "room" (phone photo).
        room = Image.new("RGB", (2000, 2800), (20, 18, 16))
        room.paste(screen, (200, 700))
        tmp = HERE / "test_out" / "fake_tv.jpg"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        # Store as orientation 6: raw pixels are 90° CCW of the visual, so that
        # ImageOps.exif_transpose (90° CW) restores `room`.
        rotated = room.transpose(Image.ROTATE_90)
        exif = rotated.getexif()
        exif[274] = 6
        rotated.save(tmp, "JPEG", quality=90, exif=exif)
        loaded = dg.load_image(str(tmp))
        # Restored visual should be portrait (2000x2800), not the raw 2800x2000.
        self.assertEqual(loaded.size, (2000, 2800))
        cropped, quad, why = dg.crop_screen_quad(loaded, (1280, 720))
        self.assertTrue(why.startswith("screen_quad"), msg=why)
        self.assertIsNotNone(quad)
        self.assertEqual(cropped.size, (1280, 720))
        arr = np.asarray(cropped)
        # The lower half should be the bright "ground", not the dark room.
        self.assertGreater(arr[500:].mean(), 150)

    def test_real_tv_photo_if_present(self):
        path = Path(os.environ["SF_TV_PHOTO"]) if os.environ.get("SF_TV_PHOTO") else Path()
        if not path.is_file():
            self.skipTest("optional photo not provided (set SF_TV_PHOTO to test this path)")
        im = dg.load_image(str(path))
        # EXIF 6 → portrait
        self.assertGreater(im.size[1], im.size[0])
        cropped, quad, why = dg.crop_screen_quad(im, (1280, 720))
        self.assertTrue(why.startswith("screen_quad"), msg=why)
        self.assertEqual(cropped.size, (1280, 720))
        out = HERE / "test_out" / "tv_photo_crop.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Offline capture controls only: synthetic bytes are never guest evidence."""

import importlib.util
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import framebuffer_capture_oracle as oracle

spec = importlib.util.spec_from_file_location("capture_runner", ROOT / "scripts/kernel-framebuffer-capture.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

PREFIX = (
    "AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\n"
    "AURORA_UEFI_OWNERSHIP_OK: arena=16777216 bytes=1048576 descriptors=111\n"
    "AURORA_UEFI_PROTECTION_OK: root=16846848 stack=17068032\n"
)


def serial(mode):
    value = PREFIX + oracle.GATE + "\n" + oracle.RELEASED + "\n"
    if mode in ("framebuffer", "framebuffer-stale"):
        value += oracle.READY + "\n"
    value += (
        f"AURORA_DISPLAY_FRAME_COMPLETE: base={oracle.BASE} bytes={oracle.SIZE} stores=484711"
        if mode == "framebuffer"
        else "AURORA_DISPLAY_FAIL: stores=0"
    ) + "\n"
    return value.encode()


def ppm(raw):
    return b"P6\n800 600\n255\n" + oracle.ppm_rgb(800, 600, 800, 1, raw)


class CaptureControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        desired, cls.rgb, cls.stores = oracle.expected()
        cls.baseline = bytes([0xA5]) * oracle.SIZE
        cls.after = desired + cls.baseline[oracle.VISIBLE :]
        cls.before_ppm, cls.after_ppm = ppm(cls.baseline), ppm(cls.after)

    def capture(self, **changes):
        args = dict(
            mode="framebuffer",
            baseline=self.baseline,
            after=self.after,
            screenshot=self.after_ppm,
            baseline_screenshot=self.before_ppm,
        )
        args.update(changes)
        return oracle.validate_capture(**args)

    def test_scene_positive(self):
        self.assertEqual(self.capture()["stores"], 484711)

    def test_negative_no_write_positive(self):
        for mode in oracle.MODES[1:]:
            self.capture(mode=mode, after=self.baseline, screenshot=self.before_ppm)

    def test_pixel_tail_channels_extent(self):
        bad = []
        for index in (0, 3, 500000, oracle.VISIBLE, oracle.SIZE - 1):
            changed = bytearray(self.after)
            changed[index] ^= 1
            bad.append(bytes(changed))
        changed = bytearray(self.after)
        changed[0::4], changed[2::4] = changed[2::4], changed[0::4]
        bad.extend((bytes(changed), self.after[:-1], self.after + b"x"))
        for raw in bad:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                self.capture(after=raw)

    def test_negative_entire_resource(self):
        for index in (0, 3, 10000, oracle.VISIBLE, oracle.SIZE - 1):
            changed = bytearray(self.baseline)
            changed[index] ^= 1
            with self.assertRaises(ValueError):
                self.capture(mode="framebuffer-record", after=bytes(changed), screenshot=ppm(changed))

    def test_ppm_controls(self):
        cases = [
            b"",
            self.after_ppm[:-1],
            self.after_ppm + b"x",
            self.after_ppm.replace(b"800 600", b"801 600", 1),
            self.after_ppm.replace(b"255", b"256", 1),
            self.after_ppm.replace(b"P6", b"P3", 1),
            self.before_ppm,
        ]
        for screenshot in cases:
            with self.assertRaises(ValueError):
                self.capture(screenshot=screenshot)

    def test_baseline_controls(self):
        for baseline in (b"", self.baseline[:-1], self.after):
            with self.assertRaises(ValueError):
                self.capture(baseline=baseline)

    def test_wrong_pitch(self):
        padded, _ = oracle.reference(800, 600, 801, 1, guard=False)
        with self.assertRaises(ValueError):
            self.capture(after=padded)
        with self.assertRaises(ValueError):
            self.capture(after=padded[: oracle.SIZE])

    def test_serial_positive(self):
        for mode in oracle.MODES:
            oracle.validate_serial(serial(mode), mode)
            oracle.validate_serial((PREFIX + oracle.GATE + "\n").encode(), mode, gate_only=True)

    def test_serial_missing_duplicate_order_geometry(self):
        good = serial("framebuffer")
        lines = good.splitlines(keepends=True)
        cases = [
            good[:-1],
            good + b"unexpected\n",
            good.replace(b"stores=484711", b"stores=484712"),
            good.replace(b"bytes=1921024", b"bytes=1920000"),
            good.replace(b"width=800", b"width=801"),
            good.replace(b"base=2147483648", b"base=3221225472"),
            good + b"AURORA_UEFI_EXCEPTION\n",
        ]
        for n in range(len(lines)):
            cases.extend((b"".join(lines[:n] + lines[n + 1 :]), good + lines[n]))
        cases.append(b"".join(lines[:5] + [lines[6], lines[5]] + lines[7:]))
        for value in cases:
            with self.assertRaises(ValueError):
                oracle.validate_serial(value, "framebuffer")

    def test_no_write_serial_controls(self):
        for mode in oracle.MODES[1:]:
            with self.assertRaises(ValueError):
                oracle.validate_serial(serial(mode).replace(b"stores=0", b"stores=1"), mode)
        with self.assertRaises(ValueError):
            oracle.validate_serial(serial("framebuffer-stale"), "framebuffer-record")
        with self.assertRaises(ValueError):
            oracle.validate_serial(serial("framebuffer"), "framebuffer", gate_only=True)

    def test_missing_stale_and_failed_qmp_capture(self):
        with tempfile.TemporaryDirectory() as d:
            obj = runner.Channel.__new__(runner.Channel)
            obj.directory = pathlib.Path(d)
            obj.command = Mock(return_value="")
            with self.assertRaises(ValueError):
                obj.capture("test")
            (obj.directory / "test.bin").write_bytes(b"stale")
            with self.assertRaises(ValueError):
                obj.capture("test")
            obj.command.assert_called()
            obj.command = Mock(return_value="Error: cannot save")
            with self.assertRaises(ValueError):
                obj.capture("other")

    def test_pin_and_review_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "pin.json"
            p.write_text("{}")
            with self.assertRaises(ValueError):
                runner.pin(dict(path=str(p), sha256="0" * 64))
            with self.assertRaises(ValueError):
                runner.review(p, runner.digest(p), "a" * 64, "capture")
            row = dict(
                schema="aurora-framebuffer-review-v1",
                role="release",
                status="approved",
                manifest_sha256="a" * 64,
                issued_unix=time.time() - 20,
                expires_unix=time.time() - 10,
            )
            p.write_text(json.dumps(row))
            with self.assertRaises(ValueError):
                runner.review(p, runner.digest(p), "a" * 64, "release")
            row.update(role="capture")
            p.write_text(json.dumps(row))
            runner.review(p, runner.digest(p), "a" * 64, "capture")
            with self.assertRaises(ValueError):
                runner.review(p, runner.digest(p), "b" * 64, "capture")

    def test_exact_boot_markers_and_arithmetic(self):
        good = serial("framebuffer")
        pairs = [
            (b"ENTRY\n", b"ENTRY altered\n"),
            (b"attempts=1", b"attempts=2"),
            (b"arena=16777216", b"arena=16777217"),
            (b"bytes=1048576", b"bytes=1048575"),
            (b"descriptors=111", b"descriptors=0"),
            (b"descriptors=111", b"descriptors=513"),
            (b"root=16846848", b"root=16846849"),
            (b"stack=17068032", b"stack=16777216"),
        ]
        for before, after in pairs:
            with self.assertRaises(ValueError):
                oracle.validate_serial(good.replace(before, after), "framebuffer")

    def test_pty_setup_failure_preserves_receipt(self):
        with tempfile.TemporaryDirectory() as d, patch.object(runner.os, "openpty", side_effect=OSError("denied")):
            receipt = runner.run_case("framebuffer", {}, {}, {}, {}, pathlib.Path(d) / "case")
            self.assertEqual(receipt["status"], "failed")
            self.assertTrue((pathlib.Path(d) / "case/receipt.json").is_file())

    def test_timeout_and_interrupt_reap_guest_and_close_pipes(self):
        for error in (ValueError("QMP response timeout"), KeyboardInterrupt("interrupted")):
            with tempfile.TemporaryDirectory() as d:
                proc = Mock(returncode=None)
                proc.stdin = tempfile.TemporaryFile()
                proc.stdout = tempfile.TemporaryFile()
                proc.poll.side_effect = lambda: proc.returncode
                proc.terminate.side_effect = lambda: setattr(proc, "returncode", -15)
                proc.wait.side_effect = lambda **kwargs: proc.returncode
                with (
                    patch.object(runner.subprocess, "Popen", return_value=proc),
                    patch.object(runner.Channel, "receive", side_effect=error),
                ):
                    receipt = runner.run_case(
                        "framebuffer",
                        {"cases": {"framebuffer": {"esp": "/esp"}}},
                        {"qemu": "fake", "firmware": "/firmware"},
                        {"data": "/data"},
                        {},
                        pathlib.Path(d) / "case",
                    )
                self.assertEqual(receipt["status"], "failed")
                self.assertIn(str(error), receipt["error"])
                proc.terminate.assert_called_once()
                proc.wait.assert_called_once_with(timeout=2)
                self.assertTrue(proc.stdin.closed and proc.stdout.closed)
                self.assertEqual(receipt["exit_status"], -15)

    def test_bounded_clock(self):
        obj = runner.Channel.__new__(runner.Channel)
        obj.deadline = time.monotonic() - 1
        with self.assertRaises(ValueError):
            obj.remaining()


if __name__ == "__main__":
    unittest.main(verbosity=2)

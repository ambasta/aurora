#!/usr/bin/env python3
"""Offline preview routing and image controls. No compiler or real guest runs."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kernel_framebuffer_preview as preview

spec = importlib.util.spec_from_file_location("preview_developer_fixture", ROOT / "tests/developer-commands.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class Routing(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.DeveloperCommands()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.env["OVMF"] = self.fixture.firmware()
        shutil.copy2(ROOT / "scripts/kernel-framebuffer-preview.sh", self.fixture.scripts)
        self.fixture.script(
            self.fixture.scripts / "kernel-uefi-build.sh",
            'printf "build|%s\\n" "$UEFI_MODE" >> "$CALLS"\n'
            'printf "%s\\n" "$PWD/build/native framebuffer"\nexit "${BUILD_STATUS:-0}"\n',
        )
        self.fixture.tool(
            "python3",
            'printf "python|%s\\n" "$*" >> "$CALLS"\n'
            'if [[ "$*" == *--preflight ]]; then exit "${PREFLIGHT_STATUS:-0}"; fi\n'
            'exit "${CAPTURE_STATUS:-0}"\n',
        )

    def run_script(self, *args, **kwargs):
        return self.fixture.run_script("kernel-framebuffer-preview.sh", *args, **kwargs)

    def test_make_target_builds_before_capture_without_review(self):
        result = subprocess.run(
            [fixture.MAKE, "capture-framebuffer"],
            cwd=self.fixture.repo,
            env=self.fixture.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.fixture.calls()
        self.assertEqual(
            calls[:2], ["python|-B scripts/kernel_framebuffer_preview.py --preflight", "build|framebuffer"]
        )
        self.assertTrue(
            calls[2].startswith(
                "python|-B scripts/kernel_framebuffer_preview.py --build-dir "
                + str(self.fixture.repo / "build/native framebuffer")
                + " qemu-system-x86_64 "
            )
        )
        self.assertNotIn("receipt", calls[2])
        self.assertNotIn("manifest", calls[2])

    def test_full_smoke_builds_four_native_profiles_on_existing_entrypoint(self):
        self.fixture.script(
            self.fixture.scripts / "kernel-uefi-build.sh",
            'printf "build|%s\\n" "$UEFI_MODE" >> "$CALLS"\n'
            'printf "%s/build/meson/kernel-images/uefi/%s\\n" "$PWD" "$UEFI_MODE"\n',
        )
        self.run_script("--full-smoke")
        calls = self.fixture.calls()
        self.assertEqual(calls[1:5], ["build|" + mode for mode in preview.admission.MODES])
        self.assertIn("--full-smoke --build-dir ", calls[5])
        self.assertIn("/kernel-images/uefi/framebuffer ", calls[5])
        self.assertEqual(len(calls), 6)

    def test_help_needs_no_prerequisites(self):
        (self.fixture.bin / "qemu-system-x86_64").unlink()
        self.assertIn("Not qualified evidence", self.run_script("--help"))
        self.fixture.assert_no_work()

    def test_missing_tools_or_firmware_are_blocked_before_work(self):
        (self.fixture.bin / "qemu-system-x86_64").unlink()
        self.assertIn("BLOCKED:", self.run_script(expected=2))
        self.fixture.assert_no_work()
        self.fixture.tool("qemu-system-x86_64", "exit 93\n")
        self.assertIn("BLOCKED:", self.run_script(env={"OVMF": "/missing.fd"}, expected=2))
        self.fixture.assert_no_work()
        (self.fixture.bin / "ld").write_text("#!/bin/bash\nexit 1\n")
        self.assertIn("BLOCKED:", self.run_script(expected=2))
        self.fixture.assert_no_work()

    def test_malformed_controls_are_failures(self):
        for name in (
            "KERNEL_TEST_FAULT",
            "KERNEL_USER_PROBE_MODE",
            "KERNEL_CONSOLE",
            "UEFI_MODE",
            "AURORA_TEST_CONTEXT",
        ):
            with self.subTest(name=name):
                self.assertIn("FAIL:", self.run_script(env={name: "1"}, expected=1))
        self.assertIn("FAIL:", self.run_script("extra", expected=1))
        self.assertIn("FAIL:", self.run_script(env={"OVMF_CODE": "code"}, expected=1))
        self.fixture.assert_no_work()

    def test_build_failure_including_exit_two_never_becomes_blocked_or_starts_guest(self):
        for status in (1, 2, 17):
            with self.subTest(status=status):
                self.fixture.record.unlink(missing_ok=True)
                output = self.run_script(env={"BUILD_STATUS": str(status)}, expected=status)
                self.assertIn("FAIL:", output)
                self.assertNotIn("BLOCKED:", output)
                self.assertEqual(len(self.fixture.calls()), 2)

    def test_preflight_and_capture_failure_are_preserved(self):
        self.run_script(env={"PREFLIGHT_STATUS": "2"}, expected=2)
        self.assertEqual(len(self.fixture.calls()), 1)
        self.fixture.record.unlink()
        self.run_script(env={"CAPTURE_STATUS": "1"}, expected=1)
        self.assertEqual(len(self.fixture.calls()), 3)

    def test_split_firmware_and_qemu_data_forwarded_as_single_arguments(self):
        self.fixture.tool("python3", 'printf "python-arg|%s\\n" "$@" >> "$CALLS"\n')
        code, variables = self.fixture.home / "code with spaces.fd", self.fixture.home / "vars with spaces.fd"
        code.write_bytes(b"code")
        variables.write_bytes(b"variables")
        data = self.fixture.home / "data with spaces"
        data.mkdir()
        self.run_script(env={"OVMF": "", "OVMF_CODE": str(code), "OVMF_VARS": str(variables), "QEMU_DATA": str(data)})
        self.assertEqual(
            self.fixture.calls()[-4:],
            ["python-arg|", "python-arg|" + str(code), "python-arg|" + str(variables), "python-arg|" + str(data)],
        )
        self.assertIn("python-arg|" + str(self.fixture.repo / "build/native framebuffer"), self.fixture.calls())
        self.assertEqual(variables.read_bytes(), b"variables")


class PreviewControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rgb = bytes([7, 31, 99]) * preview.WIDTH * preview.HEIGHT
        cls.ppm = b"P6\n800 600\n255\n" + cls.rgb

    def test_png_round_trip_and_rejection(self):
        data = preview.png(self.ppm)
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        chunks = {}
        offset = 8
        while offset < len(data):
            size = struct.unpack("!I", data[offset : offset + 4])[0]
            kind = data[offset + 4 : offset + 8]
            body = data[offset + 8 : offset + 8 + size]
            crc = struct.unpack("!I", data[offset + 8 + size : offset + 12 + size])[0]
            self.assertEqual(crc, zlib.crc32(kind + body))
            chunks[kind] = body
            offset += size + 12
        self.assertEqual(offset, len(data))
        self.assertEqual(set(chunks), {b"IHDR", b"IDAT", b"IEND"})
        self.assertEqual(struct.unpack("!2I5B", chunks[b"IHDR"]), (800, 600, 8, 2, 0, 0, 0))
        rows = zlib.decompress(chunks[b"IDAT"])
        self.assertEqual(rows, (b"\0" + self.rgb[:2400]) * 600)
        for bad in (b"", self.ppm[:-1], self.ppm + b"x", self.ppm.replace(b"800 600", b"801 600")):
            with self.assertRaises(ValueError):
                preview.png(bad)

    def test_pty_unavailable_is_blocked(self):
        with patch.object(preview.os, "openpty", side_effect=OSError("denied")):
            with self.assertRaises(preview.admission.common.Blocked):
                preview.preflight()

    def test_output_symlink_rejected_before_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "build").symlink_to(root / "elsewhere")
            with patch.object(preview, "ROOT", root), self.assertRaisesRegex(ValueError, "symlink"):
                preview.preflight()

    def test_command_is_bounded_local_tcg_without_device_passthrough(self):
        firmware = preview.firmware_options("", "/code.fd", "/vars.fd")
        argv = preview.capture.command({"qemu": "qemu"}, {}, "/esp", "/dev/pts/7", True, firmware)
        self.assertIn("tcg", argv)
        self.assertNotIn("-L", argv)
        self.assertNotIn("-bios", argv)
        self.assertNotIn("-icount", argv)
        self.assertEqual(argv[-3:], ["-qmp", "stdio", "-S"])
        self.assertIn("if=pflash,unit=0,format=raw,readonly=on,file=/code.fd", argv)
        self.assertIn("if=pflash,unit=1,format=raw,snapshot=on,file=/vars.fd", argv)
        self.assertIn("format=raw,file=fat:ro:/esp,snapshot=on", argv)
        self.assertEqual(argv[argv.index("-nic") + 1], "none")
        legacy = preview.capture.command(
            {"qemu": "qemu", "firmware": "/combined.fd"}, {"data": "/data"}, "/esp", "stdio"
        )
        self.assertEqual(legacy[:3], ["qemu", "-L", "/data"])
        self.assertEqual(legacy[legacy.index("-bios") + 1], "/combined.fd")

    def test_success_is_unqualified_fresh_image_and_failure_cannot_reuse_it(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            (root / "build").mkdir()

            def synthetic(*args, **kwargs):
                directory = args[5]
                directory.mkdir()
                (directory / "after.ppm").write_bytes(self.ppm)
                return {"status": "passed", "synthetic": True}

            with (
                patch.object(preview, "ROOT", root),
                patch.object(preview.admission, "configure_paths"),
                patch.object(preview, "preflight"),
                patch.object(preview.admission, "checked", return_value={}) as checked,
                patch.object(preview.capture, "run_case", side_effect=synthetic),
            ):
                first = preview.run("qemu", "firmware", "", "", "", build_dir=root / "native/framebuffer")
                second = preview.run("qemu", "firmware", "", "", "", build_dir=root / "native/framebuffer")
                self.assertFalse(first["qualified"])
                self.assertNotEqual(first["image"], second["image"])
                self.assertEqual(checked.call_count, 4)
                with patch.object(
                    preview.capture, "run_case", return_value={"status": "failed", "error": "guest failed"}
                ):
                    with self.assertRaisesRegex(ValueError, "guest failed"):
                        preview.run("qemu", "firmware", "", "", "", build_dir=root / "native/framebuffer")
                records = [json.loads(p.read_text()) for p in root.glob("build/framebuffer-preview/*/preview.json")]
                self.assertEqual(sorted(row["status"] for row in records), ["failed", "passed", "passed"])
                self.assertEqual(len(list(root.glob("build/framebuffer-preview/*/framebuffer.png"))), 2)
                self.assertNotIn("image", next(row for row in records if row["status"] == "failed"))

    def test_full_smoke_preserves_failures_and_requires_real_normal_entrypoint(self):
        for failure, restore_status, unsettled in (
            (None, 0, False),
            ("framebuffer-record", 0, False),
            (None, 7, False),
            ("framebuffer-record", 0, True),
        ):
            with (
                self.subTest(failure=failure, restore_status=restore_status, unsettled=unsettled),
                tempfile.TemporaryDirectory() as temporary,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                root = Path(temporary)
                (root / "build").mkdir()
                build = root / "build/meson/kernel-images/uefi/framebuffer"
                modes = []

                def synthetic(mode, manifest, pins, roots, env, directory, **kwargs):
                    modes.append(mode)
                    directory.mkdir()
                    (directory / "after.ppm").write_bytes(self.ppm)
                    return dict(
                        mode=mode,
                        status="failed" if mode == failure else "passed",
                        error="synthetic guest failure",
                        unsettled=mode == failure and unsettled,
                    )

                def restore(argv, log, **kwargs):
                    self.assertEqual(argv, ["bash", root / "scripts/kernel-uefi-smoke.sh", "normal"])
                    self.assertEqual(kwargs["env"]["MESON_BUILD_DIR"], str(root / "build/meson"))
                    log.write_text("normal smoke output")
                    return restore_status

                with (
                    patch.object(preview, "ROOT", root),
                    patch.object(preview, "preflight"),
                    patch.object(preview.admission, "configure_paths"),
                    patch.object(preview.admission, "checked", side_effect=lambda mode: {"mode": mode}),
                    patch.object(preview.capture, "run_case", side_effect=synthetic),
                    patch.object(preview.transport, "run_logged", side_effect=restore) as normal,
                ):
                    if failure or restore_status:
                        with self.assertRaises(ValueError):
                            preview.run("qemu", "firmware", "", "", "", build_dir=build, full_smoke=True)
                    else:
                        preview.run("qemu", "firmware", "", "", "", build_dir=build, full_smoke=True)
                self.assertEqual(modes, list(preview.admission.MODES[:2] if failure else preview.admission.MODES))
                self.assertEqual(normal.call_count, 0 if unsettled else 1)
                record = json.loads(next(root.glob("build/framebuffer-preview/*/preview.json")).read_text())
                self.assertEqual(record["status"], "failed" if failure or restore_status else "passed")
                self.assertEqual(
                    record["normal_restoration"]["status"], "failed" if unsettled or restore_status else "passed"
                )
                if failure:
                    self.assertIn("synthetic guest failure", record["error"])

    def test_postcapture_source_drift_prevents_png_success(self):
        with tempfile.TemporaryDirectory() as temporary, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temporary)
            (root / "build").mkdir()
            with (
                patch.object(preview, "ROOT", root),
                patch.object(preview.admission, "configure_paths"),
                patch.object(preview, "preflight"),
                patch.object(preview.admission, "checked", side_effect=[{}, ValueError("changed image")]),
                patch.object(preview.capture, "run_case", return_value={"status": "passed"}),
            ):
                with self.assertRaisesRegex(ValueError, "changed image"):
                    preview.run("qemu", "firmware", "", "", "", build_dir=root / "native/framebuffer")
                self.assertEqual(list(root.glob("build/framebuffer-preview/*/framebuffer.png")), [])
                record = next(root.glob("build/framebuffer-preview/*/preview.json"))
                self.assertEqual(json.loads(record.read_text())["status"], "failed")

    def test_admission_failure_starts_no_guest_or_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(preview, "ROOT", root),
                patch.object(preview.admission, "configure_paths"),
                patch.object(preview, "preflight"),
                patch.object(preview.admission, "checked", side_effect=ValueError("changed image")),
                patch.object(preview.capture, "run_case") as guest,
            ):
                with self.assertRaisesRegex(ValueError, "changed image"):
                    preview.run("qemu", "firmware", "", "", "", build_dir=root / "native/framebuffer")
                guest.assert_not_called()
                self.assertFalse((root / "build").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

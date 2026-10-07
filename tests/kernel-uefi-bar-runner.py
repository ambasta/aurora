#!/usr/bin/env python3
"""Compiler-free BAR entrypoint controls; synthetic inputs are never qualification."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bar_runner", ROOT / "scripts/kernel-uefi-bar-run.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
REAL_TRACE = runner.module("bar-trace")


class BarRunner(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-bar-runner-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        self.out = self.home / "fresh receipts"
        self.calls = self.home / "calls"
        self.builder = self.repo / "scripts/kernel-uefi-build.sh"
        self.builder.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$UEFI_MODE" >> "$CALLS"\n'
            'if [ "$UEFI_MODE" = normal ]; then exit "${RESTORE_STATUS:-0}"; fi\n'
            'exit "${BUILD_STATUS:-0}"\n'
        )
        self.builder.chmod(0o755)
        self.qemu = self.home / "qemu-system-x86_64"
        self.qemu.write_text("#!/bin/sh\nexit 93\n")
        self.qemu.chmod(0o755)
        self.data = self.home / "data"
        self.data.mkdir()
        self.fixture = self.home / "clean firmware"
        self.code = self.fixture / "output/OVMF_CODE.fd"
        self.variables = self.fixture / "output/OVMF_VARS.fd"
        self.firmware_patch = self.fixture / "provenance/policy-three-file.patch"
        self.stock = self.home / "stock.fd"
        self.events = self.home / "events"
        for index, path in enumerate((self.code, self.variables, self.firmware_patch, self.stock, self.events)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"synthetic prerequisite {index}\n")
        self.coverage_path = self.home / "coverage.json"
        self.coverage_path.write_text(json.dumps({"events": "events"}))
        self.coverage = {"synthetic_control": True}
        self.trace = SimpleNamespace(load_coverage=Mock(return_value=self.coverage), validate_coverage=Mock())
        self.provenance = SimpleNamespace(
            PINS={
                key: runner.digest(path)
                for key, path in (
                    ("qemu", self.qemu),
                    ("events", self.events),
                    ("clean_code", self.code),
                    ("clean_vars", self.variables),
                    ("clean_patch", self.firmware_patch),
                    ("stock_code", self.stock),
                )
            }
        )
        self.env = dict(
            PATH=str(self.home),
            QEMU=str(self.qemu),
            QEMU_DATA=str(self.data),
            AURORA_BAR_COVERAGE=str(self.coverage_path),
            AURORA_BAR_FIRMWARE=str(self.fixture),
            LD_LIBRARY_PATH=str(self.home),
            OVMF=str(self.stock),
            CALLS=str(self.calls),
        )
        self.addCleanup(patch.stopall)
        patch.object(runner, "ROOT", self.repo).start()
        patch.object(runner, "module", side_effect=self.module).start()
        patch.dict(os.environ, self.env, clear=True).start()

    def module(self, name):
        if name == "bar-trace":
            return self.trace
        if name == "bar-provenance":
            return self.provenance
        if name == "bar-smoke":
            return self.smoke
        self.fail("Unexpected validator import: " + name)

    def assert_no_work(self):
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.out.exists())
        self.assertFalse((self.repo / "build").exists())

    def reject(self, expected):
        with self.assertRaisesRegex((ValueError, OSError), expected):
            runner.run("bar-prepare", self.out)
        self.assert_no_work()

    def test_each_missing_required_selector_rejects_without_artifacts_or_restore(self):
        for name in ("QEMU_DATA", "AURORA_BAR_COVERAGE", "AURORA_BAR_FIRMWARE", "LD_LIBRARY_PATH"):
            with self.subTest(name=name), patch.dict(os.environ, {name: ""}):
                self.reject("Set " + name)

    def test_qemu_default_name_is_discovered_without_executing_it(self):
        del os.environ["QEMU"]
        config = runner.preflight("bar-prepare", self.out, dict(os.environ))
        self.assertEqual(config["qemu"], self.qemu)
        self.trace.validate_coverage.assert_called_once_with(self.coverage)
        self.assert_no_work()

    def test_missing_qemu_is_actionable(self):
        os.environ["QEMU"] = "missing-qemu"
        self.reject("Missing dependency: missing-qemu")

    def test_invalid_directories_and_files_reject_before_work(self):
        for name in ("QEMU_DATA", "AURORA_BAR_COVERAGE", "AURORA_BAR_FIRMWARE"):
            with self.subTest(name=name), patch.dict(os.environ, {name: str(self.home / "missing")}):
                self.reject(name + " must name a readable")
        self.code.unlink()
        self.reject("clean firmware CODE must name a readable file")

    def test_unreviewed_inputs_reject_before_build(self):
        for path, label in (
            (self.qemu, "QEMU"),
            (self.events, "trace events"),
            (self.code, "clean firmware CODE"),
            (self.variables, "clean firmware VARS"),
            (self.firmware_patch, "clean firmware patch"),
        ):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                self.reject("Unreviewed " + label)
                path.write_bytes(original)

    def test_real_coverage_validator_error_is_preserved(self):
        self.trace.validate_coverage = REAL_TRACE.validate_coverage
        self.reject("Invalid AURORA_BAR_COVERAGE: Unpinned trace binary")

    def test_malformed_coverage_key_and_json_report_named_input(self):
        for error in (KeyError("events"), json.JSONDecodeError("invalid", "?", 0)):
            self.trace.load_coverage.side_effect = error
            self.reject("Invalid AURORA_BAR_COVERAGE")

    def test_stock_modes_do_not_require_clean_fixture(self):
        del os.environ["AURORA_BAR_FIRMWARE"]
        config = runner.preflight("bar-state", self.out, dict(os.environ))
        self.assertFalse(config["clean"])
        self.assertEqual(config["code"], self.stock)
        self.assert_no_work()

    def test_clean_profile_never_uses_stock_firmware(self):
        del os.environ["AURORA_BAR_FIRMWARE"]
        self.reject("stock OVMF is unsuitable")

    def test_mixed_controls_reject_before_build(self):
        for name in (
            "KERNEL_TEST_FUTURE",
            "KERNEL_USER_PROBE_MODE",
            "KERNEL_CONSOLE",
            "UEFI_MODE",
            "UEFI_CONSOLE_HANDOFF",
            "AURORA_TEST_CONTEXT",
        ):
            with self.subTest(name=name), patch.dict(os.environ, {name: "active"}):
                self.reject("Unset " + name)

    def test_existing_output_directory_and_file_are_not_reused(self):
        self.out.mkdir()
        marker = self.out / "keep"
        marker.write_text("retained")
        with self.assertRaisesRegex(ValueError, "fresh and absent"):
            runner.run("bar-prepare", self.out)
        self.assertEqual(marker.read_text(), "retained")
        self.assertFalse(self.calls.exists())
        marker.unlink()
        self.out.rmdir()
        self.out.write_text("retained file")
        with self.assertRaisesRegex(ValueError, "fresh and absent"):
            runner.run("bar-prepare", self.out)
        self.assertEqual(self.out.read_text(), "retained file")

    def test_dangling_output_symlink_rejects_without_following_it(self):
        self.out.symlink_to(self.home / "missing-output")
        with self.assertRaisesRegex(ValueError, "fresh and absent"):
            runner.run("bar-prepare", self.out)
        self.assertTrue(self.out.is_symlink())
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.home / "missing-output").exists())

    def test_shared_image_output_and_comma_paths_reject(self):
        for output in (self.repo / "build/uefi/receipts", self.home / "comma,output"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                runner.run("bar-prepare", output)
        self.assert_no_work()

    def test_output_creation_failure_does_not_restore(self):
        with patch.object(Path, "mkdir", side_effect=OSError("output unavailable")):
            self.reject("output unavailable")

    def test_build_spawn_failure_does_not_restore(self):
        self.builder.unlink()
        with self.assertRaises(FileNotFoundError):
            runner.run("bar-prepare", self.out)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.out / "restore.log").exists())

    def test_failed_started_build_restores_once_and_preserves_failure(self):
        os.environ["BUILD_STATUS"] = "79"
        with patch.object(runner, "execute") as execute:
            with self.assertRaises(subprocess.CalledProcessError) as result:
                runner.run("bar-prepare", self.out)
            self.assertEqual(result.exception.returncode, 79)
            execute.assert_not_called()
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare", "normal"])
        self.assertTrue((self.out / "restore.log").is_file())

    def test_interrupted_build_is_killed_and_joined_before_restore(self):
        events = []
        process = Mock(pid=12345)
        process.poll.return_value = None
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        with patch.object(runner.subprocess, "Popen", return_value=process) as spawn:
            with patch.object(runner.os, "killpg", side_effect=lambda *args: events.append("kill-group")):
                with patch.object(
                    runner.subprocess, "run", side_effect=lambda *args, **kwargs: events.append("restore")
                ):
                    with self.assertRaises(KeyboardInterrupt):
                        runner.run("bar-prepare", self.out)
        self.assertEqual(events, ["kill-group", "restore"])
        self.assertEqual(process.wait.call_count, 2)
        self.assertTrue(spawn.call_args.kwargs["start_new_session"])

    def test_interrupted_wait_never_signals_an_already_reaped_builder(self):
        process = Mock(pid=12345)
        process.poll.return_value = 0
        process.wait.side_effect = [KeyboardInterrupt(), 0]
        with patch.object(runner.subprocess, "Popen", return_value=process):
            with patch.object(runner.os, "killpg") as kill:
                with patch.object(runner.subprocess, "run") as restore:
                    with self.assertRaises(KeyboardInterrupt):
                        runner.run("bar-prepare", self.out)
        kill.assert_not_called()
        restore.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)

    def test_real_sigint_cannot_leave_a_child_overwriting_restored_image(self):
        self.check_real_interruption(signal.SIGINT)

    def test_real_sigterm_cannot_leave_a_child_overwriting_restored_image(self):
        self.check_real_interruption(signal.SIGTERM)

    def check_real_interruption(self, interruption):
        ready = self.home / "child-ready"
        profile = self.home / "profile"
        child = self.home / "delayed-child.py"
        child.write_text(
            "import pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text('started')\n"
            "time.sleep(0.6)\n"
            "pathlib.Path(sys.argv[2]).write_text('stale-console')\n"
        )
        self.builder.write_text(
            '#!/bin/sh\nif [ "$UEFI_MODE" = normal ]; then printf normal > "$PROFILE"; exit 0; fi\n'
            '"$REAL_PYTHON" "$CHILD" "$READY" "$PROFILE" &\nwait\n'
        )
        script = (
            "import importlib.util, pathlib, sys\n"
            "s=importlib.util.spec_from_file_location('runner',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
            "m.ROOT=pathlib.Path(sys.argv[2])\n"
            "m.preflight=lambda mode, output, env: {'output': output}\n"
            "m.execute=lambda *args: None\n"
            "sys.argv=['runner','bar-prepare','--output',sys.argv[3]]\n"
            "sys.exit(m.main())\n"
        )
        env = dict(os.environ, REAL_PYTHON=sys.executable, CHILD=str(child), READY=str(ready), PROFILE=str(profile))
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-c",
                script,
                str(ROOT / "scripts/kernel-uefi-bar-run.py"),
                str(self.repo),
                str(self.out),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "synthetic build child did not start")
            process.send_signal(interruption)
            stdout, stderr = process.communicate(timeout=5)
            self.assertNotEqual(process.returncode, 0, stdout + stderr)
            self.assertNotIn(b"PASS:", stdout)
            if interruption == signal.SIGTERM:
                self.assertEqual(process.returncode, 143)
            self.assertEqual(profile.read_text(), "normal")
            time.sleep(0.7)
            self.assertEqual(profile.read_text(), "normal", "surviving build child raced normal restoration")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_validator_failure_restores_without_suppressing_rejection(self):
        with patch.object(runner, "execute", side_effect=ValueError("exact serial rejected")):
            with self.assertRaisesRegex(ValueError, "exact serial rejected"):
                runner.run("bar-prepare", self.out)
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare", "normal"])

    def test_dual_failure_retains_validator_error_and_reports_restore_error(self):
        os.environ["RESTORE_STATUS"] = "81"
        errors = io.StringIO()
        with patch.object(runner, "execute", side_effect=ValueError("trace rejected")), redirect_stderr(errors):
            with self.assertRaisesRegex(ValueError, "trace rejected"):
                runner.run("bar-prepare", self.out)
        self.assertIn("normal-image restoration also failed", errors.getvalue())
        self.assertIn("81", errors.getvalue())

    def test_restore_failure_cannot_print_pass(self):
        os.environ["RESTORE_STATUS"] = "81"
        output = io.StringIO()
        with patch.object(runner, "execute"), redirect_stdout(output):
            with self.assertRaises(subprocess.CalledProcessError):
                runner.run("bar-prepare", self.out)
        self.assertNotIn("PASS:", output.getvalue())

    def test_success_restores_once_and_uses_exact_requested_output(self):
        output = io.StringIO()
        with patch.object(runner, "execute") as execute, redirect_stdout(output):
            runner.run("bar-prepare", self.out)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[1]["output"], self.out)
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare", "normal"])
        self.assertIn(str(self.out / "receipt.json"), output.getvalue())
        self.assertIn("normal image restored", output.getvalue())

    def test_actual_executor_keeps_original_clock_profile_and_mandatory_validators(self):
        build = self.repo / "build/uefi"
        (build / "esp/EFI/BOOT").mkdir(parents=True)
        (build / "esp/EFI/BOOT/BOOTX64.EFI").write_text("synthetic loader")
        (self.repo / "build/aurorac").write_text("synthetic compiler identity")
        for name in ("payload.bin", "payload.elf"):
            (build / name).write_text("synthetic payload")
        (build / "bar-metadata.json").write_text("{}")
        self.smoke = SimpleNamespace(validate=Mock())
        self.trace.validate_trace = Mock(return_value={"synthetic_validation": True})
        self.provenance.validate = Mock()
        self.provenance.REVISION = "synthetic firmware revision"
        expected_modes = (
            "bar-state",
            "bar-capture",
            "bar-inherited",
            "bar-read",
            "bar-prepare",
            "bar-write",
            "bar-revoked",
            "bar-alias",
        )
        expected_clean = ("bar-read", "bar-prepare", "bar-write", "bar-revoked", "bar-alias")
        self.assertEqual(runner.MODES, expected_modes)
        self.assertEqual(runner.CLEAN, expected_clean)
        for mode in expected_modes:
            with self.subTest(mode=mode):
                config = runner.preflight(mode, self.out, dict(os.environ))
                self.out.mkdir()
                status = 33 if mode in ("bar-read", "bar-prepare") else 35

                def guest(argv, **kwargs):
                    kwargs["stdout"].write("synthetic serial\n")
                    (self.out / "trace.log").write_text("synthetic trace\n")
                    (self.out / "firmware.log").write_text("synthetic firmware log\n")
                    return SimpleNamespace(returncode=status)

                with patch.object(runner.subprocess, "run", side_effect=guest) as launch:
                    with redirect_stdout(io.StringIO()):
                        runner.execute(mode, config, dict(os.environ))
                launch.assert_called_once()
                argv = launch.call_args.args[0]
                firmware = (
                    [
                        "-drive",
                        f"if=pflash,format=raw,unit=0,file={self.code},readonly=on",
                        "-drive",
                        f"if=pflash,format=raw,unit=1,file={self.out}/vars-runtime.fd",
                    ]
                    if mode in expected_clean
                    else ["-bios", str(self.stock)]
                )
                self.assertEqual(
                    argv,
                    [
                        str(self.qemu),
                        "-L",
                        str(self.data),
                        "-machine",
                        "q35",
                        "-accel",
                        "tcg",
                        "-cpu",
                        "qemu64",
                        "-smp",
                        "1",
                        "-m",
                        "128M",
                        *firmware,
                        "-drive",
                        f"format=raw,file=fat:ro:{self.out}/esp,snapshot=on",
                        "-device",
                        "nvme,serial=AURORA_READ_ONLY,bus=pcie.0,addr=02.0",
                        "-nic",
                        "none",
                        "-display",
                        "none",
                        "-serial",
                        "stdio",
                        "-monitor",
                        "none",
                        "-no-reboot",
                        "-trace",
                        f"events={self.events},file={self.out}/trace.log",
                        "-chardev",
                        f"file,id=firmware,path={self.out}/firmware.log",
                        "-device",
                        "isa-debugcon,iobase=0x402,chardev=firmware",
                        "-device",
                        "isa-debug-exit,iobase=0xf4,iosize=0x04",
                    ],
                )
                self.assertEqual(launch.call_args.kwargs["stdin"], subprocess.DEVNULL)
                self.assertEqual(launch.call_args.kwargs["timeout"], 60)
                self.smoke.validate.assert_called_once_with(status, "synthetic serial\n", mode, {})
                self.trace.validate_trace.assert_called_once_with(
                    "synthetic trace\n", "synthetic firmware log\n", "synthetic serial\n", mode, self.coverage, {}
                )
                self.provenance.validate.assert_called_once_with(self.out / "receipt.json")
                for validator, label in (
                    (self.smoke.validate, "serial rejected"),
                    (self.trace.validate_trace, "trace rejected"),
                    (self.provenance.validate, "provenance rejected"),
                ):
                    shutil.rmtree(self.out)
                    self.out.mkdir()
                    validator.side_effect = ValueError(label)
                    with patch.object(runner.subprocess, "run", side_effect=guest), redirect_stdout(io.StringIO()):
                        with self.assertRaisesRegex(ValueError, label):
                            runner.execute(mode, config, dict(os.environ))
                    validator.side_effect = None
                self.smoke.validate.reset_mock()
                self.trace.validate_trace.reset_mock()
                self.provenance.validate.reset_mock()
                shutil.rmtree(self.out)

    def test_public_make_exports_receipt_and_fixture_selectors(self):
        shutil.copy2(ROOT / "Makefile", self.repo / "Makefile")
        bin_path = self.home / "bin"
        bin_path.mkdir()
        python = bin_path / "python3"
        python.write_text(
            '#!/bin/sh\nprintf "%s|%s|%s|%s\\n" "$*" "$AURORA_BAR_FIRMWARE" '
            '"$AURORA_BAR_COVERAGE" "$AURORA_NVME_RECEIPTS" >> "$CALLS"\n'
        )
        python.chmod(0o755)
        result = subprocess.run(
            [
                shutil.which("make", path=os.defpath),
                "smoke-nvme-prepare",
                "AURORA_NVME_RECEIPTS=" + str(self.out),
                "AURORA_BAR_FIRMWARE=" + str(self.fixture),
                "AURORA_BAR_COVERAGE=" + str(self.coverage_path),
            ],
            cwd=self.repo,
            env={"PATH": str(bin_path), "CALLS": str(self.calls)},
            text=True,
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.calls.read_text().strip(),
            f"scripts/kernel-uefi-bar-run.py bar-prepare --output {self.out}|"
            f"{self.fixture}|{self.coverage_path}|{self.out}",
        )
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()

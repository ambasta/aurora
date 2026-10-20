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
sys.path.insert(0, str(ROOT / "scripts"))
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
        self.build = self.repo / "build/kernel-images/uefi/bar-prepare"
        self.builder = self.repo / "scripts/meson_test.py"
        self.builder.write_text(
            "import os, pathlib, sys\n"
            "mode = sys.argv[sys.argv.index('--profile') + 1]\n"
            "with pathlib.Path(os.environ['CALLS']).open('a') as calls: calls.write(mode + '\\n')\n"
            "sys.exit(int(os.environ['BUILD_STATUS'])) if os.environ.get('BUILD_STATUS') else None\n"
            "print(pathlib.Path('build/kernel-images/uefi', mode).resolve())\n"
        )
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
        patch.object(runner, "selected_kernel_compiler", side_effect=lambda build: build / "aurorac").start()
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

    def main_result(self):
        output, errors = io.StringIO(), io.StringIO()
        argv = ["bar-runner", "bar-prepare", "--output", str(self.out)]
        with patch.object(sys, "argv", argv), redirect_stdout(output), redirect_stderr(errors):
            status = runner.main()
        return SimpleNamespace(returncode=status, stdout=output.getvalue(), stderr=errors.getvalue())

    def assert_outcome(self, result, outcome, diagnostic=""):
        transcript = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0 if outcome == "PASS" else 2, transcript)
        stream = result.stdout if outcome == "PASS" else result.stderr
        self.assertTrue(any(line.startswith(outcome + ":") for line in stream.splitlines()), transcript)
        self.assertIn(diagnostic, transcript)
        for other in {"PASS", "FAIL", "BLOCKED"} - {outcome}:
            self.assertFalse(any(line.startswith(other + ":") for line in transcript.splitlines()), transcript)

    def test_missing_qemu_reports_blocked_without_work(self):
        os.environ["QEMU"] = "missing-qemu"
        self.assert_outcome(self.main_result(), "BLOCKED", "Missing dependency: missing-qemu")
        self.assert_no_work()

    def test_ordinary_defaults_select_package_and_fresh_controls(self):
        for name in ("AURORA_BAR_COVERAGE", "AURORA_BAR_FIRMWARE", "LD_LIBRARY_PATH"):
            del os.environ[name]
        with (
            patch.object(
                runner.controls, "supported_firmware", return_value=(self.code, self.variables, self.firmware_patch)
            ),
            patch.object(runner.controls, "stock_firmware", return_value=self.stock),
        ):
            config = runner.preflight("bar-prepare", self.out, dict(os.environ))
        self.assertTrue(config["packaged"])
        self.assertIsNone(config["coverage_path"])
        self.assertEqual(config["stock"], self.stock)
        self.trace.validate_coverage.assert_not_called()
        self.assert_no_work()

    def test_default_controls_generated_once_before_selected_guest(self):
        del os.environ["AURORA_BAR_COVERAGE"]
        with (
            patch.object(runner.controls, "stock_firmware", return_value=self.stock),
            patch.object(runner.controls, "generate", return_value=self.coverage_path) as generate,
            patch.object(runner, "execute") as execute,
            redirect_stdout(io.StringIO()),
        ):
            runner.run("bar-prepare", self.out)
        generate.assert_called_once_with(
            "bar", self.out / "controls", self.qemu, self.data, self.stock, dict(os.environ)
        )
        self.assertEqual(execute.call_args.args[1]["coverage_path"], self.coverage_path)
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])

    def test_stock_control_selects_inherited_measurement_not_early_refusal(self):
        controls = runner.controls
        build = self.home / "native-bar-read"
        (build / "esp").mkdir(parents=True)
        (build / "bar-metadata.json").write_text("{}")
        stock_check = Mock(side_effect=RuntimeError("stock trace oracle reached"))
        trace = SimpleNamespace(EVENT_TEXT=REAL_TRACE.EVENT_TEXT, validate_stock_control=stock_check)
        for family, mode in ((family, mode) for family in ("bar", "ivrs") for mode in ("bar-inherited", "bar-state")):
            with self.subTest(family=family, mode=mode):
                _, serial, _ = REAL_TRACE.bar.fixture(mode)
                root = self.home / ("controls-" + family + "-" + mode)

                def fake_run(argv, output, **kwargs):
                    Path(output).write_text(serial if Path(output).name == "serial.log" else "events\n")
                    if Path(output).name == "serial.log":
                        self.assertEqual(kwargs["expected"], 35)
                        (root / "stock.trace").write_text("synthetic stock trace\n")

                with (
                    patch.object(controls, "digest", return_value=controls.QEMU_SHA256),
                    patch.object(controls, "native_image", return_value=build) as native,
                    patch.object(controls.transport, "run_logged", side_effect=fake_run),
                    patch.object(
                        controls, "module", side_effect=lambda name: trace if name == "bar-trace" else REAL_TRACE.bar
                    ),
                    patch.object(controls, "msix_control") as msix,
                ):
                    if mode == "bar-inherited":
                        with self.assertRaisesRegex(RuntimeError, "stock trace oracle reached"):
                            controls.generate(family, root, self.qemu, self.data, self.stock, self.env)
                        stock_check.assert_called_once_with("synthetic stock trace\n")
                        stock_check.reset_mock()
                    else:
                        with self.assertRaisesRegex(ValueError, "Missing/duplicate/malformed descriptor"):
                            controls.generate(family, root, self.qemu, self.data, self.stock, self.env)
                        stock_check.assert_not_called()
                    native.assert_called_once_with("bar-read", root / "stock", self.env)
                    msix.assert_not_called()

    def test_supported_firmware_prefix_checks_marker_patch_and_image_shapes(self):
        prefix = self.home / "package"
        firmware = prefix / "firmware"
        firmware.mkdir(parents=True)
        code, variables, policy, version = [
            firmware / name for name in ("OVMF_CODE.fd", "OVMF_VARS.fd", "policy-three-file.patch", "VERSION")
        ]
        for path, size in ((code, 3653632), (variables, 540672)):
            with path.open("wb") as stream:
                stream.truncate(size)
        policy.write_bytes(b"synthetic reviewed policy")
        version.write_text(runner.controls.FIRMWARE_VERSION + "\n")
        env = {"AURORA_BOOT_FIXTURE_PREFIX": str(prefix)}
        with patch.object(runner.controls, "PATCH_SHA256", runner.digest(policy)):
            self.assertEqual(runner.controls.supported_firmware(env), (code, variables, policy))
            for path, value in ((version, b"wrong version\n"), (policy, b"modified policy"), (variables, b"truncated")):
                with self.subTest(path=path):
                    original = path.read_bytes()
                    path.write_bytes(value)
                    try:
                        with self.assertRaises(ValueError) as caught:
                            runner.controls.supported_firmware(env)
                        self.assertNotIsInstance(caught.exception, runner.MissingPrerequisite)
                    finally:
                        path.write_bytes(original)
            variables.unlink()
            with self.assertRaises(runner.MissingPrerequisite):
                runner.controls.supported_firmware(env)

    def test_packaged_receipt_cannot_choose_its_own_firmware_prefix(self):
        oracle = runner.controls.module("bar-provenance")
        prefix = self.home / "package"
        firmware = prefix / "firmware"
        firmware.mkdir(parents=True)
        (firmware / "VERSION").write_text(runner.controls.FIRMWARE_VERSION + "\n")
        files = {
            role: {"path": str(firmware / name)}
            for role, name in (
                ("firmware_code", "OVMF_CODE.fd"),
                ("vars_template", "OVMF_VARS.fd"),
                ("firmware_patch", "policy-three-file.patch"),
            )
        }
        files["firmware_patch"]["sha256"] = oracle.PINS["clean_patch"]
        contents = dict(
            firmware_code=b"x" * 3653632,
            vars_template=b"v" * 540672,
            vars_initial=b"v" * 540672,
            firmware_patch=b"policy",
        )
        receipt = dict(firmware_package=runner.controls.FIRMWARE_VERSION, firmware_source_revision=oracle.REVISION)
        oracle.validate_clean_firmware(receipt, files, contents, str(prefix))
        files["firmware_code"]["path"] = str(self.home / "untrusted-code")
        with self.assertRaisesRegex(ValueError, "path mismatch"):
            oracle.validate_clean_firmware(receipt, files, contents, str(prefix))
        files["firmware_code"]["path"] = str(firmware / "OVMF_CODE.fd")
        contents["vars_initial"] = b"reused"
        with self.assertRaisesRegex(ValueError, "non-pristine"):
            oracle.validate_clean_firmware(receipt, files, contents, str(prefix))

    def test_ivrs_external_coverage_missing_is_blocked_and_malformed_fails(self):
        spec = importlib.util.spec_from_file_location(
            "ivrs_runner_input_controls", ROOT / "scripts/kernel-uefi-ivrs-run.py"
        )
        ivrs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ivrs)
        msix, amdvi = self.home / "msix", self.home / "amdvi"
        trace = SimpleNamespace(
            load_coverage=Mock(return_value={"msix_control": str(msix), "amdvi_control": str(amdvi)}),
            validate_coverage=Mock(),
        )
        env = dict(self.env, AURORA_IVRS_COVERAGE=str(self.coverage_path))
        with (
            patch.object(
                ivrs, "module", side_effect=lambda name: self.provenance if name == "ivrs-provenance" else trace
            ),
            patch.object(
                ivrs.controls, "supported_firmware", return_value=(self.code, self.variables, self.firmware_patch)
            ),
        ):
            for missing in (msix, amdvi):
                with self.subTest(missing=missing), self.assertRaises(runner.MissingPrerequisite):
                    ivrs.prerequisites(env)
                missing.mkdir()
            trace.validate_coverage.side_effect = ValueError("contradictory raw control")
            with self.assertRaisesRegex(ValueError, "Invalid AURORA_IVRS_COVERAGE") as caught:
                ivrs.prerequisites(env)
            self.assertNotIsInstance(caught.exception, runner.MissingPrerequisite)
            trace.load_coverage.side_effect = TypeError("wrong coverage JSON shape")
            with self.assertRaisesRegex(ValueError, "Invalid AURORA_IVRS_COVERAGE"):
                ivrs.prerequisites(env)

    def test_explicit_run_only_uses_selected_image_without_any_build(self):
        self.build.mkdir(parents=True)
        with (
            patch.object(runner.transport, "run_logged", side_effect=AssertionError("unexpected build")),
            patch.object(runner.controls, "generate", side_effect=AssertionError("unexpected setup controls")),
            patch.object(runner, "execute") as execute,
            redirect_stdout(io.StringIO()),
        ):
            runner.run("bar-prepare", self.out, self.build)
        self.assertEqual(execute.call_args.args[3], self.build)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.out / "build.log").exists())

    def test_run_only_rejects_unprepared_coverage_and_wrong_profile(self):
        self.build.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "Wrong prebuilt BAR profile"):
            runner.run("bar-read", self.out, self.build)
        with self.assertRaisesRegex(ValueError, "cannot modify"):
            runner.run("bar-prepare", self.build / "esp" / "run", self.build)
        self.assertFalse((self.build / "esp").exists())
        del os.environ["AURORA_BAR_COVERAGE"]
        with patch.object(runner.controls, "stock_firmware", return_value=self.stock):
            with self.assertRaisesRegex(ValueError, "requires explicit validated"):
                runner.run("bar-prepare", self.out, self.build)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.out.exists())

    def test_ivrs_run_only_extracts_execution_without_ninja(self):
        spec = importlib.util.spec_from_file_location(
            "ivrs_run_only_controls", ROOT / "scripts/kernel-uefi-ivrs-run.py"
        )
        ivrs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ivrs)
        build = self.build.parent / "ivrs-read"
        build.mkdir(parents=True)
        paths = dict(QEMU=self.qemu, QEMU_DATA=self.data, AURORA_IVRS_COVERAGE=self.coverage_path)
        with (
            patch.object(ivrs.transport, "run_logged", side_effect=AssertionError("unexpected build")),
            patch.object(ivrs, "execute") as execute,
        ):
            ivrs.run("ivrs-read", self.out, paths, build)
        self.assertEqual(execute.call_args.args[:4], ("ivrs-read", self.out, paths, build))
        with self.assertRaisesRegex(ValueError, "cannot modify"):
            ivrs.run("ivrs-read", build / "esp" / "run", paths, build)
        self.assertFalse((build / "esp").exists())
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.out / "build.log").exists())

    def test_main_missing_external_paths_and_selected_compiler_are_blocked(self):
        for name in ("QEMU_DATA", "AURORA_BAR_COVERAGE", "AURORA_BAR_FIRMWARE", "AURORAC"):
            with self.subTest(name=name), patch.dict(os.environ, {name: str(self.home / "missing")}):
                self.assert_outcome(self.main_result(), "BLOCKED", name)
                self.assert_no_work()
        for path in (self.code, self.variables, self.firmware_patch):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.unlink()
                try:
                    self.assert_outcome(self.main_result(), "BLOCKED", str(path))
                    self.assert_no_work()
                finally:
                    path.write_bytes(original)

    def test_main_unreadable_external_input_is_blocked(self):
        real_access = os.access

        def readable(path, mode):
            return False if Path(path) == self.code else real_access(path, mode)

        with patch.object(runner.os, "access", side_effect=readable):
            self.assert_outcome(self.main_result(), "BLOCKED", str(self.code))
        self.assert_no_work()
        for operation, target in (
            ("resolve", self.code),
            ("exists", self.code),
            ("is_file", self.code),
            ("is_dir", self.data),
        ):
            original = getattr(Path, operation)

            def probe(path, *args, **kwargs):
                if path == target:
                    raise PermissionError("unreadable external prerequisite " + str(target))
                return original(path, *args, **kwargs)

            with self.subTest(operation=operation), patch.object(Path, operation, probe):
                self.assert_outcome(self.main_result(), "BLOCKED", str(target))
                self.assert_no_work()

    def test_main_missing_coverage_artifacts_are_blocked_but_invalid_coverage_fails(self):
        for error in (FileNotFoundError("missing retained trace"), PermissionError("unreadable retained trace")):
            with self.subTest(error=error), patch.object(self.trace, "load_coverage", side_effect=error):
                self.assert_outcome(self.main_result(), "BLOCKED", str(error))
                self.assert_no_work()
        with patch.dict(self.coverage, {"msix_control": str(self.home / "missing-msix-control")}):
            self.assert_outcome(self.main_result(), "BLOCKED", "MSI-X")
            self.assert_no_work()
        for error in (KeyError("events"), TypeError("wrong coverage type"), ValueError("invalid trace inventory")):
            with self.subTest(error=error), patch.object(self.trace, "load_coverage", side_effect=error):
                self.assert_outcome(self.main_result(), "FAIL", "Invalid AURORA_BAR_COVERAGE")
                self.assert_no_work()
        self.trace.validate_coverage = REAL_TRACE.validate_coverage
        self.assert_outcome(self.main_result(), "FAIL", "Unpinned trace binary")
        self.assert_no_work()

    def test_main_invalid_selectors_controls_and_pins_still_fail(self):
        cases = (
            ("QEMU", str(self.data)),
            ("QEMU", str(self.code)),
            ("QEMU", "invalid,qemu"),
            ("QEMU_DATA", str(self.code)),
            ("AURORA_BAR_COVERAGE", str(self.data)),
            ("AURORA_BAR_FIRMWARE", str(self.code)),
            ("AURORAC", str(self.data)),
            ("KERNEL_TEST_FUTURE", "active"),
        )
        for name, value in cases:
            with self.subTest(name=name), patch.dict(os.environ, {name: value}):
                self.assert_outcome(self.main_result(), "FAIL", name)
                self.assert_no_work()
        comma_directory = self.home / "invalid,data"
        comma_directory.mkdir()
        with patch.dict(os.environ, {"QEMU_DATA": str(comma_directory)}):
            self.assert_outcome(self.main_result(), "FAIL", "commas or line breaks")
            self.assert_no_work()
        self.code.write_bytes(self.code.read_bytes() + b"unreviewed")
        self.assert_outcome(self.main_result(), "FAIL", "Unreviewed clean firmware CODE")
        self.assert_no_work()

    def test_main_build_and_validator_failures_never_report_blocked(self):
        cases = (
            ({"BUILD_STATUS": "79"}, None, "79"),
            ({}, ValueError("serial rejected"), "serial rejected"),
            ({}, OSError("missing generated trace"), "missing generated trace"),
            ({}, subprocess.TimeoutExpired("synthetic qemu", 60), "timed out"),
        )
        for env, error, diagnostic in cases:
            with self.subTest(env=env, error=error), patch.dict(os.environ, env):
                with patch.object(runner, "execute", side_effect=error):
                    self.assert_outcome(self.main_result(), "FAIL", diagnostic)
                self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])
                shutil.rmtree(self.out)
                self.calls.unlink()

    def test_main_existing_output_and_output_creation_error_still_fail(self):
        self.out.mkdir()
        marker = self.out / "keep"
        marker.write_text("retained")
        self.assert_outcome(self.main_result(), "FAIL", "fresh and absent")
        self.assertEqual(marker.read_text(), "retained")
        self.assertFalse(self.calls.exists())
        marker.unlink()
        self.out.rmdir()
        with patch.object(Path, "mkdir", side_effect=PermissionError("output unavailable")):
            self.assert_outcome(self.main_result(), "FAIL", "output unavailable")
        self.assert_no_work()

    def test_main_success_reports_selected_native_profile(self):
        with patch.object(runner, "execute"):
            self.assert_outcome(self.main_result(), "PASS", "actual cold BAR gate")
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])

    def test_hardware_alias_uses_canonical_image_and_original_guest_mode(self):
        build = self.build.parent / "bar-read"
        self.builder.write_text("print(" + repr(str(build)) + ")\n")
        with patch.object(runner, "execute") as execute, redirect_stdout(io.StringIO()):
            runner.run("bar-inherited", self.out)
        self.assertEqual(execute.call_args.args[0], "bar-inherited")
        self.assertEqual(execute.call_args.args[3], build)

    def test_invalid_native_handoff_never_launches_guest(self):
        for selected in ("relative\n", str(self.build) + "\nextra\n", str(self.build.parent / "normal") + "\n"):
            with self.subTest(selected=selected):
                self.builder.write_text("print(" + repr(selected) + ", end='')\n")
                with patch.object(runner, "execute") as execute:
                    with self.assertRaisesRegex(ValueError, "native image"):
                        runner.run("bar-prepare", self.out)
                    execute.assert_not_called()
                shutil.rmtree(self.out)

    def test_missing_or_invalid_supported_firmware_fails_before_work(self):
        del os.environ["AURORA_BAR_FIRMWARE"]
        for error, label in (
            (runner.MissingPrerequisite("missing package"), "BLOCKED"),
            (ValueError("package mismatch"), "FAIL"),
        ):
            with self.subTest(label=label), patch.object(runner.controls, "supported_firmware", side_effect=error):
                self.assert_outcome(self.main_result(), label, str(error))
                self.assert_no_work()

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
        with patch.object(
            runner.controls, "supported_firmware", side_effect=runner.MissingPrerequisite("clean package absent")
        ):
            self.reject("clean package absent")

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

    def test_missing_native_builder_fails_without_guest(self):
        self.builder.unlink()
        with self.assertRaisesRegex(ValueError, "Child exited 2"):
            runner.run("bar-prepare", self.out)
        self.assertFalse(self.calls.exists())
        self.assertFalse((self.out / "restore.log").exists())

    def test_failed_native_build_preserves_failure(self):
        os.environ["BUILD_STATUS"] = "79"
        with patch.object(runner, "execute") as execute:
            with self.assertRaisesRegex(ValueError, "Child exited 79"):
                runner.run("bar-prepare", self.out)
            execute.assert_not_called()
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])
        self.assertFalse((self.out / "restore.log").exists())

    def test_real_sigint_reaps_owned_builder_children(self):
        self.check_real_interruption(signal.SIGINT)

    def test_real_sigterm_reaps_owned_builder_children(self):
        self.check_real_interruption(signal.SIGTERM)

    def check_real_interruption(self, interruption):
        ready = self.home / "child-ready"
        profile = self.home / "profile"
        profile.write_text("normal")
        child = self.home / "delayed-child.py"
        child.write_text(
            "import pathlib, sys, time\n"
            "pathlib.Path(sys.argv[1]).write_text('started')\n"
            "time.sleep(0.6)\n"
            "pathlib.Path(sys.argv[2]).write_text('stale-console')\n"
        )
        self.builder.write_text(
            "import os, subprocess, sys\n"
            "p = subprocess.Popen([sys.executable, os.environ['CHILD'], os.environ['READY'], os.environ['PROFILE']])\n"
            "p.wait()\n"
        )
        script = (
            "import importlib.util, pathlib, sys\n"
            "sys.path.insert(0, str(pathlib.Path(sys.argv[1]).resolve().parent))\n"
            "s=importlib.util.spec_from_file_location('runner',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
            "m.ROOT=pathlib.Path(sys.argv[2])\n"
            "m.preflight=lambda mode, output, env: {'output': output, 'coverage_path': 'already-checked'}\n"
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
            self.assertEqual(profile.read_text(), "normal", "surviving build child wrote after runner exit")
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_validator_failure_preserves_rejection(self):
        with patch.object(runner, "execute", side_effect=ValueError("exact serial rejected")):
            with self.assertRaisesRegex(ValueError, "exact serial rejected"):
                runner.run("bar-prepare", self.out)
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])

    def test_success_builds_once_and_uses_exact_requested_output(self):
        output = io.StringIO()
        with patch.object(runner, "execute") as execute, redirect_stdout(output):
            runner.run("bar-prepare", self.out)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[1]["output"], self.out)
        self.assertEqual(execute.call_args.args[3], self.build)
        self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])
        self.assertIn(str(self.out / "receipt.json"), output.getvalue())
        self.assertIn("actual cold BAR gate", output.getvalue())

    def test_actual_executor_keeps_original_clock_profile_and_mandatory_validators(self):
        build = self.build
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

                def guest(argv, log, **kwargs):
                    log.write_text("synthetic serial\n")
                    (self.out / "trace.log").write_text("synthetic trace\n")
                    (self.out / "firmware.log").write_text("synthetic firmware log\n")
                    return status

                with patch.object(runner.transport, "run_logged", side_effect=guest) as launch:
                    with redirect_stdout(io.StringIO()):
                        runner.execute(mode, config, dict(os.environ), build)
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
                self.assertEqual(launch.call_args.args[1], self.out / "serial.log")
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
                    with (
                        patch.object(runner.transport, "run_logged", side_effect=guest),
                        redirect_stdout(io.StringIO()),
                    ):
                        with self.assertRaisesRegex(ValueError, label):
                            runner.execute(mode, config, dict(os.environ), build)
                    validator.side_effect = None
                self.smoke.validate.reset_mock()
                self.trace.validate_trace.reset_mock()
                self.provenance.validate.reset_mock()
                shutil.rmtree(self.out)

    def prepare_public_make(self):
        shutil.copy2(ROOT / "Makefile", self.repo / "Makefile")
        shutil.copy2(ROOT / "scripts/kernel-run.sh", self.repo / "scripts/kernel-run.sh")
        bin_path = self.home / "bin"
        bin_path.mkdir()
        for name in ("bash", "dirname"):
            (bin_path / name).symlink_to(shutil.which(name, path=os.defpath))
        return bin_path

    def prepare_public_runner(self):
        """Run real Make/main/lifecycle with synthetic validators, images and QEMU."""
        self.public_bin = self.prepare_public_make()
        for name in (
            "kernel-uefi-bar-run.py",
            "qemu_transport.py",
            "kernel_profiles.py",
            "kernel_layout.py",
            "kernel_trace_controls.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, self.repo / "scripts" / name)
        for relative in (
            "kernel/bootstrap-layout-values.inc",
            "kernel/uefi/image-page-policies.inc",
            "kernel/uefi/runtime-fixtures.inc",
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.python_calls = self.home / "python-calls"
        self.main_status = self.home / "main-status"
        python = self.public_bin / "python3"
        python.write_text(
            "#!"
            + sys.executable
            + " -B\n"
            + r"""import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

Path(os.environ["PYTHON_CALLS"]).write_text("runner invoked\n")
sys.argv = sys.argv[1:]
sys.path.insert(0, str(Path(sys.argv[0]).resolve().parent))
spec = importlib.util.spec_from_file_location("public_bar_runner", sys.argv[0])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

def validate(label):
    if os.environ.get("VALIDATOR_FAILURE") == label:
        raise ValueError(label + " rejected")

def smoke(status, serial, mode, metadata):
    if status != 33:
        raise ValueError("Wrong emulator exit status: " + str(status))
    if serial != "synthetic serial\n":
        raise ValueError("Wrong synthetic serial")
    validate("serial")

def trace_result(*args):
    validate("trace")
    return {"synthetic_validation": True}

modules = {
    "bar-trace": SimpleNamespace(
        load_coverage=lambda path: {"synthetic_control": True},
        validate_coverage=lambda coverage: None,
        validate_trace=trace_result,
    ),
    "bar-provenance": SimpleNamespace(
        PINS=SYNTHETIC_PINS,
        REVISION="synthetic firmware revision",
        validate=lambda path: validate("provenance"),
    ),
    "bar-smoke": SimpleNamespace(validate=smoke),
}
runner.module = modules.__getitem__
real_run_logged = runner.transport.run_logged
def synthetic_qemu(argv, log, **kwargs):
    if "--print-image-dir" in argv:
        return real_run_logged(argv, log, **kwargs)
    out = log.parent
    log.write_text("synthetic serial\n")
    (out / "trace.log").write_text("synthetic trace\n")
    (out / "firmware.log").write_text("synthetic firmware\n")
    return 124 if os.environ.get("GUEST_TIMEOUT") else int(os.environ.get("GUEST_STATUS", "33"))

runner.transport.run_logged = synthetic_qemu
status = runner.main()
Path(os.environ["MAIN_STATUS"]).write_text(str(status) + "\n")
sys.exit(status)
""".replace("SYNTHETIC_PINS", repr(self.provenance.PINS))
        )
        python.chmod(0o755)
        self.builder.write_text(
            "#!"
            + sys.executable
            + " -B\n"
            + r"""import os
from pathlib import Path
import sys

def selected_kernel_compiler(build):
    return build / "aurorac"

if __name__ == "__main__":
    mode = sys.argv[sys.argv.index("--profile") + 1]
    with Path(os.environ["CALLS"]).open("a") as calls:
        calls.write(mode + "\n")
    status = int(os.environ.get("BUILD_STATUS", "0"))
    if status:
        sys.exit(status)
    build = Path("build/kernel-images/uefi") / mode
    (build / "esp/EFI/BOOT").mkdir(parents=True)
    (build / "esp/EFI/BOOT/BOOTX64.EFI").write_text("synthetic loader")
    Path("build/aurorac").write_text("synthetic compiler identity")
    for name in ("payload.bin", "payload.elf"):
        (build / name).write_text("synthetic payload")
    (build / "bar-metadata.json").write_text("{}")
    print(build.resolve())
"""
        )

    def public_make_result(self, env=None, receipt=True):
        environment = dict(
            self.env,
            PATH=str(self.public_bin) + os.pathsep + str(self.home),
            PYTHON_CALLS=str(self.python_calls),
            MAIN_STATUS=str(self.main_status),
            PYTHONOPTIMIZE=str(sys.flags.optimize),
        )
        if receipt:
            environment["AURORA_NVME_RECEIPTS"] = str(self.out)
        environment.update(env or {})
        return subprocess.run(
            [shutil.which("make", path=os.defpath), "--no-print-directory", "smoke-nvme-prepare"],
            cwd=self.repo,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_public_make_missing_or_empty_receipt_is_blocked_before_python(self):
        self.prepare_public_runner()
        for env in ({}, {"AURORA_NVME_RECEIPTS": ""}):
            with self.subTest(env=env):
                self.assert_outcome(self.public_make_result(env, receipt=False), "BLOCKED", "AURORA_NVME_RECEIPTS")
                self.assertFalse(self.python_calls.exists())
                self.assertFalse(self.main_status.exists())
                self.assert_no_work()

    def test_public_make_real_runner_prerequisites_block_and_invalid_inputs_fail(self):
        self.prepare_public_runner()
        cases = (
            ({"QEMU": "missing-qemu"}, "BLOCKED", "Missing dependency: missing-qemu"),
            ({"QEMU": str(self.data)}, "FAIL", "QEMU"),
            ({"QEMU": str(self.code)}, "FAIL", "QEMU"),
            ({"AURORA_BAR_COVERAGE": str(self.home / "missing")}, "BLOCKED", "AURORA_BAR_COVERAGE"),
            ({"QEMU_DATA": str(self.code)}, "FAIL", "QEMU_DATA"),
        )
        for env, outcome, diagnostic in cases:
            with self.subTest(env=env):
                self.assert_outcome(self.public_make_result(env), outcome, diagnostic)
                self.assertTrue(self.python_calls.is_file())
                self.assertEqual(self.main_status.read_text(), "2\n")
                self.assert_no_work()
        self.code.write_bytes(self.code.read_bytes() + b"unreviewed")
        self.assert_outcome(self.public_make_result(), "FAIL", "Unreviewed clean firmware CODE")
        self.assert_no_work()

    def test_public_make_real_runner_build_guest_validator_and_success_outcomes(self):
        self.prepare_public_runner()
        cases = (
            ({"BUILD_STATUS": "79"}, "FAIL", "79"),
            ({"GUEST_STATUS": "7"}, "FAIL", "Wrong emulator exit status: 7"),
            ({"GUEST_TIMEOUT": "1"}, "FAIL", "Wrong emulator exit status: 124"),
            ({"VALIDATOR_FAILURE": "serial"}, "FAIL", "serial rejected"),
            ({"VALIDATOR_FAILURE": "trace"}, "FAIL", "trace rejected"),
            ({"VALIDATOR_FAILURE": "provenance"}, "FAIL", "provenance rejected"),
            ({}, "PASS", "actual cold BAR gate"),
        )
        for env, outcome, diagnostic in cases:
            with self.subTest(env=env):
                result = self.public_make_result(env)
                self.assert_outcome(result, outcome, diagnostic)
                self.assertEqual(self.main_status.read_text(), "0\n" if outcome == "PASS" else "2\n")
                self.assertEqual(self.calls.read_text().splitlines(), ["bar-prepare"])
                self.assertTrue((self.out / "build.log").is_file())
                self.assertFalse((self.out / "restore.log").exists())
                if outcome == "PASS":
                    receipt = json.loads((self.out / "receipt.json").read_text())
                    self.assertEqual(receipt["mode"], "bar-prepare")
                    self.assertEqual(receipt["status"], 33)
                    self.assertTrue((self.out / "trace-result.json").is_file())
                shutil.rmtree(self.out)
                shutil.rmtree(self.repo / "build", ignore_errors=True)
                self.calls.unlink()

    def test_public_make_exports_receipt_and_fixture_selectors(self):
        bin_path = self.prepare_public_make()
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

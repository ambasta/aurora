#!/usr/bin/env python3
"""Compiler-free controls for explicitly observed Meson artifact identity."""

import argparse
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compiler_contract as contract
import meson_toolchain
import meson_test


class MesonIdentityTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(compiler_sha256=None, developer_build_receipt=None, meson_selected_compiler=True)
        values.update(changes)
        return argparse.Namespace(**values)

    def test_no_external_pin_or_fresh_build_claim(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            path = Path(tmp) / "fixture"
            path.write_text("synthetic executable bytes; never invoked")
            path.chmod(0o755)
            identity = contract.resolve_identity(self.args(), path, tmp)
            self.assertIsNone(identity.expected)
            self.assertEqual(identity.record()["origin"], "meson-selected-artifact")
            self.assertIsNone(identity.record()["external_expected_sha256"])
            identity.verify()
            path.write_text("changed bytes")
            with self.assertRaises(contract.ContractError):
                identity.verify()

    def test_conflicting_identity_modes_rejected(self):
        with self.assertRaises(contract.ContractError):
            contract.validate_identity_selection(self.args(compiler_sha256="0" * 64))
        with self.assertRaises(contract.ContractError):
            contract.validate_identity_selection(self.args(developer_build_receipt=Path("/not-read")))

    def test_no_legacy_context_bypass(self):
        with patch.dict(os.environ, {"AURORA_TEST_CONTEXT": "/not-read"}):
            with self.assertRaises(contract.ContractError):
                contract.validate_identity_selection(self.args())

    def test_missing_identity_still_rejected(self):
        with self.assertRaises(contract.ContractError):
            contract.validate_identity_selection(self.args(meson_selected_compiler=False))

    def test_toolchain_replacement_rejected(self):
        first = dict(files={"/compiler": "old"}, version="14")
        meson_toolchain.verify(first, first.copy())
        with self.assertRaises(ValueError):
            meson_toolchain.verify(first, dict(files={"/compiler": "new"}, version="14"))

    def test_implicit_search_variables_rejected_before_tool_queries(self):
        for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
            for value in ("", "/one:/two"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}, clear=True),
                    patch.object(meson_toolchain.subprocess, "check_output") as query,
                ):
                    with self.assertRaisesRegex(ValueError, "Unset " + name):
                        meson_toolchain.snapshot(["never-executed"])
                    query.assert_not_called()

    def test_absent_search_variables_bind_policy_and_reject_legacy_record(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            tool = Path(tmp) / "synthetic-tool"
            tool.write_text("compiler-free fingerprint fixture")

            def query(command, **kwargs):
                return {"-dumpfullversion": "14.2.0", "-dumpmachine": "x86_64-linux-gnu"}.get(command[-1], str(tool))

            with (
                patch.object(meson_toolchain.shutil, "which", return_value=str(tool)),
                patch.object(meson_toolchain.subprocess, "check_output", side_effect=query),
            ):
                observed = meson_toolchain.snapshot([str(tool)])
            self.assertEqual(observed["search_policy"], "explicit-meson-flags-v1")
            meson_toolchain.verify(observed, observed.copy())
            legacy = {key: value for key, value in observed.items() if key != "search_policy"}
            with self.assertRaises(ValueError):
                meson_toolchain.verify(legacy, observed)

    def test_direct_meson_guard_rejects_before_creating_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "aurora-toolchain.json"
            argv = ["meson_toolchain.py", "--configure", "--cxx", "never-executed", "--record", str(record)]
            for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
                with (
                    self.subTest(name=name),
                    patch.dict(os.environ, {name: ""}, clear=True),
                    patch.object(sys, "argv", argv),
                    patch.object(meson_toolchain.subprocess, "check_output") as query,
                ):
                    with self.assertRaisesRegex(ValueError, "Unset " + name):
                        meson_toolchain.main()
                    query.assert_not_called()
                    self.assertFalse(record.exists())

    def test_make_convenience_rejects_before_meson_or_build_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
                with (
                    self.subTest(name=name),
                    patch.dict(os.environ, {name: "/one:/two"}, clear=True),
                    patch.object(
                        contract, "tool_record", return_value={"resolved": "/synthetic/compiler", "sha256": "0" * 64}
                    ),
                    patch.object(contract, "query", return_value="14.2.0"),
                    patch.object(meson_test.subprocess, "run") as launch,
                ):
                    with self.assertRaisesRegex(ValueError, "Unset " + name):
                        meson_test.execute(root, "full")
                    launch.assert_not_called()
                    self.assertFalse((root / "build").exists())

    def test_cli_modes_are_exclusive(self):
        parser = argparse.ArgumentParser()
        contract.add_identity_arguments(parser)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--meson-selected-compiler", "--compiler-sha256", "0" * 64])


class MesonEntrypointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.calls = []
        self.identity = dict(files={"/synthetic/g++": "fixture"}, version="14")
        self.failure = None
        self.flags = []
        self.configured_compiler = "/synthetic/g++"
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(contract, "tool_record", side_effect=lambda name: dict(resolved=name, sha256=name)),
            patch.object(contract, "parse_cxx", return_value="/synthetic/g++"),
            patch.object(contract, "query", return_value="14.2.0"),
            patch.object(meson_toolchain, "snapshot", return_value=self.identity),
            patch.object(meson_test.subprocess, "run", side_effect=self.run_command),
            patch.object(meson_test.subprocess, "check_output", side_effect=self.introspect),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["CXX"], "/synthetic/g++")
        if command[1] == self.failure:
            raise subprocess.CalledProcessError(23, command)
        if command[1] == "setup":
            build = Path(command[2])
            self.assertEqual(command[3:], [str(self.root), "--backend=ninja", "-Dlsp=false"])
            (build / "build.ninja").touch()
            (build / "aurora-toolchain.json").write_text(json.dumps(self.identity))
        return subprocess.CompletedProcess(command, 0)

    def introspect(self, command, **kwargs):
        if command[-1] == "--compilers":
            return json.dumps({"build": {"cpp": {"exelist": [self.configured_compiler]}}}).encode()
        self.assertEqual(command[-1], "--buildoptions")
        return json.dumps([{"name": "cpp_args", "value": self.flags}]).encode()

    def test_fresh_default_and_explicit_builds_setup_then_compile_then_full(self):
        for supplied in (None, "build/chosen-gcc", str(self.root / "absolute-gcc")):
            with self.subTest(directory=supplied):
                self.calls.clear()
                if supplied:
                    os.environ["MESON_BUILD_DIR"] = supplied
                meson_test.execute(self.root, "full")
                self.assertEqual([command[1] for command in self.calls], ["setup", "compile", "test"])
                build = Path(self.calls[0][2])
                self.assertEqual(self.calls[1][2:4], ["-C", str(build)])
                self.assertEqual(self.calls[2][2:7], ["-C", str(build), "--suite", "full", "--no-rebuild"])
                if supplied:
                    self.assertEqual(build, (self.root / supplied).resolve())
                else:
                    self.assertEqual(build.parent, self.root / "build")
                    self.assertTrue(build.name.startswith("meson-"))

    def test_incremental_reuse_and_changed_flags_select_separate_default(self):
        meson_test.execute(self.root, "compiler")
        first = self.calls[0][2]
        self.calls.clear()
        meson_test.execute(self.root, "compiler")
        self.assertEqual([command[1] for command in self.calls], ["compile", "test"])
        self.assertEqual(self.calls[0][3], first)
        os.environ["CXXFLAGS"] = "-O1"
        self.flags = ["-O1"]
        self.calls.clear()
        meson_test.execute(self.root, "compiler")
        self.assertEqual(self.calls[0][1], "setup")
        self.assertNotEqual(self.calls[0][2], first)

    def test_setup_compile_and_test_failures_propagate_without_later_steps(self):
        for step, expected in [
            ("setup", ["setup"]),
            ("compile", ["setup", "compile"]),
            ("test", ["setup", "compile", "test"]),
        ]:
            with self.subTest(step=step):
                os.environ["MESON_BUILD_DIR"] = str(self.root / step)
                self.failure = step
                self.calls.clear()
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    meson_test.execute(self.root, "full")
                self.assertEqual(caught.exception.returncode, 23)
                self.assertEqual([command[1] for command in self.calls], expected)

    def test_existing_explicit_build_rejects_different_compiler_or_flags(self):
        os.environ["MESON_BUILD_DIR"] = str(self.root / "configured")
        meson_test.execute(self.root, "full")
        for compiler, flags in [("/different/g++", []), ("/synthetic/g++", ["-O1"])]:
            with self.subTest(compiler=compiler, flags=flags):
                self.calls.clear()
                self.configured_compiler = compiler
                self.flags = flags
                with self.assertRaises(contract.ContractError):
                    meson_test.execute(self.root, "full")
                self.assertEqual(self.calls, [])


class NativeCompilerWrapperTests(unittest.TestCase):
    def test_plain_absolute_and_launcher_compilers_do_not_recurse(self):
        adapter = Path(__file__).resolve().parents[1] / "scripts/meson-native-run.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            compiler = tools / "g++"
            compiler.write_text('#!/bin/sh\nprintf "selected:%s\\n" "$@"\n')
            compiler.chmod(0o755)
            launcher = tools / "launcher"
            launcher.write_text('#!/bin/sh\nexec g++ "$@"\n')
            launcher.chmod(0o755)
            for selection in ("g++", str(compiler), "launcher g++"):
                with self.subTest(selection=selection):
                    env = {**os.environ, "PATH": str(tools)}
                    command = [
                        sys.executable,
                        "-B",
                        str(adapter),
                        "--repo",
                        str(root),
                        "--build-root",
                        str(root / "outputs"),
                        "--cxx",
                        selection,
                        "--",
                        "g++",
                        "argument with spaces",
                        "literal;not-a-command",
                    ]
                    with subprocess.Popen(
                        command,
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        start_new_session=True,
                    ) as process:
                        try:
                            stdout, stderr = process.communicate(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.communicate()
                            self.fail("compiler wrapper recursed or hung")
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn("selected:argument with spaces\n", stdout)
                    self.assertIn("selected:literal;not-a-command\n", stdout)
                    self.assertEqual(list((root / "outputs").iterdir()), [])

    def test_missing_compiler_rejected_before_native_command(self):
        adapter = Path(__file__).resolve().parents[1] / "scripts/meson-native-run.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "ran"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(adapter),
                    "--repo",
                    str(root),
                    "--build-root",
                    str(root / "outputs"),
                    "--cxx",
                    "missing-cxx",
                    "--",
                    sys.executable,
                    "-c",
                    f'open({str(marker)!r}, "w").close()',
                ],
                env={**os.environ, "PATH": str(root)},
                capture_output=True,
                text=True,
                timeout=3,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Configured C++ executable was not found", result.stderr)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

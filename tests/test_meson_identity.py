#!/usr/bin/env python3
"""Compiler-free controls for explicitly observed Meson artifact identity."""

import argparse
import json
from pathlib import Path
import os
import signal
import shutil
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
        values = dict(
            compiler_sha256=None,
            developer_build_receipt=None,
            meson_selected_compiler=True,
        )
        values.update(changes)
        return argparse.Namespace(**values)

    def test_no_external_pin_or_fresh_build_claim(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {}, clear=True),
        ):
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

    def test_implicit_search_variables_rejected_before_tool_queries(self):
        for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
            for value in ("", "/one:/two"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}, clear=True),
                    patch.object(meson_toolchain.subprocess, "check_output") as query,
                ):
                    with self.assertRaisesRegex(ValueError, "Unset " + name):
                        meson_toolchain.explicit_search()
                    query.assert_not_called()

    def test_make_convenience_rejects_before_meson_or_build_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
                with (
                    self.subTest(name=name),
                    patch.dict(os.environ, {name: "/one:/two"}, clear=True),
                    patch.object(
                        contract,
                        "tool_record",
                        return_value={
                            "resolved": "/synthetic/compiler",
                            "sha256": "0" * 64,
                        },
                    ),
                    patch.object(meson_test.shutil, "which", return_value="/synthetic/meson"),
                    patch.object(meson_test.subprocess, "run") as launch,
                ):
                    with self.assertRaisesRegex(contract.ContractError, "Unset " + name):
                        meson_test.execute(root, "full")
                    launch.assert_not_called()
                    self.assertFalse((root / "build").exists())

    def test_missing_meson_cli_reports_recovery_without_creating_build(self):
        entrypoint = Path(__file__).resolve().parents[1] / "scripts/meson_test.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = subprocess.run(
                [sys.executable, "-B", str(entrypoint), "--repo-root", str(root)],
                env={"PATH": str(root)},
                capture_output=True,
                text=True,
                timeout=3,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("BLOCKED: Missing development tool: meson", result.stderr)
            self.assertIn("./scripts/container.sh make test", result.stderr)
            self.assertIn("docs/local-development.md", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(list(root.iterdir()), [])

    def test_cli_modes_are_exclusive(self):
        parser = argparse.ArgumentParser()
        contract.add_identity_arguments(parser)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--meson-selected-compiler", "--compiler-sha256", "0" * 64])


class MesonToolchainDiagnosticTests(unittest.TestCase):
    def test_real_meson_refreshes_old_options_without_wiping_files_or_lock(self):
        meson = shutil.which("meson")
        if meson is None:
            self.skipTest("Meson is required for the language-free reconfiguration fixture")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            (root / "meson.build").write_text("project('old-options-fixture')\n")
            options_file = root / "meson_options.txt"
            options_file.write_text("option('lsp', type: 'boolean', value: false)\n")

            def run(*arguments):
                result = subprocess.run([meson, *map(str, arguments)], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            run("setup", build, root, "--backend=ninja", "-Dlsp=false")
            old = {item["name"] for item in json.loads(run("introspect", build, "--buildoptions"))}
            self.assertTrue({"kernel_compiler", "kernel_images", "uefi_ld"}.isdisjoint(old))
            sentinel = build / "user-notes"
            sentinel.write_text("preserve this user file")
            kept = build / "retained-failure/.keep"
            kept.parent.mkdir()
            kept.write_text("retained failure")
            options_file.write_text((Path(__file__).resolve().parents[1] / "meson_options.txt").read_text())
            with (build / ".aurora-test.lock").open("a") as lock:
                meson_test.fcntl.flock(lock, meson_test.fcntl.LOCK_EX | meson_test.fcntl.LOCK_NB)
                inode = os.fstat(lock.fileno()).st_ino
                run("setup", build, root, "--reconfigure")
                refreshed = {
                    item["name"]: item["value"] for item in json.loads(run("introspect", build, "--buildoptions"))
                }
                self.assertEqual(
                    {name: refreshed[name] for name in ("kernel_compiler", "kernel_images", "uefi_ld")},
                    {"kernel_compiler": "", "kernel_images": True, "uefi_ld": ""},
                )
                run("setup", build, root, "--reconfigure", "-Dkernel_images=false")
                self.assertEqual((build / ".aurora-test.lock").stat().st_ino, inode)
                with (build / ".aurora-test.lock").open("a") as competing:
                    with self.assertRaises(BlockingIOError):
                        meson_test.fcntl.flock(competing, meson_test.fcntl.LOCK_EX | meson_test.fcntl.LOCK_NB)
            options = {item["name"]: item["value"] for item in json.loads(run("introspect", build, "--buildoptions"))}
            self.assertEqual(
                {name: options[name] for name in ("kernel_compiler", "kernel_images", "uefi_ld")},
                {"kernel_compiler": "", "kernel_images": False, "uefi_ld": ""},
            )
            self.assertEqual(sentinel.read_text(), "preserve this user file")
            self.assertEqual(kept.read_text(), "retained failure")

    def test_wrapper_reports_only_blocked_reason_and_route_before_setup(self):
        repo = Path(__file__).resolve().parents[1]
        for failure in ("version", "execution"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tools = root / "tools"
                tools.mkdir()
                for name in ("g++", "gcc", "meson", "ninja", "as", "ld", "nm", "objcopy", "objdump", "readelf"):
                    tool = tools / name
                    tool.write_text(
                        "#!/bin/sh\n"
                        + ("echo unwanted-tool-stderr >&2; exit 7\n" if failure == "execution" else "echo 16.1.0\n")
                    )
                    tool.chmod(0o755)
                result = subprocess.run(
                    [sys.executable, "-B", str(repo / "scripts/meson_test.py"), "--repo-root", str(root)],
                    env={"PATH": str(tools)},
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.splitlines()), 2, result.stderr)
                self.assertTrue(result.stderr.startswith("BLOCKED:"), result.stderr)
                self.assertIn("./scripts/container.sh make test", result.stderr)
                self.assertIn("require 16.2.0, got 16.1.0" if failure == "version" else "Cannot inspect", result.stderr)
                self.assertNotIn("unwanted-tool-stderr", result.stderr)
                self.assertEqual(list(root.iterdir()), [tools])

    def test_setup_reports_exact_version_and_recovery_without_a_compiler(self):
        meson = shutil.which("meson")
        if meson is None:
            self.skipTest("Meson is required for the language-free setup diagnostic fixture")
        repo = Path(__file__).resolve().parents[1]
        source = (repo / "meson.build").read_text()
        # Exercise the actual setup stanza, with no languages or compilation.
        preflight = source[source.index("toolchain_check = run_command(") : source.index("# The JSON dependency")]
        for mode in ("version", "empty-stderr", "supported"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                scripts = root / "scripts"
                scripts.mkdir()
                if mode == "empty-stderr":
                    (scripts / "meson_toolchain.py").write_text("raise SystemExit(7)\n")
                else:
                    shutil.copy2(repo / "scripts/meson_toolchain.py", scripts / "meson_toolchain.py")
                tools = root / "tools"
                tools.mkdir()
                versions = {
                    "g++": "16.1.0" if mode == "version" else "16.2.0",
                    "gcc": "16.2.0",
                    "meson": "1.12.1",
                    "ninja": "1.13.2",
                    **{name: "GNU synthetic " + "2.47" for name in ("as", "ld", "nm", "objcopy", "objdump", "readelf")},
                }
                for name, version in versions.items():
                    tool = tools / name
                    tool.write_text('#!/bin/sh\nprintf "%s\\n" "' + version + '"\n')
                    tool.chmod(0o755)
                # Meson itself is real; only version-inspection tools are synthetic.
                (root / "meson.build").write_text(
                    "project('toolchain-diagnostic')\n"
                    + "python = find_program('"
                    + sys.executable
                    + "')\n"
                    + "oracle_cxx = 'g++'\ntoolchain_args = []\n"
                    + preflight
                )
                env = {
                    key: value for key, value in os.environ.items() if key not in meson_toolchain.IMPLICIT_SEARCH_ENV
                }
                env["PATH"] = (
                    str(tools) + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
                )
                result = subprocess.run(
                    [meson, "setup", str(root / "build"), str(root)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                terminal = result.stdout + result.stderr
                if mode == "supported":
                    self.assertEqual(result.returncode, 0, terminal)
                    self.assertNotIn("BLOCKED:", terminal)
                else:
                    self.assertNotEqual(result.returncode, 0, terminal)
                    self.assertIn("BLOCKED:", terminal)
                    self.assertIn("./scripts/container.sh make test", terminal)
                    self.assertIn("docs/local-development.md", terminal)
                    self.assertIn(
                        "require 16.2.0, got 16.1.0" if mode == "version" else "check failed (exit 7)", terminal
                    )
                    self.assertFalse((root / "build/build.ninja").exists())


class MesonEntrypointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.calls = []
        self.queries = []
        self.failure = None
        self.flags = []
        self.configured_compiler = "/synthetic/g++"
        self.kernel_images = True
        self.kernel_compiler = ""
        self.missing_options = set()
        self.preflight = unittest.mock.Mock()
        for patcher in (
            patch.dict(os.environ, {}, clear=True),
            patch.object(contract, "parse_cxx", return_value="/synthetic/g++"),
            patch.object(
                meson_test.shutil,
                "which",
                side_effect=lambda name: name if name.startswith("/") else "/synthetic/" + name,
            ),
            patch.object(meson_test.subprocess, "run", side_effect=self.run_command),
            patch.object(meson_test.subprocess, "check_output", side_effect=self.introspect),
            patch.object(meson_toolchain, "check", self.preflight),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(command[0], "/synthetic/meson")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["CXX"], "/synthetic/g++")
        if command[1] == self.failure:
            raise subprocess.CalledProcessError(23, command)
        if command[1] == "setup":
            build = Path(command[2])
            if "--reconfigure" in command:
                self.assertEqual(command[3:5], [str(self.root), "--reconfigure"])
                if "kernel_images" in self.missing_options:
                    self.kernel_images = True
                self.missing_options.clear()
                if "-Dkernel_images=false" in command:
                    self.kernel_images = False
                return subprocess.CompletedProcess(command, 0)
            self.assertEqual(command[3:6], [str(self.root), "--backend=ninja", "-Dlsp=false"])
            self.assertIn(command[6], ("-Dkernel_images=true", "-Dkernel_images=false"))
            self.kernel_images = command[6] == "-Dkernel_images=true"
            self.kernel_compiler = command[7].removeprefix("-Dkernel_compiler=")
            (build / "build.ninja").touch()
        return subprocess.CompletedProcess(command, 0)

    def introspect(self, command, **kwargs):
        self.queries.append(command)
        if command[-1] == "--compilers":
            return json.dumps({"build": {"cpp": {"exelist": [self.configured_compiler]}}}).encode()
        self.assertEqual(command[-1], "--buildoptions")
        options = [
            {"name": "cpp_args", "value": self.flags},
            {"name": "kernel_images", "value": self.kernel_images},
            {"name": "kernel_compiler", "value": self.kernel_compiler},
            {"name": "uefi_ld", "value": ""},
        ]
        return json.dumps([item for item in options if item["name"] not in self.missing_options]).encode()

    def test_explicit_stale_build_missing_options_rejects_without_reconfigure_or_work(self):
        os.environ["MESON_BUILD_DIR"] = "build/meson"
        meson_test.execute(self.root, "full")
        for missing in (
            {"kernel_compiler"},
            {"kernel_images"},
            {"uefi_ld"},
            {"cpp_args"},
            {"kernel_compiler", "kernel_images", "uefi_ld", "cpp_args"},
        ):
            with self.subTest(missing=missing):
                self.calls.clear()
                self.queries.clear()
                self.missing_options = missing
                with self.assertRaises(contract.ContractError) as caught:
                    meson_test.execute(self.root, "full")
                self.assertEqual(
                    str(caught.exception),
                    "Missing Meson build options: "
                    + ", ".join(sorted(missing))
                    + "; select a fresh matching MESON_BUILD_DIR",
                )
                self.assertEqual(self.calls, [])
                self.assertEqual([command[-1] for command in self.queries], ["--buildoptions"])

    def test_stale_default_refreshes_only_missing_project_options_under_lock(self):
        for scope in ("full", "compiler"):
            with self.subTest(scope=scope):
                meson_test.execute(self.root, scope)
                build = self.root / "build" / ("meson" if scope == "full" else "meson-compiler")
                sentinel = build / "user-notes"
                sentinel.write_text("keep this")
                lock_inode = (build / ".aurora-test.lock").stat().st_ino
                self.calls.clear()
                self.preflight.reset_mock()
                self.missing_options = {"kernel_compiler", "kernel_images", "uefi_ld"}
                original = self.run_command

                def inspect_lock(command, **kwargs):
                    with (build / ".aurora-test.lock").open("a") as lock:
                        with self.assertRaises(BlockingIOError):
                            meson_test.fcntl.flock(lock, meson_test.fcntl.LOCK_EX | meson_test.fcntl.LOCK_NB)
                    return original(command, **kwargs)

                with patch.object(meson_test.subprocess, "run", side_effect=inspect_lock):
                    meson_test.execute(self.root, scope)
                self.assertEqual(
                    [command[1] for command in self.calls],
                    ["setup"] * (1 if scope == "full" else 2) + ["compile", "test"],
                )
                self.assertEqual(self.calls[0][4:], ["--reconfigure"])
                if scope == "compiler":
                    self.assertEqual(self.calls[1][4:], ["--reconfigure", "-Dkernel_images=false"])
                self.preflight.assert_called_once_with(["/synthetic/g++"], None)
                self.assertEqual(sentinel.read_text(), "keep this")
                self.assertEqual((build / ".aurora-test.lock").stat().st_ino, lock_inode)

    def test_stale_default_does_not_reconfigure_mismatched_compiler_or_flags(self):
        meson_test.execute(self.root, "full")
        self.missing_options = {"kernel_compiler", "kernel_images", "uefi_ld"}
        for compiler, flags in [("/other/g++", []), ("/synthetic/g++", ["-O1"])]:
            with self.subTest(compiler=compiler, flags=flags):
                self.calls.clear()
                self.configured_compiler, self.flags = compiler, flags
                with self.assertRaises(contract.ContractError):
                    meson_test.execute(self.root, "full")
                self.assertEqual(self.calls, [])

    def test_missing_builtin_option_is_not_an_old_project_configuration(self):
        meson_test.execute(self.root, "full")
        self.calls.clear()
        self.missing_options = {"cpp_args"}
        with self.assertRaisesRegex(contract.ContractError, "Missing Meson build options"):
            meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])

    def test_incorrect_reconfigured_options_stop_before_compile(self):
        meson_test.execute(self.root, "full")
        self.calls.clear()
        self.missing_options = {"kernel_images"}

        def wrong_configuration(command, **kwargs):
            result = self.run_command(command, **kwargs)
            self.kernel_images = False
            return result

        with patch.object(meson_test.subprocess, "run", side_effect=wrong_configuration):
            with self.assertRaisesRegex(contract.ContractError, "did not restore requested build options"):
                meson_test.execute(self.root, "full")
        self.assertEqual([command[1] for command in self.calls], ["setup", "setup"])

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
                self.assertEqual(
                    self.calls[2][2:7],
                    ["-C", str(build), "--suite", "full", "--no-rebuild"],
                )
                self.assertIn("--no-rebuild", self.calls[2])
                self.assertIn("--ninja-args=meson-test-prereq", self.calls[1])
                self.assertEqual(self.calls[1][4:6], ["-j", "3"])
                self.assertEqual(self.calls[2][7:9], ["--num-processes", "4"])
                if supplied:
                    self.assertEqual(build, (self.root / supplied).resolve())
                else:
                    self.assertEqual(build.parent, self.root / "build")
                    self.assertEqual(build.name, "meson")

    def test_native_image_build_selects_only_requested_alias(self):
        for profile in ("bios", "uefi"):
            self.calls.clear()
            build = meson_test.execute(self.root, None, ["kernel-" + profile + "-normal"])
            self.assertEqual(self.calls[-1][-1], "kernel-" + profile + "-normal")
            self.assertFalse(any(command[1] == "test" for command in self.calls))
            self.assertEqual(build, Path(self.calls[-1][3]))

    def test_kernel_compiler_switch_requires_matching_configuration_in_both_directions(self):
        external = self.root / "external-compiler"
        external.write_bytes(b"synthetic compiler, never run")
        external.chmod(0o755)
        os.environ["AURORAC"] = str(external)
        meson_test.execute(self.root, None, ["kernel-uefi-normal"])
        self.assertEqual(self.kernel_compiler, str(external))
        self.calls.clear()
        os.environ.pop("AURORAC")
        with self.assertRaisesRegex(contract.ContractError, "AURORAC/native selection"):
            meson_test.execute(self.root, None, ["kernel-bios-normal"])
        self.assertEqual(self.calls, [])
        self.kernel_compiler = ""
        os.environ["AURORAC"] = str(external)
        with self.assertRaisesRegex(contract.ContractError, "AURORAC/native selection"):
            meson_test.execute(self.root, None, ["kernel-uefi-normal"])
        self.assertEqual(self.calls, [])

    def test_disabled_image_request_fails_before_compile(self):
        os.environ["MESON_BUILD_DIR"] = str(self.root / "hosted-only")
        meson_test.execute(self.root, "compiler")
        self.calls.clear()
        with self.assertRaisesRegex(contract.ContractError, "Kernel images disabled"):
            meson_test.execute(self.root, None, ["kernel-bios-normal"])
        self.assertEqual(self.calls, [])

    def test_make_all_compiler_copy_is_regular_and_unchanged_copy_is_stable(self):
        build = self.root / "native"
        build.mkdir()
        compiler = build / "aurorac"
        compiler.write_bytes(b"synthetic compiler; never executed")
        compiler.chmod(0o755)
        (build / "meson-info").mkdir()
        (build / "meson-info/intro-buildoptions.json").write_text(json.dumps([dict(name="kernel_compiler", value="")]))
        meson_test.publish_compatibility_compiler(self.root, build)
        destination = self.root / "build/aurorac"
        self.assertFalse(destination.is_symlink())
        self.assertEqual(destination.read_bytes(), compiler.read_bytes())
        self.assertEqual(destination.stat().st_mode, compiler.stat().st_mode)
        before = destination.stat().st_mtime_ns
        meson_test.publish_compatibility_compiler(self.root, build)
        self.assertEqual(destination.stat().st_mtime_ns, before)
        compiler.write_bytes(b"changed synthetic compiler")
        with patch.object(meson_test.shutil, "copy2", side_effect=OSError("copy fixture")):
            with self.assertRaises(OSError):
                meson_test.publish_compatibility_compiler(self.root, build)
        self.assertEqual(destination.read_bytes(), b"synthetic compiler; never executed")
        self.assertEqual(list(destination.parent.iterdir()), [destination])

    def test_selected_kernel_compiler_uses_configured_path_and_rejects_ambiguous_option(
        self,
    ):
        build = self.root / "native"
        (build / "meson-info").mkdir(parents=True)
        options = build / "meson-info/intro-buildoptions.json"
        selected = self.root / "reviewed-compiler"
        for value, expected in (("", build / "aurorac"), (str(selected), selected)):
            options.write_text(json.dumps([dict(name="kernel_compiler", value=value)]))
            self.assertEqual(meson_test.selected_kernel_compiler(build), expected)
        for values in (
            [],
            [dict(name="kernel_compiler", value="relative/compiler")],
            [dict(name="kernel_compiler", value="")] * 2,
        ):
            options.write_text(json.dumps(values))
            with self.assertRaises(contract.ContractError):
                meson_test.selected_kernel_compiler(build)

    def test_make_all_compiler_copy_rejects_existing_symlink(self):
        directory = self.root / "build"
        directory.mkdir()
        (directory / "aurorac").symlink_to(self.root / "do-not-touch")
        with self.assertRaisesRegex(contract.ContractError, "symlinked compatibility compiler"):
            meson_test.publish_compatibility_compiler(self.root, self.root)

    def test_incremental_reuse_rejects_changed_flags_until_explicit_reconfigure(self):
        meson_test.execute(self.root, "compiler")
        self.assertFalse(self.kernel_images)
        first = self.calls[0][2]
        self.calls.clear()
        meson_test.execute(self.root, "compiler")
        self.assertEqual([command[1] for command in self.calls], ["compile", "test"])
        self.assertEqual(self.calls[0][3], first)
        os.environ["CXXFLAGS"] = "-O1"
        self.calls.clear()
        with self.assertRaisesRegex(contract.ContractError, "Configured cpp_args differ"):
            meson_test.execute(self.root, "compiler")
        self.assertEqual(self.calls, [])
        self.flags = ["-O1"]  # Meson was explicitly reconfigured by the developer.
        meson_test.execute(self.root, "compiler")
        self.assertEqual([command[1] for command in self.calls], ["compile", "test"])
        self.assertEqual(self.calls[0][3], first)
        self.assertEqual(Path(first).name, "meson-compiler")

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
                self.failure = None
                self.calls.clear()
                meson_test.execute(self.root, "full")
                self.assertEqual([command[1] for command in self.calls][-2:], ["compile", "test"])

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

    def test_lock_contention_names_directory_and_retry_succeeds(self):
        build = self.root / "busy-build"
        build.mkdir()
        os.environ["MESON_BUILD_DIR"] = "busy-build"
        with (build / ".aurora-test.lock").open("a") as lock:
            meson_test.fcntl.flock(lock, meson_test.fcntl.LOCK_EX | meson_test.fcntl.LOCK_NB)
            with self.assertRaises(contract.ContractError) as caught:
                meson_test.execute(self.root, "full")
            message = str(caught.exception)
            self.assertIn(str(build.resolve()), message)
            self.assertIn("Wait for its active build/test command to finish", message)
            self.assertIn("MESON_BUILD_DIR", message)
            self.assertEqual(self.calls, [])
            self.assertFalse((build / "build.ninja").exists())
        # The lock file stays in place: contention depends on the held lock.
        self.assertTrue((build / ".aurora-test.lock").exists())
        meson_test.execute(self.root, "full")
        self.assertEqual([command[1] for command in self.calls], ["setup", "compile", "test"])

    def test_other_lock_errors_are_not_reported_as_contention(self):
        with patch.object(meson_test.fcntl, "flock", side_effect=PermissionError("permission fixture")):
            with self.assertRaisesRegex(contract.ContractError, "Cannot lock.*permission fixture.*permissions"):
                meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])

    def test_build_preparation_failure_names_operation_path_and_recovery(self):
        blocked = self.root / "not-a-build-directory"
        blocked.write_text("keep this file")
        os.environ["MESON_BUILD_DIR"] = str(blocked)
        with self.assertRaises(contract.ContractError) as caught:
            meson_test.execute(self.root, "full")
        message = str(caught.exception)
        self.assertIn("Cannot prepare build directory/lock", message)
        self.assertIn(str(blocked), message)
        self.assertIn("writable MESON_BUILD_DIR", message)
        self.assertEqual(blocked.read_text(), "keep this file")
        self.assertEqual(self.calls, [])

    def test_cli_remaining_oserror_names_path_and_recovery(self):
        missing = self.root / "missing-source"
        with patch.object(sys, "argv", ["meson_test.py", "--repo-root", str(missing)]):
            with self.assertRaises(SystemExit) as caught:
                meson_test.main()
        message = str(caught.exception)
        self.assertIn("Meson setup/build/test", message)
        self.assertIn(str(missing), message)
        self.assertIn("path/tool availability and permissions", message)
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
                    env.pop("AURORA_MESON_KEEP_ARTIFACTS", None)
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


class MesonArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scratch = self.root / "build"
        self.scratch.mkdir()
        self.cwd = self.root / "cwd"
        self.cwd.mkdir()
        self.external = self.root / "explicit-artifacts"
        self.external.mkdir()
        self.sibling = self.scratch / "aurora-meson-older"
        self.sibling.mkdir()
        (self.sibling / "evidence").write_text("older evidence")
        self.adapter = Path(__file__).resolve().with_name("meson_artifacts.py")
        self.env = {
            **os.environ,
            "TMPDIR": str(self.scratch),
            "CXX": "chosen-cxx --flag",
        }
        self.env.pop("AURORA_MESON_KEEP_ARTIFACTS", None)

    def run_adapter(self, code=None, *, command=None):
        if command is None:
            command = [sys.executable, "-B", "-c", code, "@ARTIFACTS@"]
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                *(["-O"] if sys.flags.optimize else []),
                str(self.adapter),
                *command,
            ],
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        first = result.stdout.splitlines()[0]
        self.assertTrue(first.startswith("Artifacts: "), result)
        parent = Path(first.removeprefix("Artifacts: "))
        self.assertEqual(parent.parent, self.scratch)
        self.assertNotEqual(parent, self.sibling)
        self.assertEqual((self.sibling / "evidence").read_text(), "older evidence")
        return result, parent

    def test_success_cleans_only_owned_scratch_and_preserves_invocation(self):
        code = (
            "import json, os, sys; from pathlib import Path; "
            "output = Path(sys.argv[1]); absent = not output.exists(); output.mkdir(); "
            "(output / 'generated').write_text('scratch'); "
            "(Path(sys.argv[3]) / 'receipt').write_text('explicit evidence'); "
            "print(json.dumps([absent, os.getcwd(), sys.argv[1:], os.environ['CXX'], os.environ['PATH']])); "
            "print('child stderr', file=sys.stderr)"
        )
        result, parent = self.run_adapter(
            command=[
                sys.executable,
                "-B",
                "-c",
                code,
                "@ARTIFACTS@",
                "--artifacts",
                str(self.external),
                "literal @ARTIFACTS@",
                "a b",
                "",
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout.splitlines()[1])
        self.assertEqual(
            observed,
            [
                True,
                str(self.cwd),
                [
                    str(parent / "output"),
                    "--artifacts",
                    str(self.external),
                    "literal @ARTIFACTS@",
                    "a b",
                    "",
                ],
                self.env["CXX"],
                self.env["PATH"],
            ],
        )
        self.assertEqual(result.stderr, "child stderr\n")
        self.assertEqual(result.stdout.splitlines()[-1], "Removed artifacts: " + str(parent))
        self.assertFalse(parent.exists())
        self.assertEqual((self.external / "receipt").read_text(), "explicit evidence")

    def test_only_explicit_keep_one_retains_success(self):
        for value in ("1", "0", ""):
            with self.subTest(keep=value):
                self.env["AURORA_MESON_KEEP_ARTIFACTS"] = value
                result, parent = self.run_adapter("from pathlib import Path; import sys; Path(sys.argv[1]).mkdir()")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(parent.exists(), value == "1")
                outcome = "Retained" if value == "1" else "Removed"
                self.assertIn(outcome + " artifacts: " + str(parent), result.stdout)

    def test_native_wrapper_retains_output_and_spill_until_complete_success(self):
        native_adapter = Path(__file__).resolve().parents[1] / "scripts/meson-native-run.py"
        compiler = self.root / "compiler"
        build = self.root / "native-build"
        for keep, ending, expected in (
            ("", "sys.exit(0)", 0),
            ("1", "sys.exit(0)", 0),
            ("", "sys.exit(23)", 23),
            ("", "Path(os.environ['AURORAC']).write_text('changed')", 1),
        ):
            with self.subTest(keep=keep, ending=ending):
                compiler.write_text("selected compiler")
                self.env["AURORA_MESON_KEEP_ARTIFACTS"] = keep
                code = (
                    "import json, os, sys, tempfile; from pathlib import Path; "
                    "output = Path(sys.argv[1]); output.relative_to(Path.cwd()); output.mkdir(); "
                    "(output / 'evidence').write_text('native output'); "
                    "spill = Path(tempfile.mkdtemp()); (spill / 'evidence').write_text('native spill'); "
                    "print(json.dumps([str(output), str(spill)]), flush=True); " + ending
                )
                result, parent = self.run_adapter(
                    command=[
                        sys.executable,
                        "-B",
                        str(native_adapter),
                        "--repo",
                        str(self.scratch),
                        "--build-root",
                        str(build),
                        "--cxx",
                        sys.executable,
                        "--compiler",
                        str(compiler),
                        "--",
                        sys.executable,
                        "-B",
                        "-c",
                        code,
                        "@ARTIFACTS@",
                    ]
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                output, spill = map(Path, json.loads(result.stdout.splitlines()[1]))
                self.assertEqual(output, parent / "output")
                self.assertEqual(spill.parent.parent, build)
                retained = expected != 0 or keep == "1"
                self.assertEqual(parent.exists(), retained)
                self.assertEqual(spill.parent.exists(), retained)
                if retained:
                    self.assertEqual((output / "evidence").read_text(), "native output")
                    self.assertEqual((spill / "evidence").read_text(), "native spill")
                if expected == 1:
                    self.assertIn("Meson-selected compiler changed during native gate", result.stderr)

    def test_failure_signal_and_interruption_retain_evidence(self):
        for end, expected in (
            ("sys.exit(23)", 23),
            ("os.kill(os.getpid(), signal.SIGTERM)", 256 - signal.SIGTERM),
            ("os.kill(os.getppid(), signal.SIGINT); time.sleep(30)", None),
        ):
            with self.subTest(end=end):
                result, parent = self.run_adapter(
                    "import os, signal, sys, time; from pathlib import Path; "
                    "output = Path(sys.argv[1]); output.mkdir(); (output / 'evidence').write_text('failure'); " + end
                )
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual((parent / "output/evidence").read_text(), "failure")
                self.assertIn("Retained artifacts: " + str(parent), result.stdout)
                self.assertNotIn("Removed artifacts:", result.stdout)

    def test_launch_error_retains_owned_directory(self):
        result, parent = self.run_adapter(command=[str(self.root / "missing-command"), "@ARTIFACTS@"])
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(parent.is_dir())
        self.assertIn("Retained artifacts: " + str(parent), result.stdout)

    def test_cleanup_error_reports_remaining_scratch_without_failing_success(self):
        result, parent = self.run_adapter(
            "import sys; from pathlib import Path; output = Path(sys.argv[1]); output.mkdir(); "
            "(output / 'evidence').write_text('kept'); parent = output.parent; "
            "parent.rename(parent.with_suffix('.moved')); "
            f"parent.symlink_to({str(self.external)!r}, target_is_directory=True)"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Artifact cleanup incomplete: " + str(parent), result.stderr)
        self.assertNotIn("Removed artifacts:", result.stdout)
        self.assertTrue(parent.is_symlink())
        self.assertTrue(self.external.is_dir())
        self.assertEqual((parent.with_suffix(".moved") / "output/evidence").read_text(), "kept")


if __name__ == "__main__":
    unittest.main()

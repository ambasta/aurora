#!/usr/bin/env python3
"""Compiler-free controls for Meson artifact identity and test execution routing."""

import argparse
import importlib.util
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


class MesonInventoryTests(unittest.TestCase):
    """Independent synthetic registration mutations; no compiler or Meson setup."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("test_inventory", Path(__file__).with_name("test-inventory.py"))
        self.inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.inventory)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.build = self.root / "build"
        self.build.mkdir()
        (self.root / "tests/compiler").mkdir(parents=True)
        for path in (
            "tests/test_artifact_budget.py",
            "tests/kernel-program.cpp",
            "tests/compiler/package_graph.py",
            "tests/compiler/equivalence.py",
        ):
            (self.root / path).write_text("")
        (self.root / "tests/test_artifact_budget.py").write_text(
            '"""equivalence controls; tests/compiler/equivalence.py is a separate gate."""\n'
        )
        self.manifest = dict(
            exceptions={"Requires a separately selected baseline": ["tests/compiler/equivalence.py"]},
            executed={},
            helpers={},
            optional={},
            variants={"package-graph-full": ["tests/compiler/package_graph.py", ["--profile", "full"]]},
        )
        self.tests = [
            self.entry("artifact-budget", "tests/test_artifact_budget.py"),
            dict(
                name="native-kernel-program",
                cmd=[str(self.build / "native-kernel-program")],
                depends=["program@exe"],
                suite=["p:full"],
            ),
            self.entry("package-graph", "tests/compiler/package_graph.py", "--profile", "dev"),
            self.entry("package-graph-full", "tests/compiler/package_graph.py", "--profile", "full"),
        ]
        self.targets = [
            dict(
                id="program@exe",
                filename=[str(self.build / "native-kernel-program")],
                target_sources=[dict(sources=[str(self.root / "tests/kernel-program.cpp")])],
            )
        ]
        self.assertEqual(self.check()["direct"], 3)

    def entry(self, name, source, *arguments):
        return dict(name=name, cmd=["python3", str(self.root / source), *arguments], suite=["p:full"])

    def check(self):
        (self.root / "tests/test-inventory.json").write_text(json.dumps(self.manifest))
        return self.inventory.check(self.root, self.tests, self.targets, self.build)

    def test_equivalence_docstring_does_not_execute_saved_baseline_gate(self):
        self.manifest["exceptions"] = {}
        with self.assertRaisesRegex(ValueError, "no registered execution/helper route:.*equivalence.py"):
            self.check()

    def test_built_fixture_without_registered_test_is_uncovered(self):
        self.tests = [test for test in self.tests if test["name"] != "native-kernel-program"]
        with self.assertRaisesRegex(ValueError, "no registered execution/helper route:.*kernel-program.cpp"):
            self.check()

    def test_full_graph_removal_or_dev_substitution_cannot_borrow_dev_coverage(self):
        original = self.tests[-1]
        mutations = [
            None,
            dict(original, cmd=original["cmd"][:-1] + ["dev"]),
            dict(original, cmd=original["cmd"] + ["--profile", "dev"]),
            dict(original, cmd=original["cmd"] + ["--smoke"]),
        ]
        for changed in mutations:
            with self.subTest(changed=changed):
                self.tests = self.tests[:3] + ([] if changed is None else [changed])
                with self.assertRaisesRegex(ValueError, "semantic variant|duplicate semantic selection"):
                    self.check()

    def test_registered_output_dependency_and_generated_edges_are_followed(self):
        self.tests[1].pop("depends")
        self.assertEqual(self.check()["direct"], 3)
        program = self.targets[0]
        for edge in (dict(depends=["program@exe"]), dict(target_sources=[dict(generated_sources=program["filename"])])):
            with self.subTest(edge=edge):
                self.targets = [program, dict(id="wrapper@exe", filename=[str(self.build / "wrapper")], **edge)]
                self.tests[1]["cmd"] = [str(self.build / "wrapper")]
                self.assertEqual(self.check()["direct"], 3)

    def test_new_source_needs_explicit_edge_and_stale_exception_rejects(self):
        (self.root / "tests/fixture.cpp").write_text("")
        with self.assertRaisesRegex(ValueError, "no registered execution/helper route:.*fixture.cpp"):
            self.check()
        self.manifest["executed"] = {"tests/compiler/package_graph.py": ["tests/fixture.cpp"]}
        self.assertEqual(self.check()["indirect"], 1)
        (self.root / "tests/compiler/equivalence.py").unlink()
        with self.assertRaisesRegex(ValueError, "exceptions no longer exist"):
            self.check()

    def test_optional_lsp_routes_are_separate_and_fail_closed(self):
        self.manifest["optional"] = {
            "lsp": {"lsp-units": "tests/lsp-units.cpp", "lsp-protocol": "tests/lsp-protocol.py"}
        }
        for path in self.manifest["optional"]["lsp"].values():
            (self.root / path).write_text("")
        disabled = self.check()
        self.assertEqual((disabled["direct"], disabled["optional_sources"], disabled["optional_tests"]), (3, 2, 0))
        units = dict(name="lsp-units", cmd=[str(self.build / "lsp-units")], suite=["p:lsp"], depends=["lsp@exe"])
        protocol = dict(self.entry("lsp-protocol", "tests/lsp-protocol.py"), suite=["p:lsp"])
        self.targets.append(
            dict(
                id="lsp@exe",
                filename=[str(self.build / "lsp-units")],
                target_sources=[dict(sources=[str(self.root / "tests/lsp-units.cpp")])],
            )
        )
        full = list(self.tests)
        self.tests = full + [units, protocol]
        enabled = self.check()
        self.assertEqual((enabled["direct"], enabled["optional_sources"], enabled["optional_tests"]), (3, 2, 2))
        for optional, diagnostic in (
            ([units], "incomplete optional suite"),
            ([units, dict(protocol, suite=["p:full"])], "optional test in wrong suite"),
            ([units, dict(protocol, cmd=["python3"])], "missing optional execution route"),
            ([units, protocol, dict(protocol, name="unknown-optional")], "outside the full suite"),
        ):
            with self.subTest(diagnostic=diagnostic):
                self.tests = full + optional
                with self.assertRaisesRegex(ValueError, diagnostic):
                    self.check()

    def test_partial_registration_rejects(self):
        self.tests[0]["suite"] = ["p:dev"]
        with self.assertRaisesRegex(ValueError, "registered tests outside the full suite"):
            self.check()


class MesonIdentityTests(unittest.TestCase):
    def args(self, **changes):
        values = dict(
            compiler_sha256=None,
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
        self.bootstrap_compiler = str(self.root / "reviewed-predecessor")
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

    def configured(self, scope="full", path=None):
        build = path or self.root / "build" / ("meson-compiler" if scope == "compiler" else "meson")
        build.mkdir(parents=True, exist_ok=True)
        (build / "build.ninja").write_text("synthetic configured build; never executed")
        self.kernel_images = scope != "compiler"
        return build

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual(command[0], "/synthetic/meson")
        self.assertTrue(kwargs["check"])
        self.assertEqual(kwargs["env"]["CXX"], "/synthetic/g++")
        if command[1] == self.failure:
            raise subprocess.CalledProcessError(23, command)
        if command[1] == "setup":
            self.bootstrap_compiler = command[-1].removeprefix("-Dbootstrap_compiler=")
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
            {"name": "bootstrap_compiler", "value": self.bootstrap_compiler},
        ]
        return json.dumps([item for item in options if item["name"] not in self.missing_options]).encode()

    def test_unconfigured_directory_rejects_before_artifacts_or_meson(self):
        for scope in ("full", "compiler", None):
            with (
                self.subTest(scope=scope),
                self.assertRaisesRegex(
                    contract.ContractError,
                    "Predecessor-backed Meson setup required.*compiler/README.md#source-bootstrap",
                ),
            ):
                meson_test.execute(self.root, scope)
            self.assertEqual(self.calls, [])
            self.assertEqual(self.queries, [])
            self.assertEqual(list(self.root.iterdir()), [])

    def test_old_default_and_explicit_options_reject_without_reconfiguration(self):
        build = self.configured()
        sentinel = build / "retained-failure"
        sentinel.write_text("keep this evidence")
        for supplied in (None, str(build)):
            if supplied:
                os.environ["MESON_BUILD_DIR"] = supplied
            for missing in (
                {"kernel_compiler"},
                {"cpp_args"},
                {"bootstrap_compiler"},
                {"kernel_images", "uefi_ld"},
            ):
                with self.subTest(supplied=supplied, missing=missing):
                    self.missing_options = missing
                    with self.assertRaisesRegex(contract.ContractError, "Missing Meson build options"):
                        meson_test.execute(self.root, "full")
                    self.assertEqual(self.calls, [])
                    self.assertEqual(sentinel.read_text(), "keep this evidence")

    def test_configured_predecessor_requires_absolute_path(self):
        self.configured()
        for path in ("", "relative/compiler"):
            self.bootstrap_compiler = path
            with self.subTest(path=path), self.assertRaises(contract.ContractError):
                meson_test.execute(self.root, "full")
            self.assertEqual(self.calls, [])

    def test_requested_predecessor_refreshes_only_implicit_default(self):
        build = self.configured()
        sentinel = build / "retained-failure"
        sentinel.write_text("preserve")
        lock = build / ".aurora-test.lock"
        lock.touch()
        inode = lock.stat().st_ino
        self.flags = ["-O2"]
        os.environ["CXXFLAGS"] = "-O2"
        predecessor = self.root / "new predecessor"
        predecessor.write_text("#!/bin/sh\nexit 0\n")
        predecessor.chmod(0o755)
        os.environ["BOOTSTRAP_COMPILER"] = str(predecessor)
        meson_test.execute(self.root, "full")
        self.assertEqual([c[1] for c in self.calls], ["setup", "compile", "test"])
        self.assertEqual(self.calls[0][2:], ["--reconfigure", str(build), "-Dbootstrap_compiler=" + str(predecessor)])
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual(self.flags, ["-O2"])
        self.calls.clear()
        meson_test.execute(self.root, "full")
        self.assertEqual([c[1] for c in self.calls], ["compile", "test"])
        self.calls.clear()
        self.bootstrap_compiler = str(self.root / "old predecessor")
        os.environ["MESON_BUILD_DIR"] = str(build)
        with self.assertRaisesRegex(contract.ContractError, "differs from BOOTSTRAP_COMPILER; run"):
            meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_empty_default_predecessor_refreshes_before_path_validation(self):
        build = self.configured()
        selected = self.root / "new predecessor"
        selected.write_text("#!/bin/sh\nexit 0\n")
        selected.chmod(0o755)
        os.environ["BOOTSTRAP_COMPILER"] = str(selected)
        self.bootstrap_compiler = ""
        meson_test.execute(self.root, "full")
        self.assertEqual([c[1] for c in self.calls], ["setup", "compile", "test"])
        self.assertEqual(self.bootstrap_compiler, str(selected))
        self.calls.clear()
        self.bootstrap_compiler = ""
        os.environ["MESON_BUILD_DIR"] = str(build)
        with self.assertRaisesRegex(contract.ContractError, "differs from BOOTSTRAP_COMPILER; run"):
            meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])

    def test_failed_predecessor_refresh_does_not_compile(self):
        build = self.configured()
        selected = self.root / "new predecessor"
        selected.write_text("#!/bin/sh\nexit 0\n")
        selected.chmod(0o755)
        os.environ["BOOTSTRAP_COMPILER"] = str(selected)
        original = self.bootstrap_compiler
        self.failure = "setup"
        with self.assertRaises(subprocess.CalledProcessError):
            meson_test.execute(self.root, "full")
        self.assertEqual([c[1] for c in self.calls], ["setup"])
        self.assertEqual(self.bootstrap_compiler, original)
        self.assertTrue((build / ".aurora-test.lock").is_file())

    def test_invalid_requested_predecessor_rejects_before_meson(self):
        nonexecutable = self.root / "nonexecutable"
        nonexecutable.write_text("not executable")
        for selected in ("", "relative/compiler", str(self.root), str(self.root / "missing"), str(nonexecutable)):
            os.environ["BOOTSTRAP_COMPILER"] = selected
            with self.subTest(selected=selected), self.assertRaisesRegex(contract.ContractError, "BOOTSTRAP_COMPILER"):
                meson_test.execute(self.root, "full")
            self.assertEqual(self.calls, [])
            self.assertEqual(self.queries, [])

    def test_configured_default_and_explicit_builds_compile_then_full(self):
        for supplied in (None, "build/chosen-gcc", str(self.root / "absolute-gcc")):
            with self.subTest(directory=supplied):
                self.calls.clear()
                if supplied:
                    os.environ["MESON_BUILD_DIR"] = supplied
                build = self.configured(path=self.root / supplied if supplied else None)
                meson_test.execute(self.root, "full")
                self.assertEqual([command[1] for command in self.calls], ["compile", "test"])
                self.assertEqual(self.calls[0][2:6], ["-C", str(build), "-j", "3"])
                self.assertIn("--ninja-args=meson-test-prereq", self.calls[0])
                self.assertEqual(
                    self.calls[1][2:9], ["-C", str(build), "--suite", "full", "--no-rebuild", "--num-processes", "4"]
                )

    def test_build_only_selects_one_existing_target_without_tests(self):
        build = self.configured("compiler")
        for target in ("aurorac", "aurora-fmt"):
            self.calls.clear()
            self.assertEqual(meson_test.execute(self.root, "compiler", [target], build_only=True), build)
            self.assertEqual(self.calls, [["/synthetic/meson", "compile", "-C", str(build), "-j", "3", target]])

    def test_invalid_build_target_rejects_before_artifacts(self):
        for targets, scope in (([], "compiler"), (["aurorac-stage0"], "compiler"), (["aurorac"], "full")):
            with self.subTest(targets=targets, scope=scope), self.assertRaises(contract.ContractError):
                meson_test.execute(self.root, scope, targets, build_only=True)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_native_image_build_selects_only_requested_alias(self):
        build = self.configured()
        for profile in ("bios", "uefi"):
            self.calls.clear()
            self.assertEqual(meson_test.execute(self.root, None, ["kernel-" + profile + "-normal"]), build)
            self.assertEqual(self.calls[-1][-1], "kernel-" + profile + "-normal")
            self.assertEqual([command[1] for command in self.calls], ["compile"])

    def test_kernel_compiler_switch_requires_matching_configuration_in_both_directions(self):
        self.configured()
        external = self.root / "external-compiler"
        external.write_bytes(b"synthetic compiler, never run")
        external.chmod(0o755)
        self.kernel_compiler = str(external)
        os.environ["AURORAC"] = str(external)
        meson_test.execute(self.root, None, ["kernel-uefi-normal"])
        self.calls.clear()
        os.environ.pop("AURORAC")
        with self.assertRaisesRegex(contract.ContractError, "Configured kernel_compiler differs"):
            meson_test.execute(self.root, None, ["kernel-bios-normal"])
        self.kernel_compiler = ""
        os.environ["AURORAC"] = str(external)
        with self.assertRaisesRegex(contract.ContractError, "Configured kernel_compiler differs"):
            meson_test.execute(self.root, None, ["kernel-uefi-normal"])
        self.assertEqual(self.calls, [])

    def test_disabled_image_request_fails_before_compile(self):
        os.environ["MESON_BUILD_DIR"] = str(self.configured("compiler"))
        with self.assertRaisesRegex(contract.ContractError, "Configured kernel_images differs"):
            meson_test.execute(self.root, None, ["kernel-bios-normal"])
        self.assertEqual(self.calls, [])

    def test_kernel_selection_and_ir_flags_do_not_configure_images(self):
        self.configured()
        compiler = self.root / "supervised-compiler"
        compiler.write_text("synthetic compiler; never executed")
        compiler.chmod(0o755)
        self.kernel_compiler = str(compiler)
        os.environ.update(AURORAC=str(compiler), CXXFLAGS="-O0", IR_TEST_CXXFLAGS="-O1")

        def fixed_kernel_flags(command, **kwargs):
            self.assertNotIn("CXXFLAGS", kwargs["env"])
            return self.run_command(command, **kwargs)

        with patch.object(meson_test.subprocess, "run", side_effect=fixed_kernel_flags):
            meson_test.execute(self.root, None, ["kernel-uefi-normal"])
        self.assertEqual(self.flags, [])
        self.assertEqual([command[1] for command in self.calls], ["compile"])

    def test_suites_reject_ir_flags_before_artifacts(self):
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-O0"}), self.assertRaises(contract.ContractError):
            meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "build").exists())

    def test_unsupported_output_and_fixture_controls_are_not_ignored(self):
        for name in ("OUT", "FORMAT_OUT", "LEXER_EVENTS", "UTF8_LINES_ARTIFACT_PARENT", "XFS_ROOT_FIXTURES"):
            for value in ("", "/unexpected"):
                with self.subTest(name=name, value=value), patch.dict(os.environ, {name: value}):
                    with self.assertRaisesRegex(contract.ContractError, name):
                        meson_test.execute(self.root, "compiler", ["aurorac"], build_only=True)
                    self.assertEqual(self.calls, [])
                    self.assertFalse((self.root / "build").exists())

    def test_caps_still_reject_for_kernels_and_suites(self):
        for scope in (None, "full"):
            for name in contract.CAP_CONTROLS:
                with self.subTest(scope=scope, control=name), patch.dict(os.environ, {name: "1024"}):
                    with self.assertRaisesRegex(contract.ContractError, "registered full caps"):
                        meson_test.execute(self.root, scope)
                    self.assertEqual(self.calls, [])
                    self.assertFalse((self.root / "build").exists())

    def test_explicit_linker_mismatch_still_rejects_before_compile(self):
        self.configured()
        os.environ["UEFI_LD"] = "/different/linker"
        with self.assertRaisesRegex(contract.ContractError, "Configured uefi_ld differs.*MESON_BUILD_DIR"):
            meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])

    def test_compatibility_outputs_are_regular_stable_and_atomic_on_failure(self):
        build = self.root / "native"
        build.mkdir()
        for name in ("aurorac", "aurora-fmt"):
            source = build / name
            source.write_bytes(b"synthetic executable; never executed")
            source.chmod(0o755)
            meson_test.publish_compatibility_output(self.root, source, name)
            destination = self.root / "build" / name
            self.assertFalse(destination.is_symlink())
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(destination.stat().st_mode, source.stat().st_mode)
            before = destination.stat().st_mtime_ns
            meson_test.publish_compatibility_output(self.root, source, name)
            self.assertEqual(destination.stat().st_mtime_ns, before)
            source.write_bytes(b"changed synthetic executable")
            with patch.object(meson_test.shutil, "copy2", side_effect=OSError("copy fixture")):
                with self.assertRaises(OSError):
                    meson_test.publish_compatibility_output(self.root, source, name)
            self.assertEqual(destination.read_bytes(), b"synthetic executable; never executed")
        self.assertEqual(sorted(path.name for path in destination.parent.iterdir()), ["aurora-fmt", "aurorac"])

    def test_selected_kernel_compiler_uses_configured_path_and_rejects_ambiguous_option(self):
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

    def test_compatibility_outputs_reject_existing_symlink(self):
        directory = self.root / "build"
        directory.mkdir()
        for name in ("aurorac", "aurora-fmt"):
            (directory / name).symlink_to(self.root / "do-not-touch")
            with self.assertRaisesRegex(contract.ContractError, "symlinked compatibility"):
                meson_test.publish_compatibility_output(self.root, self.root / "missing-source", name)

    def test_incremental_reuse_rejects_changed_flags_until_explicit_reconfigure(self):
        build = self.configured("compiler")
        for _ in range(2):
            self.calls.clear()
            meson_test.execute(self.root, "compiler")
            self.assertEqual([command[1] for command in self.calls], ["compile", "test"])
            self.assertEqual(self.calls[0][3], str(build))
        os.environ["CXXFLAGS"] = "-O1"
        self.calls.clear()
        with self.assertRaisesRegex(contract.ContractError, "Configured cpp_args differ"):
            meson_test.execute(self.root, "compiler")
        self.assertEqual(self.calls, [])
        self.flags = ["-O1"]  # Explicit developer reconfiguration, never changed by the shortcut.
        meson_test.execute(self.root, "compiler")
        self.assertEqual([command[1] for command in self.calls], ["compile", "test"])

    def test_compile_and_test_failures_propagate_without_later_steps(self):
        self.configured()
        for step, expected in [("compile", ["compile"]), ("test", ["compile", "test"])]:
            self.failure = step
            self.calls.clear()
            with self.subTest(step=step), self.assertRaises(subprocess.CalledProcessError) as caught:
                meson_test.execute(self.root, "full")
            self.assertEqual(caught.exception.returncode, 23)
            self.assertEqual([command[1] for command in self.calls], expected)
        self.failure = None
        self.calls.clear()
        meson_test.execute(self.root, "full")
        self.assertEqual([command[1] for command in self.calls], ["compile", "test"])

    def test_existing_explicit_build_rejects_different_compiler_or_flags(self):
        os.environ["MESON_BUILD_DIR"] = str(self.configured(path=self.root / "configured"))
        for compiler, flags in [("/different/g++", []), ("/synthetic/g++", ["-O1"])]:
            self.configured_compiler, self.flags = compiler, flags
            with self.subTest(compiler=compiler, flags=flags), self.assertRaises(contract.ContractError):
                meson_test.execute(self.root, "full")
            self.assertEqual(self.calls, [])

    def test_lock_contention_names_directory_and_retry_preserves_lock(self):
        build = self.configured(path=self.root / "busy-build")
        os.environ["MESON_BUILD_DIR"] = "busy-build"
        with (build / ".aurora-test.lock").open("a") as lock:
            inode = (build / ".aurora-test.lock").stat().st_ino
            meson_test.fcntl.flock(lock, meson_test.fcntl.LOCK_EX | meson_test.fcntl.LOCK_NB)
            with self.assertRaisesRegex(contract.ContractError, "already in use.*busy-build"):
                meson_test.execute(self.root, "full")
            self.assertEqual(self.calls, [])
            self.assertEqual(self.queries, [])
        meson_test.execute(self.root, "full")
        self.assertEqual((build / ".aurora-test.lock").stat().st_ino, inode)
        self.assertEqual([command[1] for command in self.calls], ["compile", "test"])

    def test_other_lock_errors_and_lock_preparation_report_recovery(self):
        build = self.configured()
        with patch.object(meson_test.fcntl, "flock", side_effect=PermissionError("permission fixture")):
            with self.assertRaisesRegex(contract.ContractError, "Cannot lock.*permission fixture.*permissions"):
                meson_test.execute(self.root, "full")
        (build / ".aurora-test.lock").unlink()
        (build / ".aurora-test.lock").mkdir()
        with self.assertRaisesRegex(contract.ContractError, "Cannot prepare build directory/lock.*MESON_BUILD_DIR"):
            meson_test.execute(self.root, "full")
        self.assertEqual(self.calls, [])

    def test_cli_build_selections_and_publication(self):
        build = self.root / "configured"
        for arguments, expected in (
            (["--build-only", "aurorac", "--publish-compiler"], "aurorac"),
            (["--build-only", "aurora-fmt", "--publish-formatter"], "aurora-fmt"),
        ):
            with (
                patch.object(sys, "argv", ["meson_test.py", "--repo-root", str(self.root), *arguments]),
                patch.object(meson_test, "execute", return_value=build) as execute,
                patch.object(meson_test, "publish_compatibility_output") as publish,
            ):
                meson_test.main()
                execute.assert_called_once_with(self.root, "compiler", [expected], build_only=True)
                publish.assert_called_once_with(self.root, build / expected, expected)

    def test_cli_invalid_publication_cannot_build(self):
        for arguments in (
            ["--publish-compiler"],
            ["--publish-formatter"],
            ["--build-only", "aurorac", "--publish-formatter"],
        ):
            with (
                patch.object(sys, "argv", ["meson_test.py", *arguments]),
                patch.object(meson_test, "execute") as execute,
                self.assertRaises(contract.ContractError),
            ):
                meson_test.main()
            execute.assert_not_called()

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

    def test_pin_runner_failure_retains_only_its_fresh_scratch(self):
        compiler = self.root / "failing-cxx"
        compiler.write_text("#!/bin/sh\nprintf 'compiler failed\\n' >&2\nexit 23\n")
        compiler.chmod(0o755)
        script = Path(__file__).resolve().parents[1] / "scripts/kernel-pin-tests.sh"
        result = subprocess.run(
            ["bash", str(script)],
            env={**self.env, "CXX": str(compiler)},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 23, result.stderr)
        parent = Path(result.stdout.splitlines()[0].removeprefix("Artifacts: "))
        self.assertEqual(parent.parent, self.scratch)
        self.assertTrue(parent.is_dir())
        self.assertIn("Retained artifacts: " + str(parent), result.stdout)
        self.assertEqual((self.sibling / "evidence").read_text(), "older evidence")

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

#!/usr/bin/env python3
"""Synthetic tooling controls only: never an Aurora compiler/native acceptance gate."""

from __future__ import annotations
import argparse
import ast
from contextlib import redirect_stdout
import io
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import shlex
import signal
import time
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aurora_test_compiler_contract", ROOT / "scripts/compiler_contract.py")
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-contract-control-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        self.patchenv = patch.dict(os.environ, self.env, clear=True)
        self.patchenv.start()
        self.addCleanup(self.patchenv.stop)
        (self.root / "compiler").mkdir()
        (self.root / "build").mkdir()
        for name in (".gitignore", "AGENTS.md", "Makefile", "README.md"):
            (self.root / name).write_text("synthetic contract control\n")
        (self.root / "compiler/main.cpp").write_text("// synthetic source, never compiled\n")
        self.compiler = self.root / "build/compiler"
        self.compiler.write_text("#!/bin/sh\nexit 0\n")
        self.compiler.chmod(0o555)
        self.tool = self.root / "build/tool"
        self.tool.write_text("synthetic tool identity")
        self.tool.chmod(0o555)
        self.depfile = self.root / "build/compiler.d"
        self.depfile.write_text("aurora-contract: main.cpp\n")
        self.receipt = self.root / "build/receipt.json"
        tool = c.file_record(self.tool)
        self.context = dict(
            schema=c.SCHEMA,
            status="built",
            mode="developer",
            root=str(self.root),
            origin="fresh-source-build",
            source_inputs=c.source_inventory(self.root),
            tools={
                name: tool
                for name in (
                    *c.TOOLS,
                    "python-supervisor",
                    "shell",
                    "cxx",
                    "cxx-cc1plus",
                    "cxx-collect2",
                    "cxx-as",
                    "cxx-ld",
                )
            },
            build_environment={name: os.environ.get(name) for name in c.BUILD_ENV},
            compiler=c.file_record(self.compiler),
            external_expected_sha256=None,
            host_test_flags=c.selected_flag_vectors(os.environ),
            build_returncode=0,
            build_recipe="gnu-cxx-main-v1",
            flags=c.parse_flags(c.DEFAULT_FLAGS),
            build_cwd=str(self.root / "compiler"),
            dependency_file=str(self.depfile),
            header_inputs={str(self.root / "compiler/main.cpp"): c.file_record(self.root / "compiler/main.cpp")},
        )
        self.context["build_command"] = c.build_argv(
            str(self.tool), self.context["flags"], str(self.compiler), str(self.depfile)
        )
        self.write()
        mocked = patch.object(c, "tool_record", return_value=tool)
        mocked.start()
        self.addCleanup(mocked.stop)

    def write(self):
        c.write_json(self.receipt, self.context)

    def checked(self):
        return c.read_context(self.receipt, self.root, self.compiler, developer=True)

    def args(self, **kwargs):
        return argparse.Namespace(compiler_sha256=kwargs.get("pin"), developer_build_receipt=kwargs.get("receipt"))

    def launch(self, goal="test", **kwargs):
        return argparse.Namespace(entry=kwargs.get("entry", "root"), goal=goal, repo_root=self.root)

    def test_valid_synthetic_receipt(self):
        self.assertEqual(self.checked()["origin"], "fresh-source-build")
        identity = c.resolve_identity(self.args(receipt=self.receipt), self.compiler, self.root)
        self.assertEqual(identity.record()["mode"], "developer")
        self.assertIsNone(identity.record()["external_expected_sha256"])
        identity.verify()

    def test_identity_requires_exactly_one(self):
        for args in (self.args(), self.args(pin="0" * 64, receipt=self.receipt)):
            with self.subTest(args=args), self.assertRaises(c.ContractError):
                c.validate_identity_selection(args)
        c.validate_identity_selection(self.args(), preflight=True)

    def test_bad_pin_formats(self):
        for value in ("", "a" * 63, "g" * 64, "A" * 64, "a" * 65, None):
            with self.subTest(value=value), self.assertRaises(c.ContractError):
                c.pin(value)

    def test_explicit_pin_is_distinct(self):
        identity = c.resolve_identity(self.args(pin=c.digest(self.compiler)), self.compiler, self.root)
        self.assertEqual(identity.record()["mode"], "explicit-pin")
        self.assertEqual(identity.expected, c.digest(self.compiler))
        self.assertIsNone(identity.record()["developer_build_receipt"])

    def test_wrong_pin_before_artifacts(self):
        before = set(self.root.rglob("*"))
        with self.assertRaises(c.ContractError):
            c.resolve_identity(self.args(pin="0" * 64), self.compiler, self.root)
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_source_bytes_with_preserved_mtime(self):
        source = self.root / "compiler/main.cpp"
        prior = source.stat()
        source.write_text("// changed source\n")
        os.utime(source, ns=(prior.st_atime_ns, prior.st_mtime_ns))
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_source_input_addition(self):
        (self.root / "compiler/new.hpp").write_text("// newly relevant input\n")
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_source_input_removal(self):
        (self.root / "compiler/main.cpp").unlink()
        with self.assertRaises((c.ContractError, OSError)):
            self.checked()

    def test_newer_stale_executable_rejected(self):
        self.compiler.chmod(0o755)
        self.compiler.write_text("#!/bin/sh\nexit 1\n")
        os.utime(self.compiler, ns=(2_000_000_000_000_000_000,) * 2)
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_same_bytes_replacement_detected(self):
        contents = self.compiler.read_bytes()
        self.compiler.unlink()
        self.compiler.write_bytes(contents)
        self.compiler.chmod(0o555)
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_current_flags_change_rejected(self):
        os.environ["CXXFLAGS"] = "-std=c++23 -O0"
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_build_recipe_change_rejected(self):
        self.context["build_command"].append("-different-recipe")
        self.write()
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_tool_change_rejected(self):
        self.tool.chmod(0o755)
        self.tool.write_text("changed tool")
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_build_environment_change_rejected(self):
        os.environ["CPATH"] = "/different/header/root"
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_wrong_root_rejected(self):
        other = self.root / "other"
        other.mkdir()
        with self.assertRaises(c.ContractError):
            c.read_context(self.receipt, other, self.compiler)

    def test_wrong_output_path_rejected(self):
        other = self.root / "build/other"
        other.write_bytes(self.compiler.read_bytes())
        with self.assertRaises(c.ContractError):
            c.read_context(self.receipt, self.root, other)

    def test_missing_receipt_rejected(self):
        self.receipt.unlink()
        with self.assertRaises(OSError):
            c.resolve_identity(self.args(receipt=self.receipt), self.compiler, self.root)

    def test_missing_success_record_rejected(self):
        for field in (
            "schema",
            "status",
            "build_returncode",
            "build_recipe",
            "build_command",
            "header_inputs",
            "host_test_flags",
        ):
            saved = self.context.pop(field)
            self.write()
            with self.subTest(field=field), self.assertRaises((c.ContractError, KeyError)):
                self.checked()
            self.context[field] = saved
        self.write()

    def test_receipt_modification_during_run(self):
        identity = c.resolve_identity(self.args(receipt=self.receipt), self.compiler, self.root)
        self.context["extra"] = "changed"
        self.write()
        with self.assertRaises(c.ContractError):
            identity.verify()

    def test_developer_cannot_claim_external_pin(self):
        self.context["external_expected_sha256"] = c.digest(self.compiler)
        self.write()
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_acceptance_context_cannot_be_developer_receipt(self):
        self.context["mode"] = "acceptance"
        self.context["external_expected_sha256"] = c.digest(self.compiler)
        self.write()
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_prebuilt_acceptance_is_not_source_build(self):
        self.context.update(
            mode="acceptance",
            origin="externally-pinned-prebuilt",
            external_expected_sha256=c.digest(self.compiler),
            prebuilt_input=c.file_record(self.compiler),
        )
        for field in ("build_command", "build_returncode", "header_inputs", "build_recipe"):
            self.context.pop(field)
        self.write()
        self.assertEqual(c.read_context(self.receipt, self.root)["origin"], "externally-pinned-prebuilt")
        with self.assertRaises(c.ContractError):
            self.checked()

    def test_acceptance_pin_preflight_creates_nothing(self):
        before = set(self.root.rglob("*"))
        for env in (
            {},
            {"ACCEPTANCE_COMPILER_SHA256": ""},
            {"ACCEPTANCE_COMPILER_SHA256": "invalid"},
            {"ACCEPTANCE_COMPILER_SHA256": "0" * 64, "ACCEPTANCE_COMPILER": str(self.compiler)},
        ):
            with self.subTest(env=env), self.assertRaises(c.ContractError):
                c.prepare_controls(self.launch("test-acceptance"), env)
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_empty_prebuilt_selector_rejects_before_queries_and_artifacts(self):
        def artifacts():
            rows = {}
            for path in (self.root, *sorted(self.root.rglob("*"))):
                relative = str(path.relative_to(self.root))
                mode = path.lstat().st_mode & 0o7777
                if path.is_symlink():
                    rows[relative] = ("symlink", mode, os.readlink(path))
                elif path.is_file():
                    rows[relative] = ("file", mode, path.stat().st_size, c.digest(path))
                else:
                    rows[relative] = ("directory", mode)
            return rows

        before = artifacts()
        pin = {"ACCEPTANCE_COMPILER_SHA256": c.digest(self.compiler)}
        routes = (
            ("root", "test", "developer", {}),
            ("root", "test-acceptance", "acceptance", pin),
            ("compiler", "test", "developer", {}),
            ("compiler", "test-short-circuit", "acceptance", pin),
        )
        for entry, goal, mode, controls in routes:
            args = self.launch(goal, entry=entry)
            # Omission still selects the documented fresh-build route.
            selected = c.prepare_controls(args, controls)
            self.assertEqual(selected[0], mode)
            self.assertIsNone(selected[2])
            # Valid nonempty paths retain the existing acceptance-only semantics.
            nonempty = {**controls, "ACCEPTANCE_COMPILER": str(self.compiler)}
            if mode == "acceptance":
                chosen = c.prepare_controls(args, nonempty)
                self.assertEqual(chosen[0], "acceptance")
                self.assertEqual(chosen[2], self.compiler)
            else:
                with self.assertRaisesRegex(c.ContractError, "prebuilt compiler is only valid in acceptance mode"):
                    c.prepare_controls(args, nonempty)
            self.assertEqual(before, artifacts())
            with (
                self.subTest(entry=entry, goal=goal, mode=mode),
                patch.dict(os.environ, {**controls, "ACCEPTANCE_COMPILER": ""}),
                patch.object(c, "tool_record", side_effect=AssertionError("no tool query")) as tool,
                patch.object(c, "query", side_effect=AssertionError("no query")) as query,
                patch.object(c, "capture", side_effect=AssertionError("no command capture")) as capture,
                patch.object(c, "execute", side_effect=AssertionError("no command execution")) as execute,
                patch.object(c, "write_json", side_effect=AssertionError("no artifact write")) as write,
                self.assertRaisesRegex(c.ContractError, "ACCEPTANCE_COMPILER must not be empty"),
            ):
                c.run(args)
            for forbidden in (tool, query, capture, execute, write):
                forbidden.assert_not_called()
            self.assertEqual(before, artifacts())
        self.assertEqual(before, artifacts())

    def test_prebuilt_alias_must_agree(self):
        env = {
            "ACCEPTANCE_COMPILER_SHA256": c.digest(self.compiler),
            "ACCEPTANCE_COMPILER": str(self.compiler),
            "OUT": str(self.compiler),
            "AURORAC": str(self.compiler),
        }
        mode, expected, chosen, full = c.prepare_controls(self.launch("test-acceptance"), env)
        self.assertEqual((mode, expected, chosen, full), ("acceptance", c.digest(self.compiler), self.compiler, True))
        env["AURORAC"] = str(self.root / "wrong")
        with self.assertRaises(c.ContractError):
            c.prepare_controls(self.launch("test-acceptance"), env)

    def test_developer_path_override_rejected(self):
        for selector in c.SELECTORS:
            with self.subTest(selector=selector), self.assertRaises(c.ContractError):
                c.prepare_controls(self.launch(), {selector: str(self.compiler)})

    def test_full_and_acceptance_reject_reduced_flags(self):
        for flag in (
            "--quick",
            "--smoke",
            "--self-test-only",
            "--freeze-reference /tmp/x",
            "--mutations-only",
            "--case-filter x",
            "--random-count 1",
            "--limit 1",
            "--compatibility",
        ):
            for goal, env in (
                ("test", {}),
                ("test-acceptance", {"ACCEPTANCE_COMPILER_SHA256": "0" * 64}),
                ("test-package-identity", {"PACKAGE_IDENTITY_COMPILER_SHA256": "0" * 64}),
            ):
                with self.subTest(flag=flag, goal=goal), self.assertRaises(c.ContractError):
                    c.prepare_controls(self.launch(goal), {**env, "PACKAGE_IDENTITY_TEST_FLAGS": flag})
        self.assertFalse(
            c.prepare_controls(self.launch("test-package-identity"), {"PACKAGE_IDENTITY_TEST_FLAGS": "--quick"})[3]
        )

    def test_skip_and_ignore_make_controls_rejected(self):
        for name in ("MAKEFLAGS", "GNUMAKEFLAGS", "MFLAGS"):
            for flags in ("-n", "-q", "-t", "-i", "--dry-run", "--ignore-errors", "--eval=x", "-f other.mk"):
                with self.subTest(name=name, flags=flags), self.assertRaises(c.ContractError):
                    c.reject_make_controls({name: flags})
        for env in (
            {"MAKEFILES": "other.mk"},
            {"SHELL": "/bin/true"},
            {"MAKE": "/bin/true"},
            {".SHELLFLAGS": "-c true"},
        ):
            with self.subTest(env=env), self.assertRaises(c.ContractError):
                c.reject_make_controls(env)
        c.reject_make_controls({"MAKEFLAGS": "w -j1 -- CXXFLAGS=-std=c++23\\ -O2"})

    def test_opaque_build_inputs_rejected(self):
        for value in (
            "@flags",
            "-fplugin=unknown.so",
            "-specs=unknown",
            "-Wp,@flags",
            "-Wl,@flags",
            "-flto",
            "-fuse-ld=gold",
            "-B/other/bin",
            "-Wa,@flags",
            "-Xassembler flags",
            "-fprofile-use=/profile",
            "-fmodules-ts",
            "-std=c++23 extra.cpp",
            "-o elsewhere",
            "-std=c++23 header.gch",
        ):
            with self.subTest(value=value), self.assertRaises(c.ContractError):
                c.parse_flags(value)
        with self.assertRaises(c.ContractError):
            c.parse_flags("-std=c++23 -include forced.hpp")
        for name in c.OPAQUE_ENV:
            with self.subTest(name=name), self.assertRaises(c.ContractError):
                c.prepare_controls(self.launch(), {name: "opaque"})

    def test_live_frozen_inputs_are_in_inventory(self):
        for relative in (
            "evidence/package-identity/contract-before-implementation.md",
            "evidence/package-graph/oracle/reference-v1/reference.py",
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("live frozen input")
            self.assertIn(relative, c.source_inventory(self.root))

    def test_system_header_dependency_parser(self):
        header = self.root / "system header.hpp"
        header.write_text("// synthetic system header")
        escaped = str(header).replace(" ", "\\ ")
        with patch.object(c, "query", return_value="aurora-contract: main.cpp \\\n " + escaped + "\n"):
            inputs = c.dependency_inputs(str(self.tool), c.parse_flags(c.DEFAULT_FLAGS), self.root / "compiler")
        self.assertIn(str(header), inputs)
        self.assertIn(str(self.root / "compiler/main.cpp"), inputs)
        Path(str(header) + ".gch").write_text("opaque PCH")
        with self.assertRaises(c.ContractError):
            c.reject_pch(inputs)

    def mock_queries(self, argv, cwd):
        if "-dumpmachine" in argv:
            return "x86_64-linux-gnu\n"
        if "-M" in argv:
            return "aurora-contract: main.cpp\n"
        if any(value.startswith("-print-prog-name=") for value in argv):
            return str(self.tool) + "\n"
        return "synthetic tool version\n"

    def simulate(self, goal="test", build_status=0, native_status=0, change=None, produce=True, prebuilt=False):
        calls = []

        def execute(argv, cwd, env, log):
            calls.append((argv, cwd, env))
            work = Path(log).parent
            planned = json.loads((work / "run.json").read_text())
            self.assertIn("source_inputs", planned)
            self.assertIn("tools", planned)
            self.assertIn("selected_controls", planned)
            if Path(log).name == "compiler.log":
                self.assertEqual(planned["build_command"], argv)
                if produce:
                    output = Path(argv[argv.index("-o") + 1])
                    output.write_bytes(self.compiler.read_bytes())
                    Path(argv[argv.index("-MF") + 1]).write_text("aurora-contract: main.cpp\n")
                return build_status
            if change:
                change(env)
            return native_status

        if prebuilt:
            os.environ["ACCEPTANCE_COMPILER"] = str(self.compiler)
            os.environ["ACCEPTANCE_COMPILER_SHA256"] = c.digest(self.compiler)
        version = subprocess.CompletedProcess([], 0, b"", b"gcc version synthetic\n")
        with (
            patch.object(c, "query", side_effect=self.mock_queries),
            patch.object(c, "capture", return_value=version),
            patch.object(c, "execute", side_effect=execute),
        ):
            with redirect_stdout(io.StringIO()):
                c.run(self.launch(goal))
        return calls

    def latest_attempt(self):
        paths = list((self.root / "build").glob("test-contract-*/run.json"))
        self.assertEqual(len(paths), 1)
        return paths[0], json.loads(paths[0].read_text())

    def test_every_subprocess_uses_retained_build_temporary_root(self):
        os.environ.update(TMPDIR="/unrelated-user-tmp", TMP="/other-tmp", TEMP="/another-tmp")
        calls = self.simulate()
        path, record = self.latest_attempt()
        expected = str(path.parent / "tmp")
        self.assertTrue(Path(expected).is_dir())
        for _, _, env in calls:
            for name in ("TMPDIR", "TMP", "TEMP"):
                self.assertEqual(env[name], expected)

    def test_failed_build_preserves_plan(self):
        with self.assertRaises(c.ContractError):
            self.simulate(build_status=7)
        path, record = self.latest_attempt()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["build_returncode"], 7)
        self.assertFalse(record["native_complete"])
        self.assertTrue(record["source_inputs"])
        self.assertTrue(record["tools"])
        self.assertTrue(record["header_inputs"])
        self.assertEqual(record["build_cwd"], str(self.root / "compiler"))
        self.assertFalse((path.parent / "compiler-context.json").exists())

    def test_success_without_compiler_is_failure(self):
        with self.assertRaises(c.ContractError):
            self.simulate(produce=False)
        path, record = self.latest_attempt()
        self.assertEqual(record["status"], "failed")
        self.assertFalse((path.parent / "compiler-context.json").exists())

    def test_fresh_acceptance_mismatch_never_starts_tests(self):
        os.environ["ACCEPTANCE_COMPILER_SHA256"] = "0" * 64
        with self.assertRaises(c.ContractError):
            self.simulate("test-acceptance")
        path, record = self.latest_attempt()
        self.assertIn("observed_compiler", record)
        self.assertNotIn("make_command", record)
        self.assertFalse((path.parent / "compiler-context.json").exists())

    def test_known_failing_native_stage_stays_failed(self):
        with self.assertRaises(c.ContractError):
            self.simulate(native_status=9)
        path, record = self.latest_attempt()
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["make_returncode"], 9)
        self.assertFalse(record["native_complete"])

    def test_changed_output_during_native_stage_fails(self):
        def change(env):
            path = Path(env["AURORA_TEST_COMPILER"])
            path.chmod(0o755)
            path.write_text("replaced bytes")

        with self.assertRaises(c.ContractError):
            self.simulate(change=change)
        self.assertFalse(self.latest_attempt()[1]["native_complete"])

    def test_interrupted_attempt_is_terminal_failed(self):
        def change(env):
            raise c.RunInterrupted(signal.SIGTERM)

        with self.assertRaises(c.RunInterrupted):
            self.simulate(change=change)
        record = self.latest_attempt()[1]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["interrupted_by_signal"], signal.SIGTERM)
        self.assertFalse(record["native_complete"])
        self.assertIn("finished_ns", record)

    def test_mocked_success_records_mode_and_scope(self):
        # Deliberately mocked commands test receipt logic, not compiler behavior.
        self.simulate("test-package-identity")
        record = self.latest_attempt()[1]
        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["mode"], "developer")
        self.assertEqual(record["scope"], "focused")
        self.assertFalse(record["native_complete"])

    def test_prebuilt_acceptance_does_not_build(self):
        original = c.file_record(self.compiler)
        calls = self.simulate("test-acceptance", prebuilt=True)
        path, record = self.latest_attempt()
        context = json.loads((path.parent / "compiler-context.json").read_text())
        self.assertEqual(len(calls), 1)
        self.assertEqual(context["origin"], "externally-pinned-prebuilt")
        self.assertNotIn("build_returncode", context)
        self.assertEqual(context["compiler"]["sha256"], c.digest(self.compiler))
        self.assertEqual(c.file_record(self.compiler), original)
        self.assertEqual(context["compiler"]["mode"], 0o555)

    def test_nested_future_source_does_not_rebuild_compiler(self):
        # Make -n executes no compiler/native recipe; the source has a future mtime.
        copied = self.root / "compiler/Makefile"
        shutil.copyfile(ROOT / "compiler/Makefile", copied)
        os.utime(self.root / "compiler/main.cpp", ns=(2_000_000_000_000_000_000,) * 2)
        env = {
            **self.env,
            "AURORA_TEST_CONTEXT": str(self.receipt),
            "AURORA_TEST_COMPILER": str(self.compiler),
            "AURORA_TEST_MODE": "developer",
            "AURORA_TEST_IDENTITY_ARGS": "--developer-build-receipt " + str(self.receipt),
            "OUT": str(self.compiler),
            "AURORAC": str(self.compiler),
        }
        result = subprocess.run(
            [shutil.which("make"), "-n", "all"],
            cwd=copied.parent,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout.decode())
        self.assertIn("compiler_contract.py check", result.stdout.decode())
        self.assertNotIn("main.cpp -o", result.stdout.decode())

    def test_sigterm_cleans_owned_child_and_grandchild(self):
        ready = self.root / "build/ready.json"
        sleeper = self.root / "build/sleeper.py"
        sleeper.write_text(
            "import json,os,subprocess,sys,time\n"
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)'],"
            "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n"
            "open(sys.argv[1],'w').write(json.dumps([os.getpid(),p.pid]))\ntime.sleep(120)\n"
        )
        supervisor = self.root / "build/supervisor.py"
        supervisor.write_text(
            "import importlib.util,sys,json\n"
            "s=importlib.util.spec_from_file_location('contract',sys.argv[1]);c=importlib.util.module_from_spec(s);"
            "sys.modules[s.name]=c;s.loader.exec_module(c)\n"
            "try:\n with c.interrupt_handlers(): c.execute([sys.executable,sys.argv[2],sys.argv[3]],"
            "sys.argv[4],dict(__import__('os').environ),sys.argv[5])\n"
            "except c.RunInterrupted as e:\n open(sys.argv[6],'w').write("
            "json.dumps({'status':'failed','signal':e.number}));"
            "sys.exit(128+e.number)\n"
        )
        terminal = self.root / "build/terminal.json"
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(supervisor),
                str(ROOT / "scripts/compiler_contract.py"),
                str(sleeper),
                str(ready),
                str(self.root),
                str(self.root / "build/process.log"),
                str(terminal),
            ],
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        pids = []
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            pids = json.loads(ready.read_text())
            process.send_signal(signal.SIGTERM)
            out, err = process.communicate(timeout=7)
            self.assertEqual(process.returncode, 128 + signal.SIGTERM, err.decode())
            self.assertEqual(json.loads(terminal.read_text())["status"], "failed")
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                live = [
                    pid
                    for pid in pids
                    if Path("/proc/" + str(pid) + "/stat").exists()
                    and Path("/proc/" + str(pid) + "/stat").read_text().split(") ", 1)[1].split()[0] != "Z"
                ]
                if not live:
                    break
                time.sleep(0.02)
            self.assertFalse(live, "owned child/grandchild remained running")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_every_pin_aware_make_call_receives_identity(self):
        runners = (
            "package_identity.py",
            "package_manifest.py",
            "package_graph.py",
            "kernel-budget-native.py",
            "utf8_range.py",
            "utf8_lines.py",
            "xfs_root.py",
            "xfs_root_api.py",
            "xfs_geometry.py",
            "verify_native.py",
        )
        found = set()
        for path in (ROOT / "Makefile", ROOT / "compiler/Makefile"):
            for line in path.read_text().splitlines():
                if not line.startswith("\t"):
                    continue
                for runner in runners:
                    if runner in line and "python3" in line:
                        found.add(runner)
                        self.assertIn("$(AURORA_TEST_IDENTITY_ARGS)", line, line)
        self.assertEqual(found, set(runners))

    def test_native_runner_identity_rejections_precede_artifacts(self):
        output = self.root / "build/forbidden-artifacts"
        specs = [
            ("tests/compiler/package_identity.py", [str(self.compiler)]),
            ("tests/compiler/package_manifest.py", [str(self.compiler)]),
            ("tests/compiler/package_graph.py", [str(self.compiler)]),
            ("tests/compiler/xfs_geometry.py", [str(self.compiler)]),
            ("tests/compiler/utf8_range.py", ["--compiler", str(self.compiler), "--artifacts", str(output)]),
            ("tests/compiler/utf8_lines.py", ["--compiler", str(self.compiler), "--artifacts", str(output)]),
            ("tests/kernel-budget-native.py", ["--compiler", str(self.compiler)]),
            ("tests/kernel-round-robin-native.py", ["--compiler", str(self.compiler), "--output", str(output)]),
            ("tests/kernel-ipc-transition-native.py", ["--compiler", str(self.compiler), "--output", str(output)]),
            ("fixtures/xfs-offline/verify_native.py", ["--compiler", str(self.compiler)]),
        ]
        for name in ("tests/compiler/xfs_root.py", "tests/compiler/xfs_root_api.py"):
            specs.append(
                (
                    name,
                    [
                        "--repo-root",
                        str(ROOT),
                        "--fixture-root",
                        str(ROOT / "fixtures/xfs-root"),
                        "--artifact-root",
                        str(output),
                        "--compiler",
                        str(self.compiler),
                    ],
                )
            )
        before = {str(p) for p in (ROOT / "build").rglob("*")} if (ROOT / "build").exists() else set()
        for name, args in specs:
            for identity in (
                [],
                ["--compiler-sha256", "bad"],
                ["--compiler-sha256", "0" * 64, "--developer-build-receipt", str(self.receipt)],
            ):
                with self.subTest(runner=name, identity=identity):
                    command = (
                        [sys.executable, "-B"]
                        + (["-O"] if not __debug__ else [])
                        + [str(ROOT / name), *args, *identity]
                    )
                    result = subprocess.run(
                        command, cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout.decode())
                    self.assertFalse(output.exists())
        after = {str(p) for p in (ROOT / "build").rglob("*")} if (ROOT / "build").exists() else set()
        self.assertEqual(before, after)

    def test_six_integrated_cap_consumers_configuration_only(self):
        # Name all five PR26 consumers and the IPC consumer; never filter missing inputs.
        consumers = (
            ("tests/compiler/package_identity.py", "PACKAGE_IDENTITY", 128),
            ("tests/compiler/package_manifest.py", "PACKAGE_MANIFEST", 256),
            ("tests/compiler/package_graph.py", "PACKAGE_GRAPH", 256),
            ("tests/kernel-budget-native.py", "KERNEL_BUDGET", 128),
            ("tests/kernel-round-robin-native.py", "ROUND_ROBIN_TEST", 128),
            ("tests/kernel-ipc-transition-native.py", "IPC_TRANSACTION", 128),
        )
        before = {str(p) for p in (ROOT / "build").rglob("*")} if (ROOT / "build").exists() else set()
        makefile = (ROOT / "Makefile").read_text()
        for name, family, focused in consumers:
            self.assertTrue((ROOT / name).is_file(), "missing required integrated cap consumer")
            self.assertIn("test: " + family + "_CAP_MIB = 1024", makefile)
            self.assertIn(family + "_CAP_MIB ?= " + str(focused), makefile)
            selected = (
                ["--compiler", "/nonexistent/compiler"]
                if family in ("KERNEL_BUDGET", "ROUND_ROBIN_TEST", "IPC_TRANSACTION")
                else ["/nonexistent/compiler"]
            )
            for cap in (focused, 513, 1024, focused - 1, 1025):
                command = (
                    [sys.executable, "-B"]
                    + (["-O"] if not __debug__ else [])
                    + [str(ROOT / name), *selected, "--check-cap-only", "--candidate-cap-mib", str(cap)]
                )
                result = subprocess.run(
                    command, cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10
                )
                if cap < focused or cap > 1024:
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0, result.stdout.decode())
                    receipt = json.loads(result.stdout)
                    self.assertEqual(receipt["status"], "configuration-only")
                    self.assertIs(receipt["native_executed"], False)
                    self.assertEqual(receipt["focused_default_mib"], focused)
                    self.assertEqual(receipt["candidate_cap_mib"], cap)
                    self.assertEqual(receipt["cap_bytes"], cap << 20)
                    self.assertEqual(receipt["maximum_cap_mib"], 1024)
        after = {str(p) for p in (ROOT / "build").rglob("*")} if (ROOT / "build").exists() else set()
        self.assertEqual(before, after)

    def test_cap_controls_match_all_six_integrated_bounds(self):
        self.assertEqual(
            c.CAP_CONTROLS,
            {
                "PACKAGE_IDENTITY_CAP_MIB": (128, 1024),
                "PACKAGE_MANIFEST_CAP_MIB": (256, 1024),
                "PACKAGE_GRAPH_CAP_MIB": (256, 1024),
                "KERNEL_BUDGET_CAP_MIB": (128, 1024),
                "ROUND_ROBIN_TEST_CAP_MIB": (128, 1024),
                "IPC_TRANSACTION_CAP_MIB": (128, 1024),
            },
        )
        c.validate_cap_controls({})
        for name, (minimum, maximum) in c.CAP_CONTROLS.items():
            for value in (str(minimum), "513", str(maximum)):
                c.validate_cap_controls({name: value})
            for value in (
                "",
                " ",
                "\t",
                "\n",
                str(minimum - 1),
                "1025",
                "-1",
                "+128",
                "128.0",
                "128 --check-cap-only",
                "1024 --self-test-only",
                "128 invalid",
                "128 unexpected",
                "128\n--check-cap-only",
                "128\t--check-cap-only",
                " 128",
                "128 ",
                "$UNEXPANDED",
                "${UNEXPANDED}",
                "1" * 5000,
                None,
                True,
                128,
            ):
                for goal in ("test", "test-round-robin", "test-ipc-transaction", "test-acceptance"):
                    env = {name: value}
                    if goal == "test-acceptance":
                        env["ACCEPTANCE_COMPILER_SHA256"] = "0" * 64
                    with self.subTest(name=name, value=str(value)[:50], goal=goal), self.assertRaises(c.ContractError):
                        c.prepare_controls(self.launch(goal), env)

    def test_mocked_full_cap_overrides_preserve_complete_requested_goal(self):
        # Command execution is mocked: this checks routing, not native coverage.
        with patch.dict(os.environ, {name: "1024" for name in c.CAP_CONTROLS}):
            calls = self.simulate()
        record = self.latest_attempt()[1]
        self.assertEqual(len(calls), 2)
        self.assertEqual(record["make_command"][1:4], ["--no-print-directory", "-j1", "test"])
        self.assertEqual(set(record["make_command"][4:]), {name + "=1024" for name in c.CAP_CONTROLS})
        self.assertFalse(any("--check-cap-only" in argument for argument in record["make_command"]))
        self.assertEqual(record["scope"], "native-aggregate")
        for name in c.CAP_CONTROLS:
            self.assertEqual(record["selected_controls"][name], "1024")

    def test_cap_controls_reject_before_artifacts_or_execution(self):
        # Pure Python pre-dispatch coverage. This does not run Make or reproduce
        # the retired end-to-end executable-expression observation.
        def artifacts():
            rows = {}
            for path in (self.root, *sorted(self.root.rglob("*"))):
                relative = str(path.relative_to(self.root))
                mode = path.lstat().st_mode & 0o7777
                if path.is_symlink():
                    rows[relative] = ("symlink", mode, os.readlink(path))
                elif path.is_file():
                    rows[relative] = ("file", mode, path.stat().st_size, c.digest(path))
                else:
                    rows[relative] = ("directory", mode)
            return rows

        before = artifacts()
        pinned = {"ACCEPTANCE_COMPILER_SHA256": c.digest(self.compiler), "ACCEPTANCE_COMPILER": str(self.compiler)}
        routes = (
            ("root", "test", "developer", {}),
            ("root", "test-acceptance", "acceptance", pinned),
            ("compiler", "test", "developer", {}),
            ("compiler", "test-short-circuit", "acceptance", pinned),
        )
        for entry, goal, mode, controls in routes:
            self.assertEqual(c.prepare_controls(self.launch(goal, entry=entry), controls)[0], mode)
            for name, (minimum, maximum) in c.CAP_CONTROLS.items():
                values = (
                    "",
                    str(minimum - 1),
                    str(maximum + 1),
                    "128 --check-cap-only",
                    "1024 --self-test-only",
                    "128 trailing",
                    "128,256",
                    " 128",
                    "128\n--check-cap-only",
                    "$UNEXPANDED",
                    "$(UNEXPANDED)",
                )
                for value in values:
                    with (
                        self.subTest(entry=entry, goal=goal, mode=mode, name=name, value=value),
                        patch.dict(os.environ, {**controls, name: value}),
                        patch.object(c, "tool_record", side_effect=AssertionError("no tool query")) as tool,
                        patch.object(c, "query", side_effect=AssertionError("no query")) as query,
                        patch.object(c, "capture", side_effect=AssertionError("no command capture")) as capture,
                        patch.object(c, "execute", side_effect=AssertionError("no command execution")) as execute,
                        patch.object(c, "write_json", side_effect=AssertionError("no artifact write")) as write,
                        self.assertRaises(c.ContractError),
                    ):
                        c.run(self.launch(goal, entry=entry))
                    for forbidden in (tool, query, capture, execute, write):
                        forbidden.assert_not_called()
                    self.assertEqual(before, artifacts())
        self.assertEqual(before, artifacts())

    def test_make_cap_ranges_reject_before_build_dispatch(self):
        before = set((ROOT / "build").rglob("*")) if (ROOT / "build").exists() else set()
        for directory, goal in (("", "test"), ("compiler", "test")):
            for name, (minimum, maximum) in c.CAP_CONTROLS.items():
                for value in (str(minimum - 1), str(maximum + 1)):
                    for location in ("environment", "command-line"):
                        env = dict(self.env)
                        argv = [shutil.which("make"), goal]
                        if location == "environment":
                            env[name] = value
                        else:
                            argv.append(name + "=" + value)
                        result = subprocess.run(
                            argv, cwd=ROOT / directory, env=env, capture_output=True, text=True, timeout=10
                        )
                        self.assertNotEqual(result.returncode, 0, result.stdout)
                        self.assertIn(name + " must be between", result.stderr)
        after = set((ROOT / "build").rglob("*")) if (ROOT / "build").exists() else set()
        self.assertEqual(before, after)

    def test_make_cap_operands_are_quoted_and_defaults_preserved(self):
        text = (ROOT / "Makefile").read_text()
        for name, (minimum, maximum) in c.CAP_CONTROLS.items():
            self.assertIn(name + " ?= " + str(minimum), text)
            self.assertIn("test: " + name + " = " + str(maximum), text)
            if name in ("ROUND_ROBIN_TEST_CAP_MIB", "IPC_TRANSACTION_CAP_MIB"):
                script = (
                    "kernel-round-robin-tests.sh"
                    if name == "ROUND_ROBIN_TEST_CAP_MIB"
                    else "kernel-ipc-transaction-tests.sh"
                )
                self.assertIn(name + '="$(' + name + ')"', text)
                self.assertIn('--candidate-cap-mib "${' + name + ':-128}"', (ROOT / "scripts" / script).read_text())
            else:
                self.assertIn('--candidate-cap-mib "$(' + name + ')"', text)

    def test_pr26_xfs_temp_root_control_preserved(self):
        spec = importlib.util.spec_from_file_location(
            "synthetic_xfs_temp_policy", ROOT / "fixtures/xfs-offline/verify_native.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with redirect_stdout(io.StringIO()) as output:
            module.transport_self_tests((ROOT / "fixtures/xfs-offline/superblock-v5-512.hex").read_bytes())
        self.assertIn("native workspace honors caller-selected tempfile root", output.getvalue())

    def test_flag_policy_preserves_supported_parsed_vectors(self):
        value = "-std=c++23 -O2 -g3 -Wall -Wextra -Werror=conversion -DCOUNT=7 -D WORD=token -U DROP"
        expected = [
            "-std=c++23",
            "-O2",
            "-g3",
            "-Wall",
            "-Wextra",
            "-Werror=conversion",
            "-DCOUNT=7",
            "-D",
            "WORD=token",
            "-U",
            "DROP",
        ]
        self.assertEqual(c.parse_flags(value), expected)
        self.assertEqual(c.parse_flags(shlex.join(expected)), expected)
        self.assertEqual(c.parse_flags(c.DEFAULT_FLAGS), shlex.split(c.DEFAULT_FLAGS))
        self.assertEqual(c.parse_flags("-DHEX=0xF0u -DNEG=-1 -UNAME"), ["-DHEX=0xF0u", "-DNEG=-1", "-UNAME"])

    def test_flag_policy_rejects_unsupported_raw_and_operand_forms(self):
        values = (
            "",
            " ",
            "-O2\n-g",
            "-O2\r-g",
            "-O2\t-g",
            "-DVALUE=$UNEXPANDED",
            "-DVALUE=${UNEXPANDED}",
            "-DVALUE=$(UNEXPANDED)",
            "-DVALUE=`inert`",
            "-DVALUE=one\\ two",
            "@ordinary-response",
            "-O2;inert",
            "-O2|inert",
            "-DNAME=hello.world",
            "-DNAME=",
            "-DNAME=two words",
            "'-DNAME=two words'",
            "-D NAME(x)",
            "-D 7NAME",
            "-U NAME=1",
            "-I -O2",
            "-I @headers",
            "-include header.hpp.gch",
            "-include header.pch",
            '-I " path"',
            '-I "path "',
            '-I "path:opaque"',
            "-Wopaque-warning",
            "-Wl,-rpath,dir",
            "-Wp,opaque",
            "-Wa,opaque",
            "-fplugin=opaque",
            "-specs=opaque",
            "-O2 " * 257,
            "-I" + "a" * 1024,
            "x" * 16385,
            "-I",
            "-D",
            "-U",
            None,
        )
        for name in ("CXXFLAGS", "IR_TEST_CXXFLAGS"):
            for value in values:
                with self.subTest(name=name, value=str(value)[:50]), self.assertRaises(c.ContractError):
                    c.parse_flags(value, name)

    def test_both_flag_vectors_have_omission_not_empty_defaults(self):
        vectors = c.selected_flag_vectors({})
        self.assertEqual(vectors["CXXFLAGS"], shlex.split(c.DEFAULT_FLAGS))
        self.assertEqual(vectors["IR_TEST_CXXFLAGS"], vectors["CXXFLAGS"])
        self.assertEqual(
            c.selected_flag_vectors({"CXXFLAGS": "-std=c++23 -O1"})["IR_TEST_CXXFLAGS"], ["-std=c++23", "-O1"]
        )
        for name in ("CXXFLAGS", "IR_TEST_CXXFLAGS"):
            with self.subTest(name=name), self.assertRaises(c.ContractError):
                c.selected_flag_vectors({name: ""})

    def test_flag_rejections_precede_artifacts_and_tool_queries(self):
        before = set(self.root.rglob("*"))
        for name in ("CXXFLAGS", "IR_TEST_CXXFLAGS"):
            for value in ("", "-DVALUE=$UNEXPANDED", "-O2\n-g", "-include -O2", "-DVALUE=`inert`"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}),
                    patch.object(c, "tool_record", side_effect=AssertionError("no tool query")) as tool,
                    patch.object(c, "execute", side_effect=AssertionError("no command")) as execute,
                    self.assertRaises(c.ContractError),
                ):
                    c.run(self.launch())
                tool.assert_not_called()
                execute.assert_not_called()
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_both_flag_vectors_are_canonical_in_forwarding_and_receipts(self):
        raw_build = '-std=c++23  -O2 "-DCOUNT=7" -D WORD=token'
        raw_ir = "-std=c++23 -O1 -g '-DTRACE=1' -U DROP"
        expected = {"CXXFLAGS": shlex.split(raw_build), "IR_TEST_CXXFLAGS": shlex.split(raw_ir)}
        with patch.dict(os.environ, {"CXXFLAGS": raw_build, "IR_TEST_CXXFLAGS": raw_ir}):
            calls = self.simulate("test-round-robin")
        path, record = self.latest_attempt()
        context = json.loads((path.parent / "compiler-context.json").read_text())
        self.assertEqual(record["host_test_flags"], expected)
        self.assertEqual(context["host_test_flags"], expected)
        self.assertEqual(record["flags"], expected["CXXFLAGS"])
        build_argv = calls[0][0]
        self.assertEqual(build_argv[1 : build_argv.index("-MD")], expected["CXXFLAGS"])
        for name, vector in expected.items():
            self.assertEqual(calls[1][2][name], shlex.join(vector))
            self.assertEqual(shlex.split(calls[1][2][name]), vector)
        self.assertEqual(record["selected_controls"]["IR_TEST_CXXFLAGS"], raw_ir)

    def test_ir_receipt_vector_mismatch_or_omission_rejects(self):
        for vectors in (
            {"CXXFLAGS": c.parse_flags(c.DEFAULT_FLAGS)},
            {"CXXFLAGS": c.parse_flags(c.DEFAULT_FLAGS), "IR_TEST_CXXFLAGS": ["-O0"]},
            None,
        ):
            self.context["host_test_flags"] = vectors
            self.write()
            with self.subTest(vectors=vectors), self.assertRaises(c.ContractError):
                self.checked()
        self.context["host_test_flags"] = c.selected_flag_vectors({})
        self.write()
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-O0"}), self.assertRaises(c.ContractError):
            self.checked()

    def test_prebuilt_receipt_records_host_vectors_without_fresh_build_claim(self):
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-std=c++23 -O0 -g"}):
            calls = self.simulate("test-acceptance", prebuilt=True)
        path, record = self.latest_attempt()
        context = json.loads((path.parent / "compiler-context.json").read_text())
        self.assertEqual(len(calls), 1)
        self.assertEqual(context["origin"], "externally-pinned-prebuilt")
        self.assertNotIn("build_returncode", context)
        self.assertNotIn("build_command", context)
        self.assertEqual(context["host_test_flags"]["IR_TEST_CXXFLAGS"], ["-std=c++23", "-O0", "-g"])
        self.assertEqual(record["host_test_flags"], context["host_test_flags"])
        self.assertEqual(shlex.split(calls[0][2]["IR_TEST_CXXFLAGS"]), context["host_test_flags"]["IR_TEST_CXXFLAGS"])
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-std=c++23 -O0 -g"}):
            self.assertEqual(
                c.read_context(path.parent / "compiler-context.json", self.root)["origin"], "externally-pinned-prebuilt"
            )
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-O1"}), self.assertRaises(c.ContractError):
            c.read_context(path.parent / "compiler-context.json", self.root)

    def test_safe_public_make_dry_runs_reject_inert_raw_flag_syntax(self):
        # Only inert variable references/malformed data; no executable Make
        # expressions, commands, sentinel creation or old review replay.
        for directory in ("", "compiler"):
            for name in ("CXXFLAGS", "IR_TEST_CXXFLAGS", "CXX"):
                for value in ("$UNEXPANDED", "$(UNEXPANDED)", "`inert`", "first\nsecond"):
                    for location in ("environment", "command-line"):
                        env = dict(self.env)
                        argv = [shutil.which("make"), "-n", "test"]
                        if location == "environment":
                            env[name] = value
                        else:
                            argv.append(name + "=" + value)
                        with self.subTest(directory=directory, name=name, location=location, value=value):
                            result = subprocess.run(
                                argv, cwd=ROOT / directory, env=env, capture_output=True, text=True, timeout=10
                            )
                            self.assertNotEqual(result.returncode, 0, result.stdout)
                            self.assertIn("unsupported raw flag syntax in controls:", result.stderr)
                            self.assertNotIn(value, result.stderr)
                            self.assertNotIn("compiler_contract.py run", result.stdout)

    def test_safe_public_make_dry_runs_preserve_canonical_flag_arguments(self):
        build = ["-std=c++23", "-O2", "-D", "WORD=token", "-DCOUNT=7"]
        ir = ["-std=c++23", "-O1", "-DTRACE=1", "-U", "DROP"]
        env = {
            **self.env,
            "CXX": "g++",
            "CXXFLAGS": shlex.join(build),
            "IR_TEST_CXXFLAGS": shlex.join(ir),
            "AURORA_TEST_CONTEXT": str(self.receipt),
            "AURORA_TEST_COMPILER": str(self.compiler),
            "AURORA_TEST_MODE": "developer",
            "AURORA_TEST_IDENTITY_ARGS": "--developer-build-receipt " + str(self.receipt),
            "OUT": str(self.compiler),
            "AURORAC": str(self.compiler),
        }
        for goal, suffix, expected in (
            ("test-initialization-facts", "initialization_facts.cpp", build),
            ("test-short-circuit", "short_circuit_ir.cpp", ir),
        ):
            result = subprocess.run(
                [shutil.which("make"), "-n", goal],
                cwd=ROOT / "compiler",
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            line = next(line for line in result.stdout.splitlines() if suffix in line and line.startswith("g++ "))
            argv = shlex.split(line.rstrip().removesuffix("\\").strip())
            self.assertEqual(argv[1 : argv.index("-I.")], expected)

    def test_supervised_header_option_forms_reject_in_both_vectors(self):
        forms = (
            "-I",
            "-I.",
            "-I../include",
            "-I include",
            '-I "include path"',
            "-isystem include",
            "-isysteminclude",
            "-isystem=include",
            "-iquote include",
            "-iquoteinclude",
            "-iquote=include",
            "-idirafter include",
            "-idirafterinclude",
            "-idirafter=include",
            "-include forced.hpp",
            "-includeforced.hpp",
            "-include=forced.hpp",
            "-imacros macros.hpp",
            "-imacrosmacros.hpp",
            "-imacros=macros.hpp",
            "-include-pch cached.pch",
        )
        for name in ("CXXFLAGS", "IR_TEST_CXXFLAGS"):
            for value in forms:
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaisesRegex(c.ContractError, "header/search/forced-header"),
                ):
                    c.parse_flags("-std=c++23 " + value, name)
            for value in (
                "-iprefix include",
                "-iwithprefix include",
                "-isysroot sysroot",
                "--sysroot=sysroot",
                "-fpch-preprocess",
                "-fpch-deps",
                "-fpreprocessed",
                "@header-flags",
            ):
                with self.subTest(name=name, value=value), self.assertRaises(c.ContractError):
                    c.parse_flags("-std=c++23 " + value, name)

    def test_header_option_rejection_precedes_tools_and_artifacts_in_all_modes(self):
        before = set(self.root.rglob("*"))
        cases = (
            "-Iinclude",
            "-I include",
            "-isystem include",
            "-iquote include",
            "-idirafter include",
            "-include forced.hpp",
            "-imacros macros.hpp",
        )
        for goal, extra in (
            ("test", {}),
            (
                "test-acceptance",
                {"ACCEPTANCE_COMPILER_SHA256": c.digest(self.compiler), "ACCEPTANCE_COMPILER": str(self.compiler)},
            ),
        ):
            for name in ("CXXFLAGS", "IR_TEST_CXXFLAGS"):
                for value in cases:
                    with (
                        self.subTest(goal=goal, name=name, value=value),
                        patch.dict(os.environ, {**extra, name: "-std=c++23 " + value}),
                        patch.object(c, "tool_record", side_effect=AssertionError("no tool query")) as tool,
                        patch.object(c, "query", side_effect=AssertionError("no subprocess query")) as query,
                        patch.object(c, "execute", side_effect=AssertionError("no execution")) as execute,
                        self.assertRaisesRegex(c.ContractError, "header/search/forced-header"),
                    ):
                        c.run(self.launch(goal))
                    tool.assert_not_called()
                    query.assert_not_called()
                    execute.assert_not_called()
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_header_rejection_keeps_default_release_and_recorded_vectors(self):
        expected = shlex.split(c.DEFAULT_FLAGS)
        self.assertEqual(c.selected_flag_vectors({}), {"CXXFLAGS": expected, "IR_TEST_CXXFLAGS": expected})
        explicit = {
            "CXXFLAGS": "-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror",
            "IR_TEST_CXXFLAGS": "-std=c++23 -O1 -g -DTRACE=1 -U DROP",
        }
        parsed = c.selected_flag_vectors(explicit)
        for name, value in explicit.items():
            self.assertEqual(parsed[name], shlex.split(value))
            self.assertEqual(c.parse_flags(shlex.join(parsed[name]), name), parsed[name])
        # Recipe-owned includes are immutable source inputs, not admitted user
        # flags. This check reads the Makefile; it never invokes Make.
        self.assertIn(
            "$(CXX) $(CXXFLAGS) -I. ../tests/compiler/initialization_facts.cpp",
            (ROOT / "compiler/Makefile").read_text(),
        )
        self.assertIn(
            "$(CXX) $(IR_TEST_CXXFLAGS) -I. ../tests/compiler/short_circuit_ir.cpp",
            (ROOT / "compiler/Makefile").read_text(),
        )

    def test_cxx_omission_and_empty_are_distinct_before_tools(self):
        before = set(self.root.rglob("*"))
        self.assertEqual(c.prepare_controls(self.launch(), {})[0], "developer")
        for name in ("CXX", "CXXFLAGS", "IR_TEST_CXXFLAGS"):
            with (
                self.subTest(name=name),
                patch.dict(os.environ, {name: ""}),
                patch.object(c, "tool_record", side_effect=AssertionError("no tool query")) as tool,
                self.assertRaises(c.ContractError),
            ):
                c.run(self.launch())
            tool.assert_not_called()
        self.assertEqual(before, set(self.root.rglob("*")))

    def test_simple_cxx_policy_retains_distribution_symlink_identity(self):
        for name in (
            "g++",
            "g++-14",
            "x86_64-linux-gnu-g++-14",
            "x86_64-pc-linux-gnu-g++",
            "/usr/x86_64-pc-linux-gnu/gcc-bin/16.2.1/g++",
        ):
            self.assertEqual(c.parse_cxx(name), name)
        link = self.root / "build/vendor-g++"
        link.symlink_to(self.tool)
        self.assertEqual(c.parse_cxx(str(link)), str(link))
        self.assertEqual(c.file_record(link)["resolved"], str(self.tool))
        for value in ("", "g++ -O2", "tool path/g++", "$UNEXPANDED", "g++\nother", "`inert`", "wrapper@g++"):
            with self.subTest(value=value), self.assertRaises(c.ContractError):
                c.parse_cxx(value)

    def test_pr26_consuming_targets_use_shared_fresh_route(self):
        for directory, targets in (
            (
                "",
                (
                    "test-round-robin",
                    "test-ipc-transaction",
                    "test-uefi-ipc",
                    "test-uefi-budget",
                    "test-uefi-dispatch",
                    "test-uefi-user-phases",
                    "test-client-disposal",
                    "test-terminal-event",
                    "test-graphical-console",
                    "test-kernel",
                    "test-division",
                    "test-uefi-runtime",
                ),
            ),
            ("compiler", ("test-short-circuit",)),
        ):
            for target in targets:
                with self.subTest(target=target):
                    result = subprocess.run(
                        [shutil.which("make"), "-n", target],
                        cwd=ROOT / directory,
                        env=self.env,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("compiler_contract.py run", result.stdout)
                    self.assertIn('--goal "' + target + '"', result.stdout)
                    self.assertNotIn("g++", result.stdout)
                    self.assertNotIn("kernel-round-robin-native.py", result.stdout)
        root_make = (ROOT / "Makefile").read_text()
        compiler_make = (ROOT / "compiler/Makefile").read_text()
        self.assertRegex(root_make, r"(?m)^test:[^\n]*\btest-round-robin(?:[ \t]|$)")
        self.assertIn("test: test-native-cap-contracts", root_make)
        self.assertIn("test: test-short-circuit", compiler_make)
        self.assertIn("ROUND_ROBIN_TEST_CAP_MIB", c.FORWARDED)
        self.assertIn("IPC_TRANSACTION_CAP_MIB", c.FORWARDED)
        self.assertIn("IPC_TRANSACTION_COMPILER", c.SELECTORS)
        self.assertIn("IPC_TRANSACTION_COMPILER_SHA256", c.PINS)
        self.assertIn("test: test-ipc-transaction", root_make)
        self.assertIn("test: test-client-disposal", root_make)
        self.assertIn("tests/kernel-client-disposal-native.py --compiler", root_make)
        context_targets = set()
        for line in root_make.replace("\\\n", " ").splitlines():
            targets, separator, prerequisite = line.partition(":")
            if separator and prerequisite.strip() == "aurora-test-context":
                context_targets.update(targets.split())
        self.assertTrue(
            {
                "test-ipc-transaction",
                "test-client-disposal",
                "test-graphical-console",
                "test-graphical-paging",
                "test-graphical-controls",
                "test-native-cap-contracts",
                "test-emulator-clock",
                "run",
                "run-uefi",
                "kernel-uefi",
                "test-developer-commands",
            }
            <= context_targets
        )

    def test_six_consumer_driver_is_not_filtered(self):
        spec = importlib.util.spec_from_file_location("synthetic_cap_driver", ROOT / "tests/native-cap-contracts.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            module.CONSUMERS,
            (
                ("tests/compiler/package_identity.py", 128, False),
                ("tests/compiler/package_manifest.py", 256, False),
                ("tests/compiler/package_graph.py", 256, False),
                ("tests/kernel-budget-native.py", 128, True),
                ("tests/kernel-round-robin-native.py", 128, True),
                ("tests/kernel-ipc-transition-native.py", 128, True),
            ),
        )

    def shell_preserves_one_identity_pair(self, script, runner, cap_control):
        scripts = self.root / "scripts"
        scripts.mkdir()
        wrapper = scripts / script
        shutil.copyfile(ROOT / "scripts" / script, wrapper)
        bindir = self.root / "fake-bin"
        bindir.mkdir()
        log = self.root / "build/shell-argv.json"
        python = bindir / "python3"
        python.write_text(
            "#!" + sys.executable + "\nimport json,os,sys\n"
            'open(os.environ["CONTROL_LOG"],"w").write(json.dumps(sys.argv[1:]))\nsys.exit(91)\n'
        )
        python.chmod(0o755)
        env = {
            **self.env,
            "PATH": str(bindir) + ":" + self.env["PATH"],
            "CONTROL_LOG": str(log),
            "AURORAC": str(self.root / "selected compiler; literal"),
            cap_control: "513",
        }
        for mode, value in (
            ("--compiler-sha256", "a" * 64),
            ("--developer-build-receipt", str(self.root / "receipt with spaces; $(false).json")),
        ):
            result = subprocess.run(["/bin/bash", str(wrapper), mode, value], env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 91, result.stderr.decode())
            self.assertEqual(
                json.loads(log.read_text()),
                ["-B", "-O", runner, "--compiler", env["AURORAC"], mode, value, "--candidate-cap-mib", "513"],
            )
            log.unlink()
        for args in (
            [],
            ["--compiler-sha256"],
            ["--bogus", "x"],
            ["--compiler-sha256", "a" * 64, "--developer-build-receipt", str(self.receipt)],
        ):
            result = subprocess.run(["/bin/bash", str(wrapper), *args], env=env, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(log.exists())
        env.pop("AURORAC")
        result = subprocess.run(
            ["/bin/bash", str(wrapper), "--compiler-sha256", "a" * 64], env=env, capture_output=True, timeout=10
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(log.exists())
        text = wrapper.read_text()
        self.assertNotIn("eval", text)
        self.assertNotIn("sha256sum", text)
        self.assertNotIn("make -C compiler", text)

    def test_round_robin_shell_preserves_one_identity_pair(self):
        self.shell_preserves_one_identity_pair(
            "kernel-round-robin-tests.sh", "tests/kernel-round-robin-native.py", "ROUND_ROBIN_TEST_CAP_MIB"
        )

    def test_ipc_shell_preserves_one_identity_pair(self):
        self.shell_preserves_one_identity_pair(
            "kernel-ipc-transaction-tests.sh", "tests/kernel-ipc-transition-native.py", "IPC_TRANSACTION_CAP_MIB"
        )

    def test_ipc_real_policy_linkage_is_retained(self):
        # Source composition only. Actual linked/native observations remain
        # separate gates; these checks prevent accidentally restoring old stubs.
        for name in (
            "kernel-uefi-ipc-tests.sh",
            "kernel-uefi-budget-tests.sh",
            "kernel-uefi-dispatch-tests.sh",
            "kernel-uefi-user-phases-tests.sh",
        ):
            text = (ROOT / "scripts" / name).read_text()
            self.assertIn('compiler="${AURORAC:-build/aurorac}"', text)
            self.assertIn('if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi', text)
            self.assertIn('"$compiler" --module-root kernel/policies examples/kernel.au', text)
        text = (ROOT / "scripts/kernel-round-robin-tests.sh").read_text()
        self.assertIn('"$compiler" --module-root kernel/policies examples/kernel.au', text)
        self.assertIn("--redefine-sym aurora_kernel_round_robin_next=aurora_kernel_round_robin_next_real", text)
        self.assertIn("tests/kernel-round-robin-adapter.cpp build/uefi/round-robin-adapter-substitute.o", text)
        ipc = (ROOT / "tests/kernel-ipc-transition-native.py").read_text()
        statements = [ast.dump(node, include_attributes=False) for node in ast.walk(ast.parse(ipc))]
        expected_statements = (
            "old, new = 'aurora_kernel_ipc_transition', 'aurora_kernel_ipc_transition_real'",
            "need(after == renamed, 'Only IPC producer may be renamed; "
            "round-robin and all other symbols must remain genuine')",
        )
        for statement in expected_statements:
            expected = ast.dump(ast.parse(statement).body[0], include_attributes=False)
            self.assertIn(expected, statements)
        for name in ("Makefile", "compiler/Makefile"):
            text = (ROOT / name).read_text()
            controls = text[text.index("override _AURORA_USER_CONTROLS :=") : text.index("# Raw user flags")]
            for control in ("IPC_TRANSACTION_COMPILER", "IPC_TRANSACTION_COMPILER_SHA256", "IPC_TRANSACTION_CAP_MIB"):
                self.assertIn(control, controls)
            raw_caps = next(line for line in text.splitlines() if line.startswith("override _AURORA_CAP_CONTROLS :="))
            self.assertIn("IPC_TRANSACTION_CAP_MIB", raw_caps)
        root = (ROOT / "Makefile").read_text()
        self.assertIn("KERNEL_BUDGET_COMPILER IPC_TRANSACTION_COMPILER", root)
        self.assertIn("./scripts/kernel-ipc-transaction-tests.sh $(AURORA_TEST_IDENTITY_ARGS)", root)

    def test_ipc_family_alias_and_pin_use_existing_selection_policy(self):
        expected = c.digest(self.compiler)
        for entry in ("root", "compiler"):
            for goal in ("test", "test-ipc-transaction"):
                # Existing family aliases treat an empty value as omission.
                mode, _, selected, _ = c.prepare_controls(
                    self.launch(goal, entry=entry), {"IPC_TRANSACTION_COMPILER": ""}
                )
                self.assertEqual(mode, "developer")
                self.assertIsNone(selected)
            pinned = {
                "ACCEPTANCE_COMPILER": str(self.compiler),
                "ACCEPTANCE_COMPILER_SHA256": expected,
                "IPC_TRANSACTION_COMPILER": str(self.compiler),
                "IPC_TRANSACTION_COMPILER_SHA256": expected,
            }
            mode, observed, selected, _ = c.prepare_controls(self.launch("test-ipc-transaction", entry=entry), pinned)
            self.assertEqual((mode, observed, selected), ("acceptance", expected, self.compiler))
            for changed in (
                {"IPC_TRANSACTION_COMPILER": str(self.root / "wrong")},
                {"IPC_TRANSACTION_COMPILER_SHA256": "0" * 64},
            ):
                with self.subTest(entry=entry, changed=changed), self.assertRaises(c.ContractError):
                    c.prepare_controls(self.launch("test-ipc-transaction", entry=entry), {**pinned, **changed})
        mode, observed, selected, full = c.prepare_controls(
            self.launch("test-ipc-transaction"), {"IPC_TRANSACTION_COMPILER_SHA256": expected}
        )
        self.assertEqual((mode, observed, selected, full), ("acceptance", expected, None, False))

    def ipc_adapter(self, fail_final=False, fail_resolve=False):
        spec = importlib.util.spec_from_file_location(
            "synthetic_ipc_adapter", ROOT / "tests/kernel-ipc-transition-native.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = self.root / "build/ipc-synthetic"
        identity = Mock(sha256=c.digest(self.compiler))
        identity.record.return_value = dict(
            mode="developer", observed_compiler_sha256=c.digest(self.compiler), external_expected_sha256=None
        )
        if fail_final:
            identity.verify.side_effect = RuntimeError("synthetic final identity failure")
        argv = [
            "synthetic_ipc_adapter",
            "--compiler",
            str(self.compiler),
            "--output",
            str(output),
            "--developer-build-receipt",
            str(self.receipt),
        ]

        def observed_run(command, folder, name, cap, **kwargs):
            symbols = b""
            if name == "root-symbols":
                symbols = b"aurora_kernel_ipc_transition T 10 20\naurora_kernel_round_robin_next T 30 40\n"
            elif name == "adapter-root-symbols":
                symbols = b"aurora_kernel_ipc_transition_real T 10 20\naurora_kernel_round_robin_next T 30 40\n"
            return subprocess.CompletedProcess(command, 0, symbols, b"")

        # Synthetic metadata/ordering only: compiler, linker, vectors and native
        # execution are mocked. These counts are not IPC qualification evidence.
        with (
            patch.object(sys, "argv", argv),
            patch.object(module, "ROOT", self.root),
            patch.object(module, "resolve_identity", return_value=identity) as resolve,
            patch.object(module, "run", side_effect=observed_run) as run,
            patch.object(module, "guard") as guard,
            patch.object(module, "sha", side_effect=lambda path: c.digest(path) if path == self.compiler else "b" * 64),
            patch.object(module, "vector_gate", side_effect=[17, 19]),
            patch.object(module, "rejection_gate", return_value=22),
            patch.object(module, "allocated", return_value=0),
            redirect_stdout(io.StringIO()),
        ):
            if fail_resolve:
                resolve.side_effect = RuntimeError("synthetic initial identity failure")
                with self.assertRaisesRegex(RuntimeError, "synthetic initial identity failure"):
                    module.main()
                self.assertFalse(output.exists())
                run.assert_not_called()
                guard.assert_not_called()
                identity.verify.assert_not_called()
                return
            if fail_final:
                with self.assertRaisesRegex(RuntimeError, "synthetic final identity failure"):
                    module.main()
                self.assertFalse((output / "summary.json").exists())
            else:
                module.main()
                summary = json.loads((output / "summary.json").read_text())
                inputs = json.loads((output / "inputs.json").read_text())
                self.assertEqual(summary["compiler_identity"], identity.record.return_value)
                self.assertEqual(inputs["compiler_identity"], identity.record.return_value)
                self.assertEqual(summary["cases"]["copy_repetitions"], 4096)
                self.assertEqual(summary["cases"]["finite_contexts"], 288)
                self.assertEqual(summary["cases"]["decoder_compact"], 73728)
                self.assertIn("no QEMU", summary["limits"])
            identity.verify.assert_called_once_with()
            resolve.assert_called_once()
            self.assertEqual(resolve.call_args.args[1:], (self.compiler, self.root))
            self.assertEqual(run.call_count, 17)

    def test_ipc_adapter_metadata_and_final_identity(self):
        self.ipc_adapter()

    def test_ipc_final_identity_failure_cannot_pass(self):
        self.ipc_adapter(fail_final=True)

    def test_ipc_initial_identity_failure_precedes_artifacts(self):
        self.ipc_adapter(fail_resolve=True)

    def round_robin_adapter(self, fail_final=False):
        spec = importlib.util.spec_from_file_location(
            "synthetic_rr_adapter", ROOT / "tests/kernel-round-robin-native.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = self.root / "build/rr-synthetic"
        identity = Mock(sha256=c.digest(self.compiler))
        identity.record.return_value = dict(
            mode="developer", observed_compiler_sha256=c.digest(self.compiler), external_expected_sha256=None
        )
        if fail_final:
            identity.verify.side_effect = RuntimeError("synthetic final identity failure")
        argv = [
            "synthetic_rr_adapter",
            "--compiler",
            str(self.compiler),
            "--output",
            str(output),
            "--developer-build-receipt",
            str(self.receipt),
        ]
        # Only adapter ordering/metadata are exercised; all native work is mocked.
        with (
            patch.object(sys, "argv", argv),
            patch.object(module, "resolve_identity", return_value=identity) as resolve,
            patch.object(module, "run") as run,
            patch.object(module, "guard"),
            patch.object(module, "vector_gate", side_effect=[17672, 1051016]),
            patch.object(module, "rejection_gate", return_value=10),
            patch.object(module, "allocated", return_value=0),
            redirect_stdout(io.StringIO()),
        ):
            if fail_final:
                with self.assertRaisesRegex(RuntimeError, "synthetic final identity failure"):
                    module.main()
                self.assertFalse((output / "summary.json").exists())
            else:
                module.main()
                summary = json.loads((output / "summary.json").read_text())
                self.assertEqual(summary["compiler_identity"], identity.record.return_value)
                self.assertEqual(summary["cases"]["copy_repetitions"], 4096)
                self.assertEqual(summary["cases"]["rejections"], 10)
                self.assertIn("no QEMU", summary["limits"])
            identity.verify.assert_called_once_with()
            resolve.assert_called_once()
            self.assertEqual(resolve.call_args.args[1:], (self.compiler, ROOT))
            self.assertEqual(run.call_count, 7)

    def test_round_robin_adapter_metadata_and_final_identity(self):
        self.round_robin_adapter()

    def test_round_robin_final_identity_failure_cannot_pass(self):
        self.round_robin_adapter(fail_final=True)

    def test_make_pin_rejections_do_not_launch_builds(self):
        # These routes must fail before any compiler/query/test workload. They run
        # only after the Make dispatcher exists; there is no fallback to native test.
        text = (ROOT / "Makefile").read_text()
        self.assertIn("compiler_contract.py", text)
        before = {str(p) for p in (ROOT / "build").glob("test-contract-*")} if (ROOT / "build").exists() else set()
        for argv in (
            [shutil.which("make"), "test-acceptance"],
            [shutil.which("make"), "test-acceptance", "ACCEPTANCE_COMPILER_SHA256=bad"],
            [shutil.which("make"), "test", "AURORAC=/nonexistent/compiler"],
        ):
            result = subprocess.run(
                argv, cwd=ROOT, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15
            )
            self.assertNotEqual(result.returncode, 0, result.stdout.decode())
        after = {str(p) for p in (ROOT / "build").glob("test-contract-*")} if (ROOT / "build").exists() else set()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)

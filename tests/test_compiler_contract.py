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
        self.receipt.write_text(json.dumps(self.context, indent=2, sort_keys=True) + "\n")

    def checked(self):
        return c.read_context(self.receipt, self.root, self.compiler, developer=True)

    def args(self, **kwargs):
        return argparse.Namespace(compiler_sha256=kwargs.get("pin"), developer_build_receipt=kwargs.get("receipt"))

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

    def test_live_oracle_is_in_inventory(self):
        relative = "evidence/package-graph/oracle/reference-v1/reference.py"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic inventory input")
        self.assertIn(relative, c.source_inventory(self.root))

    def test_historical_header_pch_rejection(self):
        header = self.root / "system header.hpp"
        header.write_text("// synthetic system header")
        inputs = {str(header): c.file_record(header)}
        c.reject_pch(inputs)
        Path(str(header) + ".gch").write_text("opaque PCH")
        with self.assertRaises(c.ContractError):
            c.reject_pch(inputs)

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
        for name, family, focused in consumers:
            self.assertTrue((ROOT / name).is_file(), "missing required integrated cap consumer")
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

    def test_historical_receipt_retains_exact_both_flag_vectors(self):
        raw_build = '-std=c++23  -O2 "-DCOUNT=7" -D WORD=token'
        raw_ir = "-std=c++23 -O1 -g '-DTRACE=1' -U DROP"
        expected = {"CXXFLAGS": shlex.split(raw_build), "IR_TEST_CXXFLAGS": shlex.split(raw_ir)}
        self.context["host_test_flags"] = expected
        self.context["flags"] = expected["CXXFLAGS"]
        self.context["build_command"] = c.build_argv(
            str(self.tool), expected["CXXFLAGS"], str(self.compiler), str(self.depfile)
        )
        self.write()
        with patch.dict(os.environ, {"CXXFLAGS": raw_build, "IR_TEST_CXXFLAGS": raw_ir}):
            self.assertEqual(self.checked()["host_test_flags"], expected)
        for name, vector in expected.items():
            self.assertEqual(shlex.split(shlex.join(vector)), vector)

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

    def test_historical_prebuilt_receipt_retains_host_vectors_without_fresh_build_claim(self):
        self.context.update(
            mode="acceptance",
            origin="externally-pinned-prebuilt",
            external_expected_sha256=c.digest(self.compiler),
            prebuilt_input=c.file_record(self.compiler),
            host_test_flags=c.selected_flag_vectors({"IR_TEST_CXXFLAGS": "-std=c++23 -O0 -g"}),
        )
        for field in ("build_command", "build_returncode", "header_inputs", "build_recipe"):
            self.context.pop(field)
        self.write()
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-std=c++23 -O0 -g"}):
            context = c.read_context(self.receipt, self.root)
            self.assertEqual(context["origin"], "externally-pinned-prebuilt")
            self.assertNotIn("build_command", context)
            self.assertEqual(context["host_test_flags"]["IR_TEST_CXXFLAGS"], ["-std=c++23", "-O0", "-g"])
        with patch.dict(os.environ, {"IR_TEST_CXXFLAGS": "-O1"}), self.assertRaises(c.ContractError):
            c.read_context(self.receipt, self.root)

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
        # Fixture includes now belong to Meson rather than a second Make graph.
        meson = (ROOT / "tests/meson.build").read_text()
        self.assertIn("'compiler/initialization_facts.cpp'", meson)
        self.assertIn("'short_circuit_ir'", meson)
        self.assertIn("include_directories('../compiler')", meson)

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
            "kernel-uefi-budget-tests.sh",
            "kernel-uefi-dispatch-tests.sh",
            "kernel-uefi-user-phases-tests.sh",
        ):
            text = (ROOT / "scripts" / name).read_text()
            self.assertIn('compiler="${AURORAC:-build/aurorac}"', text)
            self.assertIn('if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi', text)
            self.assertIn('"$compiler" --module-root kernel/policies examples/kernel.au', text)
        text = (ROOT / "scripts/kernel-uefi-ipc-tests.sh").read_text()
        self.assertIn(': "${AURORAC:?', text)
        self.assertIn('[[ -x "$AURORAC" ]]', text)
        self.assertNotIn("make -C compiler", text)
        self.assertNotIn("${AURORAC:-", text)
        for fragment in (
            'scripts/meson-native-fixture.py --compiler "$AURORAC"',
            "--source examples/kernel-program-console.au --module-root kernel/policies --module-root library",
            "--local-symbols --referenced-reflection-only",
            "--bridge kernel/uefi/program-note-entry.S --bridge kernel/uefi/kernel-policy-entry.S",
            "--object build/uefi/ipc-language.o --depfile build/uefi/ipc-language.d",
            "tests/kernel-ipc.cpp build/uefi/ipc-language.o",
            "tests/kernel-program-mailbox.cpp build/uefi/ipc-language.o",
        ):
            self.assertIn(fragment, text)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)

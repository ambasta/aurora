#!/usr/bin/env python3
"""Compiler-free controls for configure-bound predecessor invocation checks."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bootstrap
import bootstrap_guard as guard


class ConfiguredGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bootstrap-guard-control-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.selection = self.build / "bootstrap-selection.json"
        self.depfile = self.build / "bootstrap-selection.d"
        self.receipt = self.fixture("receipt.json", b"retained original receipt\n")
        self.pin = self.fixture("route.json", b"source-owned route\n")
        self.compiler = self.fixture("predecessor", b"\x7fELFfixture predecessor\n")
        self.compiler.chmod(0o755)
        self.oracle = self.fixture("historical-oracle", b"\x7fELFfixture historical oracle\n")
        self.oracle.chmod(0o755)
        self.header = self.fixture("historical header.hpp", b"historical compile input\n")
        self.log = self.fixture("historical.log", b"original command output\n")
        self.library = self.fixture("runtime.so", b"runtime library bytes\n")
        self.sha256 = bootstrap.digest(self.compiler)
        self.value = {
            "route": dict(zip(guard.ROLES, ("final", "historical"), strict=True)),
            "tools": {"files": [bootstrap.file_identity(self.library)]},
            "stages": [
                {
                    "source": {"name": name},
                    "artifact": bootstrap.file_identity(compiler),
                    "inputs": [bootstrap.file_identity(self.header)],
                    "commands": [{"log": bootstrap.file_identity(self.log)}],
                }
                for name, compiler in (("final", self.compiler), ("historical", self.oracle))
            ],
        }
        self.full_verify = unittest.mock.Mock(return_value=deepcopy(self.value))
        for patcher in (
            patch.object(bootstrap, "ROOT", self.root),
            patch.object(bootstrap, "MANIFEST", self.pin),
            patch.object(bootstrap, "verify", self.full_verify),
            patch.object(guard, "runtime_identity", side_effect=self.runtime),
            patch.dict(os.environ, {"PATH": os.environ["PATH"]}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.configure()
        self.selection_sha256 = bootstrap.digest(self.selection)

    def fixture(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def runtime(self, compiler):
        return [
            bootstrap.file_identity(path)
            for path in (bootstrap.meson_toolchain.selected_tool("ldd"), sys.executable, self.library)
        ]

    def configure(self):
        return guard.configure(str(self.compiler), self.sha256, str(self.receipt), self.selection, self.depfile)

    def check(self, **overrides):
        arguments = {
            "compiler": str(self.compiler),
            "sha256": self.sha256,
            "receipt": str(self.receipt),
            "selection_sha256": self.selection_sha256,
        }
        arguments.update(overrides)
        return guard.check(self.selection, **arguments)

    def test_configure_verifies_history_once_and_invocations_do_not(self):
        self.full_verify.assert_called_once_with(str(self.compiler), self.sha256, str(self.receipt))
        with patch.object(bootstrap, "check_file", wraps=bootstrap.check_file) as checked:
            self.check()
            self.check()
            self.assertNotIn(str(self.header), [call.args[0]["path"] for call in checked.call_args_list])
            self.assertNotIn(str(self.log), [call.args[0]["path"] for call in checked.call_args_list])
        self.assertEqual(self.full_verify.call_count, 1)
        self.assertEqual(self.receipt.read_bytes(), b"retained original receipt\n")

    def test_configure_dependencies_cover_actual_evidence_and_runtime(self):
        dependency_text = self.depfile.read_text()
        for path in (self.compiler, self.oracle, self.receipt, self.pin, self.header, self.log, self.library):
            with self.subTest(path=path):
                self.assertIn(guard.depfile_escape(path), dependency_text)
        self.assertTrue(dependency_text.startswith("bootstrap-selection.json: "))
        self.assertNotIn("schema", json.loads(self.selection.read_text()))

    def test_evidence_inside_active_build_is_not_silently_untracked(self):
        inner = self.build / "historical.hpp"
        inner.write_bytes(b"untrackable historical input")
        self.full_verify.return_value["stages"][0]["inputs"].append(bootstrap.file_identity(inner))
        with self.assertRaisesRegex(ValueError, "outside the active Meson build"):
            self.configure()

    def test_full_validation_failure_never_replaces_configured_selection(self):
        before = self.selection.read_bytes()
        self.full_verify.side_effect = ValueError("historical header changed")
        with self.assertRaisesRegex(ValueError, "historical header changed"):
            self.configure()
        self.assertEqual(self.selection.read_bytes(), before)

    def test_compiler_receipt_pin_and_runtime_changes_fail(self):
        for path in (self.compiler, self.receipt, self.pin, self.library):
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                try:
                    with self.assertRaises(ValueError):
                        self.check()
                finally:
                    path.write_bytes(original)

    def test_changed_driver_or_guard_binding_fails(self):
        original = self.selection.read_text()
        for name in ("driver", "guard", "toolchain"):
            value = json.loads(original)
            value["identities"][name]["sha256"] = "0" * 64
            self.selection.write_text(json.dumps(value))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "identity changed: " + name):
                self.check(selection_sha256=bootstrap.digest(self.selection))
        self.selection.write_text(original)

    def test_selection_edited_before_invocation_cannot_bless_changed_runtime(self):
        value = json.loads(self.selection.read_text())
        self.library.write_bytes(b"changed runtime")
        value["runtimes"] = {role: self.runtime(record["path"]) for role, record in value["roles"].items()}
        self.selection.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "selection SHA256 mismatch"):
            self.check()

    def command_metadata(self, arguments):
        directory = self.build / "meson-info"
        directory.mkdir(exist_ok=True)
        value = [{"name": "hosted-frontend-assembly", "target_sources": [{"compiler": arguments}]}]
        (directory / "intro-targets.json").write_text(json.dumps(value))

    def test_wrapper_pin_comes_from_generated_command_not_selection_bytes(self):
        self.command_metadata(
            [
                sys.executable,
                str(Path(guard.__file__).resolve()),
                "run",
                "--selection",
                str(self.selection),
                "--selection-sha256",
                self.selection_sha256,
                "--",
                "unused child",
            ]
        )
        self.selection.write_bytes(b"altered before invocation")
        self.assertEqual(guard.configured_selection_sha256(self.build), self.selection_sha256)
        with self.assertRaisesRegex(ValueError, "selection SHA256 mismatch"):
            self.check(selection_sha256=guard.configured_selection_sha256(self.build))

    def test_wrapper_rejects_missing_invalid_or_ambiguous_command_pin(self):
        prefix = [str(Path(guard.__file__).resolve()), "run", "--selection", str(self.selection)]
        for tail in (
            ["--"],
            ["--selection-sha256", "--"],
            ["--selection-sha256", "invalid", "--"],
            ["--selection-sha256", self.selection_sha256, "--selection-sha256", self.selection_sha256, "--"],
        ):
            self.command_metadata(prefix + tail)
            with self.subTest(tail=tail), self.assertRaises(ValueError):
                guard.configured_selection_sha256(self.build)

    def test_wrong_role_or_digest_cannot_relabel_the_oracle(self):
        with self.assertRaisesRegex(ValueError, "configured bootstrap selection differs"):
            self.check(role="historical_cpp_oracle")
        with self.assertRaisesRegex(ValueError, "configured bootstrap selection differs"):
            self.check(sha256="0" * 64)
        self.check(compiler=str(self.oracle), sha256=bootstrap.digest(self.oracle), role="historical_cpp_oracle")

    def test_new_runtime_shadow_fails_even_when_old_files_are_unchanged(self):
        shadow = self.fixture("shadow-runtime.so", b"shadow library")
        actual_runtime = self.runtime(self.compiler) + [bootstrap.file_identity(shadow)]
        with patch.object(guard, "runtime_identity", return_value=actual_runtime):
            with self.assertRaisesRegex(ValueError, "runtime changed"):
                self.check()

    def test_environment_override_cannot_change_runtime(self):
        for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT", "GCC_EXEC_PREFIX", "COMPILER_PATH", "CPATH"):
            with self.subTest(name=name), patch.dict(os.environ, {name: "/different/runtime"}):
                with self.assertRaises(ValueError):
                    self.check()

    def test_preexisting_mutation_stops_before_command(self):
        self.compiler.write_bytes(b"changed before invocation")
        with patch.object(guard.subprocess, "run") as child:
            with self.assertRaisesRegex(ValueError, "file digest changed"):
                guard.run(
                    self.selection,
                    str(self.compiler),
                    self.sha256,
                    str(self.receipt),
                    ["unused"],
                    selection_sha256=self.selection_sha256,
                )
            child.assert_not_called()

    def test_mutation_during_command_fails_afterward(self):
        def child(command, **kwargs):
            self.compiler.write_bytes(b"changed during invocation")
            return subprocess.CompletedProcess(command, 0)

        with patch.object(guard.subprocess, "run", side_effect=child):
            with self.assertRaisesRegex(ValueError, "file digest changed"):
                guard.run(
                    self.selection,
                    str(self.compiler),
                    self.sha256,
                    str(self.receipt),
                    ["unused"],
                    selection_sha256=self.selection_sha256,
                )

    def test_child_failure_returns_its_status_after_both_checks(self):
        result = subprocess.CompletedProcess(["unused"], 5)
        with patch.object(guard.subprocess, "run", return_value=result) as child:
            status = guard.run(
                self.selection,
                str(self.compiler),
                self.sha256,
                str(self.receipt),
                ["unused"],
                selection_sha256=self.selection_sha256,
            )
        self.assertEqual(status, 5)
        self.assertEqual(child.call_args.kwargs, {})

    def test_runtime_discovery_uses_current_resolved_libraries(self):
        # Exercise the real resolver separately from the synthetic check fixture.
        result = subprocess.CompletedProcess([], 0, "libfixture.so => " + str(self.library) + " (0x1234)\n", "")
        with (
            patch.object(guard, "runtime_identity", self.real_runtime),
            patch.object(guard.subprocess, "run", return_value=result) as inspect,
        ):
            records = guard.runtime_identity(self.compiler)
        self.assertIn(bootstrap.file_identity(self.library), records)
        self.assertEqual(inspect.call_count, 2)
        self.assertEqual([call.args[0][-1] for call in inspect.call_args_list], [str(self.compiler), sys.executable])

    real_runtime = staticmethod(guard.runtime_identity)


if __name__ == "__main__":
    unittest.main()

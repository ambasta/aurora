#!/usr/bin/env python3
"""Compiler-free behavioral controls for source-bound bootstrap artifacts."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "header.hpp").write_text("fixture header\n")
        commit, tree = "1" * 40, "2" * 40
        self.pin = deepcopy(bootstrap.route())
        for stage in self.pin["stages"]:
            stage.update(commit=commit, tree=tree)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # The supported image has no Git. This responder deliberately reports clean
        # status even for changed files, exercising independent blob/mode checks.
        git = self.bin / "git"
        git.write_text(
            "#!"
            + sys.executable
            + "\n"
            + r"""
import hashlib, pathlib, sys
args = sys.argv[3:]
data = b'fixture header\n'
if args[:2] == ['worktree', 'add']:
    source = pathlib.Path(args[-2]); source.mkdir(parents=True)
    (source/'header.hpp').write_bytes(data)
elif args[0] == 'rev-parse':
    print(('1' if args[1] == 'HEAD' else '2') * 40)
elif args[0] == 'symbolic-ref':
    sys.exit(1)
elif args[0] == 'cat-file':
    sys.exit(0 if args[2] == '1' * 40 + '^{commit}' else 1)
elif args[0] == 'ls-tree':
    oid = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    sys.stdout.buffer.write(('100644 blob ' + oid + '\theader.hpp\0').encode())
elif args[0] != 'status':
    sys.exit(2)
"""
        )
        git.chmod(0o755)
        meson = self.bin / "meson"
        meson.write_text(
            "#!"
            + sys.executable
            + """
import json, pathlib, sys
args = sys.argv[1:]
if args[0] == 'setup':
    out = pathlib.Path(args[1]); out.mkdir()
    (out/'build.ninja').write_text('synthetic build graph')
    (out/'meson-info').mkdir()
    (out/'meson-info/intro-buildoptions.json').write_text(json.dumps(args[3:]))
    (out/'compile_commands.json').write_text('[]')
elif args[0] == 'compile':
    out = pathlib.Path(args[args.index('-C')+1])
    (out/'aurorac').write_text('#!/bin/sh\\necho fixture compiler\\n')
    (out/'aurorac').chmod(0o755)
"""
        )
        meson.chmod(0o755)
        ninja = self.bin / "ninja"
        ninja.write_text("#!/bin/sh\nprintf 'fixture.o: #deps 0\\n'\n")
        ninja.chmod(0o755)
        self.tools = {
            "selected": {"meson": str(meson)},
            "files": [bootstrap.file_identity(meson)],
            "versions": {"meson": "fixture"},
            "host": ["fixture"],
            "environment": {"fixture": "one", "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH")},
        }
        for patcher in (
            patch.object(bootstrap, "ROOT", self.repo),
            patch.object(bootstrap, "route", lambda: deepcopy(self.pin)),
            patch.object(bootstrap, "tool_identity", lambda **kwargs: deepcopy(self.tools)),
            patch.dict(os.environ, {"PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cache = self.repo / "build/cache"
        self.receipt, self.value = bootstrap.build(self.cache)
        self.compiler = self.value["stages"][-1]["artifact"]["path"]
        self.sha256 = bootstrap.digest(self.compiler)

    def verify(self):
        return bootstrap.verify(self.compiler, self.sha256, str(self.receipt))

    def test_six_hops_convergence_and_cache_reuse(self):
        self.assertEqual(len(self.verify()["stages"]), 6)
        self.assertEqual(bootstrap.output([self.compiler]), "fixture compiler")
        with patch.object(bootstrap, "record_command", side_effect=AssertionError("cache must not execute builds")):
            receipt, value = bootstrap.build(self.cache)
        self.assertEqual(receipt, self.receipt)
        self.assertEqual(value, self.value)
        self.assertEqual([r["argv"][1] for r in value["stages"][-1]["commands"]], ["setup", "compile", "test"])

    def test_container_coordinator_translates_paths_and_checks_source_bytes(self):
        real_run, calls = subprocess.run, []

        def launch(command, **kwargs):
            if command[0].endswith("container.sh"):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0)
            return real_run(command, **kwargs)

        with (
            patch.object(sys, "argv", ["bootstrap.py", "build", "--container", "--cache", str(self.cache)]),
            patch.object(bootstrap.subprocess, "run", side_effect=launch),
        ):
            bootstrap.main()
        self.assertEqual(
            calls[0][:4], [str(self.repo / "scripts/container.sh"), "python3", "scripts/bootstrap.py", "build"]
        )
        self.assertEqual(calls[0][5], "/workspace/build/cache")
        relative = Path(calls[0][7]).relative_to("/workspace")
        mounted = self.root / "mounted"
        shutil.copytree(self.repo / relative.parent, mounted / relative.parent)
        with patch.object(bootstrap, "ROOT", mounted):
            stages = bootstrap.prepared_sources(mounted / relative, self.pin)
            (mounted / stages[0]["source_dir"] / "header.hpp").write_text("changed after preparation")
            with self.assertRaisesRegex(ValueError, "prepared source bytes/modes changed"):
                bootstrap.prepared_sources(mounted / relative, self.pin)

    def test_host_preparation_rejects_hidden_blob_changes_and_symlink_escape(self):
        source = Path(self.value["stages"][0]["source_dir"])
        (source / "header.hpp").write_text("Git status deliberately hides this change")
        with self.assertRaisesRegex(ValueError, "pinned Git blob/mode"):
            bootstrap.prepare_sources(self.cache, self.pin)
        (source / "header.hpp").write_text("fixture header\n")
        for target in (source, source.parent, source.parent.parent):
            backup = self.root / "saved-source"
            target.rename(backup)
            target.symlink_to(self.root, target_is_directory=True)
            with patch.object(bootstrap, "record_command") as launch:
                with self.assertRaisesRegex(ValueError, "path escapes checkout"):
                    bootstrap.prepare_sources(self.cache, self.pin)
                launch.assert_not_called()
            target.unlink()
            backup.rename(target)

    def test_one_receipt_selects_both_roles_and_cross_checks_are_optional(self):
        value, roles = bootstrap.select(str(self.receipt))
        self.assertEqual(roles["build_predecessor"]["path"], self.compiler)
        self.assertEqual(roles["build_predecessor"]["sha256"], self.sha256)
        self.assertEqual(roles["historical_cpp_oracle"], value["stages"][-1]["artifact"])
        self.assertEqual(bootstrap.select(str(self.receipt), self.compiler, self.sha256)[1], roles)
        with self.assertRaisesRegex(ValueError, "not the receipt's predecessor"):
            bootstrap.select(str(self.receipt), str(self.root / "other-aurorac"))
        with self.assertRaisesRegex(ValueError, "differs from the receipt"):
            bootstrap.select(str(self.receipt), self.compiler, "0" * 64)
        with self.assertRaisesRegex(ValueError, "To fix: .*build --container"):
            bootstrap.select("relative/receipt.json")

    def test_generators_refuse_an_executable_changed_after_configure(self):
        bootstrap.require_digest(self.compiler, self.sha256)
        Path(self.compiler).write_text("changed executable bytes")
        with self.assertRaisesRegex(ValueError, "changed since Meson verified it; reconfigure Meson"):
            bootstrap.require_digest(self.compiler, self.sha256)
        self.assertEqual(bootstrap.child_status(-9), 137)

    def test_missing_commit_names_fetch_and_deleted_worktree_is_readded(self):
        self.pin["stages"][0]["commit"] = "3" * 40
        with self.assertRaisesRegex(ValueError, "git fetch origin " + "3" * 40):
            bootstrap.prepare_sources(self.cache, self.pin, fresh=True)
        self.pin["stages"][0]["commit"] = "1" * 40
        source = Path(self.value["stages"][0]["source_dir"])
        shutil.rmtree(source)
        calls = []
        real = bootstrap.record_command
        with patch.object(
            bootstrap, "record_command", side_effect=lambda argv, *rest: calls.append(argv) or real(argv, *rest)
        ):
            bootstrap.prepare_sources(self.cache, self.pin)
        self.assertEqual(calls[0][3:6], ["worktree", "add", "-f"])

    def test_changed_binary_is_rejected(self):
        Path(self.compiler).write_text("#!/bin/sh\necho changed compiler\n")
        with self.assertRaisesRegex(ValueError, "file digest changed"):
            self.verify()
        with self.assertRaisesRegex(ValueError, "file digest changed"):
            bootstrap.build(self.cache)

    def test_missing_receipt_and_failed_or_altered_command_rejected(self):
        with self.assertRaisesRegex(ValueError, "receipt"):
            bootstrap.verify(self.compiler, self.sha256, "")
        incomplete = deepcopy(self.value)
        incomplete["stages"].pop()
        bootstrap.write_json(self.receipt, incomplete)
        with self.assertRaisesRegex(ValueError, "incomplete six-source receipt"):
            self.verify()
        for field, replacement in (("returncode", 1), ("argv", ["true"])):
            value = deepcopy(self.value)
            value["stages"][3]["commands"][2][field] = replacement
            bootstrap.write_json(self.receipt, value)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "reconstruction command"):
                self.verify()
        self.receipt.unlink()
        with self.assertRaisesRegex(ValueError, "To fix: .*reconfigure Meson"):
            self.verify()

    def test_source_configuration_and_tool_mismatches_rejected(self):
        for field, value in (("commit", "0" * 40), ("tree", "1" * 40)):
            original = self.pin["stages"][-1][field]
            self.pin["stages"][-1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "source pin/configuration mismatch"):
                self.verify()
            self.pin["stages"][-1][field] = original
        self.pin["meson_options"].append("-Doptimization=0")
        with self.assertRaisesRegex(ValueError, "configuration mismatch"):
            self.verify()
        self.pin["meson_options"].pop()
        (self.bin / "meson").write_text("changed tool bytes")
        with self.assertRaisesRegex(ValueError, "file digest changed"):
            self.verify()

    def test_driver_edits_keep_receipts_and_cache_but_new_runtime_is_rejected(self):
        # Driver bytes are not artifact provenance; editing them must not force six rebuilds.
        with patch.object(
            bootstrap,
            "digest",
            side_effect=lambda path: bootstrap.hashlib.sha256(
                Path(path).read_bytes() + (b"edited" if Path(path) == Path(bootstrap.__file__) else b"")
            ).hexdigest(),
        ):
            self.assertEqual(bootstrap.build(self.cache)[0], self.receipt)
        self.assertNotIn("driver_sha256", self.value)
        shadow = self.root / "newly-selected-runtime"
        shadow.write_text("new library in an unchanged search directory")
        self.tools["files"].append(bootstrap.file_identity(shadow))
        with self.assertRaisesRegex(ValueError, "current tool identity differs from the receipt"):
            self.verify()

    def test_environment_invalidates_cache_and_preserves_previous_run(self):
        self.tools["environment"]["fixture"] = "two"
        second, _ = bootstrap.build(self.cache)
        self.assertNotEqual(second, self.receipt)
        self.assertTrue(self.receipt.exists())

    def test_dirty_source_header_and_missing_logs_rejected(self):
        source = Path(self.value["stages"][0]["source_dir"])
        (source / "untracked").write_text("untracked input")
        with self.assertRaisesRegex(ValueError, "worktree bytes/modes changed"):
            bootstrap.build(self.cache)
        (source / "untracked").unlink()
        header = source / "header.hpp"
        header.write_text("changed header")
        with self.assertRaisesRegex(ValueError, "source worktree bytes/modes changed"):
            bootstrap.build(self.cache)
        header.write_text("fixture header\n")
        Path(self.value["stages"][2]["commands"][2]["log"]["path"]).unlink()
        with self.assertRaisesRegex(ValueError, "To fix:"):
            self.verify()

    def test_failed_fresh_build_keeps_logs_and_old_cache(self):
        meson = self.bin / "meson"
        original = meson.read_text()
        meson.write_text("#!/bin/sh\necho deliberate build failure\nexit 23\n")
        with self.assertRaisesRegex(ValueError, "retained log"):
            bootstrap.build(self.cache, fresh=True)
        failed = list(self.cache.glob("source-*/seed/0.log"))
        self.assertTrue(any("deliberate build failure" in path.read_text() for path in failed))
        self.assertTrue(self.receipt.exists())
        meson.write_text(original)
        self.assertEqual(bootstrap.build(self.cache)[0], self.receipt)


if __name__ == "__main__":
    unittest.main()

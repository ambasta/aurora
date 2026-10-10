#!/usr/bin/env python3
"""Compiler-free cleanup controls; all deletions are tiny disposable fixtures."""

from contextlib import redirect_stdout
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import clean


class CleanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-clean-controls-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build/meson-0123456789abcdef"
        self.ninja = shutil.which("ninja")
        self.assertIsNotNone(self.ninja, "Ninja is needed for real, compiler-free clean-tool controls")
        for directory in ("meson-info", "meson-private", "meson-logs", "objects", "tests/aurora-meson-old"):
            (self.build / directory).mkdir(parents=True, exist_ok=True)
        (self.build / "meson-info/meson-info.json").write_text(
            json.dumps({"directories": {"source": str(self.root), "build": str(self.build)}})
        )
        (self.build / "meson-info/intro-projectinfo.json").write_text(
            json.dumps({"descriptive_name": "aurora-bootstrap"})
        )
        (self.build / "meson-private/meson.lock").touch()
        (self.build / ".aurora-test.lock").touch()
        (self.build / "build.ninja").write_text(
            "rule fixture\n command = false\n depfile = $out.d\n"
            "build objects/compiler.o: fixture\nbuild aurorac: fixture\n"
        )
        for name in (
            "objects/compiler.o",
            "objects/compiler.o.d",
            "aurorac",
            "aurorac.d",
            "meson-logs/testlog.txt",
            "tests/aurora-meson-old/failure.log",
            "unknown-output",
        ):
            (self.build / name).write_bytes(b"fixture\n")

    def products(self, dry_run=False):
        with redirect_stdout(io.StringIO()) as output:
            clean.clean_build(self.root, self.build, self.ninja, dry_run)
        return output.getvalue()

    def tree(self):
        return {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_real_ninja_preview_and_cleanup_preserve_untracked_evidence(self):
        before = self.tree()
        preview = self.products(True)
        self.assertEqual(self.tree(), before)
        self.assertIn("4 files, 32 bytes", preview)
        self.assertIn("objects/compiler.o.d", preview)
        self.products()
        removed = set(before) - set(self.tree())
        self.assertEqual(
            removed,
            {
                "build/meson-0123456789abcdef/" + name
                for name in ("objects/compiler.o", "objects/compiler.o.d", "aurorac", "aurorac.d")
            },
        )
        self.assertIn("0 files, 0 bytes", self.products())

    def test_wrong_owner_and_keep_refused_without_deletion(self):
        info = self.build / "meson-info/meson-info.json"
        original = info.read_text()
        info.write_text(json.dumps({"directories": {"source": "/elsewhere", "build": str(self.build)}}))
        with self.assertRaisesRegex(ValueError, "ownership mismatch"):
            self.products()
        info.write_text(original)
        for pin in (self.build / ".keep", self.build / "objects/.keep"):
            pin.touch()
            with self.assertRaisesRegex(ValueError, "kept output"):
                self.products()
            pin.unlink()
        self.assertTrue((self.build / "aurorac").exists())

    def test_symlink_and_outside_outputs_refused(self):
        outside = self.root / "outside"
        outside.write_text("keep")
        product = self.build / "aurorac"
        product.unlink()
        product.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.products()
        product.unlink()
        (self.build / "build.ninja").write_text("rule fixture\n command = false\nbuild ../../outside: fixture\n")
        with self.assertRaisesRegex(ValueError, "escapes build"):
            self.products()
        self.assertEqual(outside.read_text(), "keep")

    def test_active_aurora_and_meson_locks_refused(self):
        for relative, kind in ((".aurora-test.lock", "flock"), ("meson-private/meson.lock", "lockf")):
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    "import fcntl,sys,time; f=open(sys.argv[1],'r+'); "
                    "getattr(fcntl,sys.argv[2])(f,fcntl.LOCK_EX); print('ready',flush=True); time.sleep(30)",
                    str(self.build / relative),
                    kind,
                ],
                stdout=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                with self.assertRaisesRegex(ValueError, "active/locked"):
                    self.products()
            finally:
                child.terminate()
                child.wait()
                child.stdout.close()
        self.assertTrue((self.build / "aurorac").exists())

    def test_direct_active_process_refused(self):
        child = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(30)"], cwd=self.build)
        try:
            with self.assertRaisesRegex(ValueError, "active process"):
                self.products()
        finally:
            child.terminate()
            child.wait()

    def test_missing_locks_preview_stays_read_only_and_symlink_lock_refuses(self):
        for name in (".aurora-test.lock", "meson-private/meson.lock"):
            (self.build / name).unlink()
        before = self.tree()
        self.products(True)
        self.assertEqual(self.tree(), before)
        (self.build / ".aurora-test.lock").symlink_to(self.root / "outside-lock")
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.products()
        self.assertFalse((self.root / "outside-lock").exists())

    def test_incomplete_or_mismatched_ninja_plan_refuses(self):
        for response in ("", "Cleaning...\nRemove aurorac\n0 files.\n", "Cleaning...\nunknown\n0 files.\n"):
            with patch.object(clean.subprocess, "check_output", return_value=response):
                with self.assertRaisesRegex(ValueError, "Ninja clean plan"):
                    self.products()
        self.assertTrue((self.build / "aurorac").exists())

    def test_source_tree_or_unowned_configuration_refuses(self):
        source = self.root / "compiler"
        source.mkdir()
        with self.assertRaisesRegex(ValueError, "beneath build"):
            clean.clean_build(self.root, source, self.ninja, False)
        (self.build / "meson-info/meson-info.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "ownership mismatch"):
            self.products()
        self.assertTrue((self.build / "aurorac").exists())

    def run_folder(self, name, status="passed", finished=1, **options):
        folder = self.root / "build/graphical-smoke" / ("run-" + name)
        folder.mkdir(parents=True)
        marker = {"schema": clean.RUN_SCHEMA, "status": status}
        if status != "running":
            marker["finished_ns"] = finished
        (folder / clean.RUN_MARKER).write_text(json.dumps(marker))
        (folder / "pixels.bin").write_bytes(b"screen fixture")
        if options.get("keep"):
            (folder / ".keep").touch()
        return folder

    def test_smoke_deletes_only_older_successes_after_preview(self):
        old = self.run_folder("Old", finished=1)
        for name, status, stamp in (
            ("New", "passed", 2),
            ("Newest", "passed", 3),
            ("Failed", "failed", 0),
            ("Running", "running", 0),
        ):
            self.run_folder(name, status, stamp)
        self.run_folder("Kept", finished=0, keep=True)
        unknown = self.run_folder("Unknown")
        (unknown / clean.RUN_MARKER).unlink()
        malformed = self.run_folder("Malformed")
        (malformed / clean.RUN_MARKER).write_text("{")
        outside = self.root / "outside-evidence"
        outside.mkdir()
        (old.parent / "run-Link").symlink_to(outside, target_is_directory=True)
        before = self.tree()
        with redirect_stdout(io.StringIO()) as out:
            clean.smoke_runs(self.root, True)
        self.assertEqual(self.tree(), before)
        self.assertIn("Would remove " + str(old), out.getvalue())
        with redirect_stdout(io.StringIO()):
            clean.smoke_runs(self.root, False)
        self.assertFalse(old.exists())
        self.assertEqual(
            set(before) - set(self.tree()),
            {"build/graphical-smoke/run-Old/" + name for name in (clean.RUN_MARKER, "pixels.bin")},
        )
        self.assertTrue(outside.exists())

    def test_smoke_internal_symlink_keep_and_lock_are_preserved(self):
        old = self.run_folder("Old", finished=1)
        self.run_folder("New", finished=2)
        self.run_folder("Newest", finished=3)
        (old / "link").symlink_to(self.build, target_is_directory=True)
        with redirect_stdout(io.StringIO()):
            clean.smoke_runs(self.root, False)
        self.assertTrue(old.exists())
        (old / "link").unlink()
        (old / "nested").mkdir()
        (old / "nested/.keep").touch()
        with redirect_stdout(io.StringIO()):
            clean.smoke_runs(self.root, False)
        self.assertTrue(old.exists())
        with (old.parent / ".retention.lock").open("r+") as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            with self.assertRaisesRegex(ValueError, "active/locked"):
                clean.smoke_runs(self.root, False)

    def test_smoke_late_pin_after_scan_preserves_window(self):
        old = self.run_folder("Old", finished=1)
        self.run_folder("New", finished=2)
        self.run_folder("Newest", finished=3)
        walk = os.walk

        def pin_after_walk(*args, **kwargs):
            yield from walk(*args, **kwargs)
            (old / ".keep").touch()

        with patch.object(clean.os, "walk", side_effect=pin_after_walk), redirect_stdout(io.StringIO()) as output:
            clean.smoke_runs(self.root, False)
        self.assertTrue((old / ".keep").is_file())
        self.assertTrue((old / "pixels.bin").is_file())
        self.assertIn("Preserved " + str(old), output.getvalue())

    def test_smoke_ancestor_swap_at_deletion_never_reaches_foreign_output(self):
        old = self.run_folder("Old", finished=1)
        self.run_folder("New", finished=2)
        self.run_folder("Newest", finished=3)
        foreign = self.root / "foreign"
        (foreign / "run-Old").mkdir(parents=True)
        sentinel = foreign / "run-Old/must-survive.txt"
        sentinel.write_text("foreign evidence")
        moved = self.root / "owned-moved"
        remove = shutil.rmtree

        def swap_then_remove(path, *args, **kwargs):
            old.parent.rename(moved)
            old.parent.symlink_to(foreign, target_is_directory=True)
            return remove(path, *args, **kwargs)

        with patch.object(clean.shutil, "rmtree", side_effect=swap_then_remove), redirect_stdout(io.StringIO()):
            clean.smoke_runs(self.root, False)
        self.assertEqual(sentinel.read_text(), "foreign evidence")
        self.assertFalse((moved / "run-Old").exists())
        self.assertTrue((moved / "run-New/pixels.bin").is_file())

    def test_directory_anchor_refuses_symlink_ancestor(self):
        alias = self.root / "alias"
        alias.symlink_to(self.build.parent, target_is_directory=True)
        with self.assertRaises(OSError):
            with clean.open_directory(alias / self.build.name):
                self.fail("followed a symlink ancestor")

    def test_make_defaults_and_explicit_selection(self):
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/clean.py", self.root / "scripts/clean.py")
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        env = os.environ.copy()
        env.pop("MESON_BUILD_DIR", None)
        before = self.tree()
        preview = subprocess.run(["make", "clean-dry-run"], cwd=self.root, env=env, text=True, capture_output=True)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("4 files, 32 bytes", preview.stdout)
        self.assertEqual(self.tree(), before)
        wrong = subprocess.run(
            ["make", "clean", "MESON_BUILD_DIR=build/unknown"], cwd=self.root, env=env, text=True, capture_output=True
        )
        self.assertNotEqual(wrong.returncode, 0)
        result = subprocess.run(["make", "clean"], cwd=self.root, env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.build / "aurorac").exists())
        self.assertTrue((self.build / "meson-logs/testlog.txt").exists())


if __name__ == "__main__":
    unittest.main()

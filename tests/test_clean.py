#!/usr/bin/env python3
"""Compiler-free cleanup behavior using tiny disposable directories only."""

from contextlib import redirect_stdout
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
        self.build = self.root / "build/meson"
        self.build.mkdir(parents=True)

    def run_clean(self, *args, **environment):
        with (
            patch.object(clean, "__file__", self.root / "scripts/clean.py"),
            patch.object(sys, "argv", ["clean", *args]),
            patch.dict(
                os.environ,
                {"MESON_BUILD_DIR": str(self.build), "CLEAN_PATHS": "", **environment},
            ),
            redirect_stdout(io.StringIO()) as output,
        ):
            clean.main()
        return output.getvalue()

    def test_meson_clean_preserves_configuration_logs_and_scratch(self):
        (self.root / "meson.build").write_text(
            "project('cleanup-controls')\ncustom_target('fixture', output: 'owned.bin', command: ['false'])\n"
        )
        result = subprocess.run(
            ["meson", "setup", str(self.build), str(self.root)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        product = self.build / "owned.bin"
        product.write_bytes(b"compiled fixture")
        saved = [self.build / name for name in ("meson-logs/testlog.txt", "tests/failed/evidence", "unknown")]
        for path in saved:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep")
        self.assertIn("meson compile --clean -C", self.run_clean("--dry-run"))
        self.assertTrue(product.exists())
        with (
            patch.object(clean, "__file__", self.root / "scripts/clean.py"),
            patch.object(sys, "argv", ["clean"]),
            patch.dict(os.environ),
        ):
            os.environ.pop("MESON_BUILD_DIR", None)
            clean.main()
        self.assertFalse(product.exists())
        self.assertTrue((self.build / "meson-private/coredata.dat").is_file())
        self.assertTrue(all(path.read_bytes() == b"keep" for path in saved))

    def test_explicit_scratch_preview_removes_only_selections(self):
        old = self.root / "build/old-review"
        (old / "meson-logs").mkdir(parents=True)
        (old / "meson-logs/failure.log").write_bytes(b"reviewed old failure")
        selected_file = self.build / "old-dump.bin"
        selected_file.touch()
        survivor = self.build / "unrelated"
        survivor.write_bytes(b"keep")
        paths = f"{old} {selected_file}"
        preview = self.run_clean("--scratch", "--dry-run", CLEAN_PATHS=paths)
        self.assertIn("Would remove " + str(old), preview)
        self.assertTrue(selected_file.exists())
        self.assertTrue((old / "meson-logs/failure.log").is_file())
        self.run_clean("--scratch", CLEAN_PATHS=paths)
        self.assertFalse(old.exists())
        self.assertFalse(selected_file.exists())
        self.assertEqual(survivor.read_bytes(), b"keep")

    def test_scope_symlinks_and_keeps_refuse_without_removal(self):
        outside = self.root / "outside"
        outside.write_bytes(b"keep")
        alias = self.root / "build/alias"
        alias.symlink_to(outside)
        folder = self.build / "scratch"
        folder.mkdir()
        (folder / ".keep").touch()
        for selected in (self.root / "build", outside, alias, folder, folder / ".keep"):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.run_clean("--scratch", str(selected))
        self.assertEqual(outside.read_bytes(), b"keep")
        self.assertTrue((folder / ".keep").exists())

    def test_current_build_and_configuration_are_preserved(self):
        info = self.build / "meson-private"
        info.mkdir()
        (info / "coredata.dat").write_bytes(b"configuration")
        for selected in (self.build, info, info / "coredata.dat"):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.run_clean("--scratch", str(selected))
        self.assertEqual((info / "coredata.dat").read_bytes(), b"configuration")
        (self.build / "meson-info").mkdir()
        (self.build / "meson-info/meson-info.json").write_text(json.dumps({"directories": {"source": "/other"}}))
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.run_clean()

    def test_in_build_alias_preserves_canonical_ancestor_keep(self):
        kept = self.root / "build/kept"
        child = kept / "child"
        child.mkdir(parents=True)
        (kept / ".keep").touch()
        alias = self.root / "build/alias"
        alias.symlink_to(kept, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "kept output"):
            self.run_clean("--scratch", str(alias / "child"))
        self.assertTrue(child.is_dir())
        self.assertTrue((kept / ".keep").exists())

    def test_make_scratch_requires_selection_and_exports_paths(self):
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / "scripts/clean.py", self.root / "scripts/clean.py")
        shutil.copyfile(ROOT / "Makefile", self.root / "Makefile")
        scratch = self.build / "scratch"
        scratch.mkdir()
        env = {**os.environ, "MESON_BUILD_DIR": str(self.build), "CLEAN_PATHS": ""}
        command = ["make", "clean-scratch-dry-run"]
        result = subprocess.run(command, cwd=self.root, env=env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("select reviewed scratch", result.stderr)
        result = subprocess.run(
            command + [f"CLEAN_PATHS={scratch}"],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Would remove " + str(scratch), result.stdout)
        self.assertTrue(scratch.exists())


if __name__ == "__main__":
    unittest.main()

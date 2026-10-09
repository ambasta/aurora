#!/usr/bin/env python3
"""Compiler-free equivalence controls for the shared native artifact budget."""

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "compiler"))
import utf8_range as harness


def legacy_allocated_bytes(root):
    return root.stat().st_blocks * 512 + sum(p.lstat().st_blocks * 512 for p in root.rglob("*"))


class ArtifactBudget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-budget-control-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / "artifacts"
        self.root.mkdir()

    def suite(self):
        suite = harness.Suite.__new__(harness.Suite)
        suite.budget_root = self.root
        suite.compiler = self.home / "compiler"
        suite.args = SimpleNamespace(budget_mib=128, sanitized_compiler=False)
        return suite

    def test_empty_nested_files_sparse_file_and_hardlinks(self):
        self.assertEqual(harness.allocated_bytes(self.root), legacy_allocated_bytes(self.root))
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        (self.root / ".hidden").write_bytes(b"hidden")
        payload = nested / "file"
        payload.write_bytes(b"x" * 5000)
        (nested / "empty").touch()
        os.link(payload, self.root / "hardlink")
        with (nested / "sparse").open("wb") as stream:
            stream.seek(2 << 20)
            stream.write(b"x")
        expected = legacy_allocated_bytes(self.root)
        self.assertEqual(harness.allocated_bytes(self.root), expected)
        # Hardlink names remain charged individually; accounting is allocated blocks.
        (self.root / "hardlink").unlink()
        self.assertEqual(harness.allocated_bytes(self.root), expected - payload.stat().st_blocks * 512)

    def test_symlinks_are_counted_without_following_child_directories(self):
        outside = self.home / "outside"
        outside.mkdir()
        (outside / "excluded").write_bytes(b"x" * 16384)
        (self.root / "directory-link").symlink_to(outside, target_is_directory=True)
        (self.root / "file-link").symlink_to(outside / "excluded")
        (self.root / "dangling").symlink_to(outside / "missing")
        (self.root / "loop").symlink_to(self.root, target_is_directory=True)
        expected = self.root.stat().st_blocks * 512 + sum(p.lstat().st_blocks * 512 for p in self.root.iterdir())
        self.assertEqual(legacy_allocated_bytes(self.root), expected)
        self.assertEqual(harness.allocated_bytes(self.root), expected)
        # The root itself follows stat(), matching the preexisting calculation.
        link = self.home / "root-link"
        link.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(harness.allocated_bytes(link), legacy_allocated_bytes(link))

    def test_disappearing_entry_still_raises(self):
        real_scandir, real_lstat = os.scandir, Path.lstat
        victim = self.root / "vanishing"

        def disappearing_lstat(path, *args, **kwargs):
            if path == victim:
                victim.unlink()
            return real_lstat(path, *args, **kwargs)

        victim.touch()
        with patch.object(Path, "lstat", disappearing_lstat):
            with self.assertRaises(FileNotFoundError):
                legacy_allocated_bytes(self.root)

        @contextmanager
        def disappearing_scandir(path):
            with real_scandir(path) as entries:
                children = list(entries)
            # Remove after discovery, before the new walker's no-follow stat.
            victim.unlink()
            yield iter(children)

        victim.touch()
        with patch.object(os, "scandir", disappearing_scandir):
            with self.assertRaises(FileNotFoundError):
                harness.allocated_bytes(self.root)

    def test_stat_errors_are_not_suppressed(self):
        (self.root / "entry").touch()
        for code in (errno.ENOENT, errno.EACCES, errno.EIO):
            with self.subTest(errno=code):
                failure = OSError(code, "synthetic stat failure")
                entry = SimpleNamespace(stat=lambda **kwargs: (_ for _ in ()).throw(failure))
                with patch.object(os, "scandir") as scandir:
                    scandir.return_value.__enter__.return_value = iter([entry])
                    with self.assertRaises(OSError) as observed:
                        harness.allocated_bytes(self.root)
                self.assertIs(observed.exception, failure)
                with patch.object(Path, "lstat", side_effect=failure):
                    with self.assertRaises(OSError) as observed:
                        legacy_allocated_bytes(self.root)
                self.assertIs(observed.exception, failure)
        with patch.object(Path, "stat", side_effect=PermissionError("root stat")):
            with self.assertRaises(PermissionError):
                harness.allocated_bytes(self.root)

    def test_root_and_nested_enumeration_errors_fail_closed_without_retry(self):
        (self.root / "payload").write_bytes(b"x" * 16384)
        nested = self.root / "nested"
        nested.mkdir()
        (nested / "payload").write_bytes(b"x" * 16384)
        real_scandir = os.scandir
        for target in (self.root, nested):
            for code in (errno.ENOENT, errno.EACCES, errno.EIO):
                for transient in (False, True):
                    with self.subTest(target=target.name, errno=code, transient=transient):
                        failure = OSError(code, "synthetic scan failure")
                        calls = 0

                        def failing_scandir(path):
                            nonlocal calls
                            if Path(path) == target:
                                calls += 1
                                if not transient or calls == 1:
                                    raise failure
                            return real_scandir(path)

                        with patch.object(os, "scandir", failing_scandir):
                            with self.assertRaises(OSError) as observed:
                                harness.allocated_bytes(self.root)
                        self.assertIs(observed.exception, failure)
                        self.assertEqual(calls, 1)

    def test_mid_enumeration_error_closes_iterator_and_fails_closed(self):
        (self.root / "payload").write_bytes(b"x" * 16384)
        real_scandir = os.scandir
        failure = OSError(errno.EIO, "synthetic iteration failure")
        closed = 0

        @contextmanager
        def failing_scandir(path):
            nonlocal closed
            try:
                with real_scandir(path) as entries:

                    def failing_entries():
                        yield next(entries)
                        raise failure

                    yield failing_entries()
            finally:
                closed += 1

        with patch.object(os, "scandir", failing_scandir):
            with self.assertRaises(OSError) as observed:
                harness.allocated_bytes(self.root)
        self.assertIs(observed.exception, failure)
        self.assertEqual(closed, 1)

    def test_no_logical_size_fallback_when_allocated_blocks_are_unavailable(self):
        with patch.object(Path, "stat", return_value=SimpleNamespace(st_size=123)):
            for walker in (legacy_allocated_bytes, harness.allocated_bytes):
                with self.assertRaises(AttributeError):
                    walker(self.root)

    def test_budget_thresholds_and_invalid_root_are_unchanged(self):
        suite = self.suite()
        cap = suite.args.budget_mib << 20
        with patch.object(harness, "allocated_bytes", return_value=cap - harness.RESERVE) as count:
            with patch.object(
                harness.shutil, "disk_usage", return_value=SimpleNamespace(free=harness.FLOOR + harness.RESERVE + 1)
            ) as disk:
                self.assertEqual(suite.budget(), cap - harness.RESERVE)
                count.return_value += 1
                with self.assertRaisesRegex(AssertionError, "owned output budget exceeded"):
                    suite.budget()
                count.return_value = 0
                disk.return_value.free -= 1
                with self.assertRaisesRegex(AssertionError, "global free-space floor"):
                    suite.budget()
                disk.return_value.free = harness.FLOOR + 1
                self.assertEqual(suite.budget(0), 0)
                disk.return_value.free -= 1
                with self.assertRaisesRegex(AssertionError, "global free-space floor"):
                    suite.budget(0)
        suite.budget_root = self.home / "absent"
        with self.assertRaisesRegex(AssertionError, "budget root must be a directory"):
            suite.budget()

    def test_command_checks_before_and_after_success_or_failure(self):
        for code in (0, 1):
            with self.subTest(returncode=code):
                suite = self.suite()
                with patch.object(suite, "budget") as budget:
                    with patch.object(harness.subprocess, "run", return_value=subprocess.CompletedProcess([], code)):
                        if code:
                            with self.assertRaisesRegex(AssertionError, "exit 1; expected 0"):
                                suite.command(["synthetic-tool"], self.root, "command")
                        else:
                            self.assertEqual(suite.command(["synthetic-tool"], self.root, "command"), b"")
                self.assertEqual([call.args for call in budget.call_args_list], [(), (0,)])


if __name__ == "__main__":
    unittest.main()

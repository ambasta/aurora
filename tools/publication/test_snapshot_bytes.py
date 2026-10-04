#!/usr/bin/env python3
"""Local regression tests; fixtures are written only to temporary directories."""

import io
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import snapshot_bytes as sb


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-snapshot-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, fixtures):
        path = self.root / "fixture.tar"
        with tarfile.open(path, "w") as archive:
            for name, data, mode, kind in fixtures:
                member = tarfile.TarInfo(name)
                member.mode = mode
                member.type = kind
                if kind == tarfile.SYMTYPE or kind == tarfile.LNKTYPE:
                    member.linkname = data.decode("utf-8")
                    archive.addfile(member)
                elif kind == tarfile.REGTYPE:
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
                else:
                    archive.addfile(member)
        return path

    def entry(self, path, data, mode="100644"):
        return {"path": path, "mode": mode, "type": "blob", "content": data.decode("utf-8")}

    def test_text_roundtrip_crlf_lf_unicode_empty_lone_cr_nul_no_final_newline(self):
        samples = {
            "crlf.log": b"first\r\nsecond\r\n",
            "lf.log": b"first\nsecond\n",
            "mixed.log": b"first\r\nsecond\nthird\rfin",
            "unicode-\u03bb.txt": "Aurora \u03bb \u00e9 \U0001f30c\r\n".encode(),
            "empty": b"",
            "no-final-newline": b"last",
            "nul": b"a\0b\r\n",
        }
        archive = self.archive([("aurora/" + path, data, 0o644, tarfile.REGTYPE) for path, data in samples.items()])
        entries = sb.snapshot_archive(archive)
        output = self.root / "tree.json"
        sb.write_json_new(output, entries)
        observed = {entry["path"]: entry["content"].encode() for entry in sb.read_snapshot(output)}
        self.assertEqual(observed, samples)

    def test_reproduces_old_read_text_newline_loss(self):
        path = self.root / "serial.log"
        path.write_bytes(b"boot\r\npass\r\n")
        self.assertNotEqual(path.read_text().encode(), path.read_bytes())
        self.assertEqual(sb.decode_exact(path.read_bytes()).encode(), path.read_bytes())

    def test_preserves_regular_and_executable_modes(self):
        archive = self.archive([("aurora/a", b"a", 0o644, tarfile.REGTYPE), ("aurora/b", b"b", 0o755, tarfile.REGTYPE)])
        self.assertEqual([entry["mode"] for entry in sb.snapshot_archive(archive)], ["100644", "100755"])

    def test_preserves_symlink_target_without_dereferencing(self):
        archive = self.archive([("aurora/link", b"../nonexistent", 0o777, tarfile.SYMTYPE)])
        self.assertEqual(sb.snapshot_archive(archive), [self.entry("link", b"../nonexistent", "120000")])

    def test_ignores_explicit_empty_directories(self):
        archive = self.archive([("aurora", b"", 0o755, tarfile.DIRTYPE), ("aurora/empty", b"", 0o755, tarfile.DIRTYPE)])
        self.assertEqual(sb.snapshot_archive(archive), [])

    def test_supports_legacy_dot_prefix(self):
        archive = self.archive([(".", b"", 0o755, tarfile.DIRTYPE), ("./a", b"a\r\n", 0o644, tarfile.REGTYPE)])
        self.assertEqual(sb.snapshot_archive(archive, prefix=""), [self.entry("a", b"a\r\n")])

    def test_rejects_non_utf8_without_replacement(self):
        archive = self.archive([("aurora/a", b"\xff", 0o644, tarfile.REGTYPE)])
        with self.assertRaises(UnicodeDecodeError):
            sb.snapshot_archive(archive)

    def test_rejects_non_git_permissions(self):
        for mode in (0o600, 0o664, 0o4755, 0o744):
            with self.subTest(mode=oct(mode)):
                archive = self.archive([("aurora/a", b"a", mode, tarfile.REGTYPE)])
                with self.assertRaisesRegex(ValueError, "permissions"):
                    sb.snapshot_archive(archive)

    def test_rejects_hardlinks_and_special_files(self):
        for kind in (tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE):
            with self.subTest(kind=kind):
                archive = self.archive([("aurora/a", b"target", 0o644, kind)])
                with self.assertRaisesRegex(ValueError, "Unsupported tar member"):
                    sb.snapshot_archive(archive)

    def test_rejects_unsafe_paths_and_prefix_mismatch(self):
        for name in ("aurora/../escape", "aurora/.git/config", "aurora/a//b", "aurora/a/./b", "/aurora/a", "other/a"):
            with self.subTest(name=name):
                archive = self.archive([(name, b"a", 0o644, tarfile.REGTYPE)])
                with self.assertRaises(ValueError):
                    sb.snapshot_archive(archive)

    def test_rejects_duplicate_paths(self):
        archive = self.archive([("aurora/a", b"a", 0o644, tarfile.REGTYPE), ("aurora/a", b"b", 0o644, tarfile.REGTYPE)])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sb.snapshot_archive(archive)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sb.index_entries([self.entry("a", b"a"), self.entry("a", b"b")])

    def test_rejects_file_directory_collision(self):
        for fixtures in (
            [("aurora/a", b"a", 0o644, tarfile.REGTYPE), ("aurora/a/b", b"b", 0o644, tarfile.REGTYPE)],
            [("aurora/a", b"a", 0o644, tarfile.REGTYPE), ("aurora/a/b", b"", 0o755, tarfile.DIRTYPE)],
        ):
            with self.subTest(fixtures=fixtures):
                archive = self.archive(fixtures)
                with self.assertRaisesRegex(ValueError, "collision"):
                    sb.snapshot_archive(archive)

    def test_output_refuses_overwrite(self):
        path = self.root / "existing.json"
        path.write_bytes(b"original\r\n")
        with self.assertRaises(FileExistsError):
            sb.write_json_new(path, [])
        self.assertEqual(path.read_bytes(), b"original\r\n")

    def test_delta_add_change_mode_delete_reconstructs_target(self):
        base = [self.entry("old", b"remove"), self.entry("same", b"same"), self.entry("run", b"#!/bin/sh\n"), self.entry("serial", b"pass\n")]
        target = [self.entry("new", b"\0"), self.entry("same", b"same"), self.entry("run", b"#!/bin/sh\n", "100755"), self.entry("serial", b"pass\r\n")]
        delta = sb.make_delta(base, target, sb.git_tree_id(base))
        self.assertEqual(len(delta), 4)
        self.assertEqual(sb.index_entries(sb.apply_delta(base, delta)), sb.index_entries(target))
        self.assertEqual(sb.git_tree_id(sb.apply_delta(base, delta)), sb.git_tree_id(target))

    def test_delta_rejects_wrong_base_and_duplicate_deletion(self):
        base = [self.entry("a", b"a")]
        with self.assertRaisesRegex(ValueError, "expected published"):
            sb.make_delta(base, [], "0" * 40)
        deletion = {"path": "a", "mode": "100644", "type": "blob", "sha": None}
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sb.apply_delta(base, [deletion, deletion])

    def test_git_known_empty_object_ids(self):
        self.assertEqual(sb.git_object_id("blob", b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertEqual(sb.git_tree_id([]), "4b825dc642cb6eb9a060e54bf8d69288fbee4904")

    @unittest.skipUnless(shutil.which("git"), "Git unavailable: independent tree-hash check cannot run")
    def test_tree_hash_matches_git_for_ordering_unicode_modes_and_symlink(self):
        repo = self.root / "objects.git"
        subprocess.run(["git", "init", "--bare", "--quiet", str(repo)], check=True)
        entries = [self.entry("dir/file", b"inside\r\n"), self.entry("dir.txt", b"nearby"), self.entry("dir0", b"next"), self.entry("\u03bb", "\u2603".encode()), self.entry("run", b"#!/bin/sh\n", "100755"), self.entry("link", b"dir/file", "120000")]
        root = {}
        for entry in entries:
            sha = subprocess.check_output(["git", "--git-dir", str(repo), "hash-object", "-w", "--stdin"], input=entry["content"].encode()).strip()
            parent = root
            parts = entry["path"].split("/")
            for part in parts[:-1]:
                parent = parent.setdefault(part, {})
            parent[parts[-1]] = (entry["mode"].encode(), b"blob", sha)

        def git_tree(directory):
            records = []
            for name, value in directory.items():
                mode, kind, sha = (b"040000", b"tree", git_tree(value)) if isinstance(value, dict) else value
                records.append(mode + b" " + kind + b" " + sha + b"\t" + name.encode() + b"\0")
            return subprocess.check_output(["git", "--git-dir", str(repo), "mktree", "-z"], input=b"".join(records)).strip()

        self.assertEqual(sb.git_tree_id(entries), git_tree(root).decode())


if __name__ == "__main__":
    unittest.main(verbosity=2)

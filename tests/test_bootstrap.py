#!/usr/bin/env python3
"""Compiler-free controls for checkpoint selection and the one-hop bump driver."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bootstrap

# A fake meson: setup makes the build directory, compile writes both compilers,
# test fails when FAKE_MESON_FAIL_TEST is set.
FAKE_MESON = r"""
import os, pathlib, sys
args = sys.argv[1:]
if args[0] == 'setup':
    pathlib.Path(args[1]).mkdir()
elif args[0] == 'compile':
    out = pathlib.Path(args[args.index('-C') + 1])
    for name, text in (('aurorac', 'c1'), ('aurorac-stage2', 'c2')):
        (out / name).write_text('#!/bin/sh\n# ' + text + '\n')
        (out / name).chmod(0o755)
elif args[0] == 'test' and os.environ.get('FAKE_MESON_FAIL_TEST'):
    print('convergence failed'); sys.exit(1)
"""


def executable(path, text):
    path.write_text("#!/bin/sh\n# " + text + "\n")
    path.chmod(0o755)
    return path


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.compiler = executable(self.root / "checkpoint", "checkpoint")
        self.oracle = executable(self.root / "oracle", "oracle")
        pin = self.root / "checkpoint.json"
        pin.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "checkpoint": {"commit": "1" * 40, "tree": "2" * 40, "sha256": bootstrap.digest(self.compiler)},
                    "historical_oracle": {"commit": "3" * 40, "sha256": bootstrap.digest(self.oracle)},
                }
            )
        )
        patcher = patch.object(bootstrap, "CHECKPOINT", pin)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_checked_in_pin_names_two_distinct_roles(self):
        with patch.object(bootstrap, "CHECKPOINT", bootstrap.ROOT / "compiler/checkpoint.json"):
            value = bootstrap.pin()
        self.assertNotEqual(value["checkpoint"]["sha256"], value["historical_oracle"]["sha256"])
        self.assertNotEqual(value["checkpoint"]["commit"], value["historical_oracle"]["commit"])

    def test_select_accepts_only_the_pinned_bytes(self):
        lines = bootstrap.select(str(self.compiler), str(self.oracle))
        self.assertEqual(lines[0::2], [str(self.compiler), str(self.oracle)])
        self.assertEqual(bootstrap.select(str(self.compiler))[2:], ["", ""])
        for compiler, oracle in (
            (str(self.oracle), ""),  # the oracle is not the checkpoint
            (str(self.compiler), str(self.compiler)),
            ("checkpoint", ""),  # relative
            ("", ""),
            (str(self.root / "missing"), ""),
        ):
            with self.subTest(compiler=compiler, oracle=oracle), self.assertRaisesRegex(ValueError, "rejected"):
                bootstrap.select(compiler, oracle)
        executable(self.compiler, "changed")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            bootstrap.select(str(self.compiler))

    def test_tree_identity_matches_git(self):
        # `git rev-parse HEAD^{tree}` after committing this exact layout.
        source = self.root / "source"
        (source / "a/b").mkdir(parents=True)
        (source / "e").mkdir()  # empty directories are not recorded
        (source / "a/b/f").write_text("x\n")
        executable(source / "run", "x").write_text("#!/bin/sh\n")
        (source / "a.txt").write_text("y")
        (source / "link").symlink_to("a.txt")
        (source / ".git").write_text("gitdir: elsewhere\n")
        self.assertEqual(bootstrap.git_tree(source), "6c440e2d738bcf0138e2c063b2c08e509e06a592")
        (source / "run").chmod(0o644)
        self.assertNotEqual(bootstrap.git_tree(source), "6c440e2d738bcf0138e2c063b2c08e509e06a592")

    def hop(self, *extra, env=None):
        source = self.root / "source"
        source.mkdir(exist_ok=True)
        (source / "meson.build").write_text("project('fixture')\n")
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "meson").write_text("#!" + sys.executable + "\n" + FAKE_MESON)
        (bin_dir / "meson").chmod(0o755)
        arguments = [
            "hop",
            "--compiler",
            str(self.compiler),
            "--oracle",
            str(self.oracle),
            "--source",
            str(source),
            "--commit",
            "4" * 40,
            "--tree",
            bootstrap.git_tree(source),
            "--output",
            str(self.root / "out"),
            *extra,
        ]
        environment = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", **(env or {})}
        with (
            patch.object(sys, "argv", ["bootstrap.py", *arguments]),
            patch.dict(os.environ, environment, clear=True),
            patch.object(bootstrap, "tools", return_value={"versions": {}}),
        ):
            bootstrap.main()
        return self.root / "out"

    def test_hop_records_the_checkpoint_and_its_predecessor(self):
        output = self.hop()
        receipt = json.loads((output / "receipt.json").read_text())
        self.assertEqual(receipt["checkpoint"]["sha256"], bootstrap.digest(output / "aurorac"))
        self.assertEqual(receipt["checkpoint"]["sha256"], bootstrap.digest(output / "build/aurorac-stage2"))
        self.assertEqual(receipt["predecessor"]["sha256"], bootstrap.digest(self.compiler))
        self.assertEqual(receipt["historical_oracle"]["sha256"], bootstrap.digest(self.oracle))
        setup, compile_, test = (record["argv"] for record in receipt["commands"])
        self.assertIn("-Dbootstrap_compiler=" + str(self.compiler), setup)
        self.assertIn("-Dhistorical_oracle=" + str(self.oracle), setup)
        self.assertEqual(compile_[-2:], ["aurorac", "aurorac-stage2"])
        self.assertEqual(tuple(test[-3:]), bootstrap.HOP_TESTS)

    def test_hop_expect_rejects_a_different_rebuild(self):
        with self.assertRaisesRegex(ValueError, "differs from the expected pin"):
            self.hop("--expect", "0" * 64)

    def test_hop_rejects_wrong_tree_failed_tests_and_reused_output(self):
        with self.assertRaisesRegex(ValueError, "retained log"):
            self.hop(env={"FAKE_MESON_FAIL_TEST": "1"})
        self.assertIn("convergence failed", (self.root / "out/2.log").read_text())
        self.assertFalse((self.root / "out/aurorac").exists())
        with self.assertRaises(FileExistsError):
            self.hop()
        with self.assertRaisesRegex(ValueError, "source tree"):
            self.hop("--tree", "0" * 40, "--output", str(self.root / "other"))


if __name__ == "__main__":
    unittest.main()

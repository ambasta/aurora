#!/usr/bin/env python3
"""Mutation controls for the checker, always exercised both normally and with -O."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parent.parent
CHECKER = PACKAGE / "model/check_traceability.py"
DOCUMENTS = ("README.md", "original-requirements.md", "requirements.md", "traceability.md", "roadmap.md", "sources.md")


class TraceabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-storage-trace-")
        self.root = Path(self.temp.name)
        for name in DOCUMENTS:
            shutil.copyfile(PACKAGE / name, self.root / name)

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, name, transform):
        path = self.root / name
        path.write_text(transform(path.read_text()))

    def run_checker(self, expected, error=""):
        for optimize in (False, True):
            args = [sys.executable] + (["-O"] if optimize else [])
            args += [str(CHECKER), "--root", str(self.root)]
            result = subprocess.run(args, capture_output=True, text=True, check=False)
            with self.subTest(optimize=optimize):
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected:
                    self.assertIn(error, result.stderr)
                    self.assertNotIn("PASS:", result.stdout)
                else:
                    self.assertIn("PASS:", result.stdout)

    def test_unchanged_package_passes_both_modes(self):
        self.run_checker(0)

    def test_mutated_original_same_length_fails_both_modes(self):
        path = self.root / "original-requirements.md"
        data = path.read_bytes()
        path.write_bytes(bytes((data[0] ^ 1,)) + data[1:])
        self.run_checker(1, "input hash changed")

    def test_missing_trace_row_fails_both_modes(self):
        self.edit(
            "traceability.md",
            lambda text: "\n".join(line for line in text.splitlines() if not line.startswith("| R01 |")),
        )
        self.run_checker(1, "trace numbering")

    def test_duplicated_trace_row_fails_both_modes(self):
        self.edit(
            "traceability.md",
            lambda text: text + next(line for line in text.splitlines() if line.startswith("| R01 |")) + "\n",
        )
        self.run_checker(1, "trace numbering")

    def test_unknown_gate_reference_fails_both_modes(self):
        self.edit("traceability.md", lambda text: text.replace("| S4,S5,X1,X3 |", "| S99 |", 1))
        self.run_checker(1, "unknown gates in R01")

    def test_unknown_adapted_section_fails_both_modes(self):
        self.edit(
            "requirements.md", lambda text: text.replace("## 56. Long-Term Direction", "## 99. Long-Term Direction")
        )
        self.run_checker(1, "adapted numbering")

    def test_unknown_roadmap_stage_fails_both_modes(self):
        self.edit("roadmap.md", lambda text: text.replace("## S11.", "## S99."))
        self.run_checker(1, "stage inventory")

    def test_duplicate_roadmap_stage_fails_both_modes(self):
        self.edit("roadmap.md", lambda text: text + "\n## S11. Duplicate stage\n")
        self.run_checker(1, "duplicated stage")


if __name__ == "__main__":
    print("HOST-ONLY document checker mutation controls; disposable copies only", flush=True)
    unittest.main(verbosity=2)

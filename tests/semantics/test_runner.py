#!/usr/bin/env python3
"""Test the independent oracle and ensure harness failures cannot become passes."""

import signal
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import run


class OracleTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(run.checked(run.MIN), run.MIN)
        self.assertEqual(run.checked(run.MAX), run.MAX)
        for value in (run.MIN - 1, run.MAX + 1):
            with self.assertRaises(run.Trap):
                run.checked(value)
        self.assertEqual(run.expected_expr(("*", ("lit", run.MIN), ("lit", -1))), {"trap": "overflow"})
        self.assertEqual(run.expected_expr(("-", ("lit", run.MIN), ("lit", run.MIN))), {"value": 0})

    def test_bounds_before_rhs(self):
        with self.assertRaisesRegex(run.Trap, "bounds"):
            run.execute([("store", "a", ("lit", -1), ("+", ("lit", run.MAX), ("lit", 1)))], {"a": [0]})

    def test_left_operand_before_right(self):
        with self.assertRaisesRegex(run.Trap, "bounds"):
            run.evaluate(("+", ("get", "a", ("lit", -1)), ("neg", ("lit", run.MIN))), {"a": [0]})

    def test_ownership_model_counts(self):
        traces = list(run.ownership_cases())[:64]
        self.assertEqual(sum("value" in expectation for _, _, expectation in traces), 10)


class HarnessTests(unittest.TestCase):
    def fake_check(self, expected, status, output=b"", compiler_status=0, diagnostic=b""):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            calls = [
                subprocess.CompletedProcess([], compiler_status, b"", diagnostic),
                subprocess.CompletedProcess([], status, output, b""),
            ]
            with patch.object(run, "command", side_effect=calls), patch.object(run, "must_run"):
                return run.check(Path("/unused"), directory, run.source("return 0;"), expected)

    def test_exact_sigill(self):
        self.assertEqual(self.fake_check({"trap": "overflow"}, -signal.SIGILL), "overflow")
        for status in (0, 1, 132, -signal.SIGSEGV, -signal.SIGABRT, -signal.SIGKILL):
            with self.subTest(status=status), self.assertRaises(AssertionError):
                self.fake_check({"trap": "overflow"}, status)

    def test_full_width_result(self):
        for value in (run.MIN, run.MAX, -1, 0, 256):
            self.assertEqual(self.fake_check({"value": value}, 0, struct.pack("<q", value)), "value")
        with self.assertRaises(AssertionError):
            self.fake_check({"value": 256}, 0, struct.pack("<q", 0))
        with self.assertRaises(AssertionError):
            self.fake_check({"value": 0}, 0, b"")
        with self.assertRaises(AssertionError):
            self.fake_check({"value": 0}, -signal.SIGILL)

    def test_sanitized_compiler_keeps_other_limits(self):
        with patch.object(run.resource, "setrlimit") as setting:
            run.limits(True)
            self.assertEqual(
                setting.call_args_list,
                [
                    unittest.mock.call(run.resource.RLIMIT_CORE, (0, 0)),
                    unittest.mock.call(run.resource.RLIMIT_CPU, (3, 3)),
                    unittest.mock.call(run.resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2),
                ],
            )
            setting.reset_mock()
            run.limits()
            self.assertIn(unittest.mock.call(run.resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2), setting.call_args_list)

    def test_sanitized_option_applies_only_to_compiler(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = [
                subprocess.CompletedProcess([], 0, b"", b""),
                subprocess.CompletedProcess([], 0, struct.pack("<q", 42), b""),
            ]
            with patch.object(run, "command", side_effect=calls) as command, patch.object(run, "must_run"):
                self.assertEqual(
                    run.check(Path("/compiler"), Path(temp), run.source("return 42;"), {"value": 42}, True), "value"
                )
                self.assertEqual(command.call_args_list[0].kwargs, {"sanitized_compiler": True})
                self.assertEqual(command.call_args_list[1].kwargs, {})

    def test_rejection_is_not_a_crash(self):
        self.assertEqual(self.fake_check({"reject": True}, 0, compiler_status=1, diagnostic=b"error"), "rejected")
        for status, diagnostic in ((0, b"error"), (-signal.SIGSEGV, b"error"), (1, b"")):
            with self.subTest(status=status), self.assertRaises(AssertionError):
                self.fake_check({"reject": True}, 0, compiler_status=status, diagnostic=diagnostic)


if __name__ == "__main__":
    unittest.main()

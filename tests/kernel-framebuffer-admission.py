#!/usr/bin/env python3
"""Defensive local model mutations for graphics stack/admission guards; no guest."""

from pathlib import Path
import importlib.util
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("graphics_admission", ROOT / "scripts/kernel_framebuffer_admission.py")
graphics = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = graphics
spec.loader.exec_module(graphics)
decoder = graphics.load("graphics_guard_decoder", ROOT / "scripts/kernel_stack.py")


class Guards(unittest.TestCase):
    def test_bridge_indirect_and_fault_reserve_reject(self):
        ops = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("mov", "%rdi,%r11"),
            ("call", "100 <entry>"),
            ("leave", ""),
            ("ret", ""),
        ]

        def body(rows):
            return [decoder.Instruction(i, 1, op, args) for i, (op, args) in enumerate(rows)]

        graphics.console.verify_bridge_body(decoder, body(ops), {256: graphics.ENTRY})
        for index, replacement in [
            (2, ("mov", "%rsi,%r11")),
            (3, ("call", "*%rax")),
            (3, ("call", "101 <wrong>")),
            (5, ("ret", "$0x8")),
        ]:
            changed = list(ops)
            changed[index] = replacement
            with self.assertRaises(ValueError):
                graphics.console.verify_bridge_body(decoder, body(changed), {256: graphics.ENTRY})
        graphics.verify_value_bridge(decoder, body([("jmp", "100 <value>")]), {256: "aurora_kernel_value"})
        for changed in (
            [("call", "100 <value>")],
            [("jmp", "101 <wrong>")],
            [("push", "%rax"), ("jmp", "100 <value>")],
        ):
            with self.assertRaises(ValueError):
                graphics.verify_value_bridge(decoder, body(changed), {256: "aurora_kernel_value"})
        graphics.verify_stack_budget(15000, 360)
        for normal, fault in [(15001, 360), (0, -1), (True, 0), (16384, 0)]:
            with self.assertRaises(ValueError):
                graphics.verify_stack_budget(normal, fault)

    def test_checked_admission_binds_exact_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            output = build / "payload.bin"
            output.write_bytes(b"checked image")

            def hashes(paths):
                return {str(path.relative_to(build)): graphics.common.digest(path) for path in paths}

            receipt = dict(
                schema="aurora-framebuffer-admission-v1",
                status="requires-independent-review",
                mode="framebuffer",
                clock="tcg-original-clock",
                sha256=hashes([output]),
            )
            path = build / "framebuffer-admission.json"
            with (
                patch.object(graphics, "BUILD", build),
                patch.object(graphics, "build_files", return_value=[output]),
                patch.object(graphics.common, "hashes", side_effect=hashes),
            ):

                def check(value):
                    path.write_text(json.dumps(value))
                    return graphics.checked("framebuffer")

                self.assertEqual(check(receipt), receipt)
                for key, bad in [
                    ("mode", "framebuffer-stale"),
                    ("clock", "icount"),
                    ("status", "approved"),
                    ("schema", "changed"),
                    ("sha256", {}),
                    ("sha256", {**receipt["sha256"], "foreign": "0" * 64}),
                ]:
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        check(receipt | {key: bad})
                path.write_text(json.dumps(receipt))
                output.write_bytes(b"changed image")
                with self.assertRaises(ValueError):
                    graphics.checked("framebuffer")
                output.write_bytes(b"checked image")
                self.assertEqual(graphics.checked("framebuffer"), receipt)
                path.unlink()
                with self.assertRaises(graphics.common.Blocked):
                    graphics.checked("framebuffer")


if __name__ == "__main__":
    unittest.main()

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
decoder = graphics.load("graphics_guard_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")


class Guards(unittest.TestCase):
    def test_existing_fail_closed_instruction_recursion_graph_controls(self):
        decoder.self_test()

    def test_immediate_push_requires_exact_machine_width_and_value(self):
        for value, raw in [("$0x0", bytes.fromhex("6a00")), ("$0x28", bytes.fromhex("6a28"))]:
            row = decoder.Instruction(0, 2, "push", value)
            converted, receipt = graphics.normalize_instruction(decoder, row, raw)
            self.assertEqual(converted.args, "%rax")
            self.assertEqual(receipt["bytes"], raw.hex())
        for value, raw in [
            ("$0x0", bytes.fromhex("666a00")),
            ("$0x0", bytes.fromhex("6a28")),
            ("$0x28", bytes.fromhex("6a00")),
            ("$0x1", bytes.fromhex("6a01")),
            ("$0x100", bytes.fromhex("6800010000")),
            ("$0x0", bytes.fromhex("6a")),
        ]:
            with self.assertRaises(ValueError):
                graphics.normalize_instruction(decoder, decoder.Instruction(0, len(raw), "push", value), raw)

    def test_memory_push_and_wide_stack_arithmetic_not_silently_normalized(self):
        for op, args in [
            ("push", "(%rsp)"),
            ("push", "0x10000(%rsp)"),
            ("push", "-0x8(%rsp)"),
            ("push", "(%rsp,%rax,8)"),
            ("sub", "$0xfffffffffffffff0,%rsp"),
        ]:
            row = decoder.Instruction(0, 1, op, args)
            same, receipt = graphics.normalize_instruction(decoder, row, b"\x90")
            self.assertEqual(same, row)
            self.assertIsNone(receipt)
            instructions = {0: row, 1: decoder.Instruction(1, 1, "ret", "")}
            with self.assertRaises(ValueError):
                decoder.analyze_function(decoder.Symbol("sample", 0, 2, 1, 2), instructions, {0: "sample"})

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
        graphics.verify_stack_budget(15000, 360)
        for normal, fault in [(15001, 360), (0, -1), (True, 0), (16384, 0)]:
            with self.assertRaises(ValueError):
                graphics.verify_stack_budget(normal, fault)

    def test_build_identity_rejects_metadata_source_and_output_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.cpp"
            source.write_text("source")
            compiler = root / "compiler"
            compiler.write_text("compiler")
            cxx = root / "cxx"
            cxx.write_text("host")

            def hashes(paths):
                return {str(path): graphics.common.digest(path) for path in paths}

            record = dict(
                schema="aurora-framebuffer-build-v1",
                mode="framebuffer",
                flags=[
                    "-DAURORA_UEFI_FRAMEBUFFER",
                    "-DAURORA_UEFI_FRAMEBUFFER_FIXTURE",
                    "-DAURORA_UEFI_FRAMEBUFFER_CAPTURE",
                ],
                source_sha256=hashes([source]),
                compiler=dict(path=str(compiler), sha256=graphics.common.digest(compiler)),
                cxx=dict(path=str(cxx), sha256=graphics.common.digest(cxx)),
            )
            with (
                patch.object(graphics.common, "source_files", return_value=[source]),
                patch.object(graphics.common, "hashes", side_effect=hashes),
            ):
                graphics.inputs(record, "framebuffer")
                for name in ("source", "compiler", "cxx"):
                    path = {"source": source, "compiler": compiler, "cxx": cxx}[name]
                    old = path.read_bytes()
                    path.write_bytes(old + b"drift")
                    with self.assertRaises(ValueError):
                        graphics.inputs(record, "framebuffer")
                    path.write_bytes(old)
                changed = json.loads(json.dumps(record))
                changed["flags"].append("-DAURORA_UEFI_CONSOLE")
                with self.assertRaises(ValueError):
                    graphics.inputs(changed, "framebuffer")
                with self.assertRaises(ValueError):
                    graphics.inputs(record, "framebuffer-stale")

    def test_developer_checked_admission_binds_exact_current_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            record = {"output_sha256": {"output": "hash"}}
            receipt = dict(
                schema="aurora-framebuffer-admission-v1",
                status="requires-independent-review",
                mode="framebuffer",
                clock="tcg-original-clock",
                build=record,
                sha256={"complete": "hash"},
            )
            (build / "framebuffer-build.json").write_text(json.dumps(record))
            path = build / "framebuffer-admission.json"
            with (
                patch.object(graphics, "BUILD", build),
                patch.object(graphics, "inputs") as inputs,
                patch.object(graphics, "build_files", return_value=[build / "output"]),
                patch.object(graphics.common, "source_files", return_value=[]),
                patch.object(graphics.common, "hashes") as hashes,
            ):

                def check(value):
                    path.write_text(json.dumps(value))
                    hashes.side_effect = [{"output": "hash"}, {"complete": "hash"}]
                    return graphics.checked("framebuffer")

                self.assertEqual(check(receipt), receipt)
                inputs.assert_called_with(record, "framebuffer")
                for key, bad in [
                    ("mode", "framebuffer-stale"),
                    ("clock", "icount"),
                    ("status", "approved"),
                    ("schema", "changed"),
                    ("build", {}),
                    ("sha256", {}),
                ]:
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        check(receipt | {key: bad})
                path.write_text(json.dumps(receipt))
                hashes.side_effect = [{"changed": "hash"}]
                with self.assertRaises(ValueError):
                    graphics.checked("framebuffer")
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    graphics.checked("framebuffer")


if __name__ == "__main__":
    unittest.main()

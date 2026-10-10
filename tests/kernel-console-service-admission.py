#!/usr/bin/env python3
"""Native-free hostile guard tests; no image execution or acceptance pin minting."""

from pathlib import Path
import importlib.util
from copy import deepcopy
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("service_admission", ROOT / "scripts/kernel_console_service_admission.py")
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
spec.loader.exec_module(service)
decoder = service.load("service_guard_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")


def body(operations):
    return [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(operations)]


class Admission(unittest.TestCase):
    def test_reflection_image_ownership_and_body_wiring(self):
        names = ("aurora_reflect_size", "aurora_reflect_field_count", "__au_reflect_s4_size")
        symbols = [decoder.Symbol(name, index, 1, 1, 2) for index, name in enumerate(names)]
        original = SimpleNamespace(functions={row.name: row for row in symbols}, symbols=symbols, relocations=[])
        code = {row.address: decoder.Instruction(row.address, 1, "ret", "") for row in symbols}
        with tempfile.TemporaryDirectory(prefix="reflection-image-") as directory:
            root = Path(directory)
            (root / "payload.bin").write_bytes(b"\xc3" * len(symbols))
            objects = {"language.o": deepcopy(original), "payload.elf": deepcopy(original)}
            fake = SimpleNamespace(Elf=lambda path: objects[path.name], disassemble=lambda path: (code, ""))
            with (
                patch.object(service.common, "load", return_value=fake),
                patch.object(fake, "associate_object", create=True) as associate,
                patch.object(service.common, "verify_reflection_body", return_value={}) as body_check,
            ):
                self.assertEqual(len(service.common.verify_reflection_image(root)), len(names))
                self.assertEqual(associate.call_count, len(names))
                self.assertEqual({call.args[1].name for call in body_check.call_args_list}, set(names))
                for mutation in ("untyped", "missing", "foreign", "relocation"):
                    objects = {"language.o": deepcopy(original), "payload.elf": deepcopy(original)}
                    if mutation == "untyped":
                        objects["language.o"].symbols.append(decoder.Symbol("__au_reflect_s5_size", 4, 1, 1, 0))
                    elif mutation == "missing":
                        objects["payload.elf"].symbols.pop()
                    elif mutation == "foreign":
                        objects["payload.elf"].symbols.append(decoder.Symbol("__au_reflect_s5_size", 4, 1, 1, 2))
                    else:
                        objects["language.o"].relocations = [(1, 0, 2, "foreign", 0)]
                    with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                        service.common.verify_reflection_image(root)
                objects = {"language.o": deepcopy(original), "payload.elf": deepcopy(original)}
                associate.side_effect = ValueError("Object/link instruction mismatch")
                with self.assertRaisesRegex(ValueError, "Object/link instruction mismatch"):
                    service.common.verify_reflection_image(root)
                associate.side_effect = None
                body_check.side_effect = ValueError("Reflection operand is not an immediate scalar")
                with self.assertRaisesRegex(ValueError, "Reflection operand"):
                    service.common.verify_reflection_image(root)

    def test_exact_session_byte_count_divisions(self):
        owner = "__au_m_m2_7console13session_files_n2_7console12SessionFiles_d6submit"
        self.assertEqual(service.SESSION_FILE_DIVISIONS, {owner: 2})
        symbol = decoder.Symbol(owner, 0, 11, 1, 2)
        code = {
            0: decoder.Instruction(0, 2, "cqto", ""),
            2: decoder.Instruction(2, 3, "idiv", "%r11"),
            5: decoder.Instruction(5, 2, "cqto", ""),
            7: decoder.Instruction(7, 3, "idiv", "%r11"),
            10: decoder.Instruction(10, 1, "ret", ""),
        }
        payload = bytes.fromhex("489949f7fb489949f7fbc3")

        def verify(functions, instructions, raw):
            return service.verify_generated_divisions(
                decoder, functions, instructions, raw, service.SESSION_FILE_DIVISIONS
            )

        evidence = verify({owner: symbol}, code, payload)
        self.assertEqual([row["owner"] for row in evidence], [owner, owner])
        original = decoder.NEUTRAL, decoder.READ_ONLY, decoder.PRESERVE_FLAGS
        try:
            decoder.configure_console("service")
            self.assertTrue({"cqto", "idiv"} <= decoder.NEUTRAL)
            self.assertIn("cqto", decoder.PRESERVE_FLAGS)
            self.assertNotIn("idiv", decoder.PRESERVE_FLAGS)
            result = decoder.analyze_function(symbol, code, {0: owner})
            self.assertEqual((result["local_peak"], result["returns"]), (8, 1))
        finally:
            decoder.NEUTRAL, decoder.READ_ONLY, decoder.PRESERVE_FLAGS = original
        for index in range(10):
            raw = bytearray(payload)
            raw[index] ^= 1
            with self.subTest(byte=index), self.assertRaises(ValueError):
                verify({owner: symbol}, code, raw)
        for mutation in ("missing-owner", "outside-owner", "missing-pair", "extra-pair", "operands", "no-payload"):
            functions, instructions, raw = {owner: symbol}, dict(code), payload
            if mutation == "missing-owner":
                functions = {}
            elif mutation == "outside-owner":
                functions[owner] = decoder.Symbol(owner, 1, 10, 1, 2)
            elif mutation == "missing-pair":
                del instructions[0]
                del instructions[2]
            elif mutation == "extra-pair":
                instructions[11] = decoder.Instruction(11, 2, "cqto", "")
                instructions[13] = decoder.Instruction(13, 3, "idiv", "%r11")
            elif mutation == "operands":
                instructions[2] = decoder.Instruction(2, 3, "idiv", "(%r11)")
            else:
                raw = None
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                verify(functions, instructions, raw)

    def test_unchanged_whole_stack_and_separate_irq_reserve(self):
        service.verify_stack_budgets(6912, 720, 639, 159)
        service.verify_stack_budgets(15201, 720, 639, 159)
        service.verify_stack_budgets(1, 12304, 2048, 1008)
        service.verify_stack_budgets(1, 1, 4000, 96)
        for values in (
            (15202, 720, 639, 159),
            (1, 12305, 2048, 1008),
            (1, 1, 4001, 96),
            (1, 1, -1, 0),
            (1, 1, True, 0),
        ):
            with self.assertRaises(ValueError):
                service.verify_stack_budgets(*values)

    def test_irq_checks_every_branch(self):
        functions = {
            "uefi_console_interrupt_dispatch": {"calls": [{"target": "large"}, {"target": "short"}]},
            "large": {"calls": []},
            "short": {"calls": []},
        }
        self.assertEqual(
            service.verify_irq_reachability(functions, set()), ["large", "short", "uefi_console_interrupt_dispatch"]
        )
        for name in ("aurora_kernel_value", "__au_v_short", "__au_runtime_console_put"):
            functions["short"]["calls"] = [{"target": name}]
            with self.assertRaises(ValueError):
                service.verify_irq_reachability(functions, {"aurora_kernel_value"})

    def test_noreturn_requires_body_and_tail_proof(self):
        functions = {"stop": {"returns": 0, "calls": []}, "leaf": {"returns": 1, "calls": []}}
        service.verify_noreturn(functions, {"stop"})
        with self.assertRaises(ValueError):
            service.verify_noreturn(functions, {"missing"})
        functions["stop"]["returns"] = 1
        with self.assertRaises(ValueError):
            service.verify_noreturn(functions, {"stop"})
        functions["stop"] = {"returns": 0, "calls": [{"kind": "tail", "target": "leaf"}]}
        with self.assertRaises(ValueError):
            service.verify_noreturn(functions, {"stop"})

    def test_exact_bridge(self):
        operations = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("mov", "%rdi,%r11"),
            ("call", "100 <entry>"),
            ("leave", ""),
            ("ret", ""),
        ]
        service.verify_bridge_body(decoder, body(operations), {256: service.ENTRY})
        for index, replacement in ((2, ("mov", "%rsi,%r11")), (3, ("call", "101 <wrong>")), (5, ("ret", "$0x8"))):
            changed = list(operations)
            changed[index] = replacement
            with self.assertRaises(ValueError):
                service.verify_bridge_body(decoder, body(changed), {256: service.ENTRY})

    def test_exact_irq(self):
        registers = (
            "rax",
            "rbx",
            "rcx",
            "rdx",
            "rbp",
            "rsi",
            "rdi",
            "r8",
            "r9",
            "r10",
            "r11",
            "r12",
            "r13",
            "r14",
            "r15",
        )
        ops = [("push", "$0x0"), ("push", "$0x40"), ("cld", "")] + [("push", "%" + r) for r in registers]
        ops += [
            ("mov", "%rsp,%rdi"),
            ("mov", "%rsp,%rbx"),
            ("and", "$0xfffffffffffffff0,%rsp"),
            ("call", "100 <dispatch>"),
            ("mov", "%rbx,%rsp"),
        ]
        ops += [("pop", "%" + r) for r in reversed(registers)] + [("add", "$0x10,%rsp"), ("iretq", "")]
        starts = {256: "uefi_console_interrupt_dispatch"}
        service.verify_irq_body(decoder, body(ops), starts)
        for index, replacement in (
            (0, ("push", "$0x8")),
            (20, ("and", "$0xffffffffffffffe0,%rsp")),
            (21, ("call", "101 <wrong>")),
            (22, ("mov", "%rax,%rsp")),
            (len(ops) - 1, ("ret", "")),
        ):
            changed = list(ops)
            changed[index] = replacement
            with self.assertRaises(ValueError):
                service.verify_irq_body(decoder, body(changed), starts)

    def test_fault_transcripts_reject_forbidden_earlier_effects(self):
        qualification = service.load("service_guest_oracles", ROOT / "tests/kernel-console-service-qualification.py")
        prefix = (
            b"AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"
            b"AURORA_UEFI_CONSOLE_TIMER_READY: polling_count=1250000 uart_irq=0\n"
        )
        ready = b"AURORA_CONSOLE_READY: UEFI, ASCII, 64-byte lines\naurora> "
        rejected = b"AURORA_UEFI_CONSOLE_FAIL: console service authority\n"
        tails = {
            "stale": rejected,
            "reentry": ready + rejected,
            "timeout": ready[:17],
            "report": ready + b"AURORA_UEFI_EXCEPTION: vector=255 error=0 rip=0 cr2=0\n"
            b"AURORA_UEFI_PAYLOAD_FAIL: exception\n",
        }
        for kind, tail in tails.items():
            mode = "console-service-" + kind
            qualification.validate_fault(prefix + tail, 35, mode, kind == "report")
            for changed in (b"x" + tail, ready + tail, tail + b"x"):
                with self.assertRaises(ValueError):
                    qualification.validate_fault(prefix + changed, 35, mode, kind == "report")
            with self.assertRaises(ValueError):
                qualification.validate_fault(prefix + tail, 33, mode, kind == "report")

    def test_source_output_and_review_identity(self):
        with tempfile.TemporaryDirectory(prefix="service-admission-") as directory:
            root = Path(directory)
            source = root / "source.cpp"
            source.write_bytes(b"checked source")
            output = root / "image.bin"
            output.write_bytes(b"checked image")
            compiler = root / "compiler"
            compiler.write_bytes(b"compiler identity")
            cxx = root / "cxx"
            cxx.write_bytes(b"host identity")

            def hashes(paths):
                return {str(path.relative_to(root)): service.digest(path) for path in paths}

            manifest = dict(
                schema="aurora-console-service-build-v1",
                mode="console",
                flags=["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_CONSOLE"],
                source_sha256=hashes([source]),
                compiler=dict(path=str(compiler), sha256=service.digest(compiler)),
                cxx=dict(path=str(cxx), sha256=service.digest(cxx)),
            )
            receipt = root / "receipt.json"
            data = dict(
                schema="aurora-console-service-admission-v1",
                mode="console",
                build=manifest,
                sha256=hashes([source, output]),
            )
            receipt.write_text(json.dumps(data))
            with (
                patch.object(service.common, "source_files", return_value=[source]),
                patch.object(service.common, "hashes", side_effect=hashes),
                patch.object(service, "ROOT", root),
                patch.object(service, "RECEIPT", receipt),
                patch.object(service, "provenance", return_value=manifest),
                patch.dict(os.environ, {"CONSOLE_SERVICE_REVIEW_SHA256": service.digest(receipt)}),
            ):
                service.verify_inputs(manifest, "console")
                service.reviewed("console")
                with self.assertRaises(ValueError):
                    service.reviewed("console-service-stale")
                output.write_bytes(b"changed image")
                with self.assertRaises(ValueError):
                    service.reviewed("console")
                output.write_bytes(b"checked image")
                source.write_bytes(b"changed source")
                with self.assertRaises(ValueError):
                    service.verify_inputs(manifest, "console")
                with self.assertRaises(ValueError):
                    service.reviewed("console")
                source.write_bytes(b"checked source")
                compiler.write_bytes(b"changed compiler")
                with self.assertRaises(ValueError):
                    service.verify_inputs(manifest, "console")
                with patch.dict(os.environ, {"CONSOLE_SERVICE_REVIEW_SHA256": "0" * 64}):
                    with self.assertRaises(ValueError):
                        service.reviewed("console")


if __name__ == "__main__":
    unittest.main()

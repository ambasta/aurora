#!/usr/bin/env python3
"""Native-free hostile semantic and artifact admission controls; no image execution."""

from pathlib import Path
import importlib.util
from copy import deepcopy
import json
import re
import subprocess
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
decoder = service.load("service_guard_decoder", ROOT / "scripts/kernel_stack.py")
sys.path.insert(0, str(ROOT / "scripts"))
bios = service.load("bios_console_controls", ROOT / "scripts/kernel_bios_console_admission.py")
assembly = service.load("uart_bridge_controls", ROOT / "scripts/meson_aurora_assembly.py")


def body(operations):
    return [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(operations)]


class Admission(unittest.TestCase):
    def test_reflection_image_ownership_and_body_wiring(self):
        names = (
            "aurora_reflect_size",
            "aurora_reflect_field_count",
            "__au_reflect_s4_size",
            "__au_reflect_s4_field_count",
        )
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
        decoder.verify_tail_bridge(body([("jmp", "100 <value>")]), {256: "aurora_kernel_value"}, "aurora_kernel_value")
        for changed in ([("call", "100 <value>")], [("jmp", "101 <wrong>")]):
            with self.assertRaises(ValueError):
                decoder.verify_tail_bridge(body(changed), {256: "aurora_kernel_value"}, "aurora_kernel_value")
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
        bootstrap = b"AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"
        timer = b"AURORA_UEFI_CONSOLE_TIMER_READY: polling_count=1250000 uart_irq=0\n"
        prefix = bootstrap + qualification.SELECTOR + timer
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
            # The selector must appear once, between the bootstrap and the timer.
            for changed in (
                bootstrap + timer + tail,
                bootstrap + qualification.SELECTOR * 2 + timer + tail,
                qualification.SELECTOR + bootstrap + timer + tail,
                bootstrap + timer + qualification.SELECTOR + tail,
            ):
                with self.assertRaises(ValueError):
                    qualification.validate_fault(changed, 35, mode, kind == "report")
        with self.assertRaises(ValueError):
            qualification.validate_fault(prefix + rejected, 35, "console", False)

    def test_checked_admission_binds_exact_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="service-admission-") as directory:
            root = Path(directory)
            output = root / "image.bin"
            output.write_bytes(b"checked image")

            def hashes(paths):
                return {str(path.relative_to(root)): service.digest(path) for path in paths}

            receipt = root / "receipt.json"
            data = dict(
                schema="aurora-console-service-admission-v1",
                mode="console",
                status="requires-independent-review",
                clock="tcg-original-clock",
                sha256=hashes([output]),
            )
            receipt.write_text(json.dumps(data))
            with (
                patch.object(service.common, "hashes", side_effect=hashes),
                patch.object(service, "build_files", return_value=[output]),
                patch.object(service, "RECEIPT", receipt),
            ):
                self.assertEqual(service.checked("console"), data)
                with self.assertRaises(ValueError):
                    service.checked("console-fixture")
                output.write_bytes(b"changed image")
                with self.assertRaises(ValueError):
                    service.checked("console")
                output.write_bytes(b"checked image")
                for key, value in (
                    ("schema", "changed"),
                    ("status", "approved"),
                    ("clock", "accelerated"),
                    ("sha256", {}),
                    ("sha256", {**data["sha256"], "foreign": "0" * 64}),
                ):
                    receipt.write_text(json.dumps(data | {key: value}))
                    with self.subTest(key=key), self.assertRaises(ValueError):
                        service.checked("console")
                receipt.write_text(json.dumps(data))
                self.assertEqual(service.checked("console"), data)


class BiosUartAdmission(unittest.TestCase):
    @staticmethod
    def abi():
        # Independent nominal fixture: symbols deliberately do not follow compiler mangling.
        fields = (
            ("receive_error", "bool"),
            ("trigger", "u64"),
            ("value", "u64"),
            ("present", "bool"),
            ("damaged", "bool"),
            ("success", "bool"),
        )
        record = dict(
            source_name="kernel::UartTransfer",
            size=48,
            alignment=8,
            reserved=48,
            fields=[
                dict(name=name, offset=index * 8, bytes=8, array_length=0, kind=kind)
                for index, (name, kind) in enumerate(fields)
            ],
        )
        functions = {}
        for suffix in ("initialize", "next", "put"):
            parameters = [
                dict(offset=0, bytes=16, kind="service", type_name="builtin::Com1UartGrant"),
                dict(offset=16, bytes=48, kind="class", type_name="copied_uart_record"),
            ]
            if suffix == "put":
                parameters.append(dict(offset=64, bytes=8, kind="u8"))
            functions["fixture_uart_" + suffix] = dict(
                source_name="uart_" + suffix,
                receiver=None,
                receiver_mutable=None,
                borrowed_root_count=0,
                borrowed_roots=[],
                borrowed_root_abi=dict(
                    kind="none",
                    register=None,
                    tuple_payload_bytes=0,
                    tuple_reserved_bytes=0,
                    saved_root_reserved_bytes=0,
                ),
                parameter_bytes=72 if suffix == "put" else 64,
                parameters=parameters,
                result=dict(bytes=48, kind="class", type_name="copied_uart_record"),
            )
        return dict(version=3, records={"copied_uart_record": record}, functions=functions)

    def test_uart_bridge_uses_exact_nominal_compiler_abi(self):
        facts = self.abi()
        template = (ROOT / "kernel/uart-policy-entry.S").read_text()
        rendered = assembly.render_bridge(template, facts)
        for suffix in ("initialize", "next", "put"):
            self.assertIn("call fixture_uart_" + suffix, rendered)
        for field, value in (("size", 40), ("alignment", 16), ("reserved", 64)):
            changed = deepcopy(facts)
            changed["records"]["copied_uart_record"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                assembly.render_bridge(template, changed)
        for index in range(6):
            for field, value in (("offset", 1), ("bytes", 1), ("kind", "u8"), ("array_length", 1)):
                changed = deepcopy(facts)
                changed["records"]["copied_uart_record"]["fields"][index][field] = value
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    assembly.render_bridge(template, changed)
        for suffix in ("initialize", "next", "put"):
            symbol = "fixture_uart_" + suffix
            for mutate in (
                lambda f: f.update(parameter_bytes=48),
                lambda f: f["parameters"][0].update(type_name="builtin::ConsoleSession"),
                lambda f: f["parameters"][0].update(kind="class"),
                lambda f: f["parameters"][1].update(offset=8),
                lambda f: f["parameters"][1].update(bytes=40),
                lambda f: f["parameters"][1].update(type_name="another_record"),
                lambda f: f["result"].update(bytes=40),
                lambda f: f["result"].update(kind="u64"),
                lambda f: f["result"].update(type_name="another_record"),
            ):
                changed = deepcopy(facts)
                mutate(changed["functions"][symbol])
                with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                    assembly.render_bridge(template, changed)
            missing = deepcopy(facts)
            del missing["functions"][symbol]
            with self.assertRaises(ValueError):
                assembly.render_bridge(template, missing)
            duplicate = deepcopy(facts)
            duplicate["functions"]["duplicate"] = deepcopy(duplicate["functions"][symbol])
            with self.assertRaises(ValueError):
                assembly.render_bridge(template, duplicate)

    def test_bios_copied_stack_record_is_not_a_scalar_size_escape(self):
        for suffix in ("initialize", "next", "put"):
            bridge = "__au_runtime_uart_" + suffix
            parameters = [["builtin::Com1UartGrant", 16], ["copied_class", 48]]
            if suffix == "put":
                parameters.append(["scalar", 8])
            record = dict(parameters=parameters, result_bytes=48, result_kind="copied_class")
            bios.verify_uart_record(record, bridge)
            for mutate in (
                lambda r: r.update(result_bytes=40),
                lambda r: r.update(result_kind="scalar"),
                lambda r: r.pop("result_kind"),
                lambda r: r["parameters"][1].__setitem__(0, "scalar"),
                lambda r: r["parameters"][1].__setitem__(1, 40),
                lambda r: r["parameters"].reverse(),
                lambda r: r["parameters"].append(["scalar", 8]),
            ):
                changed = deepcopy(record)
                mutate(changed)
                with self.assertRaises(ValueError):
                    bios.verify_uart_record(changed, bridge)
        with self.assertRaises(ValueError):
            bios.verify_uart_record(record, "__au_runtime_console_entry")

    def test_bios_bridges_bind_result_register_and_target(self):
        for copied in (False, True):
            operations = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11")]
            if copied:
                operations.append(("mov", "%rsi,%r10"))
            operations += [("call", "100 <entry>"), ("leave", ""), ("ret", "")]
            bios.bridge_contract(body(operations), {256: "entry"}, "entry", copied)
            mutations = [(2, ("mov", "%rsi,%r11")), (-3, ("call", "101 <wrong>")), (-1, ("ret", "$0x8"))]
            if copied:
                mutations.append((3, ("mov", "%rsi,%r9")))
            for index, replacement in mutations:
                changed = list(operations)
                changed[index] = replacement
                with self.assertRaises(ValueError):
                    bios.bridge_contract(body(changed), {256: "entry"}, "entry", copied)
            with self.assertRaises(ValueError):
                bios.bridge_contract(body(operations[:-1]), {256: "entry"}, "entry", copied)

    def test_bios_maps_missing_inputs_and_stack_overflow_fail_closed(self):
        self.assertEqual(bios.merge_functions({"console": 1}, {"uart": 2}), {"console": 1, "uart": 2})
        with self.assertRaises(ValueError):
            bios.merge_functions({"same": 1}, {"same": 2})
        with tempfile.TemporaryDirectory(prefix="bios-admission-inputs-") as temporary:
            root = Path(temporary)
            path = root / "facts.json"
            path.write_text('{"functions":{},"functions":{}}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                bios.read_json(path)
            with self.assertRaises(FileNotFoundError):
                bios.read_json(root / "missing.abi.json")
            directory = root / "kernel-images/bios/console"
            directory.mkdir(parents=True)
            # Image admission is mandatory even when this gate is invoked alone.
            # Stub the subprocess, not the failure: these remain compiler-free controls.
            denied = subprocess.CalledProcessError(1, ["kernel-image.py", "--check-only"])
            with (
                patch.object(bios.stack, "command", side_effect=denied) as image_check,
                patch.object(bios.stack, "Elf") as elf,
            ):
                with self.assertRaises(subprocess.CalledProcessError):
                    bios.admission(directory, ROOT)
                image_check.assert_called_once_with(
                    sys.executable,
                    "-B",
                    str(ROOT / "tests/kernel-image.py"),
                    "--root",
                    str(ROOT),
                    "--build-dir",
                    str(directory),
                    "--console",
                    "--check-only",
                )
                elf.assert_not_called()
            with patch.object(bios.stack, "command", return_value=""):
                with self.assertRaises(FileNotFoundError):
                    bios.admission(directory, ROOT)
        # Reserve IRQ and a fault that interrupts that IRQ, not just the larger one.
        main, fault = 512, 720
        normal = 32768 - main - 63 - 191 - fault
        exact = bios.check_budget(dict(peak=normal), dict(peak=fault), main)
        self.assertEqual(exact["minimum_unused"], 0)
        with self.assertRaisesRegex(ValueError, "main stack exhausted"):
            bios.check_budget(dict(peak=normal + 1), dict(peak=fault), main)
        bios.check_budget(dict(peak=1), dict(peak=16384 - 191), 1)
        with self.assertRaisesRegex(ValueError, "emergency stack exhausted"):
            bios.check_budget(dict(peak=1), dict(peak=16384 - 191 + 1), 1)
        with self.assertRaises(ValueError):
            bios.check_budget(dict(peak=1 << 64), dict(peak=1), 1)

    def test_bios_active_owner_routes_diagnostics_and_stops_fault_reentry(self):
        serial = (ROOT / "kernel/console.hpp").read_text()
        put = serial[serial.index("static auto put(Byte value)") : serial.index("static auto text(")]
        self.assertRegex(
            put,
            r"if \(console::Interactive::owns_uart\(\)\)\s*\{\s*"
            r"console::Interactive::put\(value\);\s*return;",
        )
        self.assertLess(put.index("Interactive::put"), put.index("Io::read"))
        main = (ROOT / "kernel/main.cpp").read_text()
        dispatch = main[main.index("auto exception_dispatch(", main.index('asm("aurora_exception_dispatch")')) :]
        guard = re.search(
            r"if \(aurora::console::Interactive::owns_uart\(\)\)\s*"
            r"aurora::console::Interactive::fail\(\);",
            dispatch,
        )
        self.assertIsNotNone(guard)
        self.assertLess(guard.start(), dispatch.index("Serial::"))
        self.assertLess(guard.start(), dispatch.index("Scheduler::interrupt"))


if __name__ == "__main__":
    unittest.main()

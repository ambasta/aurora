#!/usr/bin/env python3
"""Independent hostile combined-profile controls. Source prepared, not qualified.

No compiler, guest or subprocess is launched. All safety assertions use explicit
exceptions or unittest assertions and remain active under python -O.
"""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("graphical_controls_target", ROOT / "scripts/kernel_graphical_console_admission.py")
graphical = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = graphical
spec.loader.exec_module(graphical)
decoder = graphical.load("graphical_controls_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")


def body(operations):
    return [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(operations)]


def fixture(specification, analyze=True):
    """Build machine-shaped fixtures only; the expected denials are below."""
    starts = {100 * index: name for index, name in enumerate(specification)}
    addresses = {name: address for address, name in starts.items()}
    symbols, code = {}, {}
    for name, rows in specification.items():
        base = addresses[name]
        symbols[name] = decoder.Symbol(name, base, len(rows), 1, 2)
        for index, (op, args) in enumerate(rows):
            if args.startswith("@"):
                target, _, offset = args[1:].partition("+")
                args = f"{addresses[target] + int(offset or 0):x} <{target}>"
            code[base + index] = decoder.Instruction(base + index, 1, op, args)
    functions = {name: decoder.analyze_function(symbol, code, starts) for name, symbol in symbols.items()} if analyze else {}
    return functions, symbols, code, starts


class Admission(unittest.TestCase):
    @staticmethod
    def paired_object(linked=False):
        # Exact independent symbol inventory from unadmitted attempt002.
        names = ["_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_20FramebufferAdmissionEENKUlOT_mjmE1_clIRKSD_EEbSC_mjm",
                 "_ZZNK6aurora4uefi10PageTables16verify_graphicalEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEPKNS0_20FramebufferAdmissionEENKUlOT_mjmE_clIRKSD_EEbSC_mjm"]
        address = 0x67e0 if linked else 0
        strings = b"\0" + names[0].encode() + b"\0" + names[1].encode() + b"\0"
        offsets = [1, len(names[0]) + 2]
        raw = b"".join(struct.pack("<IBBHQQ", offset, 0x22, 2, 3, address, 866) for offset in offsets)
        sections = [(0,) * 10, (0, 2, 0, 0, 0, 48, 2, 0, 8, 24),
                    (0, 3, 0, 0, 48, len(strings), 0, 0, 1, 0), (0,) * 10]
        symbols = [decoder.Symbol(name, address, 866, 3, 2) for name in names]
        return SimpleNamespace(type=2 if linked else 1, data=raw + strings, sections=sections,
            symbols=symbols, functions={row.name: row for row in symbols}, relocations=[],
            section_data=lambda index: strings if index == 2 else b"", function_bytes=lambda symbol: b"\x90" * symbol.size)

    def test_exact_paired_alias_raw_identity(self):
        evidence = graphical.paired_alias_evidence(self.paired_object())
        self.assertEqual(evidence["canonical"], graphical.PAIRED_WALK)
        self.assertEqual({row["name"] for row in evidence["aliases"]},
                         {graphical.PAIRED_WALK, graphical.PAIRED_ALIAS})
        for missing in [graphical.PAIRED_WALK, graphical.PAIRED_ALIAS]:
            obj = self.paired_object(); del obj.functions[missing]
            with self.assertRaisesRegex(ValueError, "Missing exact"): graphical.paired_alias_evidence(obj)
        for field, value in [("address", 1), ("size", 865), ("section", 2), ("kind", 0)]:
            obj = self.paired_object(); row = obj.functions[graphical.PAIRED_ALIAS]
            changed = dict(vars(row)); changed[field] = value
            obj.functions[graphical.PAIRED_ALIAS] = decoder.Symbol(**changed)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "Diverged"):
                graphical.paired_alias_evidence(obj)
        for name in ["arbitrary_alias", graphical.PAIRED_ALIAS + ".clone"]:
            obj = self.paired_object(); obj.symbols.append(decoder.Symbol(name, 0, 866, 3, 2))
            with self.assertRaisesRegex(ValueError, "alias inventory"): graphical.paired_alias_evidence(obj)
        # Mutate either raw symbol independently: bind, visibility, type,
        # section, address and size must all agree with the parsed inventory.
        for entry in [0, 1]:
            for field, value in [(1, 0x12), (1, 0x20), (2, 0), (2, 3),
                                 (3, 2), (4, 1), (5, 865)]:
                obj = self.paired_object(); raw = bytearray(obj.data)
                values = list(struct.unpack_from("<IBBHQQ", raw, entry * 24)); values[field] = value
                struct.pack_into("<IBBHQQ", raw, entry * 24, *values); obj.data = bytes(raw)
                with self.subTest(entry=entry, field=field, value=value), self.assertRaisesRegex(ValueError, "raw identity"):
                    graphical.paired_alias_evidence(obj)
        obj = self.paired_object(); obj.data = obj.data[:24] + obj.data[:24] + obj.data[48:]
        with self.assertRaisesRegex(ValueError, "Duplicate or missing"): graphical.paired_alias_evidence(obj)

    def test_paired_frame_spelling_is_exact_and_typedef_scoped(self):
        for signature in [graphical.PAIRED_SU, graphical.PAIRED_SU.replace("uint64_t", "unsigned long"),
                          graphical.PAIRED_DEMANGLED]:
            self.assertEqual(graphical.paired_frame_identity(signature), graphical.PAIRED_WALK)
        for signature in [graphical.PAIRED_SU.replace("uint64_t", "unsigned long long"),
                          graphical.PAIRED_SU.replace("auto:2", "auto:3"),
                          graphical.PAIRED_SU.replace("unsigned int", "unsigned short"),
                          graphical.PAIRED_SU + " extra", graphical.PAIRED_DEMANGLED.replace("#3", "#1"),
                          graphical.PAIRED_DEMANGLED.replace("#3", "#4")]:
            with self.subTest(signature=signature), self.assertRaisesRegex(ValueError, "exact paired walker frame"):
                graphical.paired_frame_identity(signature)
        self.assertIsNone(graphical.paired_frame_identity("unrelated(uint64_t)"))
        self.assertIsNone(graphical.paired_frame_identity(graphical.PAIRED_SU_PARENT))

    def test_paired_aliases_both_associate_but_have_one_compiler_frame(self):
        with tempfile.TemporaryDirectory(prefix="paired-frame-controls-") as directory:
            root = Path(directory)
            su = root / "graphical-console.su"
            line = "tables.hpp:308:27:" + graphical.PAIRED_SU + "\t128\tstatic\n"
            su.write_text(line)
            obj, linked = self.paired_object(), self.paired_object(linked=True)
            with patch.object(graphical, "CPP_OBJECTS", ("graphical-console",)), \
                 patch.object(decoder, "Elf", return_value=obj), \
                 patch.object(decoder, "command", return_value=graphical.PAIRED_DEMANGLED + "\n"), \
                 patch.object(decoder, "frame_identity", side_effect=graphical.paired_frame_identity), \
                 patch.object(decoder, "associate_object", wraps=decoder.associate_object) as associate:
                frames, receipts, aliases = graphical.graphical_cpp_frames(decoder, root, linked)
                self.assertEqual(frames, {graphical.PAIRED_WALK: 128})
                self.assertEqual(set(receipts), {graphical.PAIRED_WALK})
                self.assertEqual(len(aliases), 1)
                self.assertEqual({call.args[2].name for call in associate.call_args_list},
                                 {graphical.PAIRED_WALK, graphical.PAIRED_ALIAS})
                self.assertIn(graphical.PAIRED_ALIAS, linked.functions)
                for content in ["", line + line]:
                    su.write_text(content)
                    with self.assertRaises(ValueError): graphical.graphical_cpp_frames(decoder, root, linked)
                su.write_text(line)
                linked.function_bytes = lambda symbol: b"\xcc" * symbol.size
                with self.assertRaisesRegex(ValueError, "instruction mismatch"):
                    graphical.graphical_cpp_frames(decoder, root, linked)

    def test_generated_imports_and_module_identity(self):
        names = graphical.expected_language_functions()  # Fixture construction only.
        imports = [decoder.Symbol(name, 0, 0, 0, 0) for name in ["__au_runtime_console_next", "__au_runtime_display_pixel"]]
        bindings = "\n".join(f"1: 000000 1 FUNC {'GLOBAL HIDDEN' if name in {graphical.BRIDGE, graphical.VALUE_BRIDGE} else 'LOCAL DEFAULT'} 1 {name}" for name in sorted(names))
        def verify(functions=names, symbols=imports, table=bindings):
            with patch.object(graphical.subprocess, "check_output", return_value=table):
                return graphical.verify_language_object(SimpleNamespace(functions=functions, symbols=symbols, path=Path("fixture.o")))
        verify()
        for changed in [imports[:-1], imports + [decoder.Symbol("__au_runtime_console_put", 0, 0, 0, 0)],
                        imports + [decoder.Symbol("unknown", 0, 0, 0, 0)]]:
            with self.assertRaisesRegex(ValueError, "import inventory"):
                verify(symbols=changed)
        for extra in ["__au_v_m1_22kernel_display_service_n0__d15display_service", "unexpected_host"]:
            with self.assertRaisesRegex(ValueError, "module/function"):
                verify(functions=names | {extra})
        for missing in sorted(names):
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "module/function inventory"):
                verify(functions=names - {missing})
        for table, reason in [(bindings.replace("LOCAL DEFAULT", "GLOBAL DEFAULT"), "private ELF binding"),
                              (bindings.replace("GLOBAL HIDDEN", "GLOBAL DEFAULT"), "private ELF binding"),
                              (bindings + "\n" + bindings.splitlines()[0], "Duplicate"),
                              ("\n".join(bindings.splitlines()[1:]), "binding inventory")]:
            with self.assertRaisesRegex(ValueError, reason): verify(table=table)

    def test_provisional_six_qword_pixel_and_value_bridge_machine_contract(self):
        # Entry stack touch follows retained consumer.s; linked disassembly and
        # the remaining synthetic ABI fixture still require allocated execution.
        entry = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("sub", "$0x80,%rsp"),
                 ("orq", "$0x0,(%rsp)"), ("mov", "%r11,-0x8(%rbp)")]
        read_indexes, write_indexes = [], []
        destinations = iter([0x18, 0x10, 0x28, 0x20, 0x30, 0x38])
        for group in [(0, 8), (16, 24), (32,), (40,)]:
            entry.append(("mov", "-0x8(%rbp),%r11"))
            for offset in group:
                read_indexes.append(len(entry)); write_indexes.append(len(entry) + 1)
                entry += [("mov", ("" if offset == 0 else hex(offset)) + "(%r11),%rax"),
                          ("mov", f"%rax,-0x{next(destinations):x}(%rbp)")]
        pixel_name = "__au_v_m1_24kernel_graphical_console_pixel_fixture"
        pixel_base = 3
        pixel = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("sub", "$0x80,%rsp")]
        pixel += [("mov", "-0x40(%rbp),%rdi"), ("mov", "-0x38(%rbp),%rsi")]
        pixel += [("pop", r) for r in ["%r10", "%r9", "%r8", "%rcx", "%rdx"]]
        pixel += [("sub", "$0x8,%rsp"), ("mov", "%r10,(%rsp)"),
                  ("call", "@__au_runtime_display_pixel"), ("add", "$0x8,%rsp"),
                  ("cmp", "$0x1,%rax"), ("ja", "@" + pixel_name + "+18"), ("leave", ""), ("ret", ""), ("ud2", "")]
        graph = {graphical.ENTRY: entry, graphical.VALUE_BRIDGE: [("jmp", "@" + graphical.VALUE_ENTRY)],
                 graphical.VALUE_ENTRY: [("ret", "")], pixel_name: pixel,
                 "__au_runtime_display_pixel": [("ret", "")]}
        def verify(rows, live_bytes=16):
            _, symbols, code, starts = fixture(rows, analyze=False)
            functions = {name: {"calls": [{"address": row.address, "live_bytes": live_bytes}
                         for row in code.values() if symbol.address <= row.address < symbol.address + symbol.size and row.op == "call"]}
                         for name, symbol in symbols.items()}
            return graphical.verify_private_abi(decoder, SimpleNamespace(functions=symbols), code, starts,
                                                {graphical.ENTRY, graphical.VALUE_BRIDGE, graphical.VALUE_ENTRY, pixel_name}, functions)
        verify(graph)
        # Missing, altered-width/opcode/value/address and displaced touches
        # must fail at the exact prologue boundary, not be skipped generically.
        changed = deepcopy(graph); del changed[graphical.ENTRY][3]
        with self.assertRaisesRegex(ValueError, "paired entry stack touch"): verify(changed)
        for operation in [("nop", ""), ("orl", "$0x0,(%rsp)"), ("orq", "$0x1,(%rsp)"),
                          ("orq", "$0x0,0x8(%rsp)"), ("orq", "$0x0,-0x8(%rsp)"),
                          ("orq", "$0x0,(%rbp)"), ("orq", "$0x0,%rsp")]:
            changed = deepcopy(graph); changed[graphical.ENTRY][3] = operation
            with self.subTest(stack_touch=operation), self.assertRaisesRegex(ValueError, "paired entry stack touch"):
                verify(changed)
        changed = deepcopy(graph)
        changed[graphical.ENTRY][3:5] = list(reversed(changed[graphical.ENTRY][3:5]))
        with self.assertRaisesRegex(ValueError, "paired entry stack touch"): verify(changed)
        changed = deepcopy(graph); changed[graphical.ENTRY].insert(4, ("orq", "$0x0,(%rsp)"))
        with self.assertRaisesRegex(ValueError, "private record save"): verify(changed)
        for operation in [("call", "@" + graphical.VALUE_ENTRY), ("jmp", "@" + graphical.ENTRY), ("jmp", "*%rax")]:
            changed = deepcopy(graph); changed[graphical.VALUE_BRIDGE] = [operation]
            with self.assertRaisesRegex(ValueError, "value-only private bridge|direct"):
                verify(changed)
        changed = deepcopy(graph); changed[graphical.VALUE_BRIDGE].append(("ret", ""))
        with self.assertRaisesRegex(ValueError, "value-only private bridge"): verify(changed)
        for index in read_indexes:
            changed = deepcopy(graph); changed[graphical.ENTRY][index] = ("mov", "(%r11),%eax")
            with self.assertRaisesRegex(ValueError, "qword/width/order"): verify(changed)
        for index in write_indexes:
            changed = deepcopy(graph); changed[graphical.ENTRY][index] = ("mov", "%rax,-0x8(%rbp)")
            with self.assertRaisesRegex(ValueError, "parameter slot"): verify(changed)
        for destination in ["-0x9", "-0x11", "-0x88", "-0x0"]:
            changed = deepcopy(graph); changed[graphical.ENTRY][write_indexes[0]] = ("mov", f"%rax,{destination}(%rbp)")
            with self.assertRaisesRegex(ValueError, "Overlapping, unaligned or unallocated"): verify(changed)
        changed = deepcopy(graph); changed[pixel_name][pixel_base + 7] = ("sub", "$0x10,%rsp"); changed[pixel_name][pixel_base + 10] = ("add", "$0x10,%rsp")
        with self.assertRaisesRegex(ValueError, "Misaligned pixel SysV"): verify(changed, live_bytes=24)
        for grant, generation in [("-0x41", "-0x39"), ("-0x88", "-0x80")]:
            changed = deepcopy(graph)
            changed[pixel_name][pixel_base] = ("mov", grant + "(%rbp),%rdi")
            changed[pixel_name][pixel_base + 1] = ("mov", generation + "(%rbp),%rsi")
            with self.assertRaisesRegex(ValueError, "unaligned or outside helper frame"): verify(changed)
        for index, replacement in [(11, ("cmp", "$0x2,%rax")), (12, ("ja", "@" + pixel_name + "+17"))]:
            changed = deepcopy(graph); changed[pixel_name][pixel_base + index] = replacement
            with self.assertRaisesRegex(ValueError, "completion validation"): verify(changed)
        for index, replacement, reason in [(1, ("mov", "-0x40(%rbp),%rsi"), "grant/generation"),
                                           (2, ("pop", "%rax"), "scalar ABI"),
                                           (8, ("mov", "%rax,(%rsp)"), "seventh argument"),
                                           (10, ("add", "$0x10,%rsp"), "seventh argument")]:
            changed = deepcopy(graph); changed[pixel_name][pixel_base + index] = replacement
            with self.assertRaisesRegex(ValueError, reason): verify(changed)

    def test_object_bytes_size_and_relocation_inventory(self):
        symbol = decoder.Symbol("leaf", 0, 5, 1, 2)
        linked = SimpleNamespace(functions={"leaf": symbol}, function_bytes=lambda _: b"\xe8\x11\x22\x33\x44")
        obj = SimpleNamespace(relocations=[(1, 1, 2, 0, 0)], function_bytes=lambda _: b"\xe8\x00\x00\x00\x00")
        decoder.associate_object(linked, obj, symbol)
        for relocation in [(1, 1, 1, 0, 0), (1, 2, 2, 0, 0), (2, 1, 2, 0, 0)]:
            with self.assertRaises(ValueError):
                decoder.associate_object(linked, SimpleNamespace(relocations=[relocation], function_bytes=obj.function_bytes), symbol)
        with self.assertRaises(ValueError):
            decoder.associate_object(linked, SimpleNamespace(relocations=obj.relocations, function_bytes=lambda _: b"\xe9\x00\x00\x00\x00"), symbol)
        with self.assertRaises(ValueError):
            decoder.associate_object(linked, obj, decoder.Symbol("leaf", 0, 4, 1, 2))

    def test_unreviewed_graph_cycles_are_never_bounded_by_accident(self):
        for graph in [{"root": [("call", "@root"), ("ret", "")]},
                      {"root": [("call", "@leaf"), ("ret", "")], "leaf": [("jmp", "@root")]}]:
            functions, *_ = fixture(graph)
            with self.assertRaises(ValueError):
                graphical.common.graph_peak(functions, {}, "root", set())

    def test_explicit_failures_survive_optimization(self):
        with self.assertRaises(ValueError):
            graphical.need(False, "independent explicit denial")
        with self.assertRaises(ValueError):
            decoder.require(False, "independent explicit decoder denial")

    def test_bridge_target_and_record_forwarding_are_exact(self):
        ops = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11"),
               ("call", "100 <entry>"), ("leave", ""), ("ret", "")]
        starts = {256: "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"}
        graphical.verify_bridge_body(decoder, body(ops), starts)
        for index, replacement in [
            (0, ("push", "%rbx")), (1, ("mov", "%rsp,%rbx")),
            (2, ("mov", "%rsi,%r11")), (2, ("mov", "%edi,%r11d")),
            (2, ("mov", "%rdi,%r10")), (3, ("call", "*%r11")),
            (3, ("jmp", "100 <entry>")), (3, ("call", "101 <interior>")),
            (4, ("nop", "")), (5, ("ret", "$0x8")),
        ]:
            changed = list(ops); changed[index] = replacement
            with self.subTest(index=index, replacement=replacement), self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(changed), starts)
        for name in ["__au_v_m1_22kernel_display_service_n0__d15display_service", "__au_runtime_console_entry"]:
            with self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(ops), {256: name})
        for changed in [ops[:-1], ops + [("nop", "")]]:
            with self.assertRaises(ValueError):
                graphical.verify_bridge_body(decoder, body(changed), starts)

    def test_irq_every_save_restore_and_dispatch(self):
        registers = "rax rbx rcx rdx rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
        ops = [("push", "$0x0"), ("push", "$0x40"), ("cld", "")]
        ops += [("push", "%" + r) for r in registers]
        ops += [("mov", "%rsp,%rdi"), ("mov", "%rsp,%rbx"),
                ("and", "$0xfffffffffffffff0,%rsp"), ("call", "100 <dispatch>"), ("mov", "%rbx,%rsp")]
        ops += [("pop", "%" + r) for r in reversed(registers)] + [("add", "$0x10,%rsp"), ("iretq", "")]
        starts = {256: "uefi_console_interrupt_dispatch"}
        graphical.verify_irq_body(decoder, body(ops), starts)
        for index in range(len(ops)):
            changed = list(ops); changed[index] = ("nop", "")
            with self.subTest(index=index), self.assertRaises(ValueError):
                graphical.verify_irq_body(decoder, body(changed), starts)
        for index, replacement in [(20, ("and", "$0xffffffffffffffe0,%rsp")),
                                   (21, ("call", "*%rax")), (22, ("mov", "%rax,%rsp"))]:
            changed = list(ops); changed[index] = replacement
            with self.assertRaises(ValueError): graphical.verify_irq_body(decoder, body(changed), starts)

    def test_irq_excludes_language_and_service_on_every_branch(self):
        graph = {"uefi_console_interrupt_dispatch": {"calls": [{"target": "large"}, {"target": "small"}]},
                 "large": {"calls": []}, "small": {"calls": []}}
        graphical.verify_irq_reachability(graph, set())
        for target in [graphical.ENTRY, "__au_v_any", "__au_runtime_console_put", "__au_runtime_display_put", "generated_leaf"]:
            changed = deepcopy(graph)
            changed["small"]["calls"] = [{"target": target}]
            changed[target] = {"calls": []}
            with self.subTest(target=target), self.assertRaises(ValueError):
                graphical.verify_irq_reachability(changed, {"generated_leaf", graphical.ENTRY})

    def test_unchanged_stack_and_separate_reserves(self):
        # Independently selected exact boundaries: 15360 total, 4096 IRQ/fault.
        for values in [(15000, 11000, 3736, 360), (15201, 720, 639, 159), (1, 12304, 2048, 1008), (1, 1, 4000, 96)]:
            graphical.verify_stack_budgets(*values)
        for values in [(15001, 11000, 3736, 360), (1, 11265, 3736, 360),
                       (1, 1, 3737, 360), (1, 12305, 2048, 1008),
                       (-1, 1, 1, 1), (True, 1, 1, 1), (1, False, 1, 1),
                       (1, 1, -1, 1), (1, 1, 1, -1), (1, 1, 1, 1.0)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                graphical.verify_stack_budgets(*values)

    def test_immediate_push_bytes_width_and_value(self):
        for args, raw in [("$0x0", bytes.fromhex("6a00")), ("$0x28", bytes.fromhex("6a28"))]:
            row, receipt = graphical.normalize_instruction(decoder, decoder.Instruction(0, 2, "push", args), raw)
            self.assertEqual(row.args, "%rax"); self.assertEqual(receipt["bytes"], raw.hex())
        for args, raw in [("$0x0", b"\x66\x6a\x00"), ("$0x0", b"\x6a\x28"),
                          ("$0x28", b"\x6a\x00"), ("$0x40", b"\x6a\x40"),
                          ("$0x1", b"\x6a\x01"), ("$0x0", b"\x68\x00\x00\x00\x00"),
                          ("$0x0", b"\x6a")]:
            with self.subTest(args=args, raw=raw), self.assertRaises(ValueError):
                graphical.normalize_instruction(decoder, decoder.Instruction(0, len(raw), "push", args), raw)

    def test_unsupported_stack_forms_and_opcode_fail_closed(self):
        for op, args in [("push", "(%rsp)"), ("push", "0x10(%rip)"), ("push", "(%rsp,%rax,8)"),
                         ("sub", "$0xfffffffffffffff0,%rsp"), ("mov", "%rax,%rsp"),
                         ("ret", "$0x8"), ("enter", "$0x10,$0x0"), ("opaque_new_opcode", "")]:
            row = decoder.Instruction(0, 1, op, args)
            with self.subTest(op=op, args=args), self.assertRaises(ValueError):
                normalized, _ = graphical.normalize_instruction(decoder, row, b"\x90")
                decoder.analyze_function(decoder.Symbol("sample", 0, 2, 1, 2),
                                         {0: normalized, 1: decoder.Instruction(1, 1, "ret", "")}, {0: "sample"})

    def test_both_walkers_require_bounded_decrement_and_entry(self):
        paired = "independent_paired_walk"
        saves = "%r15 %r14 %r13 %r12 %rbp %rbx".split()
        def walk(name):
            return [("push", r) for r in saves] + [("mov", "%ecx,%r14d"), ("test", "%r14d,%r14d"),
                ("je", "@" + name + "+11"), ("lea", "-0x1(%r14),%ecx"), ("call", "@" + name)] + [("pop", r) for r in reversed(saves)] + [("ret", "")]
        graph = {"root": [("mov", "$0x3,%ecx"), ("call", "@" + decoder.WALK),
                          ("mov", "$0x3,%ecx"), ("call", "@" + paired), ("ret", "")],
                 decoder.WALK: walk(decoder.WALK), paired: walk(paired)}
        graphical.paired_recursion_proofs(decoder, *fixture(graph), paired)
        for name in [decoder.WALK, paired]:
            for index, replacement in [(6, ("mov", "%edx,%r14d")), (7, ("cmp", "$0x1,%r14d")),
                                       (8, ("jne", "@" + name + "+11")), (9, ("lea", "0x1(%r14),%ecx")),
                                       (9, ("mov", "%r14d,%ecx")), (15, ("pop", "%rax"))]:
                changed = deepcopy(graph); changed[name][index] = replacement
                with self.subTest(walker=name, index=index, replacement=replacement), self.assertRaises(ValueError):
                    graphical.paired_recursion_proofs(decoder, *fixture(changed), paired)
        for index in [0, 2]:
            for args in ["$0x4,%ecx", "%eax,%ecx", "$0x3,%cl"]:
                changed = deepcopy(graph); changed["root"][index] = ("mov", args)
                with self.assertRaises(ValueError): graphical.paired_recursion_proofs(decoder, *fixture(changed), paired)
        changed = deepcopy(graph); changed[paired][10] = ("call", "@" + decoder.WALK)
        with self.assertRaises(ValueError): graphical.paired_recursion_proofs(decoder, *fixture(changed), paired)
        functions, symbols, code, starts = fixture(graph)
        for missing in [decoder.WALK, paired]:
            changed = dict(functions); del changed[missing]
            with self.assertRaises(ValueError):
                graphical.paired_recursion_proofs(decoder, changed, symbols, code, starts, paired)
        with self.assertRaises(ValueError):
            graphical.paired_recursion_proofs(decoder, functions, symbols, code, starts, decoder.WALK)
        self.assertEqual(decoder.WALK, next(name for name in graph if name not in {"root", paired}))

    def test_wait_exact_bytes_decode_single_owner_and_single_sti(self):
        start = 10
        code = {start + i: decoder.Instruction(start + i, 1, op, "") for i, op in enumerate(["sti", "hlt", "cli"])}
        named = {"uefi_console_poll_begin": decoder.Symbol("begin", 10, 0, 1, 0),
                 "uefi_console_poll_end": decoder.Symbol("end", 13, 0, 1, 0)}
        graph = {"uefi_console_interrupt_dispatch": {"calls": []}}
        owners = {"trusted_wait_for_sample": decoder.Symbol("trusted_wait_for_sample", 9, 5, 1, 2)}
        payload = b"\x90" * 10 + b"\xfb\xf4\xfa" + b"\x90"
        def verify(c=code, n=named, g=graph, p=payload, o=owners):
            return graphical.verify_wait_closure(c, n, g, set(), p, o)
        verify()
        for raw in [b"\xfa\xf4\xfb", b"\xfb\x90\xfa", b"\xfb\xf4\x90", b"\xfb\xf4"]:
            with self.assertRaises(ValueError): verify(p=b"\x90" * 10 + raw)
        for index in code:
            changed = dict(code); changed[index] = decoder.Instruction(index, 1, "nop", "")
            with self.assertRaises(ValueError): verify(c=changed)
            changed = dict(code); changed[index] = decoder.Instruction(index, 2, code[index].op, "")
            with self.assertRaises(ValueError): verify(c=changed)
        changed = dict(code); changed[1] = decoder.Instruction(1, 1, "sti", "")
        with self.assertRaises(ValueError): verify(c=changed)
        for changed in [{}, {"wrong_owner": decoder.Symbol("wrong_owner", 9, 5, 1, 2)},
                        dict(owners, second_wait_for_sample=decoder.Symbol("second_wait_for_sample", 9, 5, 1, 2))]:
            with self.assertRaises(ValueError): verify(o=changed)
        changed = deepcopy(named); changed["uefi_console_poll_end"] = decoder.Symbol("end", 14, 0, 1, 0)
        with self.assertRaises(ValueError): verify(n=changed)

    def test_each_wait_path_retains_paired_service_not_just_maximum(self):
        path = ["uefi_payload_entry", graphical.BRIDGE, graphical.ENTRY, "__au_runtime_console_next", "wait_for_sample"]
        graph = {name: {"calls": [{"target": path[index + 1]}] if index + 1 < len(path) else []}
                 for index, name in enumerate(path)}
        graphical.verify_retained_wait_paths(graph, path[-1], set())
        for source, target in [(0, 2), (1, 3), (2, 4), (0, 4)]:
            changed = deepcopy(graph); changed[path[source]]["calls"].append({"target": path[target]})
            with self.subTest(source=source, target=target), self.assertRaisesRegex(ValueError, "bypasses retained"):
                graphical.verify_retained_wait_paths(changed, path[-1], set())

    def test_inventory_has_no_missing_unframed_or_extra_authority(self):
        fixed = {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common", "uefi_console_interrupt"}
        language = {graphical.ENTRY, graphical.BRIDGE, graphical.VALUE_BRIDGE, "generated_helper"}
        frames = {"trusted_cpp", "__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"}
        memory = {"memcpy", "memset"}
        linked = fixed | language | frames | memory
        graphical.verify_inventory(linked, frames, language, memory)
        for missing in sorted(linked):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                graphical.verify_inventory(linked - {missing}, frames, language, memory)
        with self.assertRaises(ValueError): graphical.verify_inventory(linked | {"unframed"}, frames, language, memory)
        for extra in ["__au_runtime_display_clear", "uefi_runtime_unexpected", "aurora_user_fixture", "aurora_kernel_budget_fixture"]:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                graphical.verify_inventory(linked | {extra}, frames | {extra}, language, memory)
        for name in [graphical.ENTRY, graphical.BRIDGE]:
            with self.assertRaises(ValueError): graphical.verify_inventory(linked, frames | {name}, language - {name}, memory)
        self.assertEqual(graphical.CPP_OBJECTS, ("payload", "acpi", "pci", "runtime", "graphical-console"))
        self.assertEqual(graphical.ASSEMBLY_OBJECTS, ("payload-entry", "console-entry", "language", "memory"))

    def test_begin_invalidates_before_fallible_checks(self):
        with tempfile.TemporaryDirectory(prefix="graphical-invalidation-") as directory:
            root = Path(directory)
            names = ["graphical-console-admission.json", "graphical-console-build.json",
                     "graphical-console-build-start.json"]
            sentinel = root / "payload.elf"
            sentinel.write_bytes(b"preserved prior image")
            def stale():
                for name in names: (root / name).write_text("previous metadata")
            with patch.object(graphical, "BUILD", root), patch.object(graphical, "RECEIPT", root / names[0]):
                stale()
                with self.assertRaisesRegex(ValueError, "Missing exact graphical build controls"):
                    graphical.begin("graphical-console", "compiler", "cxx", [])
                self.assertTrue(all(not (root / name).exists() for name in names))
                stale()
                with patch.object(graphical, "source_files", return_value=[]), \
                     patch.object(graphical.common, "hashes", return_value={}), \
                     patch.object(graphical.common, "executable", side_effect=RuntimeError("tool unavailable")):
                    with self.assertRaisesRegex(RuntimeError, "tool unavailable"):
                        graphical.begin("graphical-console", "compiler", "cxx", graphical.expected_flags("graphical-console"))
                self.assertTrue(all(not (root / name).exists() for name in names))
                stale()
                with patch.object(Path, "unlink", side_effect=PermissionError("read-only metadata")), \
                     patch.object(graphical.common, "executable") as executable:
                    with self.assertRaisesRegex(PermissionError, "read-only metadata"):
                        graphical.begin("graphical-console", "compiler", "cxx", graphical.expected_flags("graphical-console"))
                    executable.assert_not_called()
                self.assertEqual(sentinel.read_bytes(), b"preserved prior image")

    def test_mode_flags_sources_artifacts_and_review_identity(self):
        with tempfile.TemporaryDirectory(prefix="graphical-controls-") as directory:
            root = Path(directory)
            paths = {name: root / name for name in ["source", "compiler", "cxx", "payload.bin", "tool", "pe_linker"]}
            for name, path in paths.items(): path.write_text("original " + name)
            def hashes(items): return {str(path.relative_to(root)): graphical.digest(path) for path in items}
            record = dict(schema="aurora-graphical-console-build-v1", mode="graphical-console",
                          flags=graphical.expected_flags("graphical-console"), translation_unit_flags=deepcopy(graphical.TU_FLAGS),
                          objects=["payload.bin"], source_sha256=hashes([paths["source"]]),
                          compiler=dict(path=str(paths["compiler"]), sha256=graphical.digest(paths["compiler"])),
                          cxx=dict(path=str(paths["cxx"]), sha256=graphical.digest(paths["cxx"])),
                          tools={name: dict(path=str(paths["tool"]), sha256=graphical.digest(paths["tool"])) for name in graphical.TOOLS},
                          pe_linker=dict(path=str(paths["pe_linker"]), sha256=graphical.digest(paths["pe_linker"])),
                          output_sha256=hashes([paths["payload.bin"]]))
            build = root / "graphical-console-build.json"
            build.write_text(json.dumps(record))
            receipt = root / "graphical-console-admission.json"
            data = dict(schema="aurora-graphical-console-admission-v1", mode="graphical-console",
                        status="requires-independent-review", clock="tcg-original-clock", build=record,
                        image={"independent_image_result": 1}, stack={"independent_stack_result": 456},
                        sha256=hashes([paths["source"], paths["payload.bin"], build]))
            receipt.write_text(json.dumps(data))
            with patch.object(graphical, "BUILD", root), patch.object(graphical, "RECEIPT", receipt), \
                 patch.object(graphical, "build_files", return_value=[paths["payload.bin"]]), \
                 patch.object(graphical, "source_files", return_value=[paths["source"]]), \
                 patch.object(graphical.common, "hashes", side_effect=hashes), \
                 patch.object(graphical.common, "executable", side_effect=lambda name: record["tools"][name]), \
                 patch.object(graphical, "image_evidence", return_value={"independent_image_result": 1}), \
                 patch.object(graphical, "stack_evidence", return_value={"independent_stack_result": 456}), \
                 patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": graphical.digest(receipt)}):
                graphical.verify_inputs(record, "graphical-console")
                graphical.checked("graphical-console")
                graphical.reviewed("graphical-console")
                for key in ["source", "compiler", "cxx", "payload.bin", "tool", "pe_linker"]:
                    path = paths[key]; saved = path.read_bytes(); path.write_bytes(saved + b" drift")
                    with self.subTest(drift=key), self.assertRaises(ValueError): graphical.checked("graphical-console")
                    path.write_bytes(saved)
                for mode in ["graphical-console-capture", "console", "framebuffer", "graphical-console-stale"]:
                    with self.assertRaises(ValueError): graphical.checked(mode)
                for flag in ["-DAURORA_UEFI_CONSOLE", "-DAURORA_UEFI_FRAMEBUFFER", "-DAURORA_UEFI_GRAPHICAL_CAPTURE", "-O0", "-DUNKNOWN"]:
                    changed = deepcopy(record); changed["flags"].append(flag)
                    with self.subTest(flag=flag), self.assertRaises(ValueError): graphical.verify_inputs(changed, "graphical-console")
                for mutate in [lambda r: r["flags"].pop(), lambda r: r["flags"].reverse(),
                               lambda r: r["objects"].append("console.o"),
                               lambda r: r["translation_unit_flags"].update(runtime=[]),
                               lambda r: r.update(schema="aurora-framebuffer-build-v1")]:
                    changed = deepcopy(record); mutate(changed)
                    with self.assertRaises(ValueError): graphical.verify_inputs(changed, "graphical-console")
                for pin in ["", "0" * 64, "A" * 64, graphical.digest(receipt)[:-1]]:
                    with patch.dict(os.environ, {"GRAPHICAL_CONSOLE_REVIEW_SHA256": pin}), self.assertRaises(ValueError):
                        graphical.reviewed("graphical-console")
                # A caller cannot relabel automatic evidence as independent acceptance.
                changed = deepcopy(data); changed["status"] = "accepted"; receipt.write_text(json.dumps(changed))
                with self.assertRaises(ValueError): graphical.checked("graphical-console")
                receipt.write_text(json.dumps(data))
                for key in list(data):
                    changed = deepcopy(data); del changed[key]; receipt.write_text(json.dumps(changed))
                    with self.subTest(missing_receipt_key=key), self.assertRaises(ValueError): graphical.checked("graphical-console")
                for key, value in [("image", {}), ("stack", {}), ("image", {"independent_image_result": True}),
                                   ("stack", {"independent_stack_result": 0}), ("extra", True)]:
                    changed = deepcopy(data); changed[key] = value; receipt.write_text(json.dumps(changed))
                    with self.subTest(forged_receipt_key=key, value=value), self.assertRaises(ValueError): graphical.checked("graphical-console")
                for raw in ['{"mode":"graphical-console","mode":"graphical-console"}',
                            '{"nested":{"same":1,"same":1}}', '{"number":NaN}', '{"number":Infinity}']:
                    receipt.write_text(raw)
                    with self.assertRaises(ValueError): graphical.read_json(receipt)
                receipt.write_text(json.dumps(data))
                build.write_text(json.dumps(dict(record, objects=["payload.bin", "console.o"])))
                with self.assertRaises(ValueError): graphical.checked("graphical-console")


if __name__ == "__main__":
    unittest.main()

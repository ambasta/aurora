#!/usr/bin/env python3
"""Pure hostile Event admission controls; no compiler, guest or qualification."""

from pathlib import Path
import copy
import importlib.util
import json
import os
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "event_admission_controls", ROOT / "scripts/kernel_iommu_event_admission.py"
)
admission = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = admission
spec.loader.exec_module(admission)
policy = admission.image
decoder = admission.load("event_test_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")


def defined(name, kind="T"):
    return "0000000000000010 " + kind + " " + name + "\n"


def imported(name):
    return "                 U " + name + "\n"


def call(name, address=0):
    return (
        f" {address:x}: e8 00 00 00 00 call {address + 5:x} <fixture+0x5> {address + 1:x}: R_X86_64_PLT32 {name}-0x4\n"
    )


def fixture(mode=admission.MODES[0]):
    if mode == "iommu-event-observe":
        symbols = defined("uefi_event_observation") + defined("aurora_kernel_value")
        objects = {name: "" for name in policy.event_objects(mode)}
        objects["language"] = defined("aurora_kernel_value")
        objects["pci"] = defined("uefi_event_observation")
        return dict(symbols=symbols, object_symbols=objects, calls={}, language_bindings={}, mode=mode)
    symbols = "".join(
        defined(name) for name in policy.EVENT_BRIDGES | policy.EVENT_IMPORTS | policy.EVENT_REFLECTION_HELPERS
    )
    symbols += defined(admission.ENTRY, "t") + defined("aurora_kernel_value", "t")
    objects = {name: "" for name in policy.EVENT_OBJECTS}
    objects["language"] = "".join(defined(name) for name in policy.EVENT_BRIDGES | policy.EVENT_REFLECTION_HELPERS)
    objects["language"] += defined(admission.ENTRY, "t") + defined("aurora_kernel_value", "t")
    objects["language"] += "".join(imported(name) for name in policy.EVENT_IMPORTS)
    objects["event-intake"] = "".join(defined(name) for name in policy.EVENT_IMPORTS)
    if mode != "iommu-event-overflow":
        objects["event-intake"] += imported(admission.BRIDGE)
    objects["payload"] = imported(admission.VALUE_BRIDGE)
    calls = {
        "event-intake": "" if mode == "iommu-event-overflow" else call(admission.BRIDGE),
        "payload": call(admission.VALUE_BRIDGE),
        "language": "".join(call(name, 16 * index) for index, name in enumerate(sorted(policy.EVENT_IMPORTS))),
    }
    bindings = {name: ("GLOBAL", "HIDDEN") for name in policy.EVENT_BRIDGES}
    bindings.update({name: ("GLOBAL", "DEFAULT") for name in policy.EVENT_REFLECTION_HELPERS})
    bindings.update({admission.ENTRY: ("LOCAL", "DEFAULT"), "aurora_kernel_value": ("LOCAL", "DEFAULT")})
    return dict(symbols=symbols, object_symbols=objects, calls=calls, language_bindings=bindings, mode=mode)


def body(operations):
    return [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(operations)]


class EventAdmission(unittest.TestCase):
    def test_exact_profiles_and_selectors(self):
        for index, mode in enumerate(admission.MODES):
            flags = list(admission.BASE_FLAGS + admission.PROFILE_FLAGS) + ["-DAURORA_IOMMU_EVENT_CASE=" + str(index)]
            admission.verify_flags(mode, flags)
            for bad in (
                flags + ["-DAURORA_UEFI_CONSOLE"],
                flags[:-1],
                flags[::-1],
                flags + [flags[-1]],
                flags[:-1] + ["-DAURORA_IOMMU_EVENT_CASE=" + str((index + 1) % 4)],
                flags + ["-O0"],
            ):
                with self.assertRaises(ValueError):
                    admission.verify_flags(mode, bad)
        with self.assertRaises(ValueError):
            admission.verify_flags("iommu-event-unknown", [])
        self.assertTrue(policy.image_options(["--iommu-event"])["require_iommu_event"])
        for args in (
            ["--iommu-event", "--ipc-policy"],
            ["--graphical-console", "--iommu-event"],
            ["--iommu-event", "--iommu-event"],
            ["--event"],
        ):
            with self.assertRaises(ValueError):
                policy.image_options(args)

    def test_observation_cannot_link_or_inherit_production_authority(self):
        valid = fixture("iommu-event-observe")
        policy.event_object_policy(**valid)
        for owner in valid["object_symbols"]:
            for name in (
                admission.BOOTSTRAP,
                admission.BRIDGE,
                "uefi_event_backing",
                "uefi_event_terminal",
                "__au_runtime_console_put",
                "BootLifetimeRing",
                "EventAdmission",
            ):
                changed = copy.deepcopy(valid)
                changed["object_symbols"][owner] += imported(name)
                with self.assertRaises(ValueError):
                    policy.event_object_policy(**changed)
        for owner in valid["object_symbols"]:
            changed = copy.deepcopy(valid)
            del changed["object_symbols"][owner]
            with self.assertRaises(ValueError):
                policy.event_object_policy(**changed)
        for mode in admission.MODES[:-1]:
            changed = copy.deepcopy(valid)
            changed["mode"] = mode
            with self.assertRaises(ValueError):
                policy.event_object_policy(**changed)
        with self.assertRaises(ValueError):
            policy.profile_selection(valid["symbols"], valid["object_symbols"], False)

    def test_exact_authority_ownership_and_direct_calls(self):
        for mode in admission.MODES:
            valid = fixture(mode)
            policy.event_object_policy(**valid)
        valid = fixture()
        mutations = []
        for name in ("console-entry", "runtime-entry", "user-clean", "unexpected"):
            changed = copy.deepcopy(valid)
            changed["object_symbols"][name] = ""
            mutations.append(changed)
        for owner in ("payload", "acpi", "pci", "runtime", "loader"):
            changed = copy.deepcopy(valid)
            changed["object_symbols"][owner] += imported("__au_runtime_iommu_event_poll")
            mutations.append(changed)
        for name in ("__au_runtime_console_next", "__au_runtime_display_pixel", "__au_runtime_bytes_allocate"):
            changed = copy.deepcopy(valid)
            changed["object_symbols"]["language"] += imported(name)
            mutations.append(changed)
        for owner in ("language", "event-intake", "payload"):
            changed = copy.deepcopy(valid)
            changed["calls"][owner] = ""
            mutations.append(changed)
        for name in (admission.ENTRY, admission.BRIDGE, admission.VALUE_BRIDGE):
            changed = copy.deepcopy(valid)
            changed["language_bindings"][name] = ("GLOBAL", "DEFAULT")
            mutations.append(changed)
        changed = copy.deepcopy(valid)
        changed["object_symbols"]["language"] = changed["object_symbols"]["language"].replace(
            "U __au_runtime_iommu_event_poll", "w __au_runtime_iommu_event_poll"
        )
        mutations.append(changed)
        changed = copy.deepcopy(valid)
        changed["mode"] = "iommu-event-overflow"
        mutations.append(changed)
        changed = fixture("iommu-event-overflow")
        changed["mode"] = "iommu-event-denial"
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                policy.event_object_policy(**changed)

    def test_event_reflection_helpers_are_profile_specific(self):
        self.assertEqual(policy.EVENT_REFLECTION_HELPERS, {"aurora_reflect_size", "aurora_reflect_field_count"})
        valid = fixture()
        policy.event_object_policy(**valid)
        for name in policy.EVENT_REFLECTION_HELPERS:
            for location in ("linked", "language"):
                changed = copy.deepcopy(valid)
                if location == "linked":
                    changed["symbols"] = changed["symbols"].replace(defined(name), "")
                else:
                    changed["object_symbols"]["language"] = changed["object_symbols"]["language"].replace(
                        defined(name), ""
                    )
                with self.subTest(missing=name, location=location), self.assertRaises(ValueError):
                    policy.event_object_policy(**changed)
        for name in (
            "__au_reflect_s1_size",
            "__au_reflect_s1_field_count",
            "__au_reflect_s2_size",
            "aurora_reflect_extra",
        ):
            changed = copy.deepcopy(valid)
            changed["symbols"] += defined(name)
            with self.subTest(foreign=name, location="linked"), self.assertRaises(ValueError):
                policy.event_object_policy(**changed)
            for owner in policy.EVENT_OBJECTS:
                changed = copy.deepcopy(valid)
                changed["object_symbols"][owner] += defined(name, "t")
                changed["language_bindings"].update({name: ("LOCAL", "DEFAULT")} if owner == "language" else {})
                with self.subTest(foreign=name, owner=owner), self.assertRaises(ValueError):
                    policy.event_object_policy(**changed)

    def test_event_requires_explicit_flag_and_excludes_foreign_authority(self):
        valid = fixture()
        with self.assertRaises(ValueError):
            policy.profile_selection(valid["symbols"], valid["object_symbols"], False)
        for name in (
            "uefi_console_interrupt",
            "uefi_runtime_enter",
            "uefi_service_drain_begin",
            "aurora_user_main",
            "aurora_kernel_budget_tick",
            "__cxa_throw",
            "_GLOBAL__sub_I_event",
            "malloc",
            "__au_runtime_unknown",
        ):
            with self.assertRaises(ValueError):
                policy.profile_selection(valid["symbols"] + defined(name), valid["object_symbols"], False, True)
        for kind in ("B", "D", "W", "w", "u", "U"):
            changed = valid["symbols"].replace("T " + admission.BRIDGE, kind + " " + admission.BRIDGE)
            with self.assertRaises(ValueError):
                policy.profile_selection(changed, valid["object_symbols"], False, True)

    def test_exact_private_bridge(self):
        ops = [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("mov", "%rdi,%r11"),
            ("call", "100 <entry>"),
            ("leave", ""),
            ("ret", ""),
        ]
        admission.verify_bridge(decoder, body(ops), {256: admission.ENTRY})
        for index, replacement in (
            (2, ("mov", "%rsi,%r11")),
            (3, ("call", "101 <wrong>")),
            (4, ("pop", "%rbp")),
            (5, ("ret", "$0x8")),
        ):
            changed = list(ops)
            changed[index] = replacement
            with self.assertRaises(ValueError):
                admission.verify_bridge(decoder, body(changed), {256: admission.ENTRY})
        admission.verify_value_bridge(decoder, body([("jmp", "100 <value>")]), {256: "aurora_kernel_value"})
        for ops in ([("call", "100 <value>")], [("jmp", "101 <wrong>")], [("ret", "")]):
            with self.assertRaises(ValueError):
                admission.verify_value_bridge(decoder, body(ops), {256: "aurora_kernel_value"})

    def test_unchanged_stack_cap_with_existing_exception_reserve(self):
        self.assertEqual(admission.verify_stack_budgets(14848, 4096, 159), 512)
        self.assertEqual(admission.verify_stack_budgets(14336, 14336, 1024), 1024)
        for values in (
            (14849, 1, 159),
            (1, 14849, 159),
            (14337, 1, 1024),
            (1, 14337, 1024),
            (1, -1, 0),
            (1, True, 1),
            (1, 1, -1),
        ):
            with self.assertRaises(ValueError):
                admission.verify_stack_budgets(*values)

    def test_fail_closed_decoder_is_not_replaced(self):
        symbols = {"bad": decoder.Symbol("bad", 0, 2, 1, 2)}
        for op, args in (
            ("sub", "%rax,%rsp"),
            ("and", "$0xffffffffffffffe0,%rsp"),
            ("push", "0x100(%rsp)"),
            ("call", "*%rax"),
            ("unknown", ""),
        ):
            instructions = {row.address: row for row in body([(op, args), ("ret", "")])}
            with self.assertRaises(ValueError):
                decoder.analyze_function(symbols["bad"], instructions, {0: "bad"})

    def test_retained_bss_extent_owner_and_nonoverlap(self):
        symbols = [
            decoder.Symbol("__payload_read_end", 0x10000, 0, 1, 0),
            decoder.Symbol("__payload_memory_end", 0x1C000, 0, 1, 0),
        ]
        addresses = dict(terminal=0x10000, backing=0x11000, ring=0x19000, before_ring=0x1A000, after_ring=0x1B000)
        symbols += [
            decoder.Symbol(name, addresses[role], size, 1, 1) for role, (name, size, _) in admission.RETAINED.items()
        ]
        sections = [(0,) * 10, (0, 8, 3, 0x10000, 0, 0xC000, 0, 0, 4096, 0)]
        original = SimpleNamespace(symbols=symbols, sections=sections)
        owner = SimpleNamespace(symbols=symbols[2:], sections=sections)
        with patch.object(admission, "load", return_value=SimpleNamespace(Elf=lambda _: owner)):
            result = admission.backing_evidence(original, Path("unused"))
            self.assertEqual(result["retained_bytes"], 45056 + 672)
            self.assertEqual(result["objects"]["backing"]["arena_offset"], 0x33000)
            for role in admission.RETAINED:
                index = 2 + list(admission.RETAINED).index(role)
                old = symbols[index]
                for replacement in (
                    decoder.Symbol(old.name, old.address + 1, old.size, old.section, old.kind),
                    decoder.Symbol(old.name, old.address, old.size + 8, old.section, old.kind),
                    decoder.Symbol(old.name, old.address, old.size, old.section, 2),
                ):
                    changed = list(symbols)
                    changed[index] = replacement
                    with self.assertRaises(ValueError):
                        admission.backing_evidence(SimpleNamespace(symbols=changed, sections=sections), Path("unused"))
            for kind, flags in ((1, 3), (8, 7), (8, 2)):
                changed = [sections[0], (0, kind, flags, 0x10000, 0, 0xC000, 0, 0, 4096, 0)]
                with self.assertRaises(ValueError):
                    admission.backing_evidence(SimpleNamespace(symbols=symbols, sections=changed), Path("unused"))
            changed = list(symbols)
            ring_index = 2 + list(admission.RETAINED).index("ring")
            row = symbols[ring_index]
            changed[ring_index] = decoder.Symbol(row.name, 0x11000, row.size, row.section, row.kind)
            with self.assertRaises(ValueError):
                admission.backing_evidence(SimpleNamespace(symbols=changed, sections=sections), Path("unused"))
            owner.symbols = []
            with self.assertRaises(ValueError):
                admission.backing_evidence(original, Path("unused"))

    def test_fence_operands(self):
        for op in ("lfence", "mfence", "pause"):
            admission.verify_scalar_instruction(decoder.Instruction(0, 1, op, ""))
            with self.assertRaises(ValueError):
                admission.verify_scalar_instruction(decoder.Instruction(0, 1, op, "%rax"))

    def test_review_is_external_and_json_is_unambiguous(self):
        with tempfile.TemporaryDirectory(prefix="event-admission-") as directory:
            receipt = Path(directory) / "receipt.json"
            receipt.write_text('{"mode":"one","mode":"two"}')
            with self.assertRaises(ValueError):
                admission.read_json(receipt)
            receipt.write_text('{"value":NaN}')
            with self.assertRaises(ValueError):
                admission.read_json(receipt)
            receipt.write_text('{"mode":"iommu-event-denial"}')
            with (
                patch.object(admission, "RECEIPT", receipt),
                patch.object(admission, "checked", return_value={"okay": True}) as check,
            ):
                for pin in ("", "bad", "0" * 64):
                    with patch.dict(os.environ, {"IOMMU_EVENT_REVIEW_SHA256": pin}), self.assertRaises(ValueError):
                        admission.reviewed(admission.MODES[0])
                check.assert_not_called()
                with patch.dict(os.environ, {"IOMMU_EVENT_REVIEW_SHA256": admission.digest(receipt)}):
                    self.assertEqual(admission.reviewed(admission.MODES[0]), {"okay": True})
                check.assert_called_once_with(admission.MODES[0])


if __name__ == "__main__":
    unittest.main()

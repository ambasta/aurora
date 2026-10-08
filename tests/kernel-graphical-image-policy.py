#!/usr/bin/env python3
"""Pure image-policy controls. No compiler, binutils, image build, guest or device.

Fixtures are independent nm/readelf/objdump-shaped policy inputs, not qualification
of generated code. Every mutation starts from a freshly accepted valid baseline.
"""

import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("graphical_image_policy", ROOT / "tests/kernel-uefi-image.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)

OBJECTS = (
    "payload",
    "payload-entry",
    "language",
    "acpi",
    "pci",
    "runtime",
    "memory",
    "graphical-console",
    "console-entry",
    "loader",
    "embed",
    "transition",
    "loader-pe",
    "embed-pe",
    "transition-pe",
    "memory-pe",
)
ENTRY = "__au_v_m1_24kernel_graphical_console_n0__d17graphical_console"
BRIDGE, VALUE = "__au_runtime_graphical_entry", "__au_runtime_graphical_value"
REFLECTION = ("aurora_reflect_size", "aurora_reflect_field_count")
NEXT, PUT, PIXEL = "__au_runtime_console_next", "__au_runtime_console_put", "__au_runtime_display_pixel"


def defined(name, kind="T"):
    return "0000000000000010 " + kind + " " + name + "\n"


def imported(name):
    return "                 U " + name + "\n"


def call(name, address=0):
    return (
        f" {address:x}: e8 00 00 00 00 call {address + 5:x} <fixture+0x5> {address + 1:x}: R_X86_64_PLT32 {name}-0x4\n"
    )


def paired():
    linked = "".join(defined(name) for name in (BRIDGE, VALUE, NEXT, PUT, PIXEL, "uefi_console_interrupt"))
    linked += "".join(defined(name) for name in REFLECTION)
    linked += defined(ENTRY, "t") + defined("aurora_kernel_value", "t")
    objects = {name: "" for name in OBJECTS}
    objects["language"] = defined(BRIDGE) + defined(VALUE) + defined(ENTRY, "t") + defined("aurora_kernel_value", "t")
    objects["language"] += "".join(defined(name) for name in REFLECTION)
    objects["language"] += imported(NEXT) + imported(PIXEL)
    objects["graphical-console"] = defined(NEXT) + defined(PUT) + defined(PIXEL) + imported(BRIDGE)
    objects["payload"] = imported(VALUE)
    objects["console-entry"] = defined("uefi_console_interrupt") + imported("uefi_console_interrupt_dispatch")
    objects["graphical-console"] += defined("uefi_console_interrupt_dispatch") + imported("uefi_console_interrupt")
    calls = {name: "" for name in OBJECTS}
    calls["graphical-console"] = call(BRIDGE)
    calls["payload"] = call(VALUE)
    calls["language"] = call(NEXT) + call(PIXEL, 16)
    bindings = {
        BRIDGE: ("GLOBAL", "HIDDEN"),
        VALUE: ("GLOBAL", "HIDDEN"),
        ENTRY: ("LOCAL", "DEFAULT"),
        "aurora_kernel_value": ("LOCAL", "DEFAULT"),
    }
    bindings.update({name: ("GLOBAL", "DEFAULT") for name in REFLECTION})
    return dict(symbols=linked, object_symbols=objects, calls=calls, language_bindings=bindings)


def serial():
    symbols = defined("uefi_console_interrupt") + defined("__au_runtime_console_entry")
    language = defined("__au_runtime_console_entry") + defined("__au_runtime_console_value")
    calls = {name: "" for name in ("payload", "acpi", "pci", "runtime", "console", "loader", "language")}
    calls["console"] = call("__au_runtime_console_entry")
    calls["language"] = call(NEXT) + call(PUT, 16)
    return dict(
        symbols=symbols, language_symbols=language, calls=calls, contents={name: b"\0clean object\0" for name in calls}
    )


class ImagePolicy(unittest.TestCase):
    def setUp(self):
        # A future accidental tool invocation makes these controls fail closed.
        self.no_tools = patch.object(policy.subprocess, "check_output", side_effect=AssertionError("No external tools"))
        self.no_tools.start()
        self.addCleanup(self.no_tools.stop)

    def baseline(self):
        fixture = paired()
        policy.graphical_object_policy(**fixture)
        return copy.deepcopy(fixture)

    def reject(self, mutate):
        fixture = self.baseline()
        mutate(fixture)
        with self.assertRaises(ValueError):
            policy.graphical_object_policy(**fixture)

    def test_explicit_flag_and_legacy_flags(self):
        for args in (
            [],
            ["--ipc-policy"],
            ["--owned-bytes"],
            ["--ipc-policy", "--disposal-policy"],
            ["--graphical-console"],
        ):
            with self.subTest(args=args):
                self.assertEqual(
                    policy.image_options(args)["require_graphical_console"], args == ["--graphical-console"]
                )
        for args in (
            ["--graphical"],
            ["--graphical-console-capture"],
            ["--disposal-policy"],
            ["--graphical-console", "--graphical-console"],
            ["--framebuffer"],
            ["--graphical-console", "--ipc-policy"],
            ["--owned-bytes", "--graphical-console"],
            ["--graphical-console", "--disposal-policy"],
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                policy.image_options(args)

    def test_paired_requires_flag_independent_of_irq(self):
        fixture = self.baseline()
        for symbols, objects in (
            (fixture["symbols"], OBJECTS),
            (fixture["symbols"], ()),
            (defined("uefi_console_interrupt"), OBJECTS),
        ):
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                policy.profile_selection(symbols, objects, False)

    def test_missing_and_extra_objects(self):
        for name in OBJECTS:
            with self.subTest(missing=name):
                self.reject(lambda f, n=name: f["object_symbols"].pop(n))
        for name in ("console", "framebuffer", "runtime-entry", "owned-bytes-runtime", "unexpected"):
            with self.subTest(extra=name):
                self.reject(lambda f, n=name: f["object_symbols"].update({n: ""}))
        for replacement in ("console", "framebuffer"):

            def cross(f):
                f["object_symbols"][replacement] = f["object_symbols"].pop("graphical-console")

            with self.subTest(replacement=replacement):
                self.reject(cross)

    def test_linked_authority_inventory(self):
        for name in (BRIDGE, VALUE, NEXT, PUT, PIXEL, "uefi_console_interrupt", ENTRY):
            with self.subTest(missing=name):
                self.reject(
                    lambda f, n=name: f.update(symbols=f["symbols"].replace(defined(n, "t" if n == ENTRY else "T"), ""))
                )
        for name in (
            "__au_runtime_console_entry",
            "__au_runtime_console_value",
            "__au_runtime_display_entry",
            "__au_runtime_display_value",
            "__au_runtime_bytes_at",
            "uefi_runtime_enter",
            "aurora_kernel_budget_tick",
            "aurora_user_entry",
        ):
            with self.subTest(extra=name):
                self.reject(lambda f, n=name: f.update(symbols=f["symbols"] + defined(n)))

    def test_generated_import_mutations(self):
        for name in (NEXT, PIXEL):
            self.reject(
                lambda f, n=name: f["object_symbols"].update(
                    language=f["object_symbols"]["language"].replace(imported(n), "")
                )
            )
        for name in (PUT, "malloc", "__au_runtime_console_entry", "__au_runtime_display_entry"):
            self.reject(
                lambda f, n=name: f["object_symbols"].update(language=f["object_symbols"]["language"] + imported(n))
            )
        self.reject(
            lambda f: f["object_symbols"].update(
                language=f["object_symbols"]["language"].replace(imported(PIXEL), imported(PUT))
            )
        )
        self.reject(
            lambda f: f["object_symbols"].update(
                language=f["object_symbols"]["language"].replace(imported(NEXT), " w " + NEXT + "\n")
            )
        )

    def test_global_and_binding_mutations(self):
        for name in (BRIDGE, VALUE):
            for kind in ("t", "W", "D"):
                self.reject(
                    lambda f, n=name, k=kind: f["object_symbols"].update(
                        language=f["object_symbols"]["language"].replace(defined(n), defined(n, k))
                    )
                )
            for binding in (("GLOBAL", "DEFAULT"), ("LOCAL", "DEFAULT"), ("WEAK", "HIDDEN")):
                self.reject(lambda f, n=name, b=binding: f["language_bindings"].update({n: b}))
            self.reject(lambda f, n=name: f["language_bindings"].pop(n))
        for name in (ENTRY, "aurora_kernel_value"):
            self.reject(
                lambda f, n=name: f["object_symbols"].update(
                    language=f["object_symbols"]["language"].replace(defined(n, "t"), defined(n))
                )
            )
        self.reject(
            lambda f: f["object_symbols"].update(language=f["object_symbols"]["language"] + defined("injected_global"))
        )
        self.reject(
            lambda f: f["object_symbols"].update(
                language=f["object_symbols"]["language"] + defined("injected_data", "B")
            )
        )
        self.reject(lambda f: f["language_bindings"].update({"injected_function": ("LOCAL", "DEFAULT")}))

    def test_crossed_owners_and_bridge_importers(self):
        for name in (NEXT, PUT, PIXEL):

            def cross(f, n=name):
                f["object_symbols"]["graphical-console"] = f["object_symbols"]["graphical-console"].replace(
                    defined(n), ""
                )
                f["object_symbols"]["runtime"] += defined(n)

            self.reject(cross)
        for name in (BRIDGE, VALUE):
            self.reject(lambda f, n=name: f["object_symbols"].update(runtime=defined(n)))
        for owner, name in (("payload", VALUE), ("graphical-console", BRIDGE)):
            self.reject(
                lambda f, o=owner, n=name: f["object_symbols"].update(
                    {o: f["object_symbols"][o].replace(imported(n), "")}
                )
            )
        self.reject(lambda f: f["object_symbols"].update(payload=imported(BRIDGE)))
        self.reject(lambda f: f["object_symbols"].update(runtime=imported(PIXEL)))
        self.reject(lambda f: f["object_symbols"].update(runtime=defined(ENTRY, "t")))

    def test_exact_language_only_reflection_helpers(self):
        self.assertEqual(policy.REFLECTION_HELPERS, frozenset(REFLECTION))
        for name in REFLECTION:
            self.reject(lambda f, n=name: f.update(symbols=f["symbols"].replace(defined(n), "")))
            for kind in ("t", "D", "W", "U"):
                self.reject(
                    lambda f, n=name, k=kind: f["object_symbols"].update(
                        language=f["object_symbols"]["language"].replace(defined(n), defined(n, k))
                    )
                )
            for binding in (("GLOBAL", "HIDDEN"), ("LOCAL", "DEFAULT"), ("WEAK", "DEFAULT")):
                self.reject(lambda f, n=name, b=binding: f["language_bindings"].update({n: b}))
            for owner in ("runtime", "graphical-console", "loader", "payload"):
                for row in (defined(name), imported(name)):
                    self.reject(lambda f, o=owner, v=row: f["object_symbols"].update({o: f["object_symbols"][o] + v}))

            def cross(f, n=name):
                f["object_symbols"]["language"] = f["object_symbols"]["language"].replace(defined(n), "")
                f["object_symbols"]["runtime"] += defined(n)

            self.reject(cross)
        for extra in ("aurora_reflect_address", "aurora_reflect_size_extra", "unrelated_global"):
            self.reject(
                lambda f, n=extra: f["object_symbols"].update(language=f["object_symbols"]["language"] + defined(n))
            )
            self.reject(lambda f, n=extra: f["language_bindings"].update({n: ("GLOBAL", "DEFAULT")}))
        self.reject(lambda f: f.update(symbols=f["symbols"] + defined("aurora_reflect_address")))

    def test_irq_engine_definition_substitution(self):
        for name, owner in (
            ("uefi_console_interrupt", "console-entry"),
            ("uefi_console_interrupt_dispatch", "graphical-console"),
        ):

            def cross(f, n=name, o=owner):
                f["object_symbols"][o] = f["object_symbols"][o].replace(defined(n), "")
                f["object_symbols"]["runtime"] += defined(n)

            self.reject(cross)
        for name, owner, importer in (
            ("uefi_console_interrupt", "console-entry", "graphical-console"),
            ("uefi_console_interrupt_dispatch", "graphical-console", "console-entry"),
        ):
            for foreign in sorted(policy.GRAPHICAL_OBJECTS - {owner, importer}):
                self.reject(
                    lambda f, n=name, o=foreign: f["object_symbols"].update({o: f["object_symbols"][o] + imported(n)})
                )

    def test_missing_crossed_and_malformed_call_relocations(self):
        for owner, name in (("payload", VALUE), ("graphical-console", BRIDGE), ("language", NEXT), ("language", PIXEL)):
            original = call(name, 16 if name == PIXEL else 0)
            variants = (
                "",
                original.replace(name, "__au_runtime_console_entry"),
                original.replace("PLT32", "PC32"),
                original.replace("-0x4", "-0x8"),
                original.replace("e8 00", "e9 00"),
                original.replace("1: R_", "2: R_"),
            )
            for replacement in variants:
                with self.subTest(owner=owner, target=name, replacement=replacement):
                    self.reject(
                        lambda f, o=owner, old=original, new=replacement: f["calls"].update(
                            {o: f["calls"][o].replace(old, new)}
                        )
                    )

    def test_old_console_baseline_and_cross_profile_rejection(self):
        fixture = serial()
        self.assertEqual(
            policy.profile_selection(fixture["symbols"], {"console", "console-entry", "language"}, False), "console"
        )
        policy.console_service_policy(**fixture)
        for key, target in (("console", BRIDGE), ("language", PIXEL)):
            broken = copy.deepcopy(fixture)
            broken["calls"][key] = call(target)
            with self.assertRaises(ValueError):
                policy.console_service_policy(**broken)
        with self.assertRaises(ValueError):
            policy.profile_selection(fixture["symbols"], {"console", "language"}, True)

    def test_framebuffer_baseline_and_wrong_flag(self):
        symbols = defined("__au_runtime_display_entry") + defined("__au_runtime_display_value") + defined(PIXEL)
        objects = {"payload", "language", "framebuffer"}
        self.assertEqual(policy.profile_selection(symbols, objects, False), "ordinary")
        with self.assertRaises(ValueError):
            policy.profile_selection(symbols, objects, True)
        self.reject(
            lambda f: f["object_symbols"].update(language=defined("__au_runtime_display_entry") + imported(PIXEL))
        )

    def test_retired_cpp_guards_for_both_engines(self):
        for graphical in (False, True):
            fixture = serial()
            if graphical:
                graph = self.baseline()
                fixture.update(
                    symbols=graph["symbols"],
                    language_symbols=graph["object_symbols"]["language"],
                    calls=graph["calls"],
                    contents={name: b"clean" for name in OBJECTS},
                    graphical=True,
                )
            policy.console_service_policy(**fixture)
            for owner in (
                "payload",
                "acpi",
                "pci",
                "runtime",
                "graphical-console" if graphical else "console",
                "loader",
            ):
                for token in (
                    "aurora::console::Line::",
                    "aurora::console::Presentation<",
                    "aurora_console_byte",
                    "aurora_console_command",
                    "__au_runtime_bytes_",
                ):
                    broken = copy.deepcopy(fixture)
                    broken["calls"][owner] += token
                    with self.subTest(graphical=graphical, owner=owner, token=token), self.assertRaises(ValueError):
                        policy.console_service_policy(**broken)
                for token in (
                    b"Unknown command.",
                    b"Line rejected:",
                    b"Show commands",
                    b"line capacity=64",
                    b"aurora> ",
                ):
                    broken = copy.deepcopy(fixture)
                    broken["contents"][owner] += token
                    with self.subTest(graphical=graphical, owner=owner, token=token), self.assertRaises(ValueError):
                        policy.console_service_policy(**broken)

    def test_exact_build_routing_and_mandatory_combined_admission(self):
        source = (ROOT / "scripts/kernel-uefi-build.sh").read_text()
        image_case = source[
            source.index("image_policy=()") : source.index('python3 tests/kernel-uefi-image.py "${image_policy[@]}"')
        ]
        self.assertEqual(image_case.count("--graphical-console"), 1)
        self.assertIn("graphical-console|graphical-console-capture) image_policy+=(--graphical-console) ;;", image_case)
        for action in ("begin", "end", "emit"):
            self.assertIn("scripts/kernel_graphical_console_admission.py " + action + ' --mode "$UEFI_MODE"', source)
        self.assertLess(
            source.index('python3 tests/kernel-uefi-image.py "${image_policy[@]}"'),
            source.index("scripts/kernel_graphical_console_admission.py end --mode"),
        )


if __name__ == "__main__":
    unittest.main()

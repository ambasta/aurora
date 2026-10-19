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
spec = importlib.util.spec_from_file_location("graphical_image_policy", ROOT / "scripts/kernel_uefi_image.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
capture_spec = importlib.util.spec_from_file_location(
    "graphical_capture_artifact_policy", ROOT / "scripts/kernel_graphical_console_admission.py"
)
capture_policy = importlib.util.module_from_spec(capture_spec)
sys.modules[capture_spec.name] = capture_policy
capture_spec.loader.exec_module(capture_policy)

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
REFLECTION = (
    "aurora_reflect_size",
    "aurora_reflect_field_count",
    *(f"__au_reflect_s{module}_{field}" for module in (1, 2, 3, 4, 5, 6) for field in ("size", "field_count")),
)
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


def fixture_artifacts(capture=False):
    # These byte containers exercise only the absence/ownership policy. They
    # intentionally cannot satisfy the unimplemented actual linked fixture proof.
    paths = ("payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI") + tuple(name + ".o" for name in OBJECTS)
    artifacts = {name: dict(contents=b"normal\0", symbols=b"", relocations=b"") for name in paths}
    if capture:
        artifacts["graphical-console.o"] = dict(
            contents=b"AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=\0",
            symbols=b"capture_scenario\npixel_attempts\n",
            relocations=b"",
        )
    return artifacts


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

    def test_console_region_irq_windows_are_required(self):
        drain = {"uefi_service_drain_begin", "uefi_service_drain_end"}
        poll = {"uefi_program_poll_begin", "uefi_program_poll_end"}
        for suffix in ("", "-cancel", "-cancel-ready", "-input", "-output", "-budget", "-fault"):
            mode = "runtime-console-region" + suffix
            expected = drain if suffix in ("-cancel", "-input") else drain | poll
            policy.console_irq_windows(expected, mode)
            for missing in expected:
                with self.assertRaises(ValueError):
                    policy.console_irq_windows(expected - {missing}, mode)
        with self.assertRaises(ValueError):
            policy.console_irq_windows(drain | poll, "unknown")
        with self.assertRaises(ValueError):
            policy.console_irq_windows(drain | poll, "runtime-console-region-cancel")
        self.assertTrue(policy.image_options(["--owned-text", "--console-region"])["require_console_region"])
        with self.assertRaises(ValueError):
            policy.image_options(["--console-region"])

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
        self.assertEqual(policy.common.stack_facts.reflection_inventory(REFLECTION), set(REFLECTION))
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
        for extra in (
            "aurora_reflect_address",
            "aurora_reflect_size_extra",
            "__au_reflect_s7_size",
            "__au_reflect_s1_address",
            "unrelated_global",
        ):
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

    def test_serial_reflection_names_remain_closed(self):
        for name, accepted in (("__au_reflect_s3_size", True), ("__au_reflect_s3_put", False)):
            fixture = serial()
            fixture["language_symbols"] += defined(name)
            if accepted:
                policy.console_service_policy(**fixture)
            else:
                with self.assertRaises(ValueError):
                    policy.console_service_policy(**fixture)

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
        spec = importlib.util.spec_from_file_location("kernel_profiles", ROOT / "scripts/kernel_profiles.py")
        catalog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(catalog)
        selected = catalog.profiles()
        combined = {name for name, recipe in selected.items() if recipe["admission"] == "graphical"}
        self.assertEqual(combined, {"uefi/graphical-console", "uefi/graphical-console-capture"})
        for name, recipe in selected.items():
            self.assertEqual("--graphical-console" in recipe["image_options"], name in combined)
        with self.assertRaises(ValueError):
            catalog.select("uefi", {}, "graphical-console-future")

    def test_production_fixture_absence_covers_every_artifact_and_evidence_channel(self):
        baseline = fixture_artifacts()
        result = capture_policy.capture_artifact_evidence("graphical-console", baseline)
        self.assertEqual(result["status"], "fixture-absent")
        self.assertEqual(result["fixture_tokens"], {})
        # Independent unique names cover data, state, functions and relocation
        # targets. Generic "normal" and the production framebuffer restoration
        # helper must remain legal.
        tokens = (
            b"graphical_capture",
            b"capture_scenario",
            b"capture_gate",
            b"pixel_attempts",
            b"AURORA_GRAPHICAL_CAPTURE_GATE:",
            b"AURORA_GRAPHICAL_CAPTURE_RELEASED",
            b"AURORA_GRAPHICAL_PRE_SAMPLE:",
            b"capture initial state",
            b"capture UART status",
            b"capture selector",
            b"capture release deadline",
            b"pixel attempt counter overflow",
            b"cross-console",
            b"cross-display",
            b"stale-console",
            b"stale-display",
            b"first-pixel-error",
            b"interior-pixel-error",
        )
        for name in baseline:
            for field in ("contents", "symbols", "relocations"):
                for token in tokens:
                    changed = copy.deepcopy(baseline)
                    changed[name][field] += token
                    with (
                        self.subTest(name=name, field=field, token=token),
                        self.assertRaisesRegex(ValueError, "Capture fixture leaked into production"),
                    ):
                        capture_policy.capture_artifact_evidence("graphical-console", changed)
        baseline["graphical-console.o"]["contents"] += b"normal\0normal private memory\0"
        baseline["graphical-console.o"]["symbols"] += b"FramebufferPayload::restore_graphical_fixture\n"
        capture_policy.capture_artifact_evidence("graphical-console", baseline)

    def test_capture_fixture_ownership_does_not_replace_state_layout_or_behavior_gates(self):
        baseline = fixture_artifacts(capture=True)
        evidence = capture_policy.capture_artifact_evidence("graphical-console-capture", baseline)
        self.assertEqual(evidence["status"], "structure-only-behavior-qualification-pending")
        with self.assertRaisesRegex(ValueError, "Missing current capture structure evidence"):
            capture_policy.require_capture_structure(evidence["mode"])
        containers = {"payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI", "embed.o", "embed-pe.o"}
        for name in baseline:
            for field in ("contents", "symbols", "relocations"):
                changed = copy.deepcopy(baseline)
                changed[name][field] += b"capture_scenario"
                if name == "graphical-console.o" or name in containers:
                    capture_policy.capture_artifact_evidence("graphical-console-capture", changed)
                else:
                    with (
                        self.subTest(owner=name, field=field),
                        self.assertRaisesRegex(ValueError, "foreign ownership"),
                    ):
                        capture_policy.capture_artifact_evidence("graphical-console-capture", changed)
        for field, token in (
            ("contents", b"AURORA_GRAPHICAL_CAPTURE_RELEASED: selector="),
            ("symbols", b"capture_scenario"),
            ("symbols", b"pixel_attempts"),
        ):
            changed = copy.deepcopy(baseline)
            changed["graphical-console.o"][field] = changed["graphical-console.o"][field].replace(token, b"wrong")
            with self.subTest(missing=token), self.assertRaisesRegex(ValueError, "Missing capture fixture"):
                capture_policy.capture_artifact_evidence("graphical-console-capture", changed)

    def test_fixture_artifact_inventory_mode_and_evidence_cannot_be_omitted_or_relabeled(self):
        for mode in ("graphical-console", "graphical-console-capture"):
            baseline = fixture_artifacts(capture=mode.endswith("-capture"))
            capture_policy.capture_artifact_evidence(mode, baseline)
            for name in baseline:
                changed = copy.deepcopy(baseline)
                del changed[name]
                with self.subTest(mode=mode, missing=name), self.assertRaisesRegex(ValueError, "artifact inventory"):
                    capture_policy.capture_artifact_evidence(mode, changed)
            changed = copy.deepcopy(baseline)
            changed["fixture.o"] = dict(contents=b"", symbols=b"", relocations=b"")
            with self.assertRaisesRegex(ValueError, "artifact inventory"):
                capture_policy.capture_artifact_evidence(mode, changed)
            for field in ("contents", "symbols", "relocations"):
                changed = copy.deepcopy(baseline)
                del changed["graphical-console.o"][field]
                with self.assertRaisesRegex(ValueError, "evidence fields"):
                    capture_policy.capture_artifact_evidence(mode, changed)
                changed = copy.deepcopy(baseline)
                changed["graphical-console.o"][field] = "untrusted decoded substitute"
                with self.assertRaisesRegex(ValueError, "original bytes"):
                    capture_policy.capture_artifact_evidence(mode, changed)
        for mode in ("capture", "console", "framebuffer", "graphical-console-F"):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "Unknown graphical profile"):
                capture_policy.capture_artifact_evidence(mode, fixture_artifacts())
        with self.assertRaisesRegex(ValueError, "leaked into production"):
            capture_policy.capture_artifact_evidence("graphical-console", fixture_artifacts(capture=True))
        with self.assertRaisesRegex(ValueError, "Missing capture fixture"):
            capture_policy.capture_artifact_evidence("graphical-console-capture", fixture_artifacts())


if __name__ == "__main__":
    unittest.main()

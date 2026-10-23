#!/usr/bin/env python3
"""Compiler-free controls for native kernel generator boundaries, not image qualification."""

import importlib.util
from contextlib import contextmanager
import copy
import ctypes
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assembly = load("kernel_assembly", "scripts/meson_aurora_assembly.py")
objects = load("kernel_object", "scripts/meson_kernel_object.py")
profiles = load("kernel_profiles", "scripts/kernel_profiles.py")
clock = load("kernel_clock", "scripts/kernel_emulator_clock.py")
image = load("kernel_image", "scripts/kernel_uefi_image.py")
transport = load("kernel_transport", "scripts/qemu_transport.py")


class GeneratorBoundaries(unittest.TestCase):
    def test_snapshot_runtime_inventory_remains_exact(self):
        # Literal independent ABI inventory, not derived from the policy helper.
        names = {
            "__au_runtime_bytes_allocate": "T",
            "__au_runtime_bytes_at": "T",
            "__au_runtime_bytes_set": "T",
            "__au_runtime_bytes_drop": "T",
            "__au_runtime_bytes_borrow_length": "T",
            "__au_runtime_bytes_borrow_span": "T",
            "__au_runtime_bytes_resize": "T",
            "__au_runtime_bytes_kernel_fault": "T",
            "__au_runtime_values_allocate": "T",
            "__au_runtime_values_at": "T",
            "__au_runtime_values_set": "T",
            "__au_runtime_values_resize": "T",
            "__au_runtime_snapshot_produce": "T",
            "unrelated_payload_function": "T",
        }
        image.snapshot_runtime_symbols(names)
        for name in names:
            if not name.startswith("__au_runtime_"):
                continue
            with self.subTest(missing=name):
                broken = dict(names)
                del broken[name]
                with self.assertRaisesRegex(ValueError, "Closed snapshot runtime authority inventory"):
                    image.snapshot_runtime_symbols(broken)
            for kind in ("U", "W", "D", "t"):
                with self.subTest(symbol=name, kind=kind):
                    with self.assertRaisesRegex(ValueError, "global text definition"):
                        image.snapshot_runtime_symbols(names | {name: kind})
        for extra in ("__au_runtime_values_borrow", "__au_runtime_values_extra", "__au_runtime_foreign"):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(ValueError, "Closed snapshot runtime authority inventory"):
                    image.snapshot_runtime_symbols(names | {extra: "T"})

    def test_bios_console_uses_direct_native_dispatch(self):
        recipe = (ROOT / "kernel-images/meson.build").read_text()
        selection = "if bios_console\n      flags += ['-fno-jump-tables']\n    endif"
        self.assertEqual(recipe.count("-fno-jump-tables"), 1)
        self.assertIn("bios_console = platform == 'bios' and mode == 'console'", recipe)
        self.assertIn(selection, recipe)
        native_begin = recipe.index("foreach name : cpp_names")
        native_end = recipe.index("native = static_library", native_begin)
        self.assertIn(selection, recipe[native_begin:native_end])

    def test_reflection_is_closed_only_for_admitted_consumers(self):
        recipe = (ROOT / "kernel-images/meson.build").read_text()
        selection = (
            "if admission == 'program' or ram_scratchpad\n"
            "    root_args += ['--referenced-reflection-only', '--local-symbols']\n  endif"
        )
        self.assertIn(selection, recipe)
        self.assertIn(
            "ram_scratchpad = platform == 'uefi' and mode in "
            "['ram-scratchpad-console', 'ram-scratchpad-console-fixture']",
            recipe,
        )
        self.assertIn(
            "profile_options = kernel_options + "
            "{'optimization': (admission == 'program' or ram_scratchpad) ? 's' : '2'}",
            recipe,
        )
        self.assertEqual(recipe.count("profile_options ="), 1)
        self.assertIn("override_options: profile_options", recipe)
        self.assertEqual(recipe.count("if admission == 'program' or bios_console or ram_scratchpad"), 2)
        self.assertIn(
            "if admission == 'program' or ram_scratchpad\n"
            "      root_args += ['--bridge', kernel_source / 'kernel/uefi/kernel-policy-entry.S']",
            recipe,
        )
        self.assertIn(
            "if admission == 'program' or ram_scratchpad\n      metadata_outputs += ['program-poll-metadata.json']",
            recipe,
        )
        self.assertIn(
            "if '--service-budget' in user_options\n      metadata_outputs += ['service-timer-metadata.json']",
            recipe,
        )
        self.assertEqual(recipe.count("--referenced-reflection-only"), 3)
        self.assertEqual(recipe.count("--local-symbols"), 3)
        uart_recipe = recipe[
            recipe.index("  if bios_console\n    uart_assembly =") : recipe.index(
                "  foreach name : profile_data[key + '.assembly']"
            )
        ]
        self.assertIn("files('../examples/kernel-uart.au')", uart_recipe)
        self.assertIn("'--local-symbols', '--referenced-reflection-only'", uart_recipe)
        self.assertIn("kernel/uart-policy-entry.S", uart_recipe)
        self.assertLess(recipe.index(selection), recipe.index("language = custom_target"))
        caller_selection = (
            "if (call_client and name == 'clean') or owned_text or ram_file\n"
            "        user_root_args += ['--referenced-reflection-only']\n"
            "      endif"
        )
        self.assertIn(
            "call_client = combined and '--blocking-call' in profile_data[key + '.user_options'].split('|')",
            recipe,
        )
        self.assertIn("ram_file = '--ram-file' in profile_data[key + '.user_options'].split('|')", recipe)
        self.assertEqual(recipe.count("if admission == 'program' or call_client or owned_text or ram_file"), 2)
        user_recipe = recipe[recipe.index("user_root_args = []") :]
        self.assertIn(caller_selection, user_recipe)
        self.assertEqual(user_recipe.count("--referenced-reflection-only"), 1)
        self.assertLess(recipe.index(caller_selection), recipe.index("user_assembly = custom_target"))
        self.assertIn(
            "owned_text = '--owned-text' in image_options and name == 'clean'",
            user_recipe,
        )
        self.assertIn("if owned_text\n        user_root_args += ['--local-symbols']\n      endif", user_recipe)
        self.assertEqual(user_recipe.count("--local-symbols"), 1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler, source = root / "compiler", root / "source.au"
            compiler.write_bytes(b"fake compiler")
            source.write_text("module test;\n")
            flags = ("--referenced-reflection-only", "--local-symbols")
            for selected in ((), flags[:1], flags[1:], flags):
                output, depfile = root / "output.s", root / "output.d"
                arguments = [
                    "generator",
                    "--compiler",
                    str(compiler),
                    "--source",
                    str(source),
                    "--output",
                    str(output),
                    "--depfile",
                    str(depfile),
                ]
                arguments.extend(selected)

                def emit(command, **kwargs):
                    for flag in flags:
                        self.assertEqual(command.count(flag), int(flag in selected))
                    Path(command[command.index("-o") + 1]).write_text("complete assembly\n")

                with patch("sys.argv", arguments), patch.object(assembly.subprocess, "run", side_effect=emit):
                    assembly.main()
                self.assertEqual(output.read_text(), "complete assembly\n")

    def test_import_dependencies_include_membership_and_full_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "main.au"
            source.write_text("module main;\n")
            roots = [root / "policies", root / "library"]
            for module_root in roots:
                (module_root / "nested").mkdir(parents=True)
                (module_root / "nested/shared.au").write_text("module shared;\n")
            deps = set(assembly.dependencies(source, roots))
            self.assertIn(source, deps)
            for module_root in roots:
                self.assertTrue({module_root, module_root / "nested", module_root / "nested/shared.au"} <= deps)
            added = roots[0] / "nested/ambiguous.au"
            added.write_text("module shared;\n")
            self.assertIn(added, assembly.dependencies(source, roots))
            added.unlink()
            self.assertNotIn(added, assembly.dependencies(source, roots))
            self.assertIn(added.parent, assembly.dependencies(source, roots))

    def test_import_dependencies_preserve_symlink_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "real.au"
            source.write_text("module real;\n")
            linked_source = root / "linked.au"
            linked_source.symlink_to(source)
            module_root = root / "modules"
            module_root.mkdir()
            linked_root = root / "linked-modules"
            linked_root.symlink_to(module_root, target_is_directory=True)
            dependencies = assembly.dependencies(linked_source, [linked_root])
            self.assertIn(linked_source, dependencies)
            self.assertIn(linked_root, dependencies)
            self.assertNotIn(source, dependencies)
            self.assertNotIn(module_root, dependencies)

    def test_failed_generation_preserves_last_output_and_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler, source = root / "compiler", root / "source.au"
            output, depfile = root / "output.s", root / "output.d"
            compiler.write_bytes(b"fake compiler")
            source.write_text("module test;\n")
            output.write_bytes(b"previous assembly")
            depfile.write_bytes(b"previous dependencies")
            arguments = [
                "generator",
                "--compiler",
                str(compiler),
                "--source",
                str(source),
                "--output",
                str(output),
                "--depfile",
                str(depfile),
            ]
            with (
                patch("sys.argv", arguments),
                patch.object(
                    assembly.subprocess, "run", side_effect=assembly.subprocess.CalledProcessError(1, "compiler")
                ),
            ):
                with self.assertRaises(assembly.subprocess.CalledProcessError):
                    assembly.main()
            self.assertEqual(output.read_bytes(), b"previous assembly")
            self.assertEqual(depfile.read_bytes(), b"previous dependencies")

    def test_successful_compiler_without_declared_facts_preserves_previous_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler, source = root / "compiler", root / "source.au"
            output, facts, depfile = root / "output.s", root / "output.stack.json", root / "output.d"
            for path in (compiler, source, output, facts, depfile):
                path.write_bytes(b"previous")

            def incomplete(command, **kwargs):
                Path(command[command.index("-o") + 1]).write_bytes(b"new assembly")

            with (
                patch(
                    "sys.argv",
                    [
                        "generator",
                        "--compiler",
                        str(compiler),
                        "--source",
                        str(source),
                        "--output",
                        str(output),
                        "--stack-facts",
                        str(facts),
                        "--depfile",
                        str(depfile),
                    ],
                ),
                patch.object(assembly.subprocess, "run", side_effect=incomplete),
            ):
                with self.assertRaises(FileNotFoundError):
                    assembly.main()
            for path in (output, facts, depfile):
                self.assertEqual(path.read_bytes(), b"previous")

    def test_bios_fixture_families_keep_original_payload_contracts(self):
        recipes = profiles.profiles()
        self.assertEqual(len([key for key in recipes if key.startswith("bios/")]), 20)
        self.assertEqual(len(profiles.BIOS_FIXTURE_MODES), 19)
        self.assertFalse(set(profiles.BIOS_FIXTURE_MODES) & set(profiles.FIXTURE_MODES))
        for image, baseline, count, family in (
            ("bios-fixture", "normal", 16, "FAULT"),
            ("bios-schedule-fixture", "schedule", 3, "SCHEDULE"),
        ):
            fixture = recipes["bios/" + image]
            normal = recipes["bios/" + baseline]
            for field in ("users", "language", "roots", "bridge", "cpp", "assembly", "link", "admission"):
                self.assertEqual(fixture[field], normal[field], field)
            self.assertEqual(
                fixture["image_options"], ["--bios-fixture-family", "ordinary" if family == "FAULT" else "schedule"]
            )
            self.assertEqual(normal["image_options"], [])
            self.assertIn("-DAURORA_BIOS_" + family + "_FIXTURE", fixture["flags"])
            self.assertNotIn("-DAURORA_BIOS_FIXTURE", normal["flags"])
            modes = {mode: value for mode, (target, value) in profiles.BIOS_FIXTURE_MODES.items() if target == image}
            first = min(modes.values())
            self.assertEqual(sorted(modes.values()), list(range(first, first + count)))
            for mode in modes:
                self.assertEqual(profiles.canonical_profile("bios", mode), image)
                self.assertNotIn("bios/" + mode, recipes)
            for extra in ({"KERNEL_CONSOLE": "1"}, {"KERNEL_TEST_PROGRAM_FPU": "1"}, {"KERNEL_TEST_DIVISION": "zero"}):
                with self.assertRaises(ValueError):
                    profiles.bios_profile(image, profiles.BIOS_CONTROLS[image] | extra)

    def test_plain_pin_table_selectors_keep_distinct_authority(self):
        recipes = profiles.profiles()
        for image, count in (("runtime-fixture", 15), ("runtime-pin-fixture", 4), ("runtime-table-fixture", 4)):
            users = copy.deepcopy(recipes["uefi/" + image]["users"])
            if image == "runtime-fixture":
                # Only its clean client adds the selectable hostile probes.
                self.assertEqual(users["clean"]["entry_flags"], ["--defsym", "UEFI_USER_PROBES=1"])
                users["clean"]["entry_flags"] = []
            self.assertEqual(users, recipes["uefi/runtime"]["users"])
            cases = {mode: value for mode, (target, value) in profiles.FIXTURE_MODES.items() if target == image}
            first = min(cases.values())
            self.assertEqual(sorted(cases.values()), list(range(first, first + count)))
            for mode in cases:
                self.assertNotIn("uefi/" + mode, recipes)
                self.assertEqual(profiles.canonical_profile("uefi", mode), image)
        pin = recipes["uefi/runtime-pin-fixture"]["flags"]
        table = recipes["uefi/runtime-table-fixture"]["flags"]
        self.assertIn("-DAURORA_PIN_LEDGER_TESTING=1", pin)
        self.assertNotIn("-DAURORA_UEFI_TABLES", pin)
        self.assertNotIn("-DAURORA_PIN_LEDGER_TESTING=1", table)
        self.assertIn("-DAURORA_DORMANT_TABLE_TESTING=1", table)
        self.assertIn("tables", recipes["uefi/runtime-table-fixture"]["checks"])
        self.assertNotIn("-DAURORA_RUNTIME_FIXTURE", recipes["uefi/runtime"]["flags"])

    def test_program_snapshot_fixtures_preserve_original_payloads(self):
        recipes = profiles.profiles()
        # Each family's selectors stay one contiguous range: seven original modes
        # plus the hostile-client cases folded in from their own images.
        for family, baseline, count in (("program", "program-console", 11), ("snapshot", "snapshot", 10)):
            fixture = recipes["uefi/" + family + "-fixture"]
            normal = recipes["uefi/" + baseline]
            for field in ("users", "language", "roots", "bridge", "cpp", "assembly", "link", "image_options"):
                self.assertEqual(fixture[field], normal[field], field)
            self.assertNotIn("-DAURORA_RUNTIME_FIXTURE", normal["flags"])
            self.assertEqual(
                set(fixture["flags"]) - set(normal["flags"]),
                {"-DAURORA_RUNTIME_FIXTURE", "-DAURORA_" + family.upper() + "_FIXTURE"},
            )
            cases = {
                mode: value for mode, (image, value) in profiles.FIXTURE_MODES.items() if image == family + "-fixture"
            }
            first = min(cases.values())
            self.assertEqual(sorted(cases.values()), list(range(first, first + count)))
            for mode in cases:
                self.assertNotIn("uefi/" + mode, recipes)
                self.assertEqual(profiles.canonical_profile("uefi", mode), family + "-fixture")

    def test_named_profiles_and_hardware_aliases_keep_one_recipe(self):
        recipes = profiles.profiles()
        for platform, names in (
            ("bios", profiles.BIOS_CONTROLS),
            ("uefi", [mode for _, variants in profiles.UEFI_FAMILIES for mode in variants]),
        ):
            for name in names:
                self.assertEqual(profiles.select(platform, {}, name), name)
                self.assertIn(platform + "/" + profiles.canonical_profile(platform, name), recipes)
        for aliases, platform in ((profiles.BIOS_ALIASES, "bios"), (profiles.UEFI_ALIASES, "uefi")):
            for alias, canonical in aliases.items():
                self.assertNotIn(platform + "/" + alias, recipes)
                self.assertEqual(profiles.canonical_profile(platform, alias), canonical)
        for platform in ("bios", "uefi"):
            for env in ({"KERNEL_TEST_UNKNOWN": "1"}, {"KERNEL_TEST_NX": "1", "KERNEL_TEST_WP": "1"}):
                with self.assertRaises(ValueError):
                    profiles.select(platform, env)
        with self.assertRaises(ValueError):
            profiles.select("uefi", {"UEFI_MODE": "console"}, "normal")
        with self.assertRaises(ValueError):
            profiles.select("bios", {"KERNEL_CONSOLE": "1"}, "normal")

    def test_pci_corrupt_inputs_move_to_hosted_policy_without_guest_aliases(self):
        recipes = profiles.profiles()
        for mode in ("pci-reserved", "pci-overlap", "pci-range"):
            self.assertNotIn("uefi/" + mode, recipes)
            self.assertNotIn(mode, profiles.UEFI_ALIASES)
            self.assertNotIn(mode, clock.ORIGINAL_UEFI_MODES)
            with self.assertRaises(ValueError):
                profiles.select("uefi", {}, mode)
        # Preserve an actual early failure witness and both hardware fault gates.
        for mode in ("pci-checksum", "pci-write", "pci-revoked", "pci-cycle"):
            self.assertNotIn("uefi/" + mode, recipes)
            self.assertEqual(profiles.canonical_profile("uefi", mode), "pci-fixture")
            self.assertIn(mode, clock.ORIGINAL_UEFI_MODES)
        self.assertEqual(
            {mode: value for mode, (image, value) in profiles.FIXTURE_MODES.items() if image == "pci-fixture"},
            {"pci-checksum": 97, "pci-cycle": 98, "pci-write": 99, "pci-revoked": 100},
        )
        self.assertEqual(
            recipes["uefi/pci-fixture"]["flags"],
            [
                "-DAURORA_UEFI_ACPI",
                "-DAURORA_UEFI_PCI",
                "-DAURORA_PCI_FIXTURE",
                "-DAURORA_RUNTIME_IMAGE_POLICY=one_page",
            ],
        )
        self.assertEqual(
            recipes["uefi/pci"]["flags"],
            ["-DAURORA_UEFI_ACPI", "-DAURORA_UEFI_PCI", "-DAURORA_RUNTIME_IMAGE_POLICY=one_page"],
        )

    def test_fixture_selector_is_sent_after_guest_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "selector.log"
            command = [
                sys.executable,
                "-c",
                (
                    "import sys; print('AURORA_FIXTURE_READY', flush=True); "
                    "print('selected=' + str(sys.stdin.buffer.read(1)[0]), flush=True)"
                ),
            ]
            self.assertEqual(transport.run_logged(command, log, startup_byte=17, timeout=5), 0)
            self.assertIn(b"selected=17", log.read_bytes())
            with self.assertRaisesRegex(ValueError, "without requesting"):
                transport.run_logged(
                    [sys.executable, "-c", "pass"], Path(directory) / "missing.log", startup_byte=17, timeout=5
                )

    def test_multipage_allowance_is_exact_and_bios_stays_one_page(self):
        for name, recipe in profiles.profiles().items():
            enabled = name == "uefi/runtime-multipage"
            self.assertEqual("--multipage" in recipe["image_options"], enabled)
            self.assertEqual("-DAURORA_RUNTIME_MULTIPAGE" in recipe["flags"], enabled)
            for index, user in enumerate(recipe["users"].values()):
                if recipe["platform"] == "uefi":
                    owned_text = (
                        name.startswith(("uefi/runtime-owned-text", "uefi/runtime-console-region")) and index == 0
                    )
                    blocking_call = "-DAURORA_BLOCKING_CALL" in recipe["flags"] and index == 0
                    ram_client = (
                        name
                        in (
                            "uefi/user-ram-file",
                            "uefi/user-ram-file-fixture",
                            "uefi/ram-scratchpad-console",
                            "uefi/ram-scratchpad-console-fixture",
                        )
                        and index == 0
                    )
                    self.assertEqual(
                        user["max_pages"], 3 if enabled or owned_text else 2 if blocking_call or ram_client else 1
                    )
                    self.assertEqual(user["base"], 0x10000000000 + index * 16384)
                else:
                    self.assertNotIn("max_pages", user)
                    self.assertEqual(user["base"], 0x1B0000 + index * 4096)
        self.assertTrue(image.image_options(["--multipage"])["require_multipage"])
        for options in (["--multipage", "--ipc-policy"], ["--owned-bytes", "--multipage"]):
            with self.assertRaises(ValueError):
                image.image_options(options)

    def test_acpi_policy_migration_and_early_loader_boundary(self):
        recipes = profiles.profiles()
        for mode in ("acpi-bad-entry", "acpi-duplicate", "acpi-changed-header"):
            self.assertNotIn("uefi/" + mode, recipes)
            self.assertNotIn(mode, profiles.UEFI_ALIASES)
            self.assertNotIn(mode, clock.ORIGINAL_UEFI_MODES)
        for mode in ("acpi-disabled", "acpi-checksum", "acpi-bad-source", "acpi-write", "acpi-revoked"):
            self.assertEqual(profiles.canonical_profile("uefi", mode), "acpi-fixture")
        self.assertIn("uefi/acpi-duplicate-root", recipes)
        self.assertNotIn("acpi-duplicate-root", profiles.FIXTURE_MODES)
        self.assertNotIn("-DAURORA_ACPI_FIXTURE", recipes["uefi/acpi"]["flags"])

    def test_ivrs_hosted_policy_and_shared_real_fault_profiles(self):
        recipes = profiles.profiles()
        for mode in ("ivrs-pair", "ivrs-alias", "ivrs-reserved", "ivrs-scope", "ivrs-capability", "ivrs-range"):
            self.assertNotIn("uefi/" + mode, recipes)
            self.assertNotIn(mode, profiles.UEFI_ALIASES)
            self.assertNotIn(mode, clock.ORIGINAL_IVRS_MODES)
        # Every live IVRS case boots ivrs-fixture; ivrs-missing rejects before its selector.
        self.assertEqual(profiles.canonical_profile("uefi", "ivrs-missing"), "ivrs-fixture")
        self.assertNotIn("ivrs-missing", profiles.FIXTURE_MODES)
        cases = {mode: value for mode, (image, value) in profiles.FIXTURE_MODES.items() if image == "ivrs-fixture"}
        self.assertEqual(set(cases), {"ivrs-write", "ivrs-revoked", "ivrs-default", "ivrs-read"})
        self.assertEqual(sorted(cases.values()), list(range(min(cases.values()), min(cases.values()) + 4)))
        self.assertEqual([name for name in recipes if "-DAURORA_UEFI_IVRS" in recipes[name]["flags"]], ["uefi/ivrs-fixture"])

    def test_copied_policy_negatives_are_hosted_not_boot_profiles(self):
        recipes = profiles.profiles()
        for mode in (
            "ipc-policy-request-input",
            "ipc-policy-request-output",
            "ipc-policy-cancel-input",
            "ipc-policy-cancel-output",
            "budget-policy-zero",
            "budget-policy-counts",
            "budget-policy-wide",
            "budget-policy-output",
            "dispatch-policy-cursor",
            "dispatch-policy-mask",
            "dispatch-policy-output",
            "user-disposal-input",
            "user-disposal-output",
        ):
            self.assertNotIn("uefi/" + mode, recipes)
            self.assertNotIn(mode, profiles.UEFI_ALIASES)
            self.assertNotIn(mode, profiles.FIXTURE_MODES)
            self.assertNotIn(mode, clock.ORIGINAL_UEFI_MODES)
        # The early no-APIC rejection is a budget-fixture case, not its own image.
        self.assertNotIn("uefi/budget-noapic", recipes)
        self.assertEqual(profiles.canonical_profile("uefi", "budget-noapic"), "budget-fixture")

    def test_ipc_same_payload_fixtures_keep_normal_image_selector_free(self):
        recipes = profiles.profiles()
        names = ("fault", "cancel", "stale", "root", "kernel-trap", "duplicate", "late", "exhausted")
        names += ("owner", "version", "phase", "transaction", "site", "unknown")
        values = [profiles.FIXTURE_MODES["ipc-" + name] for name in names]
        self.assertTrue(all(image == "ipc-fixture" for image, _ in values))
        self.assertEqual(sorted(v for _, v in values), list(range(values[0][1], values[0][1] + len(names))))
        for name in names[8:]:
            self.assertNotIn("uefi/ipc-" + name, recipes)
        self.assertEqual(recipes["uefi/ipc-fixture"]["users"], recipes["uefi/ipc"]["users"])
        self.assertNotIn("-DAURORA_RUNTIME_FIXTURE", recipes["uefi/ipc"]["flags"])
        self.assertNotIn("-DAURORA_IPC_FIXTURE", recipes["uefi/ipc"]["flags"])

    def test_budget_family_preserves_payload_and_page_contract(self):
        recipes = profiles.profiles()
        names = ("fault", "discovery", "cache", "alias", "pending", "forged", "root", "epoch")
        names += ("noapic", "mmio", "softint", "fpu", "context")
        values = [profiles.FIXTURE_MODES["budget-" + name] for name in names]
        self.assertTrue(all(image == "budget-fixture" for image, _ in values))
        self.assertEqual(sorted(v for _, v in values), list(range(values[0][1], values[0][1] + len(names))))
        for name in names:
            self.assertNotIn("uefi/budget-" + name, recipes)
        users = copy.deepcopy(recipes["uefi/budget-fixture"]["users"])
        # Only the fixture service adds the selectable probes, and only the
        # fixture launcher loads their selector word.
        self.assertEqual(users["bounds"]["entry_flags"], ["--defsym", "IPC_PROBES=1"])
        users["bounds"]["entry_flags"] = []
        self.assertEqual(users, recipes["uefi/budget"]["users"])
        entry = {name: recipes["uefi/" + name]["assembly"]["runtime-entry"]["flags"] for name in ("budget", "budget-fixture")}
        self.assertEqual(entry["budget-fixture"], entry["budget"] + ["--defsym", "AURORA_IPC_PROBES=1"])
        self.assertNotIn("-DAURORA_RUNTIME_FIXTURE", recipes["uefi/budget"]["flags"])
        self.assertEqual(profiles.canonical_profile("uefi", "budget-smp"), "budget")

    def test_ram_file_roles_are_exact(self):
        recipes = profiles.profiles()
        ram_profiles = {"uefi/user-ram-file", "uefi/user-ram-file-fixture"}
        scratchpad_profiles = {"uefi/ram-scratchpad-console", "uefi/ram-scratchpad-console-fixture"}
        self.assertEqual({name for name in recipes if "user-ram-file" in name}, ram_profiles)
        for name, recipe in recipes.items():
            ram_file = name in ram_profiles | scratchpad_profiles
            self.assertEqual("-DAURORA_RAM_FILE" in recipe["flags"], ram_file)
            self.assertEqual("--ram-file" in recipe["user_options"], ram_file)
            if name not in ram_profiles:
                continue
            self.assertEqual(recipe["checks"], ["ram-file"])
            self.assertEqual(recipe["user_options"], ["--service-budget", "--user-budget", "--ram-file"])
            self.assertNotIn("-DAURORA_BLOCKING_CALL", recipe["flags"])
            self.assertEqual(tuple(recipe["users"]), ("clean", "bounds"))
            for role, pages, define, source in (
                ("clean", 2, "CALL_CLIENT=1", "ram-file-client"),
                (
                    "bounds",
                    1,
                    "SERVE_SERVICE=1",
                    "ram-file-service-fixture" if name.endswith("-fixture") else "ram-file-service",
                ),
            ):
                user = recipe["users"][role]
                self.assertEqual(user["max_pages"], pages)
                self.assertEqual(user["entry_flags"], ["--defsym", define])
                self.assertEqual(user["source"], "tests/kernel-programs/" + source + ".au")
                self.assertEqual(user["entry"], "kernel/uefi/ipc-user-entry.S")
                self.assertTrue(user["combined"])

    def test_scratchpad_profiles_are_exact_and_share_production_caller(self):
        recipes = profiles.profiles()
        names = {"uefi/ram-scratchpad-console", "uefi/ram-scratchpad-console-fixture"}
        self.assertEqual({name for name in recipes if "scratchpad" in name}, names)
        for name, recipe in recipes.items():
            scratchpad = name in names
            fixture = name == "uefi/ram-scratchpad-console-fixture"
            self.assertEqual("-DAURORA_RAM_SCRATCHPAD_CONSOLE" in recipe["flags"], scratchpad)
            self.assertEqual("-DAURORA_SCRATCHPAD_FIXTURE" in recipe["flags"], fixture)
            self.assertEqual("--ram-scratchpad-console" in recipe["user_options"], scratchpad)
            self.assertEqual("--ram-scratchpad-fixture" in recipe["user_options"], fixture)
            self.assertEqual("ram-scratchpad" in recipe["checks"], scratchpad)
            if not scratchpad:
                continue
            self.assertEqual(profiles.canonical_profile("uefi", recipe["mode"]), recipe["mode"])
            self.assertEqual(
                recipe["flags"],
                [
                    "-DAURORA_UEFI_ACPI",
                    "-DAURORA_UEFI_PCI",
                    "-DAURORA_UEFI_RUNTIME",
                    "-DAURORA_UEFI_IPC",
                    "-DAURORA_UEFI_SERVICE_BUDGET",
                    "-DAURORA_UEFI_USER_BUDGET",
                    "-DAURORA_RAM_FILE",
                    "-DAURORA_RAM_SCRATCHPAD_CONSOLE",
                ]
                + (["-DAURORA_SCRATCHPAD_FIXTURE"] if fixture else [])
                + ["-DAURORA_RUNTIME_IMAGE_POLICY=call"],
            )
            self.assertEqual(recipe["checks"], ["ram-scratchpad"])
            self.assertEqual(recipe["admission"], "")
            self.assertEqual(recipe["language"], "examples/kernel-ram-scratchpad-console.au")
            self.assertEqual(recipe["bridge"], "kernel/uefi/ram-scratchpad-console-entry.S")
            self.assertEqual(recipe["image_options"], ["--ipc-policy"])
            self.assertEqual(recipe["user_kind"], "ipc")
            self.assertEqual(recipe["user_mode"], "normal")
            self.assertEqual(
                recipe["user_options"],
                ["--service-budget", "--user-budget", "--ram-file", "--ram-scratchpad-console"]
                + (["--ram-scratchpad-fixture"] if fixture else []),
            )
            self.assertEqual(tuple(recipe["users"]), ("clean", "bounds"))
            self.assertEqual(
                recipe["users"]["clean"],
                dict(
                    source="examples/kernel-ram-scratchpad-client.au",
                    roots=["library"],
                    base=0x10000000000,
                    entry="kernel/uefi/ram-scratchpad-client-entry.S",
                    entry_flags=[],
                    combined=True,
                    max_pages=2,
                ),
            )
            self.assertEqual(
                recipe["users"]["bounds"],
                dict(
                    source="tests/kernel-programs/"
                    + ("scratchpad-service-fixture.au" if fixture else "ram-file-service.au"),
                    roots=["library"],
                    base=0x10000004000,
                    entry="kernel/uefi/ipc-user-entry.S",
                    entry_flags=["--defsym", "SERVE_SERVICE=1"],
                    combined=True,
                    max_pages=1,
                ),
            )

    def test_scratchpad_linked_controls_retain_full_boot_and_disabled_gates(self):
        recipe = (ROOT / "tests/native/meson.build").read_text()
        inventory = (ROOT / "tests/native/kernel-image-tests.txt").read_text().splitlines()
        self.assertEqual(len(inventory), 12)
        self.assertEqual(len(set(inventory)), 12)
        for mode in ("ram-scratchpad-console", "ram-scratchpad-console-fixture"):
            self.assertIn("native-uefi-" + mode + "-linked-image", inventory)
        begin = recipe.index("  foreach mode : ['ram-scratchpad-console', 'ram-scratchpad-console-fixture']")
        linked = recipe[begin : recipe.index("  endforeach", begin)]
        self.assertIn("test('native-uefi-' + mode + '-linked-image', python,", linked)
        self.assertIn(
            "args: ['-B', '-O', files('../../tests/kernel-uefi-user-phases-image.py'), '--ram-scratchpad-build-dir',",
            linked,
        )
        self.assertIn("meson.project_build_root() / 'kernel-images/uefi' / mode", linked)
        self.assertIn("mode == 'ram-scratchpad-console-fixture' ? ['--ram-scratchpad-fixture'] : []", linked)
        self.assertIn("depends: kernel_profile_images['uefi/' + mode]", linked)
        self.assertIn("suite: ['full', 'slow', 'integration', 'boot']", linked)
        disabled = recipe[recipe.index("  foreach image_name : fs.read('kernel-image-tests.txt')") :]
        self.assertIn("test(image_name, python,", disabled)
        self.assertIn('raise SystemExit("Kernel images disabled:', disabled)
        self.assertIn("suite: ['full', 'slow', 'integration', 'boot']", disabled)

    def test_depfile_escaping(self):
        self.assertEqual(assembly.escaped("a b#c$d:e\\f"), "a\\ b\\#c$$d\\:e\\\\f")
        for path in ["line\nfeed", "carriage\rreturn"]:
            with self.assertRaises(ValueError):
                assembly.escaped(path)

    def test_sidecars_keep_same_compile_and_full_source_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "kernel/uefi/payload.cpp"
            source.parent.mkdir(parents=True)
            source.write_text("// fixture\n")
            native = root / "native/kernel_uefi_payload.cpp.o"
            native.parent.mkdir()
            output = root / "objects/payload.o"
            output.parent.mkdir()
            for suffix, data in [
                (".o", b"object"),
                (".su", b"kernel/uefi/payload.cpp:12:3:full signature\t8\tstatic\n"),
                (".ci", b"full source and exact symbol\n"),
            ]:
                native.with_suffix(suffix).write_bytes(data)
            objects.export_object(source, native, output, root, True)
            for suffix in [".o", ".su", ".ci"]:
                self.assertEqual(output.with_suffix(suffix).read_bytes(), native.with_suffix(suffix).read_bytes())
            mapping = json.loads(output.with_suffix(".source.json").read_text())
            self.assertEqual(mapping["source"], str(source))
            self.assertEqual(mapping["native_object"], str(native))
            self.assertEqual(mapping["compile_directory"], str(root))
            self.assertEqual(mapping["sidecars"]["ci"], str(native.with_suffix(".ci")))
            # A same-basename foreign sidecar must not replace a missing one.
            native.with_suffix(".ci").unlink()
            (root / "payload.ci").write_text("wrong compilation")
            native.write_bytes(b"new unadmitted object")
            with self.assertRaises(FileNotFoundError):
                objects.export_object(source, native, output, root, True)
            self.assertEqual(output.read_bytes(), b"object")

    def test_bios_does_not_require_uefi_callgraph_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, native, output = root / "main.cpp", root / "main.cpp.o", root / "kernel-main.o"
            source.write_text("// fixture")
            native.write_bytes(b"object")
            native.with_suffix(".su").write_bytes(b"stack")
            objects.export_object(source, native, output, root)
            self.assertEqual(output.read_bytes(), b"object")
            self.assertFalse(output.with_suffix(".ci").exists())

    def test_independent_clock_binds_explicit_image_directory(self):
        esp = "/configured/kernel-images/uefi/normal/esp"
        expected = clock.expected_uefi_argv("normal", "/qemu", "/firmware", "", esp=esp)
        receipt = clock.uefi_clock_receipt("normal", "tcg-original-clock", expected, "/qemu", "/firmware", "", esp=esp)
        self.assertIn("format=raw,file=fat:ro:" + esp + ",snapshot=on", receipt["argv"])
        with self.assertRaises(ValueError):
            clock.uefi_clock_receipt(
                "normal", "tcg-original-clock", expected, "/qemu", "/firmware", "", esp="/other/esp"
            )


class SmokeRunOnlyFixture(unittest.TestCase):
    """Real wrappers and clock checks; recording substitutes never boot a guest."""

    def children(self):
        # This fixture process is single-threaded and owns no other child work.
        children = []
        for path in Path("/proc").iterdir():
            if not path.name.isdecimal():
                continue
            try:
                raw = (path / "stat").read_text()
            except (FileNotFoundError, ProcessLookupError):
                continue
            fields = raw[raw.rfind(")") + 2 :].split()
            if int(fields[1]) == os.getpid():
                children.append(int(path.name))
        return tuple(children)

    def reap_wrapper_children(self):
        # A transport can own a separate guest session. Adoption, rather than
        # an outer killpg, keeps that guest owned if its supervisor exits first.
        for signum in (signal.SIGTERM, signal.SIGKILL):
            deadline, signaled = time.monotonic() + 2, {}
            while children := self.children():
                for pid in children:
                    # WNOWAIT verifies direct-child ownership and keeps the PID
                    # unreaped until after any signal, preventing PID reuse.
                    os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if pid not in signaled:
                        os.kill(pid, signum)
                        signaled[pid] = time.monotonic() + 2
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        del signaled[pid]
                    elif signum == signal.SIGKILL and time.monotonic() >= signaled[pid]:
                        raise transport.ChildNotReaped("Smoke wrapper descendants have not settled")
                # TERM has a shared grace period. KILL settling is per owned
                # child: an orphan adopted after killing its supervisor must
                # get the same guard from its own signal, not the supervisor's.
                if signum == signal.SIGTERM and time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            if not self.children():
                return
        raise transport.ChildNotReaped("Smoke wrapper descendants have not settled")

    @contextmanager
    def owned_wrapper(self):
        self.assertEqual(self.children(), (), "Smoke fixture already has child work")
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        # Linux PR_GET_CHILD_SUBREAPER / PR_SET_CHILD_SUBREAPER, scoped to this
        # serial fixture only. Production transport and its deadlines are unchanged.
        if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) or libc.prctl(36, 1, 0, 0, 0):
            raise OSError(ctypes.get_errno(), "Cannot own smoke wrapper descendants")
        try:
            yield
        finally:
            primary = sys.exc_info()[1]
            with transport.defer_interrupts():
                leaked = bool(self.children())
                try:
                    self.reap_wrapper_children()
                except BaseException as cleanup_error:
                    raise transport.ChildNotReaped("Smoke wrapper cleanup failed: " + str(cleanup_error)) from primary
                if libc.prctl(36, previous.value, 0, 0, 0):
                    raise transport.ChildNotReaped("Cannot restore smoke fixture child ownership") from primary
                if leaked and primary is None:
                    raise transport.ChildNotReaped("Successful smoke wrapper left descendants")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aurora-smoke-routing-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        for name in (
            "kernel-smoke.sh",
            "kernel-uefi-smoke.sh",
            "kernel_profiles.py",
            "kernel_layout.py",
            "qemu_transport.py",
            "kernel_emulator_clock.py",
            "uefi-firmware.sh",
        ):
            shutil.copy2(ROOT / "scripts" / name, self.repo / "scripts" / name)
        for relative in (
            "kernel/bootstrap-layout-values.inc",
            "kernel/uefi/image-page-policies.inc",
            "kernel/uefi/runtime-fixtures.inc",
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.calls = self.root / "calls"
        self.qemu = self.root / "qemu"
        self.qemu.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\nfrom pathlib import Path\n"
            "with open(os.environ['CALLS'], 'a') as output:\n"
            "    output.write(json.dumps(['qemu', *sys.argv[1:]]) + '\\n')\n"
            "for arg in sys.argv[1:]:\n"
            "    if 'file=fat:ro:' in arg: assert Path(arg.split('file=fat:ro:')[1].split(',')[0]).is_dir()\n"
            "    elif arg.startswith('file='): assert Path(arg[5:].split(',')[0]).is_file()\n"
            "print('synthetic serial')\nraise SystemExit(33)\n"
        )
        self.qemu.chmod(0o755)
        firmware = self.root / "OVMF.fd"
        firmware.write_bytes(b"recording firmware")
        self.env = dict(
            PATH=os.environ["PATH"],
            HOME=str(self.root),
            LC_ALL="C",
            PYTHONDONTWRITEBYTECODE="1",
            QEMU=str(self.qemu),
            OVMF=str(firmware),
            CALLS=str(self.calls),
        )
        for platform in ("bios", "uefi"):
            script = "kernel-build.sh" if platform == "bios" else "kernel-uefi-build.sh"
            build = self.repo / "scripts" / script
            build.write_text('#!/usr/bin/env bash\necho \'["build"]\' >> "$CALLS"\nprintf "%s\\n" "$BUILT_IMAGE"\n')
            build.chmod(0o755)
        for name in (
            "kernel-smoke",
            "kernel-schedule-smoke",
            "kernel-uefi-smoke",
            "kernel-uefi-budget-smoke",
            "kernel-uefi-dispatch-smoke",
            "kernel-uefi-user-phases-smoke",
            "kernel-snapshot-smoke",
            "kernel-uefi-runtime-smoke",
            "kernel-acpi-smoke",
        ):
            (self.repo / "tests" / (name + ".py")).write_text(
                "import json, os, sys\nfrom pathlib import Path\n"
                "assert sys.argv[1] == '33'\n"
                "assert Path(sys.argv[2]).read_text() == 'synthetic serial\\n'\n"
                "if len(sys.argv) == 5: json.loads(Path(sys.argv[4]).read_text())\n"
                "with open(os.environ['CALLS'], 'a') as output:\n"
                "    output.write(json.dumps(['oracle', *sys.argv]) + '\\n')\n"
            )

    def native(self, platform, mode):
        image = (
            self.root
            / "native/kernel-images"
            / platform
            / profiles.canonical_profile(platform, mode.removeprefix("--"))
        )
        image.mkdir(parents=True, exist_ok=True)
        (image / "esp").mkdir(exist_ok=True)
        for name in ("aurora.img", "user-metadata.json", "user-images.json", "service-timer-metadata.json"):
            (image / name).write_text('{"fixture":"' + name + '"}\n')
        return image

    def invoke(self, platform, *arguments, image=None, success=True):
        script = "kernel-smoke.sh" if platform == "bios" else "kernel-uefi-smoke.sh"
        with self.owned_wrapper():
            try:
                result = subprocess.run(
                    ["bash", str(self.repo / "scripts" / script), *map(str, arguments)],
                    cwd=self.root,
                    env=self.env | {"BUILT_IMAGE": str(image)},
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=5,
                )
            except subprocess.TimeoutExpired as error:
                output = error.stdout or b""
                text = output.decode(errors="replace") if isinstance(output, bytes) else output
                error.add_note("Captured wrapper output:\n" + text)
                raise
        self.assertEqual(result.returncode == 0, success, result.stdout)
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []


class WrapperTimeoutCleanup(SmokeRunOnlyFixture):
    def test_late_adopted_guest_has_its_own_kill_settle_guard(self):
        elapsed, killed, alive = [0.0], {}, {101, 102}

        def children():
            return (101,) if 101 in alive else ((102,) if 102 in alive else ())

        def kill(pid, signum):
            if signum == signal.SIGKILL:
                killed[pid] = elapsed[0]

        def waitpid(pid, options):
            if pid in killed and elapsed[0] - killed[pid] >= 1.5:
                alive.remove(pid)
                return pid, 0
            return 0, 0

        def sleep(seconds):
            elapsed[0] += seconds
            self.assertLess(elapsed[0], 10, "Cleanup did not honor its bounded guards")

        with (
            patch.object(self, "children", side_effect=children),
            patch.object(os, "waitid", return_value=None),
            patch.object(os, "kill", side_effect=kill),
            patch.object(os, "waitpid", side_effect=waitpid),
            patch.object(time, "monotonic", side_effect=lambda: elapsed[0]),
            patch.object(time, "sleep", side_effect=sleep),
        ):
            self.reap_wrapper_children()
        self.assertEqual(alive, set())
        self.assertEqual(set(killed), {101, 102})
        self.assertLess(elapsed[0], 5.1)

    def test_killed_child_that_does_not_settle_still_fails(self):
        elapsed = [0.0]

        def sleep(seconds):
            elapsed[0] += seconds
            self.assertLess(elapsed[0], 10, "Cleanup did not honor its bounded guards")

        with (
            patch.object(self, "children", return_value=(101,)),
            patch.object(os, "waitid", return_value=None),
            patch.object(os, "kill"),
            patch.object(os, "waitpid", return_value=(0, 0)),
            patch.object(time, "monotonic", side_effect=lambda: elapsed[0]),
            patch.object(time, "sleep", side_effect=sleep),
            self.assertRaisesRegex(transport.ChildNotReaped, "not settled"),
        ):
            self.reap_wrapper_children()
        self.assertLess(elapsed[0], 4.1)

    def test_timeout_reaps_term_ignoring_guest_in_separate_session(self):
        ready, escaped = self.root / "ready.json", self.root / "escaped-timeout"
        self.qemu.write_text(
            f"#!{sys.executable}\n"
            "import json, os, signal, time\nfrom pathlib import Path\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "record = dict(guest=os.getpid(), transport=os.getppid(), session=os.getsid(0))\n"
            f"Path({str(ready)!r}).write_text(json.dumps(record))\n"
            "time.sleep(20)\n"
            f"Path({str(escaped)!r}).write_text('escaped timeout')\n"
        )
        wrapper = self.repo / "scripts/kernel-uefi-smoke.sh"
        wrapper.write_text(
            wrapper.read_text().replace("set -euo pipefail\n", "set -euo pipefail\necho timeout-diagnostic >&2\n", 1)
        )
        image = self.native("uefi", "snapshot")
        with self.assertRaises(subprocess.TimeoutExpired) as failure:
            self.invoke("uefi", "--run-only", image, "--output-dir", self.root / "timed-out", "snapshot")
        self.assertEqual(failure.exception.timeout, 5)
        self.assertIn(b"timeout-diagnostic", failure.exception.stdout)
        self.assertIn("timeout-diagnostic", "\n".join(failure.exception.__notes__))
        observed = json.loads(ready.read_text())
        self.assertEqual(observed["guest"], observed["session"])
        self.assertFalse(escaped.exists())
        self.assertEqual(self.children(), ())
        for name in ("guest", "transport"):
            self.assertFalse(Path("/proc", str(observed[name])).exists(), name + " survived wrapper timeout")


class SmokeRunOnlyRouting(SmokeRunOnlyFixture):
    def test_run_only_uses_canonical_images_and_isolates_all_evidence(self):
        for platform, mode in (
            ("bios", "normal"),
            ("bios", "--schedule-smp"),
            ("uefi", "normal"),
            ("uefi", "budget-smp"),
            ("uefi", "dispatch"),
            ("uefi", "user-phases"),
            ("uefi", "snapshot"),
            ("uefi", "runtime"),
            ("uefi", "acpi-two"),
        ):
            with self.subTest(platform=platform, mode=mode):
                image = self.native(platform, mode)
                before = {
                    p.relative_to(image): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in image.rglob("*")
                    if p.is_file()
                }
                output = self.root / (platform + mode)
                calls = self.invoke(platform, "--run-only", image, "--output-dir", output, mode)
                self.assertEqual([call[0] for call in calls], ["qemu", "oracle"])
                boot = (
                    "file=" + str(image / "aurora.img") + ",format=raw,if=ide,snapshot=on"
                    if platform == "bios"
                    else "format=raw,file=fat:ro:" + str(image / "esp") + ",snapshot=on"
                )
                self.assertIn(boot, calls[0])
                self.assertEqual(Path(calls[1][3]).parent, output)
                if platform == "uefi":
                    self.assertTrue((output / (mode + ".clock.json")).is_file())
                if len(calls[1]) == 6:
                    self.assertEqual(Path(calls[1][5]).parent, output)
                after = {
                    p.relative_to(image): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in image.rglob("*")
                    if p.is_file()
                }
                self.assertEqual(after, before)
                self.calls.unlink()

    def test_default_still_builds_and_clock_plan_and_shared_normal_remain_supported(self):
        for platform in ("bios", "uefi"):
            image = self.native(platform, "normal")
            calls = self.invoke(platform, "normal", image=image)
            self.assertEqual([call[0] for call in calls], ["build", "qemu", "oracle"])
            if platform == "bios":
                self.assertIn("file=" + str(image / "aurora.img") + ",format=raw,if=ide", calls[1])
            self.calls.unlink()
        self.assertEqual(self.invoke("uefi", "--clock-plan", "--shared-normal", "normal"), [])
        calls = self.invoke(
            "uefi", "--shared-normal", "--run-only", image, "--output-dir", self.root / "shared", "normal"
        )
        self.assertEqual([call[0] for call in calls], ["qemu", "oracle"])

    def test_invalid_run_only_inputs_reject_before_build_or_guest(self):
        for platform in ("bios", "uefi"):
            image = self.native(platform, "normal")
            alias = self.root / (platform + "-linked")
            alias.symlink_to(image, target_is_directory=True)
            output = self.root / (platform + "-fresh")
            cases = [
                ("--run-only", image),
                ("--output-dir", output, "normal"),
                ("--run-only", image, "--output-dir", output, "normal", "extra"),
                ("--run-only", image, "--output-dir", output, "unknown"),
                ("--run-only", image, "--output-dir", output, "--schedule" if platform == "bios" else "budget"),
                ("--run-only", alias, "--output-dir", output, "normal"),
                ("--run-only", image.relative_to(self.root), "--output-dir", output, "normal"),
                ("--run-only", image, "--output-dir", self.root, "normal"),
                ("--run-only", image, "--output-dir", image / "evidence", "normal"),
                ("--run-only", image, "--output-dir", "relative", "normal"),
            ]
            if platform == "uefi":
                cases += [
                    ("--clock-plan", "--run-only", image, "--output-dir", output, "normal"),
                    ("--shared-normal", "--run-only", image, "--output-dir", output, "budget"),
                ]
            for arguments in cases:
                with self.subTest(platform=platform, arguments=arguments):
                    self.assertEqual(self.invoke(platform, *arguments, success=False), [])
                    self.assertFalse(output.exists())

    def test_missing_metadata_and_reused_output_cannot_report_success(self):
        for platform, mode, metadata in (
            ("bios", "normal", "user-metadata.json"),
            ("uefi", "budget", "service-timer-metadata.json"),
        ):
            image = self.native(platform, mode)
            (image / metadata).unlink()
            output = self.root / (platform + "-output")
            calls = self.invoke(platform, "--run-only", image, "--output-dir", output, mode, success=False)
            self.assertNotIn("build", [call[0] for call in calls])
            self.assertNotIn("oracle", [call[0] for call in calls])
            if self.calls.exists():
                self.calls.unlink()
            self.assertEqual(
                self.invoke(platform, "--run-only", image, "--output-dir", output, mode, success=False), []
            )

    def test_missing_boot_input_cannot_report_success(self):
        for platform in ("bios", "uefi"):
            image = self.native(platform, "normal")
            if platform == "bios":
                (image / "aurora.img").unlink()
            else:
                (image / "esp").rmdir()
            calls = self.invoke(
                platform, "--run-only", image, "--output-dir", self.root / platform, "normal", success=False
            )
            self.assertEqual([call[0] for call in calls], ["qemu"])
            self.calls.unlink()


if __name__ == "__main__":
    unittest.main()

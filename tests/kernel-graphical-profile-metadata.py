#!/usr/bin/env python3
"""Pure metadata controls: no tool, compiler, image, guest or device execution.

Registration and source inventories do not establish runtime qualification.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def literal(relative, name):
    tree = ast.parse((ROOT / relative).read_text())
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(values) != 1:
        raise ValueError("Missing or ambiguous literal: " + name)
    return ast.literal_eval(values[0])


class ProfileMetadata(unittest.TestCase):
    def test_exact_modes_remain_separate(self):
        combined = literal("scripts/kernel_graphical_console_admission.py", "MODES")
        self.assertEqual(combined, ("graphical-console", "graphical-console-capture"))
        for checker in ("kernel_console_service_admission.py", "kernel_framebuffer_admission.py",
                        "kernel_program_console_admission.py"):
            self.assertTrue(set(combined).isdisjoint(literal("scripts/" + checker, "MODES")))
        build = (ROOT / "scripts/kernel-uefi-build.sh").read_text()
        self.assertIn(" graphical-console|graphical-console-capture)", build)
        self.assertNotIn("graphical-console|framebuffer", build)

    def test_no_legacy_clock_admission_or_inherited_receipt(self):
        clock = load("graphical_metadata_clock", "scripts/kernel_emulator_clock.py")
        self.assertEqual(len(clock.MODE_CLOCKS), 184)
        self.assertEqual(sum(value == clock.FIXED0 for value in clock.MODE_CLOCKS.values()), 53)
        selected = sorted(mode for (family, mode), value in clock.MODE_CLOCKS.items() if value == clock.FIXED0)
        self.assertEqual(hashlib.sha256(("\n".join(selected) + "\n").encode()).hexdigest(),
                         "a5b6f5d5194dc6113bb6864fe3c2e4efa44faf5ab6a6fee42fe8dc9ecd2160ee")
        for mode in ("graphical-console", "graphical-console-capture", "graphical-console-future"):
            with self.assertRaises(ValueError):
                clock.clock_profile("uefi", mode)
            with self.assertRaises(ValueError):
                clock.uefi_family(mode)
        combined = literal("scripts/kernel_graphical_console_admission.py", "MODES")
        self.assertTrue(set(combined).isdisjoint(mode for family, mode in clock.AUXILIARY_CLOCKS))

    def test_mandatory_combined_checker_routing(self):
        build = (ROOT / "scripts/kernel-uefi-build.sh").read_text()
        self.assertIn("set -euo pipefail", build)
        invalidation = build.index("    rm -f -- build/uefi/graphical-console-admission.json")
        guard = build.index("    if [[ ! -f scripts/kernel_graphical_console_admission.py ]]")
        self.assertLess(invalidation, guard)
        self.assertLess(guard, build.index('cxx="'))
        prefix = build[invalidation:guard]
        self.assertIn("build/uefi/graphical-console-build.json", prefix)
        self.assertIn("build/uefi/graphical-console-build-start.json", prefix)
        self.assertNotIn("||", prefix)
        self.assertNotIn("payload", prefix)
        commands = re.findall(r'^\s*python3 -B scripts/kernel_graphical_console_admission.py (\w+) --mode "\$UEFI_MODE"',
                              build, re.MULTILINE)
        self.assertEqual(commands, ["begin", "end", "emit"])
        begin = build.index("scripts/kernel_graphical_console_admission.py begin")
        compile_at = build.index("-c kernel/uefi/graphical-console.cpp")
        end = build.index("scripts/kernel_graphical_console_admission.py end")
        emit = build.index("scripts/kernel_graphical_console_admission.py emit")
        self.assertLess(begin, compile_at)
        self.assertLess(compile_at, end)
        self.assertLess(end, emit)
        self.assertIn('--linker "$UEFI_LINKER"', build[begin:compile_at])
        # Exact mode predicates keep legacy admission branches separate. This
        # intentionally does not pin the temporary source-only refusal guard.
        for match in re.finditer(r'^\s*python3 -B scripts/kernel_graphical_console_admission.py[^\n]*',
                                 build, re.MULTILINE):
            self.assertNotIn("||", match[0])
            self.assertNotIn("&&", match[0])

    def test_combined_live_source_inventory(self):
        admission = load("graphical_metadata_admission", "scripts/kernel_graphical_console_admission.py")
        paths = admission.source_files()
        self.assertEqual(len(paths), len(set(paths)))
        required = ("Makefile", "compiler/Makefile", "meson.build", "tests/meson.build",
                    "tests/compiler-test-inventory.json",
                    "examples/kernel-graphical-console.au", "kernel/uefi/graphical-console.cpp",
                    "kernel/uefi/graphical-console-entry.S", "scripts/kernel-uefi-build.sh",
                    "scripts/kernel_graphical_console_admission.py",
                    "tests/kernel-graphical-profile-metadata.py", "tests/developer-commands.py")
        for relative in required:
            self.assertIn(ROOT / relative, paths)
        for path in paths:
            self.assertTrue(path.is_file(), str(path))
            self.assertNotIn("build", path.relative_to(ROOT).parts)

    def test_combined_artifacts_exclude_legacy_objects(self):
        admission = load("graphical_metadata_outputs", "scripts/kernel_graphical_console_admission.py")
        paths = [path.relative_to(admission.BUILD).as_posix() for path in admission.build_files()]
        self.assertEqual(len(paths), len(set(paths)))
        for required in ("graphical-console.o", "graphical-console.su", "language.o", "language.s",
                         "console-entry.o", "console-poll-metadata.json", "image-metadata.json",
                         "payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI"):
            self.assertIn(required, paths)
        self.assertTrue({"console.o", "framebuffer.o", "program-build.json",
                         "console-service-admission.json", "framebuffer-admission.json"}.isdisjoint(paths))

    def test_isolated_compiler_header_staging_is_closed(self):
        headers = literal("tests/compiler/ir_exhaustive.py", "HEADERS")
        self.assertEqual(len(headers), len(set(headers)))
        self.assertIn("services.hpp", headers)
        for header in headers:
            path = ROOT / "compiler" / header
            self.assertTrue(path.is_file(), header)
            for dependency in re.findall(r'^\s*#include\s+"([^"]+)"', path.read_text(), re.MULTILINE):
                self.assertIn(dependency, headers, header + " requires " + dependency)

    def test_root_registration_and_compiler_inventory_stay_complete(self):
        inventory = load("graphical_metadata_inventory", "tests/test-inventory.py")
        root = (ROOT / "Makefile").read_text()
        root_all, root_runners, reached, recipes = inventory.make_inventory(root)
        compiler_all, compiler_runners, _, _ = inventory.make_inventory((ROOT / "compiler/Makefile").read_text())
        self.assertIn("test-developer-commands", reached)
        self.assertTrue(inventory.compiler_dispatch(recipes))
        commands = [line.strip() for line in recipes["test-developer-commands"]
                    if "kernel-graphical-profile-metadata.py" in line]
        self.assertEqual(commands, ["python3 -B tests/kernel-graphical-profile-metadata.py",
                                    "python3 -B -O tests/kernel-graphical-profile-metadata.py"])
        manifest = json.loads((ROOT / "tests/compiler-test-inventory.json").read_text())
        # Direct registration is separate from the Display runner's mandatory
        # composed child. Do not hide the two new borrow runners as unknown gaps.
        self.assertEqual({key: manifest["service_group.py"][key] for key in ("make", "root_make", "meson")},
                         {"make": False, "root_make": False, "meson": False})
        self.assertEqual({key: manifest["service_group_ir_abi.py"][key] for key in ("make", "root_make", "meson")},
                         {"make": True, "root_make": True, "meson": True})
        display = (ROOT / "tests/compiler/display_service.py").read_text()
        self.assertIn('ROOT / "tests/compiler/service_group.py", compiler', display)
        self.assertIn('require(grouped.returncode == 0,', display)
        self.assertIn('../tests/compiler/service_group_ir_abi.py', (ROOT / "compiler/Makefile").read_text())
        self.assertIn("files('compiler/service_group_ir_abi.py')", (ROOT / "tests/meson.build").read_text())
        inventory.check(manifest, {path.name for path in (ROOT / "tests/compiler").glob("*.py")},
                        root_all | compiler_all, root_runners=root_runners | compiler_runners)
        meson = (ROOT / "tests/meson.build").read_text()
        for name in ("graphical-profile-metadata", "graphical-profile-metadata-optimized"):
            self.assertEqual(meson.count("test('" + name + "',"), 1)
            declaration = meson.split("test('" + name + "',", 1)[1].split("\n", 2)[:2]
            self.assertIn("suite: ['full', 'dev']", "\n".join(declaration))


if __name__ == "__main__":
    unittest.main()

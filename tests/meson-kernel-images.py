#!/usr/bin/env python3
"""Compiler-free controls for native kernel generator boundaries, not image qualification."""

import importlib.util
import json
from pathlib import Path
import tempfile
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


class GeneratorBoundaries(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

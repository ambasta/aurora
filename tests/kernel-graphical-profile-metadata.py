#!/usr/bin/env python3
"""Pure metadata controls: no tool, compiler, image, guest or device execution.

Registration and artifact inventories do not establish runtime qualification.
"""

import ast
from copy import deepcopy
from contextlib import redirect_stdout
import io
import os
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
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
    values = [
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    if len(values) != 1:
        raise ValueError("Missing or ambiguous literal: " + name)
    return ast.literal_eval(values[0])


class ProfileMetadata(unittest.TestCase):
    def test_exact_modes_remain_separate(self):
        combined = literal("scripts/kernel_graphical_console_admission.py", "MODES")
        self.assertEqual(combined, ("graphical-console", "graphical-console-capture"))
        for checker in (
            "kernel_console_service_admission.py",
            "kernel_framebuffer_admission.py",
            "kernel_program_console_admission.py",
        ):
            self.assertTrue(set(combined).isdisjoint(literal("scripts/" + checker, "MODES")))
        catalog = load("metadata_profiles", "scripts/kernel_profiles.py").profiles()
        for mode in combined:
            self.assertEqual(catalog["uefi/" + mode]["admission"], "graphical")
            self.assertEqual(catalog["uefi/" + mode]["bridge"], "kernel/uefi/graphical-console-entry.S")

    def test_no_legacy_clock_admission_or_inherited_receipt(self):
        clock = load("graphical_metadata_clock", "scripts/kernel_emulator_clock.py")
        self.assertEqual(len(clock.MODE_CLOCKS), 205)
        self.assertEqual(sum(value == clock.FIXED0 for value in clock.MODE_CLOCKS.values()), 62)
        self.assertEqual(clock.clock_profile("uefi", "user-resume"), clock.FIXED0)
        selected = sorted(
            mode
            for (family, mode), value in clock.MODE_CLOCKS.items()
            if value == clock.FIXED0
            and mode
            not in (
                "runtime-owned-text",
                "runtime-owned-text-site",
                "runtime-owned-text-region",
                "runtime-owned-text-stale",
                "user-resume",
                "user-call",
                "user-call-pending",
                "user-call-owner",
                "user-call-site",
            )
        )
        self.assertEqual(
            hashlib.sha256(("\n".join(selected) + "\n").encode()).hexdigest(),
            "a5b6f5d5194dc6113bb6864fe3c2e4efa44faf5ab6a6fee42fe8dc9ecd2160ee",
        )
        for mode in ("graphical-console", "graphical-console-capture", "graphical-console-future"):
            with self.assertRaises(ValueError):
                clock.clock_profile("uefi", mode)
            with self.assertRaises(ValueError):
                clock.uefi_family(mode)
        combined = literal("scripts/kernel_graphical_console_admission.py", "MODES")
        self.assertTrue(set(combined).isdisjoint(mode for family, mode in clock.AUXILIARY_CLOCKS))

    def test_mandatory_combined_checker_routing(self):
        profiles = load("metadata_profile_selection", "scripts/kernel_profiles.py")
        catalog = profiles.profiles()
        for mode in ("graphical-console", "graphical-console-capture"):
            self.assertEqual(profiles.select("uefi", {"UEFI_MODE": mode}), mode)
            self.assertEqual(profiles.canonical_profile("uefi", mode), mode)
            self.assertEqual(catalog["uefi/" + mode]["admission"], "graphical")
            for inherited in ({"KERNEL_CONSOLE": "1"}, {"KERNEL_TEST_SCHEDULE": "1"}):
                with self.assertRaises(ValueError):
                    profiles.select("uefi", inherited, mode)
        for mode in ("console", "framebuffer", "program-console"):
            self.assertNotEqual(catalog["uefi/" + mode]["admission"], "graphical")

    def test_combined_artifacts_exclude_legacy_objects(self):
        admission = load("graphical_metadata_outputs", "scripts/kernel_graphical_console_admission.py")
        paths = [path.relative_to(admission.BUILD).as_posix() for path in admission.build_files()]
        self.assertEqual(len(paths), len(set(paths)))
        for required in (
            "graphical-console.o",
            "graphical-console.su",
            "graphical-console.ci",
            "language.o",
            "language.s",
            "console-entry.o",
            "console-poll-metadata.json",
            "image-metadata.json",
            "payload.elf",
            "payload.bin",
            "esp/EFI/BOOT/BOOTX64.EFI",
        ):
            self.assertIn("objects/" + required if required.endswith((".o", ".su", ".ci")) else required, paths)
        for name in admission.CPP_OBJECTS + ("loader",):
            for suffix in (".su", ".ci"):
                self.assertIn("objects/" + name + suffix, paths)
        self.assertTrue(
            {
                "objects/console.o",
                "objects/framebuffer.o",
                "console-service-admission.json",
                "framebuffer-admission.json",
            }.isdisjoint(paths)
        )

    def test_isolated_compiler_header_staging_is_closed(self):
        headers = literal("tests/compiler/ir_exhaustive.py", "HEADERS")
        generated = literal("tests/compiler/ir_exhaustive.py", "GENERATED_HEADERS")
        self.assertEqual(generated, ("hosted_frontend_abi.hpp",))
        self.assertTrue(set(headers).isdisjoint(generated))
        self.assertEqual(len(headers), len(set(headers)))
        self.assertIn("services.hpp", headers)
        for header in headers:
            path = ROOT / "compiler" / header
            self.assertTrue(path.is_file(), header)
            for dependency in re.findall(r'^\s*#include\s+"([^"]+)"', path.read_text(), re.MULTILINE):
                self.assertIn(dependency, headers + generated, header + " requires " + dependency)

    def test_root_registration_and_compiler_inventory_stay_complete(self):
        inventory = load("graphical_metadata_inventory", "tests/test-inventory.py")
        root = (ROOT / "Makefile").read_text()
        _, _, _, recipes = inventory.make_inventory(root)
        manifest = json.loads((ROOT / "tests/compiler-test-inventory.json").read_text())
        compiler_all = inventory.compiler_meson_inventory((ROOT / "compiler/Makefile").read_text(), manifest)
        root_runners = inventory.root_meson_inventory(root, manifest)
        commands = [
            line.strip()
            for line in recipes["test-developer-commands"]
            if "kernel-graphical-profile-metadata.py" in line
        ]
        self.assertEqual(
            commands,
            [
                "python3 -B -O tests/kernel-graphical-profile-metadata.py",
            ],
        )
        manifest = json.loads((ROOT / "tests/compiler-test-inventory.json").read_text())
        # Direct registration is separate from the Display runner's mandatory
        # composed child. Do not hide the two new borrow runners as unknown gaps.
        self.assertEqual(
            {key: manifest["service_group.py"][key] for key in ("make", "root_make", "meson")},
            {"make": False, "root_make": False, "meson": False},
        )
        self.assertEqual(
            {key: manifest["service_group_ir_abi.py"][key] for key in ("make", "root_make", "meson")},
            {"make": True, "root_make": True, "meson": True},
        )
        display = (ROOT / "tests/compiler/display_service.py").read_text()
        grouped = ast.parse(
            'grouped = run([sys.executable, "-B", "-O", ROOT / "tests/compiler/service_group.py", '
            'compiler, "--artifacts", work / "service-group"])'
        ).body[0]
        self.assertIn(
            ast.dump(grouped),
            [ast.dump(node) for node in ast.walk(ast.parse(display)) if isinstance(node, ast.Assign)],
        )
        self.assertIn("require(grouped.returncode == 0,", display)
        self.assertIn("files('compiler/service_group_ir_abi.py')", (ROOT / "tests/meson.build").read_text())
        inventory.check(
            manifest,
            {path.name for path in (ROOT / "tests/compiler").glob("*.py")},
            root_runners | compiler_all,
            root_runners=root_runners,
        )
        meson = (ROOT / "tests/meson.build").read_text()
        for name in ("graphical-profile-metadata-optimized",):
            self.assertEqual(meson.count("test('" + name + "',"), 1)
            declaration = meson.split("test('" + name + "',", 1)[1].split("\n", 2)[:2]
            self.assertIn("suite: ['full', 'dev']", "\n".join(declaration))

    def test_hosted_source_closure_and_identity_selection(self):
        runner = load("graphical_metadata_runner", "tests/kernel-graphical-console.py")
        expected = set(runner.SOURCE_INPUTS) | {
            "kernel/console-session.hpp",
            "kernel/console-uart.hpp",
            "kernel/console.hpp",
            "kernel/display-session.hpp",
            "kernel/graphical-session.hpp",
            "kernel/uefi/framebuffer-pixels.hpp",
            "kernel/uefi/framebuffer-policy.hpp",
            "kernel/uefi/graphical-capture-policy.hpp",
            "kernel/uefi/handoff.hpp",
            "kernel/uefi/runtime-layout.hpp",
        }
        self.assertEqual(set(runner.source_inputs()), expected)
        self.assertEqual(len(list(runner.cases())), 39)
        self.assertIn("library/graphics/font5x7.au", runner.SOURCE_INPUTS)
        self.assertNotRegex((ROOT / "library/graphics/font5x7.au").read_text(), r"(?m)^\s*import\b")
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(
                runner.arguments(["--run", "compiler", "--developer-selected-compiler"]).developer_selected_compiler
            )
            for extra in (
                [],
                ["--compiler-sha256", "invalid"],
                ["--developer-selected-compiler", "--compiler-sha256", "0" * 64],
                ["--developer-selected-compiler", "--developer-build-receipt", "receipt"],
            ):
                with self.subTest(extra=extra), self.assertRaises(RuntimeError):
                    runner.arguments(["--run", "compiler", *extra])
            for extra in (["--compiler-sha256", "0" * 64], ["--developer-build-receipt", "receipt"]):
                self.assertFalse(runner.arguments(["--run", "compiler", *extra]).developer_selected_compiler)
        with patch.dict(os.environ, {"AURORA_TEST_CONTEXT": "active"}), self.assertRaises(RuntimeError):
            runner.arguments(["--run", "compiler", "--developer-selected-compiler"])

    def test_hosted_failure_receipts_and_identity_finalization(self):
        runner = load("graphical_metadata_receipts", "tests/kernel-graphical-console.py")
        with tempfile.TemporaryDirectory(prefix="graphical-runner-controls-") as directory:
            base = Path(directory)
            compiler = base / "compiler"
            compiler.write_text("inert compiler identity fixture")
            for scenario in ("success", "short", "excess", "failure", "drift", "failure-and-drift"):
                out = base / scenario
                identity = SimpleNamespace(record=lambda: {"mode": "mocked-control"}, verify=lambda: None)
                if "drift" in scenario:

                    def drift():
                        raise RuntimeError("synthetic identity drift")

                    identity.verify = drift

                def execute(selected, work, records):
                    self.assertEqual(selected, compiler)
                    (work / "consumer.s").write_text("synthetic generated output")
                    if "failure" in scenario:
                        raise RuntimeError("synthetic native failure")
                    count = {"short": 153, "excess": 155}.get(scenario, 154)
                    records.extend(dict(name=str(n), geometry=[], status="passed") for n in range(count))

                args = SimpleNamespace(run=compiler, developer_selected_compiler=True, artifacts=out)
                with (
                    redirect_stdout(io.StringIO()),
                    patch.object(runner, "SelectedCompiler", return_value=identity),
                    patch.object(runner, "source_inputs", return_value={"fixture": "source-hash"}),
                    patch.object(runner, "file_record", return_value={"path": "tool", "sha256": "tool-hash"}),
                    patch.object(runner, "drift_checks"),
                    patch.object(runner, "execute_cases", side_effect=execute),
                    patch.object(runner.subprocess, "run", side_effect=AssertionError("No subprocess permitted")),
                ):
                    if scenario == "success":
                        runner.run_gate(args)
                    else:
                        with self.assertRaises(RuntimeError) as error:
                            runner.run_gate(args)
                        if "failure" in scenario:
                            self.assertEqual(str(error.exception), "synthetic native failure")
                        elif scenario in ("short", "excess"):
                            self.assertEqual(str(error.exception), "incomplete hosted graphical case inventory")
                record = json.loads((out / "run.json").read_text())
                self.assertEqual(record["status"], "passed" if scenario == "success" else "failed")
                self.assertFalse(record["native_complete"])
                self.assertFalse(record["guest_executed"])
                self.assertFalse(record["image_qualified"])
                self.assertEqual(record["case_count"], len(record["cases"]))
                self.assertEqual(
                    record["expected_cases"],
                    dict(transcript_geometry=117, session_reset=2, output_failure=13, denial=22),
                )
                if scenario == "success":
                    self.assertEqual(record["case_count"], 154)
                self.assertIn("consumer.s", record["generated_sha256"])
                if "drift" in scenario:
                    self.assertEqual(record["finalization_error"], "synthetic identity drift")

    def test_hosted_observer_rebuilt_for_each_execution(self):
        runner = load("graphical_metadata_rebuild", "tests/kernel-graphical-console.py")
        with tempfile.TemporaryDirectory(prefix="graphical-rebuild-controls-") as directory:
            work = Path(directory)
            calls = []

            def command(argv, directory, name):
                calls.append((argv, directory, name))
                if name == "link":
                    raise RuntimeError("stopped before native execution")

            with (
                patch.object(runner, "command", side_effect=command),
                patch.object(runner, "check_font") as check_font,
                patch.object(runner.subprocess, "run", side_effect=AssertionError("No subprocess permitted")),
            ):
                for _ in range(2):
                    with self.assertRaisesRegex(RuntimeError, "stopped before native execution"):
                        runner.execute_cases(work / "compiler", work, [])
            self.assertEqual(check_font.call_count, 2)
            check_font.assert_called_with(work / "compiler", work)
            self.assertEqual([name for _, _, name in calls], ["compile", "assemble", "link"] * 2)
            for argv, directory, name in calls:
                self.assertEqual(directory, work)
                if name == "link":
                    self.assertIn(str(ROOT / "tests/kernel-graphical-console.cpp"), argv)
                    self.assertIn(str(work / "consumer.o"), argv)
                    self.assertEqual(argv[-2:], ["-o", str(work / "consumer")])

    def test_graphical_route_inventory_mutations(self):
        inventory = load("graphical_metadata_routes", "tests/test-inventory.py")
        entries = []
        for name, (script, feedback, optimized) in inventory.GRAPHICAL_PYTHON_TESTS.items():
            argv = ["python3", "-B", *(["-O"] if optimized else []), str(ROOT / "tests" / script)]
            depends = []
            if name == "graphical-console-native":
                argv = ["python3", "-B", str(ROOT / "tests/meson_artifacts.py")] + argv
                argv += ["--run", "./aurorac", "--developer-selected-compiler", "--artifacts", "@ARTIFACTS@"]
                depends = ["aurorac@exe"]
            entries.append(
                dict(
                    name=name,
                    cmd=argv,
                    suite=["aurora-bootstrap:full", "aurora-bootstrap:" + feedback],
                    depends=depends,
                )
            )
        entries.append(
            dict(
                name="graphical-paging",
                cmd=["./tests/graphical-paging"],
                suite=["aurora-bootstrap:full", "aurora-bootstrap:dev"],
                depends=["model@@graphical-paging@exe"],
            )
        )
        inventory.check_graphical_meson(entries)
        for mutate in (
            lambda rows: rows.pop(),
            lambda rows: rows.append(deepcopy(rows[0])),
            lambda rows: rows[0].update(suite=["full", "dev"]),
            lambda rows: rows[0].update(depends=[]),
            lambda rows: rows[0]["cmd"].pop(),
            lambda rows: rows[0]["cmd"].pop(2),
            lambda rows: rows[-1].update(depends=[]),
            lambda rows: rows[1]["cmd"].append("--skip"),
        ):
            changed = deepcopy(entries)
            mutate(changed)
            with self.assertRaises(ValueError):
                inventory.check_graphical_meson(changed)
        meson = (ROOT / "tests/meson.build").read_text()
        self.assertRegex(meson, r"(?s)graphical_paging = executable\('graphical-paging'.*?link_args: \['-no-pie'\]\)")
        for name, (_, feedback, _) in inventory.GRAPHICAL_PYTHON_TESTS.items():
            declarations = re.findall(r"(?s)test\('" + re.escape(name) + r"',.*?\)\n", meson)
            self.assertEqual(len(declarations), 1, name)
            self.assertIn("suite: ['full', '" + feedback + "']", declarations[0])
            if name == "graphical-console-native":
                self.assertRegex(
                    declarations[0], r"'--developer-selected-compiler'\s*,\s*'--artifacts'\s*,\s*'@ARTIFACTS@'"
                )
                self.assertRegex(declarations[0], r"\bdepends\s*:\s*aurorac\b")


if __name__ == "__main__":
    unittest.main()

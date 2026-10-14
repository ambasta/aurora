#!/usr/bin/env python3
"""Compiler-free controls for native kernel generator boundaries, not image qualification."""

import importlib.util
from contextlib import contextmanager
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

    def test_reflection_and_local_symbols_are_explicit_and_supervisor_only(self):
        recipe = (ROOT / "kernel-images/meson.build").read_text()
        selection = (
            "if admission == 'program'\n    root_args += ['--referenced-reflection-only', '--local-symbols']\n  endif"
        )
        self.assertIn(selection, recipe)
        self.assertEqual(recipe.count("--referenced-reflection-only"), 1)
        self.assertEqual(recipe.count("--local-symbols"), 1)
        self.assertLess(recipe.index(selection), recipe.index("language = custom_target"))
        self.assertNotIn("--referenced-reflection-only", recipe[recipe.index("user_root_args = []") :])
        self.assertNotIn("--local-symbols", recipe[recipe.index("user_root_args = []") :])
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

    def test_noapic_rejection_is_exact_and_cannot_retain_runtime_authority(self):
        recipes = profiles.profiles()
        for name, recipe in recipes.items():
            self.assertEqual("--budget-noapic" in recipe["image_options"], name == "uefi/budget-noapic")
        self.assertEqual(recipes["uefi/budget-noapic"]["image_options"], ["--ipc-policy", "--budget-noapic"])
        self.assertTrue(image.image_options(["--ipc-policy", "--budget-noapic"])["require_budget_noapic"])
        for options in (["--budget-noapic"], ["--ipc-policy", "--budget-noapic", "--snapshot"]):
            with self.assertRaises(ValueError):
                image.image_options(options)
        runtime = "                 U aurora_kernel_terminal_event\n"
        payload = "0000000000001000 T uefi_runtime_enter\n"
        image.budget_noapic_policy(runtime, payload)
        for name in ("uefi_runtime_enter", "aurora_kernel_ipc_transition", "aurora_kernel_budget_tick"):
            for kind in ("U", "T", "w"):
                with self.subTest(symbol=name, kind=kind), self.assertRaises(ValueError):
                    image.budget_noapic_policy(runtime + "0000000000000010 " + kind + " " + name + "\n", payload)
        for name in ("uefi_service_drain_begin", "uefi_service_drain_end", "uefi_service_forged_pc"):
            with self.subTest(symbol=name), self.assertRaises(ValueError):
                image.budget_noapic_policy(runtime, payload + "0000000000002000 T " + name + "\n")
        with self.assertRaises(ValueError):
            image.budget_noapic_policy(runtime, "")

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
            deadline, signaled = time.monotonic() + 2, set()
            while children := self.children():
                for pid in children:
                    # WNOWAIT verifies direct-child ownership and keeps the PID
                    # unreaped until after any signal, preventing PID reuse.
                    os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                    if pid not in signaled:
                        os.kill(pid, signum)
                        signaled.add(pid)
                    if os.waitpid(pid, os.WNOHANG)[0]:
                        signaled.discard(pid)
                if time.monotonic() >= deadline:
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
            "qemu_transport.py",
            "kernel_emulator_clock.py",
            "uefi-firmware.sh",
        ):
            shutil.copy2(ROOT / "scripts" / name, self.repo / "scripts" / name)
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

    def test_only_budget_noapic_requires_absent_timer_metadata(self):
        image = self.native("uefi", "budget-noapic")
        calls = self.invoke(
            "uefi", "--run-only", image, "--output-dir", self.root / "bad-timer", "budget-noapic", success=False
        )
        self.assertEqual([call[0] for call in calls], ["qemu"])
        self.calls.unlink()
        (image / "service-timer-metadata.json").unlink()
        output = self.root / "no-timer"
        calls = self.invoke("uefi", "--run-only", image, "--output-dir", output, "budget-noapic")
        self.assertEqual([call[0] for call in calls], ["qemu", "oracle"])
        self.assertIsNone(json.loads((output / "budget-noapic.metadata.json").read_text())["kernel"])

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

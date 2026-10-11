#!/usr/bin/env python3
"""Compiler-free public console routing checks with recording tool substitutes.

The real Makefile, smoke wrapper and dependency selectors run in private copies.
Most cases record the exact PTY invocation. A failure-path case executes the
real PTY test against fake failing and interrupted emulators. No compiler, real QEMU or
guest acceptance is claimed.
"""

from pathlib import Path
import json
import importlib.util
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
MAKE = shutil.which("make")
SMOKE_SCRIPTS = (
    "kernel-uefi-tables-all.sh",
    "kernel-uefi-ivrs-all.sh",
    "kernel-uefi-pin-all.sh",
    "kernel-uefi-span-all.sh",
    "kernel-uefi-bar-all.sh",
    "kernel-protection-smoke.sh",
    "kernel-scheduling-smoke.sh",
    "kernel-uefi-all.sh",
    "kernel-acpi-all.sh",
    "kernel-division-smoke.sh",
    "kernel-pci-all.sh",
    "kernel-unsigned-smoke.sh",
    "kernel-uefi-runtime-all.sh",
    "kernel-uefi-ipc-all.sh",
    "kernel-uefi-budget-all.sh",
    "kernel-uefi-dispatch-all.sh",
    "kernel-uefi-user-phases-all.sh",
)


def target_prerequisites(source, target):
    """Collect every literal rule for a target, including continued rule lines."""
    logical = re.sub(r"\\\r?\n", " ", source)
    prerequisites = []
    for line in logical.splitlines():
        if not line or line.startswith("\t"):
            continue
        rule = line.split("#", 1)[0].split(";", 1)[0]
        if ":" not in rule:
            continue
        targets, dependencies = rule.split(":", 1)
        if "=" in dependencies:
            continue  # Target-specific variable assignments are not prerequisites.
        if target in targets.split():
            prerequisites.extend(dependencies.lstrip(":").replace("|", " ").split())
    return prerequisites


class MakePrerequisiteParsing(unittest.TestCase):
    def test_collects_fragmented_continued_and_shared_target_rules(self):
        source = (
            "test: test-program-stream\n"
            "other: smoke\n"
            "test other: test-compiler " + chr(92) + "\n  test-console # retained gate\n"
            "test: test-library | prepare\n"
            "\t@echo smoke\n"
        )
        self.assertEqual(
            target_prerequisites(source, "test"),
            ["test-program-stream", "test-compiler", "test-console", "test-library", "prepare"],
        )

    def test_detects_smoke_in_later_clause_and_exact_target_names(self):
        source = "test: test-compiler\ntest-extra: smoke-extra\ntest: smoke-console\n"
        self.assertEqual(target_prerequisites(source, "test"), ["test-compiler", "smoke-console"])


class ConsoleRouting(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-console-routing-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "repo"
        self.scripts = self.repo / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.record = self.home / "calls"
        self.env = {"PATH": str(self.bin), "HOME": str(self.home), "CALLS": str(self.record), "LC_ALL": "C"}
        for name in ("kernel-run.sh", "kernel-console-smoke.sh", "uefi-firmware.sh", "uefi-linker.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        shutil.copy2(ROOT / "Makefile", self.repo / "Makefile")
        (self.repo / "tests").mkdir()
        shutil.copy2(ROOT / "tests/kernel-console-pty.py", self.repo / "tests/kernel-console-pty.py")
        for name in ("bash", "dirname", "mkdir", "printf"):
            resolved = shutil.which(name)
            self.assertIsNotNone(resolved, name)
            (self.bin / name).symlink_to(resolved)
        for name in ("qemu-system-x86_64", "g++", "make", "as", "ld", "objcopy", "nm", "objdump", "readelf"):
            self.tool(name, 'printf "unexpected-tool|%s\\n" "$0" >> "$CALLS"\nexit 93\n')
        self.tool("ld", 'printf "Supported emulations:\n i386pep\n"\n')
        self.tool(
            "python3",
            'case "$*" in\n'
            '  "-B tests/kernel-console-pty.py --build-dir "*|"-B tests/kernel-console-pty.py --uefi --build-dir "*)\n'
            "    test -f tests/kernel-console-pty.py\n"
            '    printf "pty|%s|%s|%s|%s|%s|%s|%s\\n" "$PWD" "$*" "$QEMU" '
            '"${OVMF-}" "${OVMF_CODE-}" "${OVMF_VARS-}" "${QEMU_DATA-}" >> "$CALLS"\n'
            '    exit "${PTY_STATUS:-0}" ;;\n'
            '  "-B tests/kernel-boot-capacity.py --qemu")\n'
            '    printf "existing|kernel-boot-capacity.py --qemu\\n" >> "$CALLS"; exit 0 ;;\n'
            '  "-B scripts/meson_test.py "*)\n'
            '    printf "native-dispatch|%s\\n" "$*" >> "$CALLS"\n'
            '    exit "${CONTEXT_STATUS:-0}" ;;\n'
            '  *) printf "unexpected-python|%s\\n" "$*" >> "$CALLS"; exit 93 ;;\n'
            "esac\n",
        )
        for name, label, selector, console in (
            ("kernel-build.sh", "bios", "KERNEL_CONSOLE", "1"),
            ("kernel-uefi-build.sh", "uefi", "UEFI_MODE", "console"),
        ):
            self.script(
                self.scripts / name,
                f'printf "build|{label}|%s\\n" "${{{selector}-}}" >> "$CALLS"\n'
                f'mkdir -p "build/native profiles/{label}/console"\n'
                f'printf "%s\\n" "$PWD/build/native profiles/{label}/console"\n'
                'exit "${BUILD_STATUS:-0}"\n',
            )
        firmware = self.home / "firmware with spaces.fd"
        firmware.write_bytes(b"synthetic fixture, never executed")
        self.env["OVMF"] = str(firmware)

    def script(self, path, body):
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def tool(self, name, body):
        self.script(self.bin / name, body)
        return self.bin / name

    def run_command(self, command, env=None, expected=0, cwd=None):
        result = subprocess.run(
            command,
            cwd=cwd or self.home,
            env=self.env | (env or {}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        self.assertEqual(result.returncode, expected, result.stdout)
        return result.stdout

    def run_script(self, *args, env=None, expected=0):
        return self.run_command([BASH, str(self.scripts / "kernel-console-smoke.sh"), *args], env, expected)

    def run_make(self, *args, env=None, expected=0):
        self.assertIsNotNone(MAKE)
        return self.run_command([MAKE, *args], env, expected, self.repo)

    def calls(self):
        return self.record.read_text().splitlines() if self.record.exists() else []

    def clear_calls(self):
        self.record.unlink(missing_ok=True)

    def assert_no_work(self):
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.repo / "build").exists())

    def assert_route(self, mode):
        calls = self.calls()
        self.assertEqual(len(calls), 2, calls)
        self.assertEqual(calls[0], f"build|{mode}|" + ("console" if mode == "uefi" else "1"))
        argv = "-B tests/kernel-console-pty.py" + (" --uefi" if mode == "uefi" else "")
        argv += " --build-dir " + str(self.repo / f"build/native profiles/{mode}/console")
        self.assertEqual(calls[1].split("|")[:3], ["pty", str(self.repo), argv])

    def test_direct_default_and_explicit_platform_dispatch(self):
        for args, mode in (((), "bios"), (("bios",), "bios"), (("uefi",), "uefi")):
            with self.subTest(args=args):
                self.run_script(*args)
                self.assert_route(mode)
                self.clear_calls()

    def test_shared_entrypoint_uses_the_same_console_pty_routes(self):
        for mode in ("bios", "uefi"):
            self.run_command([BASH, str(self.scripts / "kernel-run.sh"), mode + "-console", "--smoke"])
            self.assert_route(mode)
            self.clear_calls()

    def test_shared_entrypoint_rejects_unknown_or_unsupported_routes_without_work(self):
        for args in (
            ("bios", "--other"),
            ("uefi", "--smoke", "extra"),
            ("console",),
            ("bios", ""),
            ("uefi", ""),
            ("bios-console", ""),
            ("uefi-console", ""),
            ("program-console", ""),
            ("iommu-event-success", "--smoke"),
            ("iommu-event", "--console"),
            ("bar-read", "--console"),
            ("ivrs-read", "--console"),
            ("graphical-console", "--console"),
            ("framebuffer", "--console"),
        ):
            self.run_command([BASH, str(self.scripts / "kernel-run.sh"), *args], expected=2)
        self.assert_no_work()

    def test_public_make_targets_dispatch_to_isolated_pty(self):
        for target, mode in (("smoke-console", "bios"), ("smoke-console-uefi", "uefi")):
            with self.subTest(target=target):
                self.run_make(target)
                self.assert_route(mode)
                self.clear_calls()

    def test_build_and_pty_status_preservation_without_restoration(self):
        for mode in ("bios", "uefi"):
            for build, pty, expected in ((0, 0, 0), (0, 17, 17), (23, 0, 23)):
                with self.subTest(mode=mode, build=build, pty=pty):
                    self.run_script(mode, env={"BUILD_STATUS": str(build), "PTY_STATUS": str(pty)}, expected=expected)
                    self.assertEqual(len(self.calls()), 1 if build else 2)
                    if not build:
                        self.assert_route(mode)
                    self.clear_calls()

    def test_parent_only_signal_waits_for_profile_build(self):
        sleep = shutil.which("sleep")
        self.assertIsNotNone(sleep)
        for mode, name, selector, console in (
            ("bios", "kernel-build.sh", "KERNEL_CONSOLE", "1"),
            ("uefi", "kernel-uefi-build.sh", "UEFI_MODE", "console"),
        ):
            self.script(
                self.scripts / name,
                f'if [[ "${{{selector}-}}" == {console} ]]; then\n'
                f'    printf "build|{mode}|started\\n" >> "$CALLS"\n'
                f'    "{sleep}" 0.2\n'
                f'    printf "build|{mode}|finished\\n" >> "$CALLS"\n'
                "else\n"
                f'    printf "build|{mode}|restored\\n" >> "$CALLS"\n'
                "fi\n",
            )
            for signum in (signal.SIGINT, signal.SIGTERM):
                with self.subTest(mode=mode, signal=signum):
                    process = subprocess.Popen(
                        [BASH, str(self.scripts / "kernel-console-smoke.sh"), mode],
                        cwd=self.home,
                        env=self.env,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                    )
                    try:
                        deadline = time.monotonic() + 5
                        while not self.calls() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.005)
                        self.assertEqual(self.calls(), [f"build|{mode}|started"])
                        process.send_signal(signum)
                        output, _ = process.communicate(timeout=5)
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 128 + signum, output)
                    self.assertEqual(self.calls(), [f"build|{mode}|started", f"build|{mode}|finished"])
                    self.clear_calls()

    def test_public_make_failure_is_not_success(self):
        for target in ("smoke-console", "smoke-console-uefi"):
            self.run_make(target, env={"PTY_STATUS": "17"}, expected=2)
            self.assertEqual(len(self.calls()), 2)
            self.clear_calls()

    def test_help_and_invalid_arguments_never_start_build_or_restore(self):
        for path in self.bin.iterdir():
            if path.name not in ("bash", "dirname"):
                path.unlink()
        self.assertIn("automated 30-second PTY", self.run_script("--help"))
        self.assertIn("automated 30-second PTY", self.run_script("-h"))
        for args in (("bad",), ("bios", "extra"), ("--help", "extra")):
            self.run_script(*args, expected=2)
        self.assert_no_work()

    def test_mixed_controls_reject_before_build_or_restore(self):
        for mode in ("bios", "uefi"):
            for name in (
                "KERNEL_TEST_DIVISION",
                "KERNEL_TEST_FUTURE",
                "KERNEL_USER_PROBE_MODE",
                "KERNEL_CONSOLE",
                "UEFI_MODE",
                "UEFI_CONSOLE_HANDOFF",
                "AURORA_TEST_CONTEXT",
            ):
                with self.subTest(mode=mode, name=name):
                    self.run_script(mode, env={name: "1"}, expected=2)
                    self.assert_no_work()

    def test_missing_emulator_and_builder_tools_never_start_restore(self):
        for mode in ("bios", "uefi"):
            names = ["qemu-system-x86_64", "g++", "make", "as", "ld", "objcopy", "nm", "python3"]
            if mode == "uefi":
                names += ["objdump", "readelf"]
            for name in names:
                with self.subTest(mode=mode, name=name):
                    tool = self.bin / name
                    held = tool.with_suffix(".held")
                    tool.rename(held)
                    try:
                        self.assertIn("Missing dependency: " + name, self.run_script(mode, expected=2))
                    finally:
                        held.rename(tool)
                    self.assert_no_work()

    def test_invalid_selected_tools_and_data_reject_without_work(self):
        for mode in ("bios", "uefi"):
            for name in ("QEMU", "CXX", "AURORAC", "QEMU_DATA"):
                with self.subTest(mode=mode, name=name):
                    self.run_script(mode, env={name: "/missing/selected-tool-or-data"}, expected=2)
                    self.assert_no_work()

    def test_invalid_firmware_and_linker_reject_without_work(self):
        for overrides in (
            {"OVMF": "/missing/OVMF.fd"},
            {"OVMF_CODE": "conflicting"},
            {"OVMF": "", "OVMF_DIR": str(self.home)},
            {"OVMF": "", "OVMF_CODE": "missing-pair"},
            {"UEFI_LD": "missing-linker"},
        ):
            self.run_script("uefi", env=overrides, expected=2)
            self.assert_no_work()
        self.tool("ld", 'printf "Supported emulations:\n elf_x86_64\n"\n')
        self.assertIn("Missing UEFI PE linker", self.run_script("uefi", expected=2))
        self.assert_no_work()

    def test_make_missing_prerequisite_or_mixed_control_does_not_restore(self):
        for target in ("smoke-console", "smoke-console-uefi"):
            for override in ("QEMU=no-such-qemu", "KERNEL_CONSOLE=1", "KERNEL_TEST_FUTURE=1"):
                self.run_make(target, override, expected=2)
                self.assert_no_work()

    def test_make_selectors_preserve_paths_with_spaces(self):
        qemu = self.tool("selected qemu", "exit 93\n")
        data = self.home / "qemu data"
        data.mkdir()
        code = self.home / "firmware CODE.fd"
        variables = self.home / "firmware VARS.fd"
        code.write_bytes(b"synthetic CODE")
        variables.write_bytes(b"synthetic VARS")
        self.run_make(
            "smoke-console-uefi",
            "QEMU=" + str(qemu),
            "QEMU_DATA=" + str(data),
            "OVMF=",
            "OVMF_CODE=" + str(code),
            "OVMF_VARS=" + str(variables),
        )
        self.assert_route("uefi")
        self.assertEqual(self.calls()[1].split("|")[3:], [str(qemu), "", str(code), str(variables), str(data)])

    def test_explicit_empty_qemu_uses_same_default_at_preflight_and_dispatch(self):
        self.run_script(env={"QEMU": ""})
        self.assertEqual(self.calls()[1].split("|")[3], "qemu-system-x86_64")

    def test_smoke_all_keeps_existing_routes_and_adds_both_consoles(self):
        for name in SMOKE_SCRIPTS:
            self.script(self.scripts / name, f'printf "existing|{name}\\n" >> "$CALLS"\n')
        self.run_make("smoke-all")
        calls = self.calls()
        self.assertEqual(calls.pop(0), "existing|kernel-boot-capacity.py --qemu")
        self.assertEqual(calls[: len(SMOKE_SCRIPTS)], ["existing|" + name for name in SMOKE_SCRIPTS])
        self.assertEqual(len(calls), len(SMOKE_SCRIPTS) + 4)
        console_calls = calls[len(SMOKE_SCRIPTS) :]
        self.assertEqual(console_calls[0], "build|bios|1")
        self.assertIn("|-B tests/kernel-console-pty.py --build-dir ", console_calls[1])
        self.assertEqual(console_calls[2], "build|uefi|console")
        self.assertIn("|-B tests/kernel-console-pty.py --uefi --build-dir ", console_calls[3])

    def test_real_pty_entrypoint_failure_propagates_through_public_make_targets(self):
        for name in ("kernel_uefi_console_clock.py", "kernel_emulator_clock.py", "qemu_transport.py"):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        self.env["REAL_PYTHON"] = sys.executable
        self.tool("python3", 'exec "$REAL_PYTHON" -B "$@"\n')
        self.tool("qemu-system-x86_64", 'printf "qemu|%s\\n" "$*" >> "$CALLS"\nexit 35\n')
        # The build substitute creates only the directory expected by the real PTY
        # runner. It never produces or starts a guest image.
        (self.repo / "build/uefi").mkdir(parents=True)
        for target, mode in (("smoke-console", "bios"), ("smoke-console-uefi", "uefi")):
            with self.subTest(target=target):
                output = self.run_make(target, expected=2)
                self.assertIn("kernel-console-pty.py", output)
                self.assertIn("QEMU closed its PTY before the expected console response", output)
                calls = self.calls()
                self.assertEqual(len(calls), 2, calls)
                self.assertEqual(calls[0], f"build|{mode}|" + ("console" if mode == "uefi" else "1"))
                self.assertTrue(calls[1].startswith("qemu|-machine " + ("q35" if mode == "uefi" else "pc")))
                self.assertIn("-accel tcg -cpu qemu64", calls[1])
                self.assertNotIn("-icount", calls[1])
                directory = self.repo / f"build/native profiles/{mode}/console"
                self.assertEqual((directory / "kernel-console-pty.log").read_bytes(), b"")
                metrics = json.loads((directory / "kernel-console-pty.metrics.json").read_text())
                self.assertEqual(metrics["platform"], mode)
                if mode == "uefi":
                    receipt = json.loads((directory / "console-pty.clock.json").read_text())
                    self.assertEqual(receipt["clock_profile"], "tcg-original-clock")
                    self.assertNotIn("-icount", receipt["argv"])
                self.clear_calls()

    def test_process_group_term_joins_detached_emulator(self):
        for name in ("kernel_uefi_console_clock.py", "kernel_emulator_clock.py", "qemu_transport.py"):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        self.env["REAL_PYTHON"] = sys.executable
        pid_file = self.home / "qemu.pid"
        self.env["QEMU_PID_FILE"] = str(pid_file)
        self.tool("python3", 'exec "$REAL_PYTHON" -B "$@"\n')
        qemu = self.bin / "qemu-system-x86_64"
        qemu.write_text(
            f"#!{sys.executable}\n"
            "import os, signal\n"
            "from pathlib import Path\n"
            "def record(message):\n"
            "    with open(os.environ['CALLS'], 'a') as stream:\n"
            "        stream.write(message + '\\n')\n"
            "def stop(number, frame):\n"
            "    record('qemu|stopped')\n"
            "    raise SystemExit(35)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "Path(os.environ['QEMU_PID_FILE']).write_text(str(os.getpid()))\n"
            "record('qemu|started')\n"
            "while True:\n"
            "    signal.pause()\n"
        )
        qemu.chmod(0o755)
        for mode in ("bios", "uefi"):
            with self.subTest(mode=mode):
                process = subprocess.Popen(
                    [BASH, str(self.scripts / "kernel-console-smoke.sh"), mode],
                    cwd=self.home,
                    env=self.env,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    deadline = time.monotonic() + 5
                    while "qemu|started" not in self.calls() and process.poll() is None:
                        self.assertLess(time.monotonic(), deadline, self.calls())
                        time.sleep(0.005)
                    self.assertIn("qemu|started", self.calls())
                    os.killpg(process.pid, signal.SIGTERM)
                    output, _ = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 143, output)
                    self.assertEqual(
                        self.calls(),
                        [
                            f"build|{mode}|" + ("console" if mode == "uefi" else "1"),
                            "qemu|started",
                            "qemu|stopped",
                        ],
                    )
                    with self.assertRaises(ProcessLookupError):
                        os.kill(int(pid_file.read_text()), 0)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.communicate(timeout=5)
                    if pid_file.exists():
                        try:
                            os.kill(int(pid_file.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        pid_file.unlink()
                self.clear_calls()

    def test_make_test_dispatches_only_canonical_native_graph(self):
        self.run_make("test")
        self.assertEqual(len(self.calls()), 1)
        self.assertIn("scripts/meson_test.py --repo-root", self.calls()[0])
        self.assertTrue(self.calls()[0].endswith("--suite full"))
        source = (self.repo / "Makefile").read_text()
        prerequisites = target_prerequisites(source, "test")
        self.assertEqual(prerequisites, [])
        self.assertFalse(any(name.startswith("smoke") for name in prerequisites), prerequisites)

    def test_make_help_discovers_both_public_console_gates(self):
        output = self.run_make("help")
        self.assertIn("make smoke-console ", output)
        self.assertIn("make smoke-console-uefi ", output)
        self.assert_no_work()


class NormalRestoration(unittest.TestCase):
    def test_console_output_cannot_be_inside_prebuilt_image(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("console_output_controls", ROOT / "tests/kernel-console-pty.py")
        console = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(console)
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary) / "native/kernel-images/bios/console"
            build.mkdir(parents=True)
            output = build / "esp/guest-output"
            with (
                patch.object(sys, "argv", ["pty", "--build-dir", str(build), "--output-dir", str(output)]),
                patch.object(console.transport, "start") as start,
            ):
                with self.assertRaisesRegex(RuntimeError, "cannot modify"):
                    console.main()
            start.assert_not_called()
            self.assertFalse(output.exists())

    def test_prebuilt_restoration_uses_one_private_run_only_call(self):
        spec = importlib.util.spec_from_file_location(
            "console_prebuilt_restoration", ROOT / "tests/kernel-console-service-qualification.py"
        )
        qualification = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qualification)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "native/kernel-images/uefi/normal"
            image.mkdir(parents=True)
            work = root / "evidence"
            work.mkdir()
            (image / "normal.log").write_text("untouched shared log")
            output = work / "normal-restoration"

            def run(argv, timeout, env=None):
                self.assertNotIn("--print-image-dir", argv)
                self.assertEqual(argv[2:], ["--run-only", str(image), "--output-dir", str(output), "normal"])
                output.mkdir()
                (output / "normal.log").write_text("fresh private log")
                (output / "normal.clock.json").write_text("fresh private clock")
                return subprocess.CompletedProcess(argv, 0, b"normal boot passed", b"")

            with patch.object(qualification, "run_bounded", side_effect=run) as bounded:
                qualification.restore_normal(work, {}, normal_build=image)
            bounded.assert_called_once()
            self.assertEqual((image / "normal.log").read_text(), "untouched shared log")
            self.assertEqual((work / "restoration-normal.log").read_text(), "fresh private log")

    def test_native_restoration_requires_fresh_mandatory_outputs_and_preserves_compiler(self):
        spec = importlib.util.spec_from_file_location(
            "console_restoration_controls", ROOT / "tests/kernel-console-service-qualification.py"
        )
        qualification = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(qualification)
        for behavior in ("fresh", "stale", "missing", "failed"):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                image = root / "native/kernel-images/uefi/normal"
                image.mkdir(parents=True)
                work = root / "evidence"
                work.mkdir()
                for name in ("normal.log", "normal.clock.json"):
                    path = image / name
                    if behavior != "missing" or name != "normal.clock.json":
                        path.write_bytes(b"same bytes are allowed after a fresh write")
                        os.utime(path, ns=(1, 1))
                calls = []

                def run(argv, timeout, env=None):
                    calls.append(argv)
                    self.assertEqual(env["AURORAC"], "/reviewed/prebuilt-compiler")
                    if "--print-image-dir" in argv:
                        return subprocess.CompletedProcess(argv, 0, (str(image) + "\n").encode(), b"")
                    self.assertEqual(argv[-1], "normal")
                    self.assertNotIn("--shared-normal", argv)
                    self.assertEqual(env["MESON_BUILD_DIR"], str(root / "native"))
                    if behavior == "fresh":
                        for name in ("normal.log", "normal.clock.json"):
                            (image / name).write_bytes(b"same bytes are allowed after a fresh write")
                    elif behavior == "missing":
                        (image / "normal.log").write_bytes(b"fresh log")
                    return subprocess.CompletedProcess(argv, 1 if behavior == "failed" else 0, b"boot", b"stderr")

                with patch.object(qualification, "run_bounded", side_effect=run):
                    if behavior == "fresh":
                        receipt = qualification.restore_normal(work, {"AURORAC": "/reviewed/prebuilt-compiler"})
                        self.assertEqual(receipt["image_directory"], str(image))
                        for name in ("normal.log", "normal.clock.json"):
                            self.assertEqual((work / ("restoration-" + name)).read_bytes(), (image / name).read_bytes())
                    else:
                        expected = {"stale": "Stale", "missing": "Missing", "failed": "restoration failed"}[behavior]
                        with self.assertRaisesRegex(ValueError, expected):
                            qualification.restore_normal(work, {"AURORAC": "/reviewed/prebuilt-compiler"})
                self.assertEqual(len(calls), 2)


class ConsoleFaultTransport(unittest.TestCase):
    def load(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location(
            "fault_transport_control", ROOT / "tests/kernel-console-service-qualification.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_shared_fault_transport_retains_four_independent_fault_oracles(self):
        qualification = self.load()
        start = qualification.transport.start
        prefix = (
            b"AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"
            b"AURORA_UEFI_CONSOLE_TIMER_READY: polling_count=1250000 uart_irq=0\n"
        )
        ready = b"AURORA_CONSOLE_READY: UEFI, ASCII, 64-byte lines\naurora> "
        rejected = b"AURORA_UEFI_CONSOLE_FAIL: console service authority\n"
        tails = {"stale": rejected, "reentry": ready + rejected, "timeout": ready[:17], "report": ready}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for mode, tail in tails.items():
                work = root / mode
                work.mkdir()
                body = "import os; os.write(1, " + repr(prefix + tail) + ")\n"
                if mode == "report":
                    body += "if os.read(0, 1) != b'x': raise SystemExit(9)\n"
                    report = b"AURORA_UEFI_EXCEPTION: vector=255 fault\nAURORA_UEFI_PAYLOAD_FAIL: exception\n"
                    body += "os.write(1, " + repr(report) + ")\n"
                body += "raise SystemExit(35)\n"

                def launch(argv, **options):
                    self.assertIn("file=fat:ro:" + str(root / "esp"), " ".join(argv))
                    return start([sys.executable, "-B", "-c", body], **options)

                with (
                    self.subTest(mode=mode),
                    patch.object(qualification.admission, "BUILD", root),
                    patch.object(qualification.shutil, "which", return_value=sys.executable),
                    patch.object(qualification.subprocess, "check_output", return_value=b"/firmware\0\0\0"),
                    patch.object(qualification.transport, "start", side_effect=launch),
                ):
                    result = qualification.fault_guest("console-service-" + mode, work)
                self.assertEqual(result["exit_status"], 35)
                self.assertEqual(result["input_sent"], mode == "report")
                self.assertTrue((work / "guest.log").read_bytes().startswith(prefix))
                self.assertTrue((work / "clock.json").is_file())

    def test_shared_helper_keeps_stdout_stderr_and_exit_status_separate(self):
        qualification = self.load()
        result = qualification.run_bounded(
            [sys.executable, "-B", "-c", "import os; os.write(1,b'out'); os.write(2,b'err'); raise SystemExit(7)"], 5
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (7, b"out", b"err"))


if __name__ == "__main__":
    unittest.main()

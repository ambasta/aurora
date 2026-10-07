#!/usr/bin/env python3
"""Synthetic command-routing checks; never build Aurora or start real QEMU.

Each case copies only entry scripts/Makefile into a temporary fixture. Fake tools
record argv/environment or fail immediately. This does not establish compiler,
native aggregate, firmware or emulator acceptance.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
MAKE = shutil.which("make")


class DeveloperCommands(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-dev-commands-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "repo"
        self.scripts = self.repo / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.record = self.home / "calls"
        self.env = {"PATH": str(self.bin), "HOME": str(self.home),
                    "CALLS": str(self.record), "LC_ALL": "C"}
        for name in ("kernel-run.sh", "compiler-test.sh", "kernel-build.sh", "kernel-uefi-build.sh", "uefi-firmware.sh", "uefi-linker.sh", "host-build-check.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        shutil.copy2(ROOT / "Makefile", self.repo / "Makefile")
        shutil.copy2(ROOT / "scripts/kernel-console.sh", self.scripts / "kernel-console.sh")
        for name in ('kernel-uefi-console.sh', 'kernel_uefi_console_clock.py', 'kernel_emulator_clock.py'):
            shutil.copy2(ROOT / 'scripts' / name, self.scripts / name)
        for name in ("bash", "dirname", "cat", "mkdir", "printf"):
            resolved = shutil.which(name)
            self.assertIsNotNone(resolved, name)
            (self.bin / name).symlink_to(resolved)
        for name in ("qemu-system-x86_64", "timeout", "g++", "python3",
                     "as", "ld", "objcopy", "objdump", "nm", "readelf"):
            self.tool(name, "exit 93\n")
        self.tool("ld", 'printf "Supported emulations:\n i386pep\n"\n')
        self.tool("make", 'printf "make|%s|%s|%s|%s\\n" "$PWD" "$*" "${CXX-}" "${CXXFLAGS-}" >> "$CALLS"\nexit "${FAKE_STATUS:-0}"\n')
        for name, label in (("kernel-smoke.sh", "bios"), ("kernel-uefi-smoke.sh", "uefi")):
            self.script(self.scripts / name,
                        'printf "%s|%s|%s|%s|%s|%s|%s\\n" "' + label + '" "$PWD" "$*" "${CXX-}" "${QEMU-}" "${OVMF-}" "${QEMU_DATA-}" >> "$CALLS"\nexit "${FAKE_STATUS:-0}"\n')

    def script(self, path, body):
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def tool(self, name, body):
        self.script(self.bin / name, body)
        return self.bin / name

    def run_script(self, name, *args, env=None, expected=0):
        current = self.env | (env or {})
        result = subprocess.run([BASH, str(self.scripts / name), *args],
                                cwd=self.home, env=current, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=5)
        self.assertEqual(result.returncode, expected, result.stdout)
        return result.stdout

    def calls(self):
        return self.record.read_text().splitlines() if self.record.exists() else []

    def assert_no_work(self):
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.repo / "build").exists())

    def firmware(self):
        path = self.home / "firmware with spaces.fd"
        path.write_bytes(b"synthetic fixture, never executed")
        return str(path)

    def test_help_does_not_need_build_or_emulator_tools(self):
        (self.bin / "qemu-system-x86_64").unlink()
        (self.bin / "make").unlink()
        self.assertIn("not an interactive OS shell", self.run_script("kernel-run.sh", "--help"))
        self.assertIn("compiler-only", self.run_script("compiler-test.sh", "--help"))
        self.assert_no_work()

    def test_invalid_arguments_do_not_dispatch(self):
        for args in (("other",), ("bios", "extra"), ("--help", "extra")):
            self.run_script("kernel-run.sh", *args, expected=2)
        self.run_script("compiler-test.sh", "test", expected=2)
        self.assert_no_work()

    def test_bios_default_and_explicit_route_from_other_directory(self):
        self.run_script("kernel-run.sh")
        self.run_script("kernel-run.sh", "bios")
        self.assertEqual(self.calls(), [f"bios|{self.repo}|normal||||", f"bios|{self.repo}|normal||||"])

    def test_uefi_overrides_and_paths_with_spaces_are_preserved(self):
        firmware = self.firmware()
        qemu = str(self.tool("alternate qemu", "exit 93\n"))
        data = self.home / "qemu data"
        data.mkdir()
        env = {"OVMF": firmware, "QEMU": qemu, "QEMU_DATA": str(data), "CXX": "g++-16"}
        self.run_script("kernel-run.sh", "uefi", env=env)
        self.assertEqual(self.calls(), [f"uefi|{self.repo}|normal|g++-16|{qemu}|{firmware}|{data}"])

    def test_existing_runner_failure_is_propagated(self):
        self.run_script("kernel-run.sh", env={"FAKE_STATUS": "17"}, expected=17)
        self.assertEqual(len(self.calls()), 1)

    def test_smoke_runners_detach_qemu_from_a_terminal(self):
        # Interactive runs give the runner a terminal stdin. timeout puts QEMU in a
        # background process group, so -serial stdio changing that terminal's mode
        # stops QEMU (SIGTTOU) until the time limit. QEMU must never inherit it.
        for name in ("timeout", "cp", "env"):
            (self.bin / name).unlink(missing_ok=True)
            (self.bin / name).symlink_to(shutil.which(name))
        for name in ("kernel-smoke.sh", "kernel-uefi-smoke.sh"):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        for name in ("kernel-build.sh", "kernel-uefi-build.sh"):
            self.script(self.scripts / name, 'mkdir -p build/uefi\nprintf "{}" > build/user-metadata.json\n')
        # Clock selection and full argv binding must use the real helper. Only
        # the normal serial validators are synthetic in this routing fixture.
        shutil.copy2(ROOT / "scripts/kernel_emulator_clock.py",
                     self.scripts / "kernel_emulator_clock.py")
        self.env["REAL_PYTHON"] = sys.executable
        self.tool("python3", 'case "$1" in\n'
                  '  scripts/kernel_emulator_clock.py) exec "$REAL_PYTHON" -B "$@" ;;\n'
                  '  tests/kernel-smoke.py|tests/kernel-uefi-smoke.py) exit 0 ;;\n'
                  '  *) echo "Unexpected Python command in terminal fixture" >&2; exit 93 ;;\n'
                  'esac\n')
        self.tool("qemu-system-x86_64", 'if [ -t 0 ]; then state=terminal; else state=detached; fi\n'
                  'printf "qemu|stdin-%s\\n" "$state" >> "$CALLS"\nexit 33\n')
        for name in ("kernel-smoke.sh", "kernel-uefi-smoke.sh"):
            leader, follower = os.openpty()
            self.addCleanup(os.close, leader)
            try:
                self.assertTrue(os.isatty(follower))
                result = subprocess.run([BASH, str(self.scripts / name)], cwd=self.home,
                                        env=self.env | {"OVMF": self.firmware()}, stdin=follower,
                                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        timeout=10)
            finally:
                os.close(follower)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("PASS:", result.stdout)
        self.assertEqual(self.calls(), ["qemu|stdin-detached"] * 2)
        receipt = json.loads((self.repo / "build/uefi/normal.clock.json").read_text())
        self.assertEqual(receipt["clock_profile"], "tcg-original-clock")
        self.assertNotIn("-icount", receipt["argv"])
        self.assertEqual(receipt["timeout_argv"], ["timeout", "30", *receipt["argv"]])
        self.assertEqual(receipt["execution_status"], "not-established-by-command-receipt")

    def test_fault_environment_is_rejected_before_dispatch(self):
        for name in ("KERNEL_TEST_DIVISION", "KERNEL_TEST_FUTURE_MODE", "KERNEL_USER_PROBE_MODE",
                     "KERNEL_CONSOLE", "UEFI_MODE"):
            output = self.run_script("kernel-run.sh", env={name: "1"}, expected=2)
            self.assertIn("Unset " + name, output)
        self.assert_no_work()

    def test_console_launcher_is_foreground_bounded_and_preserves_status(self):
        self.script(self.scripts / "kernel-build.sh",
                    'printf "build|%s\\n" "$KERNEL_CONSOLE" >> "$CALLS"\n')
        self.tool("timeout", 'printf "timeout|%s\\n" "$*" >> "$CALLS"\nexit "$FAKE_STATUS"\n')
        for status, expected in ((33, 0), (35, 35), (124, 124)):
            self.run_script("kernel-console.sh", env={"FAKE_STATUS": str(status)}, expected=expected)
        self.assertEqual(len(self.calls()), 6)
        for build, command in zip(self.calls()[::2], self.calls()[1::2]):
            self.assertEqual(build, "build|1")
            self.assertTrue(command.startswith("timeout|--foreground --kill-after=2 300 qemu-system-x86_64 "))
            self.assertIn("snapshot=on", command)
            self.assertIn("-nic none -display none -serial stdio -monitor none", command)

    def test_console_launcher_rejects_mixed_controls_before_build(self):
        for name in ("KERNEL_TEST_SCHEDULE", "KERNEL_USER_PROBE_MODE", "KERNEL_CONSOLE", "AURORA_TEST_CONTEXT"):
            self.run_script("kernel-console.sh", env={name: "1"}, expected=2)
        self.run_script("kernel-console.sh", "extra", expected=2)
        self.assert_no_work()

    def test_uefi_console_uses_original_clock_and_preserves_status(self):
        self.script(self.scripts / 'kernel-uefi-build.sh',
                    'mkdir -p build/uefi\nprintf "build|%s\\n" "$UEFI_MODE" >> "$CALLS"\n')
        self.env['REAL_PYTHON'] = sys.executable
        self.tool('python3', 'exec "$REAL_PYTHON" -B "$@"\n')
        self.tool('timeout', 'printf "timeout|%s\\n" "$*" >> "$CALLS"\nexit "$FAKE_STATUS"\n')
        firmware = self.firmware()
        for status, expected in ((33, 0), (35, 35), (124, 124)):
            self.run_script('kernel-uefi-console.sh', env={'FAKE_STATUS': str(status), 'OVMF': firmware},
                            expected=expected)
        self.assertEqual(len(self.calls()), 6)
        for build, command in zip(self.calls()[::2], self.calls()[1::2]):
            self.assertEqual(build, 'build|console')
            self.assertTrue(command.startswith('timeout|--foreground --kill-after=2 300 qemu-system-x86_64 '))
            self.assertIn('-machine q35 -accel tcg', command)
            self.assertNotIn('-icount', command)
        receipt = json.loads((self.repo / 'build/uefi/console.clock.json').read_text())
        self.assertEqual(receipt['clock_profile'], 'tcg-original-clock')
        self.assertEqual(receipt['command_template'], 'normal')
        self.assertEqual(receipt['execution_status'], 'not-established-by-command-receipt')

    def test_uefi_console_rejects_mixed_controls_before_build(self):
        for name in ('KERNEL_TEST_SCHEDULE', 'KERNEL_USER_PROBE_MODE', 'KERNEL_CONSOLE', 'UEFI_MODE',
                     'UEFI_CONSOLE_HANDOFF', 'AURORA_TEST_CONTEXT'):
            self.run_script('kernel-uefi-console.sh', env={name: '1'}, expected=2)
        self.run_script('kernel-uefi-console.sh', 'extra', expected=2)
        self.assert_no_work()

    def test_empty_fault_environment_is_not_an_injection(self):
        self.run_script("kernel-run.sh", env={"KERNEL_TEST_DIVISION": "", "UEFI_MODE": ""})
        self.assertEqual(len(self.calls()), 1)

    def test_missing_qemu_or_timeout_fails_before_build(self):
        for name in ("qemu-system-x86_64", "timeout"):
            path = self.bin / name
            held = path.with_name(name + ".held")
            path.rename(held)
            output = self.run_script("kernel-run.sh", expected=2)
            self.assertIn("Missing dependency: " + name, output)
            held.rename(path)
        self.assert_no_work()

    def test_invalid_firmware_and_data_fail_before_build(self):
        self.assertIn("combined OVMF.fd", self.run_script("kernel-run.sh", "uefi", env={"OVMF": str(self.home / "missing.fd")}, expected=2))
        self.assertIn("combined OVMF.fd", self.run_script("kernel-run.sh", "uefi", env={"OVMF": str(self.home)}, expected=2))
        self.assertIn("QEMU_DATA", self.run_script("kernel-run.sh", env={"QEMU_DATA": str(self.home / "missing-data")}, expected=2))
        self.assert_no_work()

    def test_compiler_route_preserves_controls_and_failure(self):
        cxx = str(self.tool("g++-16", "exit 93\n"))
        flags = "-std=c++23 -O2 -Wall -Wextra -Werror"
        self.run_script("compiler-test.sh", env={"CXX": cxx, "CXXFLAGS": flags, "FAKE_STATUS": "19"}, expected=19)
        self.assertEqual(self.calls(), [f"make|{self.repo}|-C compiler test|{cxx}|{flags}"])

    def test_compiler_missing_tool_has_no_work(self):
        self.run_script("compiler-test.sh", env={"CXX": "no-such-compiler"}, expected=2)
        self.assert_no_work()

    def test_image_builders_check_dependencies_before_outputs(self):
        for name in ("kernel-build.sh", "kernel-uefi-build.sh"):
            self.assertIn("Missing dependency: no-such-compiler", self.run_script(name, env={"CXX": "no-such-compiler"}, expected=2))
        (self.bin / "readelf").unlink()
        self.assertIn("Missing dependency: readelf", self.run_script("kernel-uefi-build.sh", expected=2))
        self.assert_no_work()

    def test_uefi_missing_pe_linker_fails_before_outputs(self):
        self.tool("ld", 'printf "Supported emulations:\n elf_x86_64\n"\n')
        self.assertIn("i386pep", self.run_script("kernel-uefi-build.sh", expected=2))
        self.assert_no_work()

    def test_make_uefi_checks_linker_before_compiler_build(self):
        self.tool("ld", 'printf "Supported emulations:\n elf_x86_64\n"\n')
        result = subprocess.run([MAKE, "kernel-uefi"], cwd=self.repo, env=self.env,
                                text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing UEFI PE linker", result.stderr)
        self.assert_no_work()

    def test_explicit_uefi_linker_never_falls_back(self):
        self.assertIn("UEFI_LD", self.run_script("kernel-uefi-build.sh",
            env={"UEFI_LD": "no-such-linker"}, expected=2))
        self.tool("elf-only", 'printf "Supported emulations:\n elf_x86_64\n"\n')
        self.run_script("kernel-uefi-build.sh", env={"UEFI_LD": "elf-only"}, expected=2)
        self.assert_no_work()

    def test_uefi_cross_linker_fallback_and_explicit_path(self):
        self.tool("ld", 'printf "Supported emulations:\n elf_x86_64\n"\n')
        self.tool("x86_64-w64-mingw32-ld", 'printf "Supported emulations:\n i386pep\n"\n')
        self.run_script("kernel-uefi-build.sh", env={"FAKE_STATUS": "79"}, expected=79)
        chosen = str(self.tool("selected PE linker", 'printf "Supported emulations:\n i386pep\n"\n'))
        self.run_script("kernel-uefi-build.sh", env={"UEFI_LD": chosen, "FAKE_STATUS": "79"}, expected=79)
        self.assertEqual(len(self.calls()), 2)

    def test_image_builders_export_selected_cxx_to_compiler_make(self):
        cxx = str(self.tool("g++-16", "exit 93\n"))
        (self.bin / "g++").unlink()
        for name in ("kernel-build.sh", "kernel-uefi-build.sh"):
            self.run_script(name, env={"CXX": cxx, "FAKE_STATUS": "79"}, expected=79)
        self.assertEqual(self.calls(), [f"make|{self.repo}|-C compiler|{cxx}|", f"make|{self.repo}|-C compiler|{cxx}|"])
        # This is a source-routing assertion, not proof of a successful build.
        for name, count in (("kernel-build.sh", 1), ("kernel-uefi-build.sh", 5)):
            source = (self.scripts / name).read_text()
            self.assertNotIn("\ng++ ", source)
            self.assertEqual(source.count('\n"$cxx" '), count)

    def test_make_help_and_run_selectors(self):
        self.assertIsNotNone(MAKE)
        result = subprocess.run([MAKE, "help"], cwd=self.repo, env=self.env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("make run-uefi", result.stdout)
        self.assert_no_work()
        firmware = self.firmware()
        qemu = str(self.tool("alternate qemu", "exit 93\n"))
        data = self.home / "make qemu data"
        data.mkdir()
        result = subprocess.run([MAKE, "run-uefi", "CXX=g++-16", "QEMU=" + qemu, "OVMF=" + firmware, "QEMU_DATA=" + str(data)],
                                cwd=self.repo, env=self.env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.calls(), [f"uefi|{self.repo}|normal|g++-16|{qemu}|{firmware}|{data}"])

    def test_host_check_routes_existing_gates_with_selected_tools(self):
        cxx = str(self.tool("selected-cxx", 'echo "selected C++"\n'))
        self.tool("as", 'echo "selected assembler"\n')
        pe = str(self.tool("selected PE", 'printf "Supported emulations:\n i386pep\n"\n'))
        self.run_script("host-build-check.sh", env={"CXX": cxx, "UEFI_LD": pe})
        self.assertEqual([line.split("|")[2] for line in self.calls()],
                         ["-C compiler --always-make", "kernel", "kernel-uefi", "test-uefi", "test-developer-commands"])
        self.assertTrue(all(line.split("|")[3] == cxx for line in self.calls()))

    def test_host_check_stops_on_first_failed_gate(self):
        self.tool("g++", 'echo "selected C++"\n'); self.tool("as", 'echo "assembler"\n')
        self.run_script("host-build-check.sh", env={"FAKE_STATUS": "79"}, expected=79)
        self.assertEqual(len(self.calls()), 1)

    def test_host_check_rejects_pins_faults_and_make_bypasses(self):
        for name, value in (("AURORAC", "/stale/aurorac"), ("OUT", "/another/compiler"),
                            ("MAKEFLAGS", "n"), ("MFLAGS", "-i"), ("GNUMAKEFLAGS", "-n"),
                            ("MAKEFILES", "injected.mk"), ("MAKEOVERRIDES", "CXX=other"),
                            ("KERNEL_TEST_FAULT", "1"), ("KERNEL_USER_PROBE_MODE", "1"),
                            ("KERNEL_CONSOLE", "1"), ("KERNEL_CONSOLE", "0"),
                            ("UEFI_MODE", "bad-table")):
            with self.subTest(name=name):
                self.assertIn("Unset " + name, self.run_script("host-build-check.sh", env={name: value}, expected=2))
        self.assert_no_work()

    def test_host_check_missing_linker_or_active_context_starts_no_build(self):
        self.run_script("host-build-check.sh", env={"UEFI_LD": "missing-linker"}, expected=2)
        self.run_script("host-build-check.sh", env={"AURORA_TEST_CONTEXT": "active"}, expected=2)
        self.run_script("host-build-check.sh", "unexpected", expected=2)
        self.assert_no_work()

    def test_direct_shortcuts_reject_inherited_context_before_work(self):
        env = {"AURORA_TEST_CONTEXT": "/invalid/context.json", "AURORAC": "/selected/aurorac"}
        for name, args in (("kernel-run.sh", ("bios",)), ("kernel-run.sh", ("uefi",)),
                           ("compiler-test.sh", ())):
            output = self.run_script(name, *args, env=env, expected=2)
            self.assertIn("rejects inherited AURORA_TEST_CONTEXT", output)
        self.assert_no_work()

    def test_make_invalid_context_is_checked_before_runner_or_builder(self):
        # The checker is mocked to reject. Any runner/build call adds an extra
        # record (or creates build/) and fails this test. No real receipt or
        # compiler is synthesized and no native-acceptance credit is claimed.
        self.tool("python3", 'printf "context-check|%s|%s|%s\\n" "$*" "${AURORA_TEST_CONTEXT-}" "${AURORAC-}" >> "$CALLS"\nexit 79\n')
        env = self.env | {"AURORA_TEST_CONTEXT": "/invalid/context.json", "AURORAC": "/selected/aurorac"}
        for goal in ("test-nvme-queues", "smoke-nvme-prepare", "run", "run-uefi", "kernel-uefi"):
            result = subprocess.run([MAKE, goal], cwd=self.repo, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            calls = self.calls()
            self.assertEqual(len(calls), 1, calls)
            self.assertTrue(calls[0].startswith("context-check|-B scripts/compiler_contract.py check --repo-root "), calls)
            self.assertTrue(calls[0].endswith("|/invalid/context.json|/selected/aurorac"), calls)
            self.assertFalse((self.repo / "build").exists())
            self.record.unlink()

    def test_make_build_and_test_aliases_are_only_printed(self):
        for argv, expected in ((["-n", "kernel-uefi", "-o", "compiler"], "./scripts/kernel-uefi-build.sh"),
                               (["-n", "test-compiler"], '--entry root --goal "test-compiler"')):
            result = subprocess.run([MAKE, *argv], cwd=self.repo, env=self.env,
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn(expected, result.stdout)
        self.assert_no_work()


if __name__ == "__main__":
    unittest.main()

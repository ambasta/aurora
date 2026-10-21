#!/usr/bin/env python3
"""Synthetic command-routing checks; never build Aurora or start real QEMU.

Each case copies only entry scripts/Makefile into a temporary fixture. Fake tools
record argv/environment or fail immediately. This does not establish compiler,
native aggregate, firmware or emulator acceptance.
"""

from pathlib import Path
import json
import os
import re
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
        self.env = {"PATH": str(self.bin), "HOME": str(self.home), "CALLS": str(self.record), "LC_ALL": "C"}
        for name in (
            "kernel-run.sh",
            "compiler-test.sh",
            "container.sh",
            "kernel-build.sh",
            "kernel-uefi-build.sh",
            "uefi-firmware.sh",
            "uefi-linker.sh",
            "host-build-check.sh",
            "qemu_transport.py",
            "kernel_profiles.py",
            "kernel_layout.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        for relative in (
            "kernel/bootstrap-layout-values.inc",
            "kernel/uefi/image-page-policies.inc",
            "kernel/uefi/runtime-fixtures.inc",
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        shutil.copy2(ROOT / "Makefile", self.repo / "Makefile")
        (self.repo / "compiler").mkdir()
        shutil.copy2(ROOT / "compiler/Makefile", self.repo / "compiler/Makefile")
        shutil.copy2(ROOT / "scripts/kernel-console.sh", self.scripts / "kernel-console.sh")
        for name in ("kernel-uefi-console.sh", "kernel_uefi_console_clock.py", "kernel_emulator_clock.py"):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        for name in ("bash", "dirname", "cat", "mkdir", "printf"):
            resolved = shutil.which(name)
            self.assertIsNotNone(resolved, name)
            (self.bin / name).symlink_to(resolved)
        for name in (
            "qemu-system-x86_64",
            "timeout",
            "g++",
            "python3",
            "as",
            "ld",
            "objcopy",
            "objdump",
            "nm",
            "readelf",
        ):
            self.tool(name, "exit 93\n")
        self.tool("ld", 'printf "Supported emulations:\n i386pep\n"\n')
        self.tool(
            "make",
            'printf "make|%s|%s|%s|%s\\n" "$PWD" "$*" "${CXX-}" "${CXXFLAGS-}" >> "$CALLS"\nexit "${FAKE_STATUS:-0}"\n',
        )
        for name, label in (("kernel-smoke.sh", "bios"), ("kernel-uefi-smoke.sh", "uefi")):
            self.script(
                self.scripts / name,
                'printf "%s|%s|%s|%s|%s|%s|%s\\n" "'
                + label
                + '" "$PWD" "$*" "${CXX-}" "${QEMU-}" "${OVMF-}" "${QEMU_DATA-}" >> "$CALLS"\n'
                'exit "${FAKE_STATUS:-0}"\n',
            )

    def script(self, path, body):
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def tool(self, name, body):
        self.script(self.bin / name, body)
        return self.bin / name

    def run_script(self, name, *args, env=None, expected=0):
        current = self.env | (env or {})
        result = subprocess.run(
            [BASH, str(self.scripts / name), *args],
            cwd=self.home,
            env=current,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
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

    def container_engine(self, name, version):
        image = "ghcr.io/ambasta/aurora-toolchain@sha256:" + "a" * 64
        (self.repo / "ci").mkdir(exist_ok=True)
        (self.repo / "ci/image").write_text(image + "\n")
        self.tool("id", 'if [[ "$1" == -u ]]; then echo 1234; else echo 5678; fi\n')
        self.tool(
            name,
            'if [[ "$1" == --version ]]; then printf "%s\\n" "'
            + version
            + '"; exit 0; fi\n'
            + 'printf "%s\\n" "'
            + name
            + '" "$@" > "$CALLS"\nexit "${FAKE_STATUS:-0}"\n',
        )
        return image

    def test_container_selects_runtime_identity_and_preserves_arguments(self):
        for engine, version, identity in (
            ("docker", "Docker version 28.0.0, build synthetic", ["--user", "1234:5678"]),
            ("podman", "podman version 5.4.0", ["--userns=keep-id"]),
            ("docker", "Emulate Docker CLI using podman. podman version 5.4.0", ["--userns=keep-id"]),
        ):
            with self.subTest(engine=engine, version=version):
                for name in ("docker", "podman"):
                    (self.bin / name).unlink(missing_ok=True)
                image = self.container_engine(engine, version)
                # Keep Docker selection stable when both engines are installed.
                if engine == "docker":
                    self.tool("podman", 'echo unexpected-podman >> "$CALLS"; exit 93\n')
                self.run_script("container.sh", "make", "argument with spaces", "literal;not-a-command")
                args = self.calls()
                self.assertEqual(args[:2], [engine, "run"])
                self.assertEqual(args[-4:], [image, "make", "argument with spaces", "literal;not-a-command"])
                for flag in ("--rm", "--init", "--read-only", "--cap-drop", "ALL", "no-new-privileges", "-i"):
                    self.assertIn(flag, args)
                self.assertIn("type=bind,source=" + str(self.repo) + ",target=/workspace", args)
                self.assertEqual(args[args.index("--network") + 1], "none")
                self.assertEqual(args[args.index("--platform") + 1], "linux/amd64")
                self.assertNotIn("-t", args)
                for flag in identity:
                    self.assertIn(flag, args)
                self.assertEqual("--user" in args, identity[0] == "--user")
                self.assertEqual("--userns=keep-id" in args, identity[0] == "--userns=keep-id")

    def test_container_default_command_and_runtime_failure(self):
        self.container_engine("podman", "podman version 5.4.0")
        self.run_script("container.sh", env={"FAKE_STATUS": "19"}, expected=19)
        self.assertEqual(self.calls()[-1], "bash")

    def test_container_forwards_only_set_build_controls_as_literal_arguments(self):
        self.container_engine("docker", "Docker version 28.0.0")
        controls = {
            "MESON_BUILD_DIR": "build/path with spaces;$(do-not-execute)",
            "BOOTSTRAP_COMPILER": "/workspace/build/predecessor with spaces;literal",
            "BOOTSTRAP_COMPILER_SHA256": "1" * 64,
            "BOOTSTRAP_RECEIPT": "/workspace/build/receipt with spaces;literal.json",
            "AURORA_BUILD_JOBS": "2",
            "AURORA_TEST_JOBS": "",
        }
        self.run_script("container.sh", "make", "test", env=controls | {"CXX": "/host/compiler", "UNRELATED": "secret"})
        args = self.calls()
        self.assertEqual(
            [args[index + 1] for index, value in enumerate(args) if value == "--env"],
            ["HOME=/tmp", *[name + "=" + value for name, value in controls.items()]],
        )
        self.assertNotIn("/host/compiler", args)
        self.assertNotIn("secret", args)
        self.run_script("container.sh", "make", "test")
        args = self.calls()
        self.assertEqual([args[index + 1] for index, value in enumerate(args) if value == "--env"], ["HOME=/tmp"])

    def test_container_blocks_missing_unknown_or_failed_engine_without_run(self):
        self.container_engine("docker", "unrecognized container engine")
        self.assertIn("BLOCKED: Unrecognized docker", self.run_script("container.sh", expected=2))
        self.assert_no_work()
        self.tool("docker", "echo unavailable >&2; exit 17\n")
        self.assertIn("BLOCKED: Cannot identify docker: unavailable", self.run_script("container.sh", expected=2))
        self.assert_no_work()
        (self.bin / "docker").unlink()
        self.assertIn("BLOCKED: Docker or Podman is required", self.run_script("container.sh", expected=2))
        self.assert_no_work()

    def test_container_help_and_invalid_pin_do_not_query_engine(self):
        self.assertIn("Docker or Podman", self.run_script("container.sh", "--help"))
        self.container_engine("docker", "Docker version 28.0.0")
        (self.repo / "ci/image").write_text("unreviewed:latest\n")
        self.tool("docker", 'echo unexpected-engine >> "$CALLS"; exit 93\n')
        self.assertIn("BLOCKED: ci/image", self.run_script("container.sh", expected=2))
        self.assert_no_work()

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

    def test_specialized_routes_preserve_adapter_arguments_and_failures(self):
        self.tool("python3", 'printf "python|%s\\n" "$*" >> "$CALLS"\nexit "${FAKE_STATUS:-0}"\n')
        for mode in ("bar-read", "ivrs-read"):
            self.run_script(
                "kernel-run.sh",
                mode,
                "--smoke",
                "--output",
                "/fresh output",
                "--run-only",
                "/native image",
                env={"FAKE_STATUS": "17"},
                expected=17,
            )
            self.assertEqual(
                self.calls()[-1],
                f"python|scripts/kernel-uefi-{mode.split('-')[0]}-run.py "
                f"{mode} --output /fresh output --run-only /native image",
            )
        firmware = self.firmware()
        self.run_script("kernel-run.sh", "iommu-event", env={"OVMF": firmware})
        self.assertEqual(
            self.calls()[-1],
            f"python|-B scripts/kernel_iommu_event_smoke.py --normal-firmware {firmware} --normal-code  --normal-vars ",
        )
        self.run_script("kernel-run.sh", "iommu-event", "--build-only", env={"OVMF": "/missing.fd"})
        self.assertEqual(self.calls()[-1], "python|-B scripts/kernel_iommu_event_smoke.py --build-only")

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
            self.script(
                self.scripts / name,
                'path="$PWD/build/config/kernel-images/'
                + ("uefi" if "uefi" in name else "bios")
                + '/normal"; mkdir -p "$path"; printf "{}" > "$path/user-metadata.json"; printf "%s\\n" "$path"\n',
            )
        # Clock selection and full argv binding must use the real helper. Only
        # the normal serial validators are synthetic in this routing fixture.
        shutil.copy2(ROOT / "scripts/kernel_emulator_clock.py", self.scripts / "kernel_emulator_clock.py")
        self.env["REAL_PYTHON"] = sys.executable
        self.tool(
            "python3",
            'if [ "$1" = -B ]; then shift; fi\n'
            'case "$1" in\n'
            '  scripts/meson_test.py) path="$PWD/build/config/kernel-images/$3/normal"; '
            'mkdir -p "$path"; printf "{}" > "$path/user-metadata.json"; printf "%s\\n" "$path" ;;\n'
            "  scripts/kernel_emulator_clock.py|scripts/qemu_transport.py|scripts/kernel_profiles.py) "
            'exec "$REAL_PYTHON" -B "$@" ;;\n'
            "  tests/kernel-smoke.py|tests/kernel-uefi-smoke.py) exit 0 ;;\n"
            '  *) echo "Unexpected Python command in terminal fixture" >&2; exit 93 ;;\n'
            "esac\n",
        )
        self.tool(
            "qemu-system-x86_64",
            "if [ -t 0 ]; then state=terminal; else state=detached; fi\n"
            'printf "qemu|stdin-%s\\n" "$state" >> "$CALLS"\n'
            "exit 33\n",
        )
        for name, arguments in (
            ("kernel-smoke.sh", []),
            ("kernel-uefi-smoke.sh", []),
            ("kernel-uefi-smoke.sh", ["--shared-normal", "normal"]),
        ):
            leader, follower = os.openpty()
            self.addCleanup(os.close, leader)
            try:
                self.assertTrue(os.isatty(follower))
                result = subprocess.run(
                    [BASH, str(self.scripts / name), *arguments],
                    cwd=self.home,
                    env=self.env | {"OVMF": self.firmware()},
                    stdin=follower,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=10,
                )
            finally:
                os.close(follower)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("PASS:", result.stdout)
        self.assertEqual(self.calls(), ["qemu|stdin-detached"] * 3)
        self.assertFalse((self.repo / "build/uefi").exists())
        receipt = json.loads((self.repo / "build/config/kernel-images/uefi/normal/normal.clock.json").read_text())
        self.assertEqual(receipt["clock_profile"], "tcg-original-clock")
        self.assertNotIn("-icount", receipt["argv"])
        self.assertEqual(receipt["timeout_argv"], ["timeout", "30", *receipt["argv"]])
        self.assertEqual(receipt["execution_status"], "not-established-by-command-receipt")

    def test_fault_environment_is_rejected_before_dispatch(self):
        for name in (
            "KERNEL_TEST_DIVISION",
            "KERNEL_TEST_FUTURE_MODE",
            "KERNEL_USER_PROBE_MODE",
            "KERNEL_CONSOLE",
            "UEFI_MODE",
        ):
            output = self.run_script("kernel-run.sh", env={name: "1"}, expected=2)
            self.assertIn("Unset " + name, output)
        self.assert_no_work()

    def test_console_launcher_is_foreground_bounded_and_preserves_status(self):
        self.script(
            self.scripts / "kernel-build.sh",
            'printf "build|%s\\n" "$KERNEL_CONSOLE" >> "$CALLS"\nprintf "%s\\n" "$PWD/native bios"\n',
        )
        self.env["REAL_PYTHON"] = sys.executable
        self.tool("python3", 'exec "$REAL_PYTHON" -B "$@"\n')
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
        self.script(
            self.scripts / "kernel-uefi-build.sh",
            'mkdir -p "build/native uefi"\nprintf "build|%s\\n" "$UEFI_MODE" >> "$CALLS"\n'
            'printf "%s\\n" "$PWD/build/native uefi"\n',
        )
        self.env["REAL_PYTHON"] = sys.executable
        self.tool("python3", 'exec "$REAL_PYTHON" -B "$@"\n')
        self.tool("timeout", 'printf "timeout|%s\\n" "$*" >> "$CALLS"\nexit "$FAKE_STATUS"\n')
        firmware = self.firmware()
        for status, expected in ((33, 0), (35, 35), (124, 124)):
            self.run_script(
                "kernel-uefi-console.sh", env={"FAKE_STATUS": str(status), "OVMF": firmware}, expected=expected
            )
        self.assertEqual(len(self.calls()), 6)
        for build, command in zip(self.calls()[::2], self.calls()[1::2]):
            self.assertEqual(build, "build|console")
            self.assertTrue(command.startswith("timeout|--foreground --kill-after=2 300 qemu-system-x86_64 "))
            self.assertIn("-machine q35 -accel tcg", command)
            self.assertNotIn("-icount", command)
        receipt = json.loads((self.repo / "build/native uefi/console.clock.json").read_text())
        self.assertEqual(receipt["clock_profile"], "tcg-original-clock")
        self.assertEqual(receipt["command_template"], "normal")
        self.assertEqual(receipt["execution_status"], "not-established-by-command-receipt")

    def test_uefi_console_rejects_mixed_controls_before_build(self):
        for name in (
            "KERNEL_TEST_SCHEDULE",
            "KERNEL_USER_PROBE_MODE",
            "KERNEL_CONSOLE",
            "UEFI_MODE",
            "UEFI_CONSOLE_HANDOFF",
            "AURORA_TEST_CONTEXT",
        ):
            self.run_script("kernel-uefi-console.sh", env={name: "1"}, expected=2)
        self.run_script("kernel-uefi-console.sh", "extra", expected=2)
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
        self.assertIn(
            "combined OVMF.fd",
            self.run_script("kernel-run.sh", "uefi", env={"OVMF": str(self.home / "missing.fd")}, expected=2),
        )
        self.assertIn(
            "combined OVMF.fd", self.run_script("kernel-run.sh", "uefi", env={"OVMF": str(self.home)}, expected=2)
        )
        self.assertIn(
            "QEMU_DATA",
            self.run_script("kernel-run.sh", env={"QEMU_DATA": str(self.home / "missing-data")}, expected=2),
        )
        self.assert_no_work()

    def test_compiler_route_preserves_controls_and_failure(self):
        cxx = str(self.tool("g++-16", "exit 93\n"))
        flags = "-std=c++23 -O2 -Wall -Wextra -Werror"
        self.run_script("compiler-test.sh", env={"CXX": cxx, "CXXFLAGS": flags, "FAKE_STATUS": "19"}, expected=19)
        self.assertEqual(self.calls(), [f"make|{self.repo}|-C compiler test|{cxx}|{flags}"])

    def test_compiler_missing_tool_has_no_work(self):
        self.run_script("compiler-test.sh", env={"CXX": "no-such-compiler"}, expected=2)
        self.assert_no_work()

    def test_compiler_make_build_and_suite_routes_use_only_meson(self):
        self.tool(
            "python3",
            'printf "meson|%s|%s|%s|%s\\n" "$*" "${CXX-}" "${CXXFLAGS-}" "${MESON_BUILD_DIR-}" >> "$CALLS"\n'
            'exit "${FAKE_STATUS:-0}"\n',
        )
        routes = (
            ([], "--build-only aurorac --publish-compiler"),
            (["all"], "--build-only aurorac --publish-compiler"),
            (["formatter"], "--build-only aurora-fmt --publish-formatter"),
            (["test"], "--suite compiler"),
        )
        controls = {"CXX": "g++-16", "CXXFLAGS": "-std=c++23 -O2 -DCOUNT=7", "MESON_BUILD_DIR": "build/chosen"}
        for goals, selection in routes:
            for status in (0, 19):
                with self.subTest(goals=goals, status=status):
                    result = subprocess.run(
                        [MAKE, *goals],
                        cwd=self.repo / "compiler",
                        env=self.env | controls | {"FAKE_STATUS": str(status)},
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(result.returncode == 0, status == 0, result.stdout + result.stderr)
                    self.assertEqual(
                        self.calls(),
                        [
                            f"meson|-B ../scripts/meson_test.py --repo-root {self.repo} {selection}|"
                            "g++-16|-std=c++23 -O2 -DCOUNT=7|build/chosen"
                        ],
                    )
                    self.assertFalse((self.repo / "build").exists())
                    self.record.unlink()

    def test_removed_compiler_aliases_do_not_dispatch(self):
        for directory, goals in (
            (self.repo, ("test-compiler", "test-formatter", "test-lint")),
            (self.repo / "compiler", ("test-modules", "test-short-circuit", "test-formatter", "test-lint")),
        ):
            for goal in goals:
                with self.subTest(directory=directory.name, goal=goal):
                    result = subprocess.run(
                        [MAKE, goal], cwd=directory, env=self.env, capture_output=True, text=True, timeout=5
                    )
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("No rule to make target", result.stderr)
                    self.assert_no_work()

    def test_make_host_checks_call_scripts_directly(self):
        routes = {
            "test-pin-ledger": "kernel-pin-tests.sh",
            "test-uefi-pins": "kernel-uefi-pin-tests.sh",
            "test-nvme-queues": "kernel-nvme-queue-tests.sh",
            "test-uefi-bar": "kernel-uefi-bar-tests.sh",
            "test-dormant-tables": "kernel-dormant-tests.sh",
            "test-uefi-tables": "kernel-uefi-tables-tests.sh",
            "test-program-stream": "kernel-program-tests.sh",
        }
        for target, script in routes.items():
            self.script(self.scripts / script, 'printf "%s\\n" "' + script + '" >> "$CALLS"\n')
        result = subprocess.run([MAKE, *routes], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), list(routes.values()))
        self.assertFalse((self.repo / "build").exists())

    def test_make_preserves_ordinary_options_and_custom_shell(self):
        self.tool("python3", 'printf "forward|%s\\n" "$*" >> "$CALLS"\nexit "${FAKE_STATUS:-0}"\n')
        extra = self.home / "extra.mk"
        extra.write_text("HARMLESS_EXTRA := yes\n")
        for directory in (self.repo, self.repo / "compiler"):
            for arguments, status, expected, dispatched in (
                (["-i"], 19, 0, True),
                (["-q"], 0, 1, False),
                (["-t"], 0, 0, False),
                (["-e"], 0, 0, True),
                (["SHELL=" + str(self.bin / "bash")], 0, 0, True),
            ):
                with self.subTest(directory=directory.name, arguments=arguments):
                    result = subprocess.run(
                        [MAKE, *arguments, "test"],
                        cwd=directory,
                        env=self.env | {"FAKE_STATUS": str(status), "MAKEFILES": str(extra)},
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    self.assertEqual(len(self.calls()), int(dispatched))
                    self.assertFalse((self.repo / "build").exists())
                    self.record.unlink(missing_ok=True)

    def test_make_uefi_routes_to_native_image_without_legacy_build(self):
        self.tool("python3", 'printf "native|%s\\n" "$*" >> "$CALLS"\nexit 79\n')
        result = subprocess.run(
            [MAKE, "kernel-uefi"], cwd=self.repo, env=self.env, text=True, capture_output=True, timeout=5
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [f"native|-B scripts/meson_test.py --repo-root {self.repo} --kernel uefi"])
        self.assertFalse((self.repo / "build").exists())

    def test_image_builders_route_exact_selected_profiles_and_status(self):
        self.env["REAL_PYTHON"] = sys.executable
        self.tool(
            "python3",
            'if [[ "$2" == scripts/kernel_profiles.py ]]; then exec "$REAL_PYTHON" "$@"; fi\n'
            'printf "native|%s|%s|%s|%s\\n" "$*" "${CXX-}" "${AURORAC-}" "${UEFI_LD-}" >> "$CALLS"\n'
            'exit "${FAKE_STATUS:-0}"\n',
        )
        for name, platform, controls, profile in (
            ("kernel-build.sh", "bios", {}, "normal"),
            ("kernel-build.sh", "bios", {"KERNEL_CONSOLE": "1"}, "console"),
            ("kernel-build.sh", "bios", {"KERNEL_TEST_SCHEDULE": "1", "KERNEL_TEST_PROGRAM_FPU": "1"}, "schedule-fpu"),
            ("kernel-build.sh", "bios", {"KERNEL_TEST_DIVISION": "overflow"}, "division-overflow"),
            ("kernel-uefi-build.sh", "uefi", {}, "normal"),
            ("kernel-uefi-build.sh", "uefi", {"UEFI_MODE": "graphical-console"}, "graphical-console"),
            ("kernel-uefi-build.sh", "uefi", {"UEFI_MODE": "program-owner"}, "program-owner"),
        ):
            for status in (0, 19):
                with self.subTest(name=name, profile=profile, status=status):
                    env = controls | {
                        "CXX": "/chosen cxx",
                        "AURORAC": "/chosen aurorac",
                        "UEFI_LD": "/chosen ld",
                        "FAKE_STATUS": str(status),
                    }
                    self.run_script(name, "--print-image-dir", env=env, expected=status)
                    self.assertEqual(
                        self.calls()[-1],
                        f"native|-B scripts/meson_test.py --kernel {platform} --profile {profile} "
                        "--print-image-dir|/chosen cxx|/chosen aurorac|/chosen ld",
                    )
        self.assertFalse((self.repo / "build").exists())
        for name in ("kernel-build.sh", "kernel-uefi-build.sh"):
            source = (self.scripts / name).read_text()
            for legacy in ("make -C compiler", "rm -f", " -c ", "objcopy", "end-build"):
                self.assertNotIn(legacy, source)

    def test_image_builder_rejects_unknown_mixed_and_extra_controls(self):
        self.env["REAL_PYTHON"] = sys.executable
        self.tool(
            "python3",
            'if [[ "$2" == scripts/kernel_profiles.py ]]; then exec "$REAL_PYTHON" "$@"; fi\n'
            'echo unexpected-native >> "$CALLS"; exit 93\n',
        )
        for name, controls in (
            ("kernel-build.sh", {"KERNEL_TEST_FUTURE": "1"}),
            ("kernel-build.sh", {"KERNEL_TEST_WP": "1", "KERNEL_TEST_NX": "1"}),
            ("kernel-build.sh", {"KERNEL_CONSOLE": "1", "KERNEL_TEST_SCHEDULE": "1"}),
            ("kernel-uefi-build.sh", {"UEFI_MODE": "future"}),
            ("kernel-uefi-build.sh", {"KERNEL_TEST_WP": "1"}),
        ):
            self.run_script(name, env=controls, expected=2)
        for name in ("kernel-build.sh", "kernel-uefi-build.sh"):
            self.run_script(name, "--unexpected", expected=2)
            self.run_script(name, "--print-image-dir", "extra", expected=2)
        self.assert_no_work()

    def test_make_help_and_run_selectors(self):
        self.assertIsNotNone(MAKE)
        result = subprocess.run(
            [MAKE, "help"],
            cwd=self.repo,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("make run-uefi", result.stdout)
        self.assert_no_work()
        firmware = self.firmware()
        qemu = str(self.tool("alternate qemu", "exit 93\n"))
        data = self.home / "make qemu data"
        data.mkdir()
        result = subprocess.run(
            [MAKE, "run-uefi", "CXX=g++-16", "QEMU=" + qemu, "OVMF=" + firmware, "QEMU_DATA=" + str(data)],
            cwd=self.repo,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.calls(), [f"uefi|{self.repo}|normal|g++-16|{qemu}|{firmware}|{data}"])

    def test_host_check_routes_existing_gates_with_selected_tools(self):
        cxx = str(self.tool("selected-cxx", 'echo "selected C++"\n'))
        self.tool("as", 'echo "selected assembler"\n')
        pe = str(self.tool("selected PE", 'printf "Supported emulations:\n i386pep\n"\n'))
        self.run_script("host-build-check.sh", env={"CXX": cxx, "UEFI_LD": pe})
        self.assertEqual(
            [line.split("|")[2] for line in self.calls()],
            ["-C compiler --always-make", "kernel", "kernel-uefi", "test-uefi", "test-developer-commands"],
        )
        self.assertTrue(all(line.split("|")[3] == cxx for line in self.calls()))

    def test_host_check_stops_on_first_failed_gate(self):
        self.tool("g++", 'echo "selected C++"\n')
        self.tool("as", 'echo "assembler"\n')
        self.run_script("host-build-check.sh", env={"FAKE_STATUS": "79"}, expected=79)
        self.assertEqual(len(self.calls()), 1)

    def test_host_check_rejects_pins_faults_and_make_bypasses(self):
        for name, value in (
            ("AURORAC", "/stale/aurorac"),
            ("OUT", "/another/compiler"),
            ("MAKEFLAGS", "n"),
            ("MFLAGS", "-i"),
            ("GNUMAKEFLAGS", "-n"),
            ("MAKEFILES", "injected.mk"),
            ("MAKEOVERRIDES", "CXX=other"),
            ("KERNEL_TEST_FAULT", "1"),
            ("KERNEL_USER_PROBE_MODE", "1"),
            ("KERNEL_CONSOLE", "1"),
            ("KERNEL_CONSOLE", "0"),
            ("UEFI_MODE", "bad-table"),
        ):
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
        for name, args in (("kernel-run.sh", ("bios",)), ("kernel-run.sh", ("uefi",)), ("compiler-test.sh", ())):
            output = self.run_script(name, *args, env=env, expected=2)
            self.assertIn("rejects inherited AURORA_TEST_CONTEXT", output)
        self.assert_no_work()

    def test_make_build_and_test_aliases_are_only_printed(self):
        for argv, expected in (
            (["-n", "kernel-uefi", "-o", "compiler"], "--kernel uefi"),
            (["-n", "test"], "scripts/meson_test.py --repo-root"),
        ):
            result = subprocess.run(
                [MAKE, *argv],
                cwd=self.repo,
                env=self.env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=5,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn(expected, result.stdout)
        self.assert_no_work()


if __name__ == "__main__":
    unittest.main()

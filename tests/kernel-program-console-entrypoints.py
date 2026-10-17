#!/usr/bin/env python3
"""Synthetic native-admission routing; no compiler or guest executes."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
MAKE = shutil.which("make")


class Entrypoints(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="program-console-routing-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.repo = self.home / "repo"
        self.scripts = self.repo / "scripts"
        self.scripts.mkdir(parents=True)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.log = self.home / "calls"
        self.env = {
            "PATH": str(self.bin),
            "HOME": str(self.home),
            "CALLS": str(self.log),
            "LC_ALL": "C",
            "REAL_PYTHON": sys.executable,
        }
        for name in (
            "kernel-program-console.sh",
            "kernel-program-console-smoke.sh",
            "kernel-run.sh",
            "uefi-firmware.sh",
            "uefi-linker.sh",
            "qemu_transport.py",
        ):
            shutil.copy2(ROOT / "scripts" / name, self.scripts / name)
        shutil.copy2(ROOT / "Makefile", self.repo / "Makefile")
        for name in ("bash", "dirname", "mkdir", "cat"):
            (self.bin / name).symlink_to(shutil.which(name))
        for name in ("qemu-system-x86_64", "g++", "make", "as", "ld", "objcopy", "nm", "objdump", "readelf"):
            self.script(self.bin / name, 'echo unexpected-tool >> "$CALLS"; exit 93\n')
        self.script(self.bin / "ld", 'printf "Supported emulations:\n i386pep\n"\n')
        self.script(self.bin / "timeout", 'echo guest >> "$CALLS"; exit "${GUEST_STATUS:-33}"\n')
        self.script(
            self.bin / "python3",
            """
case "$*" in
    "-B scripts/qemu_transport.py "*) exec "$REAL_PYTHON" "$@" ;;
    "-B scripts/kernel_program_console_admission.py checked --mode "*)
        echo checked >> "$CALLS"; exit "${CHECK_STATUS:-0}" ;;
    "-B tests/kernel-program-console-pty.py "*)
        echo "pty|$*" >> "$CALLS"
        case "$*" in *--read-only-recovery) exit "${READ_PTY_STATUS:-0}" ;; esac
        exit "${PTY_STATUS:-0}" ;;
    "-B scripts/kernel_uefi_console_clock.py "*)
        echo clock >> "$CALLS"; exit 0 ;;
    *) echo unexpected-python >> "$CALLS"; exit 93 ;;
esac
""",
        )
        self.script(
            self.scripts / "kernel-uefi-build.sh",
            """
echo "build|$UEFI_MODE" >> "$CALLS"
mkdir -p "build/native profiles/$UEFI_MODE"
printf '%s\\n' "$PWD/build/native profiles/$UEFI_MODE"
exit "${BUILD_STATUS:-0}"
""",
        )
        firmware = self.home / "firmware.fd"
        firmware.write_bytes(b"synthetic firmware, never executed")
        self.env["OVMF"] = str(firmware)

    def script(self, path, body):
        path.write_text("#!/bin/bash\nset -eu\n" + body)
        path.chmod(0o755)

    def run_script(self, name="kernel-program-console-smoke.sh", args=(), env=None, expected=0):
        result = subprocess.run(
            [BASH, str(self.scripts / name), *args],
            cwd=self.repo,
            env=self.env | (env or {}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        self.assertEqual(result.returncode, expected, result.stdout)
        return result.stdout

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def clear(self):
        self.log.unlink(missing_ok=True)

    def test_profile_builder_delegates_to_canonical_graph(self):
        script = (ROOT / "scripts/kernel-uefi-build.sh").read_text()
        self.assertIn("scripts/kernel_profiles.py --select uefi", script)
        self.assertIn('scripts/meson_test.py --kernel uefi --profile "$profile"', script)
        self.assertNotIn("make -C compiler", script)

    def test_public_smoke_builds_isolated_profile(self):
        for mode in (
            "program-console",
            "program-request-fault",
            "program-service-fault",
            "program-completion-fault",
            "program-request-budget",
            "program-service-budget",
            "program-completion-budget",
            "program-pending",
            "program-owner",
            "program-ordinal",
            "program-unknown",
            "program-transaction",
        ):
            self.run_script(args=(mode,))
            self.assertEqual(
                self.calls(),
                [
                    f"build|{mode}",
                    f"pty|-B tests/kernel-program-console-pty.py --mode {mode} "
                    f"--build-dir {self.repo}/build/native profiles/{mode}",
                ]
                + (
                    [
                        f"pty|-B tests/kernel-program-console-pty.py --mode {mode} "
                        f"--build-dir {self.repo}/build/native profiles/{mode} --read-only-recovery"
                    ]
                    if mode.endswith(("-fault", "-budget"))
                    else []
                ),
            )
            self.clear()

    def test_read_only_recovery_failure_is_not_a_pass(self):
        self.run_script(args=("program-service-fault",), env={"READ_PTY_STATUS": "7"}, expected=7)
        self.assertEqual(len(self.calls()), 3)
        self.assertTrue(self.calls()[-1].endswith("--read-only-recovery"))

    def test_public_launch_rebuilds_checks_and_starts_original_clock(self):
        self.run_script(name="kernel-program-console.sh")
        self.assertEqual(self.calls(), ["build|program-console", "checked", "clock", "guest"])
        self.clear()
        self.run_script(name="kernel-program-console.sh", env={"GUEST_STATUS": "0"}, expected=1)
        self.assertEqual(self.calls()[-1], "guest")

    def test_shared_entrypoint_preserves_protected_launch_statuses(self):
        for status, expected in ((33, 0), (0, 1), (35, 35), (124, 124), (137, 137)):
            self.run_script(
                name="kernel-run.sh",
                args=("program-console", "--console"),
                env={"GUEST_STATUS": str(status)},
                expected=expected,
            )
            self.assertEqual(self.calls(), ["build|program-console", "checked", "clock", "guest"])
            self.clear()

    def test_shared_entrypoint_defaults_to_protected_smoke_and_rejects_interactive_faults(self):
        self.run_script(name="kernel-run.sh", args=("program-owner",))
        self.assertEqual(self.calls()[0], "build|program-owner")
        self.assertIn("tests/kernel-program-console-pty.py --mode program-owner", self.calls()[1])
        self.clear()
        for args in (("program-owner", "--console"), ("program-invalid", "--smoke")):
            self.assertIn("FAIL:", self.run_script(name="kernel-run.sh", args=args, expected=1))
            self.assertEqual(self.calls(), [])

    def test_alias_argument_errors_remain_failures(self):
        for name, args in (
            ("kernel-program-console.sh", ("--help",)),
            ("kernel-program-console-smoke.sh", ("--help",)),
            ("kernel-program-console-smoke.sh", ("program-console", "extra")),
        ):
            self.assertIn("FAIL:", self.run_script(name=name, args=args, expected=1))
            self.assertEqual(self.calls(), [])

    def test_build_admission_and_guest_failures_never_become_blocked(self):
        for build, pty, expected in ((2, 0, 2), (19, 0, 19), (0, 2, 2), (0, 17, 17)):
            result = self.run_script(env={"BUILD_STATUS": str(build), "PTY_STATUS": str(pty)}, expected=expected)
            self.assertIn("FAIL:", result)
            self.assertNotIn("BLOCKED:", result)
            self.assertEqual(len(self.calls()), 1 if build else 2)
            self.assertNotIn("build|normal", self.calls())
            self.clear()
        self.run_script(name="kernel-program-console.sh", env={"CHECK_STATUS": "1"}, expected=1)
        self.assertEqual(self.calls(), ["build|program-console", "checked"])

    def test_missing_prerequisites_block_before_any_mutation(self):
        for env in (
            {"QEMU": "missing-qemu"},
            {"CXX": "missing-cxx"},
            {"AURORAC": "missing-compiler"},
            {"OVMF": str(self.home / "missing.fd")},
            {"QEMU_DATA": str(self.home / "missing-data")},
            {"UEFI_LD": "missing-linker"},
        ):
            result = self.run_script(env=env, expected=2)
            self.assertIn("BLOCKED:", result)
            self.assertEqual(self.calls(), [])
            self.assertFalse((self.repo / "build").exists())

    def test_invalid_controls_fail_before_any_mutation(self):
        for env in (
            {"UEFI_MODE": "normal"},
            {"AURORA_TEST_CONTEXT": "context"},
            {"KERNEL_TEST_FAULT": "1"},
            {"OVMF_CODE": "code.fd"},
            {"OVMF": "", "OVMF_CODE": "code.fd"},
            {"OVMF": "", "OVMF_CODE": "same.fd", "OVMF_VARS": "same.fd"},
        ):
            result = self.run_script(env=env, expected=1)
            self.assertIn("FAIL:", result)
            self.assertEqual(self.calls(), [])
        self.run_script(args=("not-a-mode",), expected=1)
        self.assertEqual(self.calls(), [])

    def test_public_make_routes(self):
        for target, expected_calls in (
            ("program-console-uefi", ["build|program-console", "checked", "clock", "guest"]),
            (
                "smoke-program-console-uefi",
                [
                    "build|program-console",
                    "pty|-B tests/kernel-program-console-pty.py --mode program-console "
                    f"--build-dir {self.repo}/build/native profiles/program-console",
                ],
            ),
        ):
            result = subprocess.run(
                [MAKE, target],
                cwd=self.repo,
                env=self.env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(self.calls(), expected_calls)
            self.clear()


if __name__ == "__main__":
    unittest.main()

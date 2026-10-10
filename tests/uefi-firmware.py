#!/usr/bin/env python3
"""Firmware discovery/argv regressions. These fixtures never boot firmware."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/uefi-firmware.sh"


class FirmwareSelection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aurora-firmware-")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def file(self, name):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic firmware fixture")
        return str(path)

    def select(self, expected=0, plan=False, resolved=False, **env):
        current = {
            name: value for name, value in os.environ.items() if not name.startswith("OVMF") and name != "QEMU_DATA"
        }
        current.update(env)
        # Empty directory is deliberate: tests never discover host firmware.
        if not any(name in env for name in ("OVMF", "OVMF_CODE", "OVMF_VARS", "OVMF_DIR")):
            current["OVMF_DIR"] = str(self.home)
        result = subprocess.run(
            [
                "bash",
                "-eu",
                "-c",
                'source "$1"; shift; uefi_firmware_select "$@"; '
                + (
                    'printf "%s\\0" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS"; '
                    if resolved
                    else ""
                )
                + 'printf "%s\\0" "${UEFI_FIRMWARE_ARGS[@]}"',
                "test",
                str(HELPER),
                *(["--plan"] if plan else []),
            ],
            env=current,
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, expected, result.stderr.decode())
        return result.stdout.decode().rstrip("\0").split("\0") if expected == 0 else result.stderr.decode()

    def test_explicit_combined(self):
        rom = self.file("combined firmware, 4m.fd")
        self.assertEqual(self.select(OVMF=rom), ["-bios", rom])

    def test_explicit_split_has_readonly_code_and_disposable_vars(self):
        code = self.file("code, firmware.fd")
        vars = self.file("variables, template.fd")
        self.assertEqual(
            self.select(OVMF_CODE=code, OVMF_VARS=vars),
            [
                "-drive",
                "if=pflash,unit=0,format=raw,readonly=on,file=" + code.replace(",", ",,"),
                "-drive",
                "if=pflash,unit=1,format=raw,snapshot=on,file=" + vars.replace(",", ",,"),
            ],
        )
        self.assertEqual(Path(vars).read_bytes(), b"synthetic firmware fixture")

    def test_common_distro_pair_names(self):
        for code, vars in [
            ("OVMF_CODE_4M.fd", "OVMF_VARS_4M.fd"),
            ("OVMF_CODE.4m.fd", "OVMF_VARS.4m.fd"),
            ("OVMF_CODE.fd", "OVMF_VARS.fd"),
            ("OVMF_CODE_4M.qcow2", "OVMF_VARS_4M.qcow2"),
        ]:
            with self.subTest(code=code):
                first = self.file(code)
                second = self.file(vars)
                args = self.select(OVMF_DIR=str(self.home))
                self.assertIn("file=" + first, args[1])
                self.assertIn("file=" + second, args[3])
                self.assertIn("format=" + ("qcow2" if code.endswith("qcow2") else "raw"), args[1])
                Path(first).unlink()
                Path(second).unlink()

    def test_split_preferred_to_combined(self):
        self.file("OVMF.fd")
        self.file("OVMF_CODE.fd")
        self.file("OVMF_VARS.fd")
        self.assertEqual(self.select()[0], "-drive")

    def test_combined_discovery_fallback(self):
        rom = self.file("OVMF.4m.fd")
        self.assertEqual(self.select(), ["-bios", rom])

    def test_incomplete_or_mismatched_pair_is_not_discovered(self):
        self.file("OVMF_CODE.fd")
        self.file("OVMF_VARS_4M.fd")
        self.assertIn("not found", self.select(expected=2))

    def test_secure_boot_variants_are_not_automatically_selected(self):
        self.file("OVMF_CODE.secboot.fd")
        self.file("OVMF_VARS.fd")
        self.assertIn("not found", self.select(expected=2))

    def test_conflicting_and_incomplete_overrides_fail(self):
        rom = self.file("OVMF.fd")
        code = self.file("OVMF_CODE.fd")
        vars = self.file("OVMF_VARS.fd")
        for env in [
            {"OVMF": rom, "OVMF_CODE": code, "OVMF_VARS": vars},
            {"OVMF": rom, "OVMF_DIR": str(self.home)},
            {"OVMF_CODE": code, "OVMF_VARS": vars, "OVMF_DIR": str(self.home)},
            {"OVMF_CODE": code},
            {"OVMF_VARS": vars},
        ]:
            with self.subTest(env=env):
                self.select(expected=2, **env)

    def test_bad_explicit_paths_never_fall_back(self):
        self.file("OVMF.fd")
        vars = self.file("OVMF_VARS.fd")
        for env in [
            {"OVMF": str(self.home)},
            {"OVMF": str(self.home / "missing")},
            {"OVMF_CODE": str(self.home / "missing"), "OVMF_VARS": vars},
            {"OVMF_DIR": str(self.home / "missing")},
        ]:
            with self.subTest(env=env):
                self.select(expected=2, **env)

    def test_empty_and_same_files_rejected(self):
        code = self.file("code.fd")
        Path(code).write_bytes(b"")
        self.select(expected=2, OVMF=code)
        Path(code).write_bytes(b"firmware")
        self.select(expected=2, OVMF_CODE=code, OVMF_VARS=code)
        alias = self.home / "alias.fd"
        alias.symlink_to(code)
        self.select(expected=2, OVMF_CODE=code, OVMF_VARS=str(alias))

    def test_plan_accepts_explicit_missing_paths_without_writes(self):
        combined = str(self.home / "missing combined.fd")
        code = str(self.home / "missing,code.qcow2")
        variables = str(self.home / "missing,,vars.fd")
        self.assertEqual(self.select(plan=True, resolved=True, OVMF=combined), [combined, "", "", "-bios", combined])
        self.assertEqual(
            self.select(plan=True, resolved=True, OVMF_CODE=code, OVMF_VARS=variables),
            [
                "",
                code,
                variables,
                "-drive",
                "if=pflash,unit=0,format=qcow2,readonly=on,file=" + code.replace(",", ",,"),
                "-drive",
                "if=pflash,unit=1,format=raw,snapshot=on,file=" + variables.replace(",", ",,"),
            ],
        )
        self.assertEqual(list(self.home.iterdir()), [])
        # The ordinary runtime selector still refuses those same missing files.
        self.select(expected=2, OVMF=combined)
        self.select(expected=2, OVMF_CODE=code, OVMF_VARS=variables)

    def test_plan_retains_conflict_pair_and_alias_checks(self):
        for env in (
            {"OVMF": "combined", "OVMF_CODE": "code", "OVMF_VARS": "vars"},
            {"OVMF": "combined", "OVMF_DIR": str(self.home)},
            {"OVMF_CODE": "code", "OVMF_VARS": "vars", "OVMF_DIR": str(self.home)},
            {"OVMF_CODE": "code"},
            {"OVMF_VARS": "vars"},
            {"OVMF_CODE": "same-missing", "OVMF_VARS": "same-missing"},
        ):
            with self.subTest(env=env):
                self.select(expected=2, plan=True, **env)
        code = self.file("code.fd")
        alias = self.home / "alias.fd"
        alias.symlink_to(code)
        self.select(expected=2, plan=True, OVMF_CODE=code, OVMF_VARS=str(alias))

    def test_plan_discovery_has_same_order_and_resolved_paths(self):
        combined = self.file("OVMF.fd")
        code = self.file("OVMF_CODE.fd")
        variables = self.file("OVMF_VARS.fd")
        self.assertEqual(self.select(plan=True), self.select())
        self.assertEqual(self.select(plan=True, resolved=True)[:3], ["", code, variables])
        Path(code).unlink()
        Path(variables).unlink()
        self.assertEqual(self.select(plan=True, resolved=True), [combined, "", "", "-bios", combined])

    def test_plan_unresolved_directory_fails_without_guessed_command(self):
        self.assertIn("Clock plan unresolved", self.select(expected=2, plan=True))
        self.assertIn(
            "existing firmware directory", self.select(expected=2, plan=True, OVMF_DIR=str(self.home / "missing"))
        )

    def test_qemu_data_discovery_and_resolved_runtime_fields(self):
        code = self.file("OVMF_CODE_4M.qcow2")
        variables = self.file("OVMF_VARS_4M.qcow2")
        # Present empty selectors suppress this test helper's OVMF_DIR default.
        env = dict(OVMF="", OVMF_CODE="", OVMF_VARS="", OVMF_DIR="", QEMU_DATA=str(self.home))
        self.assertEqual(self.select(resolved=True, **env)[:3], ["", code, variables])
        self.assertEqual(self.select(plan=True, **env), self.select(**env))


if __name__ == "__main__":
    unittest.main()

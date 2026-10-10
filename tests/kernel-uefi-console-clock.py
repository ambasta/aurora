#!/usr/bin/env python3
"""Native-free opt-in console argv controls; no image or QEMU execution."""

from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_emulator_clock as clock
import kernel_uefi_console_clock as console


class ConsoleClock(unittest.TestCase):
    def test_exact_normal_clock_and_mutations(self):
        for combined, code, variables in (
            ("/firmware.fd", "", ""),
            ("", "/code.fd", "/vars.fd"),
            ("", "/code,a.qcow2", "/vars,b.qcow2"),
        ):
            with self.subTest(combined=combined, code=code):
                qemu, data = "/qemu with spaces", "/data with spaces"
                argv = clock.expected_uefi_argv("normal", qemu, combined, data, code, variables)
                result = console.receipt(argv, qemu, combined, code, variables, data)
                self.assertEqual(result["clock_profile"], clock.ORIGINAL)
                self.assertEqual(result["command_template"], "normal")
                self.assertEqual(result["timeout_argv"], ["timeout", "--foreground", "--kill-after=2", "300"] + argv)
                self.assertNotIn("-icount", result["argv"])
                mutations = [
                    argv + ["-icount", "shift=0,align=off,sleep=off"],
                    argv + ["-icount", "shift=0,align=off,sleep=on"],
                ]
                for option, value in (
                    ("-monitor", "stdio"),
                    ("-smp", "2"),
                    ("-m", "256M"),
                    ("-machine", "pc"),
                    ("-nic", "user"),
                    ("-serial", "file:log"),
                ):
                    changed = argv.copy()
                    changed[changed.index(option) + 1] = value
                    mutations.append(changed)
                for changed in mutations:
                    with self.assertRaises(ValueError):
                        console.receipt(changed, qemu, combined, code, variables, data)

    def test_explicit_profile_esp_is_bound(self):
        esp = "/native/profile with spaces/esp"
        argv = clock.expected_uefi_argv("normal", "qemu", "/firmware.fd", "", esp=esp)
        result = console.receipt(argv, "qemu", "/firmware.fd", "", "", "", esp=esp)
        self.assertEqual(result["argv"], argv)
        for wrong in ("build/uefi/esp", "/another/profile/esp"):
            with self.assertRaises(ValueError):
                console.receipt(argv, "qemu", "/firmware.fd", "", "", "", esp=wrong)


if __name__ == "__main__":
    unittest.main()

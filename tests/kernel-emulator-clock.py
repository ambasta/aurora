#!/usr/bin/env python3
"""Native-free source/argv controls. No compiler, image build or guest execution."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("kernel_emulator_clock", ROOT / "scripts/kernel_emulator_clock.py")
CLOCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLOCK)
FIXED_ARGS = ["-icount", "shift=0,align=off,sleep=off"]
SELECTED_NAMES_SHA256 = "8de8cbdb6c9811690811e802adeed75095d0335ca69901ade7b2f69b83e9608e"
WRAPPERS = {
    "bios": ("kernel-protection-smoke.sh", "kernel-scheduling-smoke.sh",
             "kernel-division-smoke.sh", "kernel-unsigned-smoke.sh"),
    "uefi": ("kernel-uefi-all.sh", "kernel-acpi-all.sh", "kernel-pci-all.sh",
             "kernel-uefi-runtime-all.sh", "kernel-uefi-span-all.sh", "kernel-uefi-pin-all.sh",
             "kernel-uefi-tables-all.sh", "kernel-uefi-ipc-all.sh", "kernel-uefi-budget-all.sh",
             "kernel-uefi-dispatch-all.sh", "kernel-uefi-user-phases-all.sh"),
    "bar": ("kernel-uefi-bar-all.sh",),
    "ivrs": ("kernel-uefi-ivrs-all.sh",),
}
# Byte identity preserves actual unchanged argv and strict validation, not just
# names in our map. New legitimate changes need a separately reviewed contract.
UNCHANGED = {
    "scripts/kernel-smoke.sh": "37f02032c31ad6b137222b3be323be299c05f9eb4fb0fa0107d2379c9dc9ddf3",
    "scripts/kernel-uefi-bar-run.py": "0a86c6a0d06babda622f50368d50ec85a7084ed6c39574f2d71c276d49e38dd1",
    "scripts/kernel-uefi-ivrs-run.py": "16d80ca8d975385691ad538287f4e5eecdacde5d0b8982f423146a1ec7fccd67",
    "tests/kernel-boot-capacity.py": "90c76ca1e1d8bf89b36179ab3c82d8c08a7b25e08c04d9a2afa170da99800a3a",
    "tests/kernel-uefi-budget-smoke.py": "51aaa29ba0f28f59576b7bbff451eafd913b306790f72bd1afc6b0839a853e93",
    "tests/kernel-uefi-dispatch-smoke.py": "506ff383b107ad1f4f05297c54e5179a73bcc05978a91f9429a389b5888f97f9",
    "tests/kernel-uefi-user-phases-smoke.py": "8b85959a9f15aa872200fd552ae1fc08ec29da16b396922c05ebd97919e6e1ee",
}


def wrapper_modes(name):
    source = (ROOT / "scripts" / name).read_text().replace("\\\n", " ")
    match = re.search(r"for mode in ([^;]+); do", source)
    if match is None:
        # The one-mode span wrapper does not have a loop.
        if name == "kernel-uefi-span-all.sh":
            match = re.search(r"kernel-uefi-smoke\.sh (runtime-span)(?:\s|$)", source)
            if match:
                return [match[1]]
        raise ValueError("Missing exact wrapper inventory: " + name)
    return match[1].split()


def shell_plan(*modes, data="", extra_env=None, root=ROOT, plan=True):
    env = {name: value for name, value in os.environ.items() if not name.startswith("OVMF")}
    env.update(QEMU="/nonexistent clock test/qemu", OVMF="/nonexistent firmware.fd",
               QEMU_DATA=data, PYTHONDONTWRITEBYTECODE="1")
    if extra_env:
        env.update(extra_env)
    command = ["bash", str(root / "scripts/kernel-uefi-smoke.sh")]
    return subprocess.run(command + (["--clock-plan"] if plan else []) + list(modes),
                          cwd=root, env=env, capture_output=True, text=True, timeout=10)


class ClockContractTests(unittest.TestCase):
    def test_exact_177_mode_partition_and_macro_boundary(self):
        inventory = []
        for family, wrappers in WRAPPERS.items():
            for wrapper in wrappers:
                inventory += [(family, mode) for mode in wrapper_modes(wrapper)]
        self.assertEqual(len(inventory), 177)
        self.assertEqual(len(set(inventory)), 177)
        self.assertEqual(set(inventory), set(CLOCK.MODE_CLOCKS))
        selected = [mode for (family, mode), profile in CLOCK.MODE_CLOCKS.items()
                    if profile == CLOCK.FIXED0]
        self.assertEqual(len(selected), 51)
        self.assertEqual(sum(p == CLOCK.ORIGINAL for p in CLOCK.MODE_CLOCKS.values()), 126)
        self.assertEqual(hashlib.sha256(("\n".join(sorted(selected)) + "\n").encode()).hexdigest(),
                         SELECTED_NAMES_SHA256)
        build = (ROOT / "scripts/kernel-uefi-build.sh").read_text()
        admitted = []
        for match in re.finditer(r"^ ([\w|_-]+)\)\n(.*?);;", build, re.MULTILINE | re.DOTALL):
            if "-DAURORA_UEFI_SERVICE_BUDGET" in match[2]:
                admitted.extend(match[1].split("|"))
        self.assertEqual(len(admitted), 51)
        self.assertEqual(set(admitted), set(selected))
        rows = CLOCK.mode_clock_rows()
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(CLOCK.mode_clock_sha256(), hashlib.sha256(raw).hexdigest())

    def test_every_mode_profile_and_hostile_clock_pairings(self):
        cases = dict(CLOCK.MODE_CLOCKS)
        cases.update(CLOCK.AUXILIARY_CLOCKS)
        self.assertEqual(len(cases), 182)
        for (family, mode), profile in cases.items():
            with self.subTest(family=family, mode=mode):
                original = ["qemu", "-accel", "tcg"]
                valid = original + (FIXED_ARGS if profile == CLOCK.FIXED0 else [])
                self.assertEqual(CLOCK.validate_clock_options(family, mode, profile, valid), profile)
                for label in (None, "", "auto", "unknown", CLOCK.ORIGINAL if profile == CLOCK.FIXED0 else CLOCK.FIXED0):
                    with self.assertRaises(ValueError):
                        CLOCK.validate_clock_options(family, mode, label, valid)
                bad = [[], "qemu", [None], [42], [""], original + ["-icount"], original + FIXED_ARGS * 2,
                       original + ["-icount", "auto"], original + ["-icount", "shift=auto"],
                       original + ["-icount", "shift=1,align=off,sleep=off"],
                       original + ["-icount", "shift=0,align=on,sleep=off"],
                       original + ["-icount", "shift=0,align=off,sleep=on"],
                       original + ["-icount", "shift=0"],
                       original + ["-icount", "shift=0,sleep=off,align=off"],
                       original + ["--icount", FIXED_ARGS[1]],
                       original + ["-icount=" + FIXED_ARGS[1]],
                       original + ["--icount=" + FIXED_ARGS[1]],
                       valid + ["-rtc", "clock=host"], valid + ["-readconfig", "clock.conf"],
                       original + FIXED_ARGS + ["-icount", "shift=1,align=off,sleep=off"],
                       original if profile == CLOCK.FIXED0 else original + FIXED_ARGS]
                for argv in bad:
                    with self.assertRaises(ValueError, msg=repr(argv)):
                        CLOCK.validate_clock_options(family, mode, profile, argv)

    def test_unknown_duplicate_and_conflicting_selection(self):
        for family, mode in (("uefi", "budget-future"), ("uefi", "dispatch-new"),
                             ("uefi", "user-new"), ("uefi", ""), ("bios", "budget"),
                             ("future", "normal"), ("uefi", "BUDGET")):
            with self.assertRaises(ValueError):
                CLOCK.clock_profile(family, mode)
        for second in (CLOCK.FIXED0, CLOCK.ORIGINAL):
            with self.assertRaises(ValueError):
                CLOCK.make_mode_map((("uefi", CLOCK.FIXED0, ("budget",)),
                                     ("uefi", second, ("budget",))))
        with self.assertRaises(ValueError):
            CLOCK.make_mode_map((("uefi", "auto", ("budget",)),))

    def test_real_shell_array_for_all_uefi_build_modes(self):
        modes = sorted(mode for family, mode in CLOCK.MODE_CLOCKS if family != "bios")
        self.assertEqual(len(modes), 140)
        for mode in modes:
            for data in ("", "/nonexistent data files"):
                with self.subTest(mode=mode, data=data):
                    result = shell_plan(mode, data=data)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    receipt = json.loads(result.stdout)
                    expected = CLOCK.clock_profile(CLOCK.uefi_family(mode), mode)
                    self.assertEqual(receipt["clock_profile"], expected)
                    self.assertEqual(receipt["mode_clock_sha256"], CLOCK.mode_clock_sha256())
                    argv = receipt["argv"]
                    self.assertEqual(receipt["timeout_argv"], ["timeout", "30", *argv])
                    self.assertEqual(receipt["execution_status"], "not-established-by-command-receipt")
                    for flag, value in (("-machine", "q35"), ("-accel", "tcg"), ("-m", "128M"),
                                        ("-nic", "none"), ("-display", "none"), ("-monitor", "none"),
                                        ("-smp", "2" if mode in ("budget-smp", "acpi-two") else "1")):
                        self.assertEqual(argv.count(flag), 1)
                        self.assertEqual(argv[argv.index(flag) + 1], value)
                    self.assertEqual(argv.count("-icount"), int(expected == CLOCK.FIXED0))
                    if expected == CLOCK.FIXED0:
                        self.assertEqual(argv[argv.index("-icount") + 1], FIXED_ARGS[1])
                    cpu = "qemu64,vendor=GenuineIntel,+sep" if mode == "runtime-sysenter" else "qemu64"
                    self.assertEqual(argv[argv.index("-cpu") + 1], cpu)
                    self.assertEqual(argv[argv.index("-bios") + 1], "/nonexistent firmware.fd")
                    self.assertEqual(argv.count("-L"), int(bool(data)))
                    if data:
                        self.assertEqual(argv[argv.index("-L") + 1], data)

    def test_full_argv_and_friendly_label_cannot_bypass_binding(self):
        for mode in ("budget", "budget-smp", "dispatch", "user-retire-pending", "normal", "ipc-policy-request-output"):
            profile = CLOCK.clock_profile(CLOCK.uefi_family(mode), mode)
            argv = CLOCK.expected_uefi_argv(mode, "qemu", "firmware", "data")
            self.assertEqual(CLOCK.uefi_clock_receipt(mode, profile, argv, "qemu", "firmware", "data")["argv"], argv)
            for flag, wrong in (("-accel", "tcg,thread=multi"), ("-cpu", "host"), ("-smp", "3"),
                                ("-machine", "pc"), ("-m", "256M"), ("-nic", "user"),
                                ("-bios", "other.fd"), ("-monitor", "stdio")):
                bad = argv[:]
                bad[bad.index(flag) + 1] = wrong
                with self.assertRaises(ValueError):
                    CLOCK.uefi_clock_receipt(mode, profile, bad, "qemu", "firmware", "data")
            for bad in (argv + ["-icount", "auto"], argv + ["-accel", "kvm"], argv + ["-smp", "1"],
                        argv + ["-no-reboot"], argv[1:], ["other-qemu", *argv[1:]]):
                with self.assertRaises(ValueError):
                    CLOCK.uefi_clock_receipt(mode, profile, bad, "qemu", "firmware", "data")

    def test_split_firmware_paths_formats_and_comma_escaping(self):
        for code_ext, code_format in (("fd", "raw"), ("qcow2", "qcow2")):
            for vars_ext, vars_format in (("fd", "raw"), ("qcow2", "qcow2")):
                code = "/nonexistent code, drive=other." + code_ext
                variables = "/nonexistent vars,, template." + vars_ext
                firmware_args = [
                    "-drive", "if=pflash,unit=0,format=" + code_format +
                    ",readonly=on,file=/nonexistent code,, drive=other." + code_ext,
                    "-drive", "if=pflash,unit=1,format=" + vars_format +
                    ",snapshot=on,file=/nonexistent vars,,,, template." + vars_ext,
                ]
                self.assertEqual(CLOCK.expected_firmware_argv("", code, variables), firmware_args)
                for mode in ("normal", "budget-smp"):
                    with self.subTest(mode=mode, code_ext=code_ext, vars_ext=vars_ext):
                        result = shell_plan(mode, data="/nonexistent data files", extra_env={
                            "OVMF": "", "OVMF_CODE": code, "OVMF_VARS": variables})
                        self.assertEqual(result.returncode, 0, result.stderr)
                        receipt = json.loads(result.stdout)
                        argv = receipt["argv"]
                        first = argv.index("-drive")
                        self.assertEqual(argv[first:first + 4], firmware_args)
                        self.assertEqual(argv.count("-drive"), 3)
                        self.assertNotIn("-bios", argv)
                        self.assertEqual(receipt["clock_profile"], CLOCK.clock_profile("uefi", mode))
                        self.assertEqual(receipt["timeout_argv"], ["timeout", "30", *argv])

    def test_split_firmware_hostile_argv_cannot_bypass_binding(self):
        code = "/code, firmware.qcow2"
        variables = "/vars,, template.fd"
        for mode in ("normal", "budget", "runtime-sysenter", "pci-bridge"):
            profile = CLOCK.clock_profile(CLOCK.uefi_family(mode), mode)
            argv = CLOCK.expected_uefi_argv(mode, "qemu", "", "data", code, variables)
            first = argv.index("-drive")
            self.assertEqual(CLOCK.uefi_clock_receipt(
                mode, profile, argv, "qemu", "", "data", code, variables)["argv"], argv)
            corruptions = []
            for offset, before, after in (
                (1, "readonly=on,", ""), (3, "snapshot=on,", ""),
                (1, "unit=0", "unit=1"), (3, "unit=1", "unit=0"),
                (1, "format=qcow2", "format=raw"), (3, "format=raw", "format=qcow2"),
                (1, "readonly=on", "snapshot=on"), (3, "snapshot=on", "readonly=on"),
                (1, "code,, firmware", "code, firmware"),
                (3, "vars,,,, template", "vars,, template"),
                (1, "code,, firmware", "other,, firmware"),
                (3, "vars,,,, template", "other,,,, template"),
                (3, "snapshot=on", "snapshot=on,readonly=on"),
            ):
                bad = argv[:]
                self.assertIn(before, bad[first + offset])
                bad[first + offset] = bad[first + offset].replace(before, after)
                corruptions.append(bad)
            swapped = argv[:]
            swapped[first + 1], swapped[first + 3] = swapped[first + 3], swapped[first + 1]
            corruptions += [swapped, argv[:first] + argv[first + 2:],
                            argv + argv[first:first + 4], argv + ["-bios", "other.fd"],
                            argv + ["-snapshot"], argv + ["-blockdev", "driver=file"],
                            argv + ["-icount", "auto"], argv + ["-readconfig", "other.conf"]]
            for bad in corruptions:
                with self.assertRaises(ValueError, msg=repr(bad)):
                    CLOCK.uefi_clock_receipt(mode, profile, bad, "qemu", "", "data", code, variables)
            # A correct clock label and argv cannot hide altered semantic inputs.
            for firmware, other_code, other_vars in (("other.fd", code, variables),
                    ("", code + ".fd", variables), ("", code, variables + ".qcow2")):
                with self.assertRaises(ValueError):
                    CLOCK.uefi_clock_receipt(mode, profile, argv, "qemu", firmware, "data", other_code, other_vars)

    def test_firmware_contract_rejects_conflicting_partial_and_invalid_paths(self):
        for paths in (("", "", ""), ("combined", "code", "vars"),
                      ("combined", "code", ""), ("combined", "", "vars"),
                      ("", "code", ""), ("", "", "vars"), ("", "same", "same"),
                      (None, "", ""), ("", [], "vars"), ("", "code", 42),
                      ("bad\0path", "", ""), ("", "bad\0code", "vars")):
            with self.assertRaises(ValueError):
                CLOCK.expected_firmware_argv(*paths)
        self.assertEqual(CLOCK.expected_firmware_argv("combined, firmware.fd", "", ""),
                         ["-bios", "combined, firmware.fd"])

    def test_plans_and_invalid_modes_never_build_execute_qemu_or_write(self):
        with tempfile.TemporaryDirectory(prefix="aurora-clock-plan-") as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            for name in ("kernel-uefi-smoke.sh", "kernel_emulator_clock.py", "uefi-firmware.sh"):
                shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
            sentinel = '#!/usr/bin/env bash\nprintf reached >> unexpected-execution\nexit 99\n'
            for target in (root / "qemu", root / "scripts/kernel-uefi-build.sh"):
                target.write_text(sentinel)
                target.chmod(0o755)
            env = {"QEMU": str(root / "qemu"), "OVMF": str(root / "missing.fd")}
            def snapshot():
                return {str(path.relative_to(root)): (
                    path.stat().st_mode,
                    hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
                    for path in root.rglob("*")}
            before = snapshot()
            for mode in ((), ("normal",), ("budget-smp",)):
                result = shell_plan(*mode, root=root, extra_env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
            split = dict(env, OVMF="", OVMF_CODE=str(root / "missing-code.qcow2"),
                         OVMF_VARS=str(root / "missing-vars.fd"))
            result = shell_plan("budget", root=root, extra_env=split)
            self.assertEqual(result.returncode, 0, result.stderr)
            for plan in (False, True):
                for modes in (("",), ("future",), ("normal", "extra")):
                    result = shell_plan(*modes, root=root, extra_env=env, plan=plan)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")
            self.assertEqual(snapshot(), before)

    def test_plan_firmware_selector_errors_and_unresolved_directory(self):
        with tempfile.TemporaryDirectory(prefix="aurora-clock-firmware-") as directory:
            for extra in ({"OVMF_CODE": "code", "OVMF_VARS": "vars"},
                          {"OVMF_DIR": directory},
                          {"OVMF": "", "OVMF_CODE": "code"},
                          {"OVMF": "", "OVMF_VARS": "vars"},
                          {"OVMF": "", "OVMF_CODE": "same", "OVMF_VARS": "same"},
                          {"OVMF": "", "OVMF_CODE": "code", "OVMF_VARS": "vars", "OVMF_DIR": directory}):
                result = shell_plan("normal", extra_env=extra)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
            result = shell_plan("budget", extra_env={"OVMF": "", "OVMF_DIR": directory})
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("Clock plan unresolved", result.stderr)

    def test_shell_rejects_unknown_empty_and_extra_selections(self):
        for modes in (("",), ("budget-new",), ("dispatch-new",), ("user-new",),
                      ("normal", "normal"), ("budget", CLOCK.ORIGINAL),
                      ("budget", "-icount", "auto"), ("--clock-plan",)):
            result = shell_plan(*modes)
            self.assertEqual(result.returncode, 2, repr(modes))
            self.assertEqual(result.stdout, "")
        # No arbitrary clock/argv environment override is recognized.
        for mode in ("normal", "budget-smp"):
            result = shell_plan(mode, extra_env={"QEMU_ARGS": "-icount auto -smp 1",
                "QEMU_CLOCK_PROFILE": "auto", "AURORA_QEMU_ARGS": "-icount auto",
                "AURORA_CLOCK_PROFILE": "tcg-original-clock"})
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["clock_profile"], CLOCK.clock_profile("uefi", mode))

    def test_both_normal_restorations_and_three_capacity_probes(self):
        self.assertEqual(CLOCK.AUXILIARY_CLOCKS, {
            ("bios-capacity", "full-127"): CLOCK.ORIGINAL,
            ("bios-capacity", "old-96-negative"): CLOCK.ORIGINAL,
            ("bios-capacity", "last-sector-negative"): CLOCK.ORIGINAL,
            ("bios-restoration", "normal"): CLOCK.ORIGINAL,
            ("uefi-restoration", "normal"): CLOCK.ORIGINAL,
        })
        # UEFI normal restoration is the same actual launcher path with no mode.
        default, explicit = shell_plan(), shell_plan("normal")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(json.loads(default.stdout), json.loads(explicit.stdout))
        self.assertNotIn("-icount", json.loads(default.stdout)["argv"])
        # BIOS default/restoration and capacity paths are preserved byte-for-byte.
        for path, digest in UNCHANGED.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)
        capacity = ast.parse((ROOT / "tests/kernel-boot-capacity.py").read_text())
        smoke = next(node for node in capacity.body if isinstance(node, ast.FunctionDef) and node.name == "smoke")
        fixtures = next(node.value for node in ast.walk(smoke) if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "fixtures" for t in node.targets))
        self.assertEqual([(row.elts[0].value, row.elts[2].value) for row in fixtures.elts],
                         [("full-127", 33), ("old-96-negative", 35), ("last-sector-negative", 35)])
        self.assertNotIn("-icount", ast.get_source_segment((ROOT / "tests/kernel-boot-capacity.py").read_text(), smoke))

    def test_launcher_executes_validated_array_and_keeps_raw_outcome(self):
        source = (ROOT / "scripts/kernel-uefi-smoke.sh").read_text()
        self.assertEqual(source.count('timeout 30 "${qemu_argv[@]}"'), 1)
        self.assertIn('"${QEMU_DATA:-}" -- "${qemu_argv[@]}"', source)
        self.assertLess(source.index('"${clock_check[@]}" >'), source.index('timeout 30 "${qemu_argv[@]}"'))
        self.assertIn('status=$?\nset -e\ncat "$log"', source)
        tail = source[source.index('status=$?'):]
        self.assertEqual(hashlib.sha256(tail.encode()).hexdigest(),
                         "e2957842c79b5c1f6e6f4399aa8b94d82cc824cc0c11948627a0144f8603695c")
        self.assertIn("trap './scripts/kernel-uefi-build.sh >/dev/null' EXIT", source)
        self.assertEqual(source.count("\ncpus=1\n"), 1)
        self.assertIn('python3 tests/kernel-uefi-budget-smoke.py "$status"', source)
        self.assertIn('python3 tests/kernel-uefi-dispatch-smoke.py "$status"', source)
        self.assertIn('python3 tests/kernel-uefi-user-phases-smoke.py "$status"', source)


if __name__ == "__main__":
    unittest.main()

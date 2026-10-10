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
SELECTED_NAMES_SHA256 = "a5b6f5d5194dc6113bb6864fe3c2e4efa44faf5ab6a6fee42fe8dc9ecd2160ee"
WRAPPERS = {
    "bios": (
        "kernel-protection-smoke.sh",
        "kernel-scheduling-smoke.sh",
        "kernel-division-smoke.sh",
        "kernel-unsigned-smoke.sh",
    ),
    "uefi": (
        "kernel-uefi-all.sh",
        "kernel-acpi-all.sh",
        "kernel-pci-all.sh",
        "kernel-uefi-runtime-all.sh",
        "kernel-uefi-span-all.sh",
        "kernel-uefi-pin-all.sh",
        "kernel-uefi-tables-all.sh",
        "kernel-uefi-ipc-all.sh",
        "kernel-uefi-budget-all.sh",
        "kernel-uefi-dispatch-all.sh",
        "kernel-uefi-user-phases-all.sh",
    ),
    "bar": ("kernel-uefi-bar-all.sh",),
    "ivrs": ("kernel-uefi-ivrs-all.sh",),
}
# The BAR launcher is checked by executable argv/validator invariants below;
# its historical whole-file hash was already stale after NVMe preparation.
# Other unchanged historical gates retain their separate identity checks.
UNCHANGED = {
    # Reviewed object-directory-only change; guest clock/argv remain unchanged.
    "scripts/kernel-uefi-ivrs-run.py": "5adc179e32b879591646dc87e0c974dd63b65fe243b35c7beb0eb916a3272ec5",
    "tests/kernel-boot-capacity.py": "a50b6cb2d0bb3b43f50afa3d8d8059c4504dbe633510eb43b8a1ab16c54c257b",
    "tests/kernel-uefi-budget-smoke.py": "51aaa29ba0f28f59576b7bbff451eafd913b306790f72bd1afc6b0839a853e93",
    "tests/kernel-uefi-dispatch-smoke.py": "506ff383b107ad1f4f05297c54e5179a73bcc05978a91f9429a389b5888f97f9",
    # Recovery validator changed only for two disposal-denial profiles; its
    # existing fixtures are compared against the accepted baseline separately.
}


# The BIOS console commit added an early opt-in rejection guard. Its closed
# whole-file provenance and the unchanged executable smoke body are independent.
BIOS_SMOKE_SHA256 = "694eaa63266939af88634664e8ecc3be261a066d69f8050fe320cd15f303d4da"
BIOS_SMOKE_BODY_SHA256 = "e95b28a60111ba61f04ecfb588c42f6a5fc69e69126c519ac34e539119ff0271"


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
    env.update(
        QEMU="/nonexistent clock test/qemu",
        OVMF="/nonexistent firmware.fd",
        QEMU_DATA=data,
        PYTHONDONTWRITEBYTECODE="1",
    )
    if extra_env:
        env.update(extra_env)
    command = ["bash", str(root / "scripts/kernel-uefi-smoke.sh")]
    return subprocess.run(
        command + (["--clock-plan"] if plan else []) + list(modes),
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


class ClockContractTests(unittest.TestCase):
    def test_existing_177_modes_plus_disposal_and_owned_profiles(self):
        inventory = []
        for family, wrappers in WRAPPERS.items():
            for wrapper in wrappers:
                inventory += [(family, mode) for mode in wrapper_modes(wrapper)]
        self.assertEqual(len(inventory), 183)
        self.assertEqual(len(set(inventory)), 183)
        snapshots = {
            ("uefi", mode)
            for mode in (
                "snapshot",
                "snapshot-fault",
                "snapshot-cancel",
                "snapshot-owner",
                "snapshot-stale",
                "snapshot-revoked",
                "snapshot-producer-selector",
                "snapshot-producer-quota",
                "snapshot-producer-pages",
                "snapshot-reply-reserved",
                "snapshot-reply-byte",
            )
        }
        self.assertEqual(set(inventory) | {("uefi", "owned-bytes")} | snapshots, set(CLOCK.MODE_CLOCKS))
        self.assertTrue(all(CLOCK.clock_profile(*key) == CLOCK.ORIGINAL for key in snapshots))
        self.assertEqual(CLOCK.clock_profile("uefi", "owned-bytes"), CLOCK.ORIGINAL)
        selected = [mode for (family, mode), profile in CLOCK.MODE_CLOCKS.items() if profile == CLOCK.FIXED0]
        self.assertEqual(len(selected), 53)
        self.assertEqual(sum(p == CLOCK.ORIGINAL for p in CLOCK.MODE_CLOCKS.values()), 142)
        self.assertEqual(
            hashlib.sha256(("\n".join(sorted(selected)) + "\n").encode()).hexdigest(), SELECTED_NAMES_SHA256
        )
        build = (ROOT / "scripts/kernel-uefi-build.sh").read_text()
        # Protected-console profiles share the budget machinery but run through
        # the separate original-clock PTY route, not the fixed-clock smoke map.
        protected_modes = {
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
        }
        admitted = []
        protected = []
        for match in re.finditer(r"^ ([\w|_-]+)\)\n(.*?);;", build, re.MULTILINE | re.DOTALL):
            if "-DAURORA_UEFI_SERVICE_BUDGET" in match[2]:
                modes = match[1].split("|")
                admitted.extend(modes)
                if "-DAURORA_UEFI_PROGRAM_CONSOLE" in match[2]:
                    protected.extend(modes)
        self.assertEqual(len(admitted), len(set(admitted)))
        self.assertEqual(len(protected), len(set(protected)))
        self.assertEqual(set(protected), protected_modes)
        self.assertTrue(protected_modes.isdisjoint(selected))
        self.assertEqual(set(admitted) - set(protected), set(selected))
        self.assertEqual(set(admitted), set(selected) | protected_modes)
        rows = CLOCK.mode_clock_rows()
        raw = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(CLOCK.mode_clock_sha256(), hashlib.sha256(raw).hexdigest())

    def test_every_mode_profile_and_hostile_clock_pairings(self):
        cases = dict(CLOCK.MODE_CLOCKS)
        cases.update(CLOCK.AUXILIARY_CLOCKS)
        self.assertEqual(len(cases), 200)
        for (family, mode), profile in cases.items():
            with self.subTest(family=family, mode=mode):
                original = ["qemu", "-accel", "tcg"]
                valid = original + (FIXED_ARGS if profile == CLOCK.FIXED0 else [])
                self.assertEqual(CLOCK.validate_clock_options(family, mode, profile, valid), profile)
                for label in (None, "", "auto", "unknown", CLOCK.ORIGINAL if profile == CLOCK.FIXED0 else CLOCK.FIXED0):
                    with self.assertRaises(ValueError):
                        CLOCK.validate_clock_options(family, mode, label, valid)
                bad = [
                    [],
                    "qemu",
                    [None],
                    [42],
                    [""],
                    original + ["-icount"],
                    original + FIXED_ARGS * 2,
                    original + ["-icount", "auto"],
                    original + ["-icount", "shift=auto"],
                    original + ["-icount", "shift=1,align=off,sleep=off"],
                    original + ["-icount", "shift=0,align=on,sleep=off"],
                    original + ["-icount", "shift=0,align=off,sleep=on"],
                    original + ["-icount", "shift=0"],
                    original + ["-icount", "shift=0,sleep=off,align=off"],
                    original + ["--icount", FIXED_ARGS[1]],
                    original + ["-icount=" + FIXED_ARGS[1]],
                    original + ["--icount=" + FIXED_ARGS[1]],
                    valid + ["-rtc", "clock=host"],
                    valid + ["-readconfig", "clock.conf"],
                    original + FIXED_ARGS + ["-icount", "shift=1,align=off,sleep=off"],
                    original if profile == CLOCK.FIXED0 else original + FIXED_ARGS,
                ]
                for argv in bad:
                    with self.assertRaises(ValueError, msg=repr(argv)):
                        CLOCK.validate_clock_options(family, mode, profile, argv)

    def test_unknown_duplicate_and_conflicting_selection(self):
        for family, mode in (
            ("uefi", "budget-future"),
            ("uefi", "dispatch-new"),
            ("uefi", "user-new"),
            ("uefi", ""),
            ("bios", "budget"),
            ("future", "normal"),
            ("uefi", "BUDGET"),
        ):
            with self.assertRaises(ValueError):
                CLOCK.clock_profile(family, mode)
        for second in (CLOCK.FIXED0, CLOCK.ORIGINAL):
            with self.assertRaises(ValueError):
                CLOCK.make_mode_map((("uefi", CLOCK.FIXED0, ("budget",)), ("uefi", second, ("budget",))))
        with self.assertRaises(ValueError):
            CLOCK.make_mode_map((("uefi", "auto", ("budget",)),))

    def test_real_shell_array_for_all_uefi_build_modes(self):
        modes = sorted(mode for family, mode in CLOCK.MODE_CLOCKS if family != "bios")
        self.assertEqual(len(modes), 156)
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
                    for flag, value in (
                        ("-machine", "q35"),
                        ("-accel", "tcg"),
                        ("-m", "128M"),
                        ("-nic", "none"),
                        ("-display", "none"),
                        ("-monitor", "none"),
                        ("-smp", "2" if mode in ("budget-smp", "acpi-two") else "1"),
                    ):
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
            for flag, wrong in (
                ("-accel", "tcg,thread=multi"),
                ("-cpu", "host"),
                ("-smp", "3"),
                ("-machine", "pc"),
                ("-m", "256M"),
                ("-nic", "user"),
                ("-bios", "other.fd"),
                ("-monitor", "stdio"),
            ):
                bad = argv[:]
                bad[bad.index(flag) + 1] = wrong
                with self.assertRaises(ValueError):
                    CLOCK.uefi_clock_receipt(mode, profile, bad, "qemu", "firmware", "data")
            for bad in (
                argv + ["-icount", "auto"],
                argv + ["-accel", "kvm"],
                argv + ["-smp", "1"],
                argv + ["-no-reboot"],
                argv[1:],
                ["other-qemu", *argv[1:]],
            ):
                with self.assertRaises(ValueError):
                    CLOCK.uefi_clock_receipt(mode, profile, bad, "qemu", "firmware", "data")

    def test_split_firmware_paths_formats_and_comma_escaping(self):
        for code_ext, code_format in (("fd", "raw"), ("qcow2", "qcow2")):
            for vars_ext, vars_format in (("fd", "raw"), ("qcow2", "qcow2")):
                code = "/nonexistent code, drive=other." + code_ext
                variables = "/nonexistent vars,, template." + vars_ext
                firmware_args = [
                    "-drive",
                    "if=pflash,unit=0,format="
                    + code_format
                    + ",readonly=on,file=/nonexistent code,, drive=other."
                    + code_ext,
                    "-drive",
                    "if=pflash,unit=1,format="
                    + vars_format
                    + ",snapshot=on,file=/nonexistent vars,,,, template."
                    + vars_ext,
                ]
                self.assertEqual(CLOCK.expected_firmware_argv("", code, variables), firmware_args)
                for mode in ("normal", "budget-smp"):
                    with self.subTest(mode=mode, code_ext=code_ext, vars_ext=vars_ext):
                        result = shell_plan(
                            mode,
                            data="/nonexistent data files",
                            extra_env={"OVMF": "", "OVMF_CODE": code, "OVMF_VARS": variables},
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        receipt = json.loads(result.stdout)
                        argv = receipt["argv"]
                        first = argv.index("-drive")
                        self.assertEqual(argv[first : first + 4], firmware_args)
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
            self.assertEqual(
                CLOCK.uefi_clock_receipt(mode, profile, argv, "qemu", "", "data", code, variables)["argv"], argv
            )
            corruptions = []
            for offset, before, after in (
                (1, "readonly=on,", ""),
                (3, "snapshot=on,", ""),
                (1, "unit=0", "unit=1"),
                (3, "unit=1", "unit=0"),
                (1, "format=qcow2", "format=raw"),
                (3, "format=raw", "format=qcow2"),
                (1, "readonly=on", "snapshot=on"),
                (3, "snapshot=on", "readonly=on"),
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
            corruptions += [
                swapped,
                argv[:first] + argv[first + 2 :],
                argv + argv[first : first + 4],
                argv + ["-bios", "other.fd"],
                argv + ["-snapshot"],
                argv + ["-blockdev", "driver=file"],
                argv + ["-icount", "auto"],
                argv + ["-readconfig", "other.conf"],
            ]
            for bad in corruptions:
                with self.assertRaises(ValueError, msg=repr(bad)):
                    CLOCK.uefi_clock_receipt(mode, profile, bad, "qemu", "", "data", code, variables)
            # A correct clock label and argv cannot hide altered semantic inputs.
            for firmware, other_code, other_vars in (
                ("other.fd", code, variables),
                ("", code + ".fd", variables),
                ("", code, variables + ".qcow2"),
            ):
                with self.assertRaises(ValueError):
                    CLOCK.uefi_clock_receipt(mode, profile, argv, "qemu", firmware, "data", other_code, other_vars)

    def test_firmware_contract_rejects_conflicting_partial_and_invalid_paths(self):
        for paths in (
            ("", "", ""),
            ("combined", "code", "vars"),
            ("combined", "code", ""),
            ("combined", "", "vars"),
            ("", "code", ""),
            ("", "", "vars"),
            ("", "same", "same"),
            (None, "", ""),
            ("", [], "vars"),
            ("", "code", 42),
            ("bad\0path", "", ""),
            ("", "bad\0code", "vars"),
        ):
            with self.assertRaises(ValueError):
                CLOCK.expected_firmware_argv(*paths)
        self.assertEqual(
            CLOCK.expected_firmware_argv("combined, firmware.fd", "", ""), ["-bios", "combined, firmware.fd"]
        )

    def test_plans_and_invalid_modes_never_build_execute_qemu_or_write(self):
        with tempfile.TemporaryDirectory(prefix="aurora-clock-plan-") as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            for name in ("kernel-uefi-smoke.sh", "kernel_emulator_clock.py", "uefi-firmware.sh"):
                shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
            sentinel = "#!/usr/bin/env bash\nprintf reached >> unexpected-execution\nexit 99\n"
            for target in (root / "qemu", root / "scripts/kernel-uefi-build.sh"):
                target.write_text(sentinel)
                target.chmod(0o755)
            env = {"QEMU": str(root / "qemu"), "OVMF": str(root / "missing.fd")}

            def snapshot():
                return {
                    str(path.relative_to(root)): (
                        path.stat().st_mode,
                        hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
                    )
                    for path in root.rglob("*")
                }

            before = snapshot()
            for mode in ((), ("normal",), ("budget-smp",)):
                result = shell_plan(*mode, root=root, extra_env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
            split = dict(
                env, OVMF="", OVMF_CODE=str(root / "missing-code.qcow2"), OVMF_VARS=str(root / "missing-vars.fd")
            )
            result = shell_plan("budget", root=root, extra_env=split)
            self.assertEqual(result.returncode, 0, result.stderr)
            for plan in (False, True):
                for modes in (("",), ("future",), ("iommu-event-future",), ("normal", "extra")):
                    result = shell_plan(*modes, root=root, extra_env=env, plan=plan)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertNotIn("is build-only", result.stderr)
                for mode in (
                    "iommu-event-denial",
                    "iommu-event-success",
                    "iommu-event-overflow",
                    "iommu-event-command-error",
                    "iommu-event-observe",
                ):
                    result = shell_plan(mode, root=root, extra_env=env, plan=plan)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertIn(f"UEFI mode '{mode}' is build-only", result.stderr)
                    self.assertIn("generic smoke launcher cannot run Event profiles", result.stderr)
                    self.assertIn(f"UEFI_MODE={mode} ./scripts/kernel-uefi-build.sh", result.stderr)
                    self.assertIn("hosted Event behavior (synthetic transport, no guest DMA)", result.stderr)
                    self.assertIn(
                        "meson test -C <configured-build> iommu-event-source-native --print-errorlogs", result.stderr
                    )
                    self.assertIn("reviewed model/firmware, admitted raw ESP and supervised plan", result.stderr)
                    self.assertIn("docs/iommu-dma-conformance.md", result.stderr)
                    self.assertNotIn("Unknown or ambiguous", result.stderr)
                    # Better guidance must not admit an Event clock or emit a
                    # successful command receipt for this unsupported route.
                    with self.assertRaises(ValueError):
                        CLOCK.uefi_family(mode)
            self.assertEqual(snapshot(), before)

    def test_snapshot_launcher_restores_normal_after_success_and_failure(self):
        # Execute the real launcher with bounded compiler-free stand-ins. This
        # checks EXIT routing only; no firmware, image compiler or guest runs.
        with tempfile.TemporaryDirectory(prefix="aurora-snapshot-restore-") as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "tests").mkdir()
            for name in ("kernel-uefi-smoke.sh", "kernel_emulator_clock.py"):
                shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
            (root / "scripts/uefi-firmware.sh").write_text(
                'uefi_firmware_select() { UEFI_FIRMWARE_COMBINED="$OVMF"; '
                'UEFI_FIRMWARE_CODE=""; UEFI_FIRMWARE_VARS=""; UEFI_FIRMWARE_ARGS=(-bios "$OVMF"); }\n'
            )
            (root / "scripts/kernel-uefi-build.sh").write_text(
                '#!/usr/bin/env bash\nset -eu\nmode="${UEFI_MODE:-normal}"\n'
                'echo "$mode" >> builds\nmkdir -p build/uefi\necho "$mode" > build/uefi/current-image\n'
                'if [[ "$mode" == snapshot* && "${FAIL_BUILD:-0}" == 1 ]]; then exit 7; fi\n'
                'echo "{}" > build/uefi/user-images.json\n'
            )
            (root / "scripts/kernel-uefi-build.sh").chmod(0o755)
            (root / "qemu").write_text('#!/usr/bin/env bash\necho guest >> executions\nexit "$GUEST_STATUS"\n')
            (root / "qemu").chmod(0o755)
            (root / "tests/kernel-snapshot-smoke.py").write_text(
                'import os\nraise SystemExit(int(os.environ["VALIDATOR_STATUS"]))\n'
            )
            for mode, build_fails, guest, validator, wanted in (
                ("snapshot", 0, 33, 0, 0),
                ("snapshot-owner", 0, 35, 0, 0),
                ("snapshot", 0, 33, 9, 9),
                ("snapshot", 1, 33, 0, 7),
            ):
                (root / "builds").write_text("")
                (root / "executions").write_text("")
                result = shell_plan(
                    mode,
                    root=root,
                    plan=False,
                    extra_env={
                        "QEMU": str(root / "qemu"),
                        "OVMF": str(root / "firmware.fd"),
                        "FAIL_BUILD": str(build_fails),
                        "GUEST_STATUS": str(guest),
                        "VALIDATOR_STATUS": str(validator),
                        "UEFI_MODE": "snapshot",
                    },
                )
                self.assertEqual(result.returncode, wanted, result.stdout + result.stderr)
                self.assertEqual((root / "builds").read_text().splitlines(), [mode, "normal"])
                self.assertEqual((root / "build/uefi/current-image").read_text(), "normal\n")
                self.assertEqual((root / "executions").read_text().splitlines(), [] if build_fails else ["guest"])

    def test_plan_firmware_selector_errors_and_unresolved_directory(self):
        with tempfile.TemporaryDirectory(prefix="aurora-clock-firmware-") as directory:
            for extra in (
                {"OVMF_CODE": "code", "OVMF_VARS": "vars"},
                {"OVMF_DIR": directory},
                {"OVMF": "", "OVMF_CODE": "code"},
                {"OVMF": "", "OVMF_VARS": "vars"},
                {"OVMF": "", "OVMF_CODE": "same", "OVMF_VARS": "same"},
                {"OVMF": "", "OVMF_CODE": "code", "OVMF_VARS": "vars", "OVMF_DIR": directory},
            ):
                result = shell_plan("normal", extra_env=extra)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
            result = shell_plan("budget", extra_env={"OVMF": "", "OVMF_DIR": directory})
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("Clock plan unresolved", result.stderr)

    def test_shell_rejects_unknown_empty_and_extra_selections(self):
        for modes in (
            ("",),
            ("budget-new",),
            ("dispatch-new",),
            ("user-new",),
            ("normal", "normal"),
            ("budget", CLOCK.ORIGINAL),
            ("budget", "-icount", "auto"),
            ("--clock-plan",),
        ):
            result = shell_plan(*modes)
            self.assertEqual(result.returncode, 2, repr(modes))
            self.assertEqual(result.stdout, "")
        # No arbitrary clock/argv environment override is recognized.
        for mode in ("normal", "budget-smp"):
            result = shell_plan(
                mode,
                extra_env={
                    "QEMU_ARGS": "-icount auto -smp 1",
                    "QEMU_CLOCK_PROFILE": "auto",
                    "AURORA_QEMU_ARGS": "-icount auto",
                    "AURORA_CLOCK_PROFILE": "tcg-original-clock",
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["clock_profile"], CLOCK.clock_profile("uefi", mode))

    def test_bios_console_guard_precedes_any_build(self):
        with tempfile.TemporaryDirectory(prefix="aurora-bios-clock-guard-") as temp:
            root = Path(temp)
            scripts = root / "scripts"
            scripts.mkdir()
            shutil.copy2(ROOT / "scripts/kernel-smoke.sh", scripts / "kernel-smoke.sh")
            builder = scripts / "kernel-build.sh"
            builder.write_text("#!/bin/sh\nprintf called > build-called\nexit 91\n")
            builder.chmod(0o755)
            for value, expected in (("1", 2), ("0", 91), (None, 91)):
                marker = root / "build-called"
                marker.unlink(missing_ok=True)
                env = dict(os.environ)
                env.pop("KERNEL_CONSOLE", None)
                if value is not None:
                    env["KERNEL_CONSOLE"] = value
                result = subprocess.run(
                    ["bash", str(scripts / "kernel-smoke.sh"), "normal"],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(marker.exists(), expected == 91)

    def test_both_normal_restorations_and_three_capacity_probes(self):
        self.assertEqual(
            CLOCK.AUXILIARY_CLOCKS,
            {
                ("bios-capacity", "full-127"): CLOCK.ORIGINAL,
                ("bios-capacity", "old-96-negative"): CLOCK.ORIGINAL,
                ("bios-capacity", "last-sector-negative"): CLOCK.ORIGINAL,
                ("bios-restoration", "normal"): CLOCK.ORIGINAL,
                ("uefi-restoration", "normal"): CLOCK.ORIGINAL,
            },
        )
        # UEFI normal restoration is the same actual launcher path with no mode.
        default, explicit = shell_plan(), shell_plan("normal")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        self.assertEqual(json.loads(default.stdout), json.loads(explicit.stdout))
        self.assertNotIn("-icount", json.loads(default.stdout)["argv"])
        # BIOS launcher pin includes only the two copied-policy mode additions;
        # its default/restoration command bodies and capacity paths are preserved.
        smoke = (ROOT / "scripts/kernel-smoke.sh").read_bytes()
        self.assertEqual(hashlib.sha256(smoke).hexdigest(), BIOS_SMOKE_SHA256)
        body = smoke[smoke.index(b'mode="${1:-normal}"\n') :]
        self.assertEqual(hashlib.sha256(body).hexdigest(), BIOS_SMOKE_BODY_SHA256)
        for path, digest in UNCHANGED.items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)
        capacity = ast.parse((ROOT / "tests/kernel-boot-capacity.py").read_text())
        smoke = next(node for node in capacity.body if isinstance(node, ast.FunctionDef) and node.name == "smoke")
        fixtures = next(
            node.value
            for node in ast.walk(smoke)
            if isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "fixtures" for t in node.targets)
        )
        self.assertEqual(
            [(row.elts[0].value, row.elts[2].value) for row in fixtures.elts],
            [("full-127", 33), ("old-96-negative", 35), ("last-sector-negative", 35)],
        )
        self.assertNotIn("-icount", ast.get_source_segment((ROOT / "tests/kernel-boot-capacity.py").read_text(), smoke))

    def test_bar_executor_preserves_all_launch_arrays_and_validators(self):
        spec = importlib.util.spec_from_file_location("bar_runner_controls", ROOT / "tests/kernel-uefi-bar-runner.py")
        controls = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controls)
        # Execute the real runner with fake QEMU and recording validators. This
        # checks all eight complete argv arrays, original clock, detached stdin,
        # deadline and required serial/trace/provenance validation after launch.
        check = controls.BarRunner("test_actual_executor_keeps_original_clock_profile_and_mandatory_validators")
        result = unittest.TestResult()
        check.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])

    def test_launcher_executes_validated_array_and_keeps_raw_outcome(self):
        source = (ROOT / "scripts/kernel-uefi-smoke.sh").read_text()
        self.assertEqual(source.count('timeout 30 "${qemu_argv[@]}"'), 1)
        self.assertIn('"${QEMU_DATA:-}" -- "${qemu_argv[@]}"', source)
        self.assertLess(source.index('"${clock_check[@]}" >'), source.index('timeout 30 "${qemu_argv[@]}"'))
        self.assertIn('status=$?\nset -e\ncat "$log"', source)
        tail = source[source.index("status=$?") :]
        self.assertEqual(
            hashlib.sha256(tail.encode()).hexdigest(),
            "7aebac189112cc5f9ada3dc59962c3bd99b21e91e723f58885cbe02d99b0f718",
        )
        self.assertIn("trap 'UEFI_MODE=normal ./scripts/kernel-uefi-build.sh >/dev/null' EXIT", source)
        self.assertEqual(source.count("\ncpus=1\n"), 1)
        self.assertIn('python3 tests/kernel-uefi-budget-smoke.py "$status"', source)
        self.assertIn('python3 tests/kernel-uefi-dispatch-smoke.py "$status"', source)
        self.assertIn('python3 tests/kernel-uefi-user-phases-smoke.py "$status"', source)


if __name__ == "__main__":
    unittest.main()

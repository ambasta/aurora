#!/usr/bin/env python3
"""Closed emulator clock selection and pure effective-command validation.

This module never builds images or executes a guest. The launcher executes the
same array checked here. A clock-plan/receipt is not a runtime success receipt.
"""

import hashlib
import json
import sys

ORIGINAL = "tcg-original-clock"
FIXED0 = "tcg-fixed0-noalign-nosleep"
FIXED0_ARGV = ("-icount", "shift=0,align=off,sleep=off")
SCOPE_MAP_SHA256 = "efd2c6c057d85bdd05cc66b0bbef7db629abdf797361347a96fee6aa1732dc99"

# Exact names, not a prefix rule. Adding a mode requires an explicit decision.
FIXED0_UEFI_MODES = tuple(
    """
budget budget-fault budget-context budget-pending budget-noapic budget-smp
budget-discovery budget-cache budget-alias budget-forged budget-root budget-mmio
budget-softint budget-fpu budget-epoch budget-policy-zero budget-policy-counts
budget-policy-wide budget-policy-output dispatch dispatch-budget dispatch-fault
dispatch-mixed dispatch-pending dispatch-cross-reply dispatch-client-owner
dispatch-stale dispatch-duplicate dispatch-full dispatch-root dispatch-peer-code
dispatch-policy-cursor dispatch-policy-mask dispatch-policy-output user-phases
user-context user-resume user-call user-call-pending user-call-owner user-call-site
user-retire-pending user-request-budget user-completion-budget
user-request-bounds user-completion-bounds user-request-overflow
user-completion-overflow user-pending user-role user-phase user-transaction user-epoch
user-root user-unknown user-stale-grant user-disposal-input user-disposal-output
""".split()
)

ORIGINAL_UEFI_MODES = tuple(
    """
runtime-table-readback runtime-table-reject runtime-table-exhaust
runtime-table-quarantine runtime-pin-cancel runtime-pin-fault runtime-pin-stale
runtime-pin-exhaust runtime-span normal owned-bytes stale stale-exhausted bad-handoff bad-map
bad-table wp nx acpi acpi-two acpi-disabled acpi-checksum acpi-bad-entry acpi-duplicate
acpi-bad-source acpi-changed-header acpi-duplicate-root acpi-write acpi-revoked pci
pci-devices pci-bridge pci-checksum pci-reserved pci-overlap pci-range pci-cycle
pci-write pci-revoked runtime runtime-code runtime-stack runtime-kernel runtime-window
runtime-root runtime-kernel-trap runtime-entry-stack runtime-write runtime-nx
runtime-return runtime-unknown runtime-syscall runtime-sysenter runtime-terminal-input runtime-terminal-output
ipc ipc-fault ipc-cancel
ipc-owner ipc-stale ipc-version ipc-phase ipc-transaction ipc-site ipc-unknown ipc-root
ipc-kernel-trap ipc-duplicate ipc-late ipc-exhausted ipc-policy-request-input
ipc-policy-request-output ipc-policy-cancel-input ipc-policy-cancel-output
snapshot snapshot-fault snapshot-cancel snapshot-owner snapshot-stale snapshot-revoked
snapshot-producer-selector snapshot-producer-quota snapshot-producer-pages
snapshot-reply-reserved snapshot-reply-byte
""".split()
)

ORIGINAL_BIOS_MODES = tuple(
    """
normal --fault --page-fault --wp --nx --stack --no-nx --user-read --user-write
--user-cli --user-code-write --user-nx --user-io --program-bad-return
--program-terminal-input --program-terminal-output --program-unknown-trap --program-kernel-trap
--domain-code --domain-stack
--domain-root-mismatch --schedule --schedule-no-apic --schedule-smp --schedule-forged
--schedule-context --schedule-root --schedule-softint --schedule-fpu --schedule-mmio
--division-zero --division-remainder-zero --division-overflow --division-remainder-min
--division-kernel-trap --unsigned-valid --unsigned-shift-count
--unsigned-conversion-overflow --unsigned-kernel-trap
""".split()
)

ORIGINAL_BAR_MODES = tuple(
    """
bar-state bar-capture bar-inherited bar-read bar-write bar-revoked bar-alias
""".split()
)

ORIGINAL_IVRS_MODES = tuple(
    """
ivrs-default ivrs-read ivrs-write ivrs-revoked ivrs-pair ivrs-alias ivrs-reserved
ivrs-scope ivrs-capability ivrs-range ivrs-missing
""".split()
)


def make_mode_map(groups):
    result = {}
    for family, profile, modes in groups:
        if profile not in (ORIGINAL, FIXED0):
            raise ValueError("Unknown clock profile")
        for mode in modes:
            key = (family, mode)
            if key in result:
                raise ValueError("Duplicate/conflicting clock selection: " + repr(key))
            result[key] = profile
    return result


MODE_CLOCKS = make_mode_map(
    (
        ("uefi", FIXED0, FIXED0_UEFI_MODES),
        ("uefi", ORIGINAL, ORIGINAL_UEFI_MODES),
        ("bios", ORIGINAL, ORIGINAL_BIOS_MODES),
        ("bar", ORIGINAL, ORIGINAL_BAR_MODES),
        ("ivrs", ORIGINAL, ORIGINAL_IVRS_MODES),
    )
)
AUXILIARY_CLOCKS = make_mode_map(
    (
        ("bios-capacity", ORIGINAL, ("full-127", "old-96-negative", "last-sector-negative")),
        ("bios-restoration", ORIGINAL, ("normal",)),
        ("uefi-restoration", ORIGINAL, ("normal",)),
    )
)


def clock_profile(family, mode):
    key = (family, mode)
    if key in MODE_CLOCKS:
        return MODE_CLOCKS[key]
    if key in AUXILIARY_CLOCKS:
        return AUXILIARY_CLOCKS[key]
    raise ValueError("Unknown emulator family/mode: " + repr(key))


def mode_clock_rows():
    return [
        dict(family=family, mode=mode, clock_profile=profile) for (family, mode), profile in sorted(MODE_CLOCKS.items())
    ]


def mode_clock_sha256():
    raw = json.dumps(mode_clock_rows(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def uefi_family(mode):
    # The common launcher historically accepts build modes from these families;
    # the production BAR/IVRS suites keep their separate, unchanged launchers.
    matches = [family for family in ("uefi", "bar", "ivrs") if (family, mode) in MODE_CLOCKS]
    if len(matches) != 1:
        raise ValueError("Unknown or ambiguous UEFI clock mode: " + repr(mode))
    return matches[0]


def validate_clock_options(family, mode, declared_profile, argv):
    """Clock-only check for external, separately command-bound runner receipts."""
    profile = clock_profile(family, mode)
    if declared_profile != profile:
        raise ValueError("Declared clock profile does not match exact mode")
    if type(argv) is not list or not argv or any(type(arg) is not str or not arg or "\0" in arg for arg in argv):
        raise ValueError("Nonempty string argv required")
    clock = []
    for index, arg in enumerate(argv):
        option = arg.split("=", 1)[0].lstrip("-") if arg.startswith("-") else ""
        if option == "icount":
            if arg != "-icount" or index + 1 == len(argv):
                raise ValueError("Noncanonical or missing icount option")
            clock.extend((arg, argv[index + 1]))
        elif option in ("rtc", "readconfig"):
            raise ValueError("Alternate clock/configuration selection forbidden")
    expected = list(FIXED0_ARGV) if profile == FIXED0 else []
    if clock != expected:
        raise ValueError("Missing, duplicate or conflicting effective clock options")
    return profile


def expected_firmware_argv(firmware, code, variables):
    """Bind resolved paths independently of the shell helper's produced argv.

    This pure command check does not establish firmware existence or identity.
    Runtime selection checks files; explicit --clock-plan paths may not exist.
    """
    if any(type(path) is not str or "\0" in path for path in (firmware, code, variables)):
        raise ValueError("Firmware paths must be strings without NUL")
    if firmware and not code and not variables:
        return ["-bios", firmware]
    if not firmware and code and variables and code != variables:
        code_format = "qcow2" if code.endswith(".qcow2") else "raw"
        vars_format = "qcow2" if variables.endswith(".qcow2") else "raw"
        return [
            "-drive",
            "if=pflash,unit=0,format=" + code_format + ",readonly=on,file=" + code.replace(",", ",,"),
            "-drive",
            "if=pflash,unit=1,format=" + vars_format + ",snapshot=on,file=" + variables.replace(",", ",,"),
        ]
    raise ValueError("Expected one combined firmware path or two separate CODE/VARS paths")


def expected_uefi_argv(mode, qemu, firmware, data, code="", variables="", esp="build/uefi/esp"):
    """Independent canonical copy of the closed common-launcher contract."""
    profile = clock_profile(uefi_family(mode), mode)
    argv = [qemu]
    if data:
        argv += ["-L", data]
    devices = {
        "bar-state": ["-device", "nvme,serial=AURORA_READ_ONLY"],
        "pci-devices": [
            "-device",
            "nvme,serial=AURORA_READ_ONLY",
            "-device",
            "qemu-xhci",
            "-device",
            "e1000e,romfile=",
        ],
        "pci-bridge": [
            "-device",
            "pcie-root-port,id=aurora_port,chassis=1,slot=2",
            "-device",
            "nvme,bus=aurora_port,serial=AURORA_READ_ONLY",
        ],
        "pci-cycle": [
            "-device",
            "pcie-root-port,id=aurora_port,chassis=1,slot=2",
            "-device",
            "nvme,bus=aurora_port,serial=AURORA_READ_ONLY",
        ],
    }
    argv += devices.get(mode, [])
    if profile == FIXED0:
        argv += list(FIXED0_ARGV)
    cpu = "qemu64,vendor=GenuineIntel,+sep" if mode == "runtime-sysenter" else "qemu64"
    cpus = "2" if mode in ("acpi-two", "budget-smp") else "1"
    argv += [
        "-machine",
        "q35",
        "-accel",
        "tcg",
        "-cpu",
        cpu,
        "-smp",
        cpus,
        "-m",
        "128M",
        *expected_firmware_argv(firmware, code, variables),
        "-drive",
        f"format=raw,file=fat:ro:{esp},snapshot=on",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "stdio",
        "-monitor",
        "none",
        "-no-reboot",
        "-device",
        "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
    return argv


def uefi_clock_receipt(mode, declared_profile, argv, qemu, firmware, data, code="", variables="", esp="build/uefi/esp"):
    family = uefi_family(mode)
    profile = validate_clock_options(family, mode, declared_profile, argv)
    if argv != expected_uefi_argv(mode, qemu, firmware, data, code, variables, esp):
        raise ValueError("Effective UEFI argv differs from closed command contract")
    return dict(
        schema="aurora-emulator-clock-command-v1",
        family=family,
        mode=mode,
        clock_profile=profile,
        mode_clock_sha256=mode_clock_sha256(),
        scope_map_sha256=SCOPE_MAP_SHA256,
        argv=argv,
        timeout_argv=["timeout", "30", *argv],
        execution_status="not-established-by-command-receipt",
    )


def main(args):
    if len(args) == 2 and args[0] == "profile":
        print(clock_profile(uefi_family(args[1]), args[1]))
        return
    esp = "build/uefi/esp"
    if len(args) >= 12 and args[0] == "verify" and args[8] == "--esp":
        esp = args[9]
        if not esp or any(character in esp for character in (",", "\n", "\r")):
            raise ValueError("Invalid explicit ESP directory")
        args = args[:8] + args[10:]
    if len(args) >= 10 and args[0] == "verify" and args[8] == "--":
        _, mode, profile, qemu, firmware, code, variables, data, _, *argv = args
        print(
            json.dumps(
                uefi_clock_receipt(mode, profile, argv, qemu, firmware, data, code, variables, esp),
                sort_keys=True,
                indent=2,
            )
        )
        return
    raise ValueError(
        "Expected profile MODE or verify MODE PROFILE QEMU OVMF CODE VARS DATA [--esp DIRECTORY] -- QEMU_ARGV"
    )


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except ValueError as error:
        print("Invalid emulator clock contract: " + str(error), file=sys.stderr)
        raise SystemExit(2)

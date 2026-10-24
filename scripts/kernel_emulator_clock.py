#!/usr/bin/env python3
"""Emulator clock selection for guest launches.

Timer-driven UEFI families run with a fixed instruction count so their tick
budgets are deterministic; every other guest uses QEMU's ordinary clock.
"""

import sys

ORIGINAL = "tcg-original-clock"
FIXED0 = "tcg-fixed0-noalign-nosleep"

FIXED0_UEFI_MODES = tuple(
    """
budget budget-fault budget-context budget-pending budget-noapic budget-smp
budget-discovery budget-cache budget-alias budget-forged budget-root budget-mmio
budget-softint budget-fpu budget-epoch
dispatch dispatch-budget dispatch-fault
dispatch-mixed dispatch-pending dispatch-cross-reply dispatch-client-owner
dispatch-stale dispatch-duplicate dispatch-full dispatch-root dispatch-peer-code
user-phases
runtime-console-region runtime-console-region-cancel runtime-console-region-cancel-ready runtime-console-region-input
runtime-console-region-fault runtime-console-region-output runtime-console-region-budget
runtime-owned-text runtime-owned-text-site runtime-owned-text-region runtime-owned-text-stale
user-context user-resume user-call user-call-pending user-call-owner user-call-site
user-ram-file user-ram-file-service-fault user-ram-file-grant user-ram-file-site user-ram-file-settlement
user-ram-file-commit-fault user-ram-file-caller-budget user-ram-file-service-budget user-ram-file-abort-budget
user-ram-file-epochs user-ram-file-pending user-ram-file-frame user-ram-file-root
user-retire-pending user-request-budget user-completion-budget
user-request-bounds user-completion-bounds user-request-overflow
user-completion-overflow user-pending user-role user-phase user-transaction user-epoch
user-root user-unknown user-stale-grant
""".split()
)


def clock_profile(family, mode):
    return FIXED0 if family == "uefi" and mode in FIXED0_UEFI_MODES else ORIGINAL


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "profile":
        raise SystemExit("usage: kernel_emulator_clock.py profile UEFI_MODE")
    print(clock_profile("uefi", sys.argv[2]))

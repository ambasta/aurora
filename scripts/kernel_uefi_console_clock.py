#!/usr/bin/env python3
"""An opt-in interactive command using the existing normal UEFI original clock."""
import json
import sys

import kernel_emulator_clock as clock


def receipt(argv, qemu, firmware, code, variables, data):
    result = clock.uefi_clock_receipt('normal', clock.ORIGINAL, argv, qemu, firmware, data, code, variables)
    result.update(schema='aurora-uefi-console-clock-v1', family='uefi-console', mode='interactive',
                  command_template='normal', timeout_argv=['timeout', '--foreground', '--kill-after=2', '300'] + argv)
    return result


if __name__ == '__main__':
    if len(sys.argv) < 8 or sys.argv[6] != '--':
        raise SystemExit('Expected QEMU OVMF CODE VARS DATA -- QEMU_ARGV')
    try:
        print(json.dumps(receipt(sys.argv[7:], *sys.argv[1:6]), indent=2))
    except ValueError as error:
        raise SystemExit(str(error)) from error

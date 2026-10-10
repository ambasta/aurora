#!/usr/bin/env python3
"""An opt-in interactive command using the existing normal UEFI original clock."""

import argparse
import json
import sys

import kernel_emulator_clock as clock


def receipt(argv, qemu, firmware, code, variables, data, esp="build/uefi/esp"):
    result = clock.uefi_clock_receipt("normal", clock.ORIGINAL, argv, qemu, firmware, data, code, variables, esp=esp)
    result.update(
        schema="aurora-uefi-console-clock-v1",
        family="uefi-console",
        mode="interactive",
        command_template="normal",
        timeout_argv=["timeout", "--foreground", "--kill-after=2", "300"] + argv,
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("qemu", "firmware", "code", "variables", "data"):
        parser.add_argument(name)
    parser.add_argument("--esp", default="build/uefi/esp")
    try:
        separator = sys.argv.index("--")
        args = parser.parse_args(sys.argv[1:separator])
        print(
            json.dumps(
                receipt(
                    sys.argv[separator + 1 :], args.qemu, args.firmware, args.code, args.variables, args.data, args.esp
                ),
                indent=2,
            )
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

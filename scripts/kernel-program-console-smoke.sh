#!/usr/bin/env bash
# Execute a separately reviewed image, preserve raw PTY evidence, restore normal.
set -euo pipefail
cd "$(dirname "$0")/.."
if (( $# > 1 )); then echo 'Expected one reviewed program profile' >&2; exit 2; fi
mode="${1:-program-console}"
if [[ -n "${AURORA_TEST_CONTEXT:-}" || -n "${UEFI_MODE:-}" ]]; then
    echo 'Unset AURORA_TEST_CONTEXT and UEFI_MODE before PTY acceptance.' >&2; exit 2
fi
# Preflight cannot alter the image or start a guest. Never compute this pin here.
python3 -B scripts/kernel_program_console_admission.py reviewed --mode "$mode"
command -v "${QEMU:-qemu-system-x86_64}" >/dev/null
source scripts/uefi-firmware.sh
uefi_firmware_select
restore() {
    local status=$? restored
    trap - EXIT INT TERM
    set +e
    UEFI_MODE=normal MAKEFLAGS=-j1 ./scripts/kernel-uefi-build.sh >build/program-console-restoration.log 2>&1
    restored=$?
    if (( restored != 0 )); then
        cat build/program-console-restoration.log >&2
        echo 'FAIL: normal-image restoration failed' >&2
        if (( status == 0 )); then status=$restored; fi
    fi
    exit "$status"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 -B tests/kernel-program-console-pty.py --mode "$mode"

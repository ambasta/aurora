#!/usr/bin/env bash
# Build, exercise the real bounded PTY acceptance gate, then restore a normal image.
set -euo pipefail
usage() {
    echo 'Usage: scripts/kernel-console-smoke.sh [bios|uefi] (automated 30-second PTY acceptance)'
}
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then usage; exit 0; fi
if [[ $# -gt 1 ]]; then usage >&2; exit 2; fi
mode="${1:-bios}"
case "$mode" in bios|uefi) ;; *) usage >&2; exit 2 ;; esac
cd "$(dirname "$0")/.."
if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
    echo 'Console smoke rejects inherited AURORA_TEST_CONTEXT; run outside supervised native tests.' >&2
    exit 2
fi
for name in "${!KERNEL_TEST_@}" KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE UEFI_CONSOLE_HANDOFF; do
    [[ -n "$name" ]] || continue
    if [[ -n "${!name:-}" ]]; then
        echo "Unset $name before console smoke acceptance." >&2
        exit 2
    fi
done
# Check both emulator and builder dependencies before arming image restoration.
# The PTY test owns its deadline; no timeout wrapper or alternate QEMU recipe is used.
qemu="${QEMU:-qemu-system-x86_64}"
export QEMU="$qemu"
cxx="${CXX:-g++}"
required=("$qemu" "$cxx" make as ld objcopy nm python3)
if [[ "$mode" == uefi ]]; then required+=(objdump readelf); fi
if [[ -n "${AURORAC:-}" ]]; then required+=("$AURORAC"); fi
for tool in "${required[@]}"; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
if [[ -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
    echo 'QEMU_DATA must name an existing directory.' >&2
    exit 2
fi
if [[ "$mode" == uefi ]]; then
    source ./scripts/uefi-firmware.sh
    uefi_firmware_select
    source ./scripts/uefi-linker.sh
    uefi_linker_select
fi
restore_normal_image() {
    local status=$? restore_status
    trap - EXIT INT TERM
    set +e
    if [[ "$mode" == uefi ]]; then
        UEFI_MODE=normal ./scripts/kernel-uefi-build.sh
    else
        KERNEL_CONSOLE=0 ./scripts/kernel-build.sh
    fi
    restore_status=$?
    if (( restore_status != 0 )); then
        echo "FAIL: normal $mode image restoration exited $restore_status" >&2
        if (( status == 0 )); then status=$restore_status; fi
    fi
    exit "$status"
}
# Only a started console-image build can need restoration. Preflight failures
# above do not build or alter either image, including through this exit trap.
trap restore_normal_image EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Keep builds synchronous: Bash defers these traps until the foreground build
# completes, including when INT/TERM is sent only to this wrapper. Do not use
# an interruptible background wait that could restore over a surviving build.
if [[ "$mode" == uefi ]]; then
    UEFI_MODE=console ./scripts/kernel-uefi-build.sh
    python3 -B tests/kernel-console-pty.py --uefi
else
    KERNEL_CONSOLE=1 ./scripts/kernel-build.sh
    python3 -B tests/kernel-console-pty.py
fi

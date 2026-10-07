#!/usr/bin/env bash
# Disposable opt-in UEFI console: original clock, LAPIC-woken UART polling.
set -euo pipefail
if [[ $# != 0 ]]; then
    echo 'Usage: scripts/kernel-uefi-console.sh (five-minute session limit)' >&2
    exit 2
fi
cd "$(dirname "$0")/.."
if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
    echo 'Run this interactive session outside the supervised native tests.' >&2
    exit 2
fi
for name in "${!KERNEL_TEST_@}" KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE UEFI_CONSOLE_HANDOFF; do
    [[ -n "$name" ]] || continue
    if [[ -n "${!name:-}" ]]; then
        echo "Unset $name before starting the interactive console." >&2
        exit 2
    fi
done
qemu="${QEMU:-qemu-system-x86_64}"
for tool in "$qemu" timeout python3; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
source ./scripts/uefi-firmware.sh
uefi_firmware_select
args=()
if [[ -n "${QEMU_DATA:-}" ]]; then
    [[ -d "$QEMU_DATA" ]] || { echo 'QEMU_DATA must name an existing directory.' >&2; exit 2; }
    args+=(-L "$QEMU_DATA")
fi
UEFI_MODE=console ./scripts/kernel-uefi-build.sh
qemu_argv=("$qemu" "${args[@]}" -machine q35 -accel tcg -cpu qemu64 -smp 1 -m 128M
    "${UEFI_FIRMWARE_ARGS[@]}" -drive format=raw,file=fat:ro:build/uefi/esp,snapshot=on
    -nic none -display none -serial stdio -monitor none -no-reboot
    -device isa-debug-exit,iobase=0xf4,iosize=0x04)
python3 scripts/kernel_uefi_console_clock.py "$qemu" "$UEFI_FIRMWARE_COMBINED" \
    "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}" -- "${qemu_argv[@]}" \
    >build/uefi/console.clock.json
echo 'UEFI serial console in QEMU: type help or exit. Timer-woken polling; five-minute session limit.'
set +e
timeout --foreground --kill-after=2 300 "${qemu_argv[@]}"
status=$?
set -e
if [[ "$status" == 33 ]]; then exit 0; fi
if [[ "$status" == 124 ]]; then echo 'Console session reached its five-minute limit.' >&2; fi
exit "$status"

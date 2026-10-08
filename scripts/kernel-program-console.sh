#!/usr/bin/env bash
# Launch only an already built and independently reviewed exact image.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# != 0 ]]; then echo 'Usage: scripts/kernel-program-console.sh (already reviewed image)' >&2; exit 2; fi
if [[ -n "${AURORA_TEST_CONTEXT:-}" || -n "${UEFI_MODE:-}" ]]; then
    echo 'Unset AURORA_TEST_CONTEXT and UEFI_MODE before interactive launch.' >&2; exit 2
fi
python3 -B scripts/kernel_program_console_admission.py reviewed --mode program-console
qemu="${QEMU:-qemu-system-x86_64}"
for tool in "$qemu" timeout python3; do command -v "$tool" >/dev/null; done
source scripts/uefi-firmware.sh
uefi_firmware_select
args=()
if [[ -n "${QEMU_DATA:-}" ]]; then args+=(-L "$QEMU_DATA"); fi
command=("$qemu" "${args[@]}" -machine q35 -accel tcg -cpu qemu64 -smp 1 -m 128M
    "${UEFI_FIRMWARE_ARGS[@]}" -drive format=raw,file=fat:ro:build/uefi/esp,snapshot=on
    -nic none -display none -serial stdio -monitor none -no-reboot
    -device isa-debug-exit,iobase=0xf4,iosize=0x04)
python3 -B scripts/kernel_uefi_console_clock.py "$qemu" "$UEFI_FIRMWARE_COMBINED" \
    "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}" -- "${command[@]}" \
    >build/uefi/program-console-interactive.clock.json
printf 'Protected Aurora console: upper, then a line of text; exit closes QEMU.\n'
set +e
timeout --foreground --kill-after=2 300 "${command[@]}"
status=$?
set -e
if [[ "$status" == 33 ]]; then exit 0; fi
exit "$status"

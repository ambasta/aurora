#!/usr/bin/env bash
# Routine developer launch: rebuild and automatically admit the local image.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/kernel-program-console-common.sh
if [[ $# != 0 ]]; then program_console_fail 'usage: scripts/kernel-program-console.sh'; exit 1; fi
program_console_controls program-console
program_console_preflight
command -v timeout >/dev/null || { program_console_blocked 'missing dependency: timeout'; exit 2; }
if UEFI_MODE=program-console ./scripts/kernel-uefi-build.sh; then :; else
    status=$?; echo "FAIL: protected-console image build/admission exited $status" >&2; exit "$status"
fi
python3 -B scripts/kernel_program_console_admission.py checked --mode program-console
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
echo "FAIL: protected console guest exited $status" >&2
# A clean host exit without the guest's debug-exit success is not a pass.
if [[ "$status" == 0 ]]; then exit 1; fi
exit "$status"

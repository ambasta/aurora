#!/usr/bin/env bash
# Routine developer launch: rebuild and automatically admit the local image.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/kernel-program-console-common.sh
if [[ $# != 0 ]]; then program_console_fail 'usage: scripts/kernel-program-console.sh'; exit 1; fi
program_console_controls program-console
program_console_preflight
command -v timeout >/dev/null || { program_console_blocked 'missing dependency: timeout'; exit 2; }
if image_dir="$(UEFI_MODE=program-console ./scripts/kernel-uefi-build.sh --print-image-dir)"; then :; else
    status=$?; echo "FAIL: protected-console image build/admission exited $status" >&2; exit "$status"
fi
python3 -B scripts/kernel_program_console_admission.py checked --mode program-console --build-dir "$image_dir"
mapfile -d '' -t command < <(python3 -B scripts/qemu_transport.py argv --platform uefi \
    --mode program-console --image "$image_dir/esp" --qemu "$qemu" --data "${QEMU_DATA:-}" \
    --firmware "$UEFI_FIRMWARE_COMBINED" --code "$UEFI_FIRMWARE_CODE" --vars "$UEFI_FIRMWARE_VARS")
(( ${#command[@]} )) || { program_console_fail 'empty QEMU command'; exit 1; }
python3 -B scripts/kernel_uefi_console_clock.py "$qemu" "$UEFI_FIRMWARE_COMBINED" \
    "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}" --esp "$image_dir/esp" -- "${command[@]}" \
    >"$image_dir/program-console-interactive.clock.json"
printf 'Protected Aurora console: upper, then a line of text; exit closes QEMU.\n'
set +e
python3 -B scripts/qemu_transport.py run --foreground --timeout 300 -- "${command[@]}"
status=$?
set -e
if [[ "$status" == 33 ]]; then exit 0; fi
echo "FAIL: protected console guest exited $status" >&2
# A clean host exit without the guest's debug-exit success is not a pass.
if [[ "$status" == 0 ]]; then exit 1; fi
exit "$status"

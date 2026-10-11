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
if [[ -n "${QEMU_DATA:-}" && ! -d "$QEMU_DATA" ]]; then
    echo 'QEMU_DATA must name an existing directory.' >&2; exit 2
fi
image_dir="$(UEFI_MODE=console ./scripts/kernel-uefi-build.sh --print-image-dir)"
mapfile -d '' -t qemu_argv < <(python3 -B scripts/qemu_transport.py argv --platform uefi \
    --mode console --image "$image_dir/esp" --qemu "$qemu" --data "${QEMU_DATA:-}" \
    --firmware "$UEFI_FIRMWARE_COMBINED" --code "$UEFI_FIRMWARE_CODE" --vars "$UEFI_FIRMWARE_VARS")
(( ${#qemu_argv[@]} )) || { echo 'FAIL: empty QEMU command' >&2; exit 2; }
python3 scripts/kernel_uefi_console_clock.py "$qemu" "$UEFI_FIRMWARE_COMBINED" \
    "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}" --esp "$image_dir/esp" -- "${qemu_argv[@]}" \
    >"$image_dir/console.clock.json"
echo 'UEFI serial console in QEMU: type help or exit. Timer-woken polling; five-minute session limit.'
set +e
python3 -B scripts/qemu_transport.py run --foreground --timeout 300 -- "${qemu_argv[@]}"
status=$?
set -e
if [[ "$status" == 33 ]]; then exit 0; fi
if [[ "$status" == 124 ]]; then echo 'Console session reached its five-minute limit.' >&2; fi
exit "$status"

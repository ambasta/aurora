#!/usr/bin/env bash
# Current-source build/check and bounded disposable graphical guests.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} == --help ]]; then
    echo 'Usage: scripts/kernel-graphical-smoke.sh [--build-only]'
    echo 'Build/check three current images, then smoke graphical guests and restore normal UEFI.'
    echo 'Build-only prints retained images for independent review before a separate runner invocation.'
    exit 0
fi
[[ $# == 0 || ( $# == 1 && $1 == --build-only ) ]] || { echo 'Invalid graphical smoke arguments' >&2; exit 2; }
for name in "${!KERNEL_TEST_@}" AURORA_TEST_CONTEXT KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE UEFI_CONSOLE_HANDOFF; do
    [[ -z "$name" || -z "${!name:-}" ]] || { echo "Unset $name before graphical smoke" >&2; exit 2; }
done
qemu="${QEMU:-qemu-system-x86_64}"
for tool in "$qemu" "${CXX:-g++}" make as ld objcopy objdump nm readelf python3; do
    command -v "$tool" >/dev/null || { echo "BLOCKED: missing dependency: $tool" >&2; exit 2; }
done
source scripts/uefi-firmware.sh
uefi_firmware_select
source scripts/uefi-linker.sh
uefi_linker_select
mkdir -p build/graphical-smoke
window=$(mktemp -d "$PWD/build/graphical-smoke/run-XXXXXX")
echo "Graphical smoke files: $window"
for mode in normal graphical-console graphical-console-capture; do
    UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh >"$window/build-$mode.log" 2>&1 || {
        echo "FAIL: $mode build/admission; see $window/build-$mode.log" >&2; exit 1;
    }
    python3 -B scripts/kernel_graphical_smoke.py --stage "$mode" --images "$window/images"
done
[[ ${1:-} != --build-only ]] || exit 0
exec python3 -B scripts/kernel_graphical_smoke.py --images "$window/images" --evidence "$window/guests" \
    "$qemu" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}"

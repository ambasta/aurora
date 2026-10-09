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
[[ ! -L build && ! -L build/uefi && ! -L build/graphical-smoke ]] || {
    echo 'FAIL: symlink in shared graphical build paths' >&2; exit 2;
}
mkdir -p build/graphical-smoke
window=$(mktemp -d "$PWD/build/graphical-smoke/run-XXXXXX")
echo "Graphical smoke files: $window"
restore_shared_image() {
    local status=$? restored
    trap - EXIT INT TERM
    set +e
    {
        if [[ -L build || -L build/uefi ]]; then
            echo 'FAIL: symlink in shared UEFI restoration path' >&2; false
        else
            if [[ -e build/uefi ]]; then mv -- build/uefi "$window/last-build"; fi &&
                UEFI_MODE=normal ./scripts/kernel-uefi-build.sh
        fi
    } >"$window/build-normal-restoration.log" 2>&1
    restored=$?
    if (( restored != 0 )); then
        echo "FAIL: shared normal UEFI image restoration exited $restored; see $window/build-normal-restoration.log" >&2
        if (( status == 0 )); then status=$restored; fi
    else
        echo "PASS: shared normal UEFI image restored; see $window/build-normal-restoration.log"
    fi
    exit "$status"
}
# Only started builds need restoration. Keep children synchronous so a handled
# interruption cannot rebuild over a still-running builder or abandon a guest.
trap restore_shared_image EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Admission inventories the whole object directory: retain old/partial outputs
# outside it rather than mixing stale graphical objects into a normal rebuild.
if [[ -e build/uefi ]]; then mv -- build/uefi "$window/previous-build"; fi
for mode in normal graphical-console graphical-console-capture; do
    if UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh >"$window/build-$mode.log" 2>&1; then :; else
        status=$?; echo "FAIL: $mode build/admission exited $status; see $window/build-$mode.log" >&2; exit "$status"
    fi
    python3 -B scripts/kernel_graphical_smoke.py --stage "$mode" --images "$window/images"
done
[[ ${1:-} != --build-only ]] || exit 0
python3 -B scripts/kernel_graphical_smoke.py --images "$window/images" --evidence "$window/guests" \
    "$qemu" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}"

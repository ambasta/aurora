#!/usr/bin/env bash
# Current-source build/check and bounded disposable graphical guests.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} == --help ]]; then
    echo 'Usage: scripts/kernel-graphical-smoke.sh [--build-only]'
    echo 'Build/check three current images, then smoke graphical guests and restore normal UEFI.'
    echo 'Build-only prints retained images for independent review before a separate runner invocation.'
    echo 'Retains the latest 2 successful and 2 failed runs; AURORA_GRAPHICAL_KEEP_RUNS=N or all overrides this.'
    echo 'Successful runs keep logs and summaries; full dumps remain on failure or explicit keep.'
    echo 'Set AURORA_GRAPHICAL_KEEP_RUNS=all or create RUN/.keep before dump removal to keep successful dumps.'
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
python3 -B scripts/kernel_graphical_smoke.py --start-run "$window"
finish_run() {
    local status=$?
    trap - EXIT INT TERM
    set +e
    python3 -B scripts/kernel_graphical_smoke.py --finish-run "$window" --status "$status" || {
        echo "FAIL: graphical smoke retention; evidence remains in $window" >&2
        if (( status == 0 )); then status=1; fi
    }
    exit "$status"
}
# Keep failure artifacts in their native profile directories; retain run logs
# and staged images under the same managed-window policy.
trap finish_run EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
for mode in normal graphical-console graphical-console-capture; do
    if image_dir="$(UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh --print-image-dir 2>"$window/build-$mode.log")"; then :; else
        status=$?; echo "FAIL: $mode build/admission exited $status; see $window/build-$mode.log" >&2; exit "$status"
    fi
    python3 -B scripts/kernel_graphical_smoke.py --stage "$mode" --build-dir "$image_dir" --images "$window/images"
done
[[ ${1:-} != --build-only ]] || exit 0
python3 -B scripts/kernel_graphical_smoke.py --images "$window/images" --evidence "$window/guests" \
    "$qemu" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}"

#!/usr/bin/env bash
# Developer preview: automatic current-source checks, no external review pins.
set -euo pipefail
cd "$(dirname "$0")/.."
fail() { echo "FAIL: framebuffer preview: $*" >&2; exit 1; }
blocked() { echo "BLOCKED: framebuffer preview: $*" >&2; exit 2; }
if [[ $# == 1 && "$1" == --help ]]; then
    echo 'Build/check and capture an emulator-only framebuffer preview under build/. Not qualified evidence.'
    echo '--full-smoke runs all four framebuffer cases and an actual normal boot.'
    exit 0
fi
modes=(framebuffer)
options=()
if [[ $# == 1 && "$1" == --full-smoke ]]; then
    modes=(framebuffer framebuffer-record framebuffer-permissions framebuffer-stale)
    options=(--full-smoke)
else
    [[ $# == 0 ]] || fail 'usage: scripts/kernel-framebuffer-preview.sh [--help|--full-smoke]'
fi
for name in "${!KERNEL_TEST_@}" AURORA_TEST_CONTEXT KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE UEFI_CONSOLE_HANDOFF; do
    [[ -n "$name" ]] || continue
    [[ -z "${!name:-}" ]] || fail "unset $name before capture"
done
qemu="${QEMU:-qemu-system-x86_64}"
for tool in "$qemu" "${CXX:-g++}" make as ld objcopy objdump nm readelf python3; do
    command -v "$tool" >/dev/null || blocked "missing dependency: $tool"
done
if [[ -n "${AURORAC:-}" ]]; then
    command -v "$AURORAC" >/dev/null || blocked "missing AURORAC: $AURORAC"
fi
[[ -z "${QEMU_DATA:-}" || -d "$QEMU_DATA" ]] || blocked 'QEMU_DATA directory is unavailable'
# Invalid selectors are input failures; missing tools/firmware are prerequisites.
if [[ -n "${OVMF:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" || -n "${OVMF_DIR:-}" ) ]] ||
   [[ -n "${OVMF_DIR:-}" && ( -n "${OVMF_CODE:-}" || -n "${OVMF_VARS:-}" ) ]]; then
    fail 'choose only one firmware selector'
fi
if [[ -n "${OVMF_CODE:-}" && -z "${OVMF_VARS:-}" || -z "${OVMF_CODE:-}" && -n "${OVMF_VARS:-}" ]]; then
    fail 'OVMF_CODE and OVMF_VARS must be supplied together'
fi
if [[ -n "${OVMF_CODE:-}" && ( "$OVMF_CODE" == "$OVMF_VARS" || "$OVMF_CODE" -ef "$OVMF_VARS" ) ]]; then
    fail 'OVMF_CODE and OVMF_VARS must be separate files'
fi
source scripts/uefi-firmware.sh
uefi_firmware_select || blocked 'UEFI firmware unavailable'
source scripts/uefi-linker.sh
uefi_linker_select || blocked 'UEFI PE linker unavailable'
python3 -B scripts/kernel_framebuffer_preview.py --preflight
image_dir=
profile_root=
for mode in "${modes[@]}"; do
    if selected="$(UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh --print-image-dir)"; then :; else
        status=$?; echo "FAIL: framebuffer $mode image build/admission exited $status" >&2; exit "$status"
    fi
    if [[ ${#options[@]} != 0 ]]; then
        [[ ${selected##*/} == "$mode" ]] || fail 'unexpected native framebuffer profile'
        [[ -z "$profile_root" || ${selected%/*} == "$profile_root" ]] || fail 'profiles selected different native builds'
        profile_root=${selected%/*}
    fi
    if [[ "$mode" == framebuffer ]]; then image_dir=$selected; fi
done
exec python3 -B scripts/kernel_framebuffer_preview.py "${options[@]}" --build-dir "$image_dir" "$qemu" "$UEFI_FIRMWARE_COMBINED" \
    "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS" "${QEMU_DATA:-}"

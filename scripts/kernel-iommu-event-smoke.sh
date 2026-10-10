#!/usr/bin/env bash
# Supplied custom Event model; ordinary firmware/QEMU restore the normal image.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} == --help ]]; then
    echo 'Usage: scripts/kernel-iommu-event-smoke.sh [--build-only]'
    echo 'Fresh four-profile Event image/FAT checks and bounded guests, then exact normal restoration.'
    echo 'Set EVENT_BUILD_RECEIPT, EVENT_CODE, EVENT_VARS, EVENT_DATA; ordinary QEMU/OVMF controls restore normal.'
    echo 'GNU mtools 4.0.48 required (MTOOLS_DIR optional); EVENT_ESP_DIR can supply validated current raw ESPs.'
    echo 'Evidence uses a new external directory under EVENT_OUTPUT_PARENT (default temporary directory).'
    exit 0
fi
[[ $# == 0 || ( $# == 1 && $1 == --build-only ) ]] || { echo 'Invalid Event smoke arguments' >&2; exit 2; }
firmware=()
if [[ ${1:-} != --build-only ]]; then
    source scripts/uefi-firmware.sh
    uefi_firmware_select
    firmware=(--normal-firmware "$UEFI_FIRMWARE_COMBINED" --normal-code "$UEFI_FIRMWARE_CODE" --normal-vars "$UEFI_FIRMWARE_VARS")
fi
exec python3 -B scripts/kernel_iommu_event_smoke.py "$@" "${firmware[@]}"

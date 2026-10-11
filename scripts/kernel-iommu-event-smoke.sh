#!/usr/bin/env bash
# Supplied custom Event model; ordinary firmware/QEMU restore the normal image.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} == --help ]]; then
    echo 'Usage: scripts/kernel-iommu-event-smoke.sh [--build-only]'
    echo 'Fresh four-profile Event image/FAT checks and bounded guests, then exact normal restoration.'
    echo 'Set EVENT_TOOL_PREFIX for packaged Event tools, or EVENT_BUILD_RECEIPT/CODE/VARS/DATA for external inputs.'
    echo 'Ordinary QEMU/OVMF controls boot normal afterward.'
    echo 'GNU mtools 4.0.48 required (MTOOLS_DIR optional); EVENT_ESP_DIR can supply validated current raw ESPs.'
    echo 'Evidence is retained in a fresh build/aurora-event-smoke-* directory by default; EVENT_OUTPUT_PARENT overrides it.'
    exit 0
fi
[[ $# == 0 || ( $# == 1 && $1 == --build-only ) ]] || { echo 'Invalid Event smoke arguments' >&2; exit 2; }
firmware=()
if [[ ${1:-} != --build-only ]]; then
    source scripts/uefi-firmware.sh
    uefi_firmware_select || {
        echo 'BLOCKED: Event developer smoke requires ordinary OVMF for normal restoration.' >&2
        exit 2
    }
    firmware=(--normal-firmware "$UEFI_FIRMWARE_COMBINED" --normal-code "$UEFI_FIRMWARE_CODE" --normal-vars "$UEFI_FIRMWARE_VARS")
fi
exec python3 -B scripts/kernel_iommu_event_smoke.py "$@" "${firmware[@]}"

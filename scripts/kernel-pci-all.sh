#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in pci pci-devices pci-bridge pci-checksum pci-reserved pci-overlap pci-range pci-cycle pci-write pci-revoked; do
    ./scripts/kernel-uefi-smoke.sh "$mode"
done

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in acpi acpi-two acpi-disabled acpi-checksum acpi-bad-source acpi-duplicate-root acpi-write acpi-revoked; do
    ./scripts/kernel-uefi-smoke.sh "$mode"
done

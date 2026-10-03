#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in --schedule --schedule-no-apic --schedule-smp --schedule-forged --schedule-context --schedule-root --schedule-softint --schedule-fpu --schedule-mmio; do
    ./scripts/kernel-smoke.sh "$mode"
done

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in budget budget-fault budget-context budget-pending budget-noapic budget-smp budget-discovery budget-cache budget-alias budget-forged budget-root budget-mmio budget-softint budget-fpu budget-epoch budget-policy-zero budget-policy-counts budget-policy-wide budget-policy-output; do
 ./scripts/kernel-uefi-smoke.sh "$mode"
done

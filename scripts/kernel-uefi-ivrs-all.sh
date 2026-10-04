#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORA_IVRS_RECEIPTS:?Set a fresh output directory for IVRS receipts}"
for mode in ivrs-default ivrs-read ivrs-write ivrs-revoked ivrs-pair ivrs-alias ivrs-reserved ivrs-scope ivrs-capability ivrs-range ivrs-missing; do
    python3 scripts/kernel-uefi-ivrs-run.py "$mode" --output "$AURORA_IVRS_RECEIPTS/$mode"
done

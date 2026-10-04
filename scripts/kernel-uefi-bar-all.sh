#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORA_BAR_RECEIPTS:?Set a new output directory for complete BAR receipts}"
for mode in bar-state bar-capture bar-inherited bar-read bar-write bar-revoked bar-alias; do
    python3 scripts/kernel-uefi-bar-run.py "$mode" --output "$AURORA_BAR_RECEIPTS/$mode"
done

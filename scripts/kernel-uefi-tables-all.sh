#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in runtime-table-readback runtime-table-reject runtime-table-exhaust runtime-table-quarantine; do
    ./scripts/kernel-uefi-smoke.sh "$mode"
done

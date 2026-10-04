#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in runtime-pin-cancel runtime-pin-fault runtime-pin-stale runtime-pin-exhaust; do
    ./scripts/kernel-uefi-smoke.sh "$mode"
done

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in normal stale stale-exhausted bad-handoff bad-map bad-table wp nx; do
    ./scripts/kernel-uefi-smoke.sh "$mode"
done

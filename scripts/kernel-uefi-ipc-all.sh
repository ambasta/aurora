#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in ipc ipc-fault ipc-cancel ipc-owner ipc-stale ipc-version ipc-phase ipc-transaction ipc-site ipc-unknown ipc-root ipc-kernel-trap ipc-duplicate ipc-late ipc-exhausted; do
 ./scripts/kernel-uefi-smoke.sh "$mode"
done

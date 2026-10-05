#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in ipc ipc-fault ipc-cancel ipc-owner ipc-stale ipc-version ipc-phase ipc-transaction ipc-site ipc-unknown ipc-root ipc-kernel-trap ipc-duplicate ipc-late ipc-exhausted ipc-policy-request-input ipc-policy-request-output ipc-policy-cancel-input ipc-policy-cancel-output; do
 ./scripts/kernel-uefi-smoke.sh "$mode"
done

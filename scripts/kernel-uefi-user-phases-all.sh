#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in user-phases user-context user-retire-pending user-request-budget user-completion-budget user-request-bounds user-completion-bounds user-request-overflow user-completion-overflow user-pending user-role user-phase user-transaction user-epoch user-root user-unknown user-stale-grant; do
 ./scripts/kernel-uefi-smoke.sh "$mode"
done

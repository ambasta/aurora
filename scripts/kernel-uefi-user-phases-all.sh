#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in user-phases user-context user-retire-pending user-request-budget user-completion-budget user-request-bounds user-completion-bounds user-request-overflow user-completion-overflow user-pending user-role user-phase user-transaction user-epoch user-root user-unknown user-stale-grant user-disposal-input user-disposal-output user-ram-file user-ram-file-service-fault user-ram-file-grant user-ram-file-site user-ram-file-settlement user-ram-file-commit-fault user-ram-file-caller-budget user-ram-file-service-budget user-ram-file-abort-budget user-ram-file-epochs user-ram-file-pending user-ram-file-frame user-ram-file-root; do
 ./scripts/kernel-uefi-smoke.sh "$mode"
done

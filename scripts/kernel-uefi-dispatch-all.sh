#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in dispatch dispatch-budget dispatch-fault dispatch-mixed dispatch-pending dispatch-cross-reply dispatch-client-owner dispatch-stale dispatch-duplicate dispatch-full dispatch-root dispatch-peer-code; do
 ./scripts/kernel-uefi-smoke.sh "$mode"
done

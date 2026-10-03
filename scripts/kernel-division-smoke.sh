#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in --division-zero --division-remainder-zero --division-overflow \
    --division-remainder-min --division-kernel-trap; do
    ./scripts/kernel-smoke.sh "$mode"
done
# Run the restored ordinary image after all division variants.
./scripts/kernel-smoke.sh normal
echo 'PASS: all 5 actual CPU division gates and restored normal boot'

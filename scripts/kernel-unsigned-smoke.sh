#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in --unsigned-valid --unsigned-shift-count --unsigned-conversion-overflow --unsigned-kernel-trap; do
    ./scripts/kernel-smoke.sh "$mode"
done
./scripts/kernel-smoke.sh normal
echo 'PASS: all 4 actual CPU unsigned gates and restored normal boot'

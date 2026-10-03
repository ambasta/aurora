#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in normal --fault --page-fault --wp --nx --stack --no-nx \
    --user-read --user-write --user-cli --user-code-write --user-nx --user-io; do
    ./scripts/kernel-smoke.sh "$mode"
done
echo 'PASS: all 13 actual CPU protection/exception/controlled-user gates'

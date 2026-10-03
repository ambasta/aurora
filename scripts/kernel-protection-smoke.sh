#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in normal --fault --page-fault --wp --nx --stack --no-nx \
    --user-read --user-write --user-cli --user-code-write --user-nx --user-io \
    --program-bad-return --program-unknown-trap --program-kernel-trap \
    --domain-code --domain-stack --domain-root-mismatch; do
    ./scripts/kernel-smoke.sh "$mode"
done
echo 'PASS: all 19 actual CPU protection/exception/private-domain gates'

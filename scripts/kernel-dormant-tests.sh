#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# -le 1 ]] || { echo 'Expected at most one private output directory' >&2; exit 2; }
output="${1:-build/kernel-dormant-$(date +%s%N)}"
python3 scripts/kernel-dormant-tests.py "$output"

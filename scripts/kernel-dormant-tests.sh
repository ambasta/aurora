#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
output="build/kernel-dormant-$(date +%s%N)"
python3 scripts/kernel-dormant-tests.py "$output"

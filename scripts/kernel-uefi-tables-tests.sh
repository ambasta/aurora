#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -O tests/kernel-uefi-tables-smoke.py
python3 tests/kernel-uefi-tables-stack.py --self-test

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -O tests/kernel-uefi-pin-smoke.py

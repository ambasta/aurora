#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/kernel-uefi-smoke.sh runtime-span

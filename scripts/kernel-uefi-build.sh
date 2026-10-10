#!/usr/bin/env bash
# Legacy environment selectors feed the canonical native Meson graph.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# != 0 && ( $# != 1 || $1 != --print-image-dir ) ]]; then
    echo 'Usage: scripts/kernel-uefi-build.sh [--print-image-dir]' >&2
    exit 2
fi
profile="$(python3 -B scripts/kernel_profiles.py --select uefi)"
exec python3 -B scripts/meson_test.py --kernel uefi --profile "$profile" "$@"

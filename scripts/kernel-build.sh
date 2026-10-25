#!/usr/bin/env bash
# Build the BIOS profile selected by the environment (default normal).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# != 0 && ( $# != 1 || $1 != --print-image-dir ) ]]; then
    echo 'Usage: scripts/kernel-build.sh [--print-image-dir]' >&2
    exit 2
fi
profile="$(python3 -B scripts/kernel_profiles.py --select bios)"
directory="$(scripts/kernel-image.sh bios "$profile")"
if [[ $# == 1 ]]; then echo "$directory"; else echo "Built BIOS $profile image in $directory"; fi

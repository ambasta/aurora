#!/usr/bin/env bash
# Build one BIOS profile or fixture mode (default normal).
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -gt 2 || ( $# == 2 && $2 != --print-image-dir ) ]]; then
    echo 'Usage: scripts/kernel-build.sh [PROFILE] [--print-image-dir]' >&2
    exit 2
fi
profile=normal print=false
for argument in "$@"; do
    if [[ $argument == --print-image-dir ]]; then print=true; else profile=$argument; fi
done
directory="$(scripts/kernel-image.sh bios "$profile")"
if $print; then echo "$directory"; else echo "Built BIOS $profile image in $directory"; fi

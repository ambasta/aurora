#!/usr/bin/env bash
# Build one kernel image profile and print its directory on stdout:
#   scripts/kernel-image.sh bios|uefi PROFILE
set -euo pipefail
cd "$(dirname "$0")/.."
(( $# == 2 )) || { echo 'usage: scripts/kernel-image.sh bios|uefi PROFILE' >&2; exit 2; }
platform=$1 profile=$2
build=${MESON_BUILD_DIR:-build/meson}
if [[ ! -f $build/build.ninja ]]; then
    echo "No configured build at $build; see compiler/README.md#source-bootstrap" >&2
    exit 2
fi
canonical=$(python3 -B scripts/kernel_profiles.py --canonical "$platform" "$profile")
scripts/watchdog.sh meson compile -C "$build" "kernel-$platform-$profile" >&2
directory=$(realpath "$build/kernel-images/$platform/$canonical")
# The directory is passed to QEMU drive options, which split on commas.
[[ $directory != *,* ]] || { echo "Kernel image path contains a comma: $directory" >&2; exit 2; }
echo "$directory"

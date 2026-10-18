#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for mode in runtime runtime-multipage runtime-terminal-input runtime-terminal-output runtime-code runtime-stack runtime-kernel runtime-window runtime-root runtime-kernel-trap runtime-entry-stack runtime-write runtime-nx runtime-return runtime-unknown runtime-syscall runtime-sysenter; do
    ./scripts/kernel-uefi-smoke.sh "$mode"
done

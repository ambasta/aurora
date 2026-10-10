#!/usr/bin/env bash
# Build the selected native profile, then run its protected-console guest oracle.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/kernel-program-console-common.sh
if (( $# > 1 )); then
    program_console_fail 'usage: scripts/kernel-program-console-smoke.sh [PROFILE]'; exit 1
fi
mode="${1:-program-console}"
program_console_controls "$mode"
program_console_preflight
trap 'exit 130' INT
trap 'exit 143' TERM
if image_dir="$(UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh --print-image-dir)"; then :; else
    status=$?; echo "FAIL: protected-console image build/admission exited $status" >&2; exit "$status"
fi
args=(--mode "$mode" --build-dir "$image_dir")
if python3 -B tests/kernel-program-console-pty.py "${args[@]}"; then :; else
    status=$?; echo "FAIL: protected-console PTY exited $status" >&2; exit "$status"
fi

#!/usr/bin/env bash
# Routine smoke rebuilds locally; explicit qualification uses reviewed prebuilt bytes.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/kernel-program-console-common.sh
qualification=false
if [[ "${1:-}" == --qualification ]]; then qualification=true; shift; fi
if (( $# > 1 )); then
    program_console_fail 'usage: scripts/kernel-program-console-smoke.sh [--qualification] [PROFILE]'; exit 1
fi
mode="${1:-program-console}"
program_console_controls "$mode"
# Reviewed qualification never rebuilds or restages the approved image before
# execution. In particular, no local digest is computed to manufacture approval.
if [[ "$qualification" == true ]]; then
    command -v python3 >/dev/null || { program_console_blocked 'missing dependency: python3'; exit 2; }
    python3 -B scripts/kernel_program_console_admission.py reviewed --mode "$mode"
fi
program_console_preflight
# Isolated local builds and reviewed prebuilt images need no destructive rebuild.
trap 'exit 130' INT
trap 'exit 143' TERM
args=(--mode "$mode")
if [[ "$qualification" == true ]]; then
    args+=(--qualification)
else
    if image_dir="$(UEFI_MODE="$mode" ./scripts/kernel-uefi-build.sh --print-image-dir)"; then :; else
        status=$?; echo "FAIL: protected-console image build/admission exited $status" >&2; exit "$status"
    fi
    args+=(--build-dir "$image_dir")
fi
if python3 -B tests/kernel-program-console-pty.py "${args[@]}"; then :; else
    status=$?; echo "FAIL: protected-console PTY exited $status" >&2; exit "$status"
fi

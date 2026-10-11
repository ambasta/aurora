#!/usr/bin/env bash
# Compatibility alias for the UEFI interactive console.
set -euo pipefail
if (( $# )); then echo 'Usage: scripts/kernel-uefi-console.sh (five-minute session limit)' >&2; exit 2; fi
exec "$(dirname "$0")/kernel-run.sh" uefi --console

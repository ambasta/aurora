#!/usr/bin/env bash
# Compatibility alias for the BIOS interactive console.
set -euo pipefail
if (( $# )); then echo 'Usage: scripts/kernel-console.sh (BIOS serial console; five-minute session limit)' >&2; exit 2; fi
exec "$(dirname "$0")/kernel-run.sh" bios --console

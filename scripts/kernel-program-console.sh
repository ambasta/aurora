#!/usr/bin/env bash
# Compatibility alias for the protected interactive console.
set -euo pipefail
if (( $# )); then echo 'FAIL: protected console: usage: scripts/kernel-program-console.sh' >&2; exit 1; fi
exec "$(dirname "$0")/kernel-run.sh" program-console --console

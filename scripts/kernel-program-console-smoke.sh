#!/usr/bin/env bash
# Compatibility alias for protected-console PTY acceptance.
set -euo pipefail
if (( $# > 1 )); then echo 'FAIL: protected console: usage: scripts/kernel-program-console-smoke.sh [PROFILE]' >&2; exit 1; fi
case "${1:-program-console}" in
    program-*) ;;
    *) echo "FAIL: protected console: unknown profile: $1" >&2; exit 1 ;;
esac
exec "$(dirname "$0")/kernel-run.sh" "${1:-program-console}" --smoke

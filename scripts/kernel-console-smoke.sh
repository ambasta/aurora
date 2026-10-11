#!/usr/bin/env bash
# Compatibility alias for ordinary console PTY acceptance.
set -euo pipefail
usage() { echo 'Usage: scripts/kernel-console-smoke.sh [bios|uefi] (automated 30-second PTY acceptance)'; }
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then usage; exit 0; fi
if (( $# > 1 )); then usage >&2; exit 2; fi
case "${1:-bios}" in bios|uefi) ;; *) usage >&2; exit 2 ;; esac
exec "$(dirname "$0")/kernel-run.sh" "${1:-bios}-console" --smoke

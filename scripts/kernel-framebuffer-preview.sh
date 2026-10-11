#!/usr/bin/env bash
set -euo pipefail
if [[ $# == 1 && "$1" == --help ]]; then exec "$(dirname "$0")/kernel-run.sh" --help; fi
[[ $# == 0 || ( $# == 1 && $1 == --full-smoke ) ]] || { echo 'FAIL: framebuffer preview: usage: scripts/kernel-framebuffer-preview.sh [--help|--full-smoke]' >&2; exit 1; }
exec "$(dirname "$0")/kernel-run.sh" framebuffer "$@"

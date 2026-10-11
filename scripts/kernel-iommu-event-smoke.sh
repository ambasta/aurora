#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} == --help ]]; then exec "$(dirname "$0")/kernel-run.sh" --help; fi
[[ $# == 0 || ( $# == 1 && $1 == --build-only ) ]] || { echo 'Invalid Event smoke arguments' >&2; exit 2; }
exec "$(dirname "$0")/kernel-run.sh" iommu-event "$@"

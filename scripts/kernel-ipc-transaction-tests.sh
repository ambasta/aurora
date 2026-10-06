#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${AURORAC:-}" || $# != 2 ]]; then
    printf '%s\n' 'Supply AURORAC and exactly one --compiler-sha256 DIGEST or --developer-build-receipt FILE pair; use make test-ipc-transaction for a fresh build.' >&2
    exit 2
fi
case "$1" in
    --compiler-sha256|--developer-build-receipt) identity=("$1" "$2") ;;
    *) printf '%s\n' 'Invalid compiler identity mode' >&2; exit 2 ;;
esac
compiler="$AURORAC"
python3 -B -O tests/kernel-ipc-transition-native.py --compiler "$compiler" "${identity[@]}" \
    --candidate-cap-mib "${IPC_TRANSACTION_CAP_MIB:-128}"

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${AURORAC:-}" || $# != 2 ]]; then
    printf '%s\n' 'Supply AURORAC and --compiler-sha256 DIGEST; Meson runs native-policy-ipc-transition with its selected compiler.' >&2
    exit 2
fi
case "$1" in
    --compiler-sha256) identity=("$1" "$2") ;;
    *) printf '%s\n' 'Invalid compiler identity mode' >&2; exit 2 ;;
esac
compiler="$AURORAC"
python3 -B -O tests/kernel-ipc-transition-native.py --compiler "$compiler" "${identity[@]}" \
    --candidate-cap-mib "${IPC_TRANSACTION_CAP_MIB:-128}"

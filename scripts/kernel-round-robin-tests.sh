#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${AURORAC:-}" || $# != 2 ]]; then
    printf '%s\n' 'Supply AURORAC and exactly one --compiler-sha256 DIGEST or --developer-build-receipt FILE pair; use make test-round-robin for a fresh build.' >&2
    exit 2
fi
case "$1" in
    --compiler-sha256|--developer-build-receipt) identity=("$1" "$2") ;;
    *) printf '%s\n' 'Invalid compiler identity mode' >&2; exit 2 ;;
esac
compiler="$AURORAC"
python3 -B -O tests/kernel-round-robin-native.py --compiler "$compiler" "${identity[@]}" \
    --candidate-cap-mib "${ROUND_ROBIN_TEST_CAP_MIB:-128}"
mkdir -p build/uefi
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
    tests/kernel-round-robin-adapter.cpp -o build/uefi/kernel-round-robin-adapter-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/kernel-round-robin-adapter-test

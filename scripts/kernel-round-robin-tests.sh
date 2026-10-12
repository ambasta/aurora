#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${AURORAC:-}" || $# != 2 ]]; then
    printf '%s\n' 'Supply AURORAC and --compiler-sha256 DIGEST; Meson runs native-policy-round-robin with its selected compiler.' >&2
    exit 2
fi
case "$1" in
    --compiler-sha256) identity=("$1" "$2") ;;
    *) printf '%s\n' 'Invalid compiler identity mode' >&2; exit 2 ;;
esac
compiler="$AURORAC"
python3 -B -O tests/kernel-round-robin-native.py --compiler "$compiler" "${identity[@]}" \
    --candidate-cap-mib "${ROUND_ROBIN_TEST_CAP_MIB:-128}"
mkdir -p build/uefi
"$compiler" --module-root kernel/policies examples/kernel.au -o build/uefi/round-robin-adapter-language.s
as --64 build/uefi/round-robin-adapter-language.s -o build/uefi/round-robin-adapter-language.o
# Replace ONLY the selection producer in this mutation test. Real Mailbox
# transitions still execute the generated Aurora transaction policy.
objcopy --redefine-sym aurora_kernel_round_robin_next=aurora_kernel_round_robin_next_real \
    build/uefi/round-robin-adapter-language.o build/uefi/round-robin-adapter-substitute.o
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
    tests/kernel-round-robin-adapter.cpp build/uefi/round-robin-adapter-substitute.o -o build/uefi/kernel-round-robin-adapter-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/kernel-round-robin-adapter-test

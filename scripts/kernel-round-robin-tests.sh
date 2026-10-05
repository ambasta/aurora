#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
python3 -B -O tests/kernel-round-robin-native.py --compiler "$compiler" \
    --compiler-sha256 "$(sha256sum "$compiler" | cut -d ' ' -f 1)" \
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

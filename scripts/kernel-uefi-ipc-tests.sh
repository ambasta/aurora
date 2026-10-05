#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
"$compiler" --module-root kernel/policies examples/kernel.au -o "build/uefi/ipc-language.s"
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" -no-pie tests/kernel-ipc.cpp build/uefi/ipc-language.s -o build/uefi/kernel-ipc-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/kernel-ipc-test
python3 -O tests/kernel-uefi-ipc-image.py
python3 -O tests/kernel-uefi-ipc-smoke.py --self-test

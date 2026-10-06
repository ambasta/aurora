#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
"${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Werror -fno-pie -no-pie "${flags[@]}" tests/kernel-uefi.cpp -o build/uefi/policy-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/policy-test

python3 -O tests/kernel-uefi-smoke.py --self-test

./scripts/kernel-uefi-memory-tests.sh

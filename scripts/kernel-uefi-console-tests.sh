#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
"${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
    tests/kernel-uefi-console-context.cpp -o build/kernel-uefi-console-context-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/kernel-uefi-console-context-test
python3 tests/kernel-uefi-console-clock.py

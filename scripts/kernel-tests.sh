#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
for test in pages protection; do
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" "tests/kernel-$test.cpp" -o "build/kernel-$test-test"
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/kernel-$test-test"
done
python3 tests/kernel-smoke.py --self-test

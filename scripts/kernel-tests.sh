#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" tests/kernel-pages.cpp -o build/kernel-pages-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/kernel-pages-test
python3 tests/kernel-smoke.py --self-test

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" tests/kernel-program.cpp -o build/kernel-division-policy-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/kernel-division-policy-test
python3 tests/kernel-division-image.py
python3 tests/kernel-division-smoke.py --self-test
python3 -O tests/kernel-division-image.py
python3 -O tests/kernel-division-smoke.py --self-test

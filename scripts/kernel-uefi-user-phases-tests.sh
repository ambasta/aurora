#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
for source in kernel-uefi-user-run kernel-client-disposal; do
 g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" "tests/$source.cpp" -o "build/uefi/$source-test"
 ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/uefi/$source-test"
done
python3 -O tests/kernel-uefi-user-phases-image.py
python3 -O tests/kernel-uefi-user-phases-smoke.py --self-test

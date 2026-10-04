#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
flags=(-std=c++23 -O1 -g -Wall -Wextra -Werror -DNDEBUG)
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
for name in bar bar-record; do
    g++ "${flags[@]}" "tests/kernel-uefi-$name.cpp" -o "build/uefi/$name-policy-test"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/uefi/$name-policy-test"
done
python3 -O tests/kernel-uefi-bar-smoke.py --self-test
python3 -O tests/kernel-uefi-bar-trace.py --self-test
python3 -O tests/kernel-uefi-bar-provenance.py --self-test

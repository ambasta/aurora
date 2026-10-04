#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
flags=(-std=c++23 -O1 -g -Wall -Wextra -Werror -DNDEBUG)
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
g++ "${flags[@]}" tests/kernel-uefi-ivrs.cpp -o build/uefi/ivrs-policy-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/ivrs-policy-test
python3 -O tests/kernel-uefi-ivrs-stack.py --self-test
python3 -O tests/kernel-uefi-ivrs-smoke.py --self-test
python3 -O tests/kernel-uefi-ivrs-trace.py --self-test
python3 -O tests/kernel-uefi-ivrs-provenance.py --self-test

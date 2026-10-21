#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
flags=(-DAURORA_RUNTIME_IMAGE_POLICY=one_page)
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Werror "${flags[@]}" tests/kernel-pci.cpp -o build/uefi/pci-policy-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/pci-policy-test
python3 -O tests/kernel-pci-smoke.py --self-test

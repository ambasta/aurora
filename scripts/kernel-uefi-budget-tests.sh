#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
"$compiler" --module-root kernel/policies examples/kernel.au -o "build/uefi/service-budget-language.s"
flags=(-DAURORA_RUNTIME_IMAGE_POLICY=one_page)
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" tests/kernel-uefi-service-budget.cpp build/uefi/service-budget-language.s -o build/uefi/kernel-service-budget-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/kernel-service-budget-test
python3 -O tests/kernel-uefi-budget-image.py
python3 -O tests/kernel-uefi-budget-smoke.py --self-test

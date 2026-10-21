#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
"$compiler" --module-root kernel/policies examples/kernel.au -o "build/uefi/dispatch-language.s"
flags=(-DAURORA_RUNTIME_IMAGE_POLICY=one_page)
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
for source in kernel-uefi-dispatch-layout kernel-dispatch; do
 g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" "tests/$source.cpp" "build/uefi/dispatch-language.s" -o "build/uefi/$source-test"
 ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/uefi/$source-test"
done
python3 -O tests/kernel-uefi-dispatch-image.py
python3 -O tests/kernel-uefi-dispatch-smoke.py --self-test

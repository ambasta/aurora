#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -j1 -C compiler; fi
"$compiler" --module-root kernel/policies examples/kernel-bios.au -o build/terminal-event-language.s
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
for source in kernel-program-layout kernel-uefi-runtime; do
 g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" "tests/$source.cpp" -no-pie build/terminal-event-language.s -o "build/uefi/$source-test"
 ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/uefi/$source-test"
done
python3 -O tests/kernel-uefi-user-image.py
python3 -O tests/kernel-uefi-runtime-smoke.py --self-test

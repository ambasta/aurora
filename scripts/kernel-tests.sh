#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -j1 -C compiler; fi
"$compiler" --module-root kernel/policies examples/kernel-bios.au -o build/terminal-event-language.s
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
for test in pages protection program program-layout domain schedule; do
g++ -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" "tests/kernel-$test.cpp" -no-pie build/terminal-event-language.s -o "build/kernel-$test-test"
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/kernel-$test-test"
done
python3 tests/kernel-smoke.py --self-test

python3 tests/kernel-schedule-smoke.py --self-test

# Same real page allocator, with the bounded CPU-only byte-owner adapter.
./scripts/kernel-owned-bytes-tests.sh

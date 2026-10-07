#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
"$compiler" --module-root kernel/policies examples/kernel-console.au -o build/console-policy-test.s
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
"${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
    tests/kernel-console.cpp build/console-policy-test.s -o build/kernel-console-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/kernel-console-test
for test in presentation uart; do
    "${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
        "tests/kernel-console-$test.cpp" build/console-policy-test.s -o "build/kernel-console-$test-test"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/kernel-console-$test-test"
done

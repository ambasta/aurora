#!/usr/bin/env bash
# Compiler-free copied-stream and two-role authority checks; never starts a guest.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/program-console
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
for name in stream run-authority; do
    "${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
        "tests/kernel-program-$name.cpp" -o "build/program-console/$name-test"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/program-console/$name-test"
done
python3 -B tests/kernel-program-admission.py
python3 -B -O tests/kernel-program-admission.py

python3 -B tests/kernel-program-console-routing.py
python3 -B tests/kernel-program-console-transcript.py
python3 -B -O tests/kernel-program-console-transcript.py

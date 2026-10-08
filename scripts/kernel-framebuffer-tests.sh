#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
for test in framebuffer framebuffer-tables framebuffer-loader framebuffer-pixels; do
    "${CXX:-g++}" -std=c++23 -O1 -Wall -Wextra -Wpedantic -Werror -no-pie \
        "tests/kernel-uefi-$test.cpp" -o "build/kernel-uefi-$test-test"
    "build/kernel-uefi-$test-test"
done
python3 -B tests/kernel_framebuffer_probe_oracle.py
"${CXX:-g++}" -std=c++23 -O1 -Wall -Wextra -Wpedantic -Werror \
    tests/kernel-display-session.cpp -o build/kernel-display-session-test
build/kernel-display-session-test
python3 -B tests/kernel-framebuffer-admission.py
python3 -B tests/test_framebuffer_capture.py

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
build_dir="${KERNEL_OWNED_BYTES_BUILD_DIR:-build/kernel-owned-bytes}"
mkdir -p "$build_dir"
flags=(-std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -DNDEBUG -fno-exceptions -fno-rtti -no-pie)
case "${SANITIZE:-0}" in
    0) ;;
    1) flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer) ;;
    *) echo 'FAIL: SANITIZE must be 0 or 1' >&2; exit 1 ;;
esac
# The real adapter and allocator are instrumented; no generated Aurora assembly
# participates in this focused host gate. LeakSanitizer is explicitly excluded.
"${CXX:-g++}" "${flags[@]}" -DAURORA_KERNEL_BYTES_TESTING=1 \
    tests/kernel-owned-bytes.cpp kernel/owned-bytes.cpp -o "$build_dir/kernel-owned-bytes-test"
ASAN_OPTIONS="${ASAN_OPTIONS:+$ASAN_OPTIONS:}detect_leaks=0:halt_on_error=1:abort_on_error=1" \
UBSAN_OPTIONS="${UBSAN_OPTIONS:+$UBSAN_OPTIONS:}halt_on_error=1:print_stacktrace=1" \
    "$build_dir/kernel-owned-bytes-test"

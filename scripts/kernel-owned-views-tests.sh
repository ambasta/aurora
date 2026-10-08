#!/usr/bin/env bash
# Focused exact-source host replay; no compiler build and no guest execution.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORAC:?Set AURORAC to the explicitly selected current-source compiler}"
[[ -x "$AURORAC" ]] || { echo 'Selected AURORAC is not executable' >&2; exit 2; }
build_dir="${KERNEL_OWNED_VIEWS_BUILD_DIR:-build/kernel-owned-views}"
mkdir -p "$build_dir"
"$AURORAC" examples/kernel-owned-bytes.au -o "$build_dir/language.s"
as --64 "$build_dir/language.s" kernel/uefi/owned-bytes-entry.S -o "$build_dir/language.o"
python3 -B tests/kernel-uefi-owned-bytes-admission.py "$build_dir/language.o"
flags=(-std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -DNDEBUG -fno-exceptions -fno-rtti -no-pie)
case "${SANITIZE:-0}" in
    0) ;;
    1) flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer) ;;
    *) echo 'FAIL: SANITIZE must be 0 or 1' >&2; exit 1 ;;
esac
"${CXX:-g++}" "${flags[@]}" tests/kernel-uefi-owned-views.cpp kernel/owned-bytes.cpp \
    "$build_dir/language.o" -o "$build_dir/native"
for mode in 0 1 2; do
    ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1" \
    UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" "$build_dir/native" "$mode"
done
"${CXX:-g++}" "${flags[@]}" -DAURORA_OWNED_VIEW_ZERO_LENGTH_CONTROL=1 \
    tests/kernel-uefi-owned-views.cpp kernel/owned-bytes.cpp "$build_dir/language.o" \
    -Wl,--wrap=__au_runtime_bytes_borrow_length -o "$build_dir/rejected-zero-length"
set +e
ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1" \
UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" \
    "$build_dir/rejected-zero-length" 0 > "$build_dir/zero-length.stdout" 2> "$build_dir/zero-length.stderr"
status=$?
set -e
[[ "$status" == 1 && ! -s "$build_dir/zero-length.stdout" ]] || { echo 'FAIL: zero-length poisoning was not rejected' >&2; exit 1; }
expected='FAIL UEFI owner-view fixture: unexpected result for independently supplied length'
[[ "$(cat "$build_dir/zero-length.stderr")" == "$expected" ]] || { echo 'FAIL: wrong zero-length rejection' >&2; exit 1; }
echo 'PASS: nonempty-to-empty readonly-view poisoning rejected'

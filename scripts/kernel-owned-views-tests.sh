#!/usr/bin/env bash
# Focused exact-source host replay; no compiler build and no guest execution.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORAC:?Set AURORAC to the explicitly selected current-source compiler}"
[[ -x "$AURORAC" ]] || { echo 'Selected AURORAC is not executable' >&2; exit 2; }
build_dir="${KERNEL_OWNED_VIEWS_BUILD_DIR:-build/kernel-owned-views}"
mkdir -p "$build_dir"
"$AURORAC" --module-root library examples/kernel-owned-bytes.au -o "$build_dir/language.s"
as --64 "$build_dir/language.s" kernel/uefi/owned-bytes-entry.S -o "$build_dir/language.o"
python3 -B tests/kernel-uefi-owned-bytes-admission.py "$build_dir/language.o"
wrappers=(-Wl,--wrap=__au_runtime_bytes_allocate -Wl,--wrap=__au_runtime_bytes_drop)
flags=(-std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -DNDEBUG -fno-exceptions -fno-rtti -no-pie)
case "${SANITIZE:-0}" in
    0) ;;
    1) flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer) ;;
    *) echo 'FAIL: SANITIZE must be 0 or 1' >&2; exit 1 ;;
esac
"${CXX:-g++}" "${flags[@]}" "${wrappers[@]}" tests/kernel-uefi-owned-views.cpp kernel/owned-bytes.cpp \
    "$build_dir/language.o" -o "$build_dir/native"
for mode in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16; do
    ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1" \
    UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" "$build_dir/native" "$mode"
done
"${CXX:-g++}" "${flags[@]}" "${wrappers[@]}" -DAURORA_OWNED_VIEW_ZERO_LENGTH_CONTROL=1 \
    tests/kernel-uefi-owned-views.cpp kernel/owned-bytes.cpp "$build_dir/language.o" \
    -Wl,--wrap=__au_runtime_bytes_borrow_span -o "$build_dir/rejected-zero-length"
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

"${CXX:-g++}" "${flags[@]}" "${wrappers[@]}" -DAURORA_RAM_SECTOR_ALIAS_CONTROL=1 \
    tests/kernel-uefi-owned-views.cpp kernel/owned-bytes.cpp "$build_dir/language.o" \
    -Wl,--wrap=__au_runtime_bytes_set -o "$build_dir/rejected-page-alias"
set +e
ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1" \
UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" \
    "$build_dir/rejected-page-alias" 8 > "$build_dir/page-alias.stdout" 2> "$build_dir/page-alias.stderr"
status=$?
set -e
[[ "$status" == 1 && ! -s "$build_dir/page-alias.stdout" ]] || { echo 'FAIL: page alias was not rejected' >&2; exit 1; }
expected='FAIL UEFI owner-view fixture: independent complete storage byte pattern'
[[ "$(cat "$build_dir/page-alias.stderr")" == "$expected" ]] || { echo 'FAIL: wrong page-alias rejection' >&2; exit 1; }
echo 'PASS: logical storage page alias rejected'

# Corrupt the actual private-ABI result after the real producer returns. Both
# success and failure must inspect the real bytes, including byte 63 and canaries.
for damage in 1 2 3; do
    "${CXX:-g++}" "${flags[@]}" "${wrappers[@]}" "-DAURORA_COPIED_RECORD_DAMAGE_CONTROL=$damage" \
        tests/kernel-uefi-owned-views.cpp kernel/owned-bytes.cpp "$build_dir/language.o" \
        -Wl,--wrap=__au_runtime_bytes_kernel_produce -o "$build_dir/rejected-copy-$damage"
    case "$damage" in
        1) expected='FAIL UEFI owner-view fixture: copied record every actual payload byte after close and reuse' ;;
        2) expected='FAIL UEFI owner-view fixture: copied record result canaries' ;;
        3) expected='FAIL UEFI owner-view fixture: copied record closed status' ;;
    esac
    for mode in 11 12 13 14; do
        set +e
        ASAN_OPTIONS="detect_leaks=0:halt_on_error=1:abort_on_error=1" \
        UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" \
            "$build_dir/rejected-copy-$damage" "$mode" > "$build_dir/copy-$damage-$mode.stdout" \
            2> "$build_dir/copy-$damage-$mode.stderr"
        status=$?
        set -e
        [[ "$status" == 1 && ! -s "$build_dir/copy-$damage-$mode.stdout" ]] || { echo 'FAIL: copied-result damage accepted' >&2; exit 1; }
        [[ "$(cat "$build_dir/copy-$damage-$mode.stderr")" == "$expected" ]] || { echo 'FAIL: wrong copied-result rejection' >&2; exit 1; }
    done
done
echo 'PASS: actual copied success/failure payload, canary and status damage rejected'

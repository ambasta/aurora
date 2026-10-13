#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORAC:?Set AURORAC to the explicitly selected current-source compiler; alternatively use meson test -C BUILD native-kernel-ipc native-kernel-program-mailbox}"
[[ -x "$AURORAC" ]] || { echo 'Selected AURORAC is not executable' >&2; exit 2; }
mkdir -p build/uefi
python3 -B scripts/meson-native-fixture.py --compiler "$AURORAC" \
    --source examples/kernel-program-console.au --module-root kernel/policies --module-root library \
    --local-symbols --referenced-reflection-only \
    --bridge kernel/uefi/program-note-entry.S --bridge kernel/uefi/kernel-policy-entry.S \
    --object build/uefi/ipc-language.o --depfile build/uefi/ipc-language.d
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer); fi
"${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" -no-pie tests/kernel-ipc.cpp build/uefi/ipc-language.o -o build/uefi/kernel-ipc-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/kernel-ipc-test
"${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror "${flags[@]}" -no-pie \
    tests/kernel-program-mailbox.cpp build/uefi/ipc-language.o -o build/uefi/kernel-program-mailbox-test
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/kernel-program-mailbox-test
python3 -O tests/kernel-uefi-ipc-image.py
python3 -O tests/kernel-uefi-ipc-smoke.py --self-test

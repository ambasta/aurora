#!/usr/bin/env bash
# Selected-compiler copied-stream and two-role authority checks; no guest.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${AURORAC:?Set AURORAC to the explicitly selected current-source compiler; alternatively use meson test -C BUILD native-kernel-program-stream native-kernel-program-run-authority}"
[[ -x "$AURORAC" ]] || { echo 'Selected AURORAC is not executable' >&2; exit 2; }
mkdir -p build/program-console
python3 -B scripts/meson-native-fixture.py --compiler "$AURORAC" \
    --source examples/kernel-program-console.au --module-root kernel/policies --module-root library \
    --local-symbols --referenced-reflection-only \
    --bridge kernel/uefi/program-note-entry.S --bridge kernel/uefi/kernel-policy-entry.S \
    --object build/program-console/language.o --depfile build/program-console/language.d
flags=()
if [[ "${SANITIZE:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
for name in stream run-authority; do
    language=()
    if [[ "$name" == stream ]]; then language+=(build/program-console/language.o); fi
    "${CXX:-g++}" -std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -no-pie "${flags[@]}" \
        "tests/kernel-program-$name.cpp" "${language[@]}" -o "build/program-console/$name-test"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/program-console/$name-test"
done
python3 -B -O tests/kernel-program-admission.py

python3 -B tests/kernel-program-console-routing.py
python3 -B -O tests/kernel-program-console-transcript.py

python3 -B -O tests/kernel-program-console-entrypoints.py

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cxx="${CXX:-g++}"
for tool in "$cxx" as nm readelf mktemp rm; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
as --64 kernel/uefi/memory.S -o "$work/memory.o"
# Disable hosted builtins so the tests exercise the actual assembly entrypoints.
"$cxx" -std=c++23 -O2 -Wall -Wextra -Werror -fno-builtin tests/kernel-uefi-memory.cpp "$work/memory.o" -o "$work/memory-test"
"$work/memory-test"
# No unresolved helpers or relocations, including recursive compiler lowering.
unresolved=$(nm -u "$work/memory.o")
test -z "$unresolved"
relocations=$(LC_ALL=C readelf -rW "$work/memory.o")
[[ "$relocations" == *'There are no relocations in this file.'* ]]
printf '%s\n' "$relocations"

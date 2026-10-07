#!/usr/bin/env bash
# Repeat the same build-only gates on each supported x86-64 Linux host.
set -euo pipefail
if [[ $# == 1 && ( "$1" == --help || "$1" == -h ) ]]; then
    echo 'Usage: scripts/host-build-check.sh'
    echo 'Build and check compiler, BIOS and UEFI with CXX and optional UEFI_LD.'
    echo 'Requires installed build dependencies; no QEMU, downloads or installation.'
    exit 0
fi
if [[ $# != 0 ]]; then echo 'Usage: scripts/host-build-check.sh' >&2; exit 2; fi
if [[ -n "${AURORA_TEST_CONTEXT:-}" ]]; then
    echo 'Run this standalone host check outside an active supervised test run.' >&2
    exit 2
fi
# This entrypoint checks fresh normal builds, never a stale pin or dry/ignored run.
for name in AURORAC OUT MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES \
            "${!KERNEL_TEST_@}" KERNEL_USER_PROBE_MODE KERNEL_CONSOLE UEFI_MODE; do
    [[ -n "$name" ]] || continue
    if [[ -n "${!name:-}" ]]; then
        echo "Unset $name before this standalone normal host build check." >&2
        exit 2
    fi
done
cd "$(dirname "$0")/.."
cxx="${CXX:-g++}"
for tool in "$cxx" make as ld objcopy objdump nm readelf python3; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }
done
source ./scripts/uefi-linker.sh
uefi_linker_select
export CXX="$cxx" UEFI_LD="$UEFI_LINKER"
for tool in "$cxx" as ld "$UEFI_LINKER"; do
    version=$("$tool" --version)
    printf '%s: %s\n' "$tool" "${version%%$'\n'*}"
done
# Toolchain changes are not Make dependencies; never reuse another lane's compiler.
make -C compiler --always-make
make kernel
make kernel-uefi
make test-uefi
make test-developer-commands
printf 'PASS: host compiler/BIOS/UEFI build and focused checks (no emulator or full native aggregate)\n'

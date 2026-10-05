#!/usr/bin/env bash
# Link only the disposable BIOS sector, independently of host ELF defaults.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$#" != 2 ]]; then
    echo 'Usage: scripts/kernel-boot-link.sh INPUT.o OUTPUT.bin' >&2
    exit 2
fi
ld -m elf_i386 --build-id=none --orphan-handling=error -T kernel/boot.ld "$1" -o "$2"

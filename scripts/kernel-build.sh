#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
for tool in g++ make as ld objcopy nm python3; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }; done
make -C compiler
build/aurorac examples/kernel.au -o build/kernel-language.s
as --64 build/kernel-language.s -o build/kernel-language.o
as --32 kernel/boot.S -o build/boot.o
ld -m elf_i386 -Ttext 0x7c00 --oformat binary -e _boot build/boot.o -o build/boot.bin
as --64 kernel/start.S -o build/start.o
as --64 kernel/exceptions.S -o build/exceptions.o
extra=()
if [[ "${KERNEL_TEST_DIVIDE_ERROR:-0}" == 1 ]]; then extra+=(-DAURORA_TEST_DIVIDE_ERROR); fi
if [[ "${KERNEL_TEST_PAGE_FAULT:-0}" == 1 ]]; then extra+=(-DAURORA_TEST_PAGE_FAULT); fi
for source in main interrupts; do
g++ -std=c++23 -Wall -Wextra -Werror -O2 -ffreestanding -fno-exceptions -fno-rtti \
    -fno-stack-protector -fno-pie -fno-asynchronous-unwind-tables -fno-unwind-tables \
    -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns "${extra[@]}" -c "kernel/$source.cpp" -o "build/kernel-$source.o"
done
ld -nostdlib -z max-page-size=0x1000 -T kernel/link.ld \
    build/start.o build/exceptions.o build/kernel-interrupts.o build/kernel-main.o build/kernel-language.o -o build/kernel.elf
objcopy -O binary build/kernel.elf build/kernel.bin
python3 tests/kernel-image.py
printf 'Built build/aurora.img (raw emulator disk) and build/kernel.elf\n'

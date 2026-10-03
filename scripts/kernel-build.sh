#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build
for tool in g++ make as ld objcopy nm python3; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }; done
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
command -v "$compiler" >/dev/null || { echo "Missing compiler: $compiler" >&2; exit 2; }
division_fixture="${KERNEL_TEST_DIVISION:-none}"
case "$division_fixture" in
    none|zero|remainder-zero|overflow|remainder-min|kernel-trap) ;;
    *) echo 'Invalid division fixture' >&2; exit 2 ;;
esac
if [[ "$division_fixture" != none && "${KERNEL_TEST_SCHEDULE:-0}" == 1 ]]; then
    echo 'Division fixtures require the sequential user-program gate' >&2; exit 2
fi
"$compiler" examples/kernel.au -o build/kernel-language.s
as --64 build/kernel-language.s -o build/kernel-language.o
as --32 kernel/boot.S -o build/boot.o
ld -m elf_i386 -Ttext 0x7c00 --oformat binary -e _boot build/boot.o -o build/boot.bin
as --64 kernel/start.S -o build/start.o
as --64 kernel/exceptions.S -o build/exceptions.o
as --64 kernel/user.S -o build/user.o
program_asm_flags=()
for flag in BAD_RETURN UNKNOWN_TRAP FOREIGN_CODE FOREIGN_STACK SOFTINT FPU APIC_READ; do
    variable="KERNEL_TEST_PROGRAM_${flag}"
    if [[ "${!variable:-0}" == 1 ]]; then program_asm_flags+=(--defsym "AURORA_PROGRAM_${flag}=1"); fi
done
as --64 "${program_asm_flags[@]}" kernel/program-entry.S -o build/program-entry.o
program_index=0
for program in clean bounds overflow; do
    base=$((0x1b0000 + program_index * 4096))
    input="tests/kernel-programs/$program.au"
    case "$division_fixture:$program" in
        zero:bounds) input=tests/kernel-programs/division-zero.au ;;
        remainder-zero:bounds) input=tests/kernel-programs/division-remainder-zero.au ;;
        overflow:overflow) input=tests/kernel-programs/division-overflow.au ;;
        remainder-min:clean) input=tests/kernel-programs/division-remainder-min.au ;;
    esac
    if [[ "${KERNEL_TEST_SCHEDULE:-0}" == 1 ]]; then
        case "$program" in
            clean) input=tests/kernel-programs/scheduled-clean.au ;;
            bounds) input=tests/kernel-programs/scheduled-spin.au ;;
            overflow) input=tests/kernel-programs/bounds.au ;;
        esac
    fi
    "$compiler" "$input" -o "build/user-$program.s" --module-root library
    entry_flags=("${program_asm_flags[@]}")
    if [[ "${KERNEL_TEST_SCHEDULE:-0}" == 1 && "$program" == clean ]]; then entry_flags+=(--defsym AURORA_PROGRAM_CONTEXT_PROBE=1); fi
    as --64 "${entry_flags[@]}" kernel/program-entry.S -o build/program-entry.o
    as --64 -L "build/user-$program.s" -o "build/user-$program.o"
    ld -nostdlib --discard-none -z max-page-size=0x1000 -T kernel/program.ld --defsym="USER_BASE=$base" \
        build/program-entry.o "build/user-$program.o" -o "build/user-$program.elf"
    objcopy -O binary "build/user-$program.elf" "build/user-$program.bin"
    program_index=$((program_index + 1))
done
python3 tests/kernel-user-image.py --division-fixture "$division_fixture"
as --64 build/kernel-user-images.S -o build/kernel-user-images.o
extra=()
if [[ "$division_fixture" != none ]]; then extra+=("-DAURORA_DIVISION_FIXTURE=\"$division_fixture\""); fi
case "$division_fixture" in
    zero|remainder-zero) extra+=(-DAURORA_TEST_DIVISION_ZERO) ;;
    kernel-trap) extra+=(-DAURORA_TEST_DIVISION_KERNEL_TRAP) ;;
esac
if [[ "${KERNEL_TEST_DIVIDE_ERROR:-0}" == 1 ]]; then extra+=(-DAURORA_TEST_DIVIDE_ERROR); fi
if [[ "${KERNEL_TEST_PAGE_FAULT:-0}" == 1 ]]; then extra+=(-DAURORA_TEST_PAGE_FAULT); fi
for flag in WP NX STACK PROGRAM_KERNEL_TRAP DOMAIN_ROOT_MISMATCH SCHEDULE SCHEDULE_FORGED SCHEDULE_CONTEXT SCHEDULE_ROOT; do
    variable="KERNEL_TEST_${flag}"
    if [[ "${!variable:-0}" == 1 ]]; then extra+=("-DAURORA_TEST_${flag}"); fi
done
case "${KERNEL_USER_PROBE_MODE:-0}" in
    [0-6]) extra+=("-DAURORA_USER_PROBE_MODE=${KERNEL_USER_PROBE_MODE:-0}");;
    *) echo 'Invalid controlled user probe mode' >&2; exit 2;;
esac
for source in main interrupts protection user-program address-spaces apic scheduler; do
g++ -std=c++23 -Wall -Wextra -Werror -O2 -ffreestanding -fno-exceptions -fno-rtti \
    -fno-stack-protector -fno-pie -fno-asynchronous-unwind-tables -fno-unwind-tables \
    -Ibuild -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns "${extra[@]}" -c "kernel/$source.cpp" -o "build/kernel-$source.o"
done
ld -nostdlib -z max-page-size=0x1000 -T kernel/link.ld \
    build/kernel-apic.o build/kernel-scheduler.o build/start.o build/exceptions.o build/user.o build/kernel-user-program.o build/kernel-address-spaces.o build/kernel-user-images.o build/kernel-protection.o build/kernel-interrupts.o build/kernel-main.o build/kernel-language.o -o build/kernel.elf
objcopy -O binary build/kernel.elf build/kernel.bin
python3 tests/kernel-image.py
printf 'Built build/aurora.img (raw emulator disk) and build/kernel.elf\n'

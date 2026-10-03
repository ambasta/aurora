#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi/esp/EFI/BOOT
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
flags=(-std=c++23 -O2 -Wall -Wextra -Werror -ffreestanding -fno-exceptions -fno-rtti -fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns)
extra=()
case "${UEFI_MODE:-normal}" in
 normal) ;;
 acpi|acpi-two) extra+=(-DAURORA_UEFI_ACPI) ;;
 acpi-duplicate-root|acpi-changed-header|acpi-checksum|acpi-bad-entry|acpi-duplicate|acpi-disabled|acpi-bad-source|acpi-write|acpi-revoked)
   flag="${UEFI_MODE#acpi-}"; flag="${flag//-/_}"; extra+=(-DAURORA_UEFI_ACPI "-DAURORA_ACPI_${flag^^}") ;;
 stale-exhausted) extra+=(-DAURORA_UEFI_EXHAUSTED) ;;
 stale) extra+=(-DAURORA_UEFI_STALE) ;;
 bad-handoff) extra+=(-DAURORA_UEFI_BAD_HANDOFF) ;;
 bad-table) extra+=(-DAURORA_UEFI_BAD_TABLE) ;;
 bad-map) extra+=(-DAURORA_UEFI_BAD_MAP) ;;
 wp) extra+=(-DAURORA_UEFI_WP) ;;
 nx) extra+=(-DAURORA_UEFI_NX) ;;
 *) echo 'Unknown UEFI build mode' >&2; exit 2 ;;
esac
"$compiler" examples/kernel.au -o build/uefi/language.s
as --64 build/uefi/language.s -o build/uefi/language.o
as --64 kernel/uefi/payload-entry.S -o build/uefi/payload-entry.o
g++ "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/payload.cpp -o build/uefi/payload.o
g++ "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/acpi.cpp -o build/uefi/acpi.o
ld -nostdlib -T kernel/uefi/payload.ld -z max-page-size=0x1000 build/uefi/payload-entry.o build/uefi/payload.o build/uefi/acpi.o build/uefi/language.o -o build/uefi/payload.elf
objcopy -O binary build/uefi/payload.elf build/uefi/payload.bin
python3 - <<'PY'
from pathlib import Path
import subprocess
symbols={}
for line in subprocess.check_output(['nm','-a','build/uefi/payload.elf'],text=True).splitlines():
 words=line.split()
 if len(words)==3: symbols[words[2]]=int(words[0],16)
if symbols['uefi_payload_entry']!=0: raise SystemExit('Entry must start payload')
if subprocess.check_output(['nm','-u','build/uefi/payload.elf'],text=True).strip(): raise SystemExit('Unresolved payload reference')
p=Path('build/uefi/payload.bin')
Path('build/uefi/uefi-payload.hpp').write_text('namespace aurora::uefi {\n'+f'inline constexpr unsigned long long payload_size={p.stat().st_size};\n'+''.join(f'inline constexpr unsigned long long {name}={symbols["__"+name]};\n' for name in ['payload_text_end','payload_read_end','payload_memory_end'])+'}\n')
Path('build/uefi/embed.S').write_text('.section .rodata.payload,"a"\n.global uefi_embedded_payload\nuefi_embedded_payload:\n.incbin "build/uefi/payload.bin"\n.global uefi_embedded_payload_end\nuefi_embedded_payload_end:\n.section .note.GNU-stack,"",@progbits\n')
PY
as --64 build/uefi/embed.S -o build/uefi/embed.o
as --64 kernel/uefi/transition.S -o build/uefi/transition.o
g++ "${flags[@]}" "${extra[@]}" -fpie -maccumulate-outgoing-args -Ibuild/uefi -c kernel/uefi/loader.cpp -o build/uefi/loader.o
for name in loader embed transition; do objcopy --remove-section=.comment --remove-section=.note.GNU-stack "build/uefi/$name.o" "build/uefi/$name-pe.o"; done
ld -mi386pep --subsystem 10 --entry=aurora_efi_entry --image-base=0x100000 --enable-reloc-section --no-insert-timestamp build/uefi/loader-pe.o build/uefi/embed-pe.o build/uefi/transition-pe.o -o build/uefi/esp/EFI/BOOT/BOOTX64.EFI
printf 'Built UEFI PE32+ loader and independent payload\n'

python3 tests/kernel-uefi-image.py

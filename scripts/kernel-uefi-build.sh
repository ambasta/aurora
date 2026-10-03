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
 ipc|ipc-fault|ipc-cancel|ipc-owner|ipc-stale|ipc-version|ipc-phase|ipc-transaction|ipc-site|ipc-unknown|ipc-root|ipc-kernel-trap|ipc-duplicate|ipc-late|ipc-exhausted)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC)
   if [[ "$UEFI_MODE" != ipc ]]; then flag="${UEFI_MODE#ipc-}"; flag="${flag//-/_}"; extra+=("-DAURORA_IPC_${flag^^}"); fi ;;
 runtime|runtime-code|runtime-stack|runtime-kernel|runtime-window|runtime-root|runtime-kernel-trap|runtime-entry-stack|runtime-write|runtime-nx|runtime-return|runtime-unknown|runtime-syscall|runtime-sysenter)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME)
   if [[ "$UEFI_MODE" != runtime ]]; then flag="${UEFI_MODE#runtime-}"; flag="${flag//-/_}"; extra+=("-DAURORA_RUNTIME_${flag^^}"); fi ;;
 pci|pci-devices|pci-bridge) extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI) ;;
 pci-checksum|pci-reserved|pci-overlap|pci-range|pci-write|pci-revoked|pci-cycle)
   flag="${UEFI_MODE#pci-}"; flag="${flag//-/_}"; extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI "-DAURORA_PCI_${flag^^}") ;;
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
runtime_objects=()
if [[ "${UEFI_MODE:-normal}" == runtime* || "${UEFI_MODE:-normal}" == ipc* ]]; then
 mode="${UEFI_MODE#runtime-}"
 case "$mode" in code|stack|kernel|window|write|nx|return|unknown|syscall|sysenter) ;; *) mode=normal ;; esac
 if [[ "$UEFI_MODE" == ipc* ]]; then
   mode="${UEFI_MODE#ipc-}"
   case "$mode" in owner|version|phase|transaction|site|unknown) ;; *) mode=normal ;; esac
   python3 scripts/kernel-uefi-ipc-images.py --compiler "$compiler" --mode "$mode"
   as --64 --defsym AURORA_IPC=1 kernel/uefi/runtime-entry.S -o build/uefi/runtime-entry.o
 else
   python3 scripts/kernel-uefi-user-images.py --compiler "$compiler" --mode "$mode"
   as --64 kernel/uefi/runtime-entry.S -o build/uefi/runtime-entry.o
 fi
 as --64 --defsym AURORA_RELATIVE_ONLY=1 kernel/exceptions.S -o build/uefi/runtime-exceptions.o
 runtime_objects+=(build/uefi/runtime-entry.o build/uefi/runtime-exceptions.o)
fi
"$compiler" examples/kernel.au -o build/uefi/language.s
as --64 build/uefi/language.s -o build/uefi/language.o
as --64 kernel/uefi/payload-entry.S -o build/uefi/payload-entry.o
g++ "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/payload.cpp -o build/uefi/payload.o
g++ "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/acpi.cpp -o build/uefi/acpi.o
g++ "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/pci.cpp -o build/uefi/pci.o
g++ "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/runtime.cpp -o build/uefi/runtime.o
ld -nostdlib -T kernel/uefi/payload.ld -z max-page-size=0x1000 build/uefi/payload-entry.o build/uefi/payload.o build/uefi/acpi.o build/uefi/pci.o build/uefi/runtime.o "${runtime_objects[@]}" build/uefi/language.o -o build/uefi/payload.elf
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

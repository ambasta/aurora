#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cxx="${CXX:-g++}"
for tool in "$cxx" make as ld objcopy objdump nm readelf python3; do command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 2; }; done
export CXX="$cxx"
source ./scripts/uefi-linker.sh
uefi_linker_select
mkdir -p build/uefi/esp/EFI/BOOT
compiler="${AURORAC:-build/aurorac}"
if [[ -z "${AURORAC:-}" ]]; then make -C compiler; fi
# Keep distro defaults outside the admitted instruction profile. Preserve exact
# compiler source/symbol metadata alongside the independent linked CFG proof.
flags=(-std=c++23 -O2 -fstack-usage -fcallgraph-info=su -Wall -Wextra -Werror -ffreestanding -fcf-protection=none -mstringop-strategy=libcall -fno-exceptions -fno-rtti -fno-stack-protector -fno-asynchronous-unwind-tables -fno-unwind-tables -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns)
extra=()
case "${UEFI_MODE:-normal}" in
 normal) ;;
 framebuffer|framebuffer-record|framebuffer-permissions|framebuffer-stale)
   extra+=(-DAURORA_UEFI_FRAMEBUFFER -DAURORA_UEFI_FRAMEBUFFER_FIXTURE -DAURORA_UEFI_FRAMEBUFFER_CAPTURE)
   if [[ "$UEFI_MODE" != framebuffer ]]; then flag="${UEFI_MODE#framebuffer-}"; extra+=("-DAURORA_FRAMEBUFFER_${flag^^}"); fi ;;
 framebuffer-probe) extra+=(-DAURORA_UEFI_FRAMEBUFFER -DAURORA_UEFI_FRAMEBUFFER_PROBE) ;;
 owned-bytes) extra+=(-DAURORA_UEFI_OWNED_BYTES) ;;
 console|console-service-stale|console-service-reentry|console-service-timeout|console-service-report)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_CONSOLE)
   if [[ "$UEFI_MODE" != console ]]; then flag="${UEFI_MODE#console-service-}"; extra+=("-DAURORA_CONSOLE_SERVICE_${flag^^}"); fi ;;
 program-console|program-request-fault|program-service-fault|program-completion-fault|program-request-budget|program-service-budget|program-completion-budget|program-pending|program-owner|program-ordinal|program-unknown|program-transaction)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC -DAURORA_UEFI_SERVICE_BUDGET -DAURORA_UEFI_USER_BUDGET -DAURORA_UEFI_PROGRAM_CONSOLE)
   if [[ "$UEFI_MODE" != program-console ]]; then flag="${UEFI_MODE#program-}"; flag="${flag//-/_}"; extra+=("-DAURORA_PROGRAM_${flag^^}"); fi ;;
 ivrs-default|ivrs-read|ivrs-write|ivrs-revoked|ivrs-pair|ivrs-alias|ivrs-reserved|ivrs-scope|ivrs-capability|ivrs-range|ivrs-missing)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_BAR_CAPTURE -DAURORA_UEFI_BAR_EDK2 -DAURORA_UEFI_IVRS)
   flag="${UEFI_MODE#ivrs-}"; extra+=("-DAURORA_IVRS_${flag^^}") ;;
 bar-prepare)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_BAR_CAPTURE -DAURORA_UEFI_BAR_EDK2 -DAURORA_UEFI_NVME_PREPARE) ;;
 bar-read|bar-inherited|bar-write|bar-revoked|bar-alias)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_BAR_CAPTURE -DAURORA_UEFI_BAR_EDK2)
   if [[ "$UEFI_MODE" == bar-write || "$UEFI_MODE" == bar-revoked || "$UEFI_MODE" == bar-alias ]]; then flag="${UEFI_MODE#bar-}"; extra+=("-DAURORA_BAR_${flag^^}"); fi ;;
 bar-capture) extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_BAR_ADMISSION -DAURORA_UEFI_BAR_CAPTURE) ;;
 bar-state) extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_BAR_ADMISSION) ;;
 user-disposal-input|user-disposal-output|user-phases|user-context|user-retire-pending|user-request-budget|user-completion-budget|user-request-bounds|user-completion-bounds|user-request-overflow|user-completion-overflow|user-pending|user-role|user-phase|user-transaction|user-epoch|user-root|user-unknown|user-stale-grant)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC -DAURORA_UEFI_SERVICE_BUDGET -DAURORA_UEFI_DISPATCH -DAURORA_UEFI_USER_BUDGET)
   if [[ "$UEFI_MODE" == user-disposal-* ]]; then extra+=(-DAURORA_USER_REQUEST_BOUNDS); fi
   flag="${UEFI_MODE#user-}"; flag="${flag//-/_}"; extra+=("-DAURORA_USER_${flag^^}"); ;;
 dispatch|dispatch-budget|dispatch-fault|dispatch-mixed|dispatch-pending|dispatch-cross-reply|dispatch-client-owner|dispatch-stale|dispatch-duplicate|dispatch-full|dispatch-root|dispatch-peer-code|dispatch-policy-cursor|dispatch-policy-mask|dispatch-policy-output)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC -DAURORA_UEFI_SERVICE_BUDGET -DAURORA_UEFI_DISPATCH)
   if [[ "$UEFI_MODE" != dispatch ]]; then flag="${UEFI_MODE#dispatch-}"; flag="${flag//-/_}"; extra+=("-DAURORA_DISPATCH_${flag^^}"); fi ;;
 budget|budget-fault|budget-noapic|budget-smp|budget-discovery|budget-cache|budget-alias|budget-pending|budget-forged|budget-root|budget-mmio|budget-softint|budget-fpu|budget-context|budget-epoch|budget-policy-zero|budget-policy-counts|budget-policy-wide|budget-policy-output)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC -DAURORA_UEFI_SERVICE_BUDGET)
   if [[ "$UEFI_MODE" != budget ]]; then flag="${UEFI_MODE#budget-}"; flag="${flag//-/_}"; extra+=("-DAURORA_BUDGET_${flag^^}"); fi ;;
 ipc|ipc-fault|ipc-cancel|ipc-owner|ipc-stale|ipc-version|ipc-phase|ipc-transaction|ipc-site|ipc-unknown|ipc-root|ipc-kernel-trap|ipc-duplicate|ipc-late|ipc-exhausted|ipc-policy-request-input|ipc-policy-request-output|ipc-policy-cancel-input|ipc-policy-cancel-output)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_IPC)
   if [[ "$UEFI_MODE" != ipc ]]; then flag="${UEFI_MODE#ipc-}"; flag="${flag//-/_}"; extra+=("-DAURORA_IPC_${flag^^}"); fi ;;
 runtime-terminal-input|runtime-terminal-output)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME)
   flag="${UEFI_MODE#runtime-terminal-}"; extra+=("-DAURORA_TERMINAL_EVENT_${flag^^}") ;;
 runtime-table-readback|runtime-table-reject|runtime-table-exhaust|runtime-table-quarantine)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_PINS -DAURORA_UEFI_TABLES -DAURORA_DORMANT_TABLE_TESTING=1)
   flag="${UEFI_MODE#runtime-table-}"; extra+=("-DAURORA_TABLE_${flag^^}")
   if [[ "$UEFI_MODE" == runtime-table-quarantine ]]; then extra+=(-DAURORA_PIN_FAULT); fi ;;
 runtime-pin-cancel|runtime-pin-fault|runtime-pin-stale|runtime-pin-exhaust)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME -DAURORA_UEFI_PINS)
   flag="${UEFI_MODE#runtime-pin-}"; extra+=("-DAURORA_PIN_${flag^^}")
   if [[ "$UEFI_MODE" == runtime-pin-fault ]]; then extra+=(-DAURORA_PIN_LEDGER_TESTING=1); fi ;;
 runtime|runtime-span|runtime-code|runtime-stack|runtime-kernel|runtime-window|runtime-root|runtime-kernel-trap|runtime-entry-stack|runtime-write|runtime-nx|runtime-return|runtime-unknown|runtime-syscall|runtime-sysenter)
   extra+=(-DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI -DAURORA_UEFI_RUNTIME)
   if [[ "$UEFI_MODE" != runtime && "$UEFI_MODE" != runtime-span ]]; then flag="${UEFI_MODE#runtime-}"; flag="${flag//-/_}"; extra+=("-DAURORA_RUNTIME_${flag^^}"); fi ;;
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
case "${UEFI_MODE:-normal}" in
 framebuffer|framebuffer-record|framebuffer-permissions|framebuffer-stale)
    framebuffer_provenance=()
    for flag in "${flags[@]}" "${extra[@]}"; do framebuffer_provenance+=("--flag=$flag"); done
    python3 -B scripts/kernel_framebuffer_admission.py begin --mode "$UEFI_MODE" \
        --compiler "$compiler" --cxx "$cxx" "${framebuffer_provenance[@]}" ;;
esac
if [[ "${UEFI_MODE:-normal}" == program-* ]]; then
 provenance_flags=()
 for flag in "${flags[@]}" "${extra[@]}"; do provenance_flags+=("--flag=$flag"); done
 python3 -B scripts/kernel_program_console_admission.py begin-build --mode "$UEFI_MODE" \
   --compiler "$compiler" --cxx "$cxx" "${provenance_flags[@]}"
fi
if [[ "${UEFI_MODE:-normal}" == console || "${UEFI_MODE:-normal}" == console-service-* ]]; then
 provenance_flags=()
 for flag in "${flags[@]}" "${extra[@]}"; do provenance_flags+=("--flag=$flag"); done
 python3 -B scripts/kernel_console_service_admission.py begin-build --mode "$UEFI_MODE" \
   --compiler "$compiler" --cxx "$cxx" "${provenance_flags[@]}"
fi
runtime_objects=()
if [[ "${UEFI_MODE:-normal}" == runtime* || "${UEFI_MODE:-normal}" == ipc* || "${UEFI_MODE:-normal}" == budget* || "${UEFI_MODE:-normal}" == dispatch* || "${UEFI_MODE:-normal}" == user-* || "${UEFI_MODE:-normal}" == program-* ]]; then
 mode="${UEFI_MODE#runtime-}"
 case "$mode" in span|code|stack|kernel|window|write|nx|return|unknown|syscall|sysenter) ;; *) mode=normal ;; esac
 if [[ "$UEFI_MODE" == program-* ]]; then
   program_image_mode=normal
   case "$UEFI_MODE" in program-owner|program-ordinal|program-unknown|program-transaction) program_image_mode="${UEFI_MODE#program-}" ;; esac
   python3 scripts/kernel-uefi-ipc-images.py --compiler "$compiler" --mode "$program_image_mode" --service-budget --user-budget --program-console
   as --64 --defsym AURORA_IPC=1 --defsym AURORA_SERVICE_BUDGET=1 kernel/uefi/runtime-entry.S -o build/uefi/runtime-entry.o
 elif [[ "$UEFI_MODE" == user-* ]]; then
   mode=normal
   if [[ "$UEFI_MODE" == user-unknown ]]; then mode=unknown; fi
   if [[ "$UEFI_MODE" == user-context ]]; then mode=context; fi
   python3 scripts/kernel-uefi-ipc-images.py --compiler "$compiler" --mode "$mode" --service-budget --dispatcher --user-budget
   as --64 --defsym AURORA_IPC=1 --defsym AURORA_SERVICE_BUDGET=1 kernel/uefi/runtime-entry.S -o build/uefi/runtime-entry.o
 elif [[ "$UEFI_MODE" == dispatch* ]]; then
   mode=normal
   if [[ "$UEFI_MODE" == dispatch-peer-code ]]; then mode=peer-code; fi
   python3 scripts/kernel-uefi-ipc-images.py --compiler "$compiler" --mode "$mode" --service-budget --dispatcher
   as --64 --defsym AURORA_IPC=1 --defsym AURORA_SERVICE_BUDGET=1 kernel/uefi/runtime-entry.S -o build/uefi/runtime-entry.o
 elif [[ "$UEFI_MODE" == budget* ]]; then
   mode="${UEFI_MODE#budget-}"
   case "$mode" in mmio|softint|fpu|context) ;; *) mode=normal ;; esac
   python3 scripts/kernel-uefi-ipc-images.py --compiler "$compiler" --mode "$mode" --service-budget
   as --64 --defsym AURORA_IPC=1 --defsym AURORA_SERVICE_BUDGET=1 kernel/uefi/runtime-entry.S -o build/uefi/runtime-entry.o
 elif [[ "$UEFI_MODE" == ipc* ]]; then
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
console_objects=()
language_entry=examples/kernel.au
framebuffer_objects=()
if [[ "${UEFI_MODE:-normal}" == framebuffer || "${UEFI_MODE:-normal}" == framebuffer-record || "${UEFI_MODE:-normal}" == framebuffer-permissions || "${UEFI_MODE:-normal}" == framebuffer-stale ]]; then
    language_entry=examples/kernel-display-service.au
    "$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/framebuffer.cpp -o build/uefi/framebuffer.o
    framebuffer_objects+=(build/uefi/framebuffer.o)
fi
if [[ "${UEFI_MODE:-normal}" == program-* ]]; then language_entry=examples/kernel-program-console.au; fi
if [[ "${UEFI_MODE:-normal}" == owned-bytes ]]; then language_entry=examples/kernel-owned-bytes.au; fi
if [[ "${UEFI_MODE:-normal}" == console || "${UEFI_MODE:-normal}" == console-service-* ]]; then
    language_entry=examples/kernel-console-service.au
    as --64 kernel/uefi/console-entry.S -o build/uefi/console-entry.o
    "$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/console.cpp -o build/uefi/console.o
    console_objects+=(build/uefi/console-entry.o build/uefi/console.o)
fi
"$compiler" --module-root kernel/policies "$language_entry" -o build/uefi/language.s
if (( ${#framebuffer_objects[@]} )); then
    as --64 build/uefi/language.s kernel/uefi/display-service-entry.S -o build/uefi/language.o
elif [[ "${UEFI_MODE:-normal}" == owned-bytes ]]; then
    as --64 build/uefi/language.s kernel/uefi/owned-bytes-entry.S -o build/uefi/language.o
    python3 tests/kernel-uefi-owned-bytes-admission.py build/uefi/language.o
elif [[ "${UEFI_MODE:-normal}" == console || "${UEFI_MODE:-normal}" == console-service-* ]]; then
    as --64 build/uefi/language.s kernel/uefi/console-service-entry.S -o build/uefi/language.o
else
    as --64 build/uefi/language.s -o build/uefi/language.o
fi
as --64 kernel/uefi/payload-entry.S -o build/uefi/payload-entry.o
as --64 kernel/uefi/memory.S -o build/uefi/memory.o
"$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/payload.cpp -o build/uefi/payload.o
"$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/acpi.cpp -o build/uefi/acpi.o
"$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/pci.cpp -o build/uefi/pci.o
"$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -Ibuild/uefi -c kernel/uefi/runtime.cpp -o build/uefi/runtime.o
owned_bytes_objects=()
if [[ "${UEFI_MODE:-normal}" == owned-bytes ]]; then
    "$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/owned-bytes.cpp -o build/uefi/owned-bytes-runtime.o
    "$cxx" "${flags[@]}" "${extra[@]}" -fpie -fvisibility=hidden -c kernel/uefi/owned-bytes.cpp -o build/uefi/owned-bytes-profile.o
    owned_bytes_objects+=(build/uefi/owned-bytes-runtime.o build/uefi/owned-bytes-profile.o)
fi
ld -nostdlib -T kernel/uefi/payload.ld -z max-page-size=0x1000 \
    build/uefi/payload-entry.o build/uefi/memory.o build/uefi/payload.o build/uefi/acpi.o \
    build/uefi/pci.o build/uefi/runtime.o "${runtime_objects[@]}" "${console_objects[@]}" \
    build/uefi/language.o "${owned_bytes_objects[@]}" "${framebuffer_objects[@]}" -o build/uefi/payload.elf
if [[ "${UEFI_MODE:-normal}" == owned-bytes ]]; then
    python3 tests/kernel-uefi-owned-bytes-stack.py build/uefi build/uefi/owned-bytes-stack.json
fi
objcopy -O binary build/uefi/payload.elf build/uefi/payload.bin
if [[ "${UEFI_MODE:-normal}" == runtime-table-* ]]; then
    python3 tests/kernel-uefi-tables-stack.py build/uefi "build/uefi/table-stack/$UEFI_MODE"
fi
python3 - <<'PY'
from pathlib import Path
import subprocess,json
symbols={}
for line in subprocess.check_output(['nm','-a','build/uefi/payload.elf'],text=True).splitlines():
 words=line.split()
 if len(words)==3: symbols[words[2]]=int(words[0],16)
if symbols['uefi_payload_entry']!=0: raise SystemExit('Entry must start payload')
if subprocess.check_output(['nm','-u','build/uefi/payload.elf'],text=True).strip(): raise SystemExit('Unresolved payload reference')
p=Path('build/uefi/payload.bin')
console_metadata = Path('build/uefi/console-poll-metadata.json')
if 'uefi_console_poll_begin' in symbols:
    begin, end = symbols['uefi_console_poll_begin'], symbols['uefi_console_poll_end']
    if not 0 < begin < end < symbols['__payload_text_end'] or p.read_bytes()[begin:end] != bytes.fromhex('fbf4fa'):
        raise SystemExit('Invalid exact console wait site')
    if 'uefi_runtime_enter' in symbols or 'aurora_kernel_budget_tick' in symbols:
        raise SystemExit('Console must not contain user runtime or service budget fixtures')
    console_metadata.write_text(json.dumps(dict(wait_begin=begin, wait_end=end,
        text_end=symbols['__payload_text_end'], frame_bytes=176, interrupt=symbols['uefi_console_interrupt'],
        dispatch=symbols['uefi_console_interrupt_dispatch'], polling_count=1250000, uart_irq=0), indent=2)+'\n')
else:
    console_metadata.unlink(missing_ok=True)
program_metadata = Path('build/uefi/program-poll-metadata.json')
if 'uefi_program_poll_begin' in symbols:
    begin, end = symbols['uefi_program_poll_begin'], symbols['uefi_program_poll_end']
    if not 0 < begin < end < symbols['__payload_text_end'] or p.read_bytes()[begin:end] != bytes.fromhex('fbf4fa'):
        raise SystemExit('Invalid exact program console wait site')
    if 'uefi_runtime_enter' not in symbols or 'aurora_kernel_budget_tick' not in symbols:
        raise SystemExit('Program console requires protected runtime and bounded timer policy')
    program_metadata.write_text(json.dumps(dict(wait_begin=begin, wait_end=end,
        text_end=symbols['__payload_text_end'], frame_bytes=176, polling_count=1250000,
        uart_irq=0, domains=2), indent=2)+'\n')
else:
    program_metadata.unlink(missing_ok=True)
Path('build/uefi/uefi-payload.hpp').write_text('namespace aurora::uefi {\n'+f'inline constexpr unsigned long long payload_size={p.stat().st_size};\n'+''.join(f'inline constexpr unsigned long long {name}={symbols["__"+name]};\n' for name in ['payload_text_end','payload_read_end','payload_memory_end'])+'}\n')
bar_faults={}
for mode,name,opcode in [('bar-write','uefi_bar_write_probe',bytes.fromhex('c70000000000')),('bar-revoked','uefi_bar_revoked_probe',bytes.fromhex('8b00'))]:
 if name in symbols:
  at=symbols[name]
  if not 0<at<symbols['__payload_text_end'] or p.read_bytes()[at:at+len(opcode)]!=opcode:raise SystemExit('Invalid exact BAR fault site')
  bar_faults[mode]=at
Path('build/uefi/bar-metadata.json').write_text(json.dumps(dict(offset=0x22000,bytes=symbols['__payload_text_end'],fault_offsets=bar_faults),indent=2)+'\n')
ivrs_faults={}
for mode,name,opcode in [('ivrs-write','uefi_ivrs_write_probe',bytes.fromhex('48c70000000000')),('ivrs-revoked','uefi_ivrs_revoked_probe',bytes.fromhex('488b00'))]:
    if name in symbols:
        address=symbols[name]
        if not 0<address<symbols['__payload_text_end'] or p.read_bytes()[address:address+len(opcode)]!=opcode: raise ValueError('Wrong IVRS probe opcode')
        ivrs_faults[mode]=address
Path('build/uefi/ivrs-metadata.json').write_text(json.dumps(dict(offset=0x22000,bytes=symbols['__payload_text_end'],fault_offsets=ivrs_faults),indent=2)+'\n')
if 'uefi_service_drain_begin' in symbols:
 drain_begin=symbols['uefi_service_drain_begin'];drain_end=symbols['uefi_service_drain_end']
 if not 0<=drain_begin<drain_end<symbols['__payload_text_end'] or p.read_bytes()[drain_begin:drain_end]!=bytes.fromhex('fb9090fa'):raise SystemExit('Invalid exact drain interval')
 forged=symbols.get('uefi_service_forged_pc',0)
 if forged and (not 2<=forged<symbols['__payload_text_end'] or p.read_bytes()[forged-2:forged]!=bytes.fromhex('cd40')):raise SystemExit('Invalid forged interrupt probe')
 Path('build/uefi/service-timer-metadata.json').write_text(json.dumps(dict(drain_begin=drain_begin,drain_end=drain_end,text_end=symbols['__payload_text_end'],forged_pc=symbols.get('uefi_service_forged_pc',0))))
Path('build/uefi/embed.S').write_text('.section .rodata.payload,"a"\n.global uefi_embedded_payload\nuefi_embedded_payload:\n.incbin "build/uefi/payload.bin"\n.global uefi_embedded_payload_end\nuefi_embedded_payload_end:\n.section .note.GNU-stack,"",@progbits\n')
PY
as --64 build/uefi/embed.S -o build/uefi/embed.o
as --64 kernel/uefi/transition.S -o build/uefi/transition.o
"$cxx" "${flags[@]}" "${extra[@]}" -fpie -maccumulate-outgoing-args -Ibuild/uefi -c kernel/uefi/loader.cpp -o build/uefi/loader.o
for name in loader embed transition memory; do objcopy --remove-section=.comment --remove-section=.note.GNU-stack "build/uefi/$name.o" "build/uefi/$name-pe.o"; done
"$UEFI_LINKER" -mi386pep --subsystem 10 --entry=aurora_efi_entry --image-base=0x100000 --enable-reloc-section --dynamicbase --nxcompat --no-insert-timestamp build/uefi/loader-pe.o build/uefi/embed-pe.o build/uefi/transition-pe.o build/uefi/memory-pe.o -o build/uefi/esp/EFI/BOOT/BOOTX64.EFI
printf 'Built UEFI PE32+ loader and independent payload\n'

image_policy=()
case "${UEFI_MODE:-normal}" in
    ipc*|budget*|dispatch*|user-*|program-*) image_policy+=(--ipc-policy) ;;
    owned-bytes) image_policy+=(--owned-bytes) ;;
esac
case "${UEFI_MODE:-normal}" in
    user-request-*|user-completion-*|user-retire-pending|user-stale-grant|user-disposal-*) image_policy+=(--disposal-policy) ;;
esac
python3 tests/kernel-uefi-image.py "${image_policy[@]}"

if [[ "${UEFI_MODE:-normal}" == ivrs-* ]]; then python3 tests/kernel-uefi-ivrs-stack.py build/uefi build/uefi/ivrs-stack.json; fi

if [[ "${UEFI_MODE:-normal}" == bar-prepare ]]; then
    python3 tests/kernel-uefi-nvme-stack.py build/uefi build/uefi/nvme-stack.json
fi

if [[ "${UEFI_MODE:-normal}" == program-* ]]; then
    python3 -B scripts/kernel_program_console_admission.py end-build --mode "$UEFI_MODE"
    python3 -B scripts/kernel_program_console_admission.py emit --mode "$UEFI_MODE"
fi

if [[ "${UEFI_MODE:-normal}" == console || "${UEFI_MODE:-normal}" == console-service-* ]]; then
    python3 -B scripts/kernel_console_service_admission.py end-build --mode "$UEFI_MODE"
    python3 -B scripts/kernel_console_service_admission.py emit --mode "$UEFI_MODE"
fi

case "${UEFI_MODE:-normal}" in
 framebuffer|framebuffer-record|framebuffer-permissions|framebuffer-stale)
    python3 -B scripts/kernel_framebuffer_admission.py end --mode "$UEFI_MODE"
    python3 -B scripts/kernel_framebuffer_admission.py emit --mode "$UEFI_MODE" ;;
esac

# Production process policy bridge, rendered from compiler ABI facts.
# No kernel file-store, fixture run-list or serial-export entry is exposed here.
# Its selected source root retains compiler facts and standalone stack checks.
# PRODUCTION_PROCESS_POLICY_ABI: each entry receives one complete argument record in RDI
# (R11 for aggregate entries, unpacked registers for scalar6). Class results
# also receive fresh caller storage in RSI (moved
# to R10). A span argument is the 56-byte contiguous readonly view (kind 0) the
# supervisor builds over bytes it has mapped; the bridge authenticates nothing.
.text
.macro process_entry name, target
.global \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call \target
    leave
    ret
.size \name,.-\name
.endm
.macro process_result_entry name, target
.global \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call \target
    leave
    ret
.size \name,.-\name
.endm
process_entry __au_runtime_process_map_admit, @process_map_admit@
process_entry __au_runtime_process_volume_grant, @process_volume_grant@
process_result_entry __au_runtime_process_frame_range, @process_frame_range@
process_entry __au_runtime_process_volume_admit, @process_volume_admit@
process_entry __au_runtime_process_volume_find, @process_volume_find@
process_result_entry __au_runtime_process_volume_entry, @process_volume_entry@
process_entry __au_runtime_process_elf_admit, @process_elf_admit@
process_entry __au_runtime_process_layout, @process_layout@
process_result_entry __au_runtime_process_region, @process_region@
process_entry __au_runtime_process_elf_entry, @process_elf_entry@
process_entry __au_runtime_process_elf_input, @process_elf_input@
process_entry __au_runtime_process_trap, @process_trap@
process_result_entry __au_runtime_process_call, @process_call@
process_result_entry __au_runtime_process_input, @process_input@
process_entry __au_runtime_process_memory_load_charge, @process_memory_load_charge@

# Scalar-only source roots use the compiler's six-register bootstrap ABI.
# The native caller supplies one complete 48-byte copied record.
.macro process_scalar6_entry name, target
.global \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq 0(%r11),%rdi
    movq 8(%r11),%rsi
    movq 16(%r11),%rdx
    movq 24(%r11),%rcx
    movq 32(%r11),%r8
    movq 40(%r11),%r9
    call \target
    leave
    ret
.size \name,.-\name
.endm
process_scalar6_entry __au_runtime_process_snapshot_writable_leaf, @process_snapshot_writable_leaf@

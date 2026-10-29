# Private process-image policy bridge, rendered from compiler ABI facts.
# PROCESS_POLICY_ABI: each entry receives one complete argument record in RDI
# (moved to R11); class results also receive fresh caller storage in RSI (moved
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
process_entry __au_runtime_process_base64_group, @process_base64_group@
# The scalar frame transition keeps the existing SysV scalar-symbol seam.
.global aurora_kernel_frame_transition
.hidden aurora_kernel_frame_transition

# Hosted pure memory-policy queries. Production uses the retained manager.
# PROCESS_MEMORY_POLICY_ABI: copied argument records and exact result storage.
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
process_result_entry __au_runtime_process_memory_map, @process_memory_map@
process_result_entry __au_runtime_process_memory_remap, @process_memory_remap@
process_result_entry __au_runtime_process_memory_unmap, @process_memory_unmap@
process_entry __au_runtime_process_memory_find, @process_memory_find@
process_entry __au_runtime_process_memory_fault, @process_memory_fault@
process_result_entry __au_runtime_process_memory_budget, @process_memory_budget@
# The scalar frame transition keeps the existing SysV scalar-symbol seam.
.global aurora_kernel_frame_transition
.hidden aurora_kernel_frame_transition

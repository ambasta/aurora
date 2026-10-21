# Assemble with the one combined generated supervisor graph. Private source
# entries remain local; these are the complete native exports, not a source ABI.
.text
.global __au_runtime_snapshot_produce
.hidden __au_runtime_snapshot_produce
.type __au_runtime_snapshot_produce,@function
__au_runtime_snapshot_produce:
    pushq %rbp
    movq %rsp, %rbp
    subq $16, %rsp
    movq %rdi, (%rsp)
    movq %rsi, 8(%rsp)
    movq %rdx, %r10
    movq %rsp, %r11
    call __au_v_m1_15kernel_snapshot_n0__d16produce_snapshot
    leave
    ret
.size __au_runtime_snapshot_produce,.-__au_runtime_snapshot_produce

.global aurora_kernel_value
.hidden aurora_kernel_value
.type aurora_kernel_value,@function
aurora_kernel_value:
    jmp snapshot_kernel_value
.size aurora_kernel_value,.-aurora_kernel_value

.global aurora_kernel_ipc_transition
.hidden aurora_kernel_ipc_transition
.type aurora_kernel_ipc_transition,@function
aurora_kernel_ipc_transition:
    jmp snapshot_ipc_transition
.size aurora_kernel_ipc_transition,.-aurora_kernel_ipc_transition

.global aurora_kernel_terminal_event
.hidden aurora_kernel_terminal_event
.type aurora_kernel_terminal_event,@function
aurora_kernel_terminal_event:
    jmp snapshot_terminal_event
.size aurora_kernel_terminal_event,.-aurora_kernel_terminal_event

.global aurora_kernel_budget_tick
.hidden aurora_kernel_budget_tick
.type aurora_kernel_budget_tick,@function
aurora_kernel_budget_tick:
    jmp snapshot_budget_tick
.size aurora_kernel_budget_tick,.-aurora_kernel_budget_tick

.section .note.GNU-stack,"",@progbits

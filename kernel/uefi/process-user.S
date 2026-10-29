# Process entry and exit for the process image (kernel/uefi/process.md#entries).
# uefi_process_enter(context) saves the kernel's callee-saved registers and
# stack, loads the process root and IRETQs to CPL 3 with only RDI and RSI set:
# context words are RIP, RSP, RDI, RSI, root. Every trap of the process enters
# kernel/exceptions.S on TSS.RSP0 under the process root; a dispatch result of 1
# jumps here to aurora_leave_user, which restores the kernel root, the kernel
# selectors and the saved stack and returns 1 from uefi_process_enter.
# uefi_process_handler(vector) returns a vector's handler address without
# absolute relocations.
.section .text
.code64
.global uefi_process_enter
.hidden uefi_process_enter
.type uefi_process_enter,@function
uefi_process_enter:
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
    mov %rsp, uefi_process_saved_rsp(%rip)
    pushq $0x23
    pushq 8(%rdi)
    pushq $0x202
    pushq $0x1b
    pushq 0(%rdi)
    mov 32(%rdi), %rax
    mov 24(%rdi), %rsi
    mov 16(%rdi), %rdi
    mov %rax, %cr3
    mov $0x23, %eax
    mov %ax, %ds
    mov %ax, %es
    xor %eax, %eax
    mov %ax, %fs
    mov %ax, %gs
    xor %ebx, %ebx
    xor %ecx, %ecx
    xor %edx, %edx
    xor %ebp, %ebp
    xor %r8d, %r8d
    xor %r9d, %r9d
    xor %r10d, %r10d
    xor %r11d, %r11d
    xor %r12d, %r12d
    xor %r13d, %r13d
    xor %r14d, %r14d
    xor %r15d, %r15d
    iretq
.size uefi_process_enter,.-uefi_process_enter
.global aurora_leave_user
.hidden aurora_leave_user
.type aurora_leave_user,@function
aurora_leave_user:
    mov uefi_process_kernel_root(%rip), %rax
    mov %rax, %cr3
    mov $0x10, %eax
    mov %ax, %ds
    mov %ax, %es
    # Interrupt privilege entry loaded a null SS; restore the kernel selector
    # before resuming the saved kernel stack. IF stays clear on this path.
    mov %ax, %ss
    mov uefi_process_saved_rsp(%rip), %rsp
    movq $0, uefi_process_saved_rsp(%rip)
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbp
    pop %rbx
    mov $1, %eax
    ret
.size aurora_leave_user,.-aurora_leave_user
.global uefi_process_handler
.hidden uefi_process_handler
.type uefi_process_handler,@function
uefi_process_handler:
    cmp $64, %edi
    jne 1f
    lea aurora_timer_interrupt(%rip), %rax
    ret
1:  cmp $131, %edi
    jne 2f
    lea aurora_process_call(%rip), %rax
    ret
2:  cmp $31, %edi
    ja 3f
    lea process_handler_offsets(%rip), %rax
    movslq (%rax,%rdi,4), %rdx
    add %rdx, %rax
    ret
3:  lea aurora_unexpected_interrupt(%rip), %rax
    ret
.size uefi_process_handler,.-uefi_process_handler
# The kernel stack waits here for a timer interrupt already pending when a
# process ended, so the timer is quiet before the next one starts.
.global uefi_process_drain
.hidden uefi_process_drain
.type uefi_process_drain,@function
uefi_process_drain:
.global uefi_process_drain_begin
.hidden uefi_process_drain_begin
uefi_process_drain_begin:
    sti
    hlt
    cli
.global uefi_process_drain_end
.hidden uefi_process_drain_end
uefi_process_drain_end:
    ret
.size uefi_process_drain,.-uefi_process_drain
.section .rodata
.balign 4
process_handler_offsets:
    .long aurora_exception_0-process_handler_offsets
    .long aurora_exception_1-process_handler_offsets
    .long aurora_exception_2-process_handler_offsets
    .long aurora_exception_3-process_handler_offsets
    .long aurora_exception_4-process_handler_offsets
    .long aurora_exception_5-process_handler_offsets
    .long aurora_exception_6-process_handler_offsets
    .long aurora_exception_7-process_handler_offsets
    .long aurora_exception_8-process_handler_offsets
    .long aurora_exception_9-process_handler_offsets
    .long aurora_exception_10-process_handler_offsets
    .long aurora_exception_11-process_handler_offsets
    .long aurora_exception_12-process_handler_offsets
    .long aurora_exception_13-process_handler_offsets
    .long aurora_exception_14-process_handler_offsets
    .long aurora_exception_15-process_handler_offsets
    .long aurora_exception_16-process_handler_offsets
    .long aurora_exception_17-process_handler_offsets
    .long aurora_exception_18-process_handler_offsets
    .long aurora_exception_19-process_handler_offsets
    .long aurora_exception_20-process_handler_offsets
    .long aurora_exception_21-process_handler_offsets
    .long aurora_exception_22-process_handler_offsets
    .long aurora_exception_23-process_handler_offsets
    .long aurora_exception_24-process_handler_offsets
    .long aurora_exception_25-process_handler_offsets
    .long aurora_exception_26-process_handler_offsets
    .long aurora_exception_27-process_handler_offsets
    .long aurora_exception_28-process_handler_offsets
    .long aurora_exception_29-process_handler_offsets
    .long aurora_exception_30-process_handler_offsets
    .long aurora_exception_31-process_handler_offsets
.section .bss
.balign 8
.global uefi_process_saved_rsp
.hidden uefi_process_saved_rsp
uefi_process_saved_rsp: .skip 8
.global uefi_process_kernel_root
.hidden uefi_process_kernel_root
uefi_process_kernel_root: .skip 8
.section .note.GNU-stack,"",@progbits

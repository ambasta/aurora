/* Supervisor-only timer gate. The C++ adapter authenticates the exact wait
 * continuation and owned frame before EOI. No user-entry/exit path is linked. */
.section .text
.code64
.global uefi_console_interrupt
.hidden uefi_console_interrupt
uefi_console_interrupt:
    pushq $0
    pushq $64
    cmpb $0, uefi_payload_trap_guard(%rip)
    jne uefi_payload_nested_fault
    movb $1, uefi_payload_trap_guard(%rip)
    cld
    push %rax
    push %rbx
    push %rcx
    push %rdx
    push %rbp
    push %rsi
    push %rdi
    push %r8
    push %r9
    push %r10
    push %r11
    push %r12
    push %r13
    push %r14
    push %r15
    mov %rsp, %rdi
    mov %rsp, %rbx
    and $-16, %rsp
    call uefi_console_interrupt_dispatch
    mov %rbx, %rsp
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %r11
    pop %r10
    pop %r9
    pop %r8
    pop %rdi
    pop %rsi
    pop %rbp
    pop %rdx
    pop %rcx
    pop %rbx
    pop %rax
    add $16, %rsp
    movb $0, uefi_payload_trap_guard(%rip)
    iretq
.section .note.GNU-stack,"",@progbits

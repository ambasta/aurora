.section .text
.code64
.global uefi_runtime_enter
uefi_runtime_enter:
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
    mov %rsp, uefi_runtime_saved_rsp(%rip)
    pushq $0x23
    push %rsi
    pushq $2
    pushq $0x1b
    push %rdi
    mov $0x23, %ax
    mov %ax, %ds
    mov %ax, %es
    xor %eax, %eax
    xor %ebx, %ebx
    xor %ecx, %ecx
    xor %edx, %edx
    xor %ebp, %ebp
    xor %esi, %esi
    xor %edi, %edi
    xor %r8d, %r8d
    xor %r9d, %r9d
    xor %r10d, %r10d
    xor %r11d, %r11d
    xor %r12d, %r12d
    xor %r13d, %r13d
    xor %r14d, %r14d
    xor %r15d, %r15d
    iretq
.global aurora_leave_user
aurora_leave_user:
    mov $0x10, %ax
    mov %ax, %ds
    mov %ax, %es
    mov uefi_runtime_saved_rsp(%rip), %rsp
    movq $0, uefi_runtime_saved_rsp(%rip)
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbp
    pop %rbx
    mov $1, %eax
    ret
.global uefi_runtime_handler
uefi_runtime_handler:
    cmp $129,%edi
    je return_handler
    cmp $31,%edi
    ja unexpected_handler
    lea handler_offsets(%rip),%rax
    movslq (%rax,%rdi,4),%rdx
    add %rdx,%rax
    ret
return_handler:
    lea aurora_program_return(%rip),%rax
    ret
unexpected_handler:
    lea aurora_unexpected_interrupt(%rip),%rax
    ret
.section .rodata
.balign 4
handler_offsets:
    .long aurora_exception_0-handler_offsets
    .long aurora_exception_1-handler_offsets
    .long aurora_exception_2-handler_offsets
    .long aurora_exception_3-handler_offsets
    .long aurora_exception_4-handler_offsets
    .long aurora_exception_5-handler_offsets
    .long aurora_exception_6-handler_offsets
    .long aurora_exception_7-handler_offsets
    .long aurora_exception_8-handler_offsets
    .long aurora_exception_9-handler_offsets
    .long aurora_exception_10-handler_offsets
    .long aurora_exception_11-handler_offsets
    .long aurora_exception_12-handler_offsets
    .long aurora_exception_13-handler_offsets
    .long aurora_exception_14-handler_offsets
    .long aurora_exception_15-handler_offsets
    .long aurora_exception_16-handler_offsets
    .long aurora_exception_17-handler_offsets
    .long aurora_exception_18-handler_offsets
    .long aurora_exception_19-handler_offsets
    .long aurora_exception_20-handler_offsets
    .long aurora_exception_21-handler_offsets
    .long aurora_exception_22-handler_offsets
    .long aurora_exception_23-handler_offsets
    .long aurora_exception_24-handler_offsets
    .long aurora_exception_25-handler_offsets
    .long aurora_exception_26-handler_offsets
    .long aurora_exception_27-handler_offsets
    .long aurora_exception_28-handler_offsets
    .long aurora_exception_29-handler_offsets
    .long aurora_exception_30-handler_offsets
    .long aurora_exception_31-handler_offsets
.section .bss
.balign 8
.global uefi_runtime_saved_rsp
uefi_runtime_saved_rsp: .skip 8
.section .note.GNU-stack,"",@progbits

.section .text
.code64
.ifdef AURORA_USER_RESUME
.global uefi_runtime_resume
uefi_runtime_resume:
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
    mov %rsp, uefi_runtime_saved_rsp(%rip)
    mov $0x23,%ax
    mov %ax,%ds
    mov %ax,%es
    mov %rdi,%rsp
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
    add $16,%rsp
    iretq
.endif
.global uefi_runtime_enter
uefi_runtime_enter:
.ifdef AURORA_IPC
    mov %rdx,%r11
.endif
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
    mov %rsp, uefi_runtime_saved_rsp(%rip)
    pushq $0x23
    push %rsi
.ifdef AURORA_SERVICE_BUDGET
    pushq 48(%r11)
.else
    pushq $2
.endif
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
 .ifndef AURORA_IPC
    xor %r11d, %r11d
 .endif
    xor %r12d, %r12d
    xor %r13d, %r13d
    xor %r14d, %r14d
    xor %r15d, %r15d
.ifdef AURORA_IPC
    mov 0(%r11),%rdi
    mov 8(%r11),%rsi
    mov 16(%r11),%rdx
    mov 24(%r11),%rcx
    mov 32(%r11),%r8
    mov 40(%r11),%r9
    xor %r11d,%r11d
.endif
    iretq
.global aurora_leave_user
aurora_leave_user:
    mov $0x10, %ax
    mov %ax, %ds
    mov %ax, %es
    # Interrupt privilege entry cleared SS; restore the kernel selector before
    # resuming the saved kernel stack. IF remains clear throughout this path.
    mov %ax, %ss
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
.ifdef AURORA_SERVICE_BUDGET
    cmp $64,%edi
    jne not_timer
    lea aurora_timer_interrupt(%rip),%rax
    ret
not_timer:
.endif
.ifdef AURORA_BLOCKING_CALL
    cmp $130,%edi
    jne not_call
    lea aurora_program_call(%rip),%rax
    ret
not_call:
.endif
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

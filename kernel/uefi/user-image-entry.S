.section .text.user_entry,"ax"
.code64
.global aurora_program_entry
.global aurora_program_return_pc
aurora_program_entry:
    or %rbx,%rax
    or %rcx,%rax
    or %rdx,%rax
    or %rbp,%rax
    or %rsi,%rax
    or %rdi,%rax
    or %r8,%rax
    or %r9,%rax
    or %r10,%rax
    or %r11,%rax
    or %r12,%rax
    or %r13,%rax
    or %r14,%rax
    or %r15,%rax
    jnz bad_entry
    cmpq $0,-8(%rsp)
    jne bad_entry
.ifdef UEFI_USER_CODE
    movabs $0x10000004000,%rax
    call *%rax
.endif
.ifdef UEFI_USER_STACK
    movabs $0x10000400000,%rax
    .global aurora_probe_pc
aurora_probe_pc:
    mov (%rax),%al
.endif
.ifdef UEFI_USER_WINDOW
    movabs $0xffff800000000000,%rax
    .global aurora_probe_pc
aurora_probe_pc:
    mov (%rax),%al
.endif
.ifdef UEFI_USER_KERNEL
    mov aurora_kernel_probe_target(%rip),%rax
    .global aurora_probe_pc
aurora_probe_pc:
    mov (%rax),%al
.endif
.ifdef UEFI_USER_WRITE
    movabs $0x10000000000,%rax
    .global aurora_probe_pc
aurora_probe_pc:
    movb $0,(%rax)
.endif
.ifdef UEFI_USER_NX
    movb $0xc3,-8(%rsp)
    lea -8(%rsp),%rax
    call *%rax
.endif
.ifdef UEFI_USER_RETURN
    mov $42,%eax
    int $0x81
    .global aurora_probe_pc
aurora_probe_pc:
.endif
.ifdef UEFI_USER_UNKNOWN
    .global aurora_probe_pc
aurora_probe_pc:
    ud2
.endif
.ifdef UEFI_USER_SYSCALL
    .global aurora_probe_pc
aurora_probe_pc:
    syscall
.endif
.ifdef UEFI_USER_SYSENTER
    .global aurora_probe_pc
aurora_probe_pc:
    sysenter
.endif
.ifdef UEFI_USER_MULTIPAGE_FAULT
    mov $1,%edi
.endif
    call aurora_user_main
    int $0x81
aurora_program_return_pc:
    ud2
bad_entry:
    ud2
.ifdef UEFI_USER_KERNEL
.balign 8
.global aurora_kernel_probe_target
aurora_kernel_probe_target:
    .quad 0
.endif
.section .note.GNU-stack,"",@progbits

/* Trusted no-argument scalar launcher, linked into each independent user image. */
.section .text.user_entry,"ax"
.code64
.global aurora_program_entry
.global aurora_program_return_pc
.extern aurora_user_main
aurora_program_entry:
    /* The privileged launcher must not leak earlier integer register state. */
    or %rbx, %rax
    or %rcx, %rax
    or %rdx, %rax
    or %rbp, %rax
    or %rsi, %rax
    or %rdi, %rax
    or %r8, %rax
    or %r9, %rax
    or %r10, %rax
    or %r11, %rax
    or %r12, %rax
    or %r13, %rax
    or %r14, %rax
    or %r15, %rax
    jnz program_bad_entry
    cmpq $0, -8(%rsp)
    jne program_bad_entry
.ifdef AURORA_PROGRAM_BAD_RETURN
    mov $42, %eax
    int $0x81
.endif
.ifdef AURORA_PROGRAM_UNKNOWN_TRAP
    ud2
.endif
.ifdef AURORA_PROGRAM_FOREIGN_CODE
    mov $0x1b1000, %rax
    call *%rax
.endif
.ifdef AURORA_PROGRAM_FOREIGN_STACK
    mov 0x104000, %al
.endif
    call aurora_user_main
    int $0x81
aurora_program_return_pc:
    ud2
program_bad_entry:
    ud2
.section .note.GNU-stack,"",@progbits

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
.ifdef AURORA_PROGRAM_APIC_READ
    mov $0xfee00000, %rax
    mov (%rax), %al
.endif
.ifdef AURORA_PROGRAM_SOFTINT
    int $64
.endif
.ifdef AURORA_PROGRAM_FPU
    fnop
.endif
.ifdef AURORA_PROGRAM_CONTEXT_PROBE
    pushq $500000
    mov $17, %rax
    mov $34, %rbx
    mov $51, %rcx
    mov $68, %rdx
    mov $85, %rbp
    mov $102, %rsi
    mov $119, %rdi
    mov $136, %r8
    mov $153, %r9
    mov $170, %r10
    mov $187, %r11
    mov $204, %r12
    mov $221, %r13
    mov $238, %r14
    mov $255, %r15
    std
.global aurora_context_probe_begin
aurora_context_probe_begin:
    decq (%rsp)
    jnz aurora_context_probe_begin
.global aurora_context_probe_end
aurora_context_probe_end:
    cmp $17, %rax
    jne program_bad_entry
    cmp $34, %rbx
    jne program_bad_entry
    cmp $51, %rcx
    jne program_bad_entry
    cmp $68, %rdx
    jne program_bad_entry
    cmp $85, %rbp
    jne program_bad_entry
    cmp $102, %rsi
    jne program_bad_entry
    cmp $119, %rdi
    jne program_bad_entry
    cmp $136, %r8
    jne program_bad_entry
    cmp $153, %r9
    jne program_bad_entry
    cmp $170, %r10
    jne program_bad_entry
    cmp $187, %r11
    jne program_bad_entry
    cmp $204, %r12
    jne program_bad_entry
    cmp $221, %r13
    jne program_bad_entry
    cmp $238, %r14
    jne program_bad_entry
    cmp $255, %r15
    jne program_bad_entry
    pushfq
    pop %rax
    test $0x400, %eax
    jz program_bad_entry
    cld
    add $8, %rsp
.endif
    call aurora_user_main
    int $0x81
aurora_program_return_pc:
    ud2
program_bad_entry:
    ud2
.section .note.GNU-stack,"",@progbits

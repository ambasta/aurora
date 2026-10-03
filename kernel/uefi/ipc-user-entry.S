.section .text.user_entry,"ax"
.code64
.global aurora_program_entry
.global aurora_program_return_pc
aurora_program_entry:
    or %rbx,%rax
    or %rbp,%rax
    or %r10,%rax
    or %r11,%rax
    or %r12,%rax
    or %r13,%rax
    or %r14,%rax
    or %r15,%rax
    jnz bad_entry
    cmpq $0,-8(%rsp)
    jne bad_entry
    push %rdi
    push %rdx
    push %rcx
    push %r8
    push %r9
    sub $8,%rsp
    mov %r9,%rdx
    call aurora_user_main
    add $8,%rsp
    pop %r9
    pop %r8
    pop %rcx
    pop %rdx
    pop %rdi
    mov $1,%esi
.ifdef IPC_OWNER
    xor $1,%edx
.endif
.ifdef IPC_STALE
    inc %rcx
.endif
.ifdef IPC_VERSION
    mov $2,%esi
.endif
.ifdef IPC_TRANSACTION
    inc %r8
.endif
.ifdef IPC_PHASE
    mov $1,%edi
.endif
.ifdef IPC_SITE
    int $0x81
.global aurora_probe_pc
aurora_probe_pc:
    ud2
.endif
.ifdef IPC_UNKNOWN
.global aurora_probe_pc
aurora_probe_pc:
    ud2
.endif
    int $0x81
aurora_program_return_pc:
    ud2
bad_entry:
    ud2
.section .note.GNU-stack,"",@progbits

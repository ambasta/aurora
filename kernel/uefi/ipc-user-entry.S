.ifdef SNAPSHOT_SERVICE
.set COPIED_SERVICE,1
.endif
.ifdef PROGRAM_NOTE_SERVICE
.set COPIED_SERVICE,1
.endif
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
.ifdef COPIED_SERVICE
    # Fixed 96-byte record at S-112, followed by a 16-byte sentinel gap.
    # Snapshot ends in zero padding; NoteRead64 owns the final length qword.
    # Reserve before the envelope: calls and locals must grow below the record.
    sub $112,%rsp
.endif
    push %rdi
    push %rdx
    push %rcx
    push %r8
    push %r9
    sub $8,%rsp
    mov %r9,%rdx
.ifdef IPC_PEER_CODE
    movabs $0x10000000000,%r10
.global aurora_probe_pc
aurora_probe_pc:
    mov (%r10),%rax
.endif
.ifdef IPC_MMIO
    movabs $0xffff900000000000,%rax
.global aurora_probe_pc
aurora_probe_pc:
    mov (%rax),%eax
.endif
.ifdef IPC_SOFTINT
.global aurora_probe_pc
aurora_probe_pc:
    int $64
.endif
.ifdef IPC_FPU
.global aurora_probe_pc
aurora_probe_pc:
    fnop
.endif
.ifdef IPC_CONTEXT
.ifdef IPC_CLIENT_CONTEXT
    cmp $0,%rdi
.else
    cmp $1,%rdi
.endif
    jne skip_context_probe
    push %rdi
    push %rsi
    push %rdx
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
.global aurora_budget_context_begin
aurora_budget_context_begin:
    decq (%rsp)
    jnz aurora_budget_context_begin
.global aurora_budget_context_end
aurora_budget_context_end:
    cmp $17, %rax
    jne bad_entry
    cmp $34, %rbx
    jne bad_entry
    cmp $51, %rcx
    jne bad_entry
    cmp $68, %rdx
    jne bad_entry
    cmp $85, %rbp
    jne bad_entry
    cmp $102, %rsi
    jne bad_entry
    cmp $119, %rdi
    jne bad_entry
    cmp $136, %r8
    jne bad_entry
    cmp $153, %r9
    jne bad_entry
    cmp $170, %r10
    jne bad_entry
    cmp $187, %r11
    jne bad_entry
    cmp $204, %r12
    jne bad_entry
    cmp $221, %r13
    jne bad_entry
    cmp $238, %r14
    jne bad_entry
    cmp $255, %r15
    jne bad_entry
    pushfq
    pop %rax
    test $0x400, %eax
    jz bad_entry
    cld
    add $8, %rsp
    pop %rdx
    pop %rsi
    pop %rdi
skip_context_probe:
.endif
.ifdef CALL_CLIENT
    sub $48,%rsp
    mov 80(%rsp),%rax
    mov %rax,0(%rsp)
    mov 72(%rsp),%rax
    mov %rax,8(%rsp)
    mov 88(%rsp),%rax
    mov %rax,16(%rsp)
    mov %rsi,24(%rsp)
    mov %r9,32(%rsp)
    mov %rsp,%r11
    call @aurora_user_main@
    add $48,%rsp
.else
.ifdef COPIED_SERVICE
    lea 48(%rsp),%r11
.ifdef PROGRAM_NOTE_SERVICE
    call @aurora_user_main@
.else
    call __au_v_m1_16snapshot_service_n0__d16aurora_user_main
.endif
.else
    call aurora_user_main
.endif
 .endif
    add $8,%rsp
    pop %r9
    pop %r8
    pop %rcx
    pop %rdx
    pop %rdi
.ifdef COPIED_SERVICE
    add $112,%rsp
.ifdef SNAPSHOT_REPLY_RESERVED
    movabs $0x8000000000000000,%r10
    or %r10,%rax
.endif
.ifdef SNAPSHOT_REPLY_BYTE
    xor $0x100,%rax
.endif
.endif
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
.ifdef IPC_ORDINAL
    inc %r9
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
.ifdef CALL_CLIENT
.global __au_runtime_call
.type __au_runtime_call,@function
__au_runtime_call:
    int $0x82
.global aurora_call_return_pc
aurora_call_return_pc:
    ret
.size __au_runtime_call,.-__au_runtime_call
.endif
.ifndef COPIED_SERVICE
.ifndef CALL_CLIENT
.section .note.GNU-stack,"",@progbits
.endif
.endif

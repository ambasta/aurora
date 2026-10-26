# PROGRAM_APPEND_CLIENT_ABI: exact Call prefix, fixture scalar and copied result.
# Same original client slot. Only phase 16 selects the live append invocation.
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
    # [S-80,S-8) result, [S-8,S) zero sentinel. The envelope and all
    # generated locals grow below the result, including across Call suspension.
    sub $80,%rsp
    push %rdi
    push %rdx
    push %rcx
    push %r8
    push %r9
    sub $8,%rsp
    cmp $16,%rdi
    je append_entry
    mov %r9,%rdx
    call @aurora_user_main@
    jmp caller_return
append_entry:
    # [RSP-32,RSP-8) contains CallSession(slot,generation) and probe.
    sub $32,%rsp
    mov 64(%rsp),%rax
    mov %rax,0(%rsp)
    mov 56(%rsp),%rax
    mov %rax,8(%rsp)
    mov %rsi,16(%rsp)
    mov %rsp,%r11
    lea 80(%rsp),%r10
    call @append_candidate@
    add $32,%rsp
    # Generated RAX is incidental for an aggregate result.
    mov $1,%eax
caller_return:
    add $8,%rsp
    pop %r9
    pop %r8
    pop %rcx
    pop %rdx
    pop %rdi
    add $80,%rsp
    mov $1,%esi
    int $0x81
aurora_program_return_pc:
    ud2
bad_entry:
    ud2
.global __au_runtime_call
.type __au_runtime_call,@function
__au_runtime_call:
    int $0x82
.global aurora_call_return_pc
aurora_call_return_pc:
    ret
.size __au_runtime_call,.-__au_runtime_call

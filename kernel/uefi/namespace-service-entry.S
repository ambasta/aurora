# NAMESPACE_OWNER_ABI: one sealed Serve prefix and a fixture-only scalar probe.
# No pointer or owner state crosses this entry. Baseline launches carry probe zero.
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
    sub $40,%rsp
    # RSP=S-80: prefix[16], probe[8], zero sentinel[8], alignment[8].
    mov 64(%rsp),%rax
    mov %rax,0(%rsp)
    mov 56(%rsp),%rax
    mov %rax,8(%rsp)
    mov 40(%rsp),%rax
    mov %rax,16(%rsp)
    movq $0,24(%rsp)
    mov %rsp,%r11
    call @aurora_user_main@
    add $40,%rsp
    pop %r9
    pop %r8
    pop %rcx
    pop %rdx
    pop %rdi
    mov $1,%esi
    int $0x81
aurora_program_return_pc:
    ud2
bad_entry:
    ud2
.global __au_runtime_serve_exchange
.type __au_runtime_serve_exchange,@function
__au_runtime_serve_exchange:
    int $0x82
.global aurora_serve_return_pc
aurora_serve_return_pc:
    ret
.size __au_runtime_serve_exchange,.-__au_runtime_serve_exchange

.section .note.GNU-stack,"",@progbits

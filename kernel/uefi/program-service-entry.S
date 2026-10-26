# PROGRAM_APPEND_SERVICE_ABI: exact Serve prefix and closed copied input.
# The existing service image retains its scalar entry for non-append commands.
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
    # Copied phase/probe/offset/prefix/suffix remains [S-176,S-8).
    # Only this entry supplies the sealed grant at [S-192,S-176).
    # All generated locals grow below the saved launch envelope.
    sub $192,%rsp
    mov %rdx,0(%rsp)
    mov %rcx,8(%rsp)
    push %rdi
    push %rdx
    push %rcx
    push %r8
    push %r9
    sub $8,%rsp
    cmp $17,%rdi
    je append_entry
    lea 64(%rsp),%r11
    call @aurora_user_main@
    jmp service_return
append_entry:
    lea 48(%rsp),%r11
    call @append_producer@
service_return:
    add $8,%rsp
    pop %r9
    pop %r8
    pop %rcx
    pop %rdx
    pop %rdi
    add $192,%rsp
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

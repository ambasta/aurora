# Exact copied Call entry for the opt-in scratchpad only. The native loader
# stages command bytes at S-176 and leaves prefix/result/sentinel pristine.
# No address in the copied value selects a destination or grants authority.
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
    # [S-192,S-96) argument, [S-96,S-16) result, [S-16,S) sentinel.
    sub $192,%rsp
    push %rdi
    push %rdx
    push %rcx
    push %r8
    push %r9
    sub $8,%rsp
    # RSP=S-240. Construct the sole prefix from the saved launch envelope.
    mov 32(%rsp),%rax
    mov %rax,48(%rsp)
    mov 24(%rsp),%rax
    mov %rax,56(%rsp)
    lea 48(%rsp),%r11
    lea 144(%rsp),%r10
    call @aurora_user_main@
    add $8,%rsp
    pop %r9
    pop %r8
    pop %rcx
    pop %rdx
    pop %rdi
    add $192,%rsp
    # Incidental generated RAX is not a semantic result.
    mov $1,%eax
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

.section .note.GNU-stack,"",@progbits

# Independent SysV envelope for the private hosted lexer adapter. The caller
# supplies a target so intentional corruption controls exercise these checks.
.text
.globl checked_hosted_lexer_call
.type checked_hosted_lexer_call,@function
checked_hosted_lexer_call:
    movq %rsp, %r11
    andq $15, %r11
    cmpq $8, %r11
    jne .Lhosted_abi_fail
    pushq %rbp
    movq %rsp, %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $24, %rsp
    movq %rbp, 0(%rsp)
    movabsq $0x789abcdef0123456, %r11
    movq %r11, 8(%rsp)
    movabsq $0x89abcdef01234567, %r11
    movq %r11, 16(%rsp)
    movabsq $0x123456789abcdef0, %rbx
    movabsq $0x23456789abcdef01, %r12
    movabsq $0x3456789abcdef012, %r13
    movabsq $0x456789abcdef0123, %r14
    movabsq $0x56789abcdef01234, %r15
    call *%rdx
    cmpq 0(%rsp), %rbp
    jne .Lhosted_abi_fail
    movabsq $0x123456789abcdef0, %r11
    cmpq %r11, %rbx
    jne .Lhosted_abi_fail
    movabsq $0x23456789abcdef01, %r11
    cmpq %r11, %r12
    jne .Lhosted_abi_fail
    movabsq $0x3456789abcdef012, %r11
    cmpq %r11, %r13
    jne .Lhosted_abi_fail
    movabsq $0x456789abcdef0123, %r11
    cmpq %r11, %r14
    jne .Lhosted_abi_fail
    movabsq $0x56789abcdef01234, %r11
    cmpq %r11, %r15
    jne .Lhosted_abi_fail
    leaq -64(%rbp), %r11
    cmpq %r11, %rsp
    jne .Lhosted_abi_fail
    movabsq $0x789abcdef0123456, %r11
    cmpq %r11, 8(%rsp)
    jne .Lhosted_abi_fail
    movabsq $0x89abcdef01234567, %r11
    cmpq %r11, 16(%rsp)
    jne .Lhosted_abi_fail
    addq $24, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    leave
    ret
.Lhosted_abi_fail:
    ud2
.size checked_hosted_lexer_call,.-checked_hosted_lexer_call

.section .note.GNU-stack,"",@progbits

# Independently handwritten SysV envelope around the private service bridge.
# Exact stack alignment, canaries and every non-frame callee-save are checked.
.text
.globl checked_display_entry
.type checked_display_entry,@function
checked_display_entry:
    movq %rsp, %r11
    andq $15, %r11
    cmpq $8, %r11
    jne .Labi_fail
    pushq %rbp
    movq %rsp, %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $24, %rsp
    movq $0x11223344, 8(%rsp)
    movq $0x55667788, 16(%rsp)
    movq $0x13579, %rbx
    movq $0x24680, %r12
    movq $0x35791, %r13
    movq $0x46802, %r14
    movq $0x57913, %r15
    call __au_runtime_display_entry
    cmpq $0x13579, %rbx
    jne .Labi_fail
    cmpq $0x24680, %r12
    jne .Labi_fail
    cmpq $0x35791, %r13
    jne .Labi_fail
    cmpq $0x46802, %r14
    jne .Labi_fail
    cmpq $0x57913, %r15
    jne .Labi_fail
    leaq -64(%rbp), %r11
    cmpq %r11, %rsp
    jne .Labi_fail
    cmpq $0x11223344, 8(%rsp)
    jne .Labi_fail
    cmpq $0x55667788, 16(%rsp)
    jne .Labi_fail
    addq $24, %rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    leave
    ret
.Labi_fail:
    ud2
.size checked_display_entry,.-checked_display_entry
.section .note.GNU-stack,"",@progbits

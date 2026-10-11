# Independent SysV envelope for the private hosted parser adapter. The caller
# supplies a target in RCX so three-argument parsing and corruption controls
# exercise the same checks. RAX is preserved for the scalar count result.
.text
.globl checked_hosted_parser_call
.type checked_hosted_parser_call,@function
checked_hosted_parser_call:
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
    call *%rcx
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
.size checked_hosted_parser_call,.-checked_hosted_parser_call

.macro clobber_control register
.globl hosted_parser_clobber_\register
.type hosted_parser_clobber_\register,@function
hosted_parser_clobber_\register:
    xorq %\register, %\register
    ret
.size hosted_parser_clobber_\register,.-hosted_parser_clobber_\register
.endm
clobber_control rbp
clobber_control rbx
clobber_control r12
clobber_control r13
clobber_control r14
clobber_control r15

.globl hosted_parser_clobber_canary
.type hosted_parser_clobber_canary,@function
hosted_parser_clobber_canary:
    movq $0, 16(%rsp)
    ret
.size hosted_parser_clobber_canary,.-hosted_parser_clobber_canary

.globl hosted_parser_shift_stack
.type hosted_parser_shift_stack,@function
hosted_parser_shift_stack:
    popq %r11
    addq $8, %rsp
    jmp *%r11
.size hosted_parser_shift_stack,.-hosted_parser_shift_stack

.globl hosted_parser_misaligned_call
.type hosted_parser_misaligned_call,@function
hosted_parser_misaligned_call:
    # Deliberately violate SysV call-site alignment; the envelope must trap.
    call checked_hosted_parser_call
    ret
.size hosted_parser_misaligned_call,.-hosted_parser_misaligned_call
# Preserve each original SysV signature while selecting the exact generated shim.
.macro checked_entry operation
.globl checked_hosted_parser_\operation
.type checked_hosted_parser_\operation,@function
checked_hosted_parser_\operation:
    leaq aurora_hosted_parser_\operation(%rip), %rcx
    jmp checked_hosted_parser_call
.size checked_hosted_parser_\operation,.-checked_hosted_parser_\operation
.endm
checked_entry create
checked_entry parse
checked_entry count
checked_entry read
checked_entry edges
checked_entry edge
checked_entry release
.section .note.GNU-stack,"",@progbits

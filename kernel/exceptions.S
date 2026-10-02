.section .text
.code64
.extern aurora_exception_dispatch
.extern aurora_leave_user
.global aurora_exception_0
aurora_exception_0:
    pushq $0
    pushq $0
    jmp exception_common
.global aurora_exception_1
aurora_exception_1:
    pushq $0
    pushq $1
    jmp exception_common
.global aurora_exception_2
aurora_exception_2:
    pushq $0
    pushq $2
    jmp exception_common
.global aurora_exception_3
aurora_exception_3:
    pushq $0
    pushq $3
    jmp exception_common
.global aurora_exception_4
aurora_exception_4:
    pushq $0
    pushq $4
    jmp exception_common
.global aurora_exception_5
aurora_exception_5:
    pushq $0
    pushq $5
    jmp exception_common
.global aurora_exception_6
aurora_exception_6:
    pushq $0
    pushq $6
    jmp exception_common
.global aurora_exception_7
aurora_exception_7:
    pushq $0
    pushq $7
    jmp exception_common
.global aurora_exception_8
aurora_exception_8:
    pushq $8
    jmp exception_common
.global aurora_exception_9
aurora_exception_9:
    pushq $0
    pushq $9
    jmp exception_common
.global aurora_exception_10
aurora_exception_10:
    pushq $10
    jmp exception_common
.global aurora_exception_11
aurora_exception_11:
    pushq $11
    jmp exception_common
.global aurora_exception_12
aurora_exception_12:
    pushq $12
    jmp exception_common
.global aurora_exception_13
aurora_exception_13:
    pushq $13
    jmp exception_common
.global aurora_exception_14
aurora_exception_14:
    pushq $14
    jmp exception_common
.global aurora_exception_15
aurora_exception_15:
    pushq $0
    pushq $15
    jmp exception_common
.global aurora_exception_16
aurora_exception_16:
    pushq $0
    pushq $16
    jmp exception_common
.global aurora_exception_17
aurora_exception_17:
    pushq $17
    jmp exception_common
.global aurora_exception_18
aurora_exception_18:
    pushq $0
    pushq $18
    jmp exception_common
.global aurora_exception_19
aurora_exception_19:
    pushq $0
    pushq $19
    jmp exception_common
.global aurora_exception_20
aurora_exception_20:
    pushq $0
    pushq $20
    jmp exception_common
.global aurora_exception_21
aurora_exception_21:
    pushq $21
    jmp exception_common
.global aurora_exception_22
aurora_exception_22:
    pushq $0
    pushq $22
    jmp exception_common
.global aurora_exception_23
aurora_exception_23:
    pushq $0
    pushq $23
    jmp exception_common
.global aurora_exception_24
aurora_exception_24:
    pushq $0
    pushq $24
    jmp exception_common
.global aurora_exception_25
aurora_exception_25:
    pushq $0
    pushq $25
    jmp exception_common
.global aurora_exception_26
aurora_exception_26:
    pushq $0
    pushq $26
    jmp exception_common
.global aurora_exception_27
aurora_exception_27:
    pushq $0
    pushq $27
    jmp exception_common
.global aurora_exception_28
aurora_exception_28:
    pushq $0
    pushq $28
    jmp exception_common
.global aurora_exception_29
aurora_exception_29:
    pushq $29
    jmp exception_common
.global aurora_exception_30
aurora_exception_30:
    pushq $30
    jmp exception_common
.global aurora_exception_31
aurora_exception_31:
    pushq $0
    pushq $31
    jmp exception_common
.global aurora_user_return
aurora_user_return:
    pushq $0
    pushq $128
    jmp exception_common
.global aurora_unexpected_interrupt
aurora_unexpected_interrupt:
    pushq $0
    pushq $255
exception_common:
    cld
    push %rax
    push %rbx
    push %rcx
    push %rdx
    push %rbp
    push %rsi
    push %rdi
    push %r8
    push %r9
    push %r10
    push %r11
    push %r12
    push %r13
    push %r14
    push %r15
    mov 120(%rsp), %rdi
    mov 128(%rsp), %rsi
    mov 136(%rsp), %rdx
    mov 144(%rsp), %rcx
    mov %rsp, %r8
    mov 112(%rsp), %r9
    mov %rsp, %rbx
    and $-16, %rsp
    call aurora_exception_dispatch
    cmp $1, %rax
    je aurora_leave_user
    mov %rbx, %rsp
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %r11
    pop %r10
    pop %r9
    pop %r8
    pop %rdi
    pop %rsi
    pop %rbp
    pop %rdx
    pop %rcx
    pop %rbx
    pop %rax
    add $16, %rsp
    iretq
.global aurora_breakpoint_probe
aurora_breakpoint_probe:
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
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
    int3
    cmp $17, %rax
    jne probe_failed
    cmp $34, %rbx
    jne probe_failed
    cmp $51, %rcx
    jne probe_failed
    cmp $68, %rdx
    jne probe_failed
    cmp $85, %rbp
    jne probe_failed
    cmp $102, %rsi
    jne probe_failed
    cmp $119, %rdi
    jne probe_failed
    cmp $136, %r8
    jne probe_failed
    cmp $153, %r9
    jne probe_failed
    cmp $170, %r10
    jne probe_failed
    cmp $187, %r11
    jne probe_failed
    cmp $204, %r12
    jne probe_failed
    cmp $221, %r13
    jne probe_failed
    cmp $238, %r14
    jne probe_failed
    cmp $255, %r15
    jne probe_failed
    pushfq
    pop %rax
    cld
    test $0x400, %rax
    jz probe_failed
    mov $1, %eax
    jmp probe_done
probe_failed:
    cld
    xor %eax, %eax
probe_done:
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbp
    pop %rbx
    ret
.section .rodata
.global aurora_exception_vectors
aurora_exception_vectors:
    .quad aurora_exception_0
    .quad aurora_exception_1
    .quad aurora_exception_2
    .quad aurora_exception_3
    .quad aurora_exception_4
    .quad aurora_exception_5
    .quad aurora_exception_6
    .quad aurora_exception_7
    .quad aurora_exception_8
    .quad aurora_exception_9
    .quad aurora_exception_10
    .quad aurora_exception_11
    .quad aurora_exception_12
    .quad aurora_exception_13
    .quad aurora_exception_14
    .quad aurora_exception_15
    .quad aurora_exception_16
    .quad aurora_exception_17
    .quad aurora_exception_18
    .quad aurora_exception_19
    .quad aurora_exception_20
    .quad aurora_exception_21
    .quad aurora_exception_22
    .quad aurora_exception_23
    .quad aurora_exception_24
    .quad aurora_exception_25
    .quad aurora_exception_26
    .quad aurora_exception_27
    .quad aurora_exception_28
    .quad aurora_exception_29
    .quad aurora_exception_30
    .quad aurora_exception_31
.section .note.GNU-stack,"",@progbits

.section .text
.code64
.global aurora_user_probe
aurora_user_probe:
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
    mov %rsp, aurora_saved_kernel_rsp(%rip)
    pushq $0x23
    pushq $0x1e4000
    pushq $2
    pushq $0x1b
    pushq $0x1d0000
    mov $0x23, %ax
    mov %ax, %ds
    mov %ax, %es
    xor %eax, %eax
    xor %ebx, %ebx
    xor %ecx, %ecx
    xor %edx, %edx
    xor %ebp, %ebp
    xor %esi, %esi
    xor %r8d, %r8d
    xor %r9d, %r9d
    xor %r10d, %r10d
    xor %r11d, %r11d
    xor %r12d, %r12d
    xor %r13d, %r13d
    xor %r14d, %r14d
    xor %r15d, %r15d
    iretq
.global aurora_leave_user
aurora_leave_user:
    mov $0x10, %ax
    mov %ax, %ds
    mov %ax, %es
    mov aurora_saved_kernel_rsp(%rip), %rsp
    movq $0, aurora_saved_kernel_rsp(%rip)
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbp
    pop %rbx
    mov $1, %eax
    ret
.section .bss
.align 8
aurora_saved_kernel_rsp: .skip 8
/* Relocation-free controlled probe, copied into its only user-executable page. */
.section .rodata.user,"a"
.global aurora_user_payload_begin
.global aurora_user_payload_end
aurora_user_payload_begin:
    mov %cs, %ax
    and $3, %eax
    cmp $3, %eax
    jne user_bad
    pushq $0x5a
    pop %rax
    cmp $0x5a, %rax
    jne user_bad
    cmp $1, %edi
    je user_read_kernel
    cmp $2, %edi
    je user_write_kernel
    cmp $3, %edi
    je user_cli
    cmp $4, %edi
    je user_write_code
    cmp $5, %edi
    je user_execute_stack
    cmp $6, %edi
    je user_io
    test %edi, %edi
    jne user_bad
    mov $42, %eax
    int $0x80
    ud2
user_read_kernel:
    mov 0x10000, %al
    jmp user_bad
user_write_kernel:
    movb $0, 0x10000
    jmp user_bad
user_cli:
    cli
    jmp user_bad
user_write_code:
    movb $0, 0x1d0000
    jmp user_bad
user_execute_stack:
    mov $0x1e0000, %rax
    call *%rax
    jmp user_bad
user_io:
    outb %al, $0x80
user_bad:
    xor %eax, %eax
    int $0x80
    ud2
aurora_user_payload_end:
.section .note.GNU-stack,"",@progbits

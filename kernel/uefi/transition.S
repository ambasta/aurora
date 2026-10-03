.section .text.transition,"ax"
.code64
.global uefi_transition_begin
.global uefi_transition_end
.global uefi_transition_fault
uefi_transition_begin:
    cli
    mov %rsi, %rsp
    xor %ebp, %ebp
    /* r9 supplies the arena-owned IDT, already pointing into this copied page. */
    sub $16, %rsp
    movw $4095, (%rsp)
    mov %r9, 2(%rsp)
    lidt (%rsp)
    mov %rdi, %cr3
    lea local_gdt(%rip), %rax
    movw $23, (%rsp)
    mov %rax, 2(%rsp)
    lgdt (%rsp)
    add $16, %rsp
    pushq $8
    lea local_code(%rip), %rax
    push %rax
    lretq
local_code:
    mov $16, %eax
    mov %ax, %ds
    mov %ax, %es
    mov %ax, %ss
    mov %rcx, %rdi
    mov %r8, %rsi
    jmp *%rdx
uefi_transition_fault:
    cli
    mov $0xf4, %dx
    mov $0x11, %al
    out %al, %dx
1:  hlt
    jmp 1b
.balign 8
local_gdt:
    .quad 0,0x00af9b000000ffff,0x00cf93000000ffff
uefi_transition_end:
.section .note.GNU-stack,"",@progbits

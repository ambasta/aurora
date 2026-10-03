/* Disposable emulator-only BIOS transport. No host bootloader is installed. */
.code16
.section .text
.global _boot
_boot:
    ljmp $0, $normalized
normalized:
    cli
    xor %ax, %ax
    mov %ax, %ds
    mov %ax, %es
    mov %ax, %ss
    mov $0x7c00, %sp
    cld
    mov %dl, drive
    sti
    mov $packet, %si
    mov $0x42, %ah
    int $0x13
    jc disk_error
    /* Bounded firmware E820 handoff: count at 0x5000, 24-byte entries at 0x5008. */
    xor %ebx, %ebx
    movw $0, 0x5000
    mov $0x5008, %di
memory_map_next:
    movl $1, %es:20(%di)
    mov $0xe820, %eax
    mov $0x534d4150, %edx
    mov $24, %ecx
    int $0x15
    jc memory_map_done
    cmp $0x534d4150, %eax
    jne memory_map_invalid
    cmp $20, %ecx
    jb memory_map_invalid
    incw 0x5000
    add $24, %di
    cmpw $32, 0x5000
    jb memory_map_continue
    test %ebx, %ebx
    jz memory_map_done
    jmp memory_map_invalid
memory_map_continue:
    test %ebx, %ebx
    jnz memory_map_next
    jmp memory_map_done
memory_map_invalid:
    movw $0, 0x5000
memory_map_done:
    cli
    in $0x92, %al
    or $2, %al
    out %al, $0x92
    /* Zero PML4, PDPT and PD; identity map the first 2 MiB. */
    xor %eax, %eax
    mov $0x1000, %di
    mov $3072, %cx
    rep stosl
    movl $0x2003, 0x1000
    movl $0x3003, 0x2000
    movl $0x0083, 0x3000
    lgdt gdt_pointer
    mov %cr4, %eax
    or $0x20, %eax
    mov %eax, %cr4
    mov $0x1000, %eax
    mov %eax, %cr3
    mov $0xc0000080, %ecx
    rdmsr
    or $0x100, %eax
    wrmsr
    mov %cr0, %eax
    or $0x80000001, %eax
    mov %eax, %cr0
    ljmpl $8, $long_mode
disk_error:
    mov $0x0e45, %ax
    int $0x10
    cli
1:  hlt
    jmp 1b
.align 8
gdt:
    .quad 0
    .quad 0x00af9a000000ffff
    .quad 0x00cf92000000ffff
gdt_pointer:
    .word 23
    .long gdt
.balign 4
packet:
    .byte 16, 0
    .word 96
    .word 0, 0x1000
    .quad 1
drive: .byte 0
.code64
long_mode:
    mov $16, %ax
    mov %ax, %ds
    mov %ax, %es
    mov %ax, %ss
    mov $0x90000, %rsp
    xor %rbp, %rbp
    mov $0x10000, %rax
    jmp *%rax
.org 510
.word 0xaa55

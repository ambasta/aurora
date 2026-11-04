/* Copied below 1 MiB. Every address within this page is relative or patched
 * before publication. There are no loader/payload relocations in the blob. */
.section .rodata.ap_worker_start,"a"
.balign 16
.code16
.global ap_worker_start_begin, ap_worker_start_end
.global ap_worker_start_gdtr, ap_worker_start_gdt
.global ap_worker_start_far32, ap_worker_start_far64
.global ap_worker_start_protected, ap_worker_start_long, ap_worker_start_parameters
ap_worker_start_begin:
    cli
    cld
    mov %cs,%ax
    mov %ax,%ds
    mov %ax,%es
    xor %ebx,%ebx
    mov %ax,%bx
    shl $4,%ebx
    lgdtl %cs:(ap_worker_start_gdtr-ap_worker_start_begin)
    mov %cr0,%eax
    or $1,%eax
    mov %eax,%cr0
    ljmpl *%cs:(ap_worker_start_far32-ap_worker_start_begin)
.code32
ap_worker_start_protected:
    mov $16,%ax
    mov %ax,%ds
    mov %ax,%es
    mov %ax,%ss
    mov (ap_worker_start_parameters-ap_worker_start_begin)(%ebx),%eax
    mov %eax,%cr3
    mov %cr4,%eax
    or $0x20,%eax
    mov %eax,%cr4
    mov $0xc0000080,%ecx
    rdmsr
    or $0x900,%eax              /* LME and NXE; grant required both. */
    wrmsr
    mov %cr0,%eax
    or $0x80010023,%eax         /* PG, WP, NE, MP and PE; integer only. */
    and $0xfffffff3,%eax        /* Clear EM and TS for initial setup. */
    mov %eax,%cr0
    ljmpl *(ap_worker_start_far64-ap_worker_start_begin)(%ebx)
.code64
ap_worker_start_long:
    mov (ap_worker_start_parameters-ap_worker_start_begin+16)(%rbx),%rsp
    xor %ebp,%ebp
    mov (ap_worker_start_parameters-ap_worker_start_begin+24)(%rbx),%rdi
    lgdt (ap_worker_start_parameters-ap_worker_start_begin+48)(%rbx)
    pushq $8
    lea 1f(%rip),%rax
    push %rax
    lretq
1:
    mov $16,%eax
    mov %ax,%ds
    mov %ax,%es
    mov %ax,%ss
    mov $24,%eax
    ltr %ax
    mov (ap_worker_start_parameters-ap_worker_start_begin+32)(%rbx),%rax
    mov %rax,%rdx
    shr $32,%rdx
    mov $0xc0000101,%ecx        /* CPU-local GS base is the reply page. */
    wrmsr
    lidt (ap_worker_start_parameters-ap_worker_start_begin+58)(%rbx)
    mov (ap_worker_start_parameters-ap_worker_start_begin+8)(%rbx),%rax
    mov (ap_worker_start_parameters-ap_worker_start_begin+40)(%rbx),%rdx
    mov %cr0,%rcx
    or $8,%rcx                 /* TS keeps the island integer-only. */
    mov %rcx,%cr0
    /* The next instruction must reside in the permanent code whitelist,
     * so switch CR3 at that entry rather than removing this page here. */
    jmp *%rdx
.balign 8
ap_worker_start_gdt:
    .quad 0,0x00cf9b000000ffff,0x00cf93000000ffff,0x00af9b000000ffff
ap_worker_start_gdtr:
    .word 31
    .long 0
ap_worker_start_far32:
    .long 0
    .word 8
ap_worker_start_far64:
    .long 0
    .word 24
.balign 8
ap_worker_start_parameters:
    .zero 68
ap_worker_start_end:
.code64
.section .note.GNU-stack,"",@progbits

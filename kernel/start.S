.section .text.entry,"ax"
.code64
.global _start
.extern aurora_kernel_main
.extern __bss_start
.extern __bss_end
_start:
    cld
    lea __bss_start(%rip), %rdi
    lea __bss_end(%rip), %rcx
    sub %rdi, %rcx
    xor %eax, %eax
    rep stosb
    call aurora_kernel_main
1:  cli
    hlt
    jmp 1b
.section .note.GNU-stack,"",@progbits

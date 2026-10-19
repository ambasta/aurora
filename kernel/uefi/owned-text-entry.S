.section .text.user_entry,"ax",@progbits
.code64
.global aurora_program_entry
aurora_program_entry:
    sub $16, %rsp
    mov %rdi, (%rsp)
    mov %rsi, 8(%rsp)
    mov %rsp, %r11
    call @aurora_user_main@
    add $16, %rsp
    int $0x81
.global aurora_program_return_pc
aurora_program_return_pc:
    ud2

.include "owned-bytes-stubs.inc"

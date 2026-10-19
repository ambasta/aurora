.section .text.user_entry,"ax",@progbits
.code64
.global aurora_program_entry
aurora_program_entry:
    sub $32, %rsp
    mov %rdi, (%rsp)
    mov %rsi, 8(%rsp)
    mov %rdx, 16(%rsp)
    .ifdef AURORA_CONSOLE_FIXTURE
    mov %rcx, 24(%rsp)
    .else
    movq $0, 24(%rsp)
    .endif
    mov %rsp, %r11
    call @aurora_user_main@
    add $32, %rsp
    int $0x81
.global aurora_program_return_pc
aurora_program_return_pc:
    ud2

.include "owned-bytes-stubs.inc"

.section .text
.global __au_runtime_console_next
.type __au_runtime_console_next,@function
__au_runtime_console_next:
    mov %rdx, %r10
    int $0x82
.global aurora_console_next_pc
aurora_console_next_pc:
    mov %rax, 0(%r10)
    mov %rdx, 8(%r10)
    mov %rcx, 16(%r10)
    ret
.size __au_runtime_console_next,.-__au_runtime_console_next
.global __au_runtime_console_put
.type __au_runtime_console_put,@function
__au_runtime_console_put:
    int $0x82
.global aurora_console_put_pc
aurora_console_put_pc:
    ret
.size __au_runtime_console_put,.-__au_runtime_console_put

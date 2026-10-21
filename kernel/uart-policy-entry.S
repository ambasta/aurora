# UART_POLICY_ABI: validate the exact copied record and Com1UartGrant signatures.
# SysV receives a private copied-argument record and copied-result destination.
# Only compiler facts select the source symbols. R11/R10 are compiler-private.
.text
.global __au_runtime_uart_initialize
.hidden __au_runtime_uart_initialize
.type __au_runtime_uart_initialize,@function
__au_runtime_uart_initialize:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @uart_initialize@
    leave
    ret
.size __au_runtime_uart_initialize,.-__au_runtime_uart_initialize
.global __au_runtime_uart_next
.hidden __au_runtime_uart_next
.type __au_runtime_uart_next,@function
__au_runtime_uart_next:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @uart_next@
    leave
    ret
.size __au_runtime_uart_next,.-__au_runtime_uart_next
.global __au_runtime_uart_put
.hidden __au_runtime_uart_put
.type __au_runtime_uart_put,@function
__au_runtime_uart_put:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @uart_put@
    leave
    ret
.size __au_runtime_uart_put,.-__au_runtime_uart_put
.section .note.GNU-stack,"",@progbits

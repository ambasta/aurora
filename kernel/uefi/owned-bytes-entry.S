# Private kernel grant bridge, assembled with the dedicated resource graph.
# No native owner crosses this boundary. The granting kernel checks complete
# cleanup before closing its still-live region. This is not a public source ABI.
.section .text
.global __au_runtime_bytes_kernel_entry
.hidden __au_runtime_bytes_kernel_entry
.type __au_runtime_bytes_kernel_entry,@function
__au_runtime_bytes_kernel_entry:
    pushq %rbp
    movq %rsp, %rbp
    subq $32, %rsp
    movq %rdi, (%rsp)
    movq %rsi, 8(%rsp)
    movq %rdx, 16(%rsp)
    movq $0, 24(%rsp)
    movq %rsp, %r11
    call __au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry
    leave
    ret
.size __au_runtime_bytes_kernel_entry,.-__au_runtime_bytes_kernel_entry
.section .note.GNU-stack,"",@progbits

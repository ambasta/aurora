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

# A separate copied-result call: R11 names the aligned 16-byte argument record,
# and R10 names fresh, disjoint caller-owned storage for exactly 72 result bytes.
# The granting native adapter closes the real region before inspecting the copy.
.global __au_runtime_bytes_kernel_produce
.hidden __au_runtime_bytes_kernel_produce
.type __au_runtime_bytes_kernel_produce,@function
__au_runtime_bytes_kernel_produce:
    pushq %rbp
    movq %rsp, %rbp
    subq $16, %rsp
    movq %rdi, (%rsp)
    movq %rsi, 8(%rsp)
    movq %rdx, %r10
    movq %rsp, %r11
    call __au_v_m1_18kernel_owned_bytes_n0__d14produce_record
    leave
    ret
.size __au_runtime_bytes_kernel_produce,.-__au_runtime_bytes_kernel_produce
.section .note.GNU-stack,"",@progbits

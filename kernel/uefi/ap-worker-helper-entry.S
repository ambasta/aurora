# AP_WORKER_HELPER_ABI: invocation-only readonly byte span, closed CRC32C consumer.
# C adapter: (result*, bytes*, length, offset, count). Source aggregate ABI
# receives a 72-byte argument record in R11 and fresh result storage in R10.
# The 56-byte contiguous span is kind, backing, three reserved words, start, length.
.text
.global __au_runtime_ap_worker_crc32c
.hidden __au_runtime_ap_worker_crc32c
.type __au_runtime_ap_worker_crc32c,@function
__au_runtime_ap_worker_crc32c:
    pushq %rbp
    movq %rsp,%rbp
    subq $80,%rsp
    movq %rdi,%r10
    movq $0,0(%rsp)
    movq %rsi,8(%rsp)
    movq $0,16(%rsp)
    movq $0,24(%rsp)
    movq $0,32(%rsp)
    movq $0,40(%rsp)
    movq %rdx,48(%rsp)
    movq %rcx,56(%rsp)
    movq %r8,64(%rsp)
    movq %rsp,%r11
    call @ap_worker_crc32c@
    leave
    ret
.size __au_runtime_ap_worker_crc32c,.-__au_runtime_ap_worker_crc32c
.section .note.GNU-stack,"",@progbits

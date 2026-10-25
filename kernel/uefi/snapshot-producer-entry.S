# The storage fixture's second closed Aurora object: the snapshot producer only.
# Assembled with its generated graph and local symbols; the kernel policies come
# from the image's primary object, so this bridge exports nothing else.
.text
.global __au_runtime_snapshot_produce
.hidden __au_runtime_snapshot_produce
.type __au_runtime_snapshot_produce,@function
__au_runtime_snapshot_produce:
    pushq %rbp
    movq %rsp, %rbp
    subq $16, %rsp
    movq %rdi, (%rsp)
    movq %rsi, 8(%rsp)
    movq %rdx, %r10
    movq %rsp, %r11
    call @produce_snapshot@
    leave
    ret
.size __au_runtime_snapshot_produce,.-__au_runtime_snapshot_produce

.section .note.GNU-stack,"",@progbits

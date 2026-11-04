# EXECUTION_BATCH_ABI: one pinned pair policy; no loan spans physical effects.
.text
.global __au_runtime_batch_create
.hidden __au_runtime_batch_create
.type __au_runtime_batch_create,@function
__au_runtime_batch_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_batch_create@
    leave
    ret
.size __au_runtime_batch_create,.-__au_runtime_batch_create
.global __au_runtime_batch_next
.hidden __au_runtime_batch_next
.type __au_runtime_batch_next,@function
__au_runtime_batch_next:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @process_batch_next@
    leave
    ret
.size __au_runtime_batch_next,.-__au_runtime_batch_next
.global __au_runtime_batch_accept
.hidden __au_runtime_batch_accept
.type __au_runtime_batch_accept,@function
__au_runtime_batch_accept:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    movq %r8,%rcx
    call @process_batch_accept@
    leave
    ret
.size __au_runtime_batch_accept,.-__au_runtime_batch_accept
.global __au_runtime_batch_result
.hidden __au_runtime_batch_result
.type __au_runtime_batch_result,@function
__au_runtime_batch_result:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @process_batch_result@
    leave
    ret
.size __au_runtime_batch_result,.-__au_runtime_batch_result

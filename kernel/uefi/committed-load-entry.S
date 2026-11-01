# COMMITTED_LOAD_ABI: short-lived opaque operation, no loan spans physical effects.
.text
.global __au_runtime_load_create
.hidden __au_runtime_load_create
.type __au_runtime_load_create,@function
__au_runtime_load_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_load_create@
    leave
    ret
.size __au_runtime_load_create,.-__au_runtime_load_create
.global __au_runtime_load_next
.hidden __au_runtime_load_next
.type __au_runtime_load_next,@function
__au_runtime_load_next:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @process_load_next@
    leave
    ret
.size __au_runtime_load_next,.-__au_runtime_load_next
.global __au_runtime_load_accept
.hidden __au_runtime_load_accept
.type __au_runtime_load_accept,@function
__au_runtime_load_accept:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movzbq %dl,%rsi
    movq %rcx,%rdx
    movq %r8,%rcx
    movq %r9,%r8
    call @process_load_accept@
    leave
    ret
.size __au_runtime_load_accept,.-__au_runtime_load_accept

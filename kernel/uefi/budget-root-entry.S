# RETAINED_BUDGET_ABI: initialized opaque plain root; no surviving loans.
.text
.global __au_runtime_budget_create
.hidden __au_runtime_budget_create
.type __au_runtime_budget_create,@function
__au_runtime_budget_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    subq $16,%rsp
    movq %rsi,0(%rsp)
    movq %rdx,8(%rsp)
    movq %rsp,%r11
    call @process_budget_create@
    leave
    ret
.size __au_runtime_budget_create,.-__au_runtime_budget_create
.global __au_runtime_budget_reset
.hidden __au_runtime_budget_reset
.type __au_runtime_budget_reset,@function
__au_runtime_budget_reset:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @process_budget_reset@
    leave
    ret
.size __au_runtime_budget_reset,.-__au_runtime_budget_reset
.global __au_runtime_budget_configure_next
.hidden __au_runtime_budget_configure_next
.type __au_runtime_budget_configure_next,@function
__au_runtime_budget_configure_next:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @process_budget_configure_next@
    leave
    ret
.size __au_runtime_budget_configure_next,.-__au_runtime_budget_configure_next
.global __au_runtime_budget_restart
.hidden __au_runtime_budget_restart
.type __au_runtime_budget_restart,@function
__au_runtime_budget_restart:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_budget_restart@
    leave
    ret
.size __au_runtime_budget_restart,.-__au_runtime_budget_restart
.global __au_runtime_budget_charge
.hidden __au_runtime_budget_charge
.type __au_runtime_budget_charge,@function
__au_runtime_budget_charge:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_budget_charge@
    leave
    ret
.size __au_runtime_budget_charge,.-__au_runtime_budget_charge
.global __au_runtime_budget_progress
.hidden __au_runtime_budget_progress
.type __au_runtime_budget_progress,@function
__au_runtime_budget_progress:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_budget_progress@
    leave
    ret
.size __au_runtime_budget_progress,.-__au_runtime_budget_progress
.global __au_runtime_budget_admitted
.hidden __au_runtime_budget_admitted
.type __au_runtime_budget_admitted,@function
__au_runtime_budget_admitted:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_budget_admitted@
    leave
    ret
.size __au_runtime_budget_admitted,.-__au_runtime_budget_admitted
.global __au_runtime_budget_available
.hidden __au_runtime_budget_available
.type __au_runtime_budget_available,@function
__au_runtime_budget_available:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_budget_available@
    leave
    ret
.size __au_runtime_budget_available,.-__au_runtime_budget_available
.global __au_runtime_budget_quantum
.hidden __au_runtime_budget_quantum
.type __au_runtime_budget_quantum,@function
__au_runtime_budget_quantum:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_budget_quantum@
    leave
    ret
.size __au_runtime_budget_quantum,.-__au_runtime_budget_quantum
.global __au_runtime_budget_used
.hidden __au_runtime_budget_used
.type __au_runtime_budget_used,@function
__au_runtime_budget_used:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_budget_used@
    leave
    ret
.size __au_runtime_budget_used,.-__au_runtime_budget_used

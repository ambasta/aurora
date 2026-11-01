# EXECUTION_LIFECYCLE_ABI: exact stable root, constructor transfer and consuming cleanup.
.text
.global __au_runtime_lifecycle_construct
.hidden __au_runtime_lifecycle_construct
.type __au_runtime_lifecycle_construct,@function
__au_runtime_lifecycle_construct:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @kernel::ExecutionOwner@
    leave
    ret
.size __au_runtime_lifecycle_construct,.-__au_runtime_lifecycle_construct
.global __au_runtime_lifecycle_prepare
.hidden __au_runtime_lifecycle_prepare
.type __au_runtime_lifecycle_prepare,@function
__au_runtime_lifecycle_prepare:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @lifecycle_prepare@
    leave
    ret
.size __au_runtime_lifecycle_prepare,.-__au_runtime_lifecycle_prepare
.global __au_runtime_lifecycle_execute
.hidden __au_runtime_lifecycle_execute
.type __au_runtime_lifecycle_execute,@function
__au_runtime_lifecycle_execute:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rdx,%r11
    movq %rsi,%rdi
    call @lifecycle_execute@
    leave
    ret
.size __au_runtime_lifecycle_execute,.-__au_runtime_lifecycle_execute
.global __au_runtime_lifecycle_force
.hidden __au_runtime_lifecycle_force
.type __au_runtime_lifecycle_force,@function
__au_runtime_lifecycle_force:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rdx,%r11
    movq %rsi,%rdi
    call @lifecycle_force@
    leave
    ret
.size __au_runtime_lifecycle_force,.-__au_runtime_lifecycle_force
.global __au_runtime_lifecycle_complete
.hidden __au_runtime_lifecycle_complete
.type __au_runtime_lifecycle_complete,@function
__au_runtime_lifecycle_complete:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @lifecycle_complete@
    leave
    ret
.size __au_runtime_lifecycle_complete,.-__au_runtime_lifecycle_complete
.global __au_runtime_lifecycle_phase
.hidden __au_runtime_lifecycle_phase
.type __au_runtime_lifecycle_phase,@function
__au_runtime_lifecycle_phase:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @lifecycle_phase@
    leave
    ret
.size __au_runtime_lifecycle_phase,.-__au_runtime_lifecycle_phase
.global __au_runtime_lifecycle_generation
.hidden __au_runtime_lifecycle_generation
.type __au_runtime_lifecycle_generation,@function
__au_runtime_lifecycle_generation:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @lifecycle_generation@
    leave
    ret
.size __au_runtime_lifecycle_generation,.-__au_runtime_lifecycle_generation
.global __au_runtime_lifecycle_finish
.hidden __au_runtime_lifecycle_finish
.type __au_runtime_lifecycle_finish,@function
__au_runtime_lifecycle_finish:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @kernel::finish@
    leave
    ret
.size __au_runtime_lifecycle_finish,.-__au_runtime_lifecycle_finish
.global __au_runtime_lifecycle_can_prepare
.hidden __au_runtime_lifecycle_can_prepare
.type __au_runtime_lifecycle_can_prepare,@function
__au_runtime_lifecycle_can_prepare:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @lifecycle_can_prepare@
    leave
    ret
.size __au_runtime_lifecycle_can_prepare,.-__au_runtime_lifecycle_can_prepare
.global __au_runtime_lifecycle_pending
.hidden __au_runtime_lifecycle_pending
.type __au_runtime_lifecycle_pending,@function
__au_runtime_lifecycle_pending:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @lifecycle_pending@
    leave
    ret
.size __au_runtime_lifecycle_pending,.-__au_runtime_lifecycle_pending

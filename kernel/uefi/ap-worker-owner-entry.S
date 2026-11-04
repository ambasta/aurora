# RETAINED_AP_WORKER_ABI: exact BSP-retained root and copied AP observations.
.text
.global __au_runtime_ap_worker_create
.hidden __au_runtime_ap_worker_create
.type __au_runtime_ap_worker_create,@function
__au_runtime_ap_worker_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_create@
    leave
    ret
.size __au_runtime_ap_worker_create,.-__au_runtime_ap_worker_create
.global __au_runtime_ap_worker_begin_start
.hidden __au_runtime_ap_worker_begin_start
.type __au_runtime_ap_worker_begin_start,@function
__au_runtime_ap_worker_begin_start:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_begin_start@
    leave
    ret
.size __au_runtime_ap_worker_begin_start,.-__au_runtime_ap_worker_begin_start
.global __au_runtime_ap_worker_startup_sent
.hidden __au_runtime_ap_worker_startup_sent
.type __au_runtime_ap_worker_startup_sent,@function
__au_runtime_ap_worker_startup_sent:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_startup_sent@
    leave
    ret
.size __au_runtime_ap_worker_startup_sent,.-__au_runtime_ap_worker_startup_sent
.global __au_runtime_ap_worker_ready
.hidden __au_runtime_ap_worker_ready
.type __au_runtime_ap_worker_ready,@function
__au_runtime_ap_worker_ready:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_ready@
    leave
    ret
.size __au_runtime_ap_worker_ready,.-__au_runtime_ap_worker_ready
.global __au_runtime_ap_worker_reserve
.hidden __au_runtime_ap_worker_reserve
.type __au_runtime_ap_worker_reserve,@function
__au_runtime_ap_worker_reserve:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_reserve@
    leave
    ret
.size __au_runtime_ap_worker_reserve,.-__au_runtime_ap_worker_reserve
.global __au_runtime_ap_worker_published
.hidden __au_runtime_ap_worker_published
.type __au_runtime_ap_worker_published,@function
__au_runtime_ap_worker_published:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_published@
    leave
    ret
.size __au_runtime_ap_worker_published,.-__au_runtime_ap_worker_published
.global __au_runtime_ap_worker_observe
.hidden __au_runtime_ap_worker_observe
.type __au_runtime_ap_worker_observe,@function
__au_runtime_ap_worker_observe:
    pushq %rbp
    movq %rsp,%rbp
    subq $64,%rsp
    movq %rdi,%r10
    movq 0(%rsi),%rax
    movq %rax,0(%rsp)
    movq 8(%rsi),%rax
    movq %rax,8(%rsp)
    movq 16(%rsi),%rax
    movq %rax,16(%rsp)
    movq 24(%rsi),%rax
    movq %rax,24(%rsp)
    movq 32(%rsi),%rax
    movq %rax,32(%rsp)
    movq %rdx,40(%rsp)
    movq %rcx,48(%rsp)
    movq %rsp,%r11
    call @ap_worker_owner_observe@
    leave
    ret
.size __au_runtime_ap_worker_observe,.-__au_runtime_ap_worker_observe
.global __au_runtime_ap_worker_acknowledged
.hidden __au_runtime_ap_worker_acknowledged
.type __au_runtime_ap_worker_acknowledged,@function
__au_runtime_ap_worker_acknowledged:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_acknowledged@
    leave
    ret
.size __au_runtime_ap_worker_acknowledged,.-__au_runtime_ap_worker_acknowledged
.global __au_runtime_ap_worker_fail
.hidden __au_runtime_ap_worker_fail
.type __au_runtime_ap_worker_fail,@function
__au_runtime_ap_worker_fail:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_fail@
    leave
    ret
.size __au_runtime_ap_worker_fail,.-__au_runtime_ap_worker_fail
.global __au_runtime_ap_worker_stage
.hidden __au_runtime_ap_worker_stage
.type __au_runtime_ap_worker_stage,@function
__au_runtime_ap_worker_stage:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_stage@
    leave
    ret
.size __au_runtime_ap_worker_stage,.-__au_runtime_ap_worker_stage
.global __au_runtime_ap_worker_sequence
.hidden __au_runtime_ap_worker_sequence
.type __au_runtime_ap_worker_sequence,@function
__au_runtime_ap_worker_sequence:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_sequence@
    leave
    ret
.size __au_runtime_ap_worker_sequence,.-__au_runtime_ap_worker_sequence
.global __au_runtime_ap_worker_used
.hidden __au_runtime_ap_worker_used
.type __au_runtime_ap_worker_used,@function
__au_runtime_ap_worker_used:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_used@
    leave
    ret
.size __au_runtime_ap_worker_used,.-__au_runtime_ap_worker_used
.global __au_runtime_ap_worker_remaining
.hidden __au_runtime_ap_worker_remaining
.type __au_runtime_ap_worker_remaining,@function
__au_runtime_ap_worker_remaining:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_remaining@
    leave
    ret
.size __au_runtime_ap_worker_remaining,.-__au_runtime_ap_worker_remaining
.global __au_runtime_ap_worker_jobs
.hidden __au_runtime_ap_worker_jobs
.type __au_runtime_ap_worker_jobs,@function
__au_runtime_ap_worker_jobs:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_jobs@
    leave
    ret
.size __au_runtime_ap_worker_jobs,.-__au_runtime_ap_worker_jobs
.global __au_runtime_ap_worker_result
.hidden __au_runtime_ap_worker_result
.type __au_runtime_ap_worker_result,@function
__au_runtime_ap_worker_result:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_result@
    leave
    ret
.size __au_runtime_ap_worker_result,.-__au_runtime_ap_worker_result
.global __au_runtime_ap_worker_incarnation
.hidden __au_runtime_ap_worker_incarnation
.type __au_runtime_ap_worker_incarnation,@function
__au_runtime_ap_worker_incarnation:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_incarnation@
    leave
    ret
.size __au_runtime_ap_worker_incarnation,.-__au_runtime_ap_worker_incarnation
.global __au_runtime_ap_worker_target
.hidden __au_runtime_ap_worker_target
.type __au_runtime_ap_worker_target,@function
__au_runtime_ap_worker_target:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_target@
    leave
    ret
.size __au_runtime_ap_worker_target,.-__au_runtime_ap_worker_target
.global __au_runtime_ap_worker_start
.hidden __au_runtime_ap_worker_start
.type __au_runtime_ap_worker_start,@function
__au_runtime_ap_worker_start:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_start@
    leave
    ret
.size __au_runtime_ap_worker_start,.-__au_runtime_ap_worker_start
.global __au_runtime_ap_worker_count
.hidden __au_runtime_ap_worker_count
.type __au_runtime_ap_worker_count,@function
__au_runtime_ap_worker_count:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_count@
    leave
    ret
.size __au_runtime_ap_worker_count,.-__au_runtime_ap_worker_count

.global __au_runtime_ap_worker_reserve_observation
.hidden __au_runtime_ap_worker_reserve_observation
.type __au_runtime_ap_worker_reserve_observation,@function
__au_runtime_ap_worker_reserve_observation:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @ap_worker_owner_reserve_observation@
    leave
    ret
.size __au_runtime_ap_worker_reserve_observation,.-__au_runtime_ap_worker_reserve_observation

.global __au_runtime_ap_worker_attempts
.hidden __au_runtime_ap_worker_attempts
.type __au_runtime_ap_worker_attempts,@function
__au_runtime_ap_worker_attempts:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_attempts@
    leave
    ret
.size __au_runtime_ap_worker_attempts,.-__au_runtime_ap_worker_attempts

.global __au_runtime_ap_worker_ticks
.hidden __au_runtime_ap_worker_ticks
.type __au_runtime_ap_worker_ticks,@function
__au_runtime_ap_worker_ticks:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_ticks@
    leave
    ret
.size __au_runtime_ap_worker_ticks,.-__au_runtime_ap_worker_ticks

.global __au_runtime_ap_worker_ordinal
.hidden __au_runtime_ap_worker_ordinal
.type __au_runtime_ap_worker_ordinal,@function
__au_runtime_ap_worker_ordinal:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @ap_worker_owner_ordinal@
    leave
    ret
.size __au_runtime_ap_worker_ordinal,.-__au_runtime_ap_worker_ordinal

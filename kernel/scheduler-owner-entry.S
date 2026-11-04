# RETAINED_SCHEDULER_ABI: initialized opaque plain root; no surviving loans.
.text
.global __au_runtime_scheduler_create
.hidden __au_runtime_scheduler_create
.type __au_runtime_scheduler_create,@function
__au_runtime_scheduler_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @scheduler_owner_create@
    leave
    ret
.size __au_runtime_scheduler_create,.-__au_runtime_scheduler_create
.global __au_runtime_scheduler_admit
.hidden __au_runtime_scheduler_admit
.type __au_runtime_scheduler_admit,@function
__au_runtime_scheduler_admit:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @scheduler_owner_admit@
    leave
    ret
.size __au_runtime_scheduler_admit,.-__au_runtime_scheduler_admit
.global __au_runtime_scheduler_select
.hidden __au_runtime_scheduler_select
.type __au_runtime_scheduler_select,@function
__au_runtime_scheduler_select:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @scheduler_owner_select@
    leave
    ret
.size __au_runtime_scheduler_select,.-__au_runtime_scheduler_select
.global __au_runtime_scheduler_observe_tick
.hidden __au_runtime_scheduler_observe_tick
.type __au_runtime_scheduler_observe_tick,@function
__au_runtime_scheduler_observe_tick:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @scheduler_owner_observe_tick@
    leave
    ret
.size __au_runtime_scheduler_observe_tick,.-__au_runtime_scheduler_observe_tick
.global __au_runtime_scheduler_observe_terminal
.hidden __au_runtime_scheduler_observe_terminal
.type __au_runtime_scheduler_observe_terminal,@function
__au_runtime_scheduler_observe_terminal:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    movq %r8,%rcx
    call @scheduler_owner_observe_terminal@
    leave
    ret
.size __au_runtime_scheduler_observe_terminal,.-__au_runtime_scheduler_observe_terminal
.global __au_runtime_scheduler_finish_restore
.hidden __au_runtime_scheduler_finish_restore
.type __au_runtime_scheduler_finish_restore,@function
__au_runtime_scheduler_finish_restore:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @scheduler_owner_finish_restore@
    leave
    ret
.size __au_runtime_scheduler_finish_restore,.-__au_runtime_scheduler_finish_restore
.global __au_runtime_scheduler_ack_retired
.hidden __au_runtime_scheduler_ack_retired
.type __au_runtime_scheduler_ack_retired,@function
__au_runtime_scheduler_ack_retired:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @scheduler_owner_ack_retired@
    leave
    ret
.size __au_runtime_scheduler_ack_retired,.-__au_runtime_scheduler_ack_retired
.global __au_runtime_scheduler_active_slot
.hidden __au_runtime_scheduler_active_slot
.type __au_runtime_scheduler_active_slot,@function
__au_runtime_scheduler_active_slot:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @scheduler_owner_active_slot@
    leave
    ret
.size __au_runtime_scheduler_active_slot,.-__au_runtime_scheduler_active_slot
.global __au_runtime_scheduler_active_stamp
.hidden __au_runtime_scheduler_active_stamp
.type __au_runtime_scheduler_active_stamp,@function
__au_runtime_scheduler_active_stamp:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @scheduler_owner_active_stamp@
    leave
    ret
.size __au_runtime_scheduler_active_stamp,.-__au_runtime_scheduler_active_stamp
.global __au_runtime_scheduler_sequence
.hidden __au_runtime_scheduler_sequence
.type __au_runtime_scheduler_sequence,@function
__au_runtime_scheduler_sequence:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @scheduler_owner_sequence@
    leave
    ret
.size __au_runtime_scheduler_sequence,.-__au_runtime_scheduler_sequence
.global __au_runtime_scheduler_phase
.hidden __au_runtime_scheduler_phase
.type __au_runtime_scheduler_phase,@function
__au_runtime_scheduler_phase:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @scheduler_owner_phase@
    leave
    ret
.size __au_runtime_scheduler_phase,.-__au_runtime_scheduler_phase
.global __au_runtime_scheduler_used
.hidden __au_runtime_scheduler_used
.type __au_runtime_scheduler_used,@function
__au_runtime_scheduler_used:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @scheduler_owner_used@
    leave
    ret
.size __au_runtime_scheduler_used,.-__au_runtime_scheduler_used
.global __au_runtime_scheduler_remaining
.hidden __au_runtime_scheduler_remaining
.type __au_runtime_scheduler_remaining,@function
__au_runtime_scheduler_remaining:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @scheduler_owner_remaining@
    leave
    ret
.size __au_runtime_scheduler_remaining,.-__au_runtime_scheduler_remaining
.global __au_runtime_scheduler_reason
.hidden __au_runtime_scheduler_reason
.type __au_runtime_scheduler_reason,@function
__au_runtime_scheduler_reason:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @scheduler_owner_reason@
    leave
    ret
.size __au_runtime_scheduler_reason,.-__au_runtime_scheduler_reason
.global __au_runtime_scheduler_complete
.hidden __au_runtime_scheduler_complete
.type __au_runtime_scheduler_complete,@function
__au_runtime_scheduler_complete:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @scheduler_owner_complete@
    leave
    ret
.size __au_runtime_scheduler_complete,.-__au_runtime_scheduler_complete

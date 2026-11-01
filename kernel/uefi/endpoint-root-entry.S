# RETAINED_ENDPOINT_ABI: exact opaque root and copied observation; no surviving loans.
.text
.global __au_runtime_endpoint_create
.hidden __au_runtime_endpoint_create
.type __au_runtime_endpoint_create,@function
__au_runtime_endpoint_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    subq $16,%rsp
    movq %rsi,0(%rsp)
    movq %rsp,%r11
    call @process_endpoint_create@
    leave
    ret
.size __au_runtime_endpoint_create,.-__au_runtime_endpoint_create
.global __au_runtime_endpoint_bind
.hidden __au_runtime_endpoint_bind
.type __au_runtime_endpoint_bind,@function
__au_runtime_endpoint_bind:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_bind@
    leave
    ret
.size __au_runtime_endpoint_bind,.-__au_runtime_endpoint_bind
.global __au_runtime_endpoint_reset
.hidden __au_runtime_endpoint_reset
.type __au_runtime_endpoint_reset,@function
__au_runtime_endpoint_reset:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_endpoint_reset@
    leave
    ret
.size __au_runtime_endpoint_reset,.-__au_runtime_endpoint_reset
.global __au_runtime_endpoint_observe
.hidden __au_runtime_endpoint_observe
.type __au_runtime_endpoint_observe,@function
__au_runtime_endpoint_observe:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @process_endpoint_observe@
    leave
    ret
.size __au_runtime_endpoint_observe,.-__au_runtime_endpoint_observe
.global __au_runtime_endpoint_accept_exchange
.hidden __au_runtime_endpoint_accept_exchange
.type __au_runtime_endpoint_accept_exchange,@function
__au_runtime_endpoint_accept_exchange:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @process_endpoint_accept_exchange@
    leave
    ret
.size __au_runtime_endpoint_accept_exchange,.-__au_runtime_endpoint_accept_exchange
.global __au_runtime_endpoint_stage_client
.hidden __au_runtime_endpoint_stage_client
.type __au_runtime_endpoint_stage_client,@function
__au_runtime_endpoint_stage_client:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_stage_client@
    leave
    ret
.size __au_runtime_endpoint_stage_client,.-__au_runtime_endpoint_stage_client
.global __au_runtime_endpoint_begin
.hidden __au_runtime_endpoint_begin
.type __au_runtime_endpoint_begin,@function
__au_runtime_endpoint_begin:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_begin@
    leave
    ret
.size __au_runtime_endpoint_begin,.-__au_runtime_endpoint_begin
.global __au_runtime_endpoint_client_step
.hidden __au_runtime_endpoint_client_step
.type __au_runtime_endpoint_client_step,@function
__au_runtime_endpoint_client_step:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_client_step@
    leave
    ret
.size __au_runtime_endpoint_client_step,.-__au_runtime_endpoint_client_step
.global __au_runtime_endpoint_step
.hidden __au_runtime_endpoint_step
.type __au_runtime_endpoint_step,@function
__au_runtime_endpoint_step:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_endpoint_step@
    leave
    ret
.size __au_runtime_endpoint_step,.-__au_runtime_endpoint_step
.global __au_runtime_endpoint_observe_step
.hidden __au_runtime_endpoint_observe_step
.type __au_runtime_endpoint_observe_step,@function
__au_runtime_endpoint_observe_step:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movzbq %sil,%rdi
    call @process_endpoint_observe_step@
    leave
    ret
.size __au_runtime_endpoint_observe_step,.-__au_runtime_endpoint_observe_step
.global __au_runtime_endpoint_completion
.hidden __au_runtime_endpoint_completion
.type __au_runtime_endpoint_completion,@function
__au_runtime_endpoint_completion:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_endpoint_completion@
    leave
    ret
.size __au_runtime_endpoint_completion,.-__au_runtime_endpoint_completion
.global __au_runtime_endpoint_delivered
.hidden __au_runtime_endpoint_delivered
.type __au_runtime_endpoint_delivered,@function
__au_runtime_endpoint_delivered:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @process_endpoint_delivered@
    leave
    ret
.size __au_runtime_endpoint_delivered,.-__au_runtime_endpoint_delivered
.global __au_runtime_endpoint_consume_control
.hidden __au_runtime_endpoint_consume_control
.type __au_runtime_endpoint_consume_control,@function
__au_runtime_endpoint_consume_control:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_consume_control@
    leave
    ret
.size __au_runtime_endpoint_consume_control,.-__au_runtime_endpoint_consume_control
.global __au_runtime_endpoint_consume_client
.hidden __au_runtime_endpoint_consume_client
.type __au_runtime_endpoint_consume_client,@function
__au_runtime_endpoint_consume_client:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movzbq %dl,%rsi
    movzbq %cl,%rdx
    call @process_endpoint_consume_client@
    leave
    ret
.size __au_runtime_endpoint_consume_client,.-__au_runtime_endpoint_consume_client
.global __au_runtime_endpoint_complete_client
.hidden __au_runtime_endpoint_complete_client
.type __au_runtime_endpoint_complete_client,@function
__au_runtime_endpoint_complete_client:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_complete_client@
    leave
    ret
.size __au_runtime_endpoint_complete_client,.-__au_runtime_endpoint_complete_client
.global __au_runtime_endpoint_cancel
.hidden __au_runtime_endpoint_cancel
.type __au_runtime_endpoint_cancel,@function
__au_runtime_endpoint_cancel:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movzbq %dl,%rsi
    call @process_endpoint_cancel@
    leave
    ret
.size __au_runtime_endpoint_cancel,.-__au_runtime_endpoint_cancel
.global __au_runtime_endpoint_finish_client
.hidden __au_runtime_endpoint_finish_client
.type __au_runtime_endpoint_finish_client,@function
__au_runtime_endpoint_finish_client:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_finish_client@
    leave
    ret
.size __au_runtime_endpoint_finish_client,.-__au_runtime_endpoint_finish_client
.global __au_runtime_endpoint_invalidate
.hidden __au_runtime_endpoint_invalidate
.type __au_runtime_endpoint_invalidate,@function
__au_runtime_endpoint_invalidate:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_endpoint_invalidate@
    leave
    ret
.size __au_runtime_endpoint_invalidate,.-__au_runtime_endpoint_invalidate
.global __au_runtime_endpoint_initial_step
.hidden __au_runtime_endpoint_initial_step
.type __au_runtime_endpoint_initial_step,@function
__au_runtime_endpoint_initial_step:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_endpoint_initial_step@
    leave
    ret
.size __au_runtime_endpoint_initial_step,.-__au_runtime_endpoint_initial_step

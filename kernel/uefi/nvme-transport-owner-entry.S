# RETAINED_NVME_TRANSPORT_ABI: exact boot-retained root and copied completion observation.
.text
.global __au_runtime_nvme_transport_create
.hidden __au_runtime_nvme_transport_create
.type __au_runtime_nvme_transport_create,@function
__au_runtime_nvme_transport_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @nvme_transport_owner_create@
    leave
    ret
.size __au_runtime_nvme_transport_create,.-__au_runtime_nvme_transport_create
.global __au_runtime_nvme_transport_reserve
.hidden __au_runtime_nvme_transport_reserve
.type __au_runtime_nvme_transport_reserve,@function
__au_runtime_nvme_transport_reserve:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @nvme_transport_owner_reserve@
    leave
    ret
.size __au_runtime_nvme_transport_reserve,.-__au_runtime_nvme_transport_reserve
.global __au_runtime_nvme_transport_published
.hidden __au_runtime_nvme_transport_published
.type __au_runtime_nvme_transport_published,@function
__au_runtime_nvme_transport_published:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @nvme_transport_owner_published@
    leave
    ret
.size __au_runtime_nvme_transport_published,.-__au_runtime_nvme_transport_published
.global __au_runtime_nvme_transport_accept_completion
.hidden __au_runtime_nvme_transport_accept_completion
.type __au_runtime_nvme_transport_accept_completion,@function
__au_runtime_nvme_transport_accept_completion:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @nvme_transport_owner_accept_completion@
    leave
    ret
.size __au_runtime_nvme_transport_accept_completion,.-__au_runtime_nvme_transport_accept_completion
.global __au_runtime_nvme_transport_acknowledged
.hidden __au_runtime_nvme_transport_acknowledged
.type __au_runtime_nvme_transport_acknowledged,@function
__au_runtime_nvme_transport_acknowledged:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @nvme_transport_owner_acknowledged@
    leave
    ret
.size __au_runtime_nvme_transport_acknowledged,.-__au_runtime_nvme_transport_acknowledged
.global __au_runtime_nvme_transport_poison
.hidden __au_runtime_nvme_transport_poison
.type __au_runtime_nvme_transport_poison,@function
__au_runtime_nvme_transport_poison:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @nvme_transport_owner_poison@
    leave
    ret
.size __au_runtime_nvme_transport_poison,.-__au_runtime_nvme_transport_poison
.global __au_runtime_nvme_transport_available
.hidden __au_runtime_nvme_transport_available
.type __au_runtime_nvme_transport_available,@function
__au_runtime_nvme_transport_available:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_available@
    leave
    ret
.size __au_runtime_nvme_transport_available,.-__au_runtime_nvme_transport_available
.global __au_runtime_nvme_transport_poisoned
.hidden __au_runtime_nvme_transport_poisoned
.type __au_runtime_nvme_transport_poisoned,@function
__au_runtime_nvme_transport_poisoned:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @nvme_transport_owner_poisoned@
    leave
    ret
.size __au_runtime_nvme_transport_poisoned,.-__au_runtime_nvme_transport_poisoned
.global __au_runtime_nvme_transport_stage
.hidden __au_runtime_nvme_transport_stage
.type __au_runtime_nvme_transport_stage,@function
__au_runtime_nvme_transport_stage:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @nvme_transport_owner_stage@
    leave
    ret
.size __au_runtime_nvme_transport_stage,.-__au_runtime_nvme_transport_stage
.global __au_runtime_nvme_transport_active_qid
.hidden __au_runtime_nvme_transport_active_qid
.type __au_runtime_nvme_transport_active_qid,@function
__au_runtime_nvme_transport_active_qid:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @nvme_transport_owner_active_qid@
    leave
    ret
.size __au_runtime_nvme_transport_active_qid,.-__au_runtime_nvme_transport_active_qid
.global __au_runtime_nvme_transport_active_cid
.hidden __au_runtime_nvme_transport_active_cid
.type __au_runtime_nvme_transport_active_cid,@function
__au_runtime_nvme_transport_active_cid:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @nvme_transport_owner_active_cid@
    leave
    ret
.size __au_runtime_nvme_transport_active_cid,.-__au_runtime_nvme_transport_active_cid
.global __au_runtime_nvme_transport_remaining
.hidden __au_runtime_nvme_transport_remaining
.type __au_runtime_nvme_transport_remaining,@function
__au_runtime_nvme_transport_remaining:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_remaining@
    leave
    ret
.size __au_runtime_nvme_transport_remaining,.-__au_runtime_nvme_transport_remaining
.global __au_runtime_nvme_transport_next_cid
.hidden __au_runtime_nvme_transport_next_cid
.type __au_runtime_nvme_transport_next_cid,@function
__au_runtime_nvme_transport_next_cid:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_next_cid@
    leave
    ret
.size __au_runtime_nvme_transport_next_cid,.-__au_runtime_nvme_transport_next_cid
.global __au_runtime_nvme_transport_tail
.hidden __au_runtime_nvme_transport_tail
.type __au_runtime_nvme_transport_tail,@function
__au_runtime_nvme_transport_tail:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_tail@
    leave
    ret
.size __au_runtime_nvme_transport_tail,.-__au_runtime_nvme_transport_tail
.global __au_runtime_nvme_transport_head
.hidden __au_runtime_nvme_transport_head
.type __au_runtime_nvme_transport_head,@function
__au_runtime_nvme_transport_head:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_head@
    leave
    ret
.size __au_runtime_nvme_transport_head,.-__au_runtime_nvme_transport_head
.global __au_runtime_nvme_transport_phase
.hidden __au_runtime_nvme_transport_phase
.type __au_runtime_nvme_transport_phase,@function
__au_runtime_nvme_transport_phase:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_phase@
    leave
    ret
.size __au_runtime_nvme_transport_phase,.-__au_runtime_nvme_transport_phase
.global __au_runtime_nvme_transport_status
.hidden __au_runtime_nvme_transport_status
.type __au_runtime_nvme_transport_status,@function
__au_runtime_nvme_transport_status:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @nvme_transport_owner_status@
    leave
    ret
.size __au_runtime_nvme_transport_status,.-__au_runtime_nvme_transport_status

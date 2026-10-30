# RETAINED_SERVICE_ABI: initialized opaque plain root; no surviving loans.
.text
.global __au_runtime_service_create
.hidden __au_runtime_service_create
.type __au_runtime_service_create,@function
__au_runtime_service_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_create@
    leave
    ret
.size __au_runtime_service_create,.-__au_runtime_service_create
.global __au_runtime_service_open_operation
.hidden __au_runtime_service_open_operation
.type __au_runtime_service_open_operation,@function
__au_runtime_service_open_operation:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_open_operation@
    leave
    ret
.size __au_runtime_service_open_operation,.-__au_runtime_service_open_operation
.global __au_runtime_service_close_operation
.hidden __au_runtime_service_close_operation
.type __au_runtime_service_close_operation,@function
__au_runtime_service_close_operation:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_close_operation@
    leave
    ret
.size __au_runtime_service_close_operation,.-__au_runtime_service_close_operation
.global __au_runtime_service_admit
.hidden __au_runtime_service_admit
.type __au_runtime_service_admit,@function
__au_runtime_service_admit:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movzbq %dl,%rsi
    call @process_service_admit@
    leave
    ret
.size __au_runtime_service_admit,.-__au_runtime_service_admit
.global __au_runtime_service_mark_ready
.hidden __au_runtime_service_mark_ready
.type __au_runtime_service_mark_ready,@function
__au_runtime_service_mark_ready:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movzbq %dl,%rsi
    call @process_service_mark_ready@
    leave
    ret
.size __au_runtime_service_mark_ready,.-__au_runtime_service_mark_ready
.global __au_runtime_service_begin_shutdown
.hidden __au_runtime_service_begin_shutdown
.type __au_runtime_service_begin_shutdown,@function
__au_runtime_service_begin_shutdown:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_service_begin_shutdown@
    leave
    ret
.size __au_runtime_service_begin_shutdown,.-__au_runtime_service_begin_shutdown
.global __au_runtime_service_lose
.hidden __au_runtime_service_lose
.type __au_runtime_service_lose,@function
__au_runtime_service_lose:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @process_service_lose@
    leave
    ret
.size __au_runtime_service_lose,.-__au_runtime_service_lose
.global __au_runtime_service_normal_exit
.hidden __au_runtime_service_normal_exit
.type __au_runtime_service_normal_exit,@function
__au_runtime_service_normal_exit:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_service_normal_exit@
    leave
    ret
.size __au_runtime_service_normal_exit,.-__au_runtime_service_normal_exit
.global __au_runtime_service_cleaned
.hidden __au_runtime_service_cleaned
.type __au_runtime_service_cleaned,@function
__au_runtime_service_cleaned:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_service_cleaned@
    leave
    ret
.size __au_runtime_service_cleaned,.-__au_runtime_service_cleaned
.global __au_runtime_service_generation
.hidden __au_runtime_service_generation
.type __au_runtime_service_generation,@function
__au_runtime_service_generation:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_generation@
    leave
    ret
.size __au_runtime_service_generation,.-__au_runtime_service_generation
.global __au_runtime_service_phase
.hidden __au_runtime_service_phase
.type __au_runtime_service_phase,@function
__au_runtime_service_phase:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_phase@
    leave
    ret
.size __au_runtime_service_phase,.-__au_runtime_service_phase
.global __au_runtime_service_disk_ready
.hidden __au_runtime_service_disk_ready
.type __au_runtime_service_disk_ready,@function
__au_runtime_service_disk_ready:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_service_disk_ready@
    leave
    ret
.size __au_runtime_service_disk_ready,.-__au_runtime_service_disk_ready
.global __au_runtime_service_reason
.hidden __au_runtime_service_reason
.type __au_runtime_service_reason,@function
__au_runtime_service_reason:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_reason@
    leave
    ret
.size __au_runtime_service_reason,.-__au_runtime_service_reason
.global __au_runtime_service_detail
.hidden __au_runtime_service_detail
.type __au_runtime_service_detail,@function
__au_runtime_service_detail:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_detail@
    leave
    ret
.size __au_runtime_service_detail,.-__au_runtime_service_detail

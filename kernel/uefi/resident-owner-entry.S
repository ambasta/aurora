# RESIDENT_OWNER_ABI: fresh complete constructor; stable owning root; consuming terminal receiver.
.text
.global __au_runtime_resident_construct
.hidden __au_runtime_resident_construct
.type __au_runtime_resident_construct,@function
__au_runtime_resident_construct:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @kernel::ServiceOwner@
    leave
    ret
.size __au_runtime_resident_construct,.-__au_runtime_resident_construct
.global __au_runtime_process_resident_prepare
.hidden __au_runtime_process_resident_prepare
.type __au_runtime_process_resident_prepare,@function
__au_runtime_process_resident_prepare:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_resident_prepare@
    leave
    ret
.size __au_runtime_process_resident_prepare,.-__au_runtime_process_resident_prepare
.global __au_runtime_process_resident_run
.hidden __au_runtime_process_resident_run
.type __au_runtime_process_resident_run,@function
__au_runtime_process_resident_run:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @process_resident_run@
    leave
    ret
.size __au_runtime_process_resident_run,.-__au_runtime_process_resident_run
.global __au_runtime_process_resident_console
.hidden __au_runtime_process_resident_console
.type __au_runtime_process_resident_console,@function
__au_runtime_process_resident_console:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_resident_console@
    leave
    ret
.size __au_runtime_process_resident_console,.-__au_runtime_process_resident_console
.global __au_runtime_process_resident_reject
.hidden __au_runtime_process_resident_reject
.type __au_runtime_process_resident_reject,@function
__au_runtime_process_resident_reject:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_resident_reject@
    leave
    ret
.size __au_runtime_process_resident_reject,.-__au_runtime_process_resident_reject
.global __au_runtime_process_resident_finish
.hidden __au_runtime_process_resident_finish
.type __au_runtime_process_resident_finish,@function
__au_runtime_process_resident_finish:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @kernel::finish@
    leave
    ret
.size __au_runtime_process_resident_finish,.-__au_runtime_process_resident_finish

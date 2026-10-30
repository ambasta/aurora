# EXECUTION_CANCEL_TEST_ABI: test-only cancellation choreography.
.text
.global __au_runtime_process_cancel_command
.hidden __au_runtime_process_cancel_command
.type __au_runtime_process_cancel_command,@function
__au_runtime_process_cancel_command:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @process_cancel_command@
    leave
    ret
.size __au_runtime_process_cancel_command,.-__au_runtime_process_cancel_command

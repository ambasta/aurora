# One private production command entry. Reports carry facts, not authority.
# EXECUTION_POLICY_ABI: a compiler-typed sealed loan and complete copied result.
.text
.global __au_runtime_process_execute_command
.hidden __au_runtime_process_execute_command
.type __au_runtime_process_execute_command,@function
__au_runtime_process_execute_command:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @process_execute_command@
    leave
    ret
.size __au_runtime_process_execute_command,.-__au_runtime_process_execute_command

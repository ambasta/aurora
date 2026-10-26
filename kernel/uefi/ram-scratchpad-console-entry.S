# Private supervisor-only Console bridges. Native callers own disjoint complete
# records; these adapters grant no capability and retain no transport bytes.
.text
.global __au_runtime_scratchpad_input
.hidden __au_runtime_scratchpad_input
.type __au_runtime_scratchpad_input,@function
__au_runtime_scratchpad_input:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @read_scratchpad_input@
    leave
    ret
.size __au_runtime_scratchpad_input,.-__au_runtime_scratchpad_input
.global __au_runtime_scratchpad_response
.hidden __au_runtime_scratchpad_response
.type __au_runtime_scratchpad_response,@function
__au_runtime_scratchpad_response:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @present_scratchpad_response@
    leave
    ret
.size __au_runtime_scratchpad_response,.-__au_runtime_scratchpad_response

.section .note.GNU-stack,"",@progbits

# NAMESPACE_CONSOLE_ABI: private supervisor-only Console bridges. Native callers own disjoint complete
# records; these adapters grant no capability and retain no transport bytes.
.text
.global __au_runtime_namespace_input
.hidden __au_runtime_namespace_input
.type __au_runtime_namespace_input,@function
__au_runtime_namespace_input:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @read_namespace_input@
    leave
    ret
.size __au_runtime_namespace_input,.-__au_runtime_namespace_input
.global __au_runtime_namespace_response
.hidden __au_runtime_namespace_response
.type __au_runtime_namespace_response,@function
__au_runtime_namespace_response:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @present_namespace_response@
    leave
    ret
.size __au_runtime_namespace_response,.-__au_runtime_namespace_response

.section .note.GNU-stack,"",@progbits

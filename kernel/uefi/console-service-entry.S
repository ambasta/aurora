# Host grants one checked synchronous service invocation. Assemble with the
# compiler-private language graph, never expose the source service entry.
.text
.global __au_runtime_console_entry
.hidden __au_runtime_console_entry
.type __au_runtime_console_entry,@function
__au_runtime_console_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call @console_service@
    leave
    ret
.size __au_runtime_console_entry,.-__au_runtime_console_entry

.global __au_runtime_console_value
.hidden __au_runtime_console_value
.type __au_runtime_console_value,@function
__au_runtime_console_value:
    jmp @aurora_kernel_value@
.size __au_runtime_console_value,.-__au_runtime_console_value
# The compiler emits the sole GNU-stack note for this combined object.

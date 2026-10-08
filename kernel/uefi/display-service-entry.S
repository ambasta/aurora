# Host grants one synchronous sealed display invocation. No source FFI.
.text
.global __au_runtime_display_entry
.hidden __au_runtime_display_entry
.type __au_runtime_display_entry,@function
__au_runtime_display_entry:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call __au_v_m1_22kernel_display_service_n0__d15display_service
    leave
    ret
.size __au_runtime_display_entry,.-__au_runtime_display_entry
.global __au_runtime_display_value
.hidden __au_runtime_display_value
.type __au_runtime_display_value,@function
__au_runtime_display_value:
    jmp aurora_kernel_value
.size __au_runtime_display_value,.-__au_runtime_display_value
# The compiler contributes the sole GNU-stack note to the combined object.

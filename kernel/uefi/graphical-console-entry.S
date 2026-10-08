# UNQUALIFIED bridge: no production caller until dual-grant admission is complete.
# Record is exactly six qwords; this bridge itself does not authenticate it.
.text
.global __au_runtime_graphical_entry
.hidden __au_runtime_graphical_entry
.type __au_runtime_graphical_entry,@function
__au_runtime_graphical_entry:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call __au_v_m1_24kernel_graphical_console_n0__d17graphical_console
    leave
    ret
.size __au_runtime_graphical_entry,.-__au_runtime_graphical_entry
# The copied bootstrap self-test remains local in a sealed service graph.
.global __au_runtime_graphical_value
.hidden __au_runtime_graphical_value
.type __au_runtime_graphical_value,@function
__au_runtime_graphical_value:
    jmp aurora_kernel_value
.size __au_runtime_graphical_value,.-__au_runtime_graphical_value
# Assemble together with generated source for its single GNU-stack note.

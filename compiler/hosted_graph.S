# Trusted register-only graph boundary. Aurora constructs and consumes owners.
# run receives an ordered {mutable Workspace*, const Input*} tuple, never a copy.
.text
.macro graph_entry operation
.globl aurora_hosted_graph_\operation
.hidden aurora_hosted_graph_\operation
.type aurora_hosted_graph_\operation, @function
aurora_hosted_graph_\operation:
.endm
.macro graph_return operation, target
    jmp \target
.size aurora_hosted_graph_\operation, .-aurora_hosted_graph_\operation
.endm

graph_entry create_input
    movq %rdi, %r11
    movq %rsi, %r10
graph_return create_input, __aurora_frontend_graph_create_input

graph_entry create_workspace
    movq %rdi, %r11
    movq %rsi, %r10
graph_return create_workspace, __aurora_frontend_graph_create_workspace

graph_entry release_input
    movq %rdi, %r11
graph_return release_input, __aurora_frontend_graph_release_input

graph_entry release_workspace
    movq %rdi, %r11
graph_return release_workspace, __aurora_frontend_graph_release_workspace

graph_entry set_function
    movq %rdi, %r10
    movq %rsi, %r11
    movq __aurora_parameter_graph_set_function_0(%r11), %rdi
graph_return set_function, __aurora_frontend_graph_set_function

graph_entry set_edge
    movq %rdi, %r10
    movq %rsi, %r11
    movq __aurora_parameter_graph_set_edge_0(%r11), %rdi
    movq __aurora_parameter_graph_set_edge_1(%r11), %rsi
graph_return set_edge, __aurora_frontend_graph_set_edge

graph_entry run
    movq %rdi, %r10
graph_return run, __aurora_frontend_graph_run

graph_entry retained
    movq %rdi, %r10
    movq %rsi, %rdi
graph_return retained, __aurora_frontend_graph_retained

# The generated assembly in this same unit owns .note.GNU-stack.

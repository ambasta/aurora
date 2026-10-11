# Private copied-value bridges, assembled with their generated Aurora graph.
# The caller owns complete disjoint input/result records; no authority is copied.
.text
# Generated supervisor symbols are local by default. Preserve exactly the
# established scalar policy ABI; imported library helpers are not native entries.
.global aurora_kernel_value
.global aurora_kernel_budget_tick
.global aurora_kernel_round_robin_next
.global aurora_kernel_ipc_transition
.global aurora_kernel_client_disposal
.global aurora_kernel_terminal_event
.global aurora_console_byte
.global aurora_console_command
.global __au_v_m2_6kernel7console_n1_6kernel_d12console_byte
.global __au_v_m2_6kernel7console_n1_6kernel_d15console_command
.global __au_v_m2_6kernel14terminal_event_n1_6kernel_d14terminal_event
.global __au_runtime_note_update
.hidden __au_runtime_note_update
.type __au_runtime_note_update,@function
__au_runtime_note_update:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call __au_v_m1_22kernel_program_console_n0__d11update_note
    leave
    ret
.size __au_runtime_note_update,.-__au_runtime_note_update
.global __au_runtime_note_project
.hidden __au_runtime_note_project
.type __au_runtime_note_project,@function
__au_runtime_note_project:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call __au_v_m1_22kernel_program_console_n0__d12project_note
    leave
    ret
.size __au_runtime_note_project,.-__au_runtime_note_project
.global __au_runtime_files_update
.hidden __au_runtime_files_update
.type __au_runtime_files_update,@function
__au_runtime_files_update:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call __au_v_m1_22kernel_program_console_n0__d12update_files
    leave
    ret
.size __au_runtime_files_update,.-__au_runtime_files_update
.global __au_runtime_files_replace
.hidden __au_runtime_files_replace
.type __au_runtime_files_replace,@function
__au_runtime_files_replace:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call __au_v_m1_22kernel_program_console_n0__d13replace_files
    leave
    ret
.size __au_runtime_files_replace,.-__au_runtime_files_replace

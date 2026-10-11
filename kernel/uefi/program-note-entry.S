# Private copied-value bridges, assembled with their generated Aurora graph.
# The caller owns complete disjoint input/result records; no authority is copied.
.text
.global __au_runtime_note_update
.hidden __au_runtime_note_update
.type __au_runtime_note_update,@function
__au_runtime_note_update:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @update_note@
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
    call @project_note@
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
    call @update_files@
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
    call @replace_files@
    leave
    ret
.size __au_runtime_files_replace,.-__au_runtime_files_replace

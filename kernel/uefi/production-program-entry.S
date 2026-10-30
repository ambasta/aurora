# Production console bridges: copied input/response/session and worker stream only.
# Named-file/note parsing and persistent backing live in the external Store.
# The caller owns complete disjoint input/result records. Only the input reader
# and response presenter borrow an existing Console grant. Copied records and
# scalar results carry no authority.
.text
# PROGRAM_SESSION_ABI: retained copied session and bounded completion facts.
.global __au_runtime_program_session
.hidden __au_runtime_program_session
.type __au_runtime_program_session,@function
__au_runtime_program_session:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @update_program_session@
    leave
    ret
.size __au_runtime_program_session,.-__au_runtime_program_session
.global __au_runtime_program_input
.hidden __au_runtime_program_input
.type __au_runtime_program_input,@function
__au_runtime_program_input:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @read_program_input@
    leave
    ret
.size __au_runtime_program_input,.-__au_runtime_program_input
.global __au_runtime_program_response
.hidden __au_runtime_program_response
.type __au_runtime_program_response,@function
__au_runtime_program_response:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @present_program_response@
    leave
    ret
.size __au_runtime_program_response,.-__au_runtime_program_response
.global __au_runtime_stream_update
.hidden __au_runtime_stream_update
.type __au_runtime_stream_update,@function
__au_runtime_stream_update:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @update_stream@
    leave
    ret
.size __au_runtime_stream_update,.-__au_runtime_stream_update

.section .note.GNU-stack,"",@progbits

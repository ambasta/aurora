# PROCESS_FILES_ABI: copied native policy reference records, test-only.
.text
.macro process_entry name, target
.global \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call \target
    leave
    ret
.size \name,.-\name
.endm
.macro process_result_entry name, target
.global \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call \target
    leave
    ret
.size \name,.-\name
.endm
process_result_entry __au_runtime_process_file_open, @process_file_open@
process_result_entry __au_runtime_process_file_create, @process_file_create@
process_result_entry __au_runtime_process_file_read, @process_file_read@
process_result_entry __au_runtime_process_file_close, @process_file_close@
process_result_entry __au_runtime_process_file_write, @process_file_write@
process_result_entry __au_runtime_process_file_commit, @process_file_commit@
process_result_entry __au_runtime_process_file_discard, @process_file_discard@
process_entry __au_runtime_process_directory_prefix, @process_directory_prefix@

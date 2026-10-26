# PROGRAM_APPEND_CLIENT_ABI: compile and execute the exact private caller shape.
.text
.global append_test_client
.type append_test_client,@function
append_test_client:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    movq %rsi,%r10
    call @append_candidate@
    leave
    ret
.size append_test_client,.-append_test_client
.global note_test_client
.type note_test_client,@function
note_test_client:
    jmp @aurora_user_main@
.size note_test_client,.-note_test_client

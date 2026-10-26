# PROGRAM_APPEND_SERVICE_ABI: execute the exact private Serve/copy signature.
.text
.global append_test_service
.type append_test_service,@function
append_test_service:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @append_producer@
    leave
    ret
.size append_test_service,.-append_test_service
.global note_test_service
.type note_test_service,@function
note_test_service:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @aurora_user_main@
    leave
    ret
.size note_test_service,.-note_test_service

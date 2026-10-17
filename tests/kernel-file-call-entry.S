# Host-only adapter for the actual copied file-read service.
.text
.global file_call_test_service
.type file_call_test_service,@function
file_call_test_service:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @aurora_user_main@
    leave
    ret
.size file_call_test_service,.-file_call_test_service

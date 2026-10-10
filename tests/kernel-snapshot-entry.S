# Host fixture for the exact compiler-private aggregate input. The separately
# compiled client remains a scalar root; no R11 address enters Aurora source.
.text
.global snapshot_test_service
.type snapshot_test_service,@function
snapshot_test_service:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call __au_v_m1_16snapshot_service_n0__d16aurora_user_main
    leave
    ret
.size snapshot_test_service,.-snapshot_test_service

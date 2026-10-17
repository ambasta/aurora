.macro host_entry name
# Host fixture for the exact compiler-private aggregate input. The separately
# compiled client remains a scalar root; no R11 address enters Aurora source.
.text
.global \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call __au_v_m1_16snapshot_service_n0__d16aurora_user_main
    leave
    ret
.size \name,.-\name

.endm
.ifdef CHECKSUM_SERVICE
host_entry snapshot_test_checksum
.else
host_entry snapshot_test_service
.endif

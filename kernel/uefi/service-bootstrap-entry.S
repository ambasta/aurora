# SERVICE_BOOTSTRAP_ABI: sealed issuer loan; closed scalar readiness result.
.text
.global __au_runtime_process_bootstrap_service
.hidden __au_runtime_process_bootstrap_service
.type __au_runtime_process_bootstrap_service,@function
__au_runtime_process_bootstrap_service:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @process_bootstrap_service@
    leave
    ret
.size __au_runtime_process_bootstrap_service,.-__au_runtime_process_bootstrap_service

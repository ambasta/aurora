# SERVICE_SATURATION_TEST_ABI: test-only factory, never in a kernel image.
.text
.global __au_runtime_service_saturation_create
.hidden __au_runtime_service_saturation_create
.type __au_runtime_service_saturation_create,@function
__au_runtime_service_saturation_create:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_service_saturation_create@
    leave
    ret
.size __au_runtime_service_saturation_create,.-__au_runtime_service_saturation_create

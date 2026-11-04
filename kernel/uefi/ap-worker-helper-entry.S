# AP_WORKER_HELPER_ABI: closed scalar leaf, no root or imported services.
.text
.global __au_runtime_ap_worker_sum_squares
.hidden __au_runtime_ap_worker_sum_squares
.type __au_runtime_ap_worker_sum_squares,@function
__au_runtime_ap_worker_sum_squares:
    pushq %rbp
    movq %rsp,%rbp
    call @ap_worker_sum_squares@
    leave
    ret
.size __au_runtime_ap_worker_sum_squares,.-__au_runtime_ap_worker_sum_squares

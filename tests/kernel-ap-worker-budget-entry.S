# AP_WORKER_BUDGET_TEST_ABI: compiled policy boundary exercise, test-only.
.text
.global __au_test_ap_worker_budget_case
.hidden __au_test_ap_worker_budget_case
.type __au_test_ap_worker_budget_case,@function
__au_test_ap_worker_budget_case:
    pushq %rbp
    movq %rsp,%rbp
    call @ap_worker_budget_case@
    leave
    ret
.size __au_test_ap_worker_budget_case,.-__au_test_ap_worker_budget_case
.section .note.GNU-stack,"",@progbits

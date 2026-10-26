# Scalar kernel-policy exports for the closed protected supervisor.
# Library helpers remain local; export only policies present in this closed
# source graph. The fixed-pair console has no dispatcher/disposal policy roots.
.global aurora_kernel_value
.global aurora_kernel_budget_tick
.ifdef aurora_kernel_round_robin_next
.global aurora_kernel_round_robin_next
.endif
.global aurora_kernel_ipc_transition
.ifdef aurora_kernel_client_disposal
.global aurora_kernel_client_disposal
.endif
.global aurora_kernel_terminal_event

.section .note.GNU-stack,"",@progbits

# SNAPSHOT_COPY_ABI: one complete private argument record in RDI/R11.
# The native issuer authenticates exact initialized RAM ranges and their
# physical disjointness. The bridge does not mint or authenticate authority.
.text
.global __au_runtime_process_snapshot_copy
.hidden __au_runtime_process_snapshot_copy
.type __au_runtime_process_snapshot_copy,@function
__au_runtime_process_snapshot_copy:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @process_snapshot_copy@
    leave
    ret
.size __au_runtime_process_snapshot_copy,.-__au_runtime_process_snapshot_copy

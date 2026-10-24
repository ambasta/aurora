# Test bridge appended to a compiled IOMMU event consumer: the six-qword host
# record is passed only in compiler-private R11.
.text
.global __au_runtime_iommu_event_entry
.hidden __au_runtime_iommu_event_entry
.type __au_runtime_iommu_event_entry,@function
__au_runtime_iommu_event_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call event_ir_entry
    leave
    ret
.size __au_runtime_iommu_event_entry,.-__au_runtime_iommu_event_entry

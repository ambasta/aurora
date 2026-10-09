# This bridge is appended to the private compiled Aurora consumer assembly.
# The six-qword host record is passed only in compiler-private R11.
.text
.global __au_runtime_iommu_event_entry
.hidden __au_runtime_iommu_event_entry
.type __au_runtime_iommu_event_entry,@function
__au_runtime_iommu_event_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call __au_v_m1_26kernel_iommu_event_service_n0__d18iommu_event_intake
    leave
    ret
.size __au_runtime_iommu_event_entry,.-__au_runtime_iommu_event_entry

.global __au_runtime_iommu_event_value
.hidden __au_runtime_iommu_event_value
.type __au_runtime_iommu_event_value,@function
__au_runtime_iommu_event_value:
    jmp aurora_kernel_value
.size __au_runtime_iommu_event_value,.-__au_runtime_iommu_event_value
# The compiler contributes the sole GNU-stack note for this combined object.

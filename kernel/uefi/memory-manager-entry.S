# MEMORY_MANAGER_ABI: exact five-grant retained bank set; closed borrowed-root operations.
# Native callers pass root, a complete packed u64 argument array and (for a
# copied result) fresh output storage. Aurora's borrowed owner is R10; scalar
# inputs use the ordinary registers and a copied result uses R11. The single
# aggregate-input entry instead receives its complete admitted record in R11.
.text
.macro manager_scalar name, target, count, copied=0
.global \name
.hidden \name
.type \name,@function
\name:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
.if \copied
    movq %rdx,%r11
.endif
    movq %rsi,%rax
.if \count > 0
    movq 0(%rax),%rdi
.endif
.if \count > 1
    movq 8(%rax),%rsi
.endif
.if \count > 2
    movq 16(%rax),%rdx
.endif
.if \count > 3
    movq 24(%rax),%rcx
.endif
.if \count > 4
    movq 32(%rax),%r8
.endif
    call \target
    leave
    ret
.size \name,.-\name
.endm

.global __au_runtime_manager_construct
.hidden __au_runtime_manager_construct
.type __au_runtime_manager_construct,@function
__au_runtime_manager_construct:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @kernel::MemoryManager@
    leave
    ret
.size __au_runtime_manager_construct,.-__au_runtime_manager_construct

manager_scalar __au_runtime_manager_frames_initialize, @manager_frames_initialize@, 2
manager_scalar __au_runtime_manager_frames_allocate, @manager_frames_allocate@, 1, 1
manager_scalar __au_runtime_manager_frames_release, @manager_frames_release@, 3
manager_scalar __au_runtime_manager_frames_record, @manager_frames_record@, 1
manager_scalar __au_runtime_manager_frames_frames, @manager_frames_frames@, 0
manager_scalar __au_runtime_manager_frames_reserved, @manager_frames_reserved@, 0
manager_scalar __au_runtime_manager_frames_free, @manager_frames_free@, 0
manager_scalar __au_runtime_manager_frames_allocated, @manager_frames_allocated@, 0
manager_scalar __au_runtime_manager_frames_owner_allocated, @manager_frames_owner_allocated@, 1
manager_scalar __au_runtime_manager_frames_poisoned, @manager_frames_poisoned@, 0
manager_scalar __au_runtime_manager_frames_audit, @manager_frames_audit@, 0, 1
manager_scalar __au_runtime_manager_attach_shared, @manager_attach_shared@, 0
manager_scalar __au_runtime_manager_prepare_load, @manager_prepare_load@, 4

.global __au_runtime_manager_map_region
.hidden __au_runtime_manager_map_region
.type __au_runtime_manager_map_region,@function
__au_runtime_manager_map_region:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @manager_map_region@
    leave
    ret
.size __au_runtime_manager_map_region,.-__au_runtime_manager_map_region

manager_scalar __au_runtime_manager_finish_load, @manager_finish_load@, 2
manager_scalar __au_runtime_manager_space_value, @manager_space_value@, 3
manager_scalar __au_runtime_manager_map_memory, @manager_map_memory@, 3, 1
manager_scalar __au_runtime_manager_remap_memory, @manager_remap_memory@, 5, 1
manager_scalar __au_runtime_manager_unmap_memory, @manager_unmap_memory@, 4, 1
manager_scalar __au_runtime_manager_fault_access, @manager_fault_access@, 4
manager_scalar __au_runtime_manager_commit_fault_block, @manager_commit_fault_block@, 3
manager_scalar __au_runtime_manager_validate_access, @manager_validate_access@, 5
manager_scalar __au_runtime_manager_verify_space, @manager_verify_space@, 2
manager_scalar __au_runtime_manager_retire_space, @manager_retire_space@, 2
manager_scalar __au_runtime_manager_space_contains, @manager_space_contains@, 4
manager_scalar __au_runtime_manager_space_executable, @manager_space_executable@, 4
manager_scalar __au_runtime_manager_space_entry, @manager_space_entry@, 4, 1
manager_scalar __au_runtime_manager_snapshot_begin, @manager_snapshot_begin@, 2
manager_scalar __au_runtime_manager_snapshot_fill, @manager_snapshot_fill@, 3
manager_scalar __au_runtime_manager_snapshot_seal, @manager_snapshot_seal@, 1
manager_scalar __au_runtime_manager_snapshot_discard, @manager_snapshot_discard@, 1
manager_scalar __au_runtime_manager_snapshot_verify, @manager_snapshot_verify@, 1
manager_scalar __au_runtime_manager_snapshot_value, @manager_snapshot_value@, 2
manager_scalar __au_runtime_manager_audit_residents, @manager_audit_residents@, 0
manager_scalar __au_runtime_manager_finish, @kernel::finish@, 0

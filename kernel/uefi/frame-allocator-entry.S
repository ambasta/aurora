# FRAME_ALLOCATOR_ABI: unique fixed-extent word owner; borrowed ledger entries; consuming terminal receiver.
.text
.global __au_runtime_frame_construct
.hidden __au_runtime_frame_construct
.type __au_runtime_frame_construct,@function
__au_runtime_frame_construct:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @kernel::FrameAllocator@
    leave
    ret
.size __au_runtime_frame_construct,.-__au_runtime_frame_construct
.global __au_runtime_frame_initialize
.hidden __au_runtime_frame_initialize
.type __au_runtime_frame_initialize,@function
__au_runtime_frame_initialize:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    call @process_frames_initialize@
    leave
    ret
.size __au_runtime_frame_initialize,.-__au_runtime_frame_initialize
.global __au_runtime_frame_allocate
.hidden __au_runtime_frame_allocate
.type __au_runtime_frame_allocate,@function
__au_runtime_frame_allocate:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rdx,%r11
    movq %rsi,%rdi
    call @process_frames_allocate@
    leave
    ret
.size __au_runtime_frame_allocate,.-__au_runtime_frame_allocate
.global __au_runtime_frame_release
.hidden __au_runtime_frame_release
.type __au_runtime_frame_release,@function
__au_runtime_frame_release:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    movq %rdx,%rsi
    movq %rcx,%rdx
    call @process_frames_release@
    leave
    ret
.size __au_runtime_frame_release,.-__au_runtime_frame_release
.global __au_runtime_frame_record
.hidden __au_runtime_frame_record
.type __au_runtime_frame_record,@function
__au_runtime_frame_record:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_frames_record@
    leave
    ret
.size __au_runtime_frame_record,.-__au_runtime_frame_record
.global __au_runtime_frame_owner_allocated
.hidden __au_runtime_frame_owner_allocated
.type __au_runtime_frame_owner_allocated,@function
__au_runtime_frame_owner_allocated:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_frames_owner_allocated@
    leave
    ret
.size __au_runtime_frame_owner_allocated,.-__au_runtime_frame_owner_allocated
.global __au_runtime_frame_frames
.hidden __au_runtime_frame_frames
.type __au_runtime_frame_frames,@function
__au_runtime_frame_frames:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_frames_frames@
    leave
    ret
.size __au_runtime_frame_frames,.-__au_runtime_frame_frames
.global __au_runtime_frame_reserved
.hidden __au_runtime_frame_reserved
.type __au_runtime_frame_reserved,@function
__au_runtime_frame_reserved:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_frames_reserved@
    leave
    ret
.size __au_runtime_frame_reserved,.-__au_runtime_frame_reserved
.global __au_runtime_frame_free
.hidden __au_runtime_frame_free
.type __au_runtime_frame_free,@function
__au_runtime_frame_free:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_frames_free@
    leave
    ret
.size __au_runtime_frame_free,.-__au_runtime_frame_free
.global __au_runtime_frame_allocated
.hidden __au_runtime_frame_allocated
.type __au_runtime_frame_allocated,@function
__au_runtime_frame_allocated:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_frames_allocated@
    leave
    ret
.size __au_runtime_frame_allocated,.-__au_runtime_frame_allocated
.global __au_runtime_frame_poisoned
.hidden __au_runtime_frame_poisoned
.type __au_runtime_frame_poisoned,@function
__au_runtime_frame_poisoned:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @process_frames_poisoned@
    leave
    ret
.size __au_runtime_frame_poisoned,.-__au_runtime_frame_poisoned
.global __au_runtime_frame_audit
.hidden __au_runtime_frame_audit
.type __au_runtime_frame_audit,@function
__au_runtime_frame_audit:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @process_frames_audit@
    leave
    ret
.size __au_runtime_frame_audit,.-__au_runtime_frame_audit
.global __au_runtime_frame_finish
.hidden __au_runtime_frame_finish
.type __au_runtime_frame_finish,@function
__au_runtime_frame_finish:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @kernel::finish@
    leave
    ret
.size __au_runtime_frame_finish,.-__au_runtime_frame_finish

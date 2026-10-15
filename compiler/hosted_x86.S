# Fixed whole-module emission boundary. The run tuple is ordered mutable output,
# readonly published metadata, readonly published instructions. No opcode enters
# a native callback and no owner descriptor is exposed for output observation.
.text
.macro emitter_entry operation
.globl aurora_hosted_emitter_\operation
.hidden aurora_hosted_emitter_\operation
.type aurora_hosted_emitter_\operation, @function
aurora_hosted_emitter_\operation:
.endm
.macro emitter_return operation, target
    jmp \target
.size aurora_hosted_emitter_\operation, .-aurora_hosted_emitter_\operation
.endm
emitter_entry create
    movq %rdi, %r11
    movq %rsi, %r10
emitter_return create, __aurora_frontend_emitter_create
emitter_entry release
    movq %rdi, %r11
emitter_return release, __aurora_frontend_emitter_release
emitter_entry status
    movq %rdi, %r10
emitter_return status, __aurora_frontend_emitter_status
emitter_entry add_retained
    movq %rdi, %r10
    movq %rsi, %rdi
emitter_return add_retained, __aurora_frontend_emitter_add_retained
emitter_entry prepare_facts
    movq %rdi, %r10
    movq %rsi, %rdi
emitter_return prepare_facts, __aurora_frontend_emitter_prepare_facts
emitter_entry append_name
    movq %rdi, %r10
    movq %rsi, %r11
emitter_return append_name, __aurora_frontend_emitter_append_name
emitter_entry add_abi_name
    movq %rdi, %r10
    movq %rsi, %r11
emitter_return add_abi_name, __aurora_frontend_emitter_add_abi_name
emitter_entry run
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %rsi
emitter_return run, __aurora_frontend_emitter_run
emitter_entry facts
    movq %rdi, %r10
    movq %rsi, %rdi
emitter_return facts, __aurora_frontend_emitter_facts
emitter_entry size
    movq %rdi, %r10
    movq %rsi, %rdi
emitter_return size, __aurora_frontend_emitter_size
emitter_entry chunk
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %rsi
    movq %rcx, %r11
emitter_return chunk, __aurora_frontend_emitter_chunk

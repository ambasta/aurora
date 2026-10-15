# Compiler-private register bridge. Paired roots are mutable workspace followed
# by its readonly Metadata owner. Scalar tails and results stay in registers;
# neither a descriptor nor any growable word/count payload is observed here.
.text
.macro initialization_entry operation
.globl aurora_hosted_initialization_\operation
.hidden aurora_hosted_initialization_\operation
.type aurora_hosted_initialization_\operation, @function
aurora_hosted_initialization_\operation:
.endm
.macro initialization_return operation, target
    jmp \target
.size aurora_hosted_initialization_\operation, .-aurora_hosted_initialization_\operation
.endm
initialization_entry create
    movq %rdi, %r11
    movq %rsi, %r10
initialization_return create, __aurora_frontend_initialization_create
initialization_entry release
    movq %rdi, %r11
initialization_return release, __aurora_frontend_initialization_release

.macro initialization_root operation, target
initialization_entry \operation
    movq %rdi, %r10
initialization_return \operation, \target
.endm
initialization_root allocated, __aurora_frontend_initialization_allocated
initialization_root status, __aurora_frontend_initialization_status
initialization_root retain, __aurora_frontend_initialization_retain
initialization_root current_count, __aurora_frontend_initialization_current_count
initialization_root retained_count, __aurora_frontend_initialization_retained_count
initialization_root slot_count, __aurora_frontend_initialization_slot_count
initialization_root word_count, __aurora_frontend_initialization_word_count

.macro initialization_scalar operation, target
initialization_entry \operation
    movq %rdi, %r10
    movq %rsi, %rdi
initialization_return \operation, \target
.endm
initialization_scalar initialize, __aurora_frontend_initialization_initialize
initialization_scalar load, __aurora_frontend_initialization_load
initialization_scalar join, __aurora_frontend_initialization_join
initialization_scalar retained_count_at, __aurora_frontend_initialization_retained_count_at
initialization_scalar scalar_state, __aurora_frontend_initialization_scalar_state
initialization_scalar write_scalar, __aurora_frontend_initialization_write_scalar
initialization_scalar object_initialized, __aurora_frontend_initialization_object_initialized
initialization_scalar object_pristine, __aurora_frontend_initialization_object_pristine
initialization_scalar object_was_constructed, __aurora_frontend_initialization_object_was_constructed
initialization_scalar object_completion, __aurora_frontend_initialization_object_completion
initialization_scalar mark_object, __aurora_frontend_initialization_mark_object
initialization_scalar clear_object, __aurora_frontend_initialization_clear_object

.macro initialization_array operation, target
initialization_entry \operation
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %rsi
    movq %rcx, %rdx
initialization_return \operation, \target
.endm
initialization_array array_first_missing, __aurora_frontend_initialization_array_first_missing
initialization_array clear_array, __aurora_frontend_initialization_clear_array
# The generated assembly in this same unit owns .note.GNU-stack.

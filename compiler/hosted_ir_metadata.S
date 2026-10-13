# Compiler-private metadata boundary. Aurora constructs, verifies and consumes
# one owning store; native ingress uses exact generated owner-field facts.
.text
.macro metadata_entry operation
.globl aurora_hosted_metadata_\operation
.hidden aurora_hosted_metadata_\operation
.type aurora_hosted_metadata_\operation, @function
aurora_hosted_metadata_\operation:
.endm
.macro metadata_return operation, target
    jmp \target
.size aurora_hosted_metadata_\operation, .-aurora_hosted_metadata_\operation
.endm

metadata_entry create
    movq %rdi, %r11
    movq %rsi, %r10
metadata_return create, __aurora_frontend_metadata_create

metadata_entry release
    movq %rdi, %r11
metadata_return release, __aurora_frontend_metadata_release

metadata_entry allocated
    movq %rdi, %r10
metadata_return allocated, __aurora_frontend_metadata_allocated

metadata_entry run
    movq %rdi, %r10
metadata_return run, __aurora_frontend_metadata_run

metadata_entry error
    movq %rdi, %r10
metadata_return error, __aurora_frontend_metadata_error

metadata_entry object_leaf_root
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %rsi
metadata_return object_leaf_root, __aurora_frontend_metadata_object_leaf_root

metadata_entry byte_array_element_root
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %rsi
metadata_return byte_array_element_root, __aurora_frontend_metadata_byte_array_element_root

.section .note.GNU-stack,"",@progbits

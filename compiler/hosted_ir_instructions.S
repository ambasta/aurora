# Register-only private boundary. Admission borrows mutable Instructions and
# readonly Metadata in a generated, ordered two-root tuple.
.text
.macro instructions_entry operation
.globl aurora_hosted_instructions_\operation
.hidden aurora_hosted_instructions_\operation
.type aurora_hosted_instructions_\operation, @function
aurora_hosted_instructions_\operation:
.endm
.macro instructions_return operation, target
    jmp \target
.size aurora_hosted_instructions_\operation, .-aurora_hosted_instructions_\operation
.endm
instructions_entry create
    movq %rdi, %r11
    movq %rsi, %r10
instructions_return create, __aurora_frontend_instructions_create
instructions_entry release
    movq %rdi, %r11
instructions_return release, __aurora_frontend_instructions_release
instructions_entry allocated
    movq %rdi, %r10
instructions_return allocated, __aurora_frontend_instructions_allocated
instructions_entry admit
    movq %rdi, %r10
instructions_return admit, __aurora_frontend_instructions_admit
instructions_entry structure
    movq %rdi, %r10
instructions_return structure, __aurora_frontend_instructions_structure
instructions_entry publish
    movq %rdi, %r10
instructions_return publish, __aurora_frontend_instructions_publish
instructions_entry error
    movq %rdi, %r10
instructions_return error, __aurora_frontend_instructions_error
.section .note.GNU-stack,"",@progbits

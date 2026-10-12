# Trusted register-only boundary for the generated resolution session.
# Owner records are constructed and consumed by Aurora. No bridge copies or
# inspects an owner descriptor; scalar offsets are substituted from ABI facts.
.text

.macro resolver_owner operation, target
.globl aurora_hosted_resolver_\operation
.hidden aurora_hosted_resolver_\operation
.type aurora_hosted_resolver_\operation, @function
aurora_hosted_resolver_\operation:
    movq %rdi, %r11
    movq %rsi, %r10
    jmp \target
.size aurora_hosted_resolver_\operation, .-aurora_hosted_resolver_\operation
.endm
resolver_owner create, __aurora_frontend_resolver_create
resolver_owner ingest, __aurora_frontend_resolver_ingest

.macro resolver_release operation, target
.globl aurora_hosted_resolver_\operation
.hidden aurora_hosted_resolver_\operation
.type aurora_hosted_resolver_\operation, @function
aurora_hosted_resolver_\operation:
    movq %rdi, %r11
    jmp \target
.size aurora_hosted_resolver_\operation, .-aurora_hosted_resolver_\operation
.endm
resolver_release release, __aurora_frontend_resolver_release
resolver_release release_pair, __aurora_frontend_resolver_release_pair

.macro resolver_span operation, target
.globl aurora_hosted_resolver_\operation
.hidden aurora_hosted_resolver_\operation
.type aurora_hosted_resolver_\operation, @function
aurora_hosted_resolver_\operation:
    movq %rdi, %r10
    movq %rsi, %r11
    jmp \target
.size aurora_hosted_resolver_\operation, .-aurora_hosted_resolver_\operation
.endm
resolver_span append_source, __aurora_frontend_resolver_append_source
resolver_span append_text, __aurora_frontend_resolver_append_text
resolver_span seed_builtin, __aurora_frontend_resolver_seed_builtin
resolver_span seed_member, __aurora_frontend_resolver_seed_member

.globl aurora_hosted_resolver_order_module
.hidden aurora_hosted_resolver_order_module
.type aurora_hosted_resolver_order_module, @function
aurora_hosted_resolver_order_module:
    movq %rdi, %r10
    movq %rsi, %r11
    movq __aurora_parameter_resolver_order_module_0(%r11), %rdi
    movq __aurora_parameter_resolver_order_module_1(%r11), %rsi
    movq __aurora_parameter_resolver_order_module_2(%r11), %rdx
    movq __aurora_parameter_resolver_order_module_3(%r11), %rcx
    jmp __aurora_frontend_resolver_order_module
.size aurora_hosted_resolver_order_module, .-aurora_hosted_resolver_order_module

.globl aurora_hosted_resolver_bind_import
.hidden aurora_hosted_resolver_bind_import
.type aurora_hosted_resolver_bind_import, @function
aurora_hosted_resolver_bind_import:
    movq %rdi, %r10
    movq %rsi, %r11
    movq __aurora_parameter_resolver_bind_import_0(%r11), %rdi
    movq __aurora_parameter_resolver_bind_import_1(%r11), %rsi
    movq __aurora_parameter_resolver_bind_import_2(%r11), %rdx
    jmp __aurora_frontend_resolver_bind_import
.size aurora_hosted_resolver_bind_import, .-aurora_hosted_resolver_bind_import

.macro resolver_index operation, target
.globl aurora_hosted_resolver_\operation
.hidden aurora_hosted_resolver_\operation
.type aurora_hosted_resolver_\operation, @function
aurora_hosted_resolver_\operation:
    movq %rdi, %r10
    movq %rsi, %rdi
    jmp \target
.size aurora_hosted_resolver_\operation, .-aurora_hosted_resolver_\operation
.endm
resolver_index count, __aurora_frontend_resolver_count
resolver_index read_source, __aurora_frontend_resolver_read_source

.macro resolver_read operation, target
.globl aurora_hosted_resolver_\operation
.hidden aurora_hosted_resolver_\operation
.type aurora_hosted_resolver_\operation, @function
aurora_hosted_resolver_\operation:
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %r11
    jmp \target
.size aurora_hosted_resolver_\operation, .-aurora_hosted_resolver_\operation
.endm
resolver_read read_syntax, __aurora_frontend_resolver_read_syntax
resolver_read read_meta, __aurora_frontend_resolver_read_meta
resolver_read read_resolved, __aurora_frontend_resolver_read_resolved

.globl aurora_hosted_resolver_status
.hidden aurora_hosted_resolver_status
.type aurora_hosted_resolver_status, @function
aurora_hosted_resolver_status:
    movq %rdi, %r10
    movq %rsi, %r11
    jmp __aurora_frontend_resolver_status
.size aurora_hosted_resolver_status, .-aurora_hosted_resolver_status

.globl aurora_hosted_resolver_run
.hidden aurora_hosted_resolver_run
.type aurora_hosted_resolver_run, @function
aurora_hosted_resolver_run:
    movq %rdi, %r10
    jmp __aurora_frontend_resolver_run
.size aurora_hosted_resolver_run, .-aurora_hosted_resolver_run

# Lowering borrows the same live Session. Inputs and copied results use the
# compiler-described argument/result records; no owner or row bytes are copied.
.macro lowering_record operation, target
.globl aurora_hosted_lowering_\operation
.hidden aurora_hosted_lowering_\operation
.type aurora_hosted_lowering_\operation, @function
aurora_hosted_lowering_\operation:
    movq %rdi, %r10
    movq %rsi, %r11
    jmp \target
.size aurora_hosted_lowering_\operation, .-aurora_hosted_lowering_\operation
.endm
lowering_record begin, __aurora_frontend_lowering_begin
lowering_record seed_scalar, __aurora_frontend_lowering_seed_scalar
lowering_record seed_service, __aurora_frontend_lowering_seed_service
lowering_record run, __aurora_frontend_lowering_run

.macro lowering_index operation, target
.globl aurora_hosted_lowering_\operation
.hidden aurora_hosted_lowering_\operation
.type aurora_hosted_lowering_\operation, @function
aurora_hosted_lowering_\operation:
    movq %rdi, %r10
    movq %rsi, %rdi
    jmp \target
.size aurora_hosted_lowering_\operation, .-aurora_hosted_lowering_\operation
.endm
lowering_index seed_layout_symbol, __aurora_frontend_lowering_seed_layout_symbol
lowering_index count, __aurora_frontend_lowering_count

.macro lowering_read operation, target
.globl aurora_hosted_lowering_\operation
.hidden aurora_hosted_lowering_\operation
.type aurora_hosted_lowering_\operation, @function
aurora_hosted_lowering_\operation:
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %r11
    jmp \target
.size aurora_hosted_lowering_\operation, .-aurora_hosted_lowering_\operation
.endm
lowering_read read_output, __aurora_frontend_lowering_read_output
lowering_read read_operand, __aurora_frontend_lowering_read_operand

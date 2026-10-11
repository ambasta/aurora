# Trusted private bridge for the one generated parser/arena/lexer module graph.
# Owning records are made and consumed by Aurora; the host only reserves storage.
.text
.globl aurora_hosted_parser_create
.hidden aurora_hosted_parser_create
.type aurora_hosted_parser_create, @function
aurora_hosted_parser_create:
    movq %rdi, %r11
    movq %rsi, %r10
    jmp __aurora_frontend_parser_create
.size aurora_hosted_parser_create, .-aurora_hosted_parser_create

.globl aurora_hosted_parser_parse
.hidden aurora_hosted_parser_parse
.type aurora_hosted_parser_parse, @function
aurora_hosted_parser_parse:
    movq %rdi, %r10
    movq %rsi, %r11
    movq %rdx, %rax
    jmp __aurora_frontend_parser_parse
.size aurora_hosted_parser_parse, .-aurora_hosted_parser_parse

.globl aurora_hosted_parser_count
.hidden aurora_hosted_parser_count
.type aurora_hosted_parser_count, @function
aurora_hosted_parser_count:
    movq %rdi, %r10
    jmp __aurora_frontend_parser_node_count
.size aurora_hosted_parser_count, .-aurora_hosted_parser_count

.globl aurora_hosted_parser_read
.hidden aurora_hosted_parser_read
.type aurora_hosted_parser_read, @function
aurora_hosted_parser_read:
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %r11
    jmp __aurora_frontend_parser_read_node
.size aurora_hosted_parser_read, .-aurora_hosted_parser_read

# Reverse-linked argument edges are copied through the same private ABI.
.globl aurora_hosted_parser_edges
.hidden aurora_hosted_parser_edges
.type aurora_hosted_parser_edges, @function
aurora_hosted_parser_edges:
    movq %rdi, %r10
    jmp __aurora_frontend_parser_edge_count
.size aurora_hosted_parser_edges, .-aurora_hosted_parser_edges

.globl aurora_hosted_parser_edge
.hidden aurora_hosted_parser_edge
.type aurora_hosted_parser_edge, @function
aurora_hosted_parser_edge:
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %r11
    jmp __aurora_frontend_parser_read_edge
.size aurora_hosted_parser_edge, .-aurora_hosted_parser_edge

# Unresolved type syntax records are copied; ownership stays inside the arena.
.globl aurora_hosted_parser_types
.hidden aurora_hosted_parser_types
.type aurora_hosted_parser_types, @function
aurora_hosted_parser_types:
    movq %rdi, %r10
    jmp __aurora_frontend_parser_type_count
.size aurora_hosted_parser_types, .-aurora_hosted_parser_types

.globl aurora_hosted_parser_type
.hidden aurora_hosted_parser_type
.type aurora_hosted_parser_type, @function
aurora_hosted_parser_type:
    movq %rdi, %r10
    movq %rsi, %rdi
    movq %rdx, %r11
    jmp __aurora_frontend_parser_read_type
.size aurora_hosted_parser_type, .-aurora_hosted_parser_type

.globl aurora_hosted_parser_release
.hidden aurora_hosted_parser_release
.type aurora_hosted_parser_release, @function
aurora_hosted_parser_release:
    movq %rdi, %r11
    jmp __aurora_frontend_parser_release
.size aurora_hosted_parser_release, .-aurora_hosted_parser_release

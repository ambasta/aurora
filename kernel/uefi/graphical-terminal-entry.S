# Private supervisor bridge, assembled with its generated Aurora graph.
# TERMINAL_PAINT_ABI: the caller owns one complete six-qword record: Display
# grant +0/+8, width +16, height +24, cell position +32 and glyph +40. The
# bridge itself does not authenticate it; the result is a bool in %rax.
.text
.global __au_runtime_terminal_paint
.hidden __au_runtime_terminal_paint
.type __au_runtime_terminal_paint,@function
__au_runtime_terminal_paint:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @paint_terminal_cell@
    leave
    ret
.size __au_runtime_terminal_paint,.-__au_runtime_terminal_paint

.section .note.GNU-stack,"",@progbits

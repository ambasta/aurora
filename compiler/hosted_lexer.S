# This trusted host-only shim is assembled in the SAME unit as generated lexer.au.
# The Aurora entry stays local; there is no new language-visible foreign ABI.
.text
.globl aurora_hosted_lexer_invoke
.hidden aurora_hosted_lexer_invoke
.type aurora_hosted_lexer_invoke, @function
aurora_hosted_lexer_invoke:
    movq %rdi, %r11
    movq %rsi, %r10
    jmp __au_v_m3_6aurora8compiler5lexer_n1_14compiler_lexer_d11next_lexeme
.size aurora_hosted_lexer_invoke, .-aurora_hosted_lexer_invoke

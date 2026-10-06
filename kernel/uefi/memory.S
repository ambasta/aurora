# Compiler-required freestanding memory primitives (x86-64 System V ABI).
# Trusted bootstrap only. Assembly prevents lowering these loops into themselves.
# The ABI requires DF clear; no routine changes it, including overlapping memmove.
.section .text
.global memcpy, memset, memmove, memcmp
.hidden memcpy, memset, memmove, memcmp
.type memcpy,@function
memcpy:
    mov %rdi, %rax
    mov %rdx, %rcx
    rep movsb
    ret
.size memcpy, .-memcpy

.type memset,@function
memset:
    mov %rdi, %r8
    mov %esi, %eax
    mov %rdx, %rcx
    rep stosb
    mov %r8, %rax
    ret
.size memset, .-memset

.type memmove,@function
memmove:
    mov %rdi, %rax
    cmp %rsi, %rdi
    jbe .Lforward
    mov %rdi, %r8
    sub %rsi, %r8
    cmp %rdx, %r8
    jae .Lforward
    # Destination starts inside source: copy backwards without setting DF.
.Lbackward:
    movb -1(%rsi,%rdx), %r8b
    movb %r8b, -1(%rdi,%rdx)
    sub $1, %rdx
    jnz .Lbackward
    ret
.Lforward:
    mov %rdx, %rcx
    rep movsb
    ret
.size memmove, .-memmove

.type memcmp,@function
memcmp:
    xor %eax, %eax
    test %rdx, %rdx
    jz .Lcompared
.Lcompare:
    movzbl (%rdi), %eax
    movzbl (%rsi), %r8d
    sub %r8d, %eax
    jnz .Lcompared
    inc %rdi
    inc %rsi
    dec %rdx
    jnz .Lcompare
.Lcompared:
    ret
.size memcmp, .-memcmp
.section .note.GNU-stack,"",@progbits

# Process-image programs (kernel/uefi/process.md#guest-rows) that each try one
# thing a process must not do; the kernel ends only that process. Assembled once
# per case with --defsym CASE=N:
#   1 write its own code page       5 read the kernel's window (upper half)
#   2 run code from its stack       6 kernel call with an unknown operation
#   3 cli (privileged instruction)  7 print from a kernel address
#   4 in from an I/O port           8 int 14, a vector user code may not raise
# GNU as, because Aurora source cannot express these.
.text
.globl _start
_start:
.if CASE == 1
    movb $0xc3, _start(%rip)
.elseif CASE == 2
    pushq $0xc3
    jmp *%rsp
.elseif CASE == 3
    cli
.elseif CASE == 4
    inb $0x80, %al
.elseif CASE == 5
    movabsq $0xffff800000000000, %rax
    movq (%rax), %rax
.elseif CASE == 6
    movl $99, %eax
    int $0x83
.elseif CASE == 7
    movl $2, %eax
    movl $1, %edi
    movabsq $0xffff800000000000, %rsi
    movl $8, %edx
    int $0x83
.elseif CASE == 8
    int $14
.endif
    ud2
.section .note.GNU-stack,"",@progbits

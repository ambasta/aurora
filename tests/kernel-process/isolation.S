# Process-image programs (kernel/uefi/process.md#guest-rows) that each try one
# thing a process must not do; the kernel ends only that process. Assembled once
# per case with --defsym CASE=N:
#   1 write its own code page       5 read the kernel's window (upper half)
#   2 run code from its stack       6 kernel call with an unknown operation
#   3 cli (privileged instruction)  7 print from a kernel address
#   4 in from an I/O port           8 int 14, a vector user code may not raise
#   9 touch a mapping's reservation past its pages (the first touch of its
#     last page commits; the next page is not the mapping's)
#  10 unmap a mapping with a length it does not have
#  11 read a mapping's old address after it moved (its byte moved with it)
#  12 open a volume file and read it into a mapping's untouched pages (the
#     record and the chunk), then print it from there: allowed, the kernel
#     commits the pages first
#  13 read a file into a mapping's reservation past its pages
#  14 read a file into its own code page
#  15 open a path at a kernel address
#  16 write an output's bytes from an address nothing maps
#  17 stale, forged and mistyped ids, each refused with invalid_handle; it
#     exits with the step that was not (0 when every one was)
# GNU as, because Aurora source cannot express these.
.macro kernel_call operation
    movl $\operation, %eax
    int $0x83
.endm
.macro expect value, step
    movl $\step, %edi
    cmpq $\value, %rax
    jne 9f
.endm
.macro open_file path, length
    xorl %edi, %edi
    leaq \path(%rip), %rsi
    movl $\length, %edx
    kernel_call 9
.endm
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
.elseif CASE == 9
    movl $4, %eax
    movl $12288, %edi
    int $0x83
    movb $1, 8192(%rax)
    movb $1, 12288(%rax)
.elseif CASE == 10
    movl $4, %eax
    movl $4096, %edi
    int $0x83
    movq %rax, %rdi
    movl $6, %eax
    movl $8192, %esi
    int $0x83
.elseif CASE == 11
    movl $4, %eax
    movl $4096, %edi
    int $0x83
    movq %rax, %rbx
    movb $0x5a, (%rbx)
    movq %rbx, %rdi
    movl $5, %eax
    movl $4096, %esi
    movl $12288, %edx
    int $0x83
    cmpb $0x5a, (%rax)
    jne 1f
    movb (%rbx), %al
1:
.elseif CASE == 12
    movl $0x20000, %edi
    kernel_call 4
    movq %rax, %rbx
    movq %rbx, %r10
    open_file a_txt, 10
    testq %rax, %rax
    jnz 1f
    movq (%rbx), %rdi
    xorl %esi, %esi
    leaq 0x10000(%rbx), %rdx
    kernel_call 3
    movq %rax, %rdx
    movl $1, %edi
    leaq 0x10000(%rbx), %rsi
    kernel_call 2
    xorl %edi, %edi
    kernel_call 1
1:
.elseif CASE == 13 || CASE == 14
    movl $4096, %edi
    kernel_call 4
    movq %rax, %rbx
    subq $64, %rsp
    movq %rsp, %r10
    open_file a_txt, 10
    movq (%rsp), %rdi
    xorl %esi, %esi
  .if CASE == 13
    leaq 8192(%rbx), %rdx
  .else
    leaq _start(%rip), %rdx
  .endif
    kernel_call 3
.elseif CASE == 15
    subq $64, %rsp
    movq %rsp, %r10
    xorl %edi, %edi
    movabsq $0xffff800000000000, %rsi
    movl $8, %edx
    kernel_call 9
.elseif CASE == 16
    subq $64, %rsp
    movq %rsp, %r10
    xorl %edi, %edi
    leaq w_txt(%rip), %rsi
    movl $10, %edx
    kernel_call 11
    movq (%rsp), %rdi
    movl $0x10000000, %esi
    movl $16, %edx
    kernel_call 12
.elseif CASE == 17
    subq $1024, %rsp
    movq %rsp, %r10
    xorl %edi, %edi
    leaq tree(%rip), %rsi
    movl $4, %edx
    kernel_call 7
    expect 0, 1
    movq (%rsp), %r14
    movq %r14, %rdi
    leaq a_txt + 5(%rip), %rsi
    movl $5, %edx
    kernel_call 8
    expect 0, 2
    movq (%rsp), %r15
    movq %r15, %rdi
    kernel_call 10
    expect 0, 3
    # The closed file's id, read and closed again.
    movq %r15, %rdi
    xorl %esi, %esi
    leaq 512(%rsp), %rdx
    kernel_call 3
    expect -1, 4
    movq %r15, %rdi
    kernel_call 10
    expect -1, 5
    # The directory read as a file.
    movq %r14, %rdi
    xorl %esi, %esi
    leaq 512(%rsp), %rdx
    kernel_call 3
    expect -1, 6
    # A live file's id with the next generation, and the file as a directory.
    movq %r14, %rdi
    leaq a_txt + 5(%rip), %rsi
    movl $5, %edx
    kernel_call 8
    expect 0, 7
    movq (%rsp), %r13
    leaq 64(%r13), %rdi
    xorl %esi, %esi
    leaq 512(%rsp), %rdx
    kernel_call 3
    expect -1, 8
    movq %r13, %rdi
    leaq a_txt + 5(%rip), %rsi
    movl $5, %edx
    kernel_call 8
    expect -1, 9
    # A made-up slot past the outputs, zero, and a handle as an output.
    movl $37, %edi
    kernel_call 10
    expect -1, 10
    xorl %edi, %edi
    kernel_call 14
    expect -1, 11
    movq %r14, %rdi
    kernel_call 13
    expect -1, 12
    # An output used after its commit, and with the next generation.
    xorl %edi, %edi
    leaq f_txt(%rip), %rsi
    movl $10, %edx
    kernel_call 11
    expect 0, 13
    movq (%rsp), %r15
    leaq 64(%r15), %rdi
    kernel_call 14
    expect -1, 14
    movq %r15, %rdi
    kernel_call 13
    expect 0, 15
    movq %r15, %rdi
    kernel_call 13
    expect -1, 16
    movq %r15, %rdi
    leaq 512(%rsp), %rsi
    movl $4, %edx
    kernel_call 12
    expect -1, 17
    # The live file still reads.
    movq %r13, %rdi
    xorl %esi, %esi
    leaq 512(%rsp), %rdx
    kernel_call 3
    expect 6, 18
    xorl %edi, %edi
9:
    kernel_call 1
.endif
    ud2
.section .rodata
tree:
    .ascii "tree"
a_txt:
    .ascii "tree/a.txt"
w_txt:
    .ascii "tree/w.txt"
f_txt:
    .ascii "tree/f.txt"
.section .note.GNU-stack,"",@progbits

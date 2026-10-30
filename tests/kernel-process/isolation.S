# Process-image programs (kernel/uefi/process.md#guest-rows) that each try one
# thing a process must not do; the kernel ends only that process. Assembled once
# per case with --defsym CASE=N:
#   1 write its own code page       5 read the kernel's window (upper half)
#   2 run code from its stack       6 raw ABI probes selected by argument (unknown, forge, write, service, block)
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
    # One raw ABI probe, selected by ordinary run-list data. The supervisor,
    # never argv, grants the service role and independent generation in RDX.
    # Match whole NUL-terminated argv data before the original three modes.
    cld
    movq %r8, %r9
    movq %rdx, %r13
    movq %rdi, %r14
    movq %rsi, %r15
    # Production supplies fixed argv, not fixture selectors. Only an exact
    # file-service argv may select one of the readonly data-driven probes.
    cmpq $13, %r15
    jne .Largument_modes
    movq %r14, %rdi
    leaq .Lproduction_service_name(%rip), %rsi
    movl $13, %ecx
    repe cmpsb
    jne .Largument_modes
    movq aurora_service_probe_mode(%rip), %r12
    testq %r12, %r12
    jz .Largument_modes
    cmpq $12, %r12
    je .Lservice_probe
    cmpq $13, %r12
    je .Lservice_probe
    cmpq $14, %r12
    je .Lservice_probe
    ud2
.Lwriter_probe:
    # The first boot recovery role has retired. Its observed generation cannot
    # authorize an ordinary program, even with a valid sector/window.
    subq $512, %rsp
    movq %rsp, %rdi
    movl $64, %ecx
    xorl %eax, %eax
    rep stosq
    xorl %r10d, %r10d
    movl $1, %edx
    xorl %esi, %esi
    xorl %edi, %edi
    cmpl $33, %r12d
    je .Lwriter_flush
    movq %rsp, %rdi
    movl $99, %esi
    kernel_call 18
    ud2
.Lwriter_flush:
    kernel_call 19
    ud2
.Largument_modes:
    leaq service_modes(%rip), %rbx
    movl $18, %r11d
.Lmode_next:
    movl 8(%rbx), %ecx
    cmpq %rcx, %r15
    jne .Lmode_skip
    movq %r14, %rdi
    movq (%rbx), %rsi
    repe cmpsb
    jne .Lmode_skip
    movl 12(%rbx), %r12d
    cmpl $32, %r12d
    jae .Lwriter_probe
    cmpl $30, %r12d
    je .Lquota_probe
    cmpl $31, %r12d
    je .Lquota_probe
    cmpl $20, %r12d
    jae .Lblock_probe
    jmp .Lservice_probe
.Lmode_skip:
    addq $16, %rbx
    decl %r11d
    jnz .Lmode_next
    movq %r14, %rdi
    movq %r15, %rsi
    # Preserve unknown operation admission independently from a valid but
    # ungranted endpoint, and the exact 65536-byte raw write regression.
    testq %rsi, %rsi
    jz 60f
    cmpb $102, (%rdi)
    je 61f
    cmpb $114, (%rdi)
    je 62f
60: movl $99, %eax
    int $0x83
61: movl $15, %eax
    int $0x83
62: subq $1024, %rsp
    movl $65536, %edi
    kernel_call 4
    testq %rax, %rax
    jz 69f
    movq %rax, %r12
    movq %rax, %rdi
    movl $65536, %ecx
    movb $90, %al
    rep stosb
    movq %rsp, %r10
    xorl %edi, %edi
    leaq raw_path(%rip), %rsi
    movl $8, %edx
    kernel_call 11
    testq %rax, %rax
    jnz 69f
    movq (%rsp), %r15
    movq %r15, %rdi
    movq %r12, %rsi
    movl $65536, %edx
    kernel_call 12
    testq %rax, %rax
    jnz 69f
    movq %r15, %rdi
    kernel_call 13
    testq %rax, %rax
    jnz 69f
    open_file raw_path, 8
    testq %rax, %rax
    jnz 69f
    cmpq $65536, 8(%rsp)
    jne 69f
    movq (%rsp), %r14
    xorq %r13, %r13
63: movq %r14, %rdi
    movq %r13, %rsi
    leaq 64(%rsp), %rdx
    kernel_call 3
    testq %rax, %rax
    jle 69f
    movq %rax, %rbx
    movq %rax, %rcx
    leaq 64(%rsp), %rdi
    movb $90, %al
    repe scasb
    jne 69f
    addq %rbx, %r13
    cmpq $65536, %r13
    jb 63b
    jne 69f
    movq %r12, %rdi
    movl $65536, %esi
    kernel_call 6
    testq %rax, %rax
    jnz 69f
    xorl %edi, %edi
    kernel_call 1
69: movl $1, %edi
    kernel_call 1

.Lquota_probe:
    # The retained server has a 64 MiB heap allowance above its eager load.
    # Indices and copied volume consume part: refusal precedes the file limit.
    # A one-byte prefix keeps every whole raw write at page offset1: the
    # failing request first copies the old page's tail, then needs a new page.
    # Select only the transfer size and loop bound; all refusal checks are shared.
    movl $65536, %ebx
    movl $1023, %r14d
    cmpl $31, %r12d
    jne .Lquota_ready
    movl $4096, %ebx
    movl $16383, %r14d
.Lquota_ready:
    subq $1024, %rsp
    movl $65536, %edi
    kernel_call 4
    testq %rax, %rax
    jz 69b
    movq %rax, %r12
    movq %rax, %rdi
    movl $65536, %ecx
    movb $90, %al
    rep stosb
    movq %rsp, %r10
    xorl %edi, %edi
    leaq shared_path(%rip), %rsi
    movl $11, %edx
    kernel_call 11
    testq %rax, %rax
    jnz 69b
    movq (%rsp), %r15
    movq %r15, %rdi
    movq %r12, %rsi
    movl $1, %edx
    kernel_call 12
    testq %rax, %rax
    jnz 69b
    xorl %r13d, %r13d
.Lquota_write:
    # Both 1 + 1023 * 65536 and 1 + 16383 * 4096 stay below the file limit.
    # Success throughout fails the test, never falling through to too_large.
    cmpq %r14, %r13
    jae 69b
    incq %r13
    movq %r15, %rdi
    movq %r12, %rsi
    movq %rbx, %rdx
    kernel_call 12
    testq %rax, %rax
    jz .Lquota_write
    cmpq $-9, %rax
    jne 69b
    # The failed output stays poisoned even for a one-byte append. Commit
    # fails, releases its pending record, and invalidates the output handle.
    movq %r15, %rdi
    movq %r12, %rsi
    movl $1, %edx
    kernel_call 12
    cmpq $-9, %rax
    jne 69b
    movq %r15, %rdi
    kernel_call 13
    cmpq $-9, %rax
    jne 69b
    movq %r15, %rdi
    movq %r12, %rsi
    movl $1, %edx
    kernel_call 12
    cmpq $-1, %rax
    jne 69b
    # Failed replacement never changes the original committed two-byte file.
    movq %rsp, %r10
    open_file shared_path, 11
    testq %rax, %rax
    jnz 69b
    cmpq $2, 8(%rsp)
    jne 69b
    movq (%rsp), %r14
    movq %r14, %rdi
    xorl %esi, %esi
    leaq 64(%rsp), %rdx
    kernel_call 3
    cmpq $2, %rax
    jne 69b
    cmpw $0x3276, 64(%rsp)
    jne 69b
    movq %r14, %rdi
    movl $2, %esi
    leaq 64(%rsp), %rdx
    kernel_call 3
    testq %rax, %rax
    jnz 69b
    movq %r14, %rdi
    kernel_call 10
    testq %rax, %rax
    jnz 69b
    # At the same exhausted quota a new output can reuse released pages.
    movq %rsp, %r10
    xorl %edi, %edi
    leaq quota_path(%rip), %rsi
    movl $17, %edx
    kernel_call 11
    testq %rax, %rax
    jnz 69b
    cmpq %r15, (%rsp)
    je 69b
    movq (%rsp), %r15
    movq %r15, %rdi
    movq %r12, %rsi
    movl $1, %edx
    kernel_call 12
    testq %rax, %rax
    jnz 69b
    movq %r15, %rdi
    kernel_call 13
    testq %rax, %rax
    jnz 69b
    movq %rsp, %r10
    open_file quota_path, 17
    testq %rax, %rax
    jnz 69b
    cmpq $1, 8(%rsp)
    jne 69b
    movq (%rsp), %r14
    movq %r14, %rdi
    xorl %esi, %esi
    leaq 64(%rsp), %rdx
    kernel_call 3
    cmpq $1, %rax
    jne 69b
    cmpb $90, 64(%rsp)
    jne 69b
    movq %r14, %rdi
    movl $1, %esi
    leaq 64(%rsp), %rdx
    kernel_call 3
    testq %rax, %rax
    jnz 69b
    movq %r14, %rdi
    kernel_call 10
    testq %rax, %rax
    jnz 69b
    movq %r12, %rdi
    movl $65536, %esi
    kernel_call 6
    testq %rax, %rax
    jnz 69b
    xorl %edi, %edi
    kernel_call 1

.Lblock_probe:
    # No block grant is issued to these ordinary processes. Unavailable must
    # copy all 512 zero bytes, even over a nonzero destination and huge LBA.
    subq $512, %rsp
    movq %rsp, %rdi
    movl $512, %ecx
    movb $165, %al
    rep stosb
    movq %rsp, %rdi
    movq $-1, %rsi
    xorl %edx, %edx
    xorl %r10d, %r10d
    cmpl $21, %r12d
    jne .Lblock_reserved
    movl $1, %edx
.Lblock_reserved:
    cmpl $22, %r12d
    jne .Lblock_call
    movl $1, %r10d
.Lblock_call:
    kernel_call 16
    cmpl $20, %r12d
    jne 69b
    cmpq $3, %rax
    jne 69b
    testq %rdx, %rdx
    jnz 69b
    movq %rsp, %rdi
    movl $512, %ecx
    xorl %eax, %eax
    repe scasb
    jne 69b
    xorl %edi, %edi
    kernel_call 1

.Lservice_probe:
    # The exact private endpoint window, with extra tail bytes so ptr+8 is
    # still owned memory: that mode must fail window identity, not extent.
    subq $131152, %rsp
    movq %rsp, %rbp
    movq %rsp, %rdi
    movl $16394, %ecx
    xorl %eax, %eax
    rep stosq
    xorl %r15d, %r15d
    xorl %r14d, %r14d
    xorl %ebx, %ebx
    movq %rbp, %rdi
    xorl %esi, %esi
    movq %r13, %rdx
    xorl %r10d, %r10d
.Lservice_exchange:
    kernel_call 15
    testq %rax, %rax
    jnz 69b
    cmpq $65536, %rdx
    ja 69b
    cmpq %rdx, (%rbp)
    jne 69b
    cmpq $1, 24(%rbp)
    jne 69b
    cmpq $0, 16(%rbp)
    je 69b
    # Canonical 64-byte control acknowledgement or not_found client reply.
    leaq 65600(%rbp), %rdi
    movl $8, %ecx
    xorl %eax, %eax
    rep stosq
    movq %rbp, %rdi
    movl $64, %esi
    movq %r13, %rdx
    movq 16(%rbp), %r10
    cmpq $0, 8(%rbp)
    jne .Lservice_client
    # Bootstrap controls 1/2/3 and client admission4 get zero replies. A
    # duplicated reply is attempted only after its valid earlier reply was
    # consumed and the kernel delivered the new terminal-cleanup5 request.
    cmpq $6, 64(%rbp)
    je .Lservice_stop
    cmpq $1, 64(%rbp)
    jb 69b
    cmpq $5, 64(%rbp)
    ja 69b
    cmpq $5, 64(%rbp)
    jne .Lservice_exchange
    cmpl $10, %r12d
    jne .Lservice_exchange
    testq %r15, %r15
    jz 69b
    movq %r15, %r10
    jmp .Lservice_exchange
.Lservice_client:
    cmpq $12, %r12
    je .Lsnapshot_request
    cmpq $13, %r12
    je .Lsnapshot_request
    cmpq $18, 64(%rbp)
    jne 69b
    movq $2, 65600(%rbp)
    cmpl $14, %r12d
    je .Lservice_exchange
    cmpl $1, %r12d
    jne .Lservice_stale
    xorl %edx, %edx
    jmp .Lservice_exchange
.Lservice_stale:
    cmpl $2, %r12d
    jne .Lservice_window
    # The case9 supervisor runs this after generation1 has been retired.
    cmpq $2, %rdx
    jb 69b
    decq %rdx
    jmp .Lservice_exchange
.Lservice_window:
    cmpl $3, %r12d
    jne .Lservice_transaction
    addq $8, %rdi
    jmp .Lservice_exchange
.Lservice_transaction:
    cmpl $4, %r12d
    jne .Lservice_count
    decq %r10
    jmp .Lservice_exchange
.Lservice_count:
    cmpl $5, %r12d
    jne .Lservice_reply
    movl $65537, %esi
    jmp .Lservice_exchange
.Lservice_reply:
    cmpl $6, %r12d
    jne .Lservice_reserved
    movq $10, 65600(%rbp)
    jmp .Lservice_exchange
.Lservice_reserved:
    cmpl $7, %r12d
    jne .Lservice_die
    movq $1, 65616(%rbp)
    jmp .Lservice_exchange
.Lservice_die:
    cmpl $8, %r12d
    jne .Lservice_spin
    ud2
.Lservice_spin:
    cmpl $9, %r12d
    jne .Lservice_duplicate
.Lservice_spinning:
    pause
    jmp .Lservice_spinning
.Lservice_duplicate:
    cmpl $11, %r12d
    je .Lservice_block_forge
    cmpl $10, %r12d
    jne 69b
    testq %r15, %r15
    jnz 69b
    movq %r10, %r15
    jmp .Lservice_exchange
.Lservice_block_forge:
    # This designated disk server really received a live block grant in R8.
    # Its first request tries a different generation, not a different owner.
    testq %r9, %r9
    jz 69b
    leaq 64(%rbp), %rdi
    xorl %esi, %esi
    leaq 1(%r9), %rdx
    xorl %r10d, %r10d
    kernel_call 16
    jmp 69b
.Lsnapshot_request:
    # Exactly one open/read/close sequence from the same authenticated loader
    # client. No repeated open/read can silently replay the failed operation.
    testq %rbx, %rbx
    jz .Lsnapshot_open
    movq 8(%rbp), %rax
    cmpq %r14, %rax
    jne 69b
    cmpq $64, (%rbp)
    jne 69b
    cmpq $65, 72(%rbp)
    jne 69b
    cmpq $0, 80(%rbp)
    jne 69b
    cmpq $0, 88(%rbp)
    jne 69b
    cmpq $1, %rbx
    je .Lsnapshot_read
    cmpq $2, %rbx
    jne 69b
    cmpq $20, 64(%rbp)
    jne 69b
    movl $3, %ebx
    cmpq $12, %r12
    # A malformed read discards the writable snapshot before best-effort
    # close. ACK that cleanup: the earlier read, not this probe's death,
    # must remain the cause of unavailable/common abandonment.
    je .Lservice_exchange
    # Mode13 has delivered its full byte. The loader sealed the snapshot,
    # but this malformed close must discard it before ELF admission.
    movq $10, 65600(%rbp)
    jmp .Lservice_exchange
.Lsnapshot_open:
    cmpq $18, 64(%rbp)
    jne 69b
    cmpq $0, 72(%rbp)
    jne 69b
    cmpq $0, 80(%rbp)
    jne 69b
    movq 88(%rbp), %rax
    testq %rax, %rax
    jz 69b
    cmpq $255, %rax
    ja 69b
    addq $64, %rax
    cmpq %rax, (%rbp)
    jne 69b
    movq 8(%rbp), %r14
    movl $1, %ebx
    movq $65, 65616(%rbp)
    movq $4096, 65624(%rbp)
    cmpq $12, %r12
    je .Lsnapshot_open_ready
    movq $1, 65624(%rbp)
.Lsnapshot_open_ready:
    movq $1, 65632(%rbp)
    movq $1, 65640(%rbp)
    jmp .Lservice_exchange
.Lsnapshot_read:
    cmpq $19, 64(%rbp)
    jne 69b
    movl $2, %ebx
    cmpq $12, %r12
    jne .Lsnapshot_read_byte
    movq $10, 65600(%rbp)
    jmp .Lservice_exchange
.Lsnapshot_read_byte:
    movq $1, 65608(%rbp)
    movb $0, 65664(%rbp)
    movl $65, %esi
    jmp .Lservice_exchange
.Lservice_stop:
    cmpl $14, %r12d
    jne .Lservice_clean_stop
    ud2
.Lservice_clean_stop:
    xorl %edi, %edi
    kernel_call 1
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
.if CASE == 6
# The private-volume harness may patch this one ELF data symbol, never code.
# It is immutable while running and has meaning only for exact file-service
# argv: zero preserves original dispatch; 12/13 are snapshot cases and 14
# acknowledges startup/loader refusal, then faults only on control6 shutdown.
.p2align 3
.globl aurora_service_probe_mode
.type aurora_service_probe_mode,@object
aurora_service_probe_mode:
    .quad 0
.size aurora_service_probe_mode,.-aurora_service_probe_mode
.Lproduction_service_name: .asciz "file-service"
raw_path: .ascii "tree/raw"
shared_path: .ascii "tree/shared"
quota_path: .ascii "tree/quota-reused"
# name address, exact argv extent (including NUL), mode. No per-mode assembly.
.p2align 3
service_modes:
.macro service_mode number
    .quad .Lmode_\number
    .long .Lmode_end_\number - .Lmode_\number
    .long \number
.endm
    service_mode 1
    service_mode 2
    service_mode 3
    service_mode 4
    service_mode 5
    service_mode 6
    service_mode 7
    service_mode 8
    service_mode 9
    service_mode 10
    service_mode 11
    service_mode 20
    service_mode 21
    service_mode 22
    service_mode 30
    service_mode 31
    service_mode 32
    service_mode 33
.Lmode_1: .asciz "svc-zero"
.Lmode_end_1:
.Lmode_2: .asciz "svc-stale"
.Lmode_end_2:
.Lmode_3: .asciz "svc-window"
.Lmode_end_3:
.Lmode_4: .asciz "svc-tx"
.Lmode_end_4:
.Lmode_5: .asciz "svc-count"
.Lmode_end_5:
.Lmode_6: .asciz "svc-reply"
.Lmode_end_6:
.Lmode_7: .asciz "svc-reserved"
.Lmode_end_7:
.Lmode_8: .asciz "svc-die"
.Lmode_end_8:
.Lmode_9: .asciz "svc-spin"
.Lmode_end_9:
.Lmode_10: .asciz "svc-duplicate"
.Lmode_end_10:
.Lmode_11: .asciz "svc-block-forge"
.Lmode_end_11:
.Lmode_20: .asciz "block-zero"
.Lmode_end_20:
.Lmode_21: .asciz "block-forge"
.Lmode_end_21:
.Lmode_22: .asciz "block-reserved"
.Lmode_end_22:
.Lmode_30: .asciz "raw-quota"
.Lmode_end_30:
.Lmode_31: .asciz "raw-quota-small"
.Lmode_end_31:
.Lmode_32: .asciz "writer-stale-write"
.Lmode_end_32:
.Lmode_33: .asciz "writer-stale-flush"
.Lmode_end_33:
.endif
.section .note.GNU-stack,"",@progbits

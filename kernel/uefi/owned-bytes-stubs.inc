.section .text

// Descriptor loads/stores execute at CPL3. Only copied words cross INT 0x82.
// R10 retains the user descriptor address; the kernel never uses that address.
.macro owner_load
    mov 0(%r10), %rdi
    mov 8(%r10), %rsi
    mov 16(%r10), %rdx
    mov 24(%r10), %rcx
.endm
.macro owner_store
    mov %rdi, 0(%r10)
    mov %rsi, 8(%r10)
    mov %rdx, 16(%r10)
    mov %rcx, 24(%r10)
.endm
.global __au_runtime_bytes_allocate
.type __au_runtime_bytes_allocate,@function
__au_runtime_bytes_allocate:
    mov %rdx, %r10
    mov %rdi, %r9
    mov %rsi, %r8
    owner_load
    int $0x82
.global aurora_bytes_allocate_pc
aurora_bytes_allocate_pc:
    owner_store
    ret
.size __au_runtime_bytes_allocate,.-__au_runtime_bytes_allocate

.macro byte_accessor name, writeback=0
.global __au_runtime_bytes_\name
.type __au_runtime_bytes_\name,@function
__au_runtime_bytes_\name:
    mov %rdi, %r10
    mov %rsi, %r8
    mov %rdx, %r9
    owner_load
    int $0x82
.global aurora_bytes_\name\()_pc
aurora_bytes_\name\()_pc:
.if \writeback
    owner_store
.endif
    ret
.size __au_runtime_bytes_\name,.-__au_runtime_bytes_\name
.endm
byte_accessor borrow_length
byte_accessor at
byte_accessor set
byte_accessor resize,1
byte_accessor drop,1

// Validate through the existing copied-descriptor syscall. Construct the view
// entirely in user memory; no kernel backing pointer or new authority crosses.
.global __au_runtime_bytes_borrow_span
.type __au_runtime_bytes_borrow_span,@function
__au_runtime_bytes_borrow_span:
    push %rdi
    push %rsi
    sub $8, %rsp
    call __au_runtime_bytes_borrow_length
    add $8, %rsp
    pop %rsi
    pop %rdi
    movq $1, 0(%rsi)
    mov 0(%rdi), %rcx
    mov %rcx, 8(%rsi)
    mov 8(%rdi), %rcx
    mov %rcx, 16(%rsi)
    mov 16(%rdi), %rcx
    mov %rcx, 24(%rsi)
    mov 24(%rdi), %rcx
    mov %rcx, 32(%rsi)
    movq $0, 40(%rsi)
    mov %rax, 48(%rsi)
    ret
.size __au_runtime_bytes_borrow_span,.-__au_runtime_bytes_borrow_span

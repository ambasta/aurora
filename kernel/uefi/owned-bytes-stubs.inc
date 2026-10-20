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

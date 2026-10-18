.section .text.user_entry,"ax",@progbits
.code64
.global aurora_program_entry
aurora_program_entry:
    sub $32, %rsp
    mov %rdi, (%rsp)
    mov %rsi, 8(%rsp)
    mov %rdx, 16(%rsp)
    movq $0, 24(%rsp)
    mov %rsp, %r11
    call @aurora_user_main@
    add $32, %rsp
    int $0x81
.global aurora_program_return_pc
aurora_program_return_pc:
    ud2

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
.section .note.GNU-stack,"",@progbits

.section .text
.global __au_runtime_console_next
.type __au_runtime_console_next,@function
__au_runtime_console_next:
    mov %rdx, %r10
    int $0x82
.global aurora_console_next_pc
aurora_console_next_pc:
    mov %rax, 0(%r10)
    mov %rdx, 8(%r10)
    mov %rcx, 16(%r10)
    ret
.size __au_runtime_console_next,.-__au_runtime_console_next
.global __au_runtime_console_put
.type __au_runtime_console_put,@function
__au_runtime_console_put:
    int $0x82
.global aurora_console_put_pc
aurora_console_put_pc:
    ret
.size __au_runtime_console_put,.-__au_runtime_console_put

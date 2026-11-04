.section .text.ap_worker.traps,"ax"
.code64
/* Entry keeps startup CR3 until RIP has left the low page. RAX is the
 * permanent root, RDI the read-only request, RSP the private guarded stack. */
.global ap_worker_enter
.hidden ap_worker_enter
.type ap_worker_enter,@function
ap_worker_enter:
    mov %rax,%cr3
    call ap_worker_main
1:  cli
    hlt
    jmp 1b
.size ap_worker_enter,.-ap_worker_enter

/* All interrupts/exceptions use private IST1. No shared global trap state,
 * serial port, allocator, runtime bridge or instruction after fault publication. */
.altmacro
.macro AP_VECTOR number
.global ap_worker_vector_\number
.hidden ap_worker_vector_\number
.type ap_worker_vector_\number,@function
ap_worker_vector_\number:
.if (\number != 8) && (\number != 10) && (\number != 11) && (\number != 12) && (\number != 13) && (\number != 14) && (\number != 17) && (\number != 21) && (\number != 29) && (\number != 30)
    pushq $0
.endif
    pushq $\number
    jmp ap_worker_fault
.size ap_worker_vector_\number,.-ap_worker_vector_\number
.endm
.set vector,0
.rept 256
AP_VECTOR %vector
.set vector,vector+1
.endr
.global ap_worker_fault
.hidden ap_worker_fault
.type ap_worker_fault,@function
ap_worker_fault:
    cli
    cld
    mov $1,%eax
    xchg %rax,%gs:96          /* CPU-local terminal latch also covers nested NMI. */
    test %rax,%rax
    jne 2f
    mov (%rsp),%rax
    mov %rax,%gs:64
    mov 8(%rsp),%rax
    mov %rax,%gs:72
    mov 16(%rsp),%rax
    mov %rax,%gs:80
    mov %cr2,%rax
    mov %rax,%gs:88
    movq $3,%gs:0             /* Aligned release publication on x86 TSO. */
2:  hlt
    jmp 2b
.size ap_worker_fault,.-ap_worker_fault

/* Offsets, not absolute pointers, remain valid after payload relocation. */
.balign 4
.global ap_worker_vector_offsets
.hidden ap_worker_vector_offsets
.type ap_worker_vector_offsets,@object
ap_worker_vector_offsets:
.macro AP_OFFSET number
    .long ap_worker_vector_\number-ap_worker_vector_offsets
.endm
.set vector,0
.rept 256
AP_OFFSET %vector
.set vector,vector+1
.endr
.size ap_worker_vector_offsets,.-ap_worker_vector_offsets
.section .note.GNU-stack,"",@progbits

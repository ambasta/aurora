# Trusted host-only test adapter. Called only in a disposable fork child.
# RDI = emitted function, RSI = aligned mapped-stack top, RDX = scalar argument.
# Single-threaded child-only scratch allows restoration independently of whether
# the generated function preserved any callee-saved GPR. No signal recovers here.
.text
.globl guard_switch
.type guard_switch, @function
guard_switch:
    pushq %rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    movq %rsp, guard_saved_rsp(%rip)
    movq %rsp, guard_observed+72(%rip)
    movq %rdi, %rax
    movq %rsi, guard_observed(%rip)
    movq %rsi, %rsp
    movq %rdx, %rdi
    movabsq $0x1122334455667788, %rbp
    movabsq $0x2233445566778899, %rbx
    movabsq $0x33445566778899aa, %r12
    movabsq $0x445566778899aabb, %r13
    movabsq $0x5566778899aabbcc, %r14
    movabsq $0x66778899aabbccdd, %r15
    call *%rax
    movq %rsp, guard_observed+8(%rip)
    movq %rax, guard_observed+16(%rip)
    movq %rbp, guard_observed+24(%rip)
    movq %rbx, guard_observed+32(%rip)
    movq %r12, guard_observed+40(%rip)
    movq %r13, guard_observed+48(%rip)
    movq %r14, guard_observed+56(%rip)
    movq %r15, guard_observed+64(%rip)
    movq guard_saved_rsp(%rip), %rsp
    movq %rsp, guard_observed+80(%rip)
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    popq %rbp
    ret
.size guard_switch, .-guard_switch
.bss
.balign 8
.local guard_saved_rsp
guard_saved_rsp: .zero 8
.section .note.GNU-stack,"",@progbits

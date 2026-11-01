.ifdef AURORA_BLOCKING_CALL
.set AURORA_REGISTER_TRAP,1
.endif
.ifdef AURORA_OWNED_TEXT
.set AURORA_REGISTER_TRAP,1
.endif
.section .text
.code64
# One trap implementation, distinct symbol namespaces when both protected
# console and hosted-process supervisors are linked into production.
.macro trap_entry name
.ifdef AURORA_PROCESS_TRAPS
.global uefi_process_\name
uefi_process_\name:
.else
.global aurora_\name
aurora_\name:
.endif
.endm
.ifdef AURORA_PROCESS_TRAPS
.extern uefi_process_exception_dispatch
.extern uefi_process_leave_user
.else
.extern aurora_exception_dispatch
.extern aurora_leave_user
.endif
trap_entry exception_0
    pushq $0
    pushq $0
    jmp exception_common
trap_entry exception_1
    pushq $0
    pushq $1
    jmp exception_common
trap_entry exception_2
    pushq $0
    pushq $2
    jmp exception_common
trap_entry exception_3
    pushq $0
    pushq $3
    jmp exception_common
trap_entry exception_4
    pushq $0
    pushq $4
    jmp exception_common
trap_entry exception_5
    pushq $0
    pushq $5
    jmp exception_common
trap_entry exception_6
    pushq $0
    pushq $6
    jmp exception_common
trap_entry exception_7
    pushq $0
    pushq $7
    jmp exception_common
trap_entry exception_8
    pushq $8
    jmp exception_common
trap_entry exception_9
    pushq $0
    pushq $9
    jmp exception_common
trap_entry exception_10
    pushq $10
    jmp exception_common
trap_entry exception_11
    pushq $11
    jmp exception_common
trap_entry exception_12
    pushq $12
    jmp exception_common
trap_entry exception_13
    pushq $13
    jmp exception_common
trap_entry exception_14
    pushq $14
    jmp exception_common
trap_entry exception_15
    pushq $0
    pushq $15
    jmp exception_common
trap_entry exception_16
    pushq $0
    pushq $16
    jmp exception_common
trap_entry exception_17
    pushq $17
    jmp exception_common
trap_entry exception_18
    pushq $0
    pushq $18
    jmp exception_common
trap_entry exception_19
    pushq $0
    pushq $19
    jmp exception_common
trap_entry exception_20
    pushq $0
    pushq $20
    jmp exception_common
trap_entry exception_21
    pushq $21
    jmp exception_common
trap_entry exception_22
    pushq $0
    pushq $22
    jmp exception_common
trap_entry exception_23
    pushq $0
    pushq $23
    jmp exception_common
trap_entry exception_24
    pushq $0
    pushq $24
    jmp exception_common
trap_entry exception_25
    pushq $0
    pushq $25
    jmp exception_common
trap_entry exception_26
    pushq $0
    pushq $26
    jmp exception_common
trap_entry exception_27
    pushq $0
    pushq $27
    jmp exception_common
trap_entry exception_28
    pushq $0
    pushq $28
    jmp exception_common
trap_entry exception_29
    pushq $29
    jmp exception_common
trap_entry exception_30
    pushq $30
    jmp exception_common
trap_entry exception_31
    pushq $0
    pushq $31
    jmp exception_common
trap_entry timer_interrupt
    pushq $0
    pushq $64
    jmp exception_common
.ifdef AURORA_REGISTER_TRAP
trap_entry program_call
    pushq $0
    pushq $130
    jmp exception_common
.endif
.ifdef AURORA_PROCESS_CALL
# The process image's kernel-call gate, INT 0x83 (kernel/uefi/process.md#entries).
trap_entry process_call
    pushq $0
    pushq $131
    jmp exception_common
.endif
# The process IDT has only INT83; protected-program return gates are not
# part of that architecture and must not remain as uninstalled entry roots.
.ifndef AURORA_PROCESS_TRAPS
trap_entry program_return
    pushq $0
    pushq $129
    jmp exception_common
trap_entry user_return
    pushq $0
    pushq $128
    jmp exception_common
.endif
trap_entry unexpected_interrupt
    pushq $0
    pushq $255
exception_common:
    # Single CPU: the supervisor-only guard covers physical trap handling,
    # including calls, root changes and restoration. A fault during that work
    # may already have pushed a CPU frame and this stub's vector/error words;
    # it must not recurse into C++ on the interrupted stack.
.ifdef AURORA_PROCESS_TRAPS
    cmpb $0, uefi_process_trap_guard(%rip)
    jne uefi_process_nested_fault
    movb $1, uefi_process_trap_guard(%rip)
.else
    cmpb $0, aurora_trap_guard(%rip)
    jne aurora_nested_fault
    movb $1, aurora_trap_guard(%rip)
.endif
    cld
    push %rax
    push %rbx
    push %rcx
    push %rdx
    push %rbp
    push %rsi
    push %rdi
    push %r8
    push %r9
    push %r10
    push %r11
    push %r12
    push %r13
    push %r14
    push %r15
    mov 120(%rsp), %rdi
    mov 128(%rsp), %rsi
    mov 136(%rsp), %rdx
    mov 144(%rsp), %rcx
    mov %rsp, %r8
    mov 112(%rsp), %r9
    mov %rsp, %rbx
    and $-16, %rsp
    # RCX is the original CS at word 18 of the normalized trap frame.
    # Keep the physical kernel-origin path separate from user policy calls.
    test $3, %cl
    jz kernel_origin_dispatch
.ifdef AURORA_PROCESS_TRAPS
    call uefi_process_exception_dispatch
.else
    call aurora_exception_dispatch
.endif
    jmp dispatch_complete
kernel_origin_dispatch:
.ifdef AURORA_PROCESS_TRAPS
    call uefi_process_kernel_exception_dispatch
.else
.ifdef AURORA_RELATIVE_ONLY
    call aurora_kernel_exception_dispatch
.else
    # BIOS retains its existing combined dispatcher; both physical origins
    # receive that complete bound. UEFI supplies the separate kernel adapter.
    call aurora_exception_dispatch
.endif
.endif
dispatch_complete:
    cmp $1, %rax
.ifdef AURORA_PROCESS_TRAPS
    je uefi_process_leave_user
.else
    je aurora_leave_user
.endif
    mov %rbx, %rsp
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %r11
    pop %r10
    pop %r9
    pop %r8
    pop %rdi
    pop %rsi
    pop %rbp
    pop %rdx
    pop %rcx
    pop %rbx
    pop %rax
    add $16, %rsp
    # All registers are restored. Only the hardware return frame remains.
.ifdef AURORA_PROCESS_TRAPS
    movb $0, uefi_process_trap_guard(%rip)
.else
    movb $0, aurora_trap_guard(%rip)
.endif
    iretq
# Emergency recursion is terminal, including if debug-exit is absent. There
# are no calls, pushes, formatting, cleanup, or memory accesses here.
trap_entry nested_fault
    cli
    mov $0xf4, %dx
    mov $0x11, %al
    out %al, %dx
1:  hlt
    jmp 1b
trap_entry breakpoint_probe
    push %rbx
    push %rbp
    push %r12
    push %r13
    push %r14
    push %r15
    mov $17, %rax
    mov $34, %rbx
    mov $51, %rcx
    mov $68, %rdx
    mov $85, %rbp
    mov $102, %rsi
    mov $119, %rdi
    mov $136, %r8
    mov $153, %r9
    mov $170, %r10
    mov $187, %r11
    mov $204, %r12
    mov $221, %r13
    mov $238, %r14
    mov $255, %r15
    std
    int3
    cmp $17, %rax
    jne probe_failed
    cmp $34, %rbx
    jne probe_failed
    cmp $51, %rcx
    jne probe_failed
    cmp $68, %rdx
    jne probe_failed
    cmp $85, %rbp
    jne probe_failed
    cmp $102, %rsi
    jne probe_failed
    cmp $119, %rdi
    jne probe_failed
    cmp $136, %r8
    jne probe_failed
    cmp $153, %r9
    jne probe_failed
    cmp $170, %r10
    jne probe_failed
    cmp $187, %r11
    jne probe_failed
    cmp $204, %r12
    jne probe_failed
    cmp $221, %r13
    jne probe_failed
    cmp $238, %r14
    jne probe_failed
    cmp $255, %r15
    jne probe_failed
    pushfq
    pop %rax
    cld
    test $0x400, %rax
    jz probe_failed
    mov $1, %eax
    jmp probe_done
probe_failed:
    cld
    xor %eax, %eax
probe_done:
    pop %r15
    pop %r14
    pop %r13
    pop %r12
    pop %rbp
    pop %rbx
    ret
.ifndef AURORA_RELATIVE_ONLY
.section .rodata
trap_entry exception_vectors
    .quad aurora_exception_0
    .quad aurora_exception_1
    .quad aurora_exception_2
    .quad aurora_exception_3
    .quad aurora_exception_4
    .quad aurora_exception_5
    .quad aurora_exception_6
    .quad aurora_exception_7
    .quad aurora_exception_8
    .quad aurora_exception_9
    .quad aurora_exception_10
    .quad aurora_exception_11
    .quad aurora_exception_12
    .quad aurora_exception_13
    .quad aurora_exception_14
    .quad aurora_exception_15
    .quad aurora_exception_16
    .quad aurora_exception_17
    .quad aurora_exception_18
    .quad aurora_exception_19
    .quad aurora_exception_20
    .quad aurora_exception_21
    .quad aurora_exception_22
    .quad aurora_exception_23
    .quad aurora_exception_24
    .quad aurora_exception_25
    .quad aurora_exception_26
    .quad aurora_exception_27
    .quad aurora_exception_28
    .quad aurora_exception_29
    .quad aurora_exception_30
    .quad aurora_exception_31
.endif
.section .bss
.balign 8
trap_entry trap_guard
    .byte 0
.ifdef AURORA_PROCESS_TRAPS
.type uefi_process_trap_guard,@object
.size uefi_process_trap_guard,1
.hidden uefi_process_trap_guard
.else
.type aurora_trap_guard,@object
.size aurora_trap_guard,1
.hidden aurora_trap_guard
.endif
.section .note.GNU-stack,"",@progbits

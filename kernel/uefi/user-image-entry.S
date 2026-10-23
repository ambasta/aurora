.section .text.user_entry,"ax"
.code64
.global aurora_program_entry
.global aurora_program_return_pc
aurora_program_entry:
    or %rbx,%rax
    or %rcx,%rax
    or %rdx,%rax
    or %rbp,%rax
    or %rsi,%rax
.ifndef UEFI_USER_PROBES
    or %rdi,%rax
.endif
    or %r8,%rax
    or %r9,%rax
    or %r10,%rax
    or %r11,%rax
    or %r12,%rax
    or %r13,%rax
    or %r14,%rax
    or %r15,%rax
    jnz bad_entry
    cmpq $0,-8(%rsp)
    jne bad_entry
.ifdef UEFI_USER_PROBES
    # runtime-fixture: %rdi selects one hostile probe, in the kernel's order;
    # zero runs the program. Every probe ends in ud2 and never falls through.
    cmp $1,%rdi
    je probe_code
    cmp $2,%rdi
    je probe_stack
    cmp $3,%rdi
    je probe_kernel
    cmp $4,%rdi
    je probe_window
    cmp $5,%rdi
    je probe_write
    cmp $6,%rdi
    je probe_nx
    cmp $7,%rdi
    je probe_return
    cmp $8,%rdi
    je aurora_probe_unknown_pc
    cmp $9,%rdi
    je aurora_probe_syscall_pc
    cmp $10,%rdi
    je aurora_probe_sysenter_pc
    test %rdi,%rdi
    jnz bad_entry
.endif
.ifdef UEFI_USER_MULTIPAGE_FAULT
    mov $1,%edi
.endif
    call aurora_user_main
    int $0x81
aurora_program_return_pc:
    ud2
bad_entry:
    ud2
.ifdef UEFI_USER_PROBES
probe_code:
    movabs $0x10000004000,%rax
    call *%rax
    ud2
probe_stack:
    movabs $0x10000400000,%rax
.global aurora_probe_stack_pc
aurora_probe_stack_pc:
    mov (%rax),%al
    ud2
probe_kernel:
    mov aurora_kernel_probe_target(%rip),%rax
.global aurora_probe_kernel_pc
aurora_probe_kernel_pc:
    mov (%rax),%al
    ud2
probe_window:
    movabs $0xffff800000000000,%rax
.global aurora_probe_window_pc
aurora_probe_window_pc:
    mov (%rax),%al
    ud2
probe_write:
    movabs $0x10000000000,%rax
.global aurora_probe_write_pc
aurora_probe_write_pc:
    movb $0,(%rax)
    ud2
probe_nx:
    movb $0xc3,-8(%rsp)
    lea -8(%rsp),%rax
    call *%rax
    ud2
probe_return:
    mov $42,%eax
    int $0x81
.global aurora_probe_return_pc
aurora_probe_return_pc:
    ud2
.global aurora_probe_unknown_pc
aurora_probe_unknown_pc:
    ud2
.global aurora_probe_syscall_pc
aurora_probe_syscall_pc:
    syscall
    ud2
.global aurora_probe_sysenter_pc
aurora_probe_sysenter_pc:
    sysenter
    ud2
.set UEFI_USER_KERNEL,1
.endif
.ifdef UEFI_USER_KERNEL
.balign 8
.global aurora_kernel_probe_target
aurora_kernel_probe_target:
    .quad 0
.endif
.section .note.GNU-stack,"",@progbits

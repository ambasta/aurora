# A process-image program (kernel/uefi/process.md#guest-rows) that recurses
# without bound: each call pushes a return address until the stack reaches its
# unmapped guard page, where the kernel ends the process with stack_guard.
# GNU as, because the compiler rejects recursion reachable from a HostFiles main.
.text
.globl _start
_start:
    call _start
    ud2
.section .note.GNU-stack,"",@progbits

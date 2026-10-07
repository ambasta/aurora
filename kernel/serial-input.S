/* Opt-in BIOS console only. IRQ4 wakes the halted kernel; it never handles data.
 * All interrupted state is preserved. No C++ call or mutable shared state. */
.section .text
.code64
.global aurora_serial_interrupt
aurora_serial_interrupt:
    push %rax
    mov $0x20, %al
    out %al, $0x20
    pop %rax
    iretq
.section .note.GNU-stack,"",@progbits

.section .text.entry,"ax"
.global uefi_payload_entry
uefi_payload_entry:
    cld
    call uefi_payload_main
1:  cli
    hlt
    jmp 1b
.section .text
.global uefi_payload_fault
uefi_payload_fault:
    mov $255, %edi
    xor %esi, %esi
    xor %edx, %edx
    jmp fault_common
.global uefi_payload_page_fault
uefi_payload_page_fault:
    mov $14, %edi
    mov (%rsp), %rsi
    mov 8(%rsp), %rdx
fault_common:
    cmpb $0, uefi_payload_trap_guard(%rip)
    jne uefi_payload_nested_fault
    movb $1, uefi_payload_trap_guard(%rip)
    cld
    and $-16, %rsp
    call uefi_payload_fail
    jmp 1b
.global uefi_payload_nested_fault
.hidden uefi_payload_nested_fault
uefi_payload_nested_fault:
    cli
    mov $0xf4, %dx
    mov $0x11, %al
    out %al, %dx
2:  hlt
    jmp 2b
.section .bss
.balign 8
.global uefi_payload_trap_guard
.hidden uefi_payload_trap_guard
.type uefi_payload_trap_guard,@object
uefi_payload_trap_guard:
    .byte 0
.size uefi_payload_trap_guard,1
.section .note.GNU-stack,"",@progbits

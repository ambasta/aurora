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
    cld
    and $-16, %rsp
    call uefi_payload_fail
    jmp 1b
.section .note.GNU-stack,"",@progbits

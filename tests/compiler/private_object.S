.text
.globl aurora_hosted_private_object_test
.hidden aurora_hosted_private_object_test
.type aurora_hosted_private_object_test,@function
aurora_hosted_private_object_test:
    call object_loop
    cmp $21, %rax
    jne .Lfailed
    call object_six_arguments
    cmp $21, %rax
    jne .Lfailed
    call object_literal
    cmp $127, %rax
    jne .Lfailed
    xor %edi, %edi
    jmp .Lexit
.Lfailed:
    mov $1, %edi
.Lexit:
    mov $60, %eax
    syscall
.size aurora_hosted_private_object_test, .-aurora_hosted_private_object_test
.section .note.GNU-stack,"",@progbits

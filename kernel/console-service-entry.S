# BIOS uses the same sealed synchronous console record as the UEFI session.
# Source declarations select compiler ABI facts; no symbol recipe is duplicated.
.text
.global __au_runtime_console_entry
.hidden __au_runtime_console_entry
.type __au_runtime_console_entry,@function
__au_runtime_console_entry:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call @console_service@
    leave
    ret
.size __au_runtime_console_entry,.-__au_runtime_console_entry

# Preserve the existing BIOS self-test and terminal-event bootstrap exports.
# No other source functions or imported library helpers become public.
.global aurora_kernel_value
.global aurora_kernel_terminal_event

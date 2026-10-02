OUTPUT_FORMAT(elf64-x86-64)
ENTRY(aurora_program_entry)
PHDRS { code PT_LOAD FLAGS(5); }
SECTIONS {
    . = USER_BASE;
    .text : { KEEP(*(.text.user_entry)) *(.text .text.*) *(.rodata .rodata.*) } :code
    .data : { *(.data .data.*) } :code
    .bss : { *(.bss .bss.*) *(COMMON) } :code
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "user images must not contain writable global storage")
    ASSERT(. - USER_BASE <= 4096, "controlled user image exceeds one page")
    /DISCARD/ : { *(.eh_frame*) *(.comment*) *(.note*) }
}

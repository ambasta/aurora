OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { code PT_LOAD FLAGS(5); rodata PT_LOAD FLAGS(4); data PT_LOAD FLAGS(6); }
SECTIONS {
    . = 0x10000;
    __text_begin = .;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) } :code
    . = ALIGN(4096);
    __text_end = .;
    __read_begin = .;
    .rodata : { *(.rodata .rodata.*) } :rodata
    . = ALIGN(4096);
    __read_end = .;
    __write_begin = .;
    .data : { *(.data .data.*) } :data
    __bss_start = .;
    .bss : { *(.bss .bss.*) *(COMMON) } :data
    __bss_end = .;
    . = ALIGN(4096);
    __write_end = .;
    ASSERT(__write_end < 0x70000, "kernel overlaps reserved protected stacks")
    /DISCARD/ : { *(.eh_frame*) *(.comment*) *(.note*) }
}

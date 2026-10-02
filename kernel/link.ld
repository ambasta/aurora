OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { code PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
    . = 0x10000;
    .text : { KEEP(*(.text.entry)) *(.text .text.*) } :code
    .rodata : { *(.rodata .rodata.*) } :code
    . = ALIGN(4096);
    .data : { *(.data .data.*) } :data
    __bss_start = .;
    .bss : { *(.bss .bss.*) *(COMMON) } :data
    __bss_end = .;
    ASSERT(__bss_end < 0x80000, "kernel overlaps reserved bootstrap stack")
    /DISCARD/ : { *(.eh_frame*) *(.comment*) *(.note*) }
}

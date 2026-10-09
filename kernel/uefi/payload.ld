ENTRY(uefi_payload_entry)
PHDRS { text PT_LOAD FLAGS(5); read PT_LOAD FLAGS(4); data PT_LOAD FLAGS(6); }
SECTIONS {
 . = 0;
 .text : { *(.text.entry) *(.text .text.*) } :text
 . = ALIGN(4096); __payload_text_end = .;
 .rodata : { *(.rodata .rodata.*) } :read
 . = ALIGN(4096); __payload_read_end = .;
 .data : { *(.data .data.*) } :data
 .bss : { *(SORT_BY_ALIGNMENT(.bss.*) SORT_BY_ALIGNMENT(.bss)) *(COMMON) } :data
 . = ALIGN(4096); __payload_memory_end = .;
 /DISCARD/ : { *(.eh_frame*) *(.comment*) *(.note*) *(.got*) }
 ASSERT(. <= 0x20000, "UEFI payload exceeds reserved range")
}

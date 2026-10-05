/* The BIOS executes these exact 512 bytes at physical 0x7c00. Host ELF notes
   are metadata, never payload; unexpected runtime sections must fail closed. */
OUTPUT_FORMAT(binary)
ENTRY(_boot)
SECTIONS {
    . = 0x7c00;
    .text : { *(.text) }
    ASSERT(_boot == 0x7c00, "boot entry must be the first BIOS byte")
    ASSERT(SIZEOF(.text) == 512, "boot text must be exactly one BIOS sector")
    .data : { *(.data .data.*) }
    .bss : { *(.bss .bss.*) *(COMMON) }
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0,
           "boot sector must not contain separate writable storage")
    /DISCARD/ : { *(.note.gnu.property) *(.note.gnu.build-id) *(.note.GNU-stack)
                   *(.gnu.build.attributes) *(.gnu.build.attributes.*) *(.comment) }
}

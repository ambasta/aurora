# Canonical text transport correction

The earlier integrated full-target receipts describe the binary fixture path at
that time. Original creation/read/native receipts remain unchanged. This later
representation change preserves the original raw file outside the main
tree and decodes the unchanged canonical hex source instead. No new mkfs or
Aurora compiler/library semantics change occurred.

The decoder bounds reads to1729 bytes and requires exact length1728,32 canonical
rows,16 two-digit byte cells per row and exact ordered offsets. It checks both
transport and decoded raw SHA256. Seventeen explicit rejection controls pass
normal and optimized Python;15 native observations pass release, optimized-Python
release and fatal ASan/UBSan compiler. Compiler pins and commands are in receipts.
Independent harness review passed:17,604 extra corner checks in each Python
mode,17 rejection controls normal/-O, and15 native observations with both
compiler pins under both modes. See independent-review.md and adjacent receipts.

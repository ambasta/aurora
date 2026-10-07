# Kernel owned-byte allocation results

Status: focused CPU-only kernel integration checkpoint.

The source was rebased from the paused PR69 candidate onto merged PR74, with
all 806 base source files verified against tree
`ef499742e3bea9ee2df2cccb268d219ea4e1d032`. The reused compiler SHA-256 is
`6756e670ccfd2dc1d94a48672915852697ab2ec08df0c09da471e37491f8afc5`.
The compiler, hosted implementation and PhysicalPages allocator are unchanged.

Focused acceptance:

- Independent adapter/bridge/shared-ABI source review found no production defect.
- The first compile-only admission rejected the paused bridge's bare entry name.
  Its log and all objects remain preserved. The corrected exact local mangled
  entry linked and passed PE32+ relocation/RX, PIC and 14 negative image checks.
- The shared-header extraction passed the existing hosted adapter suite:
  53,969 checks and 68 isolated traps, including real resize behavior.
- The completed kernel host suite passed 483,187 checks and 239 exact isolated
  faults in both normal and fatal ASan/UBSan modes, with leak detection excluded.
  It covers 70 descriptor/authority faults, 16 bounds faults and 153 retained-state
  faults. Every initialization/drop page and all 120 nonempty rollback-prefix
  corruption positions are covered. Independent review found no false-pass defect.
  The first launch stopped before compilation because an optional timing tool was
  missing; that log is retained. The replay uses Bash timing. Two pre-execution
  fixtures were corrected: an out-of-contract maximum quota and a 65,535-byte
  owner that consumes all sixteen pages, leaving room only for an empty second owner.
- Both Python modes passed nine positive/184 negative transcript controls,
  15 clock-contract tests and one positive/20 negative object-import controls.
  The initial clock control failure retained an old 140-mode shell-plan count;
  the corrected 141-mode count includes the new separately selected profile.
- Both Python modes compiled an unsupported resize fixture and rejected its exact
  import and actual unresolved ELF link. An extra scalar graph also failed the
  actual duplicate-reflection-helper link. These are compile-only negative tests.

All seven compared ordinary UEFI artifacts (ELF, PE, assembly and metadata) are
byte-identical to the PR74 baseline with the same compiler, including after
formatting the touched source. Exact linked closure is 1,072 bytes plus the
512-byte fault reserve, for 1,584 bytes against the 15,360-byte admission cap in the unchanged 16 KiB stack. The
decoded synchronous fault path is 159 bytes. Both Python modes independently
passed six positive/48 negative proof controls and reproduced identical linked
receipts. Independent source, host-evidence and compile-only review accepted
the candidate with no remaining blocker. The final mandatory-gated image build
retains identical ELF/PE/payload/assembly bytes.

Actual QEMU/OVMF gates passed through the existing public smoke launcher:

- `owned-bytes`: runtime lengths 65, 513 and 4,097; two live owners; two, two and
  four real leased pages; six successful allocations and six releases; closed
  grant with zero used bytes/pages. Whole-page poison/readback and compiler-driven
  moves/cleanup passed in the guest.
- `normal`: a subsequent real normal UEFI boot passed after automatic image
  restoration. Restored ELF/PE/assembly/image metadata match the original PR74
  normal baseline byte-for-byte after both guest steps.

The owned-byte guest's complete linked receipt is identical to the final admitted
image receipt. The QEMU executable SHA-256 is
`d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`;
the OVMF ROM SHA-256 is
`14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`.
The original TCG clock, 128 MiB emulated RAM, existing public smoke launcher
and profile-appropriate validators were used. The guest pair took 5.59 and 3.32 seconds including their image builds;
those timings are observations, not a performance comparison.

Final documentation updates do not alter compiler, adapter, image or gate code.
No full native/emulator aggregate, physical hardware, resize-in-kernel, userspace
allocator or device activation is claimed.

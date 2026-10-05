# Checked readonly byte-window integration results

Date: 2026-10-05. Fresh compiler, complete native aggregate and all170+2 actual
emulator gates passed, followed by independent terminal/retained-validator review.
Publication is a separate action. This record describes a bounded language feature.

## Implemented boundary

Named readonly byte spans can create `.subspan(i64 offset, i64 count)` children.
Both expressions evaluate once, left to right, before bounds checks. Unsigned
offset comparison precedes subtraction and count comparison; payload address
adjustment follows both checks. Empty endpoint views retain root/direct-parent
borrow authority and cannot be read or widened. Exact typed spills, static
creation-site identity and dependent-child-before-parent release preserve the
existing lexical/call-only boundary. Ordinary class methods named subspan and
ordinary overloads retain their meaning. Existing single-span library APIs are
unchanged. See [the complete contract](../compiler/READONLY-WINDOWS.md).

## Exact source and compiler chain

- Integration base: PR22 main `3d85ef4ec24fa7f879106f1803df0931d9b386f4`, tree
  `4687cf171d1098349c46bee7158b90ff85719d82`; its535-file source checkpoint was
  independently reviewed after a separate native/all170+2 kernel pass.
- Reviewed isolated window source:532 files. The14-path window delta had no
  implementation conflict with that kernel checkpoint; only README/matrix shared
  edits were reconciled, preserving the full kernel text plus exact window suffixes.
- Tested combined source:540 files; manifest `11d804796114f1e0bdf8f6fc1a51db7db170cfeb509d42e7328ed6abe321782c`.
- Fresh release compiler: `b3c8d58565844e1b671d1589975985374b17387b405543e05762631b95552580`.
- Isolated fatal ASan/UBSan compiler: `697874667bbf9ca024e30c79e89d8ce63fcbddaf5df1c176eec3540e7121c1df`.
- Fresh build terminal: `50ae4ba21555d3247a719149eb21dec275b566b54acfe0ebaddafbb664f1a127`.
- Full native terminal: `0f4df6ecd6080fab53dc257f73b701a4d4efa850a571e6e56bd0881abc556611`.
- Emulator terminal: `60100263b54dd87804d553b2f82cc884f9cdb96133211d61ed6cebb7d2ed3c46`.

The final source-only checkpoint changes result documentation and adds this
record plus the evidence index. Every compiler, test, library, kernel, fixture,
launcher and source example remains byte/mode-identical to the tested freeze.
The separately sealed final source manifest/archive identifies those later docs.
The source archive is a complete declared source subset, not a replacement for
all historical files in the remote Git tree. Publication must preserve unlisted
paths and recheck the remote base.

## Verification

1. Complete isolated release and fatal host ASan/UBSan compiler targets passed.
   Independent provenance review additionally exercised source/native lifetimes,
   handwritten malformed IR, spill boundaries, joins/loops, exact bounds traps,
   evaluation order and mixed scalar/span/class call arrangements. The independent
   report hash is `bb4c6d05d911561c7a6aec1fc4312b7a30539d95f8ded86df8f2022be2937562`; it matches
   the sealed compiler capsule.
2. Fresh combined `make --jobs=1 test` passed with all seven compiler SHA options
   explicitly set to the new release pin and all four512MiB inner guards unchanged.
   The29 top-level dependency targets include the readonly-window source/IR/native
   recipe, existing compiler/library/module/semantics suites, host kernel checks,
   package identity/manifest/graph and the real Aurora interrupt-budget policy.
   The window recipe recorded132 native cases/66 exact traps/21 source rejections,
   seven accepted/25 rejected direct-IR cases, and312 native direct-IR cases with
   290 exact bounds traps. These corpora overlap other review corpora and are not
   additive proof counts.
3. Native independent review verified all21,458 generated records, the5.4GB
   declared input closure, all314 package archives and raw package observations,
   plus104,120 policy and815,301 decoder vectors and ten rejection controls.
   Review: `37a69e2727ebd65afb839bf63d6be76e152b0fa80158a66786999019d9ea6d2a`.
4. All170 fresh modes passed:37 BIOS,115 ordinary UEFI, seven BAR and eleven IVRS.
   Two additional normal BIOS/UEFI builds and actual boots both exited33 and
   restored normal images. No historical mode prefix or compiler-only pass was
   reused as this run's acceptance. The output-fault image matched the unchanged
   reviewed linked-image bytes before QEMU.
5. Independent final review checked all172 retained serial validators, all18
   BAR/IVRS trace/provenance runs, stack/PE/ELF records, the complete1,207-path seal,
   source/host/runtime continuity, all21,453 native-original archive members,
   final image identities and the closed lease. Review:
   `5d4c002b26502e82c556ba36149c060a8824099b236266e7773df2d9e5c1bb81`.

The original native build is archived byte/mode/path-exact before emulator
overwrites. All raw serial results, expected QEMU statuses, validators, normal
restoration and input identities are retained. The exact
[receipt index](evidence/readonly-windows/receipts.json) identifies the chain.

## Firmware, resources and preserved qualifications

Qualified replacement CODE:
`24b30416142749dd60ac241fe755df6232fc5b10663a8b799501659b796d0268`.
Pristine VARS:
`5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e`.
This is the already qualified replacement; it is not historical bit-reproducible
firmware recovery or physical-platform qualification.

The admitted three-root cap was4GiB with64MiB reserve, a1GiB filesystem floor and
a separate3GiB reservation for unresolved old work. Native growth was768MiB with
a90-minute deadline. The measured emulator worst-case projection was2,469,717,730
bytes; terminal charged allocation was1,149,054,976 bytes, with23,347,388,416 free.
Sampled resource observations are not continuous historical upper-bound proofs.
No external live compaction or global descriptor scan was used. Existing reviewed
test-internal successful-output retirement remains disclosed in native review.

The first source-only materialization lacked preventive destination-ancestor and
pre-write allocation checks. Independent audit verified exact final source,
archive, non-symlink ancestor and bounded allocation state; future script guards
were corrected. Later checks do not retroactively supply those pre-run checks.
No product defect or out-of-scope write was established. Earlier isolated failed,
interrupted or rejected attempts are preserved and receive no pass credit. The
old unresolved kernel namespace/fence was never modified or declared closed.

Leak checking is unavailable under the traced host environment; address and
undefined-behavior sanitizer findings were fatal in the isolated compiler gates.
The combined chain is fresh release/native/emulator evidence, not a new combined
sanitizer run. No mutable/returned/heap view, C ABI, new kernel mechanism, general
stack/resource or Rust-equivalent safety proof, physical AMD support or measured
equivalent-C performance follows. General ownership, self-hosting, device drivers
and a complete operating-system distribution remain future work.

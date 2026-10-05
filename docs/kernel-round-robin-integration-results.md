# Aurora two-slot policy and short-circuit integration results

Date: 2026-10-05. The fresh combined compiler, all 45 focused commands, complete
native aggregate and all **178 actual emulator executions** passed. Independent
native/corpus, linked-image/stack and final retained-trace reviews passed.
Publication is a separate action; this record does not claim that PR26 is merged.

## Running mechanism and authority

The real two-client UEFI `Dispatcher::select` path now asks
`kernel::round_robin_next` for a copied class/enum decision. Cursor 0/1 and mask
0..3 are checked before arithmetic; invalid input is recoverably rejected. Idle
preserves the cursor. Two continuously eligible clients alternate. The private
packed-scalar bootstrap transport is validated before any authority-bearing
mutation. C++ still builds eligibility from retained live state, validates the
actual mailbox receive and commits only afterward. Frames, domains, epochs,
capabilities, hardware and assembly entry/return remain trusted bootstrap code.
The BIOS three-task scheduler is unchanged. See the [policy contract](kernel-round-robin-contract.md).

The combined source also includes independently reviewed exact-bool `&&`/`||`:
C++ precedence, left-to-right evaluation, lazy runtime RHS and mandatory full
static checking of both operands. Exact typed stack/guard joins and an emitted
stack-depth certificate preserve the unchanged x86 backend's call alignment.
Per-function limits are 65,536 retained block states and 262,144 retained operand
Values; they are not whole-compiler memory/time bounds. See the
[language contract](../compiler/SHORT-CIRCUIT.md).

The BIOS-only Aurora root retains the exact prior value/ownership probe while
excluding unused UEFI policy graphs. It composes with accepted PR24 boot-sector
layout and PR25 127-sector transport fixes; it does not replace either fix.
No unsafe Aurora escape, raw pointer, C ABI, heap interface, physical-device
operation or host bootloader change was introduced.

## Exact source and compiler chain

- Accepted publication base: PR25 main `c2deb1d3319fa9f590f5ccacbddab972d4ad8774`,
  tree `dfe6f7748f752f7d5366fdb431adb2712b712684`.
- Tested combined source: **566 files**, manifest
  `f8aec37b518c2dc9ccfe0ba95b35055b06bbc3e01fa10d2295348abcd2de9366`.
- Tested source archive:
  `637f518c26b5d52009825635aad815056e35893471ff47e9713278bc031d9518`.
- Fresh release compiler:
  `66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
- Focused terminal:
  `1f687b5f60cfb48748e094e3940633f151f533caec784c9ab0c162dc33726fe9`.
- Complete native terminal:
  `86ae24ffa1b0b60a02665c460db22ff98599c1760d90e93eade9ec48d86baae0`.
- Complete emulator terminal:
  `8ddaecd8bfe03f13d201da57cc6667a190e60a800c70803e15b7d16623ab8e02`.

Finalization updates six result-documentation files and adds this record plus
an evidence index and receipt map. The separate final source manifest/archive
identifies those later documents. All 560 other tested files and their modes,
including every compiler, library, kernel, fixture, test and launcher, remain
unchanged. The source-only archive is the declared source subset, not a replacement
for all historical files in the remote Git tree. Publication must preserve
unlisted paths and recheck the existing PR26 head.

## Verification

1. The isolated short-circuit compiler passed complete release and fatal host
   ASan/UBSan targets, then independent source/IR/native and final sanitizer audits.
   The sanitizer compiler was
   `5ff9115b5c35818dd0be0e9e4645b14ca18ab804c497ed34f131aaff71acca73`.
   **LeakSanitizer was disabled because of executor ptrace limitations.** The
   large IR translation unit retained the documented `-O1 -g1` sanitizer build;
   ASan/UBSan diagnostics remained fatal. This is neither a leak-clean result nor
   a whole-kernel sanitizer run. The reviewed compiler implementation bytes were
   preserved when composing the fresh combined release build.
2. The fresh 45-command focused stage covered compiler identity, the BIOS graph,
   ordinary/optimized boot-layout and capacity/configuration checks, independent
   native oracles, copies, negative source/IR cases, decoder boundaries and linked
   output-fault images. The copied decision is 24 bytes, aligned to 8; the generated
   selection chain uses 304 bytes including its initial return address.
   Conservative reviewed stack bounds are 14,815/16,384 bytes for bootstrap with
   one early diagnostic, 1,575/1,511 for dispatcher/budget RSP0 paths and 1,903/1,743
   for their drain paths. These do not cover arbitrary NMI nesting or recursive faults.
3. A single fresh `make --jobs=1 test` completed all 33 root targets, 34 recipe
   markers and 31 compiler scripts. Its exact 19-argument invocation supplies
   seven external compiler-hash options, four explicit compiler paths and all five
   1024 MiB aggregate caps. Focused 128/256 MiB defaults and process/file/source
   limits remain unchanged. Both ordinary and optimized configuration checks ran,
   without substituting configuration-only output for native acceptance.
4. Independent native review verified all 26,588 generated records and source,
   tool, retained-input, admission, seal and closed-lease continuity. It performed
   59,346 corpus checks and reopened 314 package archives containing 8,792 members
   and 908,173,319 expanded bytes. Round-robin evidence includes 17,672 policy and
   1,051,016 decoder vectors, ten source rejections and 4,096 copy repetitions.
   Existing interrupt-budget evidence includes 104,120 policy and 815,301 decoder
   vectors plus ten rejections. These overlapping finite corpora are not additive
   safety proofs. The current short-circuit recipe recorded 320 source fixtures /
   360 executions, 40 negative fixtures with absent/preserved-output checks,
   15 source traps, 13 accepted/35 rejected direct-IR controls, 904 native
   value/effect cases and 16 required-RHS traps.
5. All **173 unique production modes** passed: 37 BIOS, 118 ordinary UEFI, seven
   BAR and eleven IVRS. Both rebuilt output-fault images matched their qualified
   five-member maps immediately before QEMU. The new cursor, mask and runtime
   output-corruption dispatcher modes each exited 35 at the expected decoder
   failure after both real client submissions, before successful selection,
   service or a timer interrupt event. This verifies real runtime decoder traversal,
   not a constant-folded unconditional failure.
6. Three additional actual BIOS capacity probes passed their expected outcomes:
   full 127-sector transfer exited 33; the old-96 and corrupted-final-sector
   controls exited 35 with their distinct retained sentinel observations. Two
   additional normal BIOS/UEFI builds and actual boots both exited 33 and restored
   normal images. Thus the count is **173 + 3 + 2 = 178 executions**.
7. Independent final review replayed all 173 production transcript validators,
   18 BAR/IVRS trace/provenance checks, stack calculations, the three capacity
   probes and both normal restorations. It checked the 1,240-path evidence seal,
   both linked guards, final PE/ELF/image identities, all source/host/runtime pins,
   strict cleanup and the closed lease. The original native build was archived
   before any emulator overwrite; all 26,583 archive entries and 554,202,846
   logical bytes were reverified. Final review:
   `88c6aebb2e86ece4ec22f38fd8727a7ab998b2b7cbd39c434c663b5d372a555f`.

The [receipt map](evidence/round-robin-policy/receipts.json) binds the exact chain.
The restored local BIOS image contains a 512-byte sector and 45,808-byte kernel;
this host-specific size is not a promised size for other GCC versions.

## Resources, portability and limits

The outer admitted cap was 4 GiB, with a 64 MiB reserve, 1 GiB free-space floor and
separate 3 GiB old-work reservation. Native execution stayed within its 90-minute
bound. The emulator's conservative no-compaction projection was 2,707,408,636 bytes;
its final charged allocation before the terminal write was 1,036,271,616 bytes,
with 19,208,585,216 bytes free. Sampled peaks are not continuous maximum proofs.
All originals were retained; no external live compaction or global descriptor
scan was used. Existing native harnesses' verified successful-batch archive and
retirement behavior remains part of their disclosed contract.

The package harnesses repeatedly scan the entire retained candidate for storage
accounting before and after each subprocess. This is a concrete source of test
harness overhead. The closed identity phase took 26m19s versus 7m36s in the earlier
readonly-window run, but those aggregate timings do not isolate compiler cost.
A separately reviewed accounting improvement and controlled compiler comparison
remain follow-up work; no measured compiler regression or speed-equivalence claim
is made.

On 2026-10-05 the user reported that the PR25 Gentoo GCC 16.2.1/binutils 2.47
rebuild succeeded. This is a user-reported build result, not an independently
observed new log, boot or physical-device qualification. QEMU and qualified
fixture firmware remain the execution platform for this checkpoint.

Acceptance commands explicitly supplied the reviewed compiler pin. Older public
reference-hash defaults remain a known `make test` portability gap across valid
host GCC builds. The separate developer/strict-acceptance workflow is not included
or credited in this checkpoint. Configured acceptance does not solve that gap.

## Preserved failures and corrections

- An early copy fixture used logical OR before that syntax was supported by the
  then-accepted compiler. The corrected author replay passed; the old failure is
  unchanged and does not describe the final compiler's language surface.
- The independent host `-O0` IR scanner exceeded its 32 MiB file cap after 17
  commands. A separately admitted `-O1` scanner completed the remaining three
  checks with identical generated assembly. This is explicit historical 17+3
  coverage, not a relabeled clean 20-command run.
- The first combined full native aggregate failed the real BIOS size gate:
  unused UEFI selection code crossed an alignment boundary, growing the payload
  to 49,904 bytes, 752 bytes beyond the old 96-sector budget. A BIOS-only root
  removed unused graphs. Separately measured Gentoo growth required PR25's
  audited 127-sector transport. Neither correction changes the failed receipt.
- The isolated compiler release-v1 wrapper rejected an offline-XFS fixture output
  outside its controlled temporary tree. The narrow TMPDIR fix was independently
  reviewed; complete v2 release/sanitizer runs supplied fresh coverage.
- A later aggregate packet was blocked **before child execution** because three
  package cap parsers rejected its requested 1024 MiB limit. The fresh test-only
  repair consistently bounds all five consumers at 1024 MiB, keeps focused
  defaults and verifies wrong-cap/no-output/configuration-only behavior. The
  blocked packet is neither an executed failure nor a passed aggregate.
- Independent emulator preparation exceeded its original 32 MiB allowance by
  110,592 bytes. Writes paused, fixtures were preserved and an explicit 36 MiB
  preparation allowance was approved. Later read-only terminal audit output had
  a separate 8 MiB allowance. A preparation measurement that overlapped launch
  counted the newly admitted run's metadata; its failed diagnostic was retained
  and the preparation-only scope corrected before descent. No retroactive claim
  of compliance with the original allowance is made.

No failed or historical emulator prefix supplied credit to the final single-run
178-execution pass. This checkpoint is not a general scheduler, SMP, arbitrary
suspended IPC, whole-language/kernel safety proof, self-hosting distribution,
physical AMD qualification or broad performance claim.

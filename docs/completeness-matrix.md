# Completeness and acceptance matrix

## Runtime-reviewed copied IPC transition candidate — 2026-10-06

All six operational Mailbox transitions use the copied Aurora policy. Trusted
bootstrap code retains identity, rights, transactions/generations, payload storage
and commits; bind/revoke are unchanged. Individual refusals preserve records and
generations, and already committed composite prefixes remain committed.

The executed 586-file `2b4da219…` source has independent acceptance for full public
D/P release native workflows, six actual native cap consumers, the separately
scoped five-entrypoint fatal ASan/UBSan supplement, and all **182 actual boots**:
177 production modes, three BIOS capacity probes and two additional normal
restoration boots. Terminal/control and raw-corpus reviews passed, with exact
source/runtime preservation and closed owned execution. See the
[results](kernel-ipc-transition-integration-results.md) and [contract](kernel-ipc-transition-contract.md).

The 51-mode timer family passed under its exact instruction-clock contract; 126
other production modes and all five capacity/restoration boots retained their
original clock. Nine genuine three-tick exhaustion modes, context samples and
pending drains remain distinct obligations. The old wall-clock retirement failure
and inconclusive traced attempt retain their original scope, with no prefix credit.

**Full IPC/kernel acceptance remains incomplete.** Both supplemental input-guard
linked reviews remain platform-blocked and unaccepted; runtime results do not
waive them. The 26-image stack/link review remains conditional on its exact bytes
and assumptions. SAN excludes generated-assembly/compiler instrumentation and
leak checking. The hosted service-budget model still has no IPC/RR restart
coverage; actual guest results are separately credited. PR28 stays draft. This
later docs/evidence-only source is not relabeled as the executed 586-file source.

## Prior five-consumer developer-test workflow — 2026-10-05

The [shared test contract](developer-test-contract.md) adds build-once local
developer provenance and an explicit externally pinned native acceptance route.
`make test` fresh-builds current source without imposing a historical binary pin;
`make test-acceptance` requires a reviewed `ACCEPTANCE_COMPILER_SHA256` and can
copy an explicitly selected pinned prebuilt without claiming a fresh source build.
All compiler-consuming gates use the run-owned read-only bytes. Require a newly
completed matching `run.json` and native-stage result. Full compiler-entry `test`
is complete only for compiler scope; focused/diagnostic work and Make exit zero
alone are not root acceptance. Actual emulator checks remain separate.

Status: **exact PR26-based full public native workflows independently reviewed**.
Revision 5 passed fresh developer `make test` and externally pinned prebuilt
`make test-acceptance` on the reviewed GNU/Linux GCC 14 host. All five cap consumers
and PR26 round-robin/short-circuit implementation bytes are retained. The baseline
is accepted main `3ac216b64caf8b769147f1864aa8389011f0112b`; the tested source has
572 files. The developer command/product passed, while its original outer audit
failed on stale completion labels; that failure remains unchanged with a separate
approved read-only composite. The prebuilt workflow has a passed original terminal,
zero bootstrap builds and independent terminal approval. See [workflow results](developer-test-workflow-results.md).
Gentoo make-test, new sanitizer/emulator runs, physical hardware and broad-host
qualification remain separate. Earlier focused kernel-budget results remain
PR25-only. Existing checkpoint evidence below keeps its original source scope.

## Verified Aurora round-robin and short-circuit checkpoint — 2026-10-05

The real UEFI two-client dispatcher now calls a copied Aurora selection policy.
Authority, mailbox mutation, context and hardware stay in trusted C++/assembly.
The 566-file tested freeze passed a fresh compiler build, all 45 focused commands,
the complete native aggregate and all 173 production QEMU modes plus three
capacity probes and two actual normal restoration boots. Independent native,
ABI/IR/linked-stack and final retained-trace reviews passed. See the
[bounded contract](kernel-round-robin-contract.md) and
[integration results](kernel-round-robin-integration-results.md); this adds no
general scheduler or physical-platform qualification claim.

The first combined aggregate is preserved as failed at the BIOS payload-size
gate. A BIOS-only root removes unused UEFI policy graphs while preserving its
value/ownership probe. The final candidate also incorporates the separately
reviewed 127-sector transport correction and exact-bool short-circuit compiler.
Fresh combined acceptance passed without reusing failed-run prefixes.

A later full-aggregate attempt was blocked before child execution when its
1024 MiB configuration conflicted with three harnesses' 512 MiB ceilings. The
test-only replay aligns all five bounded cap contracts while preserving focused
defaults and all behavioral gates. Configuration-only checks are not native or
emulator acceptance; the blocked packet and prior failures remain preserved.

## Verified Aurora kernel-budget checkpoint — 2026-10-05

The [interrupt-budget transition](kernel-budget-contract.md) is a pure Aurora
class/enum implementation wired into the existing UEFI service/client timer path
through a private scalar bootstrap transport. Next-state calculation and
resume/exhaust selection execute in Aurora; domain/frame/epoch/ISR authority,
timer hardware, storage and cancellation remain trusted bootstrap mechanisms.
A fresh compiler build, full native aggregate, all 170 actual emulator modes and
two additional normal BIOS/UEFI boots passed, with independent terminal reviews.
The [evidence index](evidence/kernel-budget-policy/README.md) identifies the exact
533-file tested freeze and preserves the earlier failed/interrupted attempts
without borrowing their mode prefixes. Result-only documentation was finalized
separately; implementation, test and runtime bytes are unchanged from that freeze.
The BIOS scheduler, general scheduling and physical-platform status do not change.

This is a requirements map, not a completion percentage. Snapshot: 2026-10-04, verified milestone022 functional checkpoint. Copied ordinary method class parameters and std::array exchange passed complete release/fatal host ASan/UBSan compiler gates, independent source/IR/native ABI review, a fresh parent aggregate and all 166 actual emulator modes (37 BIOS, 129 UEFI-family), followed by two separate normal restoration boots. All 368 source and 236 external inputs stayed unchanged through integration. No new kernel functionality or physical-device qualification is added. Bounded integer-only single-CPU preemption and a separate validated UEFI handoff remain the baseline. See the [verification record](verification.md) for exact source identity, commands and limits. No physical AMD platform is qualified; [Framework 13 / 7840U](framework-13-7840u.md) is the first complete-machine target.

“C++-expressive” means comparable useful systems-programming capability under newly specified safety rules. It does **not** mean preserving arbitrary pointer manipulation, undefined behavior, C++ source compatibility, object layouts, or the C ABI. The confirmed identity is a recognizable modern C++ API with extreme safety, modern/elegant design and high performance. The target must specify safe replacements and any excluded features; unsafe features may be removed rather than preserved for compatibility. Neither the current compiler nor this matrix proves that every useful C++ pattern already has an equivalent.

| Area | Implemented baseline | Target and evidence gate |
|---|---|---|
| Compiler pipeline | C++23-hosted frontend → trusted semantics/lifetime checks → typed IR → immutable validated module → x86-64 backend; lower-level bounds-token/type/CFG checks, no optimizer; corrected-source aggregate verified in milestone003 | Precise semantics, typed intermediate representation, optimization validation, reproducible toolchain and diagnostics; differential/property/fuzz tests and independent review |
| Scalars/control flow | C++-recognizable declarations; i64/u64/u8/bool locals, branches/functions, restricted while loops; checked signed +/−/*/negation; milestone007 adds checked / and %, truncation toward zero, dividend-signed remainder, distinct zero-divisor failure and explicit minimum/-1 behavior; independently reviewed and integrated; milestone008 adds reviewed checked u64/conversions/bit operations/shifts, final integration passed; milestone013 adds checked u8 and canonical compact byte layouts | Complete specified numeric/control-flow model, checked range arithmetic, defined failure behavior; edge cases agree across interpreter/backends |
| Classes/value abstraction | Milestone011 adds bounded acyclic class-field composition, Value constraints, readonly constructor snapshots and independent public-field projections;  milestone005 constructors/private methods/const receivers; milestone006 compiler adds immutable ordinary-function class parameters and complete independent results, with 59 new value-call/206 IR/4 exhaustive-dispatch checks; milestone012 adds reviewed copied class-valued method results; milestone022 adds immutable copied class-valued ordinary method arguments and a separately checked combined receiver/argument/result private ABI; general constructor bodies, overloads, inheritance, resource fields and source-visible borrowing remain deferred | Fields, methods, initialization, deterministic destruction, Java-inspired encapsulation/interfaces with inline values and explicit dispatch; no mandatory GC/boxing; explicit ownership; test partial construction, moves, drops, dispatch and invalidation |
| Fixed arrays | Local scalar arrays, value copies and checked indexing; milestone010 adds reviewed private zero-initialized scalar-array fields and compiled std::array<T,N>, scalar T and literal N in 1..64, copied at()/mutable set(); milestone022 adds copied exchange with independent old-value results and replacement snapshots; canonical builtin::array plus fixed bare array alias; 216 container/463 IR cases, final integration passed | General ownership-safe collections and aggregate lifetime rules; boundary, overflow, initialization and aliasing tests |
| Modules and source/artifact I/O | Explicit bounded import roots, exports/namespaces, defining-module lookup, scoped metadata views; descriptor-relative Linux source reads, atomic fail-latched output, depth caps; no separate binary-module ABI | Native module/package identities, lifecycle and resource contracts; independently tested visibility, import graphs, artifact failure behavior and later native-capability replacement of host adapter |
| Safe type-level algebra | Not implemented | Key-set queries, mapped/conditional types, checked refinement and bounded evaluation; no unchecked top type/assertion loopholes; preserve privacy, nominal resource identity, lifetimes and effects |
| Generics/compile-time programming | Restricted builtin/class size, type-ID, field-count facts and static assertions; milestone009 adds reviewed explicit one/two-parameter Scalar-constrained class templates, 64 definitions/256 specializations per graph; milestone010 adds Scalar-plus-i64 literal-capacity parameters restricted to 1..64, with canonical value identity and readonly substitution; milestone011 adds bounded Value class composition, and reviewed milestone012 extends Value to closed nominal enums while Scalar stays numeric/bool; milestone020 adds fully concrete nested template-id arguments to depth four, independent of class depth four, with unchanged leaf/definition/instance/capacity bounds; milestone021 adds explicit one/two-parameter Scalar/Value namespace-level function templates and narrow bare-parameter class-template substitution, with combined 64-definition/256-instance budgets; no deduction, overloads, generic methods, nested dependent expansion, function-template calls in template bodies, recursive instantiation, general concepts or reflective code generation | Constrained generics and typed reflection/code generation; generated code obeys ordinary visibility, lifetime and effect checks; reproducibility/resource-limit tests |
| Memory safety | Scoped local owned integers plus readonly whole-array u8 spans and checked named-parent readonly subwindows, synchronous capability-record parameters and conservative lexical/call lifetime rejection; no async/heap ownership implementation | Heap/arena ownership, interprocedural lifetimes, aliasing/provenance and trusted intrinsic rules; formal core model, negative tests, adversarial safe clients and compiler validation |
| Runtime reflection | Runtime size/field-count lookup for builtin/class/mentioned-array IDs and reviewed nominal enum descriptors; class counts public fields only; no member traversal or invocation | Exported descriptors, checked invocation/mutation, ownership-preserving dynamic arguments, unload leases; stale/malformed metadata and privilege-bypass tests |
| Concurrency/async | Not implemented | Defined atomics, data-race prevention, synchronization, cancellation and suspension lifetimes; model checking/stress/fault tests and soundness argument |
| Freestanding core and platform/runtime | First Aurora-authored scalar std.core module implemented and cross-module execution tested; general platform/runtime services remain absent | Separate core/kernel/user profiles; Aurora-authored startup, capability-scoped allocation, threading, I/O, time/math and native OS boundary replacing libc responsibilities; no C API/ABI; dependency/failure gates in [library-stack.md](library-stack.md) |
| Safe standard library | Tiny published std.core and std.numeric/Accumulator modules; milestone006 adds scalar-specialized std::minmax/MinMax and checked range_width using independent value boundaries; milestone007 verified scalar std.integer gcd/lcm/div/DivResult; milestone008 adds reviewed scalar std.bit popcount/bit_width/has_single_bit, final integration passed; milestone009 adds reviewed std.utility pair for all nine scalar tuples; milestone010 adds reviewed std.array with private fixed scalar storage and complete independent copies; milestone012 adds reviewed std.decimal recoverable numeric accumulation and copied DecimalResult reports; milestone013 adds recoverable std.bytes codecs and compact fixed storage; milestone021 adds real std::make_pair<T,U> using independent copied values; milestone022 adds std::array exchange; no strings, heap containers or general runtime package set | C++-recognizable strings/containers/algorithms/ranges/ownership/concurrency/reflection in Aurora; checked views/invalidation, Unicode/numerics and effects; no unsafe API loopholes or assumption of unchanged libc++ reuse |
| Tooling/self-hosting | Host compiler/build/test harness; no native self-hosting | Native toolchain/packages/debugger/profiler; build compiler/system using the native core/runtime/library, inspect target dependencies and compare multi-stage outputs |
| Boot/CPU | Separate OVMF-tested relocatable UEFI loader/payload with bounded final-map handoff, own stack/mappings and Aurora execution; Sequential protected user domains now run on UEFI; bounded UEFI run budgets and controlled client recovery are implemented. Emulator-only BIOS loader, explicit 4 KiB permissioned identity mappings, serial result, IDT/GDT/TSS/guarded IST, NXE/WP and fail-stop paths verified in QEMU | Native or UEFI boot contract; validated memory map, exception recovery, per-CPU state, feature detection, real-machine logs |
| Memory/process isolation | Partial trusted C++ bootstrap: E820 usable-map validation and bounded 128-page arena, move-only generation/epoch tickets; controlled ring-3 probe plus new separately compiled user fixtures, bounded scalar return and validated compiler-fault containment in three owned CR3 domains with leased stacks, tested foreign-access denial, root restoration, scrubbed reuse and stale-handle checks; bounded integer-only BIOS preemption plus milestone009 sequential UEFI domains with explicit layout authority, private backing and guarded entry stacks; no general process model | Physical/virtual allocation, user isolation, capabilities, revocation and resource accounting; cross-domain access/forgery tests fail safely |
| Scheduler/SMP/IPC | Bounded QEMU xAPIC single-CPU integer-context preemption, fixed tasks/slice budgets, pending-IRQ drain; staged copied-scalar request/reply IPC on UEFI with incarnation-bound grants and cancellation/restart; UEFI role/phase/transaction-bound client and service interrupt-count budgets with disposal, mapping retirement, scrub and rebinding; Aurora owns the copied two-slot next-eligible policy, with authority and commit still in trusted bootstrap code; no SMP, arbitrary suspended IPC, calibrated time or general scheduler | Preemptive scheduling, multiprocessor synchronization, timers and bounded IPC; fairness, interrupt storms, starvation and restart tests |
| Platform/power | Bounded post-firmware RSDP/XSDT/MADT discovery through a revocable R-NX window, tested in OVMF; read-only q35 MCFG/PCI function inventory through revocable UC mappings; milestone014 adds explicit validated read-only BAR/profile authority with revoked-window tests and a pinned clean-firmware fixture; no AML, device activation/IOMMU driver stack or physical-platform power support | Discovery, DMA isolation, interrupt routing, suspend/resume, shutdown and thermal policy; malformed tables, stale DMA and transition-failure tests |
| Storage/network/input | No target driver/filesystem/network/input implementation; native NVMe object/extent filesystem and XFS on-disk backend are specified in [storage requirements](../storage/design/requirements.md); host-only durability model and traceability tests pass, not mount support | Real drivers and services, persistence/recovery, networking and input; corruption, unplug, exhaustion and restart tests on named devices |
| AMD display | Not implemented; no framebuffer acceptance result | Boot framebuffer then native display separately; modesetting, hotplug and resume tested on named GPU/connector tuples |
| AMD acceleration | Not implemented | GPU memory isolation, submissions, shaders, fences, preemption and recovery; correctness plus adversarial multi-client and reset tests |
| Performance qualification | No equivalent-C benchmark evidence | Reproducible equivalent-semantics C comparisons; layout/allocation/atomics/dispatch/check/reflection costs, latency/throughput/memory/code-size; no blanket zero-cost claim |
| Whole-system assurance | Proposal and bootstrap tests | Threat model, audited trusted base, scoped proofs, independent security review, update/recovery and operational tooling |
| AMD coverage | QEMU configuration only; no physical qualification | All Zen CPU generations and Navi/RDNA onward GPUs, integrated/discrete where applicable; per-platform/device/firmware records, never extrapolate all devices from one success |
| Native system ecosystem | Not implemented | Toolchain, source-package system, graphical desktop, terminal/shell, installer and system services authored in Aurora; acceptance inventory in [system-release.md](system-release.md) |

The modern C++ syntax, fixed-array, loop and checked-arithmetic expansion is implemented, independently reviewed and verified by a fresh aggregate run. Earlier integration results above remain evidence for their identified checkpoint, not automatic verification of these changes. Old fn/let syntax is rejected. Historical milestone001 receipts are preserved, not retroactively relabeled.

## Required evidence discipline

Run `make test` for the complete developer native graph, or `make test-acceptance` with an independently reviewed expected pin for explicitly pinned native checks, and `make smoke` for the actual emulator boot; one does not substitute for the other. Preserve the newly completed matching run receipt, command, tool versions, source identity, output and pass/fail status under the [shared test contract](developer-test-contract.md). Mark a feature **implemented but unverified**, **partially implemented**, or **not implemented** whenever that is more accurate than “supported.” A proof must identify its modeled features and trusted assumptions; passing tests is not such a proof.

The detailed language target is in [language.md](language.md); dependency milestones are in [roadmap.md](roadmap.md); hardware-specific requirements and primary references are in [amd-support.md](amd-support.md). A fully functional kernel needs the relevant platform, isolation, scheduling and device rows, while a usable general-purpose OS additionally needs services, libraries, applications and operations. Until those gates pass, the deliverable remains a compiler/kernel bootstrap.

## Class-value checkpoint

Milestone005 established the constructor/method checkpoint in [CLASSES.md](../compiler/CLASSES.md). The milestone006 compiler adds ordinary-function class value boundaries and native MinMax APIs under [VALUE-CALLS.md](../compiler/VALUE-CALLS.md). It passes 59 new value-call cases, 206 typed-IR cases, four exhaustive-dispatch compile checks, existing source/module/depth/host-I/O suites, scalar-oracle checks and address/undefined-behavior sanitizer gates. Independent compiler review passed; final integrated verification passed. Existing milestone005 and earlier receipts are unchanged. This compiler status does not expand kernel or physical-hardware qualification claims.

## Checked integer candidate

The milestone007 compiler implements checked i64 division/remainder and the freestanding `std.integer` algorithms described in [INTEGERS.md](../compiler/INTEGERS.md). It passes 84 integer cases, 216 direct IR cases, six exhaustive-dispatch checks and 1,510 independent integer-oracle cases with 181 exact UD2-site checks, including sanitizer runs. Independent compiler review passed; final integrated verification passed. Zero divisors never intentionally reach hardware IDIV, minimum/-1 quotient traps, and its remainder is zero. These results do not establish general numeric completeness, constant-expression arithmetic, a global stack/resource bound or equivalent-C performance. Kernel and hardware status above remains separately qualified.

## Unsigned and bit candidate

Milestone008 adds the exact typed contracts in [UNSIGNED.md](../compiler/UNSIGNED.md), preserving prior scalar/class/array/call safety checks. The compiler passes 95 unsigned source cases, 385 typed IR cases, ten exhaustive-dispatch checks and 4,219 default native unsigned-oracle cases with 501 exact trap-site checks and 67 rejection fixtures. Alternate runs of 6,665/766 and 8,959/1,044 cases/traps overlap this coverage and must not be added together. Existing regression suites and sanitizer gates pass; independent compiler review passed. Final integrated verification passed. The real std.bit functions are scalar-specialized; that checkpoint did not yet include generic value templates or reusable containers. This compiler status does not expand kernel or physical-hardware qualification claims.

## Constrained value-template candidate

Milestone009 implements [explicit scalar class templates](../compiler/TEMPLATES.md) and compiled std.utility/std::pair<T,U>, preserving defining-module privacy, ordered nominal type identity, complete construction and independent class-value copies. It passes 117 template tests, 393 direct IR cases, ten exhaustive-dispatch checks and existing suites/sanitizers. Independent compiler review passed; final integration verification passed. The exact 64-template/256-specialization limits are tested locally and across module graphs. These do not establish global resource bounds. General generic programming, nested aggregate containers, strings and runtime allocation remain future work. Kernel and physical-hardware claims are separately qualified.

## Bounded fixed-container candidate

Milestone010 implements [private fixed storage and literal-capacity templates](../compiler/FIXED-CONTAINERS.md), with compiled std::array<T,N>. The reviewed candidate passes 216 container cases, including 55 exact trap-site checks and 96 rejection fixtures, 463 typed IR cases, ten exhaustive-dispatch controls, and 18 native receiver-array IR checks including ten exact-site traps. Existing suites and sanitizers pass. Alternate-seed runs overlap the same coverage. Independent compiler review passed; final integrated verification passed. The wrapper has no heap, slices or escaping element references. Public reflection counts logical fields; storage layout and full copies count scalar leaves, with a 64-leaf limit per ordinary class-value boundary. These caps do not establish global compiler resource bounds or stack safety. Kernel and physical-hardware claims remain separately qualified.

## Milestone011 scope

[Composed values](../compiler/COMPOSED-VALUES.md) and the [UEFI service budget](../kernel/uefi/service-budget.md) passed final exact-source integration and independent review. Nested mutation, resources/references, general template deduction and full scheduler semantics remain deferred. See verification.md for the repaired kernel segment-state regression and exact evidence; prior failed development records remain historical.

## Milestone012 scope

[Closed nominal enums and copied method results](../compiler/ENUM-RESULTS.md) are
implemented on the verified composition baseline. Value includes enum identities;
Scalar remains numeric/bool, arrays reject enums, and no numeric enum conversion
exists. Results preserve complete recursive logical initialization, empty-child
storage rules, exact shape and disjoint receiver/constructor/result authority.
The real std.decimal API reports numeric digit failures without requiring text
storage or a general expected type.

The checkpoint passes 107 combined cases, 196 decimal cases and 592 direct IR
cases, with existing compiler regressions and ASan/UBSan. Independent compiler
review passed, including additional ABI cases. Alternate-seed coverage overlaps.
The bounded two-client/one-service UEFI dispatcher is independently reviewed,
including cross-mailbox denial, round-robin selection, service cancellation/restart
and committed-reply preservation. All 122 emulator gates and parent aggregate
checks pass. Clients remain cooperative. This does not advance physical hardware,
full runtime completeness or equivalent-performance qualification.


## Milestone013 scope

Checked u8 and compact fixed byte layout passed source, mathematical, ABI,
malformed-IR and sanitizer gates with independent review. Logical initialization
and nominal shape remain separate from physical byte extents and ABI reservation
rounding. The real recoverable std.bytes codec is compiled and tested; it does not
provide arbitrary class serialization or claim equivalent-C throughput.

Controlled user-phase budgets contain only retained known compiler faults and
verified count exhaustion. Peer transaction authority survives offender disposal;
unknown-origin faults remain fatal. All 139 modes passed on the final compiler,
with 202 build/test inputs captured before and unchanged after the complete run.
See verification.md for parent checks and independent-review compiler identities.


## Milestone014 scope

Readonly byte spans, synchronous binary readers and a separate protected span
program are verified. Static creation-site identity strengthens branch joins;
this does not claim unique runtime generations or general borrowing. The narrow
read-only PCI BAR/resource slice passed seven actual modes plus the span mode,
with all 139 historical modes preserved. Stock controller state is rejected;
the clean test firmware's exact configuration and provenance are mandatory.
DMA, NVMe queues, IOMMU isolation, filesystem mounting and real hardware remain
unimplemented. Storage S0 requirements and host crash/model checks are integrated.


## Milestone015 scope

The library adds checked LE/BE16/32/64 reads, incremental CRC32C and an exact512-byte
XFS v5 header-integrity fact probe. Its reports do not establish log cleanliness,
feature support or mountability. Independent native/oracle/fixture checks and
complete release/sanitized compiler targets passed without compiler changes.

Read-only AMD-Vi discovery reconciles paired IVHD10/11 requester facts with live
PCI and full-aperture resource exclusions. Architectural-default admission refuses
the observed disabled-enable-bit configuration; a separately selected, exact QEMU
profile permits only three cold register reads. All158 actual modes passed,
including independent11 new modes and four parent spots. Stack lifetimes were
fixed without widening the16KiB stack; the reviewed maximum is12,776 bytes with
fault reserve. This is not active translation or DMA isolation. Filesystem and
physical-device goals remain open.

## Reviewed compiler initialization-fact storage

This reviewed implementation changes only the verifier's local must-initialized and
may-initialized fact representation. It adds no language feature and includes no
mutable-byte-view implementation. Dense facts use a checked immutable slot
universe and two bitsets; logical dataflow decisions and generated assembly remain
unchanged on the finite differential corpus.

Release model/IR/full compiler gates pass. The complete instrumented target also passes, with minimal -g1 debug metadata
only for the IR test binary and unchanged fatal ASan/UBSan instrumentation.
Independent source/model/storage review passed with exact manifests and the
sparse-memory tradeoff retained.

The measured dense workloads improve, while a valid sparse-prefix source uses
about10.7% more RSS. This is not a universal improvement or an overall compiler
resource guarantee. [RESOURCE-NOTE.md](../compiler/RESOURCE-NOTE.md) records both
counterexamples and improvements, precise logical-storage exclusions, limits and
failed build receipts. Main combined milestone acceptance remains a separate decision.


## Milestone016 scope

Representation-only compiler initialization facts use checked dense bitsets with
unchanged admission rules; sparse-memory regressions are documented alongside
dense-case improvements. Complete release/instrumented and independent differential
checks passed. Only the large IR sanitizer-test build used reduced debug metadata;
runtime instrumentation and fatal checks remained enabled.

Real kernel page leases are held in a persistent four-entry ledger. Clean,
never-published cancellation scrubs before release; test-selected uncertain
publication remains permanently quarantined through service slot1 death and
incarnation2-to4 restart, stale-authority rejection and clean42 execution.
All162 actual modes and parent checks passed. No device publication/completion
API, IOMMU activation, DMA isolation or physical qualification is implemented.


## Milestone017 scope

Readonly std.utf8 decodes/validates Unicode17 UTF-8 with strict byte ranges,
recoverable signed-range failures and stateless incomplete-prefix replay. Native
independent tests cover every scalar and short/boundary inputs on release and
instrumented compilers. Public report classes are data, not buffer certificates.
Compiler implementation, kernel and prior fixtures remain unchanged. Parent
aggregate plus runtime-span, pin-fault and normal UEFI profiles passed. The previous
162-mode run belongs to M016 and was not rerun for this library-only delta.
Encoding, owned strings, normalization, graphemes, fonts, paths and terminal
semantics remain separate requirements.


## Milestone018 scope

Owned UTF-8 encoding extends std.utf8 using existing fixed-array/value-class APIs.
All scalar encodings and invalid-scalar, zero-tail, copy, report and access cases
passed independent native checks. Public report constructors can supply arbitrary
data; accessor range/padding checks do not certify forged success bytes as UTF-8.
Parent aggregate and three existing smoke profiles passed on unchanged compiler/
kernel; no fresh full162 run. String allocation, normalization, graphemes, output
services and terminal behavior remain separate.


## Verified milestone019: dormant table bytes and XFS header geometry

The integrated checkpoint passed all **166 actual emulator modes** (37 BIOS,
129 UEFI-family), independent review of all four new modes, a fresh coordinating
`make test`, and fresh readback/quarantine/normal UEFI smoke profiles. The latter
three are selected repetitions, not a second full suite. Normal images restored.

- The bootstrap kernel constructs bounded AMD3.10-format dormant tables in real
  leased guest RAM, checks every DTE/leaf through a software model, rejects
  corruption, tests exhaustion, and scrubs or quarantines pages across restart.
  No IOMMU register programming, device publication, DMA or interrupt isolation
  is implemented. Each mode retains the 16 KiB stack and existing page budgets;
  the measured bound is 13,136 bytes including a 1,024-byte fault reserve.
- Native `fs.xfs_geometry` adds recoverable facts for a deliberately narrow XFS
  v5/512-byte header profile, overflow-safe geometry and explicit feature masks.
  Independent tests exercise 2,016 identical byte-distinct headers under each
  compiler pin, all 42 scalar result leaves, failure zeroing and input stability.
  Success is copied data, not authority or evidence of mountability. No XFS
  mount/replay/write path, storage transport or physical-device qualification.

See [verification](verification.md) for hashes, failures, test limits and
archival evidence. General heap safety, active DMA, SMP, native toolchain,
filesystem service, graphics and the complete desktop remain future work.

## Verified milestone020: bounded nested generic values

The integrated compiler permits fully concrete nested Value template arguments,
including private fixed byte-array wrappers and closed nominal enum descendants.
The four-level template-id cap is independent of class-depth four; 64 leaves,
64 template definitions, 256 interned instances including children, and literal
capacities 1..64 remain unchanged. Child-first nominal resolution preserves
transitive visibility, defining-module binding and copied value boundaries.
See [NESTED-VALUES.md](../compiler/NESTED-VALUES.md).

Independent source/adversarial review and complete release/fatal ASan/UBSan
compiler targets passed. Parent adoption verified all 18 paths, rebuilt the release
compiler to the reviewed pin, then passed a fresh `make test` and `runtime-span`,
`runtime-pin-fault`, `normal` UEFI profiles. All 359 captured source inputs and
183 external pins were unchanged during those gates; normal image restored.
Documentation-only finalization is identified separately in M020 evidence.
M019's full 166 modes remain historical, not a fresh M020 run. Dependent body
expansion, recursion, deduction, ownership/references, new ABI/IR, full standard
library capability and physical hardware support are not added.


## Verified milestone021: explicit copied-value function templates

Namespace-level function templates accept one/two explicit Scalar/Value type
arguments and instantiate independently copied concrete functions. std::make_pair
and the executable token/source-range example consume existing inline values.
Class-template-id arguments may be bare function parameters or concrete M020 trees;
nested dependent expressions and calls to function templates from any template
body are rejected. Combined graph budgets are 64 definitions/256 instances.
Nominal depth, class containment, leaves, array capacities and copied-value
boundaries remain independently checked. Unrequested ordinary tuple validity is
deferred; structural restrictions and fixed exported-signature visibility are eager.

Complete release/fatal host ASan/UBSan compiler gates, independent release review
and fatal replay passed. Parent adopted 18 pinned paths and rebuilt the identical
release compiler, then passed fresh make test and runtime-span/runtime-pin-fault/
normal UEFI profiles, restoring normal. All 363 source and 183 external inputs
were unchanged through those gates. Final documentation-only changes are recorded
separately. M019's full 166 modes remain historical. No new IR/ABI, deduction,
overloads, generic methods, function capacity parameters, recursive expansion,
heap/resource/reference generics, complete library, self-hosting or physical
hardware support follows. See [contract](../compiler/FUNCTION-TEMPLATES.md) and
[evidence](evidence/milestone-021/README.md).

## Verified milestone022: copied ordinary method parameters

Complete named class arguments become independent readonly snapshots at their
left-to-right evaluation positions, before synchronous receiver acquisition.
Results require pristine exact nominal storage separate from receiver and argument
snapshots. New private combined ABI inputs use R10 receiver, R11 argument record
and RAX result, with separately saved slots and 32 bytes of hidden overhead.
The six-parameter/64-leaf/source-frame and existing graph limits remain. No new IR
instruction, source pointer, template grammar or foreign ABI promise is added.
The real std::array exchange replaces from a snapshot and returns old contents.

Complete release/fatal sanitizer compiler suites and independent frozen-source
review pass: focused 152 fixtures/219 executions, 51 new direct IR cases and
21 handwritten native ABI cases. These are bounded, overlapping evidence, not
formal proof counts; two source-fixture gaps have diagnostic-specific addenda.
Fresh parent make test and all 166 actual existing modes passed on release pin
e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e.
Two normal BIOS/UEFI boots restored the images. Independent receipt/source/live
image checks and all 168 retained validator replays passed. All 368 source and
236 external inputs were unchanged; later edits are documentation-only.

The initial concurrent sanitizer stress SIGKILL remains unclassified; exact
isolated input replay and full 28/28 stress pass. The abandoned bare-array parser
exception was reverted; parser.hpp is byte-identical M021. No ownership/reference/
generic-method, global resource bound, Rust-equivalent safety, physical-hardware
or equivalent-C performance claim is added. See [contract](../compiler/METHOD-VALUES.md)
and [evidence](evidence/milestone-022/README.md).

## XFS-only local-root lookup checkpoint after milestone022

The candidate `fs.xfs_root` module interprets an offline 512-byte v3 root inode and
bounded 32-bit shortform directory from checked readonly byte spans, after the
existing XFS geometry/header gates. It validates the full directory before found
or missing, returns copied class reports, and masks all failure facts to zero.
The supported core/feature flags, CRC/identity, inode geometry, raw names,16-entry
limit and saved-offset accounting are explicit in [the contract](xfs-root-contract.md).
Fresh M022 standalone tests passed203 cases/2,233 full u64 observations plus77 API
observations and12 rejection controls; independent source and portable Make review
passed. This isolated full parent `make test` passed; the
[independent delta review](evidence/xfs-root-m022-20261004/review.md) records the final acceptance scope. Kernel/compiler implementation remains byte-identical to accepted M022.
The Storage/network/input row's absence of target drivers and filesystem services
continues to apply: an offline root lookup is not a mount, allocation/existence
proof, replay, file-data reader, block-device service, or read-write filesystem.

## Read-only UTF-8 scalar-range checkpoint

`std.utf8_range` adds scalar-indexed substring byte observations over readonly
spans. The entire selected window must be valid final UTF-8 before a copied
relative byte offset/count is returned; errors expose zero coordinates.
It preserves the previous UTF-8 APIs and accepted M022 compiler/kernel sources.
Independent native review and the fresh full top-level `make test` passed on
the frozen implementation. No string container, grapheme/normalization/display-width
support, returned view,
new emulator qualification, or performance guarantee is claimed. See [the exact
contract](utf8-range-contract.md).

## Independent package identity candidate

A library-only candidate adds `package.identity`: bounded canonical package-name
and numeric version-triple parsing from readonly input, owned copied facts,
recoverable errors, exact identity equality and numeric version ordering. Its
[restricted format and acceptance gate](package-identity-contract.md) are explicit;
this is neither full SemVer nor a manifest/dependency/build/install implementation.
The example executes without target libc using the unchanged accepted M022
compiler. Independent adversarial/oracle review and the full focused Make recipe passed;
parent aggregate remains pending. It does not advance compiler, kernel, self-hosting, package authenticity
or physical-device qualification claims.

## Read-only UTF-8 line-scanning checkpoint

`std.utf8_lines` observes the first LF/CRLF-terminated or unterminated final line
of a readonly byte window. Strict UTF-8 validation covers consumed bytes including
the terminator; later lines are checked on later calls. Copied masked counts
support progress through empty lines without retained views or mutable storage.
This explicitly differs from whole-window `utf8_subrange` validation. Independent
native review and a fresh full top-level aggregate passed on the frozen source.
Compiler/kernel, old APIs, terminal behavior and hardware qualification are unchanged. See [the exact
contract](utf8-lines-contract.md).


## Declarative package manifest candidate

A library-only `package.manifest` candidate parses an explicit versioned ASCII
profile into copied package/dependency observations using the accepted package.identity
module. It validates the entire manifest, canonical pinned versions, dependency-name
uniqueness, self-name exclusion, exact line endings and trailing-byte rejection.
The supported zero-to-eight dependency profile is bounded by current value/language
limits. [The contract and gate](package-manifest-contract.md) describe independent
native oracle, failure/ownership/privacy tests, separate review and fresh full
aggregate required before acceptance. No compiler, kernel, resolver, build execution,
installation or trust/cryptography capability is added.


## Bounded package graph candidate

`package.graph` adds actual whole-catalog validation and deterministic dependency-
first ordering for zero to eight caller-supplied exact manifests. Its supported
profile rejects duplicate canonical roots, missing names, exact-version conflicts
and cycles, with whole-set error precedence and no partial successful facts.
Copied order/identity observations survive input-owner changes. The existing
compiler and package parsers are unchanged. See [the contract](package-graph-contract.md)
for limits. Independent oracle, corrected full focused Make and separate native
review passed; fresh full aggregate/final seal remain required. Source retrieval,
recipe execution, installation, general dependency
solving and provenance authority remain absent.

## Unaccepted exact ordinary-function overload candidate

The isolated candidate implements same-defining-module ordinary overloads by
exact arity and nominal argument tuple, with a 32-declaration cap. Return type
never discriminates; no implicit conversion, template/method overload, generic
method or cross-module overload merging is admitted. Existing copied-class and
readonly-span boundaries stage arguments once left to right. Single-declaration
bootstrap symbols remain unchanged and overloaded root answer rejects. Complete
isolated release/fatal host sanitizer compiler gates and independent source/IR/native
review passed. Parent integration remains required before acceptance. See the
[contract](../compiler/FUNCTION-OVERLOADS.md). This adds no new IR instruction,
ABI, kernel mechanism, heap/reference API or optional feature.


## Replacement emulator fixture qualification (2026-10-04)

The historical custom BAR/IVRS firmware CODE image with SHA256
`82c1ea28dc532053bfbe5c0b7a8013f3eef5742534e3358264a220b70ec24d49`
remains unrecovered. Rebuilding the historical pinned input closure produced
`24b30416142749dd60ac241fe755df6232fc5b10663a8b799501659b796d0268`;
this is a separately qualified replacement, not a bit-reproducible recovery.
The pristine VARS SHA256 remains
`5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e`.

Using the accepted M022 compiler, the replacement passed seven BAR profiles,
eleven IVRS profiles, and two actual normal BIOS/UEFI restoration boots. Three
BAR refusal profiles intentionally use stock firmware; fifteen profiles use the
replacement. Independent receipt/source/tool review passed before adoption. The
only validator change is `PINS['clean_code']` in
`tests/kernel-uefi-bar-provenance.py`; IVRS imports that same pin. Historical
receipts retain their original fixture identity. This acceptance is limited to
the tested emulator BAR/IVRS contract and makes no physical-hardware, firmware
security, whole-run zero-interrupt, or new compiler integration claim.


## Verified ordinary-overload integration (2026-10-04)

The exact ordinary-function overload candidate above has now completed fresh
combined native testing, all 166 existing emulator modes and two separately
rebuilt actual normal BIOS/UEFI boots, with independent final review. No executable
source or validator changed after the tested freeze. Native test success is
qualified by an exact supplemental review while the original empty-tmp bookkeeping
failure remains preserved. The qualified replacement firmware and all physical
hardware/security limitations remain explicit in the
[integration results](function-overloads-integration-results.md).

## Verified bounded readonly byte windows

Named-span `.subspan(i64 offset, i64 count)` provides checked bounds, endpoint-empty
views, exact root/direct-parent provenance and lexical/call-only non-escape rules.
Existing whole-span/single-span APIs remain unchanged. Isolated complete release
and fatal host sanitizer compiler targets and independent provenance/native review
passed. Fresh integration on the accepted PR22 kernel source rebuilt the exact
reviewed compiler and passed the complete native aggregate, all170 actual emulator
modes and two separate normal restoration boots. Independent final review checked
the full retained evidence and replayed all172 validators. Final edits after this
tested540-file freeze are result documentation only.

No mutable/returned view, heap container, new kernel mechanism, full-language
safety/resource proof, physical AMD qualification or equivalent-C performance
claim follows. Leak checking remains unavailable. See the [source/IR contract](../compiler/READONLY-WINDOWS.md)
and [exact integration evidence](readonly-windows-integration-results.md).


## Verified bounded BIOS host-toolchain layout portability

The BIOS sector now uses an explicit 0x7c00/512-byte linker contract rather than
the host linker's default ELF section layout. Named GNU metadata is discarded;
unknown sections, separate writable storage and invalid entry/size fail closed.
The production-linker regression passes four assembler-note variants, preserves
the previous relocated instruction bytes and rejects nine malformed layouts,
under ordinary and optimized Python on Debian GNU binutils 2.44. The original
Gentoo 2.47p1 report identified an allocated GNU property note in the boot object;
the user subsequently reported a successful PR25 rebuild on 2026-10-05. That
report is not an independently observed build log or boot. The standalone fix passed a production kernel
build using the unchanged accepted compiler, ordinary/optimized image validators,
an actual normal BIOS boot and an actual controlled divide-fault BIOS boot. Fault
cleanup restored identical normal image bytes (512-byte boot sector, 45,808-byte
kernel payload). Independent focused source review passed. The standalone narrow linker change did not rerun the full native/all-mode
aggregates; the later combined checkpoint above passed them. These
results establish no additional physical-platform or broad host-distribution
qualification. See the
[toolchain contract and diagnostic commands](../kernel/README.md#host-toolchain-boot-layout).


## Verified bounded BIOS capacity portability

An actual 127-sector (65,024-byte) single-read contract replaces the former
96-sector loader limit, keeping destination `[0x10000,0x1fe00)`, the conservative
EDD count/window bounds, BSS initialization and protected stack reservation.
This addresses measured legitimate Gentoo GCC 16.2.1 code-generation growth to
49,904 bytes; it is separate from the earlier ELF-note boot-sector fix and any
round-robin candidate. Validation now checks exact ELF/flat-image correspondence
and transfer-padding memory coverage. Synthetic boundary and rejection checks
pass, including optimized Python. Independent source/layout controls also pass.
Actual maximum-transfer sentinel execution and both failing controls verify
observed bytes and serial outcomes. A fresh production build with the unchanged
accepted compiler, normal/fault BIOS boots, image validators and exact normal
restoration pass. The user reported a successful PR25 Gentoo rebuild on
2026-10-05; no independent log, new boot or physical-hardware result is inferred.
The later combined checkpoint passed full native and all-mode emulation. Future growth beyond
this bound needs a separately reviewed loading mechanism.
See the [active transport contract](../kernel/README.md#bounded-bios-transport-capacity-and-host-code-generation).


## Verified bounded exact-bool short-circuit semantics

The isolated frontend adds C++-precedence `&&` and `||`, exact bool operands,
left-to-right single evaluation and runtime-only RHS laziness. Both operands
remain statically checked. Existing typed IR joins retain stack provenance and
lifetime/initialization facts; an emitted-depth certificate protects unchanged
x86 call alignment. Explicit per-function block/operand-retention limits reject
excessive logical-prefix complexity before snapshot copies. Independent isolated
release and fatal host ASan/UBSan compiler suites passed, followed by the fresh
combined native and 173+3+2 emulator checkpoint. LeakSanitizer was disabled for
executor ptrace limitations; no leak-clean claim follows. See
[contract](../compiler/SHORT-CIRCUIT.md) and the linked integration results. This
language feature itself adds no kernel authority, ABI or heap/reference extension,
full-language safety/resource proof or physical-hardware/performance qualification.

# Aurora implementation roadmap

For what exists now, use the [current project state](completeness-matrix.md#current-project-state).
This page defines dependencies and observable completion gates, not a second
feature-status log. All six destination goals remain open. The detailed release
inventory is in [system release requirements](system-release.md); storage and
physical-platform requirements retain their own linked acceptance contracts.

## Language and system co-evolution

The language, kernel, userspace libraries, drivers, services and applications
advance together, including drivers wherever they execute. Tie each language extension to a real consumer, the capability
it needs and its safety guarantees. Use existing Aurora features for substantive
subsystem ownership now, rather than waiting for self-hosting or adding only
stateless predicates. GNU C++ remains a legitimate bootstrap tool: retire a
C++ component after its Aurora replacement passes equivalent qualification,
without removing hardware/ownership checks prematurely.

The simple UEFI and graphical consoles now retain Aurora-owned line/session
state behind sealed ConsoleSession/DisplaySession capabilities. The
[native console](native-console-service.md) includes bounded editing, a RAM note
and four named session-local RAM files; the [graphical console](framebuffer-console.md)
adds Aurora-owned presentation. This state lasts for the session, not across
reboots. The protected-console source also uses ConsoleSession for individual
input and response turns, exercised by the production-console qualification in
[9aa7b5d](https://github.com/ambasta/aurora/commit/9aa7b5dd72e005ead6053e7ec5742f5663786fa9);
its retained `ProgramSession` now selects protected-console commands and owns
phase, CR carry and terminal outcome. Native effects and general authenticated child lifetimes remain migration
dependencies. The retained source file-owner incarnation policy now owns startup,
readiness, terminal cleanup eligibility and later-operation restart admission. The BIOS console uses the same Aurora
editor and sealed ConsoleSession for its bounded three-command session and
presentation; trusted native code retains interrupt transport and shutdown.
General terminal sessions remain open. The shared typed named-file core remains
separate from parsing/presentation; production now retains its private note and
named-file state in the same external Aurora owner as process files.

The kernel is to become entirely Aurora. The [process image](../kernel/uefi/process.md)
already uses Aurora policies for memory admission, ELF layout, faults and kernel
calls. A separate Aurora program owns file state. The retained source MemoryManager
owns the allocation and mapping ledgers, reservation banks, cross-resident quota
admission, fixed two-slot address-space lifecycle and loader snapshot lifecycle.
Native code authenticates backing reachability and synchronous hardware effects
across metadata detach/reattach; it retains privileged execution, volatile
page-table access and process/IPC transport. This is not an all-Aurora kernel.
Retiring those components needs these language and bridge capabilities, each a
milestone with its own consumer:

- further kernel-side Aurora state that persists across bridge calls: retained
  budget, service-incarnation and memory-manager roots now exist; privileged
  execution and process/IPC transport remain native;
- broader checked mutable memory views and data copies: boot-admitted OwnedWords
  provides fixed-extent scalar access and lexical readonly u64 borrowing for the
  frame ledger, not general allocation, mutable views, resizing, pointer adoption
  or escaping views;
- a privileged-instruction and physical-address capability (page-table writes,
  CR3, INVLPG, MSRs, LAPIC, GDT/IDT loads, IRETQ);
- a trap-entry form for interrupt and kernel-call entry;
- a UEFI call surface for the loader;
- variable-length results (paths) and a validated user-range type;
- more than six parameters per function or constructor, and one calling
  convention for scalar-only bridge functions;
- recursion reachable from a hosted `main` (fixtures use GNU as today).

The bounded native linker now links supported guest-built objects without host
`ld`; general linking, assembly and complete native system rebuilding remain open.

## 1. Protected programs and file services

The [process runtime](../kernel/uefi/process.md) now runs static ELF programs with
private address spaces, demand-backed quotas, owner-counted frame audits and
bounded timer-parked continuations. Production `run PATH [args]` loads committed
executables through a retained external file owner, then restores the console's
exact architecture and mapping boundary. Same-boot compile/link/run is the native
toolchain consumer; it does not require serial artifact export and a host link.

The command admission is a scoped linear `ExecutionLease`, issued by a sealed
`ExecutionEffects` loan. Every result, including an inert refusal or a failed load
that still owes client close, must be explicitly finalized. Local moves transfer
that obligation; normal scope exit cannot silently drop it. The issuer cannot
release, forward or mint again while its lease is live, and forwarding consumes
its single issuance opportunity without refund. Native bindings authenticate
physical resources; they do not replace source command ordering. This is not an
escaping child handle, automatic destructor, asynchronous task or general init
contract. Explicit cancellation drains already-dispatched work under existing
budgets and does not claim rollback or replay.

The synchronous command now groups its lease and phase/result state in one
source-owned CommandExecution, replacing the separate copyable session value.
A lexical owning constructor establishes all fields before its body reads the
authentic preparation; ordinary borrowed progress and explicit consuming finish
keep the issuer pinned until finalization. This is ownership of a command
operation, including refusals and close obligations, not a retained child handle
or asynchronous supervisor. General escaping ownership remains a separate
contract rather than an extension of the temporary execution loan.

The complete file-owner bootstrap sequence now has its own source consumer:
`ServiceBootstrapLease` resolves one unpublished startup through initial Serve,
volume admission and optional disk readiness. Its explicit consuming publication
requires native authenticated receipts; the existing incarnation root remains
the sole lifetime policy. This establishes a real readiness dependency without
introducing a generic init manager, escaping service owner or larger process
capacity. General composition must still specify dependency failure, restart
bounds and cancellation authority rather than importing PID1 conventions.

The fixed production file-service slot now has a retained, noncopyable Aurora
owner across runtime operations. Its authority is distinct from the existing
incarnation policy and from native page-table/continuation storage. Short-lived
command and bootstrap grants derive from the exact owner and a matching admitted
operation; neither copied generations nor slot ownership alone authorize an
arbitrary client launch. Production console exit explicitly advances shutdown
and consumes the owner after reclamation. The consuming receiver currently has
an admitted native entry, not a general source-call or escaping child-handle
surface. Larger process graphs and owned child lifetimes remain open.

The Serve-authorized Aurora service owns boot-volume copies, namespace/handle
state and retained mutable RAM files. The kernel authenticates incarnations and
copies bounded requests/replies; the legacy kernel file store is removed.
Production's bounded note/named-file policy also lives in that owner, while the
existing protected workers and native ledger retain only frozen projections and
authenticated completion state. File publication follows the established policy
and worker-retirement gates, not possession of a copied payload.

Preserve cumulative caller budgets across RPCs, independent server request caps,
immutable in-flight client identity and exactly one terminal cleanup. A delivered
operation may commit after caller expiry; an uncertain/lost reply is never replayed
or described as rollback. Service loss invalidates grants and visibly loses
volatile contents; a later command may start a new incarnation, not resume the
failed request. Mounted read-only data is separate from those RAM commits.

Next: general program/service lifetimes and scheduling, restart-safe storage,
partial I/O/backpressure and durable mounted writes. Gate each step with actual
compiled consumers, stale/foreign authority, exhaustion, cancellation, owner death
and complete frame reclamation. Preserve writable/sealed executable-snapshot
cleanup and real committed-but-reply-lost cases at the production boundary.
Existing fixture contracts remain useful bounded
references, not substitutes for production integration or a general scheduler.

## 2. DMA-safe transport and persistent storage

The closed emulator profiles now exercise default-deny AMD-Vi admission,
requester invalidation with fresh completion and real NVMe DMA. The raw transport
has exercised Identify/read/write/Flush and cold-boot persistence on disposable
images. Backing remains pinned for the boot; errors quarantine rather than reset,
reuse or reclaim it. These observations do not establish physical-device isolation,
drain, recovery or safe DMA-page reclamation.

A sealed read-only block capability connects the retained source file owner to
NVMe. Its strict fresh-format XFS gate reads the complete supported log and checks
root/inode metadata before exposing `/disk`; actual process guests exercise this
path and whole-image immutability. Production NVMe/GOP guests also exercise eager
readiness, unsupported-log refusal and continued RAM-file/console operation.
Preserve those combined gates and the unchanged RAM-only composition as the
transport and mount profile evolve.

Next: qualify broader clean-log histories before extending XFS admission, then
follow the [native filesystem and XFS roadmap](../storage/design/roadmap.md) for
transactions, durability, recovery/GC and XFS read-write. Gate transport, filesystem
recovery and mounted service behavior separately; offline parsing and synthetic
sectors alone do not establish device provenance or clean-unmount history. No
physical disk access follows from emulator qualification.

## 3. Display, input, terminal and desktop

With usable process/service boundaries, add authority-checked display/input and
buffer lifetimes, then native terminal sessions and the tiling desktop. Serial
diagnostic prompts are not an application terminal. Pending terminal/parser or
console increments must pass their own final integration gates before promotion.

Gate: input/output hotplug, window lifecycle/workspaces, clipboard authority,
Unicode/text shaping, resize/backpressure/EOF, session/job control, composition
and reset recovery. Use the [release inventory](system-release.md) for the full
application and accessibility requirements; functional references do not promise
Linux binaries, configuration, wire protocols or POSIX compatibility.

## 4. Language, runtime and native toolchain

Grow the language where the above consumers need it, retaining checked values,
private class state and explicit ownership. Runtime-capacity byte and copied-class
owners, move-only classes and synchronous borrows already exist; general lifetime/effect and
concurrency models, TypeScript-like type transformations and richer reflection
remain open. See the [compiler reference](../compiler/README.md) and
[library dependency plan](library-stack.md), rather than historical exclusions.

The hosted compiler has an [Aurora lexical phase](../compiler/LEXER.md) and
[complete bounded module parsing](../compiler/ARCHITECTURE.md#hosted-aurora-parser).
An explicitly selected, source-built predecessor emits the imported frontend;
current C1/C2 stages verify convergence. Aurora owns existing module grammar,
unresolved declaration admission, module/template resolution and resolved semantic/
ownership analysis through typed IR. Independent metadata, callable, frame and
call-graph checks also live in Aurora, alongside durable instruction storage,
structural CFG normalization and static entry, call, local-storage and scalar
admission. The source-owned whole-function verifier owns current values,
operand stacks, initialization, synchronous service loans, resource and
object-loan provenance, bounds evidence and the bounded FIFO worklist, with no
native semantic fallback. Bounded multi-owner borrowing enables the emitter
workspace to read instruction and metadata owners together; the formatter
shares append through exclusive mutable typed-buffer borrows.
The seed, or a cached first compiler, builds current C1/C2 with convergence; execution and ABI
tests qualify emission without a production fallback or historical-emitter dependency.
Qualification requires final-source pinned-container `merge`, normal BIOS/UEFI
and affected guest gates. Compiler or host-bridge changes additionally run
`release`, including the [seed's bootstrap check](../compiler/README.md#source-bootstrap)
and in-guest self-host row. Every guest family is required for releases and seed
changes; an ordinary compiler change retains affected-family scope.
Successful lowering-record projection now runs in Aurora, preserving exact
identity/ordering and filling pending metadata/instruction owners before independent
admission. The compiler is a hosted Aurora program: source file I/O, diagnostics
and artifact output run over `HostFiles`, allocation over the Aurora memory runtime.
The bounded test graph, ordinary UEFI console/session, production terminal painter
and existing console/hosted UART object composer now runs
in Aurora: it appends generated wrapper text and remaps selected private references
without changing source symbol bindings. The test graph also emits its bounded
register-move/tail-jump wrappers directly from the same table/ABI-derived recipe
used by predecessor/reference text; console/UART/painter wrappers still use GNU as.
The painter emits its source object directly and retains its existing Display-only
import and private entry ABI; production UART, diagnostics and timer policy stay native.
The checked single-object linker closes the supported guest object-to-executable
path. General assembler/linker support, complete native rebuilding and broader
runtime/file/process services remain separate self-hosting dependencies.

Gate: positive, rejection, adversarial, resource and ABI tests with independent
review; no unchecked assertion, visibility bypass or resource duplication. Then
build native assembler/linker/runtime/graphics components and self-host the
compiler/system with differential and multi-stage reproducibility checks.
Measure equivalent-C workloads before making performance claims. Compiler speed has
dropped with each frontend migration; record every change with
[scripts/compiler-speed.py](../compiler/ARCHITECTURE.md#compile-speed). Self-hosting
alone is not a compiler safety proof or a complete binutils/glibc/Mesa alternative.

## 5. Physical qualification and production readiness

Qualify the complete [Framework Laptop 13 / Ryzen 7 7840U](framework-13-7840u.md)
first, then only advertise tested [AMD tuples](amd-support.md). Gate: actual
machine/device discovery, isolation, power transitions, fault recovery, updates,
performance/energy and usable applications. Emulator evidence cannot substitute.
Production acceptance also needs an explicit trusted computing base, sustained
adversarial testing, scoped assurance arguments and recoverable releases.

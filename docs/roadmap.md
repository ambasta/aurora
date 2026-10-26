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
phase, CR carry and terminal outcome. Native effect execution and authenticated
lifecycle remain migration dependencies. The BIOS console uses the same Aurora
editor and sealed ConsoleSession for its bounded three-command session and
presentation; trusted native code retains interrupt transport and shutdown.
General terminal sessions and file services remain open.

## 1. Protected programs and file services

Build from the existing protected-domain fixtures, bounded scheduling, copied
request/reply IPC, cancellation/restart and Aurora policy functions. These are
working bounded mechanisms, not a general process or runtime API. The
[protected command console](program-console-contract.md) demonstrates one embedded
compiled application with scoped recovery and authority-failure qualification.
The file-call path now implements a reusable bounded read-service incarnation
for `wc` and `crc`, with fresh per-command caller/grant authority and full cleanup
after failure. The bounded retained source-owned mutable RAM-file service is also
implemented with bounded local qualification in [#234](https://github.com/ambasta/aurora/pull/234);
it is separate from that reusable read service and is not a general filesystem
or scheduler. The opt-in interactive scratchpad supplies real protected command
input/output and explicit user-facing
lifecycle outcomes, originally qualified in
[#235](https://github.com/ambasta/aurora/pull/235), and now includes explicit atomic append
to the existing volatile file and a read-only caller-computed CRC32C command. General program lifetime, mounted
durable storage and broader service APIs remain dependencies.

Build capability-scoped blocking request/reply on the bounded two-program
suspend/resume mechanism, then integrate protected-program startup/lifecycle and file
services with explicit resource limits, cancellation, partial I/O and reclamation.
Use RAM-backed service tests before claiming durable device-backed operation.
Gate: real compiled programs exercise allowed operations; foreign/stale authority,
exhaustion, restart and interrupted operations fail safely without cross-domain
access. Trusted C++/assembly ownership and commit boundaries remain explicit.

## 2. DMA-safe transport and persistent storage

Actual DMA conformance is blocked. Discovery, CPU-only table/queue preparation,
pin ownership and [test-only event/completion references](iommu-models.md)
are prerequisites, not observed hardware isolation or completion.
A permissible independently reviewed conformance path must establish default-deny
translation, invalidation completion, fault containment and safe reclamation
before active device authority. No physical disk access follows from this plan.

Gate: separately qualify transport and recovery before advancing the
[native filesystem and XFS roadmap](../storage/design/roadmap.md) to mounted file
services, transactions, durability, recovery/GC and XFS read-write. Offline XFS
parsing and RAM-sector correctness do not establish those outcomes.

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
One pinned checkpoint builds current C1/C2 with convergence; execution and ABI
tests qualify emission without a production fallback or historical-emitter dependency.
Qualification requires final-source pinned-container `merge`, normal BIOS/UEFI
and affected guest gates; releases and compiler bumps also run `release` and
every guest family, including the
[source-bootstrap gates](../compiler/README.md#source-bootstrap) for bumps.
Host record projection, conversion, quota/report transport and authorized source
file I/O remain native dependencies; module traversal and x86 text emission run
in Aurora.
The bounded frontend B/C, ordinary UEFI console/session, production terminal painter
and existing console/hosted UART object composer now runs
in Aurora: it appends generated wrapper text and remaps selected private references
without changing source symbol bindings. Frontend B/C also emit their bounded
register-move/tail-jump wrappers directly from the same table/ABI-derived recipe
used by predecessor/reference text; console/UART/painter wrappers still use GNU as.
The painter emits its source object directly and retains its existing Display-only
import and private entry ABI; production UART, diagnostics and timer policy stay native.
General assembler/linker and host runtime/file/process services remain
separate self-hosting dependencies.

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

# Compiler status and ownership

Source-bootstrap builds are restored. x86 text emission runs in Aurora, with one
source authority and no native fallback. `emitter-differential-*` in `slow` and
`full` hold its acceptance, diagnostics and ABI facts identical to the predecessor's
C++ backend and its C1/C2 outputs byte-identical; assembly and stack facts may now
differ from the predecessor so code generation can improve. Each final source
still needs its own full, convergence and BIOS/UEFI qualification.

| Component | Current source authority | Remaining work |
|---|---|---|
| Source loading and file I/O | C++ host | Native runtime and source-loading migration |
| Formatting | Aurora owns syntax roles, layout and findings; native host retains source transport and token/comment/reparse/idempotence checks | Final-source qualification required |
| Lexing and parsing | Aurora | Complete final-source predecessor/current convergence |
| Resolution, immutable linkage spelling and typed lowering | Aurora; native projection reads bounded copied name chunks; hash-chained index lookups, AVL order only for the two walked domains | Validate final integrated behavior and paired compile-time/output gates |
| Metadata, callable and frame admission | Aurora owns frame size and disjoint slot domains; C++ transports raw declarations | Retain host conversion, quota arithmetic and transport bounds |
| Instruction storage and static admission | Aurora owns service argument-vector shape and copied-argument contracts | Preserve admission before whole-function verification |
| Initialization and synchronous service loans | Aurora verification workspace | Final integrated allocation, cleanup and semantic qualification |
| Current values, operand stacks, bounds evidence | Aurora whole-function verifier | Final-source qualification; no native fallback |
| Ownership, provenance and worklist | Aurora whole-function verifier over the original paired source stores | Preserve diagnostic priority, declaration order, bounded FIFO work and nominal type identity |
| Call graph | Aurora | Validate final integrated behavior |
| x86 emission | Aurora, fixed native transport | Same acceptance, diagnostics and ABI facts as the C++ backend on the whole corpus, byte-identical C1/C2 (`emitter-differential-*`); inlines single-field getters; owned-value bounds checks and sizes use multiplies, not divq; no register allocation yet |
| Direct class fields | Aurora source and independent metadata admission share an 8,192-field cap, including empty, nested, resource and array fields | Existing leaf, byte, depth and array-element limits still apply |
| Private host bridge | One 84-entry table generates Aurora forwarders and host transport declarations; compiler facts supply layouts, symbols and raw enum validation | Preserve fail-closed conversion; native replacement remains incomplete |
| Bootstrap route | One digest-pinned checkpoint (C2 of `d4cbabb`, one hop from the C2 of `2fd30b2`, which the recorded six-stage source route built), then current C1/C2 with convergence | Bump in one hop: build an accepted main commit with the current checkpoint, pass C1/C2 convergence and the historical-oracle differential, then the release gates ([recipe](README.md#bumping-the-checkpoint-one-hop)) |
| Assembly, linking and hosted runtime | External bootstrap tools/C++ | Native replacements remain incomplete |

## Hosted Aurora parser

Aurora owns the module grammar. The C++ syntax adapter remains for formatting and
tooling; production lowering does not require a second C++ grammar. See
[modules](MODULES.md), [lexing](LEXER.md) and the [source-bootstrap recipe](README.md#source-bootstrap).

### Hosted Aurora expression parser

Expressions, declarations and bodies are part of the same Aurora parser. The
legacy C++ expression parser is retired; final-source convergence remains a required gate.

## Current boundaries

Metadata and instruction-flow masks share the source-owned `FlagMasks` table.
Its existing generated ABI bridge supplies native readers; structural passes
read the needed `u64` masks once per pass and keep the 32-byte code row unchanged.

Native adapters bind storage, convert records and enforce transport bounds. The
whole-function Aurora verifier borrows the original metadata and instruction
owners after admission and structural checks. It owns values, stack facts,
lifetimes, provenance, region identity, bounds evidence and the FIFO worklist.
There is no copied instruction stream, native semantic fallback or per-value
native bridge. All declarations, including unused functions, are checked before
the existing call-graph pass and publication.

Current facts occupy a dense, key-sorted prefix of owned storage. Lookup uses
binary search; insertion and erasure shift the affected suffix. Retained snapshots
preserve the same canonical order. Restoration validates that order and owning-root
relationships, then fills the prefix directly without tree insertion or rotations.
There are no parent/child links, heights or free-list records. Existing owner access,
active-fact checks, initialization epochs and allocation limits remain. These logical
operation counts do not imply constant-cost indexed access through the runtime owner.

The private host bridge admits the complete source report, including when no
metrics pointer was requested. It checks transport/status/error/metric bounds,
not the semantic truth of a successful report. A started report publishes partial
metrics before rejection; a not-started failure preserves the caller's metrics.
RAII releases the actual eleven source owners before destroying their region.
Allocation and integrity failures remain Internal; semantic errors retain their
exact typed-IR diagnostic text. The source allocation label is now
`hosted IR verification allocation failed`, rather than the retired initializer's
`hosted IR initialization allocation failed`.

The Aurora workspace owns synchronous service-loan acquisition, suspension,
helper-use validation, consumption, release and closure. Up to two ID-sorted records
per snapshot preserve exact identity and called state independently of acquisition
order; sparse IDs never size storage. Static admission still precedes dynamic checks.
Call validation precedes ordinary arguments and copied destinations; consumption
follows them. Non-service functions allocate no loan rows. Fact metrics count active
loans, while the initialization-payload metric includes actual service-row capacity,
excluding unused retained capacity and current rows.

The Aurora verification workspace also owns local-object logical
completion and construction history. One must/may pair per admitted object slot
replaces native whole-object and nested-field completion sets; complete copies
and construction mark them together. Physical scalar initialization stays a
separate observation, so empty/nested values and typed-owner snapshots retain
their stricter completion requirements. The same source verifier owns lifetime,
resource-token and object-loan checks. Retained-fact metrics count the compressed object pair;
payload metrics include the local scalar, object and receiver-field bit domains.

Receiver initialization uses one must/may pair per canonical direct field. Scalar,
array and class initializers always write a whole field; disjoint admitted leaf
ranges and joins preserve this invariant. Metadata derives physical and logical
observations separately, including vacuously initialized empty payloads. Constructors
start empty; ordinary receivers and the first borrowed formal's derived observation
start complete without granting new receiver authority. Resource-only fields remain
outside these facts. Source resource facts retain their tokens, region and loan checks.
Receiver fact counts are compressed field counts, not the old per-leaf cardinality;
all classes admit at most 8,192 direct fields, including private and zero-leaf
fields. A class-array field counts once; each nested class is admitted separately.
The shared cap preserves the existing 8,192-scalar flat-local boundary and bounds
receiver storage to 128 word pairs (2,048 bytes per snapshot), independently of
physical payload. Existing depth-four and array-element limits remain in force.
The four initialization pools retain the independent 1,209,026,560-byte logical
payload cap across current and retained storage, within a separately checked
region grant for all eleven owner pools. Growth refusal uses terminal allocation failure
and owner cleanup. Allocation headers, metadata and other workspaces are outside
this budget; resize briefly holds old and replacement storage together, so this
is not a transient-memory or whole-process RSS ceiling. The field cap does not
reduce that independent budget: up to 65,536 retained local-state snapshots
dominate it, and pools allocate on demand rather than reserving the ceiling.

The verifier protects the backend against malformed internal IR. It is not a
verified compiler or a proof of Rust-equivalent safety. C++ host code, generated
bridges and Aurora emission remain trusted. Kernel execution also needs its separate
image, stack and authority checks.

## Aurora emission boundary

`x86_module.au` consumes one mutable `EmitWorkspace` and the existing readonly
`MetadataStore` and `InstructionStore`. The validated capsule gates the private
owner bridge and checks that both stores are the original admitted pair. The
host transfers only retained callable IDs in emission order and requested ABI
source/member names. It never serializes another instruction inventory.

`x86_scalar.au`, `x86_objects.au` and `x86_resources.au` select all 85 instruction
forms. Shared source helpers own widths, payload-only copies, owner transfers,
padding, stack probes and private argument records. The source driver owns both
peepholes, linkage, reflection ordering, literal IDs and traps. `x86_facts.au`
serializes stack and ABI JSON, including invalid-byte escaping. Both are explicit
optional artifact requests against the same live emitted `ValidatedModule`.
The internal C++ `stackFacts()` compatibility map and JSON decoder are removed;
`stackFactsJson(validated)` follows the same ownership contract as ABI requests.
Tests inspect the requested JSON independently. No JSON is serialized or decoded
on an ordinary compile without a sidecar request, and no IR owner is retained.

The workspace has bounded pools and sticky executable-emission failures. Assembly
seals first; a named `Artifact` selector prepares one shared optional suffix for
stack or ABI JSON. A new request discards only that suffix and ABI name ingress,
so stack/ABI ordering and retry after a malformed optional request preserve the
executable and source facts. Failed executable emission requires a fresh workspace.
Incomplete/failed artifacts are not extractable. The host reads copied 512-byte
chunks; `ArtifactWriter` retains its single-write 64 MiB limit and atomic replacement.
The original emitted module must remain alive while requesting sidecars; moving
its validated owner is supported. Before using cached roots, the host checks the
supplied live instruction owner's unique, non-wrapping region generation and its
original metadata pairing. A later module cannot revive stale roots through
allocator-address reuse. This retains no source owners or metadata snapshot.

Workspace extents and the region's final logical payload quota are checked and
count-derived from retained functions, reflection views and published instructions;
there is no fixed million-row limit or bitmap sized by pruned callables. Optional
ABI-name rows/bytes are bounded by their minimum contribution to the requested
64 MiB JSON artifact, with a separate runtime-name allowance. Requested stack
JSON has a checked bound of twice assembly bytes plus conservative per-function/
per-call overhead. Actual elapsed time and peak RSS, including transient resizing
and native copied strings, remain unmeasured for this source draft.
`x86.hpp` contains the public interface only; no production fallback remains.

Each checkpoint bump builds with the pinned checkpoint from
[the bootstrap recipe](README.md#source-bootstrap), compares full assembly and
both sidecars to the external old compiler, checks all existing backend/host
artifact gates and C1/C2 convergence, measures time and peak memory, then runs the
final-source GCC 16 full suite plus normal BIOS/UEFI and affected profiles.

## Compile speed

The nine `ir_verification*.au` modules implement whole-function verification.
`ir_verify.cpp` retains only the native orchestration of source admission,
verification, graph checks and publication; `ir_verify.hpp` exposes metrics.
The obsolete native dynamic verifier and production initialization adapter are
removed. The byte-exact old initialization source remains solely as a historical
emitter-corpus fixture, not as a production fallback or current-verifier proof.
Test-only source probes exercise the current workspace without a production
friend, accessor or widened publication boundary. Final-source generation,
regressions and performance comparison remain required after this migration.
Control state observes the effective receiver of a named borrowed root, while
lexical receiver authority and implicit root seeding remain separately guarded.
Four isolated bound-root contracts matched independently observed native outcomes,
diagnostics and partial metrics byte-for-byte for the reviewed correction. They
now join the 59 preserved contracts; the final 63-case run and integrated
qualification remain pending. The existing borrowed object suite already covers
forwarding; these contracts add exact comparison scope.

The formerly timing-out XFS input compiled in 12.7 seconds after metadata-name
sharing and lookup simplification, versus 32.8 seconds before them, with identical
assembly. This is one diagnostic input, not a whole-compiler benchmark; the full
XFS test and final integrated suite still determine acceptance.

## Acceptance and next step

Each deletion-first change requires final-source GCC16 full validation, generated
ABI checks and multi-stage convergence; no execution waiver applies.

Language contracts: [values](VALUES.md), [ownership](OWNERSHIP.md),
[generics](GENERICS.md), [scalars](SCALARS.md), [services](SERVICES.md),
[stack probes](STACK-GUARDS.md). Project direction: [roadmap](../docs/roadmap.md).

## Source formatter boundary

The formatter runs one bounded layout operation over the admitted Aurora arena.
It marks only executable statement/initializer expression trees, preserving the
former formatter's distinction from type/template expressions. Input is copied
once through a synchronous span; no input pointer or source owner is retained.
Both input and output retain the 1 MiB limit. Each scratch pool has at most
1,048,577 rows, grows geometrically, and is additionally constrained by the
count-derived region quota. Findings and output are readable only on completion;
allocation/output failure and repeated preparation are terminal. Workspace owners
are released before the parser arena and region. Payload quota excludes allocation
headers and transient old/new resizing storage; process peak memory is separate.
A shared `append_row` helper synchronously borrows each mutable typed row buffer
for growth and storage. Callers snapshot receiver-derived arguments before the
exclusive field loan and update counts afterward; ownership and cleanup remain
with the workspace. The replacement sixth source-bootstrap checkpoint supplies
this capability without adding a stage. Qualification still requires the final
integrated-source `full` and applicable boot/emulator gates.

The host retains the existing two parse/layout passes, token/comment equivalence
and idempotence safeguards. It copies completed chunks and validated finding
coordinates into source-backed results. Formatting does not resolve imports.

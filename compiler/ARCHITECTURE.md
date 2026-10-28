# Compiler status and ownership

Source-bootstrap builds are restored. x86 text emission runs in Aurora, with one
source authority and no native fallback. `hosted-lexer-bootstrap` holds its C1/C2
outputs byte-identical; assembly and stack facts may differ from the predecessor
so code generation can improve. Each final source
still needs its own full, convergence and BIOS/UEFI qualification.

| Component | Current source authority | Remaining work |
|---|---|---|
| Module traversal | Aurora owns discovery requests, byte, duplicate/cycle/depth/file limits, dependency postorder and every loading diagnostic; C++ retains authorized file opening and bytes | Native runtime/file I/O migration |
| Formatting | Aurora owns syntax roles, layout, findings, token/comment/reparse/idempotence checks and their diagnostics; the native host transports source and output | Final-source qualification required |
| Lexing and parsing | Aurora | Complete final-source predecessor/current convergence |
| Resolution, immutable linkage spelling and typed lowering | Aurora; after lowering one Aurora call runs projection through emission and ABI declaration spelling; Aurora renders resolver, lowering, lint, source and pipeline diagnostics and the host only prints them | Validate final integrated behavior and paired compile-time/output gates |
| Metadata, callable and frame admission | Aurora owns frame size and disjoint slot domains; successful source projection, or the textual-IR test reader, writes pending raw declarations | Retain independent admission |
| Instruction storage and static admission | Aurora owns service argument-vector shape and copied-argument contracts | Preserve admission before whole-function verification |
| Initialization and synchronous service loans | Aurora verification workspace | Final integrated allocation, cleanup and semantic qualification |
| Current values, operand stacks, bounds evidence | Aurora whole-function verifier | Final-source qualification; no native fallback |
| Ownership, provenance and worklist | Aurora whole-function verifier over the original paired source stores | Preserve diagnostic priority, declaration order, bounded FIFO work and nominal type identity |
| Call graph | Aurora, including edge construction | Preserve retained-set order |
| x86 emission | Aurora, fixed native transport | Byte-identical C1/C2 (`hosted-lexer-bootstrap`); inlines single-field getters; owned-value bounds checks and sizes use multiplies, not divq; no register allocation yet |
| Direct class fields | Aurora source and independent metadata admission share an 8,192-field cap, including empty, nested, resource and array fields | Existing leaf, byte, depth and array-element limits still apply |
| Private host bridge | One 38-entry table generates Aurora forwarders, host transport declarations and a closed wrapper recipe; compiler facts supply layouts and symbols. A test graph adds 82 rows (readers of internal rows, the textual-IR reader, initialization probes) for test drivers only | Preserve fail-closed conversion; native replacement remains incomplete |
| Bootstrap route | One digest-pinned checkpoint (C2 of `d4cbabb`, one hop from the C2 of `2fd30b2`, which the recorded six-stage source route built), then current C1/C2 with convergence | Bump in one hop: build an accepted main commit with the current checkpoint, pass C1/C2 convergence, then the release gates ([recipe](README.md#bumping-the-checkpoint-one-hop)) |
| Assembly, linking and hosted runtime | External bootstrap tools/C++ | Native replacements remain incomplete |

## Hosted Aurora parser

Aurora owns the module grammar; the host has no syntax tree, grammar or lexer of
its own and only prints the diagnostics Aurora renders. See
[modules](MODULES.md), [lexing](LEXER.md) and the [source-bootstrap recipe](README.md#source-bootstrap).

### Hosted Aurora expression parser

Expressions, declarations and bodies are part of the same Aurora parser. The
legacy C++ expression parser is retired; final-source convergence remains a required gate.
`hosted-parser` checks each grammar entry and the whole-source entry against data
cases and a reviewed golden dump of the Aurora records and rendered diagnostics
([test contract](../docs/developer-test-contract.md)). It and the hosted lexer,
lowering and formatter drivers link the C1-built test graph, which alone exports
the readers of internal rows; `hosted-parser-invalid` links the resolver and
pipeline adapters with forged Aurora entries to test report transport, malformed
chunks and owner release on every failure exit.

## Current boundaries

Each source is lexed, parsed, admitted and ingested by Aurora; a rejected source
never reaches the Session, which renders and latches its rejection from the copied
result and the lent bytes. Module loading advances through
source-owned graph steps in the existing resolver Session. Transient scratch frames
track active ancestry and are cleared before ingestion. Completed module
order/scopes and import bindings persist; resumption replays unfinished ancestry,
bounded by 64 files and depth 16. Duplicate
checks happen at each edge, and depth precedes active/completed checks. Aurora also
validates each requested name, maps it to its relative path, charges every source
against the 1 MiB file and 4 MiB graph limits and, at the next step, checks that the
requested module's header spells the name in an interface unit; it renders each
of these rejections. Host opening, not-found/ambiguity across roots, read errors,
inode authority and overlays remain native.
The explicit-order in-memory resolver API remains separate compatibility transport,
not a fallback traversal. No additional owner, callback or runtime capability is used.

After successful lowering the host makes one Aurora call, `compiler_pipeline::run`
(`pipeline.au`). It consumes the resolver Session and, in the Session's region,
projects it, admits the metadata, admits and structures the instructions,
verifies every declaration, checks the call graph and selects retained
functions, publishes, then emits code and the requested stack and ABI facts. Its
`Result` holds those artifacts and the rendered unread-local warnings, or the first
failure: a stage and the failing store's reason, which Aurora renders with its
message and code (the metadata, instruction and verification message tables live
in `pipeline.au`). Every store shares the Session region's existing
loose ceiling; the separate grants the host used to derive for projection,
metadata, instructions, each function's verification, the graph and emission are
gone. Textual IR (`tests/tools/air.au`, test tooling) enters at the same point:
its reader fills the pending stores, admits the metadata, gathers the case's ABI
declarations and calls `compiler_pipeline::stages`, which runs everything from
instruction admission on and can list the published IR instead of emitting.

Projection borrows the readonly resolver Session and one mutable
`ProjectionWorkspace`. Aurora checks row ownership, exclusive operand
ranges (including discarded instruction payloads), nominal/type domains and all
85 active instruction shapes. Canonical row-ID ordering preserves callable IDs,
class/enum byte order, numeric descriptor/scope order and frame-slot ordering.
Interned names and literals are copied into the durable owners; no Session view
or scratch owner survives projection.

The same traversal counts against an empty pending pair, which is then released,
and fills exactly allocated metadata/instruction capacities; measurement never
writes or admits a destination. Fill checks every count and pending state before
returning. Projection scratch is released before metadata admission. When ABI
facts are requested, `pipeline_declarations.au` then reads the root module's
record, enum and function declarations from the Session and finds each in the
admitted metadata by its linkage spelling; function rows cover every declared
callable because the facts print only retained ones. The Session is released
before instruction, CFG, lifetime and graph admission. No native success fallback
remains. Lowering sorts the initial layout order itself.

Module loading, the resolver and lowering render a rejection into the Session's
byte pool just before the Session latches it, ending with a `report` metadata row
that names the message bytes, the module-relative span and, for loading, the
code; nothing appends after a latched rejection, so that row is the Session's
last. Loading covers byte limits, source admission and every import-graph
rejection, prefixed `module NAME: ` when the source answers an import; storage
failures report the allocation or transport message. Type and template-id
spellings expand on the scratch stack without recursion, bounded at depth 128.
The host copies the report through `resolver_report`, 384 message bytes per call,
and prints it; `pipeline_diagnostic` copies the failure or the rendered lint
warnings, ordered by offset, the same way, and the formatter and the bootstrap
object composer report through `formatter_diagnostic` and `object_report`. Code
numbers are the printed ones (4001 is AU4001). The Session region
has no host-computed ledger: every pool is a checked i64 byte extent bounded by
the input limits Aurora enforces, so the region grants that range and allocation
failure remains the only other refusal.

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

The pipeline stops at the first unsuccessful report. A started report publishes
its metrics into the `Result` before rejection; a not-started failure keeps the
previous function's. Allocation and integrity failures remain Internal; semantic errors retain their
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
`MetadataStore` and `InstructionStore`. The pipeline adds the retained callable
IDs in graph order and the declaration spellings itself; no host transport
remains between publication and the sealed artifacts, for compilations and
textual-IR fixtures alike.

`x86_scalar.au`, `x86_objects.au` and `x86_resources.au` select all 85 instruction
forms. Shared source helpers own widths, payload-only copies, owner transfers,
padding, stack probes and private argument records. The source driver owns both
peepholes, linkage, reflection ordering, literal IDs and traps. `x86_facts.au`
serializes stack and ABI JSON, including invalid-byte escaping. Both are explicit
optional artifact requests; a compilation seals and copies each in turn.
Tests inspect the requested JSON independently. No JSON is serialized or decoded
on an ordinary compile without a sidecar request, and no IR owner is retained.

Outgoing 56-byte span descriptors use one register-preserving contiguous copy
from the admitted local slot to the disjoint argument record; all seven words
and the temporary stack-save facts are retained. Service records clear only
class gaps, narrow-scalar slack and final alignment padding before publishing
the fully stored record. Text and object emission use the same recipes.
Canonical contiguous u8 receiver-array initialization uses a compact exact fill
from eight bytes upward, preserving registers/arithmetic flags and accounting
for its 24-byte stack save; no initialized byte or neighboring padding is elided.

The workspace has bounded pools and sticky executable-emission failures. Assembly
seals first; a named `Artifact` selector prepares one shared optional suffix for
stack or ABI JSON. A new request discards only that suffix and ABI name ingress,
so stack/ABI ordering and retry after a malformed optional request preserve the
executable and source facts. Failed executable emission requires a fresh workspace.
Incomplete/failed artifacts are not extractable. The host reads copied 512-byte
chunks; `ArtifactWriter` retains its single-write 64 MiB limit and atomic replacement.
A compilation copies code, stack facts and ABI facts into its `Result` as each is
sealed. Requested stack JSON has a checked bound of twice assembly bytes plus
conservative per-function/per-call overhead.

Each checkpoint bump builds with the pinned checkpoint from
[the bootstrap recipe](README.md#source-bootstrap), checks the existing backend/host
artifact gates and C1/C2 convergence, records timings and limits, then runs the
final-source merge and release suites, every guest family and normal BIOS/UEFI.

## Compile speed

The nine `ir_verification*.au` modules implement whole-function verification.
Admission, verification, graph checks and publication run in `pipeline.au`
(`stages`), for compilations and textual-IR fixtures alike; its `Result` carries
the last started function's verifier metrics. There is no C++ IR model: the
obsolete native dynamic verifier, production initialization adapter and the
fixture-side `ir::Module` reader, codec, owners and orchestration are removed. The retired historical emitter corpus remains in Git history, not as
a production fallback or current-verifier proof.
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

One Aurora call owns the whole operation: it lexes, parses and admits the source
(the resolver's `parse_source`), lays it out, relexes the output and requires the
same tokens and line comments in the same order, parses the output and formats it
again into a second workspace, requiring identical bytes. Layout marks only
executable statement/initializer expression trees, preserving the former
formatter's distinction from type/template expressions. Input is copied once
through a synchronous span with the admission limits; no input pointer or source
owner is retained. The workspace moves into the call with the host region, which
also backs the call's parse arena and second workspace, and moves back.
Both input and output retain the 1 MiB limit. Each scratch pool has at most
1,048,577 rows, grows geometrically, and is additionally constrained by the
count-derived region quota. Findings (the source's, then the output's) and output are readable only on
completion, and the output also after its own rejection; a rejection, a refused
output, allocation/output failure and repeated preparation are terminal. The
workspace is released before its region. Payload quota excludes allocation
headers and transient old/new resizing storage; process peak memory is separate.
A shared `append_row` helper synchronously borrows each mutable typed row buffer
for growth and storage. Callers snapshot receiver-derived arguments before the
exclusive field loan and update counts afterward; ownership and cleanup remain
with the workspace. The replacement sixth source-bootstrap checkpoint supplies
this capability without adding a stage. Qualification still requires the final
integrated-source `full` and applicable boot/emulator gates.

The host keeps the 1 MiB bound, copies completed chunks and validated finding
coordinates into source-backed results, and prints Aurora's rendering of a
rejection (`rejectSource`) or a refusal's existing message. Formatting does
not resolve imports.

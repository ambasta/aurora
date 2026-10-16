# Compiler status and ownership

Source-bootstrap builds are restored. x86 text emission runs in Aurora, with one
source authority and no native fallback; `emitter-differential-*` in `slow` and
`full` hold it byte-identical to the predecessor's C++ backend. Each final source
still needs its own full, convergence and BIOS/UEFI qualification.

| Component | Current source authority | Remaining work |
|---|---|---|
| Source loading and file I/O | C++ host | Native runtime and source-loading migration |
| Lexing and parsing | Aurora | Complete final-source predecessor/current convergence |
| Resolution and typed lowering | Aurora | Validate final integrated behavior |
| Metadata, callable and frame admission | Aurora owns frame size and disjoint slot domains; C++ transports raw declarations | Retain host conversion, quota arithmetic and transport bounds |
| Instruction storage and static admission | Aurora owns service argument-vector shape and copied-argument contracts | C++ retains dynamic loans, lifetimes, physical initialization and logical completion |
| Initialization and synchronous service loans | Aurora workspace | Resource ownership and object provenance remain native |
| Current values, operand stacks, bounds evidence | C++ verifier | Migration frozen; unmerged draft is not current functionality |
| Ownership, provenance and worklist | C++ verifier; Aurora owns entry-binding uniqueness | Continue deletion-first migration; retain dynamic checks |
| Call graph | Aurora | Validate final integrated behavior |
| x86 emission | Aurora, fixed native transport | Byte-identical to the C++ backend on the whole corpus in both profiles (`emitter-differential-*`); compile time 1.05x the C++ backend |
| Private host bridge | One 107-entry table generates Aurora forwarders and host transport declarations; compiler facts supply layouts, symbols and raw enum validation | Preserve fail-closed conversion; native replacement remains incomplete |
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

Native adapters still bind storage, convert records and enforce transport bounds.
Those checks do not justify duplicated semantic policy. Static source admission
and dynamic native lifetime/provenance checks have different inputs; remove a
native check only after establishing which authority replaces it.

Aurora admits the unique entry-binding prefix and immutable service roots/kinds.
Native code derives region identity once per function, checks region operands
against that binding, and retains object lifetime and ownership provenance checks.
Neither immutable authority occupies CFG snapshots.

The Aurora workspace owns synchronous service-loan acquisition, suspension,
helper-use validation, consumption, release and closure. Up to two ID-sorted records
per snapshot preserve exact identity and called state independently of acquisition
order; sparse IDs never size storage. Static admission still precedes dynamic checks.
Call validation precedes ordinary arguments and copied destinations; consumption
follows them. Non-service functions allocate no loan rows. Fact metrics count active
loans, while the initialization-payload metric includes actual service-row capacity,
excluding unused retained capacity and current rows.

The existing Aurora initialization workspace also owns local-object logical
completion and construction history. One must/may pair per admitted object slot
replaces native whole-object and nested-field completion sets; complete copies
and construction mark them together. Physical scalar initialization stays a
separate observation, so empty/nested values and typed-owner snapshots retain
their stricter completion requirements. Native code retains lifetime, resource
token and object-loan checks. Retained-fact metrics count the compressed object pair;
payload metrics include the local scalar, object and receiver-field bit domains.

Receiver initialization uses one must/may pair per canonical direct field. Scalar,
array and class initializers always write a whole field; disjoint admitted leaf
ranges and joins preserve this invariant. Metadata derives physical and logical
observations separately, including vacuously initialized empty payloads. Constructors
start empty; ordinary receivers and the first borrowed formal's derived observation
start complete without granting new receiver authority. Resource-only fields remain
outside these facts. Native code retains their tokens, region and loan checks.
Receiver fact counts are compressed field counts, not the old per-leaf cardinality;
zero-leaf field counts use checked dynamic extents rather than a storage-size cap.
Each workspace's region grants at most 1,209,026,560 logical payload bytes across
its current and retained pools. Growth refusal uses terminal allocation failure
and owner cleanup. Allocation headers, metadata and other workspaces are outside
this budget; resize briefly holds old and replacement storage together, so this
is not a transient-memory or whole-process RSS ceiling.

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

`x86_scalar.au`, `x86_objects.au` and `x86_resources.au` select all 84 instruction
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

The next qualification must source-build with the explicit three-root predecessor
in [the bootstrap recipe](README.md#source-bootstrap), compare full assembly and
both sidecars to the external old compiler, check all existing backend/host
artifact gates and C1/C2 convergence, measure time and peak memory, then run the
final-source GCC 16 full suite plus normal BIOS/UEFI and affected profiles.

## Compile speed

The native verifier implementation lives in `ir_verify.cpp`, compiled into the
existing hosted frontend library. `ir_verify.hpp` exposes its metrics and retained
block-entry budget interface; body-only edits do not require rebuilding IR test
translation units or the resolver. Stage2 reuses the same host object, while the
parser-invalid fixture compiles the implementation with its existing adapter stubs.

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

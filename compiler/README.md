# Aurora compiler

Aurora is an intentionally incompatible safe C++-inspired language. It has no
C header/macro layer, raw-pointer escape, unsafe block or C ABI. The hosted build
uses an Aurora-written [lexer](LEXER.md) and a bounded
[syntax parser](ARCHITECTURE.md#hosted-aurora-parser),
bootstrapped with an explicitly selected predecessor compiler.
Complete module syntax, declaration admission, module/template resolution and
resolved type/lifetime analysis through typed IR run in Aurora. The `ir_graph.au`
candidate independently checks normalized module call graphs and
selects retained functions. Aurora also owns independent metadata/layout, callable
and frame admission, structural CFG normalization, entry-parameter and static
call-site admission and whole-function value, lifetime and provenance verification.
After lowering, one Aurora call (`pipeline.au`) consumes the resolver Session and
projects it into metadata and instruction owners, admits and verifies them, checks
the call graph, publishes and emits code plus any requested stack and ABI facts;
the host copies out the artifacts or renders the first failure.
`builtin_catalog.au` is the only copy of the built-in type, scalar descriptor and
sealed service catalog: the resolver seeds its descriptors and lowering its scalar, service and initial layout prelude from it, and the host
takes service kinds/operations from the generated header and its admission
service groups from `catalog_summary`. On the resolver path Aurora lexes, parses, admits and ingests
each source and keeps its module header and imports; the host gets back only the
header name or a rendered rejection. aurora-fmt likewise parses, lays out and
verifies its output in one Aurora call. Aurora also decides module-loading policy
(names, relative paths, byte limits, headers and interfaces) and renders every
source, resolver, lowering and lint diagnostic (`diagnostics.au`,
`lowering_messages.au`): code, message and span, copied out 384 bytes at a time.
Opening files under the explicit roots, module-loading and pipeline messages,
diagnostic printing, allocation and artifact transport remain C++23, as does the textual-IR fixture path (`ir::validate`, `X86Emitter`), now test
tooling outside the compiler's library.
The Aurora-native x86-64 emitter
consumes the admitted source stores; the host retains artifact I/O.
The same semantic traversal feeds typed x86 forms to the text backend or the
checked relocatable-object backend selected by `--emit-object`. Object output
uses a separate typed workspace for code, symbols, labels and relocations. It
supports the source UART, ordinary UEFI console/session, production terminal painter
and hosted frontend forms, including readonly
literal data and RIP-relative references, plus size/public-field-count reflection
helpers with the same defining-module visibility and symbol-selection rules as
text output. Neither backend adds reflection access to private values.

Native console, UART and hosted frontend wrappers remain private bootstrap adapters.
For frontend B/C, `frontend_wrapper.au` emits the 104 wrappers directly, using the
same table/ABI-derived recipe that renders predecessor frontend A and the GNU
reference. The closed recipe admits at most 256 sorted hidden exports, 1024-byte
identifier names and six ordered register moves or readonly record-lane loads
per wrapper, followed by one symbolic PLT32 tail jump. It has no assembly parser,
stack operations, stores, calls, conditional branches or arbitrary external resolution.
The existing `ObjectWorkspace` owns encoding, fixups and ELF output; native code
only lends recipe bytes and transports the result. Invalid/reused workspaces
cannot expose output, and allocation failure releases every owner.

`private_object.au` composes frontend B/C, the ordinary UEFI console/session,
production terminal painter and existing BIOS console, UEFI device-fixture and
hosted UART objects. It is the only production object composer; build helpers
have no GNU partial-link fallback or composer selector. The source
input retains its eight-section ELF64LE x86-64 profile. Frontend wrappers use an
explicit eight-section profile with empty readonly data, no LOCAL definitions,
byte-aligned text and only hidden `aurora_hosted_*` exports. GNU console/UART/painter
wrappers retain their existing nine-section profile with empty data/BSS.
Composition preserves source symbol indices and LOCAL bindings, appends wrapper
text and exports, and remaps PLT32 references to selected source text symbols.
It does not evaluate relocations or provide a general linker. Unsupported
sections, writable payload, executable stacks, symbols and relocations reject
before output is sealed. Artifact reads retain the 64 MiB ceiling and atomic
output protects all input identities; language-source reads remain limited to
1 MiB. The GNU profile additionally admits exactly the existing
`__au_runtime_uart_initialize`, `__au_runtime_uart_next`, `__au_runtime_uart_put`,
`__au_runtime_console_entry`, `__au_runtime_console_value` and
`__au_runtime_terminal_paint` exports. The painter keeps its six-qword private
entry ABI and only its existing Display pixel runtime import; no console, UART
or timer authority moves with object production.

The pinned predecessor still emits frontend A as text. C1 emits frontend B and
its wrappers directly as objects linked into C2; C2 emits frontend C for
source-object, composed-object, ABI/header and stack-fact convergence. One
private-object test driver compares normalized wrapper and composed text,
readonly data, symbols and relocations with GNU references, checks malformed
recipe/ELF data and every allocation failure, and preserves source LOCAL
identity. Shared CLI input/output robustness is tested once in `diagnostics.py`.
Console, UART and painter objects run in their existing hosted drivers and
guest families. No checkpoint bump is needed. GNU assembler/linker and Linux
host I/O remain dependencies for frontend A, other text output, native
console/UART/painter adapters and final links. This adds no Aurora C ABI.

The verifier keeps active facts in a flat, sorted owner-backed prefix and restores
canonical snapshots directly, without rebuilding a search tree. Binary searches
and key-only cursor checks read a parallel 24-byte key pool rather than copying
the 200-byte active fact and its token, span and loan payloads on every probe.
The full row is fetched only where its payload or epoch is needed. Every
key-changing write updates both pools; allocation failure is terminal and closes
both actual owners, including a partially completed resize. The checked quota
includes the key pool. The workspace remains within the existing 520-byte class
bound by deriving its scalar-slot count from the already validated group counts.
Each compound storage operation captures its control row once and passes validated
counts to private helpers; owner extent, liveness, first-error and partial-publication
checks remain. Runtime owner validation still applies to each key access. This is
not a claim that all aggregate copies or the measured performance gap are gone.

Metadata name comparison borrows its validated byte ranges once. The hosted
adapter returns a checked contiguous span for inline reads; fragmented kernel
backings retain checked owner snapshots. Identity, extent, lifecycle and failure
checks remain mandatory. These access changes add no language features or unchecked views.

Hosted owner lookup uses a 64-slot direct-mapped cache per region, keyed by the
never-reused allocation ID, plus the last region found. Every unlink clears its
slot first, so a hit is the record the registry walk would find; the walk no
longer reorders the list. Region, success, ID and length checks are unchanged.
On the 46-module frontend workload this cut user instructions by 6.1% and user
cycles by about 4.5% (six alternating pairs, identical outputs).

Resolver index keys are found through hash chains threaded through the index
rows (bucket heads live in the first rows, rebuilt when the row count reaches a
power of two); only the two domains lowering walks in key order keep AVL links.
Ingest marks requested token ordinals instead of heapsorting the requests and
publishes each module's token references as one sorted range rather than one
index row per token. Visibility and reflection walk the owners' category lists
instead of all metadata, metadata name searches skip the prefix the key shares
with both bounds, and owned-value bounds checks and sizes avoid divq. Outputs
are byte-identical. Against the native-verifier baseline (`f2256be`), C2 on
the 47-input frontend now runs 0.65x the user instructions and 0.73x the
cycles; against `6c4871d`, a one-line `std.json` rejection takes 0.52x the
instructions and 0.58x the cycles on C1 (paired runs on a shared host; see the
commit messages for each step).

## Build and check

For a fresh checkout, use a local copy of the checkpoint compiler, or rebuild it
from source with `scripts/bootstrap.py rebuild`, and configure Meson with
its path using the [setup commands](#source-bootstrap) below. The ordinary
shortcuts reuse the configured graph:

```sh
make -C compiler
build/aurorac --module-root library examples/core_math.au -o build/core_math.s
build/aurorac --check --diagnostics=json examples/core_math.au --module-root library
make -C compiler test
```

Compiler-only testing uses the canonical Meson graph and is not root `full`.
`ir-exhaustive` (release suite only) retains codec inventory checks and runs the CLI
with temporary copies of the verifier or emitter, interposed on the pipeline entry,
that observe unknown forms or operators or lack a handler. Aurora dispatch
rejects these at runtime; it does not provide the former C++ visitor's compile-time exhaustiveness guarantee.
[Development and qualification](../docs/developer-test-contract.md) defines exact
routes, selected-artifact identity, explicit pinned compatibility and merge gates.
The optional [language server](lsp/README.md) has its own dependency and suite.

### Bootstrap evolution policy

New language features land first with independent library or product consumers.
Compiler adoption waits for a scheduled checkpoint bump: every input the
checkpoint compiles, including compiler-imported library helpers, must stay
within its supported language subset. Batch bumps at milestones or for a
justified set of compiler adoptions, rather than one bump per feature. A bump
reviews the new pin, its hop receipt, the release suite and the batched adoption
together. Keep every checkpoint commit reachable from main, with its receipt in
the bump PR, so each one can be rebuilt from the one before it.

### Source bootstrap

The build has one predecessor stage and a self-check, like GCC's
bootstrap-and-compare:

```text
checkpoint C0 --compiles--> C1 (aurorac) --compiles--> C2 (aurorac-stage2) --compiles--> frontend C
                            hosted-lexer-bootstrap: C1's frontend B and C2's frontend C identical
```

[`checkpoint.json`](checkpoint.json) names C0 by source commit and tree. C0 is
the C2 of main commit `ab255328` (four distinct borrowed roots with per-root
mutability), built in one hop from the C2 of `d4cbabb`; `history` lists the
earlier checkpoints. No compiler binary is committed, downloaded or pinned by
digest. Any C0 built from that source with the supported tools (GCC 16.2.0 or
newer, binutils 2.47 or newer) is accepted, and `hosted-lexer-bootstrap` checks
it the way GCC's `make compare` does: C1's frontend B must equal C2's frontend C.
Meson's `bootstrap_compiler` option names the executable; Ninja tracks it, so
replacing it regenerates the frontend.

To build C0 from source with no binary at all (host tools and Git):

```sh
python3 scripts/bootstrap.py rebuild --output build/checkpoint-ab255328a762
C0=$PWD/build/checkpoint-ab255328a762/aurorac
meson setup build/meson . "-Dbootstrap_compiler=$C0" "-Duefi_ld=$UEFI_LD"
meson setup build/meson-compiler . -Dkernel_images=false "-Dbootstrap_compiler=$C0"
meson test -C build/meson-compiler hosted-lexer-bootstrap
```

`rebuild` builds the historical C++ seed and Aurora stages
([below](#historical-route)), then every checkpoint in `history` and the current
one, each with the previous compiler and each passing its stage compare. Every
source is exported with `git archive` and verified against its recorded tree.
The recorded sources select their predecessor with an exact-version gate and,
from `2fd30b2` on, a digest of the binary they were first built with; `rebuild`
replaces those two scripts in its exported copies with this checkout's
minimum-version gate and a `select` that accepts the compiler it is given.
Keep `OUTPUT/aurorac` outside directories you delete, or rerun `rebuild`.

#### Bumping the checkpoint (one hop)

Pick an accepted main commit `NEW` whose compiler adopts the batched features.
Its `checkpoint.json` still names the current C0, so its own Meson graph accepts
C0:

```sh
git worktree add --detach build/hop-src NEW
python3 scripts/bootstrap.py hop --compiler "$C0" --source build/hop-src \
  --commit NEW --tree "$(git rev-parse NEW^{tree})" --output build/checkpoint-NEW
```

The hop checks that the checkout's files hash to `TREE`, configures NEW with C0
and the fixed options, builds C1 and C2, runs `hosted-lexer-bootstrap`, copies
NEW's C2 to `OUTPUT/aurorac` and writes `OUTPUT/receipt.json` (source,
predecessor, tool versions, commands, logs and timings). The bump commit names
NEW in `checkpoint.json`, moves the old checkpoint to `history`, and qualifies
with the release suite and the merge gates.

#### Historical route

The first checkpoint came from the six-stage source route kept in
[`bootstrap-history.json`](bootstrap-history.json): a GNU C++ seed and five
Aurora stages, each built by the previous one, ending at the `borrow` stage
`672821f`, whose C1 built the first checkpoint `2fd30b2`.

| Stage | Immutable source | Required predecessor capability |
|---|---|---|
| Historical seed | `bdf646f09d5e14c88124c4bc9e4f998beda16183` | GNU C++ source build; no Aurora predecessor |
| ABI facts | `17f4f1440e6faa9cdaf8711c04400854bdb60d9e` | Historical seed; adds compiler facts |
| Copied arguments | `c0ef02cc105de2b7699d8565f6a53f1dea9e1205` | ABI-facts compiler |
| Owner-field initialization | `bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4` | Copied arguments used by its frontend |
| Paired roots | `052f79d7995be93053f73659bcfc37687b00b341` | Region-backed owner-field initialization |
| Multiple roots and mutable typed buffers (`borrow`, oracle) | `672821f70f37b185c46690791bd00d74d4414403` | Paired-root frontend signature and ordered ABI facts |
| First checkpoint | `2fd30b2c252afda5fbf6e78c399bca1cae7bd04e` (its C2) | Three borrowed roots for the Aurora emitter; mutable typed-buffer borrows |
| Checkpoint C0 | `d4cbabbb692a5553d8b14641e145a2f5ddc6ca93` (its C2) | Readonly typed views, used by the compiler's own sources |

Direct skips between historical stages failed before producing comparable
frontend assembly (missing `--abi-facts`, incomplete class-argument names,
`move(named_local)` transfers, and a second or third borrowed root); the
commands and identities are in the corresponding PRs.

The checkpoint emits frontend A for current compiler C1; C1 emits B for current
compiler C2. The same compilation emits `--abi-facts` metadata for collected
resolved declarations and the exact emitted module. The closed private bootstrap
adapter generates its record layouts, enum values and bridge symbol targets from
those facts; this is not a general exported ABI. Frontends are emitted with
`aurorac --local-symbols`, which binds every generated function and reflection
entry locally without changing ABI or instructions (`--check` rejects it), so
only the wrappers are external. Initialization and emission use
one closed entry table in the existing bootstrap adapter for root authority,
argument-record names, host declarations and the five fixed register transports.
The facts normalizer accepts up to four distinct concrete owning roots, each
independently mutable or readonly. Tuple storage does not imply pointee mutability or prove
distinct ownership. Aurora forwards and owner lifetime/semantic checks remain
unchanged. Both stages generate their own facts and header. The existing bootstrap
test checks current C1/C2 assembly, object,
facts and header convergence, binds B to the frontend actually linked into C2, and compares current
C1/C2 corpus diagnostics/output. No compiler binary or generated frontend is
committed. The candidate's independent module graph pass runs in Aurora after all
source whole-function checks and before import pruning, without a C++ graph fallback.
Successful lowering-record projection runs in Aurora without native traversal or
per-value callbacks. Module file opening, optional ABI declarations, diagnostics
and quota/report transport remain native. Aurora now owns complete x86 text emission, including
stack facts and ABI JSON; its host adapter lends the two admitted owners and
copies bounded sealed output, with no native opcode fallback. Aurora owns metadata/layout,
callable/frame admission, durable instruction storage, structural CFG checks and
entry-parameter and static call-site admission.
Source verification and emission consume the same normalized storage; these
migrations still await execution qualification.

## Emitter qualification

The C++ x86 backend of the last historical stage, `672821f`, was retired after
the Aurora emitter matched its acceptance, diagnostics and ABI facts on the whole
corpus (see Git history). Emission is now checked by C1/C2 convergence in
`hosted-lexer-bootstrap` and by the execution suites. Record before/after
`scripts/compiler-speed.py` time and peak-memory observations for emitter changes.

Numeric register immediates use flag-preserving MOV encodings: nonnegative u32
patterns write the 32-bit register and zero-extend; negative i32 patterns use
the sign-extending immediate form; other patterns retain full-width `movabs`.
Text and direct-object emission make the same choice, including unsigned values
with a negative-i32 bit pattern. Symbol-address materialization and relocation
policy are unchanged; the emitter rebuilds offsets for the compact output.

## Supported source

- A file starts with `module name;` or `export module name;`; direct named imports
  use explicit `--module-root` directories. Namespaces and exports never bypass
  private members or defining-module lookup.
- Functions use `auto name(Type parameter) -> Result`; locals use an explicit
  type, mandatory initializer and optional `const`. Local `auto` deduction is absent.
- Types include i64/u64/u8/bool, closed nominal enums, inline classes, fixed
  arrays and the separately checked ownership/view/service modes below.
- Blocks, exact-bool `if`/`else`, `while`, return and restricted `static_assert`
  work. No `for`, `break` or `continue`; a loop conservatively may run zero times.
  Every continuing function path must return, and unreachable statements reject.
- Arithmetic, conversions and indexing are checked. Operands and arguments
  evaluate left-to-right. Array stores check their index before evaluating RHS.
  Constructor arguments snapshot left-to-right, then fields initialize in
  declaration order; direct owner fields may allocate or call a region-backed
  owner factory. Checked failure is fail-stop, with no exception unwinding.
- Decimal/binary integers, ASCII byte literals, exact-length byte-string array
  initializers and synchronous readonly literal arguments have exact scalar/byte
  rules. Comments use `//`; legacy `fn`/`let` and conventional C declarations reject.

## Component references

- [Scalars, literals and evaluation](SCALARS.md)
- [Classes and copied values](VALUES.md)
- [Generics, overloads and fixed storage](GENERICS.md)
- [Runtime owners, readonly views and object loans](OWNERSHIP.md)
- [Sealed synchronous Console/Display/Event services](SERVICES.md)
- [Modules, visibility and bounded host I/O](MODULES.md)
- [Frontend/IR/backend architecture](ARCHITECTURE.md)
- [Diagnostics, formatter and lint](TOOLING.md)

These are bounded mechanisms. General ownership/lifetime polymorphism,
concurrency/effects, arbitrary destructors, rich type algebra/reflection,
optimizer, separate binary compilation, complete runtime and self-hosting remain
open. Safety tests are not a proof of Rust equivalence or production readiness.

## Owned scalar safety and const

```text
own<i64> seed = own(40);
{
    mutref<i64> edit = borrow_mut(seed);
    write(edit, read(edit) + 2);
}
const own<i64> answer = move(seed);
```

`own<i64>` is an affine stack-resident scalar capability, not a heap allocation or a general resource implementation. `own(value)` initializes it; `move(name)` transfers its value and invalidates the old binding. Owners never support reassignment, even without `const`; unused owners may be dropped. Implicit owner copies are rejected.

`borrow(owner)` creates a shared reference. `borrow_mut(owner)` creates an exclusive reference and requires a non-const owner. Multiple shared references may coexist; shared/exclusive borrows cannot overlap. A borrowed owner cannot move, and an exclusively borrowed owner cannot be read through its original binding. `read` copies a scalar value through an owner/reference; `write` changes it through a non-const mutable-reference binding and returns the written value.

Const is deliberately stronger than shallow C++ smart-pointer constness: a const owner cannot be mutably borrowed, nor moved into a mutable owner. Moving it to another const owner is permitted. A `const mutref<i64>` binding cannot write through that binding. This does not provide arbitrary casts, type assertions or a way to remove constness.

Borrow lifetimes end at the declaring block's end, not at inferred last use. References cannot be returned, passed to functions, copied, rebound, placed in aggregates, or borrowed again. They target already-declared scalar owners only. At conditional joins an owner is unavailable if any continuing path moved it; return-only paths do not constrain later code. Unsupported reference escape and aggregate borrowing fail closed.

## Precise while-loop ownership rule

The compiler records incoming owner-liveness and borrow state before the condition. It checks the condition and body once under that state. Each continuing backedge must preserve every incoming local's owner-liveness and borrow counts; moving an outer owner on any continuing path is rejected, even if the condition is a constant or appears to permit just one iteration. Moves on paths that definitely return are permitted because those paths never take the backedge.

Body-local owners may be created, moved and dropped on each iteration. Body-local borrows expire at the iteration block's end. Existing outer references can be read/written according to their capability. Since the condition can initially be false, exit state restores incoming ownership facts; scalar/aggregate value mutations remain real runtime effects. Nested loops obey the same rule. There is no claimed general fixed-point lifetime solver, loop escape reference model or `break`/`continue` behavior yet.

## Working reflection

`size_of(Type)`, `type_id(Type)` and `field_count(Type)` are compile-time queries. `static_assert(bool_expression)` accepts literals, these queries, comparisons, logical negation, and exact-bool `&&`/`||` composition; general arithmetic constant evaluation and code generation remain deferred.

Builtin type IDs: i64=1, bool=2, own<i64>=3, ref<i64>=4, mutref<i64>=5. U64 has ID8 and size8; U8 has ID11 and size1; existing builtin sizes are 8,1,8,8,8. Scalar bool's logical size is one byte, but its current stack slot is eight bytes. Class IDs begin at 100 in deterministic graph declaration order and are compilation-graph-local; defining-module/native names determine source type identity. Mentioned array types have IDs `1000000 + 2*N + B`, where B is one for bool and zero for i64. U64 array IDs use `2000000 + N`; U8 arrays use `3000000 + N`. Class IDs cannot collide with either array range.

Classes admit at most 8,192 direct fields, public or private, including empty/nested values, resource fields and array fields. Each array declaration counts once and every nested class is checked independently; existing leaf, byte, containment-depth and array-length limits still apply. Excess fields produce `class exceeds 8192 direct fields` before receiver initialization storage is created.

`reflect_size(id)` and `reflect_field_count(id)` execute runtime lookups. Unknown IDs return zero. Descriptor entries are emitted for builtins, declared classes and array types used in storage/size/type-ID queries. Array size is `8*N`; arrays and builtins have zero named fields. Class field counts include public fields only, and class size includes all fields. Reflection cannot expose private values or bypass lifetime checks. Runtime queries use the defining module's visible descriptor view; unavailable/private IDs return zero, and reflection cannot implicitly import a type. Member traversal, invocation, mapped/conditional types and `keyof`-style type algebra remain design goals.

The Call family is registered for a compilation only when admitted syntax in its
complete import graph references `builtin::CallSession`, `builtin::CallResult`
or `builtin::CallStatus`, including unused templates and enum-case expressions.
Graphs without those references retain the historical builtin catalogue, IDs,
ABI facts and emitted reflection output. Comments, strings and user type names
do not activate it. Port and Serve are likewise independently syntax-activated
optional families; their appended identities do not change Serve-free or Port-free
catalogues. Registration does not alter per-module visibility.

`--referenced-reflection-only` is an explicit closed-image output mode. It emits
only helpers directly referenced by runtime metadata queries in retained, validated
IR. Every source function, including unused imports, is still checked before
retention; queried helper bodies and scope visibility are unchanged. The default
keeps all existing external reflection symbols. Closed images must not rely on
handwritten/native calls to helpers that source queries do not retain. Closed
supervisors and their packed fixtures, source UART objects, the ordinary UEFI
console/session and the hosted frontend opt in, as do selected closed user images.
Other outputs retain their existing default inventories. Object composition
requires this closed reflection inventory and LOCAL source definitions. The compiler
retains queried helpers; image admission still checks imports, W^X and mixed-stack
bounds from compiler facts.

## Temporary machine integration

The bootstrap assembly boundary currently passes six scalar arguments in RDI, RSI, RDX, RCX, R8, R9 and returns RAX. It preserves RBP, does not touch RBX/R12–R15, and aligns RSP to sixteen bytes immediately before calls. Scalar-only programs generate no red zone, libc, heap allocation, SIMD or runtime-library calls. Resource programs explicitly link the hosted byte adapter described in OWNERSHIP.md. Sealed service graphs use checked service adapters and private source-symbol linkage. Console-only graphs have no owned-byte allocator dependency; the closed ConsoleSession+ByteRegion prefix can also link the existing byte adapter (see SERVICES.md). External assembly callers must provide canonical zero/one bools and correct stack alignment.

These temporary register choices are implementation machinery, not a source-level C ABI or binary interoperability promise. Only scalar-signature unqualified root functions retain unmangled names for the temporary bootstrap assembly bridge. Imported/namespaced functions use length-prefixed Aurora-native symbols. The compiler emits a complete import graph with per-defining-module reflection helpers; separately linking overlapping compiled graphs is not supported yet. A versioned Aurora-native ABI remains to be designed.

`examples/kernel.au` performs a mutable borrow, releases it, moves ownership and returns 42. `examples/class_values.au` demonstrates class copies/visibility/reflection. `examples/loops_arrays.au` demonstrates checked traversal and independent arrays.

Runtime-sized [typed copied-class owners](OWNERSHIP.md#runtime-sized-copied-class-ownership)
support the `syntax_arena.au` AST, explicit parser-frame and variable-arity
argument-edge, unresolved type-syntax and declaration/statement storage. Complete
module syntax, including namespaces, templates, classes and their complete members,
is parsed in one Aurora call that the resolver ingests directly; no C++ syntax tree
exists. A standalone type read returns an explicit ordinal/half cursor. Grammar
errors precede semantic admission for multiply-invalid files, including
cross-declaration cases, as
specified in [architecture](ARCHITECTURE.md#hosted-aurora-parser).
The replaced C++ grammar, syntax adapter and reference lexer are removed. Unresolved
declaration admission, module visibility, template resolution and resolved
type/lifetime analysis run in Aurora. Production lowers the resolved Session
directly to typed IR, without a resolved C++ AST round trip. The
pinned checkpoint remains the bootstrap starting point; this does not
establish whole-compiler self-hosting.

CFG joins require exact source lifetime, provenance and operand-stack agreement
before weakening the retained current value. An already unknown current stays
unknown without scheduling another visit; initialization joins independently
report changes. Current values are excluded from retained-fact metrics, so these
joins adjust only the initialization count and do not copy a native state.

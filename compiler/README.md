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
call-site admission. Aurora also validates lowering graph ownership and projects
exact raw metadata/instruction prefixes into the independent pending stores.
Module file loading, identity spelling and dynamic value/provenance verification
remain C++23. The Aurora-native x86-64 emitter
consumes the admitted source stores; the host retains artifact I/O.
GNU assembler/linker and Linux host I/O remain bootstrap dependencies.

## Build and check

For a fresh checkout, complete [source bootstrap](#source-bootstrap) once in the
selected pinned tool environment. Then the ordinary shortcuts reuse Meson:

```sh
make -C compiler
build/aurorac --module-root library examples/core_math.au -o build/core_math.s
build/aurorac --check --diagnostics=json examples/core_math.au --module-root library
make -C compiler test
```

Compiler-only testing uses the canonical Meson graph and is not root `full`.
`ir-exhaustive` retains compile-time verifier/codec inventory checks and runs the
source emitter against admitted fixtures with unknown observations and a removed
handler in temporary copies. Aurora dispatch rejects these at runtime; it does
not provide the former C++ visitor's compile-time exhaustiveness guarantee.
[Development and qualification](../docs/developer-test-contract.md) defines exact
routes, selected-artifact identity, explicit pinned compatibility and merge gates.
The optional [language server](lsp/README.md) has its own dependency and suite.

### Source bootstrap

The Aurora-native emitter requires three borrowed roots: its mutable output
workspace and the existing readonly metadata and instruction stores. The exact
main checkpoint `7811ba83730e9a8b4329da983a01e475d73999a6` supplies that language
capability. It is retained in main history, not by a new tag. The source-bootstrap
and qualification gates below are required for each integrated emitter candidate.

The current source no longer contains a C++ expression parser or raw compiler
seed. Meson requires `bootstrap_compiler`, an absolute executable path. Ninja
tracks that executable as an ordinary input; changing it regenerates the frontend.
The source build below establishes the predecessor's provenance. Acceptance still
compares the actual generated frontend and current compiler stages.

Start from a normal Git checkout containing the historical seed source
`bdf646f09d5e14c88124c4bc9e4f998beda16183` and the reviewed ABI-facts precursor
[`17f4f1440e6faa9cdaf8711c04400854bdb60d9e`](https://github.com/ambasta/aurora/commit/17f4f1440e6faa9cdaf8711c04400854bdb60d9e)
(retained by the annotated tag `bootstrap-abi-facts-v1`), plus the copied-argument
checkpoint [`c0ef02cc105de2b7699d8565f6a53f1dea9e1205`](https://github.com/ambasta/aurora/commit/c0ef02cc105de2b7699d8565f6a53f1dea9e1205)
(retained by `bootstrap-copied-arguments-v1`), and the owner-field checkpoint
[`bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4`](https://github.com/ambasta/aurora/commit/bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4)
(retained by `bootstrap-owner-field-initializers-v1`). The candidate adds the paired-root
ABI-facts dependency merged in PR #166 at immutable source commit
[`052f79d7995be93053f73659bcfc37687b00b341`](https://github.com/ambasta/aurora/commit/052f79d7995be93053f73659bcfc37687b00b341).
The emitter adds the multi-root checkpoint
[`7811ba83730e9a8b4329da983a01e475d73999a6`](https://github.com/ambasta/aurora/commit/7811ba83730e9a8b4329da983a01e475d73999a6)
after that paired-root hop. Prepare the source worktrees on the host, where Git is installed; the pinned
development image does not include Git:

```sh
git fetch origin tag bootstrap-abi-facts-v1
git fetch origin tag bootstrap-copied-arguments-v1
git fetch origin tag bootstrap-owner-field-initializers-v1
git fetch origin 052f79d7995be93053f73659bcfc37687b00b341
git fetch origin 7811ba83730e9a8b4329da983a01e475d73999a6
git worktree add --detach build/predecessor-source bdf646f09d5e14c88124c4bc9e4f998beda16183
git worktree add --detach build/abi-facts-source 17f4f1440e6faa9cdaf8711c04400854bdb60d9e
test "$(git -C build/abi-facts-source rev-parse HEAD)" = 17f4f1440e6faa9cdaf8711c04400854bdb60d9e
git worktree add --detach build/copied-argument-source c0ef02cc105de2b7699d8565f6a53f1dea9e1205
test "$(git -C build/copied-argument-source rev-parse HEAD)" = c0ef02cc105de2b7699d8565f6a53f1dea9e1205
git worktree add --detach build/owner-field-source bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4
test "$(git -C build/owner-field-source rev-parse HEAD)" = bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4
git worktree add --detach build/paired-root-source 052f79d7995be93053f73659bcfc37687b00b341
test "$(git -C build/paired-root-source rev-parse HEAD)" = 052f79d7995be93053f73659bcfc37687b00b341
git worktree add --detach build/multi-root-source 7811ba83730e9a8b4329da983a01e475d73999a6
test "$(git -C build/multi-root-source rev-parse HEAD)" = 7811ba83730e9a8b4329da983a01e475d73999a6
```

Then enter the [pinned development environment](../docs/local-development.md)
with `./scripts/container.sh bash` and run the build commands from the current
checkout. Keep the historical worktrees and compilers separate from current source:

```sh
meson setup build/predecessor-seed build/predecessor-source -Dkernel_images=false
meson compile -C build/predecessor-seed -j 2 aurorac
SEED=$(realpath build/predecessor-seed/aurorac)
meson setup build/abi-facts-compiler build/abi-facts-source -Dkernel_images=false \
  "-Dbootstrap_compiler=$SEED" \
  "-Dbootstrap_compiler_sha256=$(sha256sum "$SEED" | cut -d ' ' -f 1)"
meson compile -C build/abi-facts-compiler -j 2 aurorac
FACTS=$(realpath build/abi-facts-compiler/aurorac)
meson setup build/copied-argument-compiler build/copied-argument-source -Dkernel_images=false \
  "-Dbootstrap_compiler=$FACTS"
meson compile -C build/copied-argument-compiler -j 2 aurorac
ARGUMENTS=$(realpath build/copied-argument-compiler/aurorac)
meson setup build/owner-field-compiler build/owner-field-source -Dkernel_images=false \
  "-Dbootstrap_compiler=$ARGUMENTS"
meson compile -C build/owner-field-compiler -j 2 aurorac
FIELDS=$(realpath build/owner-field-compiler/aurorac)
meson setup build/paired-root-compiler build/paired-root-source -Dkernel_images=false \
  "-Dbootstrap_compiler=$FIELDS"
meson compile -C build/paired-root-compiler -j 2 aurorac
PAIR=$(realpath build/paired-root-compiler/aurorac)
meson setup build/multi-root-compiler build/multi-root-source -Dkernel_images=false \
  "-Dbootstrap_compiler=$PAIR"
meson compile -C build/multi-root-compiler -j 2 aurorac
P=$(realpath build/multi-root-compiler/aurorac)
meson setup build/meson . \
  "-Dbootstrap_compiler=$P" "-Duefi_ld=$UEFI_LD"
meson setup build/meson-compiler . -Dkernel_images=false \
  "-Dbootstrap_compiler=$P"
meson compile -C build/meson-compiler -j 2 aurorac aurorac-stage2
meson test -C build/meson-compiler --no-rebuild --num-processes 1 \
  hosted-lexer-bootstrap compiler-test-inventory
```

The digest option above belongs only to the unchanged historical precursor graph.
The working route remains six source-built predecessors; no additional skip has
passed direct compilation. The existing register-carry hop remains omitted.

| Stage | Immutable source | Required predecessor capability |
|---|---|---|
| Historical seed | `bdf646f09d5e14c88124c4bc9e4f998beda16183` | GNU C++ source build; no Aurora predecessor |
| ABI facts | `17f4f1440e6faa9cdaf8711c04400854bdb60d9e` | Historical seed; adds compiler facts |
| Copied arguments | `c0ef02cc105de2b7699d8565f6a53f1dea9e1205` | ABI-facts compiler |
| Owner-field initialization | `bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4` | Copied arguments used by its frontend |
| Paired roots | `052f79d7995be93053f73659bcfc37687b00b341` | Region-backed owner-field initialization |
| Multiple roots | `7811ba83730e9a8b4329da983a01e475d73999a6` | Paired-root frontend signature and ordered ABI facts |
| Current C1/C2 | Final integrated source | Three borrowed roots for the Aurora emitter |

| Direct skip experiment | Observed boundary | Route status |
|---|---|---|
| Seed → copied-argument source | `--abi-facts` unsupported | Retain ABI-facts stage |
| ABI-facts → owner-field source | Class argument requires a complete local name | Retain copied-argument stage |
| Copied-argument → paired-root source | Owning transfer requires `move(named_local)` | Retain owner-field stage |
| Owner-field → multi-root source | Second borrowed root rejected | Retain paired-root stage |
| Paired-root → current source | Third borrowed root rejected | Retain multi-root stage |
| Each still earlier compiler → current source | Missing facts or second borrowed root rejected | No direct replacement checkpoint established |

These attempts failed before producing comparable frontend assembly; they are
negative diagnostics, not convergence or qualification. Commands, exact source
and compiler identities, timings, peak memory, host load and failed artifacts
belong in the accompanying PR/retained evidence rather than this status table.

| Next checkpoint decision | Required evidence before changing the route |
|---|---|
| Replace the largest experimentally buildable suffix with one checkpoint | Build that exact source directly with the proposed earlier compiler; compare generated frontend assembly byte for byte against its normal-route build, then build the next source through both routes |
| Admit a new stage or replacement | Record its complete historical-seed source route, current C1/C2 assembly/object/facts/header and corpus convergence, and uninterrupted final-source full qualification; retain failed attempts without waivers |
| No successful shorter route | Keep the working six-stage route; no speculative checkpoint or new stage |

A retained compiler may be reused only with its exact source/build/tool provenance
and qualification receipt, not by filename or digest alone. Current setup selects
the resulting predecessor by path; its deprecated digest option is ignored and
retained solely for existing-directory compatibility.

Both ordinary default directories are now configured: `make`/`make test` use the
image-enabled graph, while `make -C compiler test` uses the hosted-only graph.
For other configurations, repeat setup with the selected path and use
`MESON_BUILD_DIR`. Keep using the same host/container path layout so configured
absolute executable paths remain valid. An unconfigured directory needs explicit
setup; the wrapper does not guess a predecessor.

`BOOTSTRAP_COMPILER=/absolute/path/to/aurorac make test` requests a different
predecessor. The wrapper reconfigures an implicit default build in place, preserving
its other options and files. An explicit `MESON_BUILD_DIR` with a different
selection is rejected with the exact reconfigure command. Without this variable,
the wrapper reuses the configured predecessor. The container launcher forwards
`BOOTSTRAP_COMPILER` literally; its path must be valid inside the container.

The predecessor emits frontend A for current compiler C1; C1 emits B for current
compiler C2. The same compilation emits `--abi-facts` metadata for collected
resolved declarations and the exact emitted module. The closed private bootstrap
adapter generates its record layouts, enum values and bridge symbol targets from
those facts; this is not a general exported ABI. Initialization and emission use
one closed entry table in the existing bootstrap adapter for root authority,
argument-record names, host declarations and the five fixed register transports.
Aurora forwards and owner lifetime/semantic checks remain unchanged. Both stages
generate their own facts and header. The existing bootstrap test checks current C1/C2 assembly, object,
facts and header convergence, binds B to the frontend actually linked into C2, and compares current
C1/C2 corpus diagnostics/output. No compiler binary or generated frontend is
committed. The candidate's independent module graph pass runs in Aurora after all
native function checks and before import pruning, without a C++ graph fallback.
Module file loading, requested identity spelling and instruction value/provenance
verification remain C++. Whole-module IR projection runs in Aurora. Aurora now owns complete x86 text emission, including
stack facts and ABI JSON; its host adapter lends the two admitted owners and
copies bounded sealed output, with no native opcode fallback. Aurora owns metadata/layout,
callable/frame admission, durable instruction storage, structural CFG checks and
entry-parameter and static call-site admission.
Native verification and emission consume the same normalized storage; these
migrations still await execution qualification.

## Source IR projection

`ir_projection.au` checks exclusive row/list ownership, all active instruction
schemas, closed identity payloads and discarded instructions. It sorts requested
identities once; native code spells only that demand set into a copied table.
A graph-only workspace is released before replay into a separately bounded Plan.
The immutable Session is stamped with its non-reused host Region incarnation;
the final source phase checks that stamp and the sealed row/operand counts.

Source measurement and fill agree on every raw pool, preserve canonical metadata
ordering, and copy literal bytes. A sorted name index uses binary search while
assigning byte offsets on first use in each pass, preserving output order.
Checked pool bases are cached before filling; owner layouts remain unchanged.
Graph-only scratch retires after validation, identity capacity shrinks after
deduplication, and the ordering tail uses actual class/function counts. Ordering
scratch retires after exact fill-count agreement, before retained-store copying.
Native success consumers read individual checked records from the sealed Session,
without duplicating its complete row/operand pools; failure reports still copy
only their fixed prefix. The Session outlives every borrowed projection read.
Pending-only typed setters fill independent
metadata and instruction regions exactly once; short, repeated and extra fills
reject. The Plan and Session are released before unchanged IR admission and
validation. Native code retains quota arithmetic, requested identity/diagnostic
rendering and capsule allocation, with no instruction-conversion fallback.

The migration's temporary native oracle compared all 16 raw pools on four
representative programs, including the complete frontend fixture; both the old
native stores and source-filled stores matched the Plan (128 pool comparisons),
with identical assembly and ABI facts. The retained lifecycle test injects
allocation failures and exhausted quotas and checks malformed tables, Session
substitution and pending-fill gates. These are focused migration receipts, not
final full-suite, convergence, performance or BIOS/UEFI qualification. The Plan's
raw output and intern storage are temporary additional memory; logical Region
quotas do not bound native vectors or allocator overlap.

## Emitter migration qualification

The source-built `7811ba8` predecessor still carries the C++ x86 backend, so it
is also the external old-backend oracle, never a production fallback. The
`emitter-differential-default` and `emitter-differential-closed` tests in `slow`
and `full` run the whole checked-in corpus through it and the current C2 compiler
in the ordinary and closed profiles; by hand:

```sh
python3 -B tests/compiler/emitter_differential.py \
  --old-compiler "$P" --new-compiler build/meson-compiler/aurorac-stage2 \
  --stage1-compiler build/meson-compiler/aurorac \
  --source-root "$PWD" --artifacts build/emitter-differential/default
python3 -B tests/compiler/emitter_differential.py \
  --old-compiler "$P" --new-compiler build/meson-compiler/aurorac-stage2 \
  --stage1-compiler build/meson-compiler/aurorac \
  --source-root "$PWD" --local-symbols --referenced-reflection-only \
  --artifacts build/emitter-differential/closed
```

Each new evidence directory retains all input/compiler hashes, exact commands,
diagnostics and assembly/stack/ABI artifacts. Accepted inputs must match byte for
byte; rejected inputs must agree and preserve every preexisting output. Any
mismatch, internal failure or watchdog timeout fails the gate and reports partial
coverage. Equal rejection is not emission coverage, so the gate also fails if any
historically supported input outside its fixed list of function-less modules is rejected.
Exactly `tests/compiler/call_service.au` and `tests/kernel-programs/call-client.au`
introduce the new Call API: each must produce the exact pinned predecessor AU2001
rejection without changing output files, then emit byte-identical assembly, stack
and ABI facts through current C1/C2 in each profile. Both remain in the corpus and
are counted separately from the unchanged historical rejection set. This narrow
applicability rule does not infer exceptions from failures or replace native/guest
Call execution and failure-case qualification. The corpus is every `.au`
file under compiler, examples, kernel, library and tests; embedded generated
fixtures and machine behavior remain covered by their existing native suites.
It supplements C1/C2 convergence and the final GCC 16 full,
BIOS/UEFI and affected-profile gates; it does not replace them. Record before/after
`scripts/compiler-speed.py` time and peak-memory observations before further
migration work, with every timeout named rather than silently extending limits.

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
do not activate it. Registration does not alter per-module visibility.

`--referenced-reflection-only` is an explicit closed-image output mode. It emits
only helpers directly referenced by runtime metadata queries in retained, validated
IR. Every source function, including unused imports, is still checked before
retention; queried helper bodies and scope visibility are unchanged. The default
keeps all existing external reflection symbols. Closed images must not rely on
handwritten/native calls to helpers that source queries do not retain. Only the
protected program-console supervisor currently opts in; other native profiles
and user-program outputs retain their existing default inventories.

## Temporary machine integration

The bootstrap assembly boundary currently passes six scalar arguments in RDI, RSI, RDX, RCX, R8, R9 and returns RAX. It preserves RBP, does not touch RBX/R12–R15, and aligns RSP to sixteen bytes immediately before calls. Scalar-only programs generate no red zone, libc, heap allocation, SIMD or runtime-library calls. Resource programs explicitly link the hosted byte adapter described in OWNERSHIP.md. Sealed service graphs use their separate checked service adapters and private source-symbol linkage without an owned-byte allocator dependency. External assembly callers must provide canonical zero/one bools and correct stack alignment.

These temporary register choices are implementation machinery, not a source-level C ABI or binary interoperability promise. Only scalar-signature unqualified root functions retain unmangled names for the temporary bootstrap assembly bridge. Imported/namespaced functions use length-prefixed Aurora-native symbols. The compiler emits a complete import graph with per-defining-module reflection helpers; separately linking overlapping compiled graphs is not supported yet. A versioned Aurora-native ABI remains to be designed.

`examples/kernel.au` performs a mutable borrow, releases it, moves ownership and returns 42. `examples/class_values.au` demonstrates class copies/visibility/reflection. `examples/loops_arrays.au` demonstrates checked traversal and independent arrays.

Runtime-sized [typed copied-class owners](OWNERSHIP.md#runtime-sized-copied-class-ownership)
support the `syntax_arena.au` AST, explicit parser-frame and variable-arity
argument-edge, unresolved type-syntax and declaration/statement storage. Complete
module syntax is parsed in one Aurora call and converted through the private
hosted adapter, including namespaces, templates, classes and their complete members.
Caller token snapshots remain immutable; a standalone type read returns an explicit
ordinal/half cursor. Grammar errors precede semantic admission for multiply-invalid
files, including cross-declaration cases, as
specified in [architecture](ARCHITECTURE.md#hosted-aurora-parser).
The replaced C++ grammar is removed, including module/container headers. Unresolved
declaration admission, module visibility, template resolution and resolved
type/lifetime analysis run in Aurora. Production lowers the resolved Session
directly to typed IR, without a resolved C++ AST round trip. The
historical predecessor remains the source-bootstrap starting point; this does not
establish whole-compiler self-hosting.

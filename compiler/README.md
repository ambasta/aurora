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
Module file loading, mechanical projection, quota and report transport checks
remain C++23. The Aurora-native x86-64 emitter
consumes the admitted source stores; the host retains artifact I/O.
GNU assembler/linker and Linux host I/O remain bootstrap dependencies.

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

For a fresh checkout, select a local copy of the pinned checkpoint compiler, or
rebuild it from the [recorded route](#historical-route), and configure Meson with
its path using the [setup commands](#source-bootstrap) below. The ordinary
shortcuts reuse the configured graph:

```sh
make -C compiler
build/aurorac --module-root library examples/core_math.au -o build/core_math.s
build/aurorac --check --diagnostics=json examples/core_math.au --module-root library
make -C compiler test
```

Compiler-only testing uses the canonical Meson graph and is not root `full`.
`ir-exhaustive` (release suite only) retains codec inventory checks and runs the source verifier and
emitter against admitted fixtures with unknown observations and a removed
handler in temporary copies. Aurora dispatch rejects these at runtime; it does
not provide the former C++ visitor's compile-time exhaustiveness guarantee.
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

The build predecessor (the checkpoint) and the historical C++ emitter oracle are
separate roles with separate pins; a newer checkpoint never replaces the oracle.
Review corpus membership changes against the previous supported set; unexplained
removal or reclassification of a previously supported input fails qualification.
New accepted oracle inputs extend coverage. Unexpected rejection must not shrink
the required corpus, and equal rejection is not emission coverage.

### Source bootstrap

The build has one predecessor stage and a self-check, like GCC's
bootstrap-and-compare:

```text
checkpoint C0 --compiles--> C1 (aurorac) --compiles--> C2 (aurorac-stage2)
                            hosted-lexer-bootstrap: C1 and C2 output identical
```

[`checkpoint.json`](checkpoint.json) pins C0 by source commit, tree and
executable SHA-256, and pins the historical oracle the same way. C0 is the C2 of
main commit `d4cbabb` (typed views), built in one hop from the previous
checkpoint, the C2 of `2fd30b2`; `history` in `checkpoint.json` lists earlier pins
and the first one was built from the last historical stage (below). No
compiler binary is committed or downloaded. Meson's `bootstrap_compiler` option
names a local copy; `scripts/bootstrap.py select` accepts it only if its bytes
have the pinned digest, and the frontend generator and initialization probe
recheck the digest before each run. Ninja tracks the executable, so replacing
it regenerates the frontend. The optional `historical_oracle` option selects the
oracle for the two `emitter-differential-*` tests (release suite); without it
those tests fail as blocked rather than pass.

```sh
# Local copies of the pinned executables; only their digests are pinned.
C0=/workspace/build/checkpoint-d4cbabbb692a/aurorac
ORACLE=/workspace/build/bootstrap-reseed/oracle/aurorac
meson setup build/meson . "-Dbootstrap_compiler=$C0" \
  "-Dhistorical_oracle=$ORACLE" "-Duefi_ld=$UEFI_LD"
meson setup build/meson-compiler . -Dkernel_images=false \
  "-Dbootstrap_compiler=$C0" "-Dhistorical_oracle=$ORACLE"
MESON_BUILD_DIR=build/meson-compiler python3 -B scripts/meson_test.py \
  --tests hosted-lexer-bootstrap
```

`BOOTSTRAP_COMPILER` and `HISTORICAL_ORACLE` request a different selection for
`make test`: the wrapper reconfigures the implicit default build after checking
the pin, and rejects an explicit `MESON_BUILD_DIR` with the exact reconfigure
command. A build directory configured with the former `bootstrap_receipt`
option must be recreated with `meson setup --wipe`, which the wrapper prints.
The container launcher forwards both variables literally.

#### Bumping the checkpoint (one hop)

Pick an accepted main commit `NEW` whose compiler adopts the batched features.
Its `checkpoint.json` still pins the current C0, so its own Meson graph accepts
C0. From the host checkout, then inside the pinned container:

```sh
git worktree add --detach build/hop-src NEW        # host: clean checkout of NEW
git rev-parse NEW^{tree}                           # host: TREE
python3 scripts/bootstrap.py hop --compiler "$C0" --oracle "$ORACLE" \
  --source build/hop-src --commit NEW --tree TREE --output build/checkpoint-NEW
```

The hop checks that the checkout's files hash to `TREE`, configures NEW with
C0 and the fixed options, builds C1 and C2, and runs `hosted-lexer-bootstrap`
and both emitter differentials. It copies NEW's C2 to `OUTPUT/aurorac`, writes
`OUTPUT/receipt.json` (source, predecessor and oracle digests, tool versions,
commands, logs and timings) and prints the new pin. The bump commit records that
pin in `checkpoint.json`, moves the old one to `history`, and qualifies with the
release suite and the merge gates. Adding `--expect SHA256` reproduces a recorded
hop. To rebuild the current C0 from the previous one (C2 of `2fd30b2`, kept at
`build/bootstrap-reseed/checkpoint/aurorac` or rebuilt by the historical route below):

```sh
git worktree add --detach build/hop-src d4cbabbb692a5553d8b14641e145a2f5ddc6ca93
./scripts/container.sh python3 scripts/bootstrap.py hop --jobs "$(nproc)" \
  --compiler /workspace/build/bootstrap-reseed/checkpoint/aurorac --oracle "$ORACLE" \
  --source /workspace/build/hop-src --commit d4cbabbb692a5553d8b14641e145a2f5ddc6ca93 \
  --tree ea4bba96465978e978646ef67c541df9073328a3 --output /workspace/build/checkpoint-d4cbabbb692a \
  --expect deae50d0f1d339a297608ef5e50f163e68fc32c9d32614e74a99ca6d9542e42e
```

With the pinned image, builds were byte-identical across build directories:
all six historical stages matched their earlier receipt, and C2 rebuilt from C0
at unchanged compiler source equals C0 itself.

#### Historical route

The first checkpoint came from the six-stage source route kept in
[`bootstrap-history.json`](bootstrap-history.json): a GNU C++ seed and five
Aurora stages, each built by the previous one, ending at the `borrow` stage
`672821f`. That stage is also the historical C++ emitter oracle. The route's
driver is `scripts/bootstrap.py` at commit `2fd30b2`, which reads
`compiler/bootstrap-route.json` at that commit; the history file records every
stage's commit, tree and reconstructed digest. To rebuild C0 without any binary
(host, then container; about 13 minutes on 4 cores under load, plus the hop's tests):

```sh
mkdir -p build/route
git archive 2fd30b2 scripts/bootstrap.py scripts/meson_toolchain.py \
  compiler/bootstrap-route.json | tar -x -C build/route
(cd build/route && python3 -c 'import sys; sys.path.insert(0, "scripts"); import bootstrap, pathlib;
print(bootstrap.prepare_sources(pathlib.Path("cache").resolve(), bootstrap.route()))')   # host Git
# SOURCES: the printed sources.json path, under /workspace in the container.
./scripts/container.sh bash -c 'cd build/route && python3 scripts/bootstrap.py build \
  --cache "$PWD/cache" --prepared SOURCES'   # six stages; prints RECEIPT
git worktree add --detach build/hop-src 2fd30b2
# BORROW: borrow/build/aurorac beside RECEIPT; it is also the oracle.
./scripts/container.sh python3 scripts/bootstrap.py hop \
  --compiler BORROW --receipt RECEIPT --source build/hop-src \
  --commit 2fd30b2c252afda5fbf6e78c399bca1cae7bd04e \
  --tree 7850b23a8995b1603422c86575d30ab53dda2527 --output build/checkpoint \
  --expect 8bcb17f354f8a28e3dfcde0e34ede9ebbbc7447d5395d52a59548d96fc1d619d
```

`2fd30b2` still selects its predecessor through the six-stage receipt, so this
first hop passes `--receipt` (which also supplies its oracle) instead of
`--oracle`. The oracle is that route's `borrow/build/aurorac`. Older receipts
remain readable as records of their own runs.

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
those facts; this is not a general exported ABI. Initialization and emission use
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
Module file loading, mechanical IR projection and quota/report transport checks
remain C++. Aurora now owns complete x86 text emission, including
stack facts and ABI JSON; its host adapter lends the two admitted owners and
copies bounded sealed output, with no native opcode fallback. Aurora owns metadata/layout,
callable/frame admission, durable instruction storage, structural CFG checks and
entry-parameter and static call-site admission.
Source verification and emission consume the same normalized storage; these
migrations still await execution qualification.

## Emitter migration qualification

The last historical stage, `672821f70f37b185c46690791bd00d74d4414403`, retains
the C++ x86 backend. `checkpoint.json` pins its route-built executable as the
historical oracle (`-Dhistorical_oracle`), separately from the checkpoint and never
as a production fallback; checkpoint bumps do not replace it. The
`emitter-differential-default` and `emitter-differential-closed` tests in the
`release` suite (run at compiler bumps and releases, not on every merge) compare the historical corpus against it, and unsupported later consumers
against current C1/C2, in ordinary and closed profiles. To run these guarded tests
directly:

```sh
MESON_BUILD_DIR=build/meson-compiler python3 -B scripts/meson_test.py \
  --tests emitter-differential-default emitter-differential-closed
```

The evidence directory, kept after a failure and removed after a pass, holds
compiler hashes, flags, exact commands, diagnostics and assembly/stack/ABI artifacts. Against the historical oracle,
accepted inputs must match exit status, diagnostics and ABI facts byte for byte;
assembly and stack facts may differ (a `historical-*-differs.json` marker records
it), because a frozen emitter must not forbid better code. C1/C2 must match every
output byte for byte, and machine behavior is checked by the execution suites.
Rejected inputs must agree and preserve every preexisting output. Any
mismatch, internal failure or watchdog timeout fails the gate and reports partial
coverage. Equal rejection is not emission coverage, so the gate also fails if any
historically supported input outside its fixed list of function-less modules is rejected.
Historical membership and its exact oracle commit come from
`tests/compiler/emitter-historical-corpus.txt`. The compiler's own modules adopted
readonly typed views at `d4cbabb`'s bump, which the oracle predates, so their
historical members are byte-exact copies of that revision under
`tests/fixtures/emitter-history/compiler-d4cbabb`, compiled as one graph (with the
retired modules and the initialization probe); the current compiler modules are
later consumers. The gate also runs the oracle on
unlisted inputs and requires a source-language rejection with preserved outputs;
an accepted omission fails and must extend historical coverage. Unsupported new
consumers still require successful C1/C2 emission, without per-feature exception
paths or pinned rejection messages. The corpus is every
`.au` file under compiler, examples, kernel, library and tests; embedded generated
fixtures and machine behavior remain covered by their existing native suites.
The default profile also compares C1/C2 for every historical input, sharing the
same real observations rather than compiling the source again in a separate
bootstrap-corpus runner. Each default input runs old, C1 and C2 exactly once; no
cross-run corpus cache or synthesized observation is used. The fast lexer and
whole-frontend convergence gate remains independent. Closed symbols and
referenced-only reflection change emission, so that profile still runs separately.
These comparisons supplement the final GCC 16 full,
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
do not activate it. Port and Serve are likewise independently syntax-activated
optional families; their appended identities do not change Serve-free or Port-free
catalogues. Registration does not alter per-module visibility.

`--referenced-reflection-only` is an explicit closed-image output mode. It emits
only helpers directly referenced by runtime metadata queries in retained, validated
IR. Every source function, including unused imports, is still checked before
retention; queried helper bodies and scope visibility are unchanged. The default
keeps all existing external reflection symbols. Closed images must not rely on
handwritten/native calls to helpers that source queries do not retain. Only the
protected program-console supervisor and singleton Call caller images opt in;
their linked admission checks bind every retained helper to a generated source
query. Call services, other native profiles and other user-program outputs retain
their existing default inventories.

## Temporary machine integration

The bootstrap assembly boundary currently passes six scalar arguments in RDI, RSI, RDX, RCX, R8, R9 and returns RAX. It preserves RBP, does not touch RBX/R12–R15, and aligns RSP to sixteen bytes immediately before calls. Scalar-only programs generate no red zone, libc, heap allocation, SIMD or runtime-library calls. Resource programs explicitly link the hosted byte adapter described in OWNERSHIP.md. Sealed service graphs use checked service adapters and private source-symbol linkage. Console-only graphs have no owned-byte allocator dependency; the closed ConsoleSession+ByteRegion prefix can also link the existing byte adapter (see SERVICES.md). External assembly callers must provide canonical zero/one bools and correct stack alignment.

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
pinned checkpoint remains the bootstrap starting point; this does not
establish whole-compiler self-hosting.

CFG joins require exact source lifetime, provenance and operand-stack agreement
before weakening the retained current value. An already unknown current stays
unknown without scheduling another visit; initialization joins independently
report changes. Current values are excluded from retained-fact metrics, so these
joins adjust only the initialization count and do not copy a native state.

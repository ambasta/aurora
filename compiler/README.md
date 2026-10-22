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
call-site admission. Module file loading, mechanical projection, dynamic
value/provenance verification remain C++23. The Aurora-native x86-64 emitter
consumes the admitted source stores; the host retains artifact I/O.
GNU assembler/linker and Linux host I/O remain bootstrap dependencies.

## Build and check

For a fresh checkout, either complete [source bootstrap](#source-bootstrap) in
the selected pinned tool environment or select a provenance-verified retained
artifact under the [bootstrap evolution policy](#bootstrap-evolution-policy).
Then explicitly configure Meson with that predecessor path using the setup
commands below. The ordinary shortcuts reuse the configured graph:

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

### Bootstrap evolution policy

New language features land first with independent library or product consumers.
Compiler adoption waits for a reviewed predecessor bump: every input compiled by
that predecessor, including compiler-imported library helpers, must remain within
its supported language subset. Batch bumps at milestones or for a justified set
of compiler adoptions, rather than requiring a bump for each feature.

A bump reviews the source pin, full historical-seed route, build/tool identities,
qualification evidence, supported corpus and batched adoption together. Preserve
every qualified checkpoint under a durable immutable reference (such as a
protected tag), with its original source identity and receipts. This retention
rule does not require every checkpoint to remain in the active chain: replacements
or shortening must satisfy the existing cross-route gates below. Preserve the
source needed to reconstruct the full seed route, not only old run summaries.

The build predecessor and historical C++ emitter oracle are separate roles even
when one executable currently serves both. Identify and retain the oracle
independently before adopting a bootstrap predecessor with the Aurora emitter.
Review corpus membership changes against the previous supported set; unexplained
removal or reclassification of a previously supported input fails qualification.
New accepted oracle inputs extend coverage. Unexpected rejection must not shrink
the required corpus, and equal rejection is not emission coverage.

Ordinary development may use a retained, digest-verified predecessor with matching
source, build configuration, tool/environment identities and qualification
evidence. This is an artifact-reuse route, not a fresh source-bootstrap result.
A source hash alone is not a cache identity across different tools/configurations;
a binary digest establishes identity, not source provenance. Rebuild from the
seed for bump qualification and fresh source-bootstrap claims. A cached later
checkpoint does not shorten the source chain; direct-build and cross-route proof
is still required. All current C1/C2, differential, final-source GCC 16 full,
applicable image/emulator and independent-review gates remain unchanged.

The checked-in [route manifest](bootstrap-route.json) pins every source commit and
tree, the fixed build options, the final predecessor and the separately named
historical C++ oracle. The [reconstruction driver](../scripts/bootstrap.py) records
local source, command, tool/runtime, header-input and artifact identities. Current
setup requires both the recorded executable digest and that complete receipt.
Invocation guards retain those bindings without replaying historical evidence
checks on every use. These local records are not signed attestations or a trust
anchor against someone who can forge the records and binaries together.

### Source bootstrap

The Aurora-native emitter requires three borrowed roots: its mutable output
workspace and the existing readonly metadata and instruction stores. The replacement
sixth checkpoint `672821f70f37b185c46690791bd00d74d4414403` supplies that capability and synchronous
mutable typed-buffer borrows for the formatter. It replaces the historical
`7811ba83730e9a8b4329da983a01e475d73999a6` hop rather than adding a seventh stage.
Qualification requires the source-bootstrap gates below, final integrated-source
GCC 16 `full` and the applicable boot/emulator gates.

The current source no longer contains a C++ expression parser or raw compiler
seed. Meson requires `bootstrap_compiler`, an absolute executable path. Ninja
tracks that executable as an ordinary input; changing it regenerates the frontend.
The source build below establishes the predecessor's provenance. Acceptance still
compares the actual generated frontend and current compiler stages.

Use a normal Git checkout containing all six commits in `bootstrap-route.json`.
Fetch missing checkpoint objects from the repository before starting; the driver
never downloads executables or rewrites source history. From the host checkout,
the supported pinned-container route is one command:

```sh
python3 scripts/bootstrap.py build --container
```

The host uses Git to prepare clean detached worktrees. The existing
`container.sh` runs the same driver inside the pinned image, which does not need
Git: it verifies the prepared file bytes/modes against the host's source manifest
before and after compilation. All prepared sources and outputs remain below
`build/bootstrap`, inside the existing checkout mount. No image, package or host
settings are changed. For advanced native use, select the exact pinned toolchain
and Git on PATH, then omit `--container`.

The driver uses the existing Meson setup, compiler targets and
`hosted-lexer-bootstrap` convergence at every historical stage, with at most two
workers. It records exact commands, output/log hashes, clean source commit/tree
and byte inventories, tool/subprogram/shared-runtime hashes and versions, implicit
startup objects/linker scripts/archives, actual Ninja header inputs, elapsed time
and child peak RSS. The pinned native GCC route requires built-in specs; external
specs are rejected because they can introduce additional implicit inputs.
It prints the three required
current Meson setup options. Inside the same container/native path layout, copy
those printed values into both current configurations:

```sh
# P, SHA and RECEIPT are the values printed by the completed reconstruction.
meson setup build/meson . \
  "-Dbootstrap_compiler=$P" "-Dbootstrap_compiler_sha256=$SHA" \
  "-Dbootstrap_receipt=$RECEIPT" "-Duefi_ld=$UEFI_LD"
meson setup build/meson-compiler . -Dkernel_images=false \
  "-Dbootstrap_compiler=$P" "-Dbootstrap_compiler_sha256=$SHA" \
  "-Dbootstrap_receipt=$RECEIPT"
meson compile -C build/meson-compiler -j 2 aurorac aurorac-stage2
meson test -C build/meson-compiler --no-rebuild --num-processes 1 \
  hosted-lexer-bootstrap compiler-test-inventory
```

A later invocation reuses only a complete receipt with matching pinned sources,
configuration and tool/environment identity, after checking the executable,
recorded inputs, source bytes and logs. Missing/mismatched data fails closed with
a rebuild command; it is never blessed by hashing an arbitrary executable. Add
`--fresh` to reconstruct all six stages in new directories, keeping old successful
and failed evidence. A fresh route is required for predecessor-bump qualification;
a cache hit is explicitly not a fresh source bootstrap. Receipts are local to
the recorded environment and paths, not a universal binary digest for every host.

The replacement sixth stage still builds directly with the paired-root compiler.
This mechanism neither adds a seventh stage nor establishes another successful
skip. The existing register-carry hop remains omitted. Historical stage convergence
does not replace current C1/C2, emitter differential, final-source GCC 16 full,
applicable image/guest or independent-review gates.

| Stage | Immutable source | Required predecessor capability |
|---|---|---|
| Historical seed | `bdf646f09d5e14c88124c4bc9e4f998beda16183` | GNU C++ source build; no Aurora predecessor |
| ABI facts | `17f4f1440e6faa9cdaf8711c04400854bdb60d9e` | Historical seed; adds compiler facts |
| Copied arguments | `c0ef02cc105de2b7699d8565f6a53f1dea9e1205` | ABI-facts compiler |
| Owner-field initialization | `bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4` | Copied arguments used by its frontend |
| Paired roots | `052f79d7995be93053f73659bcfc37687b00b341` | Region-backed owner-field initialization |
| Multiple roots and mutable typed buffers | `672821f70f37b185c46690791bd00d74d4414403` | Paired-root frontend signature and ordered ABI facts |
| Current C1/C2 | Final integrated source | Three borrowed roots for the Aurora emitter; mutable typed-buffer borrows for formatter append |

The following failed skip attempts refer to their original historical sources,
including the old multi-root checkpoint `7811ba8`, not the replacement above.

| Historical direct skip experiment | Observed boundary | Route status |
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
| Replace the largest experimentally buildable suffix with one checkpoint | Build that exact source directly with the proposed earlier compiler; compare predecessor-generated frontend assembly against its normal-route build under the narrowly bounded cross-route gate below, then build the next source through both routes |
| Admit a new stage or replacement | Record its complete historical-seed source route, current C1/C2 assembly/object/facts/header and corpus convergence, and uninterrupted final-source full qualification; retain failed attempts without waivers |
| No successful shorter route | Keep six source-built stages; replacement of stage six does not establish a shorter route |

For the cross-route predecessor comparison only, assembly text may differ solely
in documented label names or equivalent address spelling, provided the assembled
objects are byte-for-byte identical. Retain both assembly files, the classified
differences, assembly commands/tool identities and object comparison. This is not
a general machine-code-equivalence waiver: any other textual difference fails.
Downstream generated assembly, objects, ABI facts, generated headers and corpus
outputs still require exact equality, including the existing C1/C2 convergence
and emitter differential gates. Safety, rejection and final-source qualification
requirements are unchanged.

A retained compiler may be reused only with its exact source/build/tool provenance
and qualification receipt, not by filename or digest alone. Current setup verifies
the selected executable against the mandatory recorded digest and reconstruction
receipt. Meson tracks that historical evidence as configuration dependencies.
The generation and historical-oracle commands check the selected compiler,
receipt, route, driver and freshly resolved runtime identities before and after
use. The configured selection is digest-bound in the generated commands, not a
new reconstruction receipt. Ordinary Make uses these current-selection checks;
changing the predecessor still requires full validation and reconfiguration.
See the [configuration/invocation split](../docs/developer-test-contract.md#predecessor-backed-frontend-and-historical-receipts).

Both ordinary default directories are now configured: `make`/`make test` use the
image-enabled graph, while `make -C compiler test` uses the hosted-only graph.
For other configurations, repeat setup with all three predecessor options and use
`MESON_BUILD_DIR`. Keep using the same host/container path layout so configured
absolute executable paths remain valid. An unconfigured directory needs explicit
setup; the wrapper does not guess a predecessor.

`BOOTSTRAP_COMPILER`, `BOOTSTRAP_COMPILER_SHA256` and `BOOTSTRAP_RECEIPT`
together request a different verified predecessor for `make test`. The wrapper reconfigures an implicit default build in place, preserving
its other options and files. An explicit `MESON_BUILD_DIR` with a different
selection is rejected with the exact reconfigure command. Without this variable,
the wrapper reuses the configured predecessor. The container launcher forwards
all three values literally; both paths must be valid inside the container.

The predecessor emits frontend A for current compiler C1; C1 emits B for current
compiler C2. The same compilation emits `--abi-facts` metadata for collected
resolved declarations and the exact emitted module. The closed private bootstrap
adapter generates its record layouts, enum values and bridge symbol targets from
those facts; this is not a general exported ABI. Initialization and emission use
one closed entry table in the existing bootstrap adapter for root authority,
argument-record names, host declarations and the five fixed register transports.
The facts normalizer accepts up to three concrete owning roots with only the
first optionally mutable. Tuple storage does not imply pointee mutability or prove
distinct ownership. Aurora forwards and owner lifetime/semantic checks remain
unchanged. Both stages generate their own facts and header. The existing bootstrap
test checks current C1/C2 assembly, object,
facts and header convergence, binds B to the frontend actually linked into C2, and compares current
C1/C2 corpus diagnostics/output. No compiler binary or generated frontend is
committed. The candidate's independent module graph pass runs in Aurora after all
native function checks and before import pruning, without a C++ graph fallback.
Module file loading, mechanical IR projection, instruction value/provenance
verification remain C++. Aurora now owns complete x86 text emission, including
stack facts and ABI JSON; its host adapter lends the two admitted owners and
copies bounded sealed output, with no native opcode fallback. Aurora owns metadata/layout,
callable/frame admission, durable instruction storage, structural CFG checks and
entry-parameter and static call-site admission.
Native verification and emission consume the same normalized storage; these
migrations still await execution qualification.

## Emitter migration qualification

The source-built replacement sixth checkpoint `672821f70f37b185c46690791bd00d74d4414403` retains
the C++ x86 backend. The manifest independently selects it as the historical oracle
as well as the build predecessor, never a production fallback. Replacing the historical `7811ba8` hop does
not replace this oracle with the current Aurora emitter. The
`emitter-differential-default` and `emitter-differential-closed` tests in `slow`
and `full` compare the historical corpus against it, and unsupported later consumers
against current C1/C2, in ordinary and closed profiles. To run these guarded tests
directly while retaining successful artifacts:

```sh
AURORA_MESON_KEEP_ARTIFACTS=1 meson test -C build/meson-compiler \
  --num-processes 2 --print-errorlogs \
  emitter-differential-default emitter-differential-closed
```

Both profiles run by default. To select from an explicit comparison target, set
`meson configure <build> -Demitter_comparison_base=<target commit>`. Immediately
before the closed test, the existing driver resolves that commit and inspects
current tracked/staged/unstaged/untracked changes. Only known documentation or
native-kernel-only changes may produce an explicit Meson SKIP. Compiler/ABI,
library, generator, option, harness or unknown changes retain the real closed
comparison, as do missing/invalid/ambiguous bases or unsupported source layouts.
This is dependency selection, not output-equivalence proof or a cached receipt.
Use the actual PR target; reset the option to empty to require both unconditionally.

Each new evidence directory retains all input/compiler hashes, exact commands,
diagnostics and assembly/stack/ABI artifacts. Accepted inputs must match byte for
byte; rejected inputs must agree and preserve every preexisting output. Any
mismatch, internal failure or watchdog timeout fails the gate and reports partial
coverage. Equal rejection is not emission coverage, so the gate also fails if any
historically supported input outside its fixed list of function-less modules is rejected.
Historical membership and its exact oracle commit come from
`tests/compiler/emitter-historical-corpus.txt`. The gate also runs the oracle on
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
historical predecessor remains the source-bootstrap starting point; this does not
establish whole-compiler self-hosting.

CFG joins require exact native lifetime, provenance and operand-stack agreement
before weakening the retained current value. An already unknown current stays
unknown without scheduling another visit; initialization joins independently
report changes. Current values are excluded from retained-fact metrics, so these
joins adjust only the initialization count and do not copy the native state.

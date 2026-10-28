# Aurora compiler

Aurora is an intentionally incompatible safe C++-inspired language. It has no
C header/macro layer, raw-pointer escape, unsafe block or C ABI. The hosted build
uses an Aurora-written [lexer](LEXER.md) and a bounded
[syntax parser](ARCHITECTURE.md#hosted-aurora-parser),
bootstrapped from source through a small C++ interpreter, the [seed](#the-seed).
Complete module syntax, declaration admission, module/template resolution and
resolved type/lifetime analysis through typed IR run in Aurora. The `ir_graph.au`
candidate independently checks normalized module call graphs and
selects retained functions. Aurora also owns independent metadata/layout, callable
and frame admission, structural CFG normalization, entry-parameter and static
call-site admission and whole-function value, lifetime and provenance verification.
After lowering, one Aurora call (`pipeline.au`) consumes the resolver Session and
projects it into metadata and instruction owners, admits and verifies them, checks
the call graph, publishes and emits code plus any requested stack and ABI facts.
`builtin_catalog.au` is the only copy of the built-in type, scalar descriptor and
sealed service catalog: the resolver seeds its descriptors, admission its service
set and lowering its scalar, service and initial layout prelude from it. On the
resolver path Aurora lexes, parses, admits and ingests each source and keeps its
module header and imports. aurora-fmt likewise parses, lays out and verifies its
output in one Aurora call. Aurora decides module-loading policy (names, relative
paths, byte limits, headers and interfaces), owns the admission and layout limits
and renders every module-loading, source, resolver, lowering, pipeline, formatter
and lint diagnostic (`diagnostics.au`, `lowering_messages.au`, `pipeline.au`,
`formatter.au`): code, message and span, copied out 384 bytes at a time.

aurorac is itself one hosted Aurora program: `aurorac.au`, whose `main` receives
`builtin::HostFiles` and a `ByteRegion` ([SERVICES.md](SERVICES.md#hosted-files)),
over the compiler modules and the Linux runtime root (`aurora.host`,
`aurora.memory`). It parses the command line, opens the input and each import
Aurora requests beneath the explicit roots (naming a missing, ambiguous,
reserved or unreadable module), runs the modules above, renders text and JSON
diagnostics and writes every artifact atomically, refusing an output that would
replace a source or share another output's destination. Run under the name
`aurora-fmt` (a second link of the same object) it is the formatter. It links
with `ld -static -e _start` and contains no C or C++ code, startup or libc.
The build configures `aurorac.au` with its runtime root (`runtime/linux` of the
source tree) as a byte string; `--runtime-root` names another.
Textual-IR test cases are read in Aurora (`tests/tools/air.au`, built into a
test-only graph) straight into the same stores and run the same pipeline stages;
there is no C++ IR model. That bridged test graph, with the C++ adapters
`hosted_resolver.cpp`, `hosted_pipeline.cpp` and `runtime/hosted_bytes.cpp`, is
what the C++ test drivers and the optional [language server](lsp/README.md) link.
The C++ left in `compiler/` (`diagnostics.hpp`, `hosted_resolver.*`,
`hosted_pipeline.*`, `format.hpp`, and the server's loader `frontend.hpp` and
`host_sources.hpp`) serves only them; none of it is part of aurorac.
The Aurora-native x86-64 emitter
consumes the admitted source stores.
The same semantic traversal feeds typed x86 forms to the text backend or the
checked relocatable-object backend selected by `--emit-object`. Object output
uses a separate typed workspace for code, symbols, labels and relocations. It
supports the source UART, ordinary UEFI console/session, production terminal painter
and compiler forms, including readonly
literal data and RIP-relative references, plus size/public-field-count reflection
helpers with the same defining-module visibility and symbol-selection rules as
text output. Neither backend adds reflection access to private values.

Native console, UART and test-graph wrappers remain private bootstrap adapters.
For the bridged test graph, `frontend_wrapper.au` emits its wrappers directly,
using the same table/ABI-derived recipe that renders the GNU reference. The closed recipe admits at most 256 sorted hidden exports, 1024-byte
identifier names and six ordered register moves or readonly record-lane loads
per wrapper, followed by one symbolic PLT32 tail jump. It has no assembly parser,
stack operations, stores, calls, conditional branches or arbitrary external resolution.
The existing `ObjectWorkspace` owns encoding, fixups and ELF output; native code
only lends recipe bytes and transports the result. Invalid/reused workspaces
cannot expose output, and allocation failure releases every owner.

`private_object.au` composes the bridged test graph, the ordinary UEFI console/session,
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

One private-object test driver compares normalized wrapper and composed text,
readonly data, symbols and relocations with GNU references, checks malformed
recipe/ELF data and every allocation failure, and preserves source LOCAL
identity. Shared CLI input/output robustness is tested once in `diagnostics.py`.
Console, UART and painter objects run in their existing hosted drivers and
guest families. GNU assembler/linker remain dependencies for other text output,
native console/UART/painter adapters and final links. This adds no Aurora C ABI.

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

A fresh checkout builds from source with GCC: `meson setup build/seed .`
without `-Dbootstrap_compiler` builds the [seed](#the-seed) and the first
compiler from it. The merge loop configures a cached first compiler instead,
using the [setup commands](#source-bootstrap) below. The ordinary shortcuts reuse the
configured graph:

```sh
make -C compiler
build/aurorac --module-root library examples/core_math.au -o build/core_math.s
build/aurorac --check --diagnostics=json examples/core_math.au --module-root library
make -C compiler test
```

Compiler-only testing uses the canonical Meson graph and is not root `full`.
`ir-exhaustive` (release suite only) runs the CLI with temporary copies of the
verifier or emitter, interposed on the pipeline entry, that observe unknown forms
or operators or lack a handler. Aurora dispatch
rejects these at runtime; it does not provide the former C++ visitor's compile-time exhaustiveness guarantee.
[Development and qualification](../docs/developer-test-contract.md) defines exact
routes, selected-artifact identity, explicit pinned compatibility and merge gates.
The optional [language server](lsp/README.md) has its own dependency and suite.

### Bootstrap evolution policy

The compiler's sources, including the library helpers they import, stay within
the subset the [seed](#the-seed) runs. A new language feature lands first with
independent library or product consumers; the compiler adopts it in the change
that teaches the seed to run it, with the seed's cases. A cached C0 that
predates the change cannot compile the new sources: rebuild it from the seed.

### Source bootstrap

The build bootstraps from source with GCC alone, like GCC's
bootstrap-and-compare, with one interpreted stage in front:

```text
GCC --builds--> aurora-seed --runs aurorac.au on the compiler's sources--> X (C0)
C0 --compiles--> C1 (aurorac) --compiles--> C2 (aurorac-stage2) --compiles--> object C
seed-bootstrap: X and C1's object of C2 (B) identical
hosted-lexer-bootstrap: B and C identical
```

Without `-Dbootstrap_compiler`, Meson takes this route: the [seed](#the-seed)
interprets the compiler compiling itself, and X, the object it writes, is the
current compiler. Since C1 and C2 compile the same sources, the two compares
make X, C1 and C2 one fixed point. No compiler binary is committed, downloaded,
pinned or replayed from history.

`-Dbootstrap_compiler` names a cached C0 instead, the merge loop's fast path:
any aurorac that compiles the current sources, such as an earlier build's
`aurorac-seed` or `aurorac` copied out of its build directory. Nothing pins it:
the stage compare checks C1 and C2 whatever C0 was, and the release suite still
builds X there and runs `seed-bootstrap`. Every stage compiles the current
sources with the current runtime root (`runtime/linux`), so C0 needs only its
executable; Ninja tracks it, so replacing it rebuilds C1.

```sh
meson setup build/seed . -Dkernel_images=false
meson compile -C build/seed aurorac-seed        # X, from GCC and the sources
install -D -m 755 build/seed/aurorac-seed build/c0/aurorac
C0=$PWD/build/c0/aurorac
meson setup build/meson . "-Dbootstrap_compiler=$C0" "-Duefi_ld=$UEFI_LD"
```

Before the seed, a checkpoint compiler named by commit was rebuilt by replaying
a historical C++ seed, five Aurora stages and every checkpoint hop since
(`scripts/bootstrap.py`, `compiler/checkpoint.json` and
`compiler/bootstrap-history.json` in Git history up to `47732eba`).

#### The seed

`compiler/seed` is a small C++ interpreter, not a second compiler: a lexer,
a parser and a tree walker for the subset of Aurora the compiler is written in.
That is modules, imports and namespaces; enums; classes with fields,
constructors and methods; functions with value and reference parameters;
locals, `if`, `while`, `return` and assignment; i64, u64, u8 and bool with the
checked arithmetic, conversions and shifts of [SCALARS.md](SCALARS.md); fixed
arrays and string literals; readonly spans and windows; `OwnedBytes`,
`OwnedValues`, `ByteRegion`, `HostFiles` and `move`. Each function is lowered on
its first call to nodes with resolved types and frame offsets, which then run.
The seed checks only what it needs to run (names, types, layouts): it does not
repeat the compiler's admission, which X performs when it compiles the same
sources. Anything else, such as templates, reflection or scalar owners, stops it
with status 3 and a message; a checked failure (overflow, a bad index or window)
stops it with status 4, where compiled code traps.

`HostFiles` is the runtime root's `aurora.host`, interpreted, over native
primitives: the zeroed 16384-byte session block and the same Linux system calls
the compiler emits for them. Owners are native and have the observable behaviour
of `aurora.memory`: a 4 GiB payload quota, at most 16383 live allocations,
zeroed or filled storage, prefix-preserving resize and inert failures; ids,
mappings and that runtime's own state are not modelled. Values have a packed
layout of the seed's own, which the subset cannot observe (it has no
reflection). The compiler's sources may use a construct only once the seed
runs it.

`tests/seed/cases.golden` runs the seed on a semantics program (whose output
the compiled program also prints), traps and rejections; `seed-bootstrap` is its
real test. The seed is built at -O1, runs on the build machine only and is
never installed. On this compiler it takes about 80 s on one core, against
15-19 s for C1 doing the same work (4.9 times C1's cycles).

The bridged test graph the C++ test drivers link is emitted by C1 with
`aurorac --local-symbols --abi-facts`, which binds every generated function and
reflection entry locally without changing ABI or instructions (`--check` rejects
it), so only the wrappers are external. The closed private bootstrap adapter
(`scripts/bootstrap_frontend.py` over the `scripts/frontend_bridge.py` table)
generates its record layouts, enum values and bridge symbol targets from those
facts; this is not a general exported ABI. The facts normalizer accepts up to four
distinct concrete owning roots, each independently mutable or readonly. Tuple
storage does not imply pointee mutability or prove distinct ownership. No compiler
binary or generated object is committed. The candidate's independent module graph
pass runs in Aurora after all source whole-function checks and before import
pruning, without a C++ graph fallback. Aurora owns complete x86 text and object
emission, including stack facts and ABI JSON, with no native opcode fallback.

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
- [Sealed synchronous services, including hosted files](SERVICES.md)
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
do not activate it. Port, Serve and HostFiles are likewise independently
syntax-activated optional families; their appended identities do not change
catalogues that do not name them. Registration does not alter per-module visibility.

`--referenced-reflection-only` is an explicit closed-image output mode. It emits
only helpers directly referenced by runtime metadata queries in retained, validated
IR. Every source function, including unused imports, is still checked before
retention; queried helper bodies and scope visibility are unchanged. The default
keeps all existing external reflection symbols. Closed images must not rely on
handwritten/native calls to helpers that source queries do not retain. Closed
supervisors and their packed fixtures, source UART objects, the ordinary UEFI
console/session, the compiler and its bridged test graph opt in, as do selected closed user images.
Other outputs retain their existing default inventories. Object composition
requires this closed reflection inventory and LOCAL source definitions. The compiler
retains queried helpers; image admission still checks imports, W^X and mixed-stack
bounds from compiler facts.

## Temporary machine integration

The bootstrap assembly boundary currently passes six scalar arguments in RDI, RSI, RDX, RCX, R8, R9 and returns RAX. It preserves RBP, does not touch RBX/R12–R15, and aligns RSP to sixteen bytes immediately before calls. Scalar-only programs generate no red zone, libc, heap allocation, SIMD or runtime-library calls. Resource programs explicitly link the hosted byte adapter described in OWNERSHIP.md; hosted programs whose `main` takes a region get the compiler-emitted entries over the Aurora memory runtime instead ([SERVICES.md](SERVICES.md#hosted-memory)). Sealed service graphs use checked service adapters and private source-symbol linkage. Console-only graphs have no owned-byte allocator dependency; the closed ConsoleSession+ByteRegion prefix can also link the existing byte adapter (see SERVICES.md). External assembly callers must provide canonical zero/one bools and correct stack alignment.

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
directly to typed IR, without a resolved C++ AST round trip. The compiler
builds itself from source through the [seed](#the-seed); that is not yet a
self-hosting toolchain (assembler, linker and runtime remain GNU and Linux).

CFG joins require exact source lifetime, provenance and operand-stack agreement
before weakening the retained current value. An already unknown current stays
unknown without scheduling another visit; initialization joins independently
report changes. Current values are excluded from retained-fact metrics, so these
joins adjust only the initialization count and do not copy a native state.

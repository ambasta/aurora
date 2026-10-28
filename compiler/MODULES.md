# Native modules and the scalar core library

This is a whole-graph module compiler, not separate binary compilation or a complete C++ module implementation. The existing safe-language checks still apply inside every module. There is no C source/header/ABI compatibility facility.

```text
// library/std/core.au
export module std.core;
export namespace std {
    auto max(i64 left, i64 right) -> i64 {
        if (left > right) { return left; }
        return right;
    }
}

// application.au
module application;
import std.core;
auto answer() -> i64 {
    return std::max(40, 42);
}
```

```sh
build/aurorac --module-root library application.au -o build/application.s
```

`--module-root DIR` may repeat and may appear before/after the input and output options. No environment variable, working-directory convention, network request or installed system library silently supplies import paths. Existing `aurorac INPUT.au -o OUTPUT.s` commands remain valid for files without imports.

## Declaration and visibility rules

- `module name;` is an ordinary root unit. `export module name;` declares an importable interface unit.
- Imports are named identifiers separated by dots and must precede declarations. `import std.core;` selects `std/core.au` under an explicit root.
- Imported files must declare the exact requested name and use `export module`.
- Declarations are module-private unless explicitly marked `export`. An `export namespace` deliberately exports its contained declarations, including nested namespace members. An interface header alone does not export all declarations.
- Namespace blocks can reopen and nest, including `namespace a::b { ... }`. A namespace and a function/class cannot occupy the same visible name.
- Qualified calls/types use `a::b::name`. Lookup begins in the current/enclosing namespace, then the unit's global namespace. Namespace aliases, using declarations, leading-global `::name` and reexports are not implemented. Explicit bounded templates use their separate contracts. Ordinary overloads support one defining-module set per qualified name; see GENERICS.md.
- Every function body resolves in its defining module, including private helper calls. An unresolved call is rejected before the graph is merged; a root function cannot silently satisfy or hijack an undeclared imported helper.
- A unit sees its own declarations and only directly imported exported declarations. Imports do not implicitly reexport their dependencies. `export import` is rejected explicitly.
- `aurora.*` names belong to the compiler. Except its own sources (`aurora.compiler.*`, `aurora.tests.*`), such a module (for example the HostFiles binding `aurora.host` and the memory runtime `aurora.memory`) is read only from the compiler's runtime root (configured, or named by `--runtime-root`), never from a `--module-root` or an overlay; a module root holding one, or a root module declaring one, is rejected.
- Duplicate imports, duplicate non-overload declarations, repeated exact overload parameter tuples, namespace/declaration collisions and ambiguous visible exported names are rejected. Multiple search roots containing the same requested module are an error, not precedence-based shadowing.
- Class exports permit checked inline scalar-field values in callers. Fields remain private by default. Public constructors and methods of directly imported exported classes are available, with private access and const receiver checks; bodies resolve in the defining class and module. See VALUES.md. Ordinary functions can now copy bounded scalar-field class parameters/results through a private native value convention; exported signatures cannot expose private types, and callers must directly see signature types. See VALUES.md. Owning and synchronous-view signatures use the separate checked ownership modes; no C-compatible ABI is implied.

## Native identities and the temporary entry seam

Imported, namespaced and class-value-signature functions have length-prefixed native identities containing the defining module, namespace path and declaration name. All class identities include the defining module and namespace; a display spelling does not determine type equality. Length prefixes and component counts prevent concatenation collisions. The compiler reserves source identifiers beginning with `__au_`.

Scalar-signature unqualified root functions temporarily keep their existing assembly names so the current tests and kernel entry bridges continue to work. This is a narrow internal bootstrap seam, not a promised C ABI, binary interoperability surface or stable native ABI. Exported source visibility is separate from physical object-file symbol visibility. The compiler currently emits one object-ready assembly file for the complete graph; linking separately compiled copies of overlapping graphs is unsupported.

Runtime class type IDs remain local to the complete compilation graph, while qualified defining-module identity controls source type equality. IDs are not stable package or cross-process identities.

## Reflection does not widen imports

Each lowered function has its defining module scope. Runtime size/field-count queries use that module's descriptor view, containing its own class types and directly imported exported class types. Builtin/scalar-array shapes remain available independently of named-class privacy.

Guessing a private or otherwise unavailable class's numeric type ID returns zero from another module, matching the existing unknown-ID rule. An unavailable type cannot be named through static reflection either. A callee does not inherit its caller's private type visibility. The typed-IR verifier rejects a query whose scope differs from its containing function's defining scope or names an unknown view; emitted helpers do not accept a caller-supplied scope selector.

This is lexical/API privacy, not confidentiality against an API author or a host capable of inspecting binaries. An exported function can intentionally return facts about its own private types. The module resolver remains trusted to establish declaration ownership and export visibility, just as the semantic analyzer remains trusted for const/lifetime policy. The lower verifier is not a second full proof of those source policies.

## Bounded, descriptor-relative source access

aurorac reads sources through its `builtin::HostFiles` capability
([SERVICES.md](SERVICES.md#hosted-files)). Explicit roots are opened once with
`open_directory` and identified by device and inode; duplicate root identities are
rejected. Imports are opened beneath those retained descriptors with
`open_beneath` (Linux `openat2` with `RESOLVE_BENEATH`, `RESOLVE_NO_SYMLINKS` and
`RESOLVE_NO_MAGICLINKS`), the input and the runtime root with the same no-symlink
policy at any path. Kernels without `openat2` fail closed with no weaker fallback.

All symlinks are rejected, including links whose current targets appear to be inside a root. The loader reads from the successfully opened descriptor without a canonical-check/path-reopen gap. Replacing the root pathname after opening it does not redirect the retained directory authority. Sources must be regular files; nonblocking open avoids hanging on a FIFO before the regular-file check. Each file is closed once read. A session holds at most 32 open directories and files, enough for the 16 roots, the file being read and, once a reserved import needs it, the runtime root.

The optional language server keeps the former C++ loader (`frontend.hpp`, `host_sources.hpp`) for its in-memory [source overlays](SOURCE-OVERLAYS.md), with the same policy.

Current limits:

- 16 explicit roots
- 64 files per graph, including the root
- 16 import edges in a dependency path
- 1 MiB per source file and 4 MiB total captured input
- 32 module path components, each at most 128 bytes
- 32 namespace components
- 128 nested parser expressions and blocks,64 nested type parses
- 128 constructed expression-tree levels, including skewed binary/member/index chains

Reads enforce byte limits on actual captured bytes, including files that grow during reading. Parser recursion and actual expression-tree depth are checked separately; a child is rejected before attachment would retain an over-depth tree, keeping later traversal and error cleanup bounded. These are explicit implementation limits, not a larger host-stack requirement. Cycles and header/alias mismatches fail before emission. No source construct evaluates arbitrary code to access files or the network.

Pinned descriptors protect path/inode authority, not atomic content versioning. Another writer to the same inode can change bytes while a bounded read is in progress; the captured buffer may contain mixed versions. Compilation uses the buffer after capture, but neither a per-file atomic snapshot nor an atomic multi-file repository snapshot is promised. Reproducible builds still require stable source contents. Privileged host changes and compromise of the host/compiler implementation are outside this guarantee.

These byte/depth limits intentionally reject overly deep otherwise-grammatical programs; they do not bound total compiler work or solve all compiler resource scaling. Typed-IR facts still scale with basic-block count and live slots; dense initialization facts are implemented, while compiler-wide budgets remain future work (see ARCHITECTURE.md).

## Atomic artifact output

aurorac writes every artifact through `create_output`, `write` and `commit`
([SERVICES.md](SERVICES.md#hosted-files)). The output is a single filename leaf in
a parent directory opened without following symlinks. Existing symlink, directory
and other nonregular destinations are rejected, and the destination's device and
inode are compared with every source read, so output = input and hard-link source
aliases are rejected; two outputs of one run naming the same leaf of the same
directory are a command-line error. Each output is an exclusive mode-0600
temporary beside the destination (at most 32 name attempts, 64 MiB of bytes);
existing files are never opened for writing or truncated. Commit checks the
destination again (regular or absent) and renames the temporary over it; a failed
write or commit removes the temporary, and uncommitted outputs are removed when
`main` returns, so a rejection leaves existing artifacts unchanged. Code, then
stack facts, then ABI facts are created; ABI facts, stack facts and code are
committed in that order.

This provides ordinary atomic replacement and prevents target symlink/hard-link swaps from causing writes through a source inode. The source-alias check is made when the output is created, not again at commit. It is not a claim of crash durability (there is no file/directory fsync protocol), multi-file transactions, or artifact integrity against a privileged or caller-equivalent actor that can tamper with private temporary entries or rewrite the output directory. Such an actor can also replace artifacts after commit. A process killed by a signal leaves its `.aurora-output-*` temporary. Inputs are captured byte buffers, not atomic file/repository versions.

`tests/compiler/diagnostics.py` and `tests/modules/run.py` cover aliases, symlinked and shared destinations, a failing write (a file-size limit) and preserved artifacts; `tests/host-files` covers the capability itself.

## Loading boundary

Aurora lexes, parses and admits each source in one reused parser arena and
ingests it into the resolver Session, which keeps its header and imports. Only a
diagnostic or the header name returns to the driver. The Session
owns import traversal and dependency postorder: each step returns the next
requested import as bytes of the requesting source, or completion, and Aurora
binds every import to the module whose header spells it. Temporary ancestry
frames are cleared before ingestion; existing order rows and import bindings
retain progress without a second owner. Aurora owns the module policy: it
requires an explicit root, validates the requested name and maps it to its
relative path, charges each source against the file and graph byte limits, and
at the next step checks that the requested module's header spells the name in
an `export module` interface, recording each request in one Session index entry.
The driver (`aurorac.au`) only opens that path under each root (rejecting a
missing, ambiguous or misplaced reserved module), captures at most one byte past
the file limit and reports those loading rejections; the language server's C++
loader may also supply an authorized overlay. Explicit-order in-memory resolution
remains supported for the C++ test drivers independently of filesystem traversal.

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

`host_sources.hpp` isolates the trusted Linux-host adapter. Directory/file handles are move-only RAII objects. Explicit roots are opened once and identified by directory inode/device; duplicate root identities are rejected. Relative imports are opened against those retained descriptors using Linux `openat2` with `RESOLVE_BENEATH`, `RESOLVE_NO_SYMLINKS` and `RESOLVE_NO_MAGICLINKS`. The exact policy is probed; unsupported kernels/policies fail closed with no weaker fallback.

All symlinks are rejected, including links whose current targets appear to be inside a root. Root paths and the explicitly supplied root source also use a no-symlink policy. The loader reads from the successfully opened descriptor without a canonical-check/path-reopen gap. Replacing the root pathname after opening it does not redirect the retained directory authority. Sources must be regular files; nonblocking open avoids hanging on a FIFO before the regular-file check.

The host adapter uses Linux/POSIX declarations solely as bootstrap OS machinery. Those host headers, descriptors and calls are not exposed as Aurora language features, target runtime APIs or C interoperability promises. A future native directory-capability API should replace this adapter.

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

The caller-selected output parent directory is also pinned through the no-symlink host adapter. The output is a single filename leaf. Existing symlink/directory/nonregular destinations are rejected, and destination inode/device identities are compared with the root and every imported source captured from opened descriptors. Accidental output=input and hard-link source aliases are rejected.

The writer creates a separate exclusive mode-0600 regular temporary in the pinned parent. A temporary candidate equal to the destination leaf is skipped. It accepts at most 64 MiB of artifact bytes, 8192 write calls, 128 interrupted-write retries and 32 temporary-name attempts. Existing output files are never opened for writing or truncated. Only a complete successful write can be atomically renamed over the destination leaf, without following a destination symlink. The transaction becomes permanently failed if writing or committing fails; a partial write cannot be retried and accidentally published.

Precommit failures preserve existing source/output bytes. Cleanup addresses only the reserved temporary leaf when its inode still matches the writer's file; a changed replacement entry is left alone. I/O cleanup errors can leave an owned temporary, and process crashes can also leave one. The writer does not scan/delete unrelated stale temporaries.

This provides ordinary atomic replacement and prevents target symlink/hard-link swaps from causing writes through a source inode. It is not a claim of crash durability (there is no file/directory fsync protocol), multi-file transactions, or artifact integrity against a privileged or caller-equivalent actor that can tamper with private temporary entries or rewrite the output directory. Such an actor can also replace artifacts after commit. Inputs are captured byte buffers, not atomic file/repository versions.

Native tests cover the destination/temp-name collision, poisoned partial writes, source aliases, destination swaps, pinned-parent replacement, own-temp cleanup and actual OS write/rename failures. The rename-denial fault gate requires an unprivileged test user; it fails explicitly rather than silently skipping that check under root.

## Loading boundary

Aurora lexes, parses and admits each source in one reused parser arena and
ingests it into the resolver Session, which keeps its header and imports. Only a
diagnostic or the header name and interface flag return to the host. The Session
owns import traversal and dependency postorder: each step returns the next
requested import as bytes of the requesting source, or completion, and Aurora
binds every import to the module whose header spells it. Temporary ancestry
frames are cleared before ingestion; existing order rows and import bindings
retain progress without a second owner. The host still authorizes and opens
files, reads bounded bytes or authorized overlays, and validates imported
headers/interfaces before the next traversal step. Explicit-order in-memory
resolution remains supported independently of filesystem traversal.

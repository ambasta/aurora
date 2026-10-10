# Package metadata

`package.identity`, `package.manifest` and `package.graph` implement a bounded, freestanding metadata profile. They do not retrieve, authenticate, install or execute packages. Version triples are exact pins, not full SemVer or constraint solving. No report grants filesystem, network, process or allocation authority.

## Identity tokens

### Format version 1

The entire selected byte window must match:

```
identity = name "@" component "." component "." component
name = [a-z][a-z0-9]* ("-" [a-z0-9]+)*
component = "0" | [1-9][0-9]{0,9}
```

Name length is 1..24 ASCII bytes. Hyphens cannot lead, trail, or repeat; the
first byte must be a lowercase letter (never a digit). Each component's numeric
value must be 0..4294967295. This is an explicitly restricted canonical version
triple, not full SemVer: no prerelease, build metadata, epoch, revision, wildcard,
range or leading zeros. No Unicode, escapes, whitespace, NUL terminator or line
ending is permitted. Case is exact. Valid token length is 7..57 bytes. This format
is an authored metadata profile, not a promise of compatibility with external
package formats, and not a complete manifest parser.

The caller imports both `package.identity` and `std.array`: the current compiler
requires direct visibility of the embedded array type. No compiler change is used.

### API and failures

`package::parse_identity(span, offset, count) -> IdentityResult` first validates
nonnegative offset/count and a complete window within the span using subtraction
before addition. Invalid windows return `IdentityStatus::out_of_range`. A valid
window not matching the complete grammar or numeric bounds returns
`IdentityStatus::malformed`. Empty input and every incomplete token are malformed;
there is no streaming or automatic completion. All failures are recoverable.

`IdentityResult` owns status, `std::array<u8,24>` name, name length, and three u64
fields carrying the bounded components. Public constructor parameters are status,
name storage, length, major, minor, patch. Its `status()` revalidates successful
constructor data. Invalid shape, name, unused nonzero tail or out-of-bound component
normalizes to malformed; an explicitly supplied out_of_range stays out_of_range.
An explicitly supplied malformed stays malformed. Publicly constructed data is
forgeable and never certifies parsing, provenance, trust, authenticity or authority.

`name_size()` returns zero on failure. `name_byte_or(index,fallback)` returns the
selected byte only for a successful result and in-range signed index.
`name_bytes_or_zero()` returns an independent complete 24-byte owned copy, all zero
on failure and zero after the successful name's end. `major_or`, `minor_or`,
`patch_or` return the supplied u64 fallback on failure. Arguments are eager.

`same_identity(left,right)` is true only if both normalized statuses are success
and name plus all three components match. `compare_versions(left,right)` returns
`VersionOrder::{less,equal,greater,invalid}`; it compares the numeric triples
lexicographically and deliberately does not compare names. Either invalid input
produces invalid. No dependency compatibility policy is implied by ordering.

### Bounds and authority

Parser scanning is bounded by 57 bytes after the window checks; result validation
by 24 name bytes. No allocation, I/O, network, resolver, installer, executable
recipe, filesystem write, hashing or signature primitive exists here. Untrusted
bytes cannot grant any authority. Input spans never escape; copied owned results
survive owner mutation and scope exit. Only std.array is imported. GNU assembler,
linker and Python remain host bootstrap/test dependencies, never target runtime.
Tests are finite execution evidence, not a memory-safety or performance proof.

Focused and full test routes use the shared development/qualification budget controls; those controls grant no package authority.

## Manifests

### Exact grammar and supported bounds

```
manifest = "aurora-package 1\n"
           "package " identity "\n"
           ("depends " identity "\n"){0,8}
           "end\n"
```

The selected byte window must match the entire grammar. Literals are case-sensitive
ASCII. Newlines are exactly one LF byte. No CR, CRLF, leading/trailing whitespace,
blank lines, comments, quotes, escape syntax, tabs, BOM, NUL, Unicode, unknown keys,
optional fields, alternate order or bytes after the final LF are accepted. `1` is
the exact schema version, without leading zeros. The required end marker makes
truncation of a dependency list observable. The supported profile permits zero to
eight direct dependencies; this is a profile limit, not a universal package limit.
Valid manifest byte lengths range from 37 to 615 inclusive.

Each `identity` is exactly the accepted package.identity token:
`[a-z][a-z0-9]*("-"[a-z0-9]+)*@component.component.component` with a 1..24-byte
name and each component canonical decimal 0..4294967295. No leading zeros except
`0` itself. Leading digit, edge/consecutive hyphens and non-ASCII names reject.
These are pinned exact-version requirements, not version ranges, complete SemVer,
features, source URLs, repositories, hashes, trust policy or build recipes.
Dependency names must be unique by canonical byte name irrespective of version;
the root package name cannot appear among its dependencies. Input order is retained.
Two different dependency names may pin the same version. No sorting or resolution
is performed. Transitive cycles cannot be detected from one manifest and are not
claimed; direct self-dependencies reject as malformed metadata.

### API

Consumers import `package.manifest`, `package.identity`, and `std.array` directly
under existing visibility rules. The module itself imports only the latter two.

`package::ManifestStatus { success, malformed, out_of_range }`.
`package::ManifestResult` privately owns outcome, copied root IdentityResult and
signed dependency count. Public constructor arguments in order are:
`(ManifestStatus status, IdentityResult identity, i64 dependencies)`.
Methods:
- `status() const -> ManifestStatus`: explicit errors retain status; successful
  construction revalidates root identity and count 0..8, otherwise malformed.
- `identity_or_error() const -> IdentityResult`: independent valid copied root on
  success; canonical malformed IdentityResult on any failure (zero owned storage).
- `dependency_count_or(i64 fallback) const -> i64`: count on success, fallback otherwise.

`package::parse_manifest(builtin::span<const u8> bytes, i64 offset, i64 count)
-> ManifestResult` validates the entire selected window including every dependency,
duplicates/self-name, final end marker and absence of trailing bytes before returning
successful metadata. Invalid signed window returns out_of_range. Window checks are
subtraction-first; a valid window violating grammar/profile constraints is malformed.
All failures recover without a trap for every representable argument/input.

`package::DependencyStatus { success, malformed, out_of_range, index_out_of_range }`.
`package::DependencyResult` privately owns outcome, copied root and selected
IdentityResults, count and selected zero-based index. Public constructor arguments:
`(DependencyStatus status, IdentityResult identity, IdentityResult dependency,
  i64 dependencies, i64 index)`.
Methods:
- `status() const -> DependencyStatus`: explicit errors retain status; successful
  construction revalidates both identities, count 1..8, index 0..count-1 and
  different root/dependency names; invalid success data normalizes to malformed.
- `identity_or_error() const -> IdentityResult`: independent copied root on success,
  canonical malformed IdentityResult otherwise.
- `dependency_or_error() const -> IdentityResult`: independent copied selected
  dependency on success, canonical malformed IdentityResult otherwise.
- `dependency_count_or(i64 fallback) const -> i64`: count or fallback.
- `index_or(i64 fallback) const -> i64`: selected index or fallback.

`package::manifest_dependency(builtin::span<const u8> bytes, i64 offset, i64 count,
 i64 index) -> DependencyResult` first validates the *whole* manifest using the same
contract. A malformed late dependency, duplicate or missing end marker masks all
facts even when an earlier requested dependency is valid. Window errors take
precedence over grammar errors, which take precedence over invalid selection.
Only after full validation does an invalid signed dependency index return
index_out_of_range. A valid manifest with zero dependencies has no selectable index.
All error getters mask both stored identities/count/index; fallbacks are eager.

### Ownership, construction and authority

Results store no span/reference/source offset and retain copied facts after input
owner overwrite, copy, function return or scope exit. The summary contains 31 scalar leaves and a selected-dependency report 61. The API returns one independent observation at a time rather than retaining the input or exposing a borrowed list. Separate calls revalidate their own input;
observations from different calls are not a transaction or a shared snapshot if the
owner changes. A successful query includes its copied root identity for context.

Public constructors are deliberately forgeable data constructors. Their local
invariant checks do not prove that any bytes were parsed, that count matches an
actual list, that other dependencies exist or are unique, or that metadata is trusted.
No constructor or parser result grants resolver, install, filesystem, process,
script, network, provenance, cryptographic or other authority. There is no IO,
allocation, source retrieval, command execution, hashing or signature verification.
Bounded duplicate comparisons may rescan prior identities (at most eight entries).
No performance or memory-safety proof is inferred from finite tests.

## Whole-catalog ordering

### Input and supported profile

The exported module is package.graph. Callers directly import package.graph,
package.manifest, package.identity and std.array under existing visibility rules.

A catalog is one readonly byte span, two copied std::array<i64,8> values holding
absolute offsets and lengths, and a signed catalog count. Count must be 0..8.
Only the first count array entries select manifests. Unused entries and bytes
outside selected windows are ignored. Windows need not be sorted, adjacent or
disjoint; there is no file/path meaning. Empty catalogs succeed without reading
bytes, including a valid empty span.

Each selected window must satisfy the complete accepted package.manifest grammar,
including its 37..615-byte bound and at most eight pinned direct dependencies.
The graph adds no alternate line endings, whitespace or identity syntax. Fixed-array callers have the compiler’s 4096-byte backing bound; runtime-owned spans can hold larger catalogs within the same eight-entry and per-manifest limits.
Eight packages is a supported profile bound, not a general ecosystem limit.

Every supplied package is validated and ordered, including disconnected or
otherwise unused packages. This is whole-catalog consistency, not root-directed
closure extraction. Root package names must be unique by canonical bytes, even
when their versions match. Multiple versions of one name are unsupported.
Every declared dependency must name exactly one supplied package and its three
numeric version components must exactly match that package. Different dependents
may require the same name/version. Incompatible pins to one name necessarily
produce version_mismatch against the single catalog entry; there is no version
selection/backtracking. A missing name is missing_package, even if other pins
also mismatch. Self-dependencies are malformed manifest input under the existing
parser, not the graph's cycle status. Transitive cycles produce cycle.

### Deterministic validation and order

Both APIs validate the entire supplied catalog before exposing any successful
fact. Error precedence is global across the set, in this exact order:

1. invalid_count: catalog count is outside 0..8.
2. out_of_range: any selected offset/length is negative or outside the span.
   Check each with subtraction-first arithmetic before computing an end.
3. malformed: any selected manifest violates its full accepted grammar/profile.
4. duplicate_package: two supplied roots have the same canonical name.
5. missing_package: any dependency name is absent from the supplied catalog.
6. version_mismatch: any present dependency has a different exact version.
7. cycle: after consistent links, not every package can be ordered.
8. index_out_of_range: only for the selected-entry API, after graph success.

A failure in a later catalog position must outrank a lower-priority earlier error.
No partial order is observable if a disconnected late component contains a cycle.

The successful order is dependency-first: each dependency precedes its dependent.
At each position, among all not-yet-emitted packages whose dependencies have been
emitted, choose the lexicographically smallest canonical package name. Compare
unsigned ASCII bytes and use shorter-before-longer for equal prefixes. Unique
names remove ties. The resulting identity sequence is independent of catalog
input order and dependency-line order. The returned catalog indices transform
accordingly when the caller permutes its catalog.

### Exported API and copied-result semantics

package::GraphStatus cases, in declaration order:
  success, invalid_count, out_of_range, malformed, duplicate_package,
  missing_package, version_mismatch, cycle, index_out_of_range.
Enum ordinal representation is not an API; tests map named cases explicitly.

package::GraphOrderResult has private outcome, copied std::array<i64,8> order,
and signed package count (10 scalar leaves). Public constructor arguments:
  (GraphStatus status, std::array<i64,8> order, i64 count).
Methods:
- status() const -> GraphStatus. Explicit errors retain their status. A success
  constructor revalidates count 0..8, the first count slots as a permutation of
  0..count-1, and all unused order slots as zero. Invalid success data is malformed.
- package_count_or(i64 fallback) const -> i64.
- catalog_index_or(i64 rank, i64 fallback) const -> i64. Returns the saved index
  for a successful result and valid rank, fallback otherwise.
Both getters mask every error; fallback arguments are eagerly evaluated.

package::order_manifests(builtin::span<const u8> bytes,
  std::array<i64,8> offsets, std::array<i64,8> lengths, i64 count)
  -> GraphOrderResult.
On success it copies the complete permutation with zero unused slots. No span,
reference or manifest bytes are stored in the result. Indices refer to this
call's catalog slots; they do not authorize or validate later changed data.

package::GraphEntryResult has private outcome, copied IdentityResult, count,
rank and catalog index (33 scalar leaves). Public constructor arguments:
  (GraphStatus status, IdentityResult identity, i64 count, i64 rank, i64 index).
Methods:
- status() const -> GraphStatus. Explicit errors retain their status. Success
  requires a valid identity, count 1..8 and both rank/index in 0..count-1;
  invalid success data is malformed.
- identity_or_error() const -> IdentityResult. Successful independent copied
  identity, canonical malformed IdentityResult with zero owned storage otherwise.
- package_count_or(i64 fallback), rank_or(i64 fallback),
  catalog_index_or(i64 fallback), each const -> i64 and masked on every error.

package::ordered_manifest(builtin::span<const u8> bytes,
  std::array<i64,8> offsets, std::array<i64,8> lengths, i64 count, i64 rank)
  -> GraphEntryResult.
This revalidates/orders the entire catalog, then checks rank, then returns the
copied identity plus rank, catalog index and total count. No rank is valid in an
empty catalog. All representable inputs and signed arguments recover without an
intentional trap. Results and constructor/argument copies survive input overwrite,
local scope exit and later mutation of caller-owned index arrays.

Public constructors are forgeable data constructors. Local invariants establish
neither that input was parsed nor that an order satisfies any graph. Separate
queries are independent observations, not a transaction or common snapshot if the
owner changes between calls. No result grants trust, provenance, capabilities,
source retrieval, filesystem, process, network, install or execution authority.
No scripts, build recipes, IO, allocation, cryptographic verification, source
resolution, version ranges, features or multi-version solving are implemented.

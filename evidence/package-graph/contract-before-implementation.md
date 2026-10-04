# Bounded exact-manifest graph contract

This contract is frozen before production implementation or independent oracle
construction. It advances the explicit system-release requirement for bootstrap
ordering and cycle/conflict handling. Repository inspection found package.identity
and package.manifest, but no package graph validator or prescribed catalog format.
No new serialized format is introduced.

Base: verified PR19 commit 7e3fe6da7f5ddff8d0d580e429035c4a64196e31,
tree db79101fe6f0dc45a21625594396bade8ea2c2ff, 513 sealed source files.
Compiler: accepted M022 SHA256
e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e.
The candidate changes neither compiler nor existing library modules. It is
independent of overload, optional, extent, framebuffer and mutable-byte work.

## Input and supported profile

The exported module is package.graph. Callers directly import package.graph,
package.manifest, package.identity and std.array under existing visibility rules.

A catalog is one readonly byte span, two copied std::array<i64,8> values holding
absolute offsets and lengths, and a signed catalog count. Count must be 0..8.
Only the first count array entries select manifests. Unused entries and bytes
outside selected windows are ignored. Windows need not be sorted, adjacent or
disjoint; there is no file/path meaning. Empty catalogs succeed without reading
bytes (M022 still requires a nonempty backing array for its whole-array span).

Each selected window must satisfy the complete accepted package.manifest grammar,
including its 37..615-byte bound and at most eight pinned direct dependencies.
The graph adds no alternate line endings, whitespace or identity syntax. M022
byte owners are currently bounded to 4096 bytes, so a catalog whose selected
windows cannot fit such an owner is not representable in this caller profile.
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

## Deterministic validation and order

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

## Exported API and copied-result semantics

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

## Observable acceptance gate

Implement a genuine Aurora validator and deterministic ordering algorithm using
accepted M022 features. Provide a compiled native example with a nontrivial
permuted catalog, shared/transitive dependencies, copied observations and input
mutation after borrow end. Confirm native binaries have no unresolved symbols,
ELF interpreter or dynamic target dependencies.

An independently designed Python model, frozen before reading production code,
must agree with full-width native observations. Cover all simple directed graphs
through four vertices, including cycles, disconnected components and diamonds;
all catalog permutations on smaller graphs and selected larger permutations;
eight-node chains/dense DAGs/cycles; deterministic lexical ties including prefixes
and hyphens; dependency-line shuffles; exact-version endpoints, conflicting pins,
missing names, duplicate roots with same/different versions, malformed late
manifests, truncation, unselected bytes, window/count signed extremes and the
whole-set error precedence. Observe the full permutation and copied identity
bytes/version values, not process exit codes or a checksum alone.

Test constructor poisoning and explicit error masking, all selection boundaries,
owned copies, scope/borrow lifetime, eager fallbacks and defining-module helper
shadowing. Negative compilation must preserve absent/existing outputs and cover
privacy/import/type/lifetime violations. Distinguish unsupported syntax rejection
from analysis of a supported lifetime operation. Tests are evidence, not a proof
of production security, stack safety or universal performance.

Run the full focused oracle and actual Make recipe with exact compiler and
source/tool identities. Obtain a distinct implementation/integration review,
independent of production and oracle authors. Run a fresh complete make test on
final integrated source before acceptance; coordinate heavy builds with the
ordinary-function-overload lane. This library-only change adds no emulator or
physical-device claim. Preserve all failures and exact source revisions.

Focused candidate cap: 256 MiB with conservative command growth reserve and a
1 GiB filesystem free-space floor. No silent cap increase; request measured
aggregate admission separately. Keep an early verified recoverable source archive.
Compaction may replace only completed successful outputs after exact recoverable
archive/hash/mode verification and proving no active/future writer or consumer.
No accepted-main edits, remote publication or changes to frozen historical evidence.

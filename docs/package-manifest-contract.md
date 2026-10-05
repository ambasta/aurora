# Bounded declarative package manifest candidate

Status at author-source freeze: the final focused oracle and actual Make replay
passed independent review. A fresh combined-source aggregate and final seal remain
required before acceptance; see the evidence index for the separately sealed result.
The freestanding example executes natively and returns a complete u64 value of 42
after input mutation.

The next source-package dependency is executable reading of one package identity
and its pinned direct dependencies, using the accepted `package.identity` module.
The system-release requirements name source recipes, dependency resolution,
version/feature constraints, integrity, isolation and reproducibility but prescribe
no concrete manifest syntax. Repository inspection found no existing parser or
manifest format to duplicate. This authored version-1 metadata profile is a bounded
prerequisite; it does not settle a future complete recipe or package format.

Baseline: published, reviewed PR17 checkpoint commit
`d8222ad235fa218629266aa28e7b42ba87f4ee5e`, tree
`b8369852f9b316680bb24ee54ed228f1b4b5a095`. Compiler SHA256:
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
Use only accepted M022 source syntax. No compiler or existing library changes,
optional/extent/mutable-byte work, or dependency on parallel text work is allowed.

## Exact grammar and supported bounds

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

## API

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

## Ownership, construction and authority

Results store no span/reference/source offset and retain copied facts after input
owner overwrite, copy, function return or scope exit. M022 class values have at
most 64 flattened scalar leaves; the summary is 31 leaves and a selected-dependency
report is 61. A full owned eight-identity list does not fit that contract, so queries
return one observation at a time. Separate calls revalidate their own input;
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

## Observable acceptance gate and resource boundary

Freeze this contract before implementation or oracle authoring. Independently
written Python grammar/integer model must agree with actual compiled x86-64 Aurora
on complete output vectors, including all copied name bytes and high-bit numerical
fallbacks. Native binaries have no unresolved symbols, interpreter or dynamic target
libraries. Host GNU tools and a tiny observation entry are bootstrap test machinery.

Cover valid empty/eight-dependency profiles, every truncation boundary, every byte
value across grammar positions, malformed identity/version overflow, duplicate names
with same/different versions, self-name, unknown fields/script-like input, CRLF/BOM/
whitespace/trailing bytes, count limits, offset/count signed endpoints, all query
indices and error precedence. Cover public constructor poisoning, owned copies,
scope/lifetime, eager evaluation, defining-module helper shadowing, import visibility,
private field/method rejection and absent/existing compiler output preservation.

Run focused oracle and actual Make recipe, then an unchanged-input full `make test`
with compiler/source/tool pins and a distinct source/integration reviewer independent
of both production and oracle authors. Preserve failures and their exact sources.
No kernel changes means no new device/emulator gate or qualification claim.

Initial whole focused candidate budget is 256 MiB, with conservative growth reserve
and a 1 GiB filesystem free floor. Aggregate may use up to 1024 MiB only after measured
approval from the parent. Keep an early verified source archive and preserve all
failed test artifacts. Only losslessly verified successful-output compaction is
permitted. No accepted-main write or publication before the parent seal.

## Reproduction and evidence

The [module](../library/package/manifest.au) and
[example](../library/examples/package_manifest.au) are native Aurora source. The
[frozen contract](../evidence/package-manifest/contract-before-implementation.md)
is a required test input; its SHA256 is
`5aa8786a1afc3fac793deccb1e4bb11ae2d6497ab10093b0545c72aa39dc7103`.
With the pinned compiler at build/aurorac, run:

```
make test-package-manifest
make test
```

The focused target runs the independent harness under Python -B -O. Its default
whole-candidate cap is 256 MiB; the aggregate target explicitly chooses 1024 MiB.
An external aggregate supervisor must additionally account for retained sibling
workspaces and growth reserve. `PACKAGE_MANIFEST_COMPILER` selects the compiler
path, without disabling its exact pin. `PACKAGE_MANIFEST_TEST_FLAGS` can select a
fresh contained --artifacts directory. Development --quick/--self-test-only modes
do not satisfy the full acceptance gate.

The source-local [evidence index](../evidence/package-manifest/README.md) records
completed checks, failures and exact checkpoint status without relabeling earlier
source or aggregate receipts. No new emulator gate is claimed for this library-only
change; the inherited aggregate still exercises compiler and hosted kernel tests.

## Explicit compiler-integration pin

The runner now accepts --compiler-sha256 as an explicit expected 64-character
lowercase hexadecimal digest. Its default remains the historical accepted M022
pin. The binary must match before the designated artifact directory is created
or any native test output is produced. PACKAGE_MANIFEST_COMPILER_SHA256 passes
that expected digest through the Make target; it does not bypass verification.
A new compiler integration must record and review its expected pin independently,
then deliberately supply it. Wrong/malformed pins and baseline-default behavior
have independent rejection/compatibility checks. The format/oracle and frozen
pre-implementation contract are unchanged.


## Current bounded resource-configuration checks

The maximum selectable whole-candidate storage cap is 1024 MiB; focused defaults
remain unchanged. Any increase still needs separate measured aggregate admission,
including retained roots, growth reserve and the existing free-space floor. This
does not change per-process address-space, per-file or source-size limits.
`--check-cap-only` validates resource configuration without reading/running a
compiler or creating a native acceptance receipt. Its configuration-only result
cannot replace this contract's behavioral oracle and full acceptance gates.
Historical frozen contracts and receipts retain their original limits and pins.

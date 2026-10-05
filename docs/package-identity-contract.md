# Bounded package identity token candidate

Status: implemented library-only candidate. Independent oracle/source review and
the focused Make recipe passed; parent aggregate and acceptance remain pending.
The first freestanding native example returns 42.
Baseline: accepted M022 compiler plus merged PR15 XFS. This independent library-only
candidate does not change compiler, kernel, storage, text-range, or optional work.

## Dependency and observable gate

The native source-package ecosystem needs a way to read small, unambiguous package
identities before dependency resolution and build planning exist. Add a genuinely
executable freestanding `package.identity` module using accepted readonly byte spans,
owned fixed arrays and copied class values. Gate: independent Python regex/integer
oracle vs actual compiled x86-64 execution, malformed/truncated/overflow/window and
owned-copy/lifetime/encapsulation checks, independent review, and parent aggregate.
The exact compiler SHA256 is
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.

## Format version 1

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
is an authored candidate contract, not a promise of compatibility with external
package formats, and not a complete manifest parser.

The caller imports both `package.identity` and `std.array`: the current compiler
requires direct visibility of the embedded array type. No compiler change is used.

## API and failures

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

## Bounds and authority

Parser scanning is bounded by 57 bytes after the window checks; result validation
by 24 name bytes. No allocation, I/O, network, resolver, installer, executable
recipe, filesystem write, hashing or signature primitive exists here. Untrusted
bytes cannot grant any authority. Input spans never escape; copied owned results
survive owner mutation and scope exit. Only std.array is imported. GNU assembler,
linker and Python remain host bootstrap/test dependencies, never target runtime.
Tests are finite execution evidence, not a memory-safety or performance proof.

Candidate storage cap is initially 128 MiB with a 1 GiB filesystem free floor;
all failures are retained. No accepted-main mutation or publication is authorized.

## Focused verification record

The independent oracle run and a separate full replay through
`make test-package-identity` both passed with the exact accepted M022 compiler:
5,503 native cases, 199,213 complete-u64 observations, and 40 normal compiler
rejections with preserved absent/existing output. Coverage is 5,021 parse cases,
351 public-constructor cases, 124 comparison cases and seven ownership/eager/
helper-shadow cases. These two replays overlap; their counts are not additive.
All 230 binaries per run passed undefined-symbol and ELF interpreter/dependency
audits. Production source was unchanged between the runs. The independent source
review found no production defect. See the [evidence record](../evidence/package-identity/README.md).

Reproduce with the accepted compiler present at build/aurorac:

```
make test-package-identity
```

The default full target runs Python with -B -O and records a fresh bounded artifact
directory. `PACKAGE_IDENTITY_COMPILER` selects the compiler path but its exact pin
is still enforced. `PACKAGE_IDENTITY_TEST_FLAGS` can supply a fresh --artifacts
path inside the candidate. `--quick` and `--self-test-only` are development modes,
not substitutes for the default full gate. The frozen format contract in
`evidence/package-identity/contract-before-implementation.md` is a required test
input and must be retained when integrating the source delta.

No full parent make-test aggregate or emulator gate has been performed for this
candidate by this author. Prior baseline gates are not relabeled as candidate
verification. Acceptance remains with the parent after its fresh aggregate.

## Integration harness revision

A distinct review found that the original harness's lexical artifact containment
check could accept a `..` path escaping the candidate and its storage accounting.
No recorded test used such a path and no escaped write was performed. Harness v2
rejects traversal components, rejects raw-path/ancestor symlinks before canonical
resolution, and then checks canonical containment. Self-tests cover contained,
traversal and outside paths. This fixes test infrastructure, not library behavior.

The default candidate ceiling remains 128 MiB. A separately approved integration
run can select `--candidate-cap-mib 1024` (accepted integer range 128..1024) because the
inherited full regression build produces more than 128 MiB. The selected ceiling
is recorded; the 1 GiB free floor and growth reserve remain enforced. Fresh parent
aggregate and distinct review will establish the final revised-harness status.

The top-level `make test` target selects `PACKAGE_IDENTITY_CAP_MIB=1024` for its
package prerequisite automatically. Standalone `make test-package-identity`
keeps the 128 MiB default. This prevents the full default aggregate from inheriting
a focused-only cap after other test products have accumulated. Both routes pass
an explicit cap argument to the same harness and record it in their manifests.

## Explicit compiler-integration pin

The runner now accepts --compiler-sha256 as an explicit expected 64-character
lowercase hexadecimal digest. Its default remains the historical accepted M022
pin. The binary must match before the designated artifact directory is created
or any native test output is produced. PACKAGE_IDENTITY_COMPILER_SHA256 passes
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

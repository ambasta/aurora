# Bounded package identity token candidate

Status: proposed contract and acceptance gate; implementation and independent review pending.
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

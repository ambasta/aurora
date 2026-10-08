# Quoted UTF-8 append qualification

## Source and scope

The base is main `2543131e63cba058fabbb658579bee8b6737ba0b`, tree
`0deb1667c3485b5df1feb43159cd48643bc51357`. All 888 baseline paths were checked
against the accepted publication manifest by SHA256, Git blob SHA1 and executable
mode, with no missing or unexpected paths. Publication uses whole-file delta
blobs against that verified tree.

The production delta is confined to `library/std/json_write.au`. The remaining
changes are an example, tests, test routing and documentation. There is no
compiler, runtime or kernel implementation change. See the
[transaction contract and emission proof](json-string-write.md).

## Focused results

The unchanged reviewed compiler is
`64d35e5f735cb29b5d39a15619d29e417d7704a932a45b089b67d7d14dd3f80d`.
The final runner is
`cbb7c4409f88ef2d1be6aae77a3aca959e57fb7f7620c8f6805d8b83a341585d`.

Both `python3 -B tests/compiler/json_string_write.py COMPILER --artifacts DIR`
and the same command with `-O` passed independently: each ran 21 programs,
316 native observations and 14 rejection fixtures (28 executions with absent
and preexisting output). Another 1,920 lead/second-byte/width boundary inputs run
inside native loops. The optimized smoke profile passed three programs,
12 native observations and seven rejection fixtures. Smoke is explicitly partial;
it does not replace the full writer gate.

Python's strict UTF-8 decoder and JSON encoder supply independent status and
canonical byte expectations. Coverage includes every single-byte input, all
controls, Unicode boundary and seeded scalar sequences, malformed versus
truncated prefixes, late invalid input, signed window extremes, empty windows
inside malformed surrounding data, and validation precedence on failed owners.

Hosted cases check every emitted byte, exact/spare capacity with allocation
disabled, exactly one replacement allocation when growth is needed, prefix/size/
capacity preservation under quota and injected faults, sticky and one-shot fault
behavior, and successful retries. A released quota blocker verifies committed
accounting preservation. Real distinct owners in one region cover windows of
4097 and 16385 bytes; 4097 NULs expand to 24584 quoted bytes. The example uses
dynamic source storage, a prefixed output, every-byte observations and subsequent
validation of its small complete JSON array.

Compile rejections cover same-root direct, empty and disjoint aliases, later
output reads/mutations, forwarded aliases, const output, and private result
state. Successful forwarding and copied reports after clear/move demonstrate that
results retain no output borrow. Public result construction checks shape only,
including zero appended bytes on every failure status.

The existing full borrowed-object regression passed 18 programs, 74 native cases
and 68 rejection fixtures. The existing scalar codec regression passed 1942
cases, 19781 full-width observations, 53 rejections and 431 hosted observations.
The borrowed-object gate was replayed on the final formatted writer bytes. The
scalar codec regression preceded writer-only formatting; its own codec inputs
were unchanged, and final writer runs bind the formatted production bytes. Both changed Aurora
files pass the compiler-owned formatter with empty diagnostics. The new Python
runner passes Ruff formatting and lint.

## Routing and developer checks

The small writer smoke belongs to Meson `dev`/`full`; the exhaustive writer gate
belongs to `slow`/`full`. Both also belong to `bytes`. No previous test is removed
or narrowed. The Make compiler aggregate includes `test-json-string-write` through
the controlled build-once wrapper.

All 41 tests in the final Meson developer suite passed with one test process.
The separately selected exhaustive Meson writer test also passed.
A focused Make run passed in externally pinned prebuilt acceptance mode with
`native_complete=false`: 21 programs, 316 native observations and 14 rejection
fixtures. The terminal receipt is `test-contract-88gep8n0/run.json`, with raw
runner artifacts retained by the recipe. This is a focused gate, not complete
root-native acceptance.

A fresh Meson build was run explicitly with `-j1`; its separately built compiler digest is
`d5ee529e956823bdd381cbd146b0220607f935abd6dd92580f358621447dd120`.
It is not presented as identical to the reviewed prebuilt compiler above.

## Review, retained evidence and limits

Independent source review found the immutable two-pass reservation/emission proof
sound. Independent raw-evidence review confirmed that both final full modes and
smoke bind the final library/runner bytes, their observed outcomes pass, expected
compile rejections are clean, and successful commands have no diagnostic stderr.
The independent review also checked the Make terminal and all 41 Meson developer
results. Final source packaging is checked separately before publication.

The unverified early six-file delta was preserved before full qualification.
Initial fixture/formatting runs and the setup attempt without Ninja on PATH remain
retained separately; corrected final receipts identify their exact inputs and are
not substituted into earlier records. Raw command, generated source/assembly,
allocation and observation evidence is kept in the separate audit archive rather
than added in bulk to the repository.

Overflow guards are reviewed arithmetically: valid hosted owners near `I64_MAX`
are impractical, and no forged owner/span is used to claim runtime coverage of
those branches. The UTF-8 corpus is not every Unicode string. Recoverable failure
preservation does not promise fail-stop unwinding or rollback of completed
argument side effects. These focused gates do not establish fresh root
full-native, sanitizer, guest, broad-host or physical AMD hardware acceptance.

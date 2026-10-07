# Shared LSP document formatting results — 2026-10-07

## Scope and source

This focused increment adds `textDocument/formatting` to the optional C++23
language server. It calls the existing compiler-owned `format::source` and
shared no-symlink regular-file admission adapter. No second lexer, parser,
formatter, semantic pipeline, source-writing path or JSON dependency for the
ordinary compiler is introduced.

The starting main revision is `5ca45a87cd477a98c8556b0b57512aca76706142`
(PR63), tree `ab147c9bdcaf26d1e09204e34597faaea117dcdf`. All 747 supplied
source paths/hashes were verified before editing. The amended source passed
independent review before the native gate. All 747 reviewed candidate file
hashes remained identical through terminal exit zero. Later edits add only
these results, compact evidence and scoped status documentation.

The [protocol contract](../compiler/lsp/README.md#document-formatting) describes
canonical option restrictions, exact-open-URI handling, current-version
snapshots, whole-document UTF-16 ranges and no-partial-edit failures. Standard
LSP requests and returned `TextEdit` values carry no version: clients must
reject a response after a newer local edit. This server never applies edits
itself or changes the accepted snapshot merely because it formatted it.

## Fresh focused gate

The serialized gate ran from 15:50:29 to 15:51:29 UTC on GNU/Linux x86-64,
using GCC 14.2.0, Python 3.12.14, Meson 1.12.1 and Ninja 1.13.2. It reused the
previously verified isolated Debian nlohmann JSON 3.11.3 development package;
no installation, download or vendoring was needed. C++ compilation used C++23,
`-O2`, `-Wall`, `-Wextra`, `-Wpedantic` and `-Werror`; Meson also enabled
`_GLIBCXX_ASSERTIONS`. The ordinary `aurorac` target was not rebuilt.

- The optional LSP executable and helper target built warning-clean, one job
  at a time. The existing 49 transport/URI/UTF-16 helper checks passed.
- The real-server protocol client passed 118 process cases and 5,458 assertions
  in each of normal and optimized Python. This includes the original diagnostic
  checks and 54 added formatting/admission process cases.
- The unchanged formatter dependency rebuilt warning-clean, passed its golden
  and adversarial checks, 128 seeded trivia variants and all 84 current `.au`
  corpus sources selected by `make test-formatter`.
- The real formatter CLI passed all 30 cases in both Python modes. Each source
  passed reparse, exact token/comment-anchor preservation and idempotence through
  the shared formatter's public API tests.
- Changed host files passed clang-format 22.1.8 and Ruff 0.16.7 checks.

There was no failed native attempt in this increment. Source review requested
stronger live reauthorization and duplicate-response assertions, plus clearer
historical-result wording; these were corrected before the first build.

The LSP binary SHA-256 is
`1564116f94571ab67fa161920c2454da93db1b2ca455ee351a70255145271159`.
[Compact machine-readable evidence](../evidence/lsp/formatting-qualification.json)
records source inputs, binary digests, phase times, options, dependency provenance
and exact coverage. Retained logs and binaries back this summary. Independent
retained-evidence and final-claim review accepted this bounded checkpoint.

## Boundary coverage

Formatting tests use actual framed requests and exact expected edit text. They
cover unsaved text over invalid readonly disk bytes, repeated requests without
implicit application, subsequent canonical changes, stale versions, close and
reopen, final newline, CRLF/CR/LF, Unicode and non-BMP UTF-16 EOF positions,
embedded NUL/tabs in preserved comments and unresolved imports/names.

Malformed/unsupported syntax, empty source, parser-depth rejection, invalid or
unsupported options, unavailable/mismatched URIs and source-access failures
return errors without result/edit fields. Exact 1 MiB input and formatted output
succeed; output expansion above that bound fails, and the same process recovers
on a valid newer snapshot. Oversized changes leave the accepted text intact.

An interleaved transcript first opens and successfully formats a valid file,
then replaces the path with a missing entry, final symlink, directory and parent
symlink. Every formatting request rejects with the source-access diagnostic;
every restoration formats the original accepted snapshot. Only the test client
performs those temporary filesystem mutations. Readonly source bytes, file
metadata and permissions remain unchanged by the server.

## Limits

Only whole-document formatting is advertised. The fixed option object is
`tabSize: 4, insertSpaces: true`; additional optional/extension options reject
explicitly. Comments can preserve style findings that layout cannot remove.
New files, active cancellation, incremental parsing, richer semantic editor
features and client UI qualification remain separate work.

These focused gates do not establish a full native aggregate, new compiler
semantic qualification, sanitizer pass, total CPU/memory guarantee, emulator
boot or physical hardware support. JSON-disabled configuration behavior and
build routing are unchanged and were not rerun in this increment.

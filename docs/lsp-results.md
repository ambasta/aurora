# Initial LSP focused results — 2026-10-07

The [compiler-owned language server](../compiler/lsp/README.md) now builds as an
explicit optional Meson target. It shares the checked frontend and immutable
overlays with `aurorac`; no second source parser or compiler subprocess is used.
The default compiler remains independent of JSON.

## Fresh validation

- GCC 14.2.0 (Debian 14.2.0-19), binutils 2.44, C++23/O2, warnings as errors
- Meson 1.12.1 and Ninja 1.13.2.git.kitware.jobserver-pipe-1
- External nlohmann JSON 3.11.3, Debian development package 3.11.3-2.1
- Actual server SHA-256: `e640e708377460907c348e7a03d9e62553c60e967b11522064b8dde8990e59cc`
- 49 transport/URI/UTF-16 helper checks
- 64 actual-server process cases and 3,402 assertions in each of normal and optimized Python
- Optional Meson suite: both registered tests passed
- Default configuration works without JSON; explicitly enabled LSP with missing JSON fails

The protocol cases cover initialization/shutdown/exit/EOF, malformed and fragmented
framing, byte lengths, duplicate JSON keys, depth/event bounds, invalid Unicode,
version ordering, exact document bounds, unsaved root/import changes, clearing and
republishing across importers, source-access rejection and unchanged disk contents
and timestamps. These are focused tests, not a proof of general safety.

The tested source began with PR60 main
`0c72576672f97296b7a9903806eaa3fb76eb4db7`. Existing compiler implementation files
were unchanged. Exact compiler/LSP inputs, test hashes, dependency identity and
scope are recorded in [qualification metadata](../evidence/lsp/qualification.json).
The `.deb` was downloaded from the official Debian mirror, matched against the
[official SHA-256](https://packages.debian.org/trixie/all/nlohmann-json3-dev/download),
and extracted into an isolated build prefix. No global install or vendoring occurred.

## Preserved correction and review

The first real protocol run failed one fixture assumption: an empty exported
interface can be imported into a graph containing a function, but opening that
interface alone correctly produces `module graph must contain a function`.
The fixture now has a valid function. No parser/checker workaround or suppression
was added. The failed run, diagnostic investigation and passing replay are retained
with the source backup.

Initial independent source review found a small CRLF-midpoint issue, fixed with
two helper regressions. Final review then reproduced a source-policy mismatch:
normalization erased `symlink/..` or `missing/..` before source admission.
Document URIs and CLI roots now reject decoded parent components first. Original
source, binary and reproducer are retained; the corrected binary passed all fresh
gates. All touched host files pass pinned Ruff 0.16.7/clang-format 22.1.8 checks.
Independent final source and retained-evidence review accepted this bounded increment.

The earlier source-only workspace was lost; no previous helper result is reused
as evidence for this reconstruction. Source and dependency provenance were backed
up before the fresh native gate.

## Limits

First error per open root; existing local files only; explicit CLI import roots;
full sync and UTF-16 only. Every open document is also checked as an independent
root, so import-only modules can still receive the shared checker's standalone
root restriction. Cancellation notifications are ignored. There is no editor
extension/UI qualification, disk
watcher, background cancellation, LSP formatting, completion, rename or semantic
navigation. The separate formatter remains available through its existing CLI.

Checks are synchronous and the existing compiler does not bound total CPU work.
No full native aggregate, sanitizer, emulator, physical hardware or new compiler
semantic qualification is claimed. Meson's printed sanitizer environment options
are defaults; this was an ordinary unsanitized release build.

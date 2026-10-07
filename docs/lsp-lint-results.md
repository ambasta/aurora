# Opt-in LSP semantic lint results — 2026-10-07

## Scope and source

The optional C++23 language server now publishes the compiler's existing AU6001
findings when initialized with `initializationOptions: {"lint": true}`. Default
sessions remain check-only. The adapter selects `AnalysisMode::Lint` in the
single shared `checkSource` call; it adds no parser, semantic pass, compiler
rule, formatter change, source write or autofix.

The base is merged PR66 main commit `a8210d359ee565a781c63db84daca59004484249`,
tree `c3d259c4c1882ac741871cfa70f2caacac92dd88`. All 757 base files matched their
SHA-256, Git blob, byte-length and executable-mode records. Independent source
review accepted the adapter and tests before the first native execution.

The corrected, fully tested 757-file source has manifest SHA-256
`9b71da9fb4350aecbfb6a4816a5b04cc21fea0a528027355ea241256a0a3dbb1`
and Git tree `da0736660d920bc5ce7b29cdeb92e6482d40d58f`.
Every source hash remained identical through terminal exit zero. Later changes
are limited to scoped result/status documentation and compact evidence.

The [protocol contract](../compiler/lsp/README.md#opt-in-semantic-lint) describes
strict initialization validation, immutable source ranges, warning severity,
root-only lint scope and versioned refresh. Any graph error suppresses that
root's warnings. A separate valid root can still warn, including when an
importer's template instantiation reports an error on that same source URI.

## Publication bounds

Each URI receives one complete replacement report of at most 128 diagnostics.
Errors take priority, followed by the earliest compiler warnings. If warnings
must be omitted, the final slot is a distinct server-owned warning with code
`aurora-lsp-diagnostics-limit` and an exact `data.omittedWarnings` count. Its
start-of-root range is explicitly marked unknown. No report is split into
partial replacement notifications and no error is dropped for a warning.

The final serialized UTF-8 payload is checked against the 8 MiB wire budget.
Independent source review checked 270,369 error/warning-count combinations
and a conservative 3,385,344-byte escaped payload bound. These are static checks;
they do not establish a frontend CPU or whole-process memory bound.

## Preserved failed fixture and correction

The initial gate ran from 17:30:55 to 17:31:29 UTC. The optional LSP and helper
built warning-clean, and all 49 helper checks passed. The real-server protocol
client then failed a newly added Unicode fixture that expected a warning after
a line comment terminated only by CR.

Aurora's existing `//` scanner stops at LF, not bare CR. The entire fixture was
therefore a comment, and the compiler correctly returned AU2001 at EOF. A
retained three-case diagnosis confirmed the CRLF and LF forms produced AU6001.
Production code was unchanged. The test correction retained Unicode LF/CRLF
cases, added valid CR-separated programs with and without a Unicode LF-comment
prefix, and explicitly checks the original CR-comment rejection.

Independent review accepted that exact test-only correction before the complete
replay. Original failure logs, source manifests and the narrow correction remain
preserved. Later stages were not run in the failed attempt.

## Complete focused replay

The serial replay ran from 17:35:08 to 17:35:11 UTC on GNU/Linux x86-64, using
GCC 14.2.0, Python 3.12.14, Meson 1.12.1 and Ninja 1.13.2. It reused the exact
LSP/helper binaries freshly built in the initial attempt because production
source had not changed. The optional nlohmann JSON 3.11.3 package was the
already verified isolated development dependency; nothing was installed,
downloaded or vendored for this increment.

C++ compilation used C++23, `-O2`, `-Wall`, `-Wextra`, `-Wpedantic`, `-Werror`
and `_GLIBCXX_ASSERTIONS`. The passing results were:

- 49 LSP framing, URI and UTF-16 helper checks.
- 163 actual-server protocol process cases and 18,745 assertions in each of
  normal and optimized Python, including all previous formatting transcripts.
- Explicit opt-in validation/retry, default-off equivalence, ignored dynamic
  configuration, exact warning identity/order/spans, underscore suppression,
  mixed warning/error roots, and warning/error/clear transitions.
- Stale and alias-URI rejection, versioned import-overlay refresh, closed-root
  warning clearing, source-access policy, and readonly byte/metadata invariants.
- Exact 127/128/129 publication boundaries, deterministic truncation, late
  imported-template error priority on a warning-heavy URI, 128 long messages,
  bounded output framing, and lint-enabled formatting isolation.
- Both 62-case semantic-lint dependency runs, 13 frontend contract checks per
  mode, and a native initializer-side-effect result of 42 in each mode.
- Changed host files passed clang-format 22.1.8 and Ruff 0.16.7 checks.

The lint dependency runs reused the exact retained compiler, formatter and
frontend-helper binaries from PR66. Their 21 relevant source dependencies and
all recorded tool/binary hashes were unchanged. The ordinary compiler and
formatter were not rebuilt, and baseline assembly comparison was not rerun.

LSP binary SHA-256:
`5f03012af9dcc893100b13ef51cde5554a5510a9c294eab78502413f6f27f7ad`

The [compact qualification record](../evidence/lsp/lint-qualification.json)
contains exact source/tool/binary identities, phases, failure scope and counts.
Independent retained-evidence and final-claim review accepted this bounded checkpoint.

## Limits

This is focused language-tooling qualification. It is not a complete native
aggregate, new compiler semantic qualification, sanitizer run, editor UI smoke
test, emulator or physical-hardware pass. JSON-disabled configuration was not
rerun because the build graph and dependency isolation are unchanged. The
server still checks existing files synchronously and has no active cancellation,
disk watcher, incremental parser, code action or general editor extension.
AU6001 retains its documented bounded root-module rule and exclusions.

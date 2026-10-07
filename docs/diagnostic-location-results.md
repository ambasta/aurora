# Shared diagnostic location correction — 2026-10-07

## Defect and bounded change

The PR69 compiler printed `aurorac: line 4: expected i64, got bool` while its
JSON payload already carried a real line 4, column 5 source span. The same
redundant line prefix was embedded in editor messages. The retained reproduction
checks both transports before and after the correction.

The [shared contract](../compiler/DIAGNOSTICS.md#text-and-message-contract) now
keeps explanations separate from source coordinates. Lexer, parser, semantic
and unknown-function resolver constructors produce location-neutral messages;
the latter also retains its real call-token span. A common renderer produces
`path:line:column: severity code: message` for both command-line tools. Unlocated
errors use an explicit tool prefix without invented coordinates. Import context,
error families, warning severity, source byte ranges and LSP UTF-16 conversion
remain intact. Literal location-like user text is never stripped.

Six rejection consumers were updated from obsolete text-prefix assumptions to
strict expected-source-path, coordinate, severity and frontend-family checks.
The package runner still compares the complete explanation exactly. Formatter
error text/JSON parity is also exercised by its ordinary CLI test entrypoint.

## Source and fresh focused evidence

The candidate preserves the complete PR70 blank-line formatter fix, based on
main `8dd6ce464b3d9fed61c840c82223d1f4c2e792fa`, tree
`97e5f719615704df728f861c1deb56041f05db83`. The tested 779-file tree is
`bb939a0d844311501336655fa53c5a3f05996150`; its corrected source manifest is
`1b78de8a8e351bf0f77db66c871c1c1845c498b9f6863067aa70bf0b61b02ce5`.
This results document is a subsequent documentation-only addition.

Fresh C++23 builds used Debian GCC 14.2.0 with `-O2 -Wall -Wextra -Wpedantic
-Werror`. Tests used Python 3.12.14. The normal and optimized Python modes each
passed:

- 72 diagnostic CLI cases, including C++ span/rendering/escaping checks,
  root/imported lexer/parser/semantic/resolver errors, nesting/EOF, CLI/I/O
  fallback, literal `line 4:` content and existing assembly preservation
- 44 formatter CLI cases, including shared text/JSON errors and PR70 blank lines
- 62 semantic-lint CLI cases, frontend contracts and a retained native side effect
- 168 actual-server cases and 18,915 assertions, including exact editor messages,
  imported provenance, UTF-16 positions, formatting and warning behavior

Additional selected gates passed 37 source-overlay cases, 49 LSP unit checks,
207 core compiler tests, 72 module/library tests and eleven bounded-depth cases.
Updated rejection consumers passed the unsigned oracle's 4,219 native cases,
501 exact-site traps and 67 rejections; readonly spans passed 91 native cases,
25 exact bounds traps and 69 rejections. Both preserve absent/existing outputs.
The actual package rejection runner passed ten invocations across five diagnostic
families. Independent adversarial matcher checks passed 85 assertions.

All 29 scalar-only example assemblies were byte-identical to the matching PR69
compiler, with both compiler hashes recorded before and after comparison. Final
compiler hashes are:

- aurorac: `11bf0b84ec4aec1a404cb4f557f4984b51a088e7a2843006bbd9d2e51483a816`
- aurora-fmt: `fadae3a414fe8fe9f8b389af9dc3d3f4baf2e8959b3781f390aac81c0d113550`
- aurora-lsp: `8a86235f7df02de9af234b77a105f08985b799907139d0b2a49b3e7aad52397b`

## Preserved interruption and limits

The first combined run passed diagnostics and overlays, then correctly failed
the PR70 blank-line fixture: its formatter binary had read the older header
before the source join finished. That failed run and binary remain retained.
Only affected formatter/LSP frontend outputs were rebuilt from the frozen joined
source, then remaining gates passed. The rebuilt LSP binary was byte-identical;
the formatter binary changed as expected. Source bytes remained identical across
all focused and resumed tests. An original manifest incorrectly named PR69 as
its base; the corrected base metadata leaves the tested file identities unchanged.
The retained composite keeps these facts explicit rather than relabelling the
failed first run as a pass.

Whole-file style checking exposed unrelated historical long-line debt in older
runners. Their unrelated reformatting was reverted; new assertion blocks use the
120-column/four-space style. This is not a historical-tree style qualification.
The XFS and package-identity assertion edits received source/matcher review;
their full native suites were not repeated. No full compiler/root aggregate,
sanitizer, kernel, emulator, parser recovery, new lint rule or language feature
is qualified by this correction.

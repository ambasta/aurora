# Formatter blank-line preservation — 2026-10-07

## Defect and policy

The previous shared layout discarded all intentional blank lines. New regression
cases failed against both the existing `aurora-fmt` binary and the real
`textDocument/formatting` endpoint before implementation changed.

The fix is confined to `compiler/format.hpp`. Both consumers use this same code.
It retains one empty separator at structural declaration, statement, member,
initializer-entry and comment boundaries. Longer runs and whitespace-only blank
lines normalize to one unindented empty line; file/block edges and expression
gaps remain canonical. It does not invent separation, retain indentation noise,
move comments across tokens, reflow comments or amplify automatic wrapping.
The [layout contract](../compiler/FORMAT.md#layout-and-preservation-contract)
defines the exact policy. Existing token/comment equivalence, reparse, bounded
output and second-pass idempotence guards remain active.

## Focused validation

The implementation/test base is merged PR69, commit
`abca077866030bf9b13b1c49c393650df761163c`, tree
`89969b066cf8822931b4d9208bc57a6930b4db95` (778 files). GNU C++ 14.2.0 built
with C++23, `-O2 -Wall -Wextra -Wpedantic -Werror`, `_GLIBCXX_ASSERTIONS=1`
and `_FILE_OFFSET_BITS=64`.

- Shared API tests passed all goldens/current-syntax/adversarial cases, 128 seeded
  trivia variants and all 84 `.au` sources selected from examples, library,
  kernel policies and kernel-program fixtures. Each case independently checks
  token spellings, exact comment bytes/anchors, reparsing and idempotence.
- CLI tests passed 34 cases in normal and optimized Python. New coverage checks
  real stdout, unchanged input, preserved comment whitespace, blank-line
  idempotence and both clean/remaining-style-warning `--check` results.
- Real LSP tests passed 164 process cases and 18,785 assertions in each Python
  mode. New coverage opens unsaved separated source over a readonly disk file,
  checks exact whole-document text and UTF-16 EOF, repeats the request, applies
  the edit through `didChange`, and requires a subsequent empty edit list.
- Changed C++/Python files passed clang-format 22.1.8 and Ruff 0.16.7.

The real LSP's shared frontend translation unit was rebuilt. Its unchanged
protocol/main object was reused only after all six source dependencies from the
recorded native dependency graph were verified byte-identical, including
protocol, positions, transport, check declarations and diagnostics. The existing
JSON dependency was reused. The ordinary compiler did not need rebuilding.

Binary SHA-256 identities:

- Shared API tests: `0e09b0753d8f69b5d21a42412eed960b1718ecdd4fbcfa1d54b176eeee0f0cfe`
- CLI: `cb265304c1d85a015d41294435b795c4daa4a463483f76cc0afca02cdefde4fe`
- LSP: `2c6a81690892c2b4ccc8bde9ce6ba58686f188d1e593a77983343f8e0a22f596`

## Interrupted build and limits

The first gate completed API/corpus checks, then its execution session disappeared
during CLI compilation without a terminal receipt or output binary. It is not
recorded as a successful complete run. Recovery verified no surviving build
process and resumed from CLI compilation; it did not repeat completed API/corpus
work. The resumed CLI/LSP/style gate terminated with exit zero and identical
before/after source manifests. Original failure and interruption evidence remain
preserved. A copied helper's outdated base labels were amended explicitly;
recorded candidate tree hashes and file identities were unchanged.

This is focused formatter/LSP regression qualification. There are no diagnostic,
node-tree, language-semantics or protocol-option changes, and no full native
aggregate, new sanitizer, emulator or editor-UI qualification is claimed.

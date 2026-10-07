# Initial compiler-owned language server

`aurora-lsp` is an optional Linux-host C++23 bootstrap executable. It uses the
same `checkSource` frontend as `aurorac`, including structured diagnostics and
immutable source overlays. It adds no source parser, build scheduler, shell
execution, network access or workspace writes. General self-hosting is future work.

## Build and use

The ordinary compiler does not require JSON. Enable the separate LSP target
explicitly with an externally installed `nlohmann_json >= 3.11.3` development
package and the normal Meson/Ninja tools:

```sh
meson setup build/lsp -Dlsp=true
meson compile -C build/lsp --jobs 1 aurora-lsp lsp-units
meson test -C build/lsp --no-rebuild --suite lsp --print-errorlogs
build/lsp/aurora-lsp --module-root "$PWD/library"
```

Missing JSON is an explicit configuration error when `lsp=true`; it is not
needed when the option is false (the default). No third-party source is vendored
into this repository. Configure an editor's language-server command as the
absolute path to `aurora-lsp`, with repeated `--module-root PATH` arguments for
its allowed imports, language ID `aurora`, and stdio transport. Editor-extension
packaging and an editor UI smoke test are not included in this checkpoint.

For an isolated extracted development package, use its pkg-config directory
and sysroot only for configuration. For example:

```sh
PKG_CONFIG_PATH="$PREFIX/usr/share/pkgconfig" \
PKG_CONFIG_SYSROOT_DIR="$PREFIX" meson setup build/lsp -Dlsp=true
```

JSON and compiler implementation headers are confined to separate translation
units (`main.cpp` and `check.cpp`). No JSON dependency is added to `aurorac`.

## Protocol and document state

Standard output contains only Content-Length-framed UTF-8 JSON-RPC messages.
Errors and bounded logs go to stderr. Supported operations are `initialize`,
`initialized`, `shutdown`, `exit`, `textDocument/didOpen`, full-content
`didChange`, `didClose`, `textDocument/publishDiagnostics`, and
`textDocument/formatting`.

The server advertises full sync and UTF-16 only. Each change must contain exactly
one complete replacement and a strictly greater signed 32-bit version. Duplicate
opens, stale changes, URI mismatches, incremental edits and malformed document
notifications cannot replace an accepted snapshot. Unsupported requests receive
`MethodNotFound`; unknown notifications are ignored. Requests before initialization
receive `ServerNotInitialized`.

Shutdown responds with null, then accepts only exit. Exit or EOF after shutdown
succeeds; either before shutdown exits with status 1. Malformed JSON receives an
error and later correctly framed messages can proceed. Bad or truncated framing
terminates because its message boundary cannot safely be recovered.

## Source authority and diagnostics

Only absolute local `file://` URIs with empty authority or `localhost` are
supported. Percent escapes and decoded UTF-8 are checked. Remote authorities,
NUL, malformed escapes, queries and fragments are rejected. Files must already
exist under the compiler's no-symlink source policy. Opening a new nonexistent
file produces a source-access diagnostic without creating it; untitled buffers
are unsupported in this first slice.

Decoded parent (`..`) components in document URIs and CLI import roots are
rejected before normalization. This prevents normalization from hiding a
symlink or missing component from the source-access policy.

Import roots come only from explicit `--module-root` arguments. `rootUri`,
workspace folders and initialization options do not implicitly grant roots.
The shared loader opens authorized regular files using its existing
no-symlink/beneath-root policy before applying a matching immutable overlay.
No temporary source copy or disk write is needed for unsaved edits.

After each accepted open/change/close, all open roots are checked against the
current snapshot map. This simple strategy also rechecks importers when an
unsaved imported document changes. Diagnostics publish on the compiler-reported
source URI. The same code/range from multiple importers is coalesced, retaining
one compiler message. Closing a document drops its overlay and clears obsolete
publications. If another root still imports it, a fresh diagnostic from disk can
remain. Open documents' publications carry their current version; closed imports'
publications omit a version.

Each open file is also independently checked as a standalone root. A module
valid only as an import, such as an empty exported interface, can therefore
receive `AU4001: module graph must contain a function` when opened, even while its
importer's graph passes. Project-root-only checking is outside this first slice.

The compiler reports its first error per root, not every error. Compiler codes,
messages and byte spans remain authoritative. UTF-16 conversion recognizes CRLF,
LF and CR; a range that splits a UTF-8 scalar expands to cover it. An unlocated
error uses LSP's mandatory range at the root's start, explicitly marked
`[location unavailable]` and `data.rangeKnown=false`. That range is not a claim of
precise compiler provenance.

No completion, rename, hover, semantic tokens, range/on-type formatting, code actions,
incremental parsing, background cancellation or disk watcher is advertised.
Document formatting uses the same standalone formatter implementation. Disk
changes are noticed on the next accepted document update; formatting separately
reauthorizes its named source before using the accepted editor snapshot. Checks are synchronous: permitted but expensive
compiler inputs can delay later requests, and total compiler CPU is not bounded.
Cancellation notifications are ignored and cannot interrupt a running check;
the protocol tests verify that they leave document state unchanged.

## Document formatting

`documentFormattingProvider: true` advertises whole-document formatting. A
`textDocument/formatting` request requires the exact URI of an open document and
an options object containing exactly `tabSize: 4` and `insertSpaces: true`.
Other indentation choices, optional whitespace flags and extension properties
are rejected with `InvalidParams` (-32602). No option is silently honored or
ignored. This deliberately narrow policy preserves the shared formatter's
four-space layout, 120-byte soft target and exact comment bytes. Editors that
send additional options must omit them for this bounded implementation.

The standard request carries a `TextDocumentIdentifier`, without a version.
The synchronous server uses the most recently accepted full-sync snapshot and
keeps that version unchanged until it sends the response. Stale changes do not
replace it. Closed, never-opened or differently spelled URIs are rejected with
`InvalidParams`; formatting does not reopen a document or fall back to disk.
LSP `TextEdit` has no version guard: a client must discard a response if its own
buffer changed after the request. No custom versioned request is required.

The shared no-symlink regular-file policy is checked again at request time;
missing or newly inaccessible files fail even when their text is cached. The
accepted snapshot is passed directly to `format::source`, using the compiler's
lossless lexer, parser, token/comment-anchor checks, reparse and second-pass
idempotence guard. Formatting is syntax-only: missing imports, semantic errors
and existing diagnostic publications do not block it or change its result.
No additional semantic check or import resolution runs for the request.

Changed text returns exactly one whole-document edit from `(0, 0)` to the
original snapshot's UTF-16 EOF, with correct CRLF/CR/LF and non-BMP accounting.
Unchanged text returns `[]`. Whitespace follows the standalone formatter:
non-comment layout uses LF and a final newline; line-comment CR, tabs and
trailing spaces remain verbatim. No style warning is printed into protocol
stdout or silently used to rewrite a comment. The response neither applies the
edit to the server snapshot nor writes a file; only a later accepted `didChange`
updates that snapshot.

Unsupported/malformed source, failed source admission, output expansion above
1 MiB or an invariant failure returns `RequestFailed` (-32803), with no result
or partial edit. Error data contains the accepted URI/version and the original
compiler diagnostic rendered in UTF-16. Unexpected internal failures return
`InternalError` (-32603). Input/output, transport and snapshot storage bounds
are unchanged. Formatting is synchronous and cancellation cannot interrupt it.

## Fixed limits

- 8 KiB ASCII headers with CRLF; exactly one Content-Length
- 8 MiB wire payload; JSON depth 64; 65,536 parser events; duplicate keys rejected
- 32 open documents; 1 MiB each; 4 MiB total open snapshot bytes
- 16 KiB URI; 1 KiB string request ID; 4 KiB diagnostic message prefix
- Existing frontend bounds: 16 roots, 64 files, 1 MiB/file and 4 MiB/graph

These application bounds are not a production-security or whole-process memory
proof. The existing compiler resource limitations still apply.

## Focused checks

`tests/lsp-units.cpp` covers framing, URI decoding and UTF-16 conversion without
JSON or the compiler frontend. `tests/lsp-protocol.py` drives the actual binary:
lifecycle, malformed framing/JSON, versions, Unicode, unsaved root/import edits,
clearing across importers, no disk mutation and policy/storage limits. It is a
protocol test client, not a build scheduler. Its formatting transcripts additionally
cover canonical options, unsaved text, whole-document ranges, comments,
idempotence, syntax-only operation, stale/closed state, source admission,
readonly bytes and exact input/output bounds. The initial diagnostic-only
source passed its original checks fresh in both normal and optimized Python;
earlier workspace evidence was not reused. The new formatting transcripts now
pass in both modes against the fresh binary, along with all 84 current formatter
corpus sources. See the initial
[diagnostic results](../../docs/lsp-results.md) and the focused
[formatting results](../../docs/lsp-formatting-results.md).

No full native aggregate, new compiler semantic qualification, sanitizer,
emulator, physical hardware or production-security pass is implied.

References: [LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/),
[nlohmann JSON parsing](https://json.nlohmann.me/api/basic_json/parse/).

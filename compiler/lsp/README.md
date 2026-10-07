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
`didChange`, `didClose`, and `textDocument/publishDiagnostics`.

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

No completion, rename, hover, semantic tokens, formatting, code actions,
incremental parsing, background cancellation or disk watcher is advertised.
The standalone compiler formatter remains separate. Disk changes are noticed on
the next accepted document update. Checks are synchronous: permitted but expensive
compiler inputs can delay later requests, and total compiler CPU is not bounded.
Cancellation notifications are ignored and cannot interrupt a running check;
the protocol tests verify that they leave document state unchanged.

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
protocol test client, not a build scheduler. The reconstructed source passed
these checks fresh in both normal and optimized Python; earlier workspace
evidence was not reused. See the [results](../../docs/lsp-results.md).

No full native aggregate, new compiler semantic qualification, sanitizer,
emulator, physical hardware or production-security pass is implied.

References: [LSP 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/),
[nlohmann JSON parsing](https://json.nlohmann.me/api/basic_json/parse/).

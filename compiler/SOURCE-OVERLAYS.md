# Existing-file source overlays

Overlays belong to the optional language server's C++ loader (`frontend.hpp`);
aurorac and aurora-fmt read files only. Its tests run in the `lsp` suite.

`checkSource(input, roots, overlays)` accepts a `SourceOverlays` map from absolute,
lexically normalized filesystem paths to shared immutable `SourceText` snapshots.
Each snapshot's path must exactly match its map key; repeated separators and
other spellings that differ from lexical normalization are rejected. The two-argument disk-source
API remains unchanged. Located errors keep the exact shared snapshot.

An overlay replaces bytes only after the ordinary host adapter opens the root
or resolves an imported file under its existing no-symlink/beneath-root policy.
Files must already exist and be regular files. Overlays do not create sources,
invent import candidates, supply missing module roots, resolve root ambiguity,
follow symlinks, or change disk files. Lexical normalization happens only after
the file-open policy has succeeded. Empty-overlay calls do not add normalization.

Both root and imported overlays participate in the same parser/resolver/analyzer
and verified-IR pipeline. All imported-header, visibility, lifetime and type checks
remain mandatory. Original opened-file identities are preserved. The overlay map
is copied for a synchronous check; immutable snapshots cannot change mid-analysis.
Unused overlays may stay cached, but are not read as modules or given path access.
Hard links follow the existing host policy: distinct authorized paths can select
independent overlay snapshots. They are not coalesced by inode. Opened-file inode
identities remain in the checked result.

Limits apply before parsing: at most 64 overlays, 1 MiB per snapshot and 4 MiB total
cached overlay bytes. Analyzed graph bytes, combining disk and overlay files,
remain capped at 4 MiB, with the existing graph/file/depth/root limits unchanged.
Editors should pass absolute normalized input/root paths and the same immutable
snapshots used for document versions and position conversion. This API does not
implement URI validation, an LSP server or an editor's version protocol itself.

`tests/compiler/source_overlays.cpp` checks root/import substitution, diagnostic
snapshot identity, unchanged disk bytes, missing-file rejection, root/child
symlinks, symlink/.. paths, ambiguous roots, malformed map entries, exact/over
byte and file caps, and combined graph accounting. The Python wrapper provides
a fresh disposable fixture directory.

The focused 2026-10-07 gate passed all 37 overlay cases, lossless reconstruction
for all 77 `.au` files in its 647-file tested snapshot, 27 diagnostic CLI cases
and 793 existing frontend checks. A profile-corrected comparison replay compiled
all 28 examples successfully with both the new and accepted lossless compilers,
then verified byte-identical assembly and five legacy rejection/output pairs.
Source and compiler pins were unchanged. Combined native gate time was 121.27
seconds. Independent source and retained-evidence review accepted this focused
composite, including the preserved failed comparison and corrected replay.

The initial comparison attempt omitted `kernel/policies` for the newly added
`kernel-console.au` example, so the baseline rejected the missing module. That
failed harness result is retained. The correction changed only the external
runner's module-root profile; no compiler rebuild or source edit was needed.
These focused checks do not claim a full native aggregate, sanitizer or QEMU run.

The current-main composition preserved the formatter implementation and passed
a fresh formatter/harness rebuild against these snapshot overloads in 42.43
seconds, including its 77-file corpus, 128 trivia variants and 30 CLI cases.
This is a separate integration check, not additional historical lexer coverage.

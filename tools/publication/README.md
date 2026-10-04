# Byte-preserving repository snapshots

This host-only helper reads an immutable source tar, preserves UTF-8 bytes and
Git file modes, constructs canonical Git object identities, and creates checked
JSON snapshots or deltas. It never publishes, extracts archive paths, follows
symlinks or obtains credentials. Unsupported data or unsafe paths fail explicitly.

Text-mode universal newline conversion must not be used for repository payloads:
serial transcripts may contain CRLF and their receipts hash the original bytes.
Raw bytes are decoded strictly as UTF-8 and re-encoded for an exact round-trip
check before serialization. Existing snapshot output files are not overwritten.

Run the seventeen regression tests from the repository root:

    python3 -m unittest discover -s tools/publication -p test_snapshot_bytes.py
    python3 -O -m unittest discover -s tools/publication -p test_snapshot_bytes.py

Create a new snapshot from an existing archive:

    python3 tools/publication/snapshot_bytes.py snapshot --archive SOURCE.tar.gz --prefix aurora/ --output NEW-tree.json

Both flags and supported archive modes are checked by the helper. The source tar
and earlier snapshots remain unchanged. See docs/publication-integrity.md for the
historical newline correction and its scope.

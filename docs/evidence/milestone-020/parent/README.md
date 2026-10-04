# Coordinating integration evidence

The unchanged original files in this directory record the parent integration:

1. `adoption.json` binds all 18 adopted candidate paths to their exact old base
   and new candidate hashes. New files require absent targets.
2. `rebuild.log` / `rebuild.status` record a fresh release rebuild, exit 0;
   `compiler.sha256` matches the independently reviewed release compiler.
3. `make-test.log` / `make-test.status` record the fresh whole-project aggregate,
   exit 0, after adoption.
4. `runtime-span.log`, `runtime-pin-fault.log`, `normal.log` and their `.status`
   files record three actual fresh UEFI profile successes, each exit 0. The last
   profile reports the normal value 42 and AURORA_UEFI_OK. The root coordinator
   confirmed final normal image restoration.
5. `source-before.json`, `external-before.json` and `after-verification.json`
   record 359 source inputs and 183 external pins unchanged across those gates,
   including the exact release compiler hash after testing.

These three selected profiles are not a fresh full 166-mode suite. No shared
kernel-image rebuild was performed by the evidence finalizer or archive reviewer.

After these gates, final acceptance prose changed README.md, the completeness
matrix, roadmap, verification record, compiler/NESTED-VALUES.md, compiler/README.md
and library/README.md. No implementation, Makefile, test or fixture changed.
`final-documentation.json` identifies these seven documentation-only differences
from the captured test inputs and verifies all other captured source hashes.
The original source manifest is preserved unchanged rather than retroactively
rewritten to describe prose that was not present during the tests.

Raw files were copied with byte operations, preserving every newline/control byte.
The parent logs are not rewritten, filtered or normalized. Exact copied hashes
are in the checkpoint's curation-manifest.json. Historical candidate handoff text
that says integration is pending remains historical and is superseded by these
known-status parent outcomes.

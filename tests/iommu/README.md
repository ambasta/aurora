# Offline IOMMU diagnostic controls

Run `make test-iommu-diagnostics` from the repository root. This runs optimized
Python with no compiler, C model, image, QEMU, guest or hardware access.
Meson registers it once in `dev` and `full`; root `make test` includes the same
compiler-free prerequisite under its existing test-context guard. This adds no
runtime gate and does not make Meson equivalent to full root native acceptance.

The driver checks six exact patch/fixture identities, preserved historical
expectations and routing, then exercises the strict in-memory patch parser and
the two relocated authored mock suites. `mock_access.py` drives all 13 access
cases against synthetic RAM/register behavior plus 14 mutant scenarios and
additional oracle controls. `mock_command.py` drives 28 new command cases against
synthetic state plus 15 mutant scenarios; the two frozen cases are identity/import
checks only. Process creation is actively blocked before any mock runs.

Mock outcomes test the fixture's ability to reject authored wrong behavior. They
are neither independent C-model evaluation nor replay of recorded runtime bytes.
No runtime result may be synthesized from mock success. Temporary mock directories
are unique and removed; the source tree and fixtures are read-only inputs.

`fixtures/` contains three byte-frozen historical files. Preserve their existing
layout and hashes, including every old one-event-per-eight-byte expectation.
The [model instructions](../../tools/qemu-amdvi/README.md) describe external source
reconstruction, explicit builds and separately admitted runtime preparation.

## Portable mock scope versus historical preparation

The command suite has 56 checks, compared with 65 in the original execution-workspace
preparation. The [exact mapping](mock-scope.json) retains 53 names, removes 12
workspace checks and adds 3 repository checks. All 28 behavioral cases,
all 15 mutants and both driving loops are AST-identical to the original
preparation. The mock DMA-count and write-payload checks use explicit failures
so they remain active under `-O`; memory behavior is unchanged.
The wrong-target-path guard is retained using synthetic
metadata without a binary read. The two frozen runtime cases remain import/identity
checks only in either mock suite.

Removed comparisons concerned two original external fixture paths (replaced by
exact fixture hashes), the external source target (now checked separately by
`verify_source.py`), the exact supervisor/wrapper, four command/plan/argv/order
relationships, the built target binary, and unused execution-release/marker state.
Added controls check two frozen fixture hashes and absence of a runtime target in
the repository. The preexisting full 30-case/matrix checks remain. Thus this is a
portable static/mock derivative, not byte-identical or equally broad preparation
coverage. Runtime supervision, pinning, source/build provenance and one-use release
state must be established in each separate execution workspace.

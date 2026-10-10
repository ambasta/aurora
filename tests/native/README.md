# Canonical root native Meson graph

`meson.build` registers the complete non-compiler root Make prerequisites. The
machine-checked `inventory.json` maps all 38 prerequisite goals to complete
commands, including ordinary/optimized Python modes and compile-negative sweeps.
The existing `tests/test-inventory.py` calls `inventory.check`; its self-tests
reject missing sources, goals, registrations, full-suite membership and modes.
Any new top-level test source or shell test wrapper needs an explicit inventory
classification. A shell-wrapper change requires command-level coverage review
before updating its recorded digest.

Meson/Ninja owns fixed host binaries, the BIOS/UEFI/console Aurora objects, the
UEFI assembly memory object and the round-robin symbol substitution. Their
outputs live beneath the configured build directory. A depfile records the
fixture source and all policy modules; imported-source edits rebuild the fixture
without rebuilding an unchanged compiler. Distinct root `-O1` framebuffer tests
remain separate from the existing `-O2` developer variants. Only identical
repeated program/layout/image commands are deduplicated, with the equivalence
recorded in the manifest.

Complete policy-vector runners and complex pin/NVMe/dormant mutation and negative
compilation sweeps remain their existing runners. The adapter binds inherited
bare `g++` calls and `CXX` to Meson's configured native command. It never builds
Aurora or turns an observed digest into an acceptance pin. The selected-compiler
mode records artifact stability only. Candidate-local policy receipts retain
their unique existing source/build directories; temporary subprocess files are
private to each invocation. Shared fixed-output pin/NVMe/BIOS wrappers take one
source-local kernel lock. Other tests remain parallel.

The protected-console note runner executes actual Aurora update/project/client/
service code with real Mailbox transactions. It covers constructor equivalence,
closed record/canary checks, changing caller-selected bytes, missing/empty/short
values, cancellation and fresh readback, plus separately trapped emitted faults.
The existing copied ABI checker verifies its exact note layout; no new decoder
or guest is introduced. It is included in the `test-program-stream` selection.

The copied snapshot fixture adds one selected-compiler native runner with a
private Meson output directory. It executes the real producer/client/service,
Mailbox controls and linked copied-record ABI checks; an optimized ordered
transcript self-test is separate. Neither registration executes a guest. The
composed image builder separately invokes the existing linked stack analysis.

All added gates belong to `full` and `slow`; `integration`, `boot`, `storage` and
`semantics` permit narrower selection. Existing `dev` coverage is not expanded.
No QEMU guest or hardware action is included. The BIOS native gate still runs
the existing normal image builder and its complete image/negative-control check;
it is not a smoke boot. Explicit pinned Make acceptance remains a separate path.

Every merge or release requires complete final-source GCC 16 `full` execution
and independent review under [the development contract](../../AGENTS.md).
GCC 14 is optional targeted compatibility evidence. AST, inventory self-tests and
static path/graph checks do not substitute for native execution, final-source
equivalence evidence, sanitizer or emulator qualification. Historical results
retain their original source/tool scope.

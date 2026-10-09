# Root native Meson migration candidate

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

All added gates belong to `full` and `slow`; `integration`, `boot`, `storage` and
`semantics` permit narrower selection. Existing `dev` coverage is not expanded.
No QEMU guest or hardware action is included. The BIOS native gate still runs
the existing normal image builder and its complete image/negative-control check;
it is not a smoke boot. Explicit pinned Make acceptance remains a separate path.

This is an unqualified migration candidate. AST, inventory self-tests and static
path/graph checks are not native execution, final-source equivalence evidence,
GCC 14/GCC 16 acceptance, sanitizer or emulator qualification.

# M022 source-only integration handover

Candidate: /workspace/scratch/48c5de6446f8/aurora-m022-method-candidate
Accepted main has not been edited or adopted. No kernel/image/integration commands
were run by this worker. Parent owns integration authorization and acceptance.

## Deliverable

Apply/review the28 source/document paths from change-manifest-final.json and
source-only-change.patch. Patch dry-run against M021 passes. Four final
status-only documentation updates are identified separately from the frozen
release/fatal test inputs. Do not copy candidate build/history/temp directories.

- Release compiler: e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e
- ASan/UBSan compiler: d3033d68ad6308030a057c9eaf2b2e258b15e245ca84a22cc2fce1873847adcd
- M021 baseline: d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64
- Primary contract: compiler/METHOD-VALUES.md
- Executable library: library/std/array.au exchange(std::array replacement)->std::array
- Native example: examples/method_value_exchange.au returns42
- Verification/limits: evidence/VERIFICATION.md
- Independent review: review/independent-method-review/REVIEW.md and addenda

## Passed isolated gates

Complete frozen release and fatalASan/UBSan compiler targets pass with unchanged
source-input inventories, status0. Source219 executions; directIR51; independent
nativeABI21; historicalIR964; all legacy compiler/library/oracle/module/host-I/O
suites, scalar semantics controls/default/stress, old-library M021 differential,
independent source/all-capacity models and isolated48-step stress passed.
Counts overlap; see verification for precise independent/unique scopes.

C++ builds were serialized under2GiB address-space cap. Only large historicalIR
sanitizer debug metadata used-g1. Address/undefined instrumentation, no-recovery,
fatal halt/abort stayed enabled. Sanitizer runtime address space was uncapped.
The first concurrent stressSIGKILL is retained and unclassified; isolated exact
retry and complete stress passed without changing the program or instrumentation.

## Required parent next gate

This changes the backend ABI boundary. Fresh parent make test AND all166 existing
emulator modes are required, with normal-image restoration and exact-source
before/after evidence. Do not substitute M021's three selected profiles or reuse
historical full-suite evidence. Independent private nativeABI checks do not prove
kernel integration, whole-program stack/resource safety or physical AMD support.
No shared kernel images, activeAMD/QEMU setup, mutable-byte candidate, helper
security work, network/install/auth/upload/publication or main adoption occurred.

# Native client-disposal recovery plan — focused qualification

The real `Dispatcher::dispose_client` now requires an accepted copied Aurora
recovery plan before selecting its receipt/consumption treatment. Live identity,
quiescence, mailbox effects, copied receipt handling, grant revocation and domain
retirement remain trusted bootstrap responsibilities. See the
[contract](kernel-client-disposal-contract.md). This is a small policy port,
not a complete dispatcher or kernel rewrite.

## Original qualification source and scope

Implementation began on accepted PR84 (`2427806afcd64afc0871cda78130a388a32cc1f8`)
and was reconciled with the complete accepted PR85 resize delta, then-main
`36219aef05cf74db710b50fae9011190f3bfcee1`, tree
`d1acfbd64ca74af747f8bdf5faa19cfc85bd2f87`.
Compiler/library implementation was unchanged. The original runs used the reviewed compiler
SHA256 `512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`.
The exact 877-file tested source stayed unchanged through final native and guest
execution. Subsequent publication changes are documentation-only and require
separate final review.

Qualification is dependency-focused. It is not a new complete root native run,
complete all-mode emulator run, physical-hardware qualification, self-hosting,
whole-language safety proof or equivalent-C performance result.

## Native and hosted gates

The new independent gate passed under ordinary and optimized Python, and again
with fatal hosted ASan/UBSan:

- 24 finite phase/state contexts: six accepted plans and eighteen refusals
- 12,737 full-width producer vectors and 87,128 decoder vectors
- 18,396 malformed/refused producer substitutions through the real dispatcher
- 338 pre-producer authority rejection controls
- 252 genuine disposal/peer lifecycle and payload combinations
- 4,096 genuine Aurora class/enum copy-probe repetitions
- 18 source rejection fixtures, each checking absent and preserved existing
  output: 36 artifact-preservation checks

The independent literal oracle is not derived from the production branch,
nominal enums, wire decoder or its result. Substitution renames only disposal;
IPC and round-robin remain genuine. Refusal tests verify complete dispatcher and
registry byte preservation and the global generation sequence, with live peers
in pending, delivered and terminal/retained-receipt states. Public APIs still
reject a selected delivered offender before calling the policy.

The unchanged historical disposal regression also passed its 65,536 exhaustive
four-operation sequences and 4,096 128-operation model traces at its established
`-O1` host level. New ordinary producer/decoder/adapter tests use `-O2`.
Warnings remain fatal throughout.

Fresh old IPC transition gates passed ordinary and fatal sanitizer runs,
including the downstream accepted-cancellation/denied-consumption committed
prefix, preserving its exact refusal/retry behavior. Fresh round-robin and
IPC/dispatcher/service-budget/user-run host suites also passed ordinary and fatal
sanitizer runs. Clock/Make-contract controls and the focused public
`make test-client-disposal` passed using the shared pinned compiler, without
claiming a full native aggregate.

Generated Aurora assembly is not instrumented by C++ host sanitizers.
LeakSanitizer remains disabled for the executor restriction; no leak-clean claim.

## Exact linked-image and stack admission

Independent pre-guest review admitted all 36 selected UEFI snapshots and normal
BIOS, binding the current source, generated objects, linked ELF bytes, flat
payload, PE image, installed user images, runtime metadata and execution
harnesses. Its admission SHA256 is
`b251229b6e70b4a2db57fe62381275b8607554b05438f67c7350ceaa5c133712`.
All 34 shared-runtime graphs were reviewed, including recovery and existing
exception/interrupt paths. Old source or stack receipts were not substituted.

The supervisor stack has 16,384 actual usable bytes in four mapped RW-NX pages;
its guard pages lie outside that interval. Exact entry bytes leave no hidden top
reservation. The largest current normal call-chain peak is 14,680 bytes, sixteen
more than the historical value. Retaining a conservative 1,024-byte synchronous
fault reserve gives 15,704 total, leaving 680 bytes before the lower guard.
The separately calculated current synchronous delivery/diagnostic upper bound
of 166 bytes fits that reserve. This margin must be recalculated for later
changes. It is not a nested-fault, NMI, SMP or whole-firmware stack proof.

The reviewer also checked exact RSP0/timed supervisor paths, call alignment,
private ABI copies and current corruption guards. The disposal output profile
retains the genuine Aurora call, volatile high-bit store/reload, dependent OR
and ordinary rejecting branch in the final linked image. Existing budget,
round-robin and IPC output guards were freshly reviewed as part of this graph.

The separate owned-byte profile's final payload and PE are byte-identical to
accepted PR85 admission artifacts, so its profile-specific 2,592-byte path plus
512-byte fault reserve is rebound to exact bytes. Other profile-specific stack
contracts, including runtime-table gates, are not claimed by this focused run.

## Actual guests and restoration

All 37 exact admitted executions passed their existing transcript validators:

- All 17 existing user-lifecycle modes plus `user-disposal-input` and
  `user-disposal-output`
- Dispatcher success, budget, fault, mixed outcome and policy-output modes
- IPC success, fault, cancellation and all four input/output policy guards
- Service-budget success, fault and policy-output modes
- The joined PR85 owned-byte profile
- Final actual normal UEFI and normal BIOS restoration boots

Both new fault modes first complete the genuine authenticated request-bounds
fault and supervisor restoration. They reject the copied invalid phase or
corrupted result at `user terminal disposition`, before disposal/revocation/
retirement/rebind markers. Existing completion faults retain the committed reply
and receipt, while peer progress, fresh incarnation and stale-grant denial remain
intact. Normal IPC/dispatcher results remain 42/73 with the established order.

Execution used the exact pre-reviewed snapshot bytes. The production launcher's
clock-plan command and existing validators were retained, with admission-bound
metadata checked before/after each guest. Every run retained its raw log, exit
status, effective command, image/tool pins and validator outputs. Normal UEFI
image bytes were restored after each UEFI run, and both final normal images were
actually booted. The tested source remained byte-identical throughout.

## Preserved development failures and corrections

1. The first independent run passed new producer/decoder/adapter checks, then
   GCC14 rejected the unchanged historical disposal regression at `-O2` with
   `-Werror=array-bounds`. Its established public recipe is `-O1`. Only this old
   regression's runner flags were corrected; its source and warnings were not
   weakened. The failed run remains retained; fresh complete corrected ordinary,
   optimized and sanitizer runs passed.
2. Initial clock controls exposed two stale numeric inventories after adding
   exactly two modes. The inventory was extended without changing old mode
   clocks. The complete corrected clock suite passed. The original 17-mode
   user-phase synthetic fixture corpus is independently pinned across both
   client-interrupt variants.
3. A build-routing control had a pre-existing positional assumption that
   `test-round-robin` immediately follows `test:`; accepted PR84 already has
   `test-console` first. This failure was reproduced on PR84. The control now
   checks the exact prerequisite anywhere on that target line; the aggregate
   was not reduced. Fresh ordinary and optimized controls passed.
4. A documentation merge conflict and one host-format line-length finding were
   corrected before the final frozen source. Both PR85 behavior and this port's
   status were preserved. Final host style checks passed.

## Final acceptance

Independent final source/evidence review accepted this exact focused checkpoint,
including 74 ordinary/optimized replays of all 37 retained guest validators,
independent reconstruction of the saved native expected vectors, source/image/
command/metadata bindings and documentation-only finalization. No blockers
remain. The acceptance record SHA256 is
`1e33a5438c13981a2117e58b4426442650f9eaa7d0ea5b05a5b68e3badea36a9`.
Its report and final seal are retained with the raw audit package. Acceptance
status wording was checked separately after that seal; no executable input
changed and no broader qualification is implied.

## Repaired-main integration — PR88

The feature was subsequently joined onto repaired main PR88, commit
`fd65276ebba04305063461f4edcdd08b1c55e2a8`, tree
`3789df38d7dff1845a99d7257a607353bfb8db22`. The join contains 879 source files.
All 21 repair paths are preserved: eighteen byte-exact and three explicit
Makefile/README/completeness overlaps retain both changes. This includes the
38-test dev/9-test slow partition, strict GNU-stack host bridge, formatter repair
and NVMe BLOCKED/FAIL outcome correction. No old-base tree was reused.

Fresh Meson compilation produced SHA256
`f0dee7330d02dfff6e145e1f8a6fbf78291c986667c0c07448140f294d5a1a65`, exactly
matching the accepted PR88 Meson compiler. The original guest compiler remains
the separately identified `512050d5...` binary above; old receipts were not
relabeled. The changed formatter header is outside aurorac's independently
checked sixteen-file transitive main/frontend/x86 source closure.

Fresh joined gates passed:

- All 38 dev tests, after an explicit one-job build and `--no-rebuild` test run
- Disposal ordinary/optimized/fatal-host-sanitizer gates and the focused public
  Make target, with the current compiler
- IPC native and fatal-host-sanitizer gates, including committed-prefix recovery
- Public developer-command controls and both Python modes of emulator-clock and
  compiler-build-contract controls
- Nine representative UEFI builds and normal BIOS, without guest execution

The first dev invocation allowed Ninja's default parallel rebuild; one cc1plus
was killed and Meson exited 125 before tests ran. That failure is retained.
Explicit serial compilation followed by all 38 tests passed; no source change
was made in response, and the kill's underlying cause was not established.

Independent comparison found 229 conservative execution inputs unchanged. All
ten representative snapshots matched the prior admitted bytes, including final
PE/ELF/payload/disk and the relevant objects, active user images and metadata.
The ten builds cover all fourteen distinct generated-assembly classes used by
the original 37 guests. Thus the original guest and exact stack evidence applies
through verified execution-input and byte identity, rather than a claim of new
guest runs. Current compiler/tool identities and the full repaired-source join
are retained separately from the original admission.

The 879-file joined source remained fixed during these gates. Only this report
and the completeness summary were then updated. Independent final joined
source/evidence acceptance remains a separate publication gate. There is no new
slow-suite, whole-47-suite, complete root-native, all-mode or hardware claim.

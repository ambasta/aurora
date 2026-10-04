# M022 copied ordinary method parameters: isolated candidate

Main accepted M021 and shared kernel/image work are untouched. This source-only
candidate adds copied concrete class method parameters and std::array exchange.
It adds a NEW private combined receiver/record/result convention without a new
IR instruction. Final release compiler e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e;
final host ASan/UBSan compiler d3033d68ad6308030a057c9eaf2b2e258b15e245ca84a22cc2fce1873847adcd.
Immutable M021 baseline d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64.

## Contract

Complete named class argument locals become distinct immutable snapshots at
their left-to-right evaluation positions, before receiver acquisition. Repeated
sources and receiver-as-argument are legal through independent copies. Callee
parameters remain immutable. Results use a pristine exact nominal destination
separate from receiver and every argument snapshot. Existing scope, privacy,
constructor completeness, receiver-cycle, nominal/depth/leaf/frame and graph
limits remain. No heap/reference/span method boundary, generic method, temporary,
class-field reassignment, new template grammar or source-visible capability is
added. The six-argument combined mode carries R10 receiver, R11 all-argument
record and RAX result address, saved privately at source-frame+8/+16/+24 with
32-byte hidden overhead. All existing ABI modes are retained.

std::array exchange copies old contents to an independent returned array and
replaces its receiver from an immutable replacement snapshot. Its implementation
uses existing qualified injected self `std::array` without explicit template
arguments. parser.hpp is byte-identical M021; bare/builtin array reservations
remain intact. The initial bare-array failure and abandoned parser exception are
recorded in DEVELOPMENT-CORRECTIONS.md, not hidden as successful development.

## Finite evidence, not additive proof counts

- Focused source suite:152 fixtures/219 executions,72 full-width native returns,
  13 exact-site traps,67 rejection fixtures each with absent and pre-existing
  output. Explicit assertions remain enabled under Python -O.
- Independent new direct IR:51 cases,5 accepted/46 malformed rejected. The
  historical IR target retains964 cases with five narrowly scoped source-contract
  or diagnostic migrations; previous blanket restrictions are not called unchanged.
- New native ABI:21 cases use independently authored assembly on one side of
  each boundary, including both directions of new scalar/class-result modes,
  literal positional/padding records,3072-byte six64-leaf maximum records,
  empty/composed values, odd operand depth, nested clobber/forwarding, exact saved
  slots/alignment and eight legacy-mode controls.
- Independent reviewer:17 source probes +15 qualified-self controls and256
  Python-list model cases (all64 capacities ×4scalar types) per compiler pin.
  Reviewed source/ABI protocol, not only emitter-to-emitter agreement.
- Focused model stress:seed983822,48steps,28native models on each pin. The first
  concurrent sanitizer stress process was SIGKILLed with no diagnostic. Exact
  isolated input replay compiled/native-validated42 in3.505sec with1,217,592KiB
  peakRSS, followed by complete isolated28/28pass. OOM is plausible, not proven.
  The firstfailure is preserved. This is not a compiler resource guarantee.
- Old-library differential:227 untouched M021 contract fixtures (217source
  hashes;105accepted/122rejected) all match statuses and accepted assembly;
  37 unchanged example/kernel-program/library-example inputs also match exactly.
  BOTH compilers use frozen old library input copies. New library output is
  deliberately kept out of old-input ABI equivalence claims. Corpora overlap.
- Scalar semantics runner:9 controls;630default release and fatal-sanitized
  cases;1526release stress cases. Full compiler target also includes signed/
  unsigned mathematical oracles, initialization-fact tests, exhaustive dispatch,
  other native IR batches, module graph, source/output host adapter checks.

## Gates and resources

Frozen full release target passes in release-final.log/status and the receipt
pins every source input unchanged before/after. Instrumented full gate is pending.
Exact commands, fatal options and sampled disk/free-space receipts are generated
by run-final-gates.py. C++ compilation alone is serialized under a2GiB address
space cap. Runtime ASan address space is never capped. Full -g is used except the
large historical IR sanitizer executable uses permitted -g1. Runtime sanitizer
instrumentation remains address+undefined, no recovery, halt+abort-on-error.
LeakSanitizer alone remains disabled as in prior milestones. XFS harness now
accepts its historical exact options OR the same options plus abort-on-error;
independent review confirms no weakening.

Only this candidate's completed successful generated trees are losslessly
archived. Before removing expanded recoverable duplicates, every path/type/mode
and file byte hash is verified against the archive and originals. Failed runs,
source inputs, authored reviews, binaries and historical evidence remain intact.
The candidate budget is384MiB and free-space floor1GiB. Parent broader integration
is neither run nor claimed here.

## Remaining acceptance

Complete frozen fatal ASan/UBSan aggregate, final source manifest/patch and parent
handover remain. Parent adoption, fresh make test, all166 required existing
emulator modes, normal-image restoration and physical qualification are separate.
No formal whole-language safety proof, global stack/resource bound, stable external
ABI, production-security, hardware-support or equivalent-C performance claim.

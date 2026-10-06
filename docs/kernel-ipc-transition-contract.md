# Copied Aurora IPC transaction transition candidate

## Dependency and observable gate, before source implementation

This candidate starts from accepted PR26 main
`3ac216b64caf8b769147f1864aa8389011f0112b`, tree
`e47002622df3e8d13d9496cd09fe90b33794335b`. All 569 source files were copied
and checked against manifest SHA256
`184bc9512620c4e7d217166f1453fa98c18f0c8dd6109a16b7e703b898b727db`.
The reviewed compiler hash is
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
No build output was copied. Final integration must use actual accepted main if
the independently developed portable test workflow lands first.

The next dependency is an independently reviewed copied-value contract, followed
by source authoring and an early reviewable checkpoint. No compiler build,
native execution, image build or QEMU run is admitted by this document. Those
stages use the established owned runners and independently admitted measured
budgets. All failed or interrupted attempts retain their evidence.

The observable goal is that all six real `Mailbox` operations depend on Aurora
for the transition, next state and payload-treatment selection, while actual
identity, storage and commit authority remain in trusted C++/assembly. An unused
module or comparison against the old C++ decision does not meet the gate.

## Accepted-base portable workflow integration

The current local source candidate reconciles the reviewed final PR27 tooling
and documentation overlay with the IPC source. PR27 merged at
2026-10-05 22:52:33 UTC as main `772b9c8a6291aa3cc656b409ce0263f73d45b034`,
tree `62a2728942d9c36df16bd00189260f6a94cb847e`. The 574-file source was
historically identified by manifest
`cad13bfbf84ff657b97ac9c4d44f4423d9238fe524119cb4727ad43eb4cf581c`.
After the environment reset, its published file content and modes were independently
Git-verified under recovery manifest
`aa0e772957f2248bde3b369f4fc9dd3092a6faf0a4d392792dde176a553e81dd`;
exact historical PR27 manifest bytes were not restored. This is a fresh
reconstruction, with no presumed equality to the lost provisional integration.
The original PR26/IPC ancestry and failed/interrupted receipts retain their scope.
Independent review and the exact final source/runner binding remain explicit gates;
this integration itself is source-only and has not been qualified or published.

`make test-ipc-transaction` uses the shared fresh-build compiler receipt or an
explicit externally reviewed pin. IPC is the sixth native cap consumer, with a
128 MiB focused default and 1024 MiB explicit aggregate ceiling. Direct shell
invocation requires supplied `AURORAC` and exactly one identity argument pair,
`--compiler-sha256 DIGEST` or `--developer-build-receipt FILE`. It never rebuilds
the supplied compiler or treats an observed self-hash as approval. The standalone
runner's `--check-cap-only` route remains compiler-free and cannot issue native
acceptance. Full native/model/sanitizer and emulator gates remain unrun for this
integration; prior five-consumer tooling results do not qualify it. See the
[developer-test contract](developer-test-contract.md).

The provisional 51-mode UEFI clock qualification is source preparation only;
the 126 other modes, capacity probes and normal restoration boots retain their
original clock. See [emulator clock contract](kernel-emulator-clock-contract.md)
for the preserved wall-time failure, exact argv binding and pending requalification.

## Public copied API

`kernel.ipc_transition` exports an inline `TransactionSnapshot` holding three
independent u64 copies: phase, state and scrubbed. Its constructor and readonly
accessors neither validate nor grant authority. `transaction_transition(u64
operation, TransactionSnapshot snapshot)` returns an independent inline
`TransactionDecision`, with a closed `TransactionAction`, next-state u64 and
closed `TransactionEffect`. The ordinary source API has no packing, raw pointer,
external span, unsafe escape, allocation, recursion or retained reference.

Numeric copied domains are deliberately explicit and validated before use:

- Operation: 0 submit, 1 receive, 2 reply, 3 consume, 4 cancel, 5 recycle
- Phase: 0 inactive, 1 request, 2 service, 3 completion
- State: 0 idle, 1 pending, 2 delivered, 3 replied, 4 cancelled, 5 consumed
- Scrubbed: 0 false or 1 true; this describes actual host payload storage

Any out-of-domain full-width input returns action `invalid`, next state zero and
effect `none`. Valid but disallowed combinations return `refused`, next state
zero and effect `none`. Valid allowed combinations return `accepted` as follows:

| Operation | Phase | Prior state | Extra predicate | Next state | Effect |
|---|---|---|---|---|---|
| submit | request | idle | none | pending | submit_request |
| receive | service | pending | none | delivered | deliver_request |
| reply | service | delivered | none | replied | store_reply |
| consume | completion | replied | none | consumed | consume_reply |
| consume | completion | cancelled | none | consumed | consume_cancelled |
| cancel | inactive | pending or delivered | none | cancelled | cancel_request |
| recycle | inactive | consumed | scrubbed | idle | recycle_record |

Scrubbed is not an occupancy flag: a real all-zero request or reply is valid.
Payload words do not enter Aurora or its scalar transport; zero and UINT64_MAX
remain exact full-width payloads. A replied transaction cannot be cancelled or
replaced by a second reply. A cancelled one cannot receive or reply. Neither
terminal state can be consumed twice. Refused and invalid results expose no
successful next-state or effect facts.

## Private transport and independently checked safety boundary

`examples/kernel.au` imports the module and implements the replaceable hidden
scalar symbol `aurora_kernel_ipc_transition(operation, phase, state, scrubbed)`.
Only copied u64 arguments and one u64 result cross this bootstrap seam; this is
not a source-language foreign ABI. Encoding is:

- 0: invalid copied input
- 1: ordinary refusal, with every remaining bit zero
- Accepted: low byte 2, next-state byte at bits 8..15, effect byte at bits 16..23
- Effects 1..7 respectively name the seven accepted rows above
- Bits 24..63 are always zero

The C++ decoder returns a classified result: malformed transport, canonical
ordinary refusal, or a checked transition. With original inputs in range, encoded
1 is refusal even at an otherwise allowed transition; encoded 0 is a copied-input
or producer-boundary failure, classified as malformed by the host. With original
inputs out of range every word is malformed, including 1. It independently validates original
input ranges, the exact refusal representation, reserved bits, effect/state
coherence, source-state safety and the operation/phase that can authorize each
effect. Use a bounded declarative invariant table rather than reintroducing the
old deciding switch. A canonical refusal remains a refusal even when the input
would permit success: no C++ fallback is allowed. A malformed or refused result
cannot mint a generation or alter any mailbox byte. Decoder results carry no
DomainHandle, grant, transaction stamp, pointer or other minted authority.

These safety checks necessarily overlap transition preconditions; their purpose
is to reject a corrupted producer, not to choose success without Aurora. Tests
must explicitly substitute refusal at every otherwise successful real operation
and observe no commit, proving production depends on the result.

## Host responsibilities and commit ordering

C++ continues to own and check DomainRegistry/DomainHandle identity, endpoint
slot and generation, client/service rights, actual participants' liveness,
nonzero exact transaction matching, the global generation sequence and its
ceiling, binding/revocation, actual payload copies/scrubbing, and atomic commit.
No authority identifier enters the pure policy. Host authority checks occur
before calling the pure policy. The host snapshots actual phase/state/scrubbed,
calls Aurora, and independently decodes against the original unmodified copies.
Only a decoded accepted transition permits the corresponding host effect.

Submit checks live participants and client ownership, calls and decodes policy,
then attempts to mint, and only after successful mint copies the request and
commits transaction and returned next state. No policy refusal or malformed
output consumes a global generation. Other operations retain these host gates:

- Receive/reply: live participants, service ownership and matching transaction
- Consume: client ownership and matching transaction; replied completion also
  requires live participants, while cancelled completion may outlive the service
- Cancel/recycle: the trusted continuation supplies phase, with no user identity
  or endpoint inferred from submitted data

The host executes only the decoded allowed effect: submit copies request;
delivery copies then clears request; reply stores the full word; either consume
copies the selected outcome, scrubs payload and clears transaction; cancellation
scrubs payload but keeps transaction; recycle clears transaction. State commits
use the decoded next state. Bind/revoke remain outside this six-operation scope,
with their accepted preconditions and global-generation behavior unchanged.
The no-mutation guarantee applies to each individual Mailbox call and its peers,
including the global generation sequence. It is not rollback for a composite
Dispatcher operation: dispose_client can have committed cancellation before a
later consume refusal; cancel_pending can have cancelled an earlier mailbox
before a later refusal. Earlier successful effects remain committed, the refusing
call preserves every record, and the aggregate cannot claim its uncompleted
outcome. Native hostile-producer tests cover these sequences; runtime unexpected
composite failures remain fail-stop. No aggregate rollback protocol is added.

All calls are synchronous under the accepted single-CPU bootstrap model. This
adds no cross-CPU concurrency/atomic-memory, general scheduler or service API.

## Real consumers and call-context review

`kernel/ipc-policy.hpp` is the operational seam, so ordinary IPC, dispatcher,
client disposal and service-budget restart all use the real Aurora decision.
Every hosted consumer that instantiates Mailbox must link its generated object,
including the substituted-round-robin-producer test. Its alternate symbol must
replace only round-robin, leaving transaction policy genuine.

Submit/reply execute under the already validated privileged exception entry in
`kernel/uefi/runtime.cpp` and `dispatch-runtime.inc`, BEFORE CR3 restoration.
Receive/cancel/consume/recycle also execute on restored supervisor paths. Review
must measure generated policy/wrapper/accessor frames and compiler private-copy
ABI, call pushes, register preservation and alignment together with all live
caller frames in BOTH 16 KiB contexts. Reusing the earlier round-robin
supervisor-only proof is insufficient. Preserve the isolated BIOS root exactly.
The changed UEFI module graph requires fresh budget-policy-output and
round-robin-policy-output linked-image guard qualification, plus new transaction
output guards. Existing layout, relocation and payload checks remain active.

## Acceptance gates

1. Independent finite operation/phase/state/scrubbed truth table of 288 tuples
   (15 accepted and 273 refused), all six
   operations, unknown codes and full-width/high-bit/random inputs. Invalid
   copied input rejects normally rather than trapping. Full-width payload tests
   use both zero and UINT64_MAX.
2. Decoder refusal classification and all 73,728 combinations of action 0..3,
   next state 0..7 and effect 0..7 over the 288 valid contexts, followed by
   field-boundary/high-bit/random encodings and all 64 output-bit mutations, terminal reversal/invented delivery/incorrect effects and
   reserved bits. Actual-Mailbox substituted producer controls preserve every
   object byte and global generation behavior on refusal/malformed output.
3. Independent class input/result copy tests, encapsulation/type/readonly
   compiler-negative cases and unchanged-output rejection checks. Existing
   `kernel-ipc.cpp`, `kernel-dispatch.cpp`, `kernel-client-disposal.cpp` and
   service-budget tests link real Aurora; repeat with fatal ASan/UBSan.
4. Independent source, native truth-table, private ABI/IR, caller-stack and final
   linked-image reviews before actual emulator admission.
5. Four actual profiles: `ipc-policy-request-input`, `ipc-policy-request-output`,
   `ipc-policy-cancel-input` and `ipc-policy-cancel-output`. Request profiles
   corrupt the copied phase or actual result after the genuine user envelope and
   authority checks, before submit commit. Cancellation profiles first complete
   submission, delivery, an authenticated service bounds fault and supervisor
   restoration, then corrupt the copied phase or result before cancel commit.
   Input corruption sets only the local phase copy to UINT64_MAX and decodes
   against the original valid phase. Modify only local copies/actual result, not
   live state or authority. Output corruption uses a volatile reserved-bit mask
   after the real Aurora call; final disassembly proves the call, dependent OR
   and ordinary decoder failure branch survive. Fault traces must stop before
   that operation's commit, success markers or any later lifecycle event.
6. Actual normal IPC result 42; dispatch results 42/73 and selection order 0,1,0;
   service-fault/budget cancellation, first-terminal preservation, cancellation
   consumption, retirement/rebind and a new transaction. Complete fresh native
   aggregate and all 173 baseline production QEMU modes plus the four new
   modes, three separately counted BIOS capacity probes and two final actual
   normal BIOS/UEFI restoration boots. Record all exact tool/source/input pins,
   raw traces, terminal quiescence and independent final review.

Existing accepted receipts remain historical evidence, not acceptance of this
changed graph. Source checkpoints are unfinished until these gates pass. This
increment does not establish a full Aurora kernel, Linux/device compatibility,
physical AMD qualification, whole-language memory-safety proof or performance
parity with C.

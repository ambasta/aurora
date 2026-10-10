# Copied kernel policies

These Aurora modules calculate bounded decisions over copied values. Trusted C++/assembly retain live identities, rights, frames, timers, storage and commit authority. Host decoders reject malformed decisions; they do not replace a refused Aurora decision with success. This single-CPU bootstrap has no stable foreign ABI, general scheduler or concurrency guarantee.

## Interrupt budgets

### API and complete input behavior

`kernel::interrupt_tick(u64 initial, u64 remaining, u64 used)` returns an inline
copied `TickDecision`. The closed `TickAction` is `rejected`, `resume`, or
`exhausted`. Readonly accessors expose copied action/counts. The decision object
contains no authority and does not grant permission to invoke a hardware action.

The input is valid exactly when initial is in 1..128, remaining is in 1..initial,
used is in 0..initial-1, and used equals initial minus remaining. A valid input
consumes exactly one interrupt: used increases by one and remaining decreases
by one. Zero remaining selects exhausted; positive remaining selects resume.
All other u64 triples return rejected with both counts zero, including an already
exhausted state. There is no wrapping, saturating update, exception or partial
state commit.

The ordered initial/range checks precede subtraction. At the conservation check,
initial minus remaining is in 0..127. On the accepted path, remaining minus one
is in 0..127 and used plus one is in 1..128. Thus all arithmetic is representable
for every possible input, including u64 maximum. The source contains no loop or
recursion and introduces no allocation or dynamic state. This local range
argument does not prove compiler correctness or whole-kernel stack safety.

### Disposable transport and independent decoder

The root `aurora_kernel_budget_tick` function converts the copied class/enum result
to a u64 through the existing scalar-symbol bootstrap seam. There is no new Aurora
source ABI. The ordinary Aurora API has no packing method. The private encoding is:

- Bits 0..7: remaining (0..127)
- Bits 8..15: used (1..128)
- Bits 16..17: action (1 = resume; 2 = exhausted)
- Bits 18..63: zero
- Whole word zero: rejection

Each successful state has one unique encoding. Remaining and used also recover
the initial total by addition, so distinct valid triples produce distinct outputs.
Checked shifts by literal 8 and 16 are representable within these ranges.

The C++ `BudgetTransition::decode` accepts no pointers or class records. Before
any state mutation it independently checks the reserved bits, action, count
ranges, conservation against the retained initial budget, strictly decreased
remaining, strictly increased used, and action/remaining consistency. It generates
no next state. It permits an otherwise canonical monotonic jump that spends more
than one interrupt, which cannot extend the run; exact one-tick advancement is the
Aurora policy's semantic obligation, tested separately against an independent
sequence oracle. The decoder does not independently establish validity or
conservation of the prior tuple; the Aurora policy validates that complete input.
It cannot manufacture domain/epoch/frame/ISR authority.

The root example is compiled as one module graph for both BIOS and UEFI, avoiding
duplicate reflection/native helper symbols. Only the UEFI service-budget runtime
calls this transition; the BIOS scheduler is unchanged. There is no stable binary
module boundary or interoperability promise.

### Actual runtime path and trusted authority

The existing timer launch keeps an immutable-by-convention copied initial count.
On each real service/client timer interrupt, the existing run/domain, epoch, root,
frame, PC/selector/flags and hardware ISR checks remain ahead of the policy call.
The timer has been stopped and acknowledged before the pure calculation runs.
The C++ decoder validates the scalar result before updating either live count.
The decoded action then selects the existing rearm or cancellation/restoration
path. A rejected result fails closed with `Aurora budget transition`.

Pending-interrupt drain returns through its existing separate branch before the
policy call. It never charges a budget. Hardware ownership, timer programming,
context preservation, state storage, live grants, mapping retirement, revocation
and cancellation remain trusted C++/assembly. This change moves policy calculation,
not these authorities, into Aurora. The defensive transport can add C++ lines;
there is no claim that total trusted-code line count shrinks.

## Two-client selection

### Total copied API

`kernel::round_robin_next(u64 cursor, u64 eligible_mask)` returns an inline copied
`SelectionDecision`. Readonly accessors return a closed `SelectionAction`, selected
slot and next cursor. Valid cursor values are 0 and 1; valid masks are 0 through 3.
The mask identifies copied eligibility facts, never capabilities or addresses.

- Any invalid input returns `rejected` with selected and next both zero.
- Mask zero returns `idle`, selected zero, and the unchanged input cursor.
- Otherwise choose the first eligible slot beginning at cursor, wrapping once.
  Return `selected`, that slot, and the opposite next cursor.

Both input range checks precede conversion, shift and subtraction. Conversion to
`i64` and shifting by cursor are bounded by 1; `1 - cursor` is in 0..1. There is no
loop, recursion, allocation, reference or arithmetic trap for any u64 input.
With two continuously pending eligible slots, successful selections alternate.
A pending peer cannot be overtaken by a just-completed client's resubmission.
This is fairness among already admitted staged transactions, not elapsed-time
fairness, arbitrary client progress, deadline admission or starvation freedom for
an ineligible or non-cooperative client.

### Private transport and decoding

`aurora_kernel_round_robin_next` in the existing kernel root graph packs a copied
result into the replaceable scalar-symbol bootstrap seam. The ordinary Aurora
API has no packing method or foreign-call declaration. The encoding is:

- Bits 0..7: action 1 idle or 2 selected
- Bits 8..15: selected slot, 0 or 1
- Bit 16: next cursor
- Bits 17..63: zero
- Whole word zero: rejected

There are four distinct successful words: `0x1`, `0x10001`, `0x10002`, `0x102`.
Several valid inputs deliberately share an output. The eight input cases are
covered by a literal independent oracle rather than a rewritten source algorithm.

The C++ `RoundRobinSelection::decode` rejects invalid prior cursor/mask, reserved
bits, unknown action, out-of-range client, an idle result for a nonempty mask,
changed idle cursor, ineligible selected client and an incorrect next cursor.
It does not reproduce the fairness choice. For mask3 it accepts either eligible
client with the correct opposite next cursor; Aurora and the independent oracle
own exact selection semantics. This division is explicit and mutation-tested.

### Authority and commit ordering

The existing phase-inactive, bound, unselected and ready-service checks precede
snapshot preparation. The C++ adapter includes a slot only if it is not disposed,
its mailbox is pending, the actual client incarnation is live, the retained
transaction is nonzero, and the actual service endpoint is authorized. The ready
service precondition also establishes no registry domain is active.

Only cursor and two eligibility bits enter Aurora. A decoded selection cannot
manufacture a grant: the adapter retains the copied real grant and calls the
actual mailbox `receive` using its service handle and retained transaction.
`receive` rechecks phase, pending state, transaction identity, participants and
service ownership. Selected state and cursor commit only after receive succeeds.
Rejected/idle outputs and failed receive never commit either field. The old
orphan behavior remains: a dead pending client is skipped, the live peer can run,
and cancellation of the unconsumable orphan still prevents improper revocation.

C++/assembly retain domain/root/frame/epoch/ISR validation, mailbox/grant lifetime,
transaction state, continuation selection, preemption, timer programming, pending
IRQ drain, cancellation, retirement and hardware authority. This code executes
from the restored supervisor service-selection path, not inside the timer ISR.
No user pointer, raw source pointer, heap, physical device or host boot change is
introduced. No overall trusted-code-size or performance improvement is claimed.

### Stack, ABI and linked-image gate

Source bounds alone do not establish generated stack bounds. Review must measure
the generated policy/wrapper/accessor call chain, include live caller frames and
call pushes, inspect callee-saves and alignment, and check private scalar input
and result registers. Native copy probes and independently authored ABI probes
must run on the pinned compiler. The final UEFI image must remain relocation-free
under existing link/image checks, fit its existing payload and stack limits, and
retain the actual scalar call at the consumer. A compiled function being present
but unused does not satisfy this port.

The output fault reads a local const-volatile high-bit mask and ORs it with the
actual produced scalar. Final linked disassembly must establish that the Aurora
call, volatile load, data-dependent OR and ordinary conditional decoder path all
survive. A constant-folded unconditional fail-stop is insufficient evidence.

## Mailbox transitions

### Public copied API

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

### Private transport and independently checked safety boundary

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

### Host responsibilities and commit ordering

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

### Real consumers and call-context review

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

## Client disposal

### Copied relation

`kernel.client_disposal` accepts phase 0..3 and mailbox state 0..5. Unknown or
full-width out-of-range values return invalid with no effect. Non-inactive
valid phases return refused with no effect. Inactive phase selects:

| Original state | Plan |
| --- | --- |
| idle | empty disposition |
| pending or delivered | cancel, then consume cancellation |
| replied or cancelled | consume the existing terminal result |
| consumed | retain the copied completion receipt |

The private scalar wrapper encodes action in bits 7:0 (0 invalid, 1 refused,
2 accepted) and effect in bits 15:8 (1 empty, 2 retained receipt, 3 cancel/consume,
4 consume terminal). All upper bits and denial effects are zero. The independent
host decoder validates each proposed effect against the original phase/state;
it never generates success when the producer refuses or returns malformed data.
Aurora enum ordinals are not the wire contract; the wrapper maps them explicitly.

### Trusted boundary and ordering

The actual caller phase, quiescence, bound dispatcher, slot, disposed/selected
checks, ready offender/service and exact live owner identity are checked before
the policy call. Domain handles, endpoint grants, generations, transaction
stamps, payloads and receipts never enter the policy. Subsequent receipt/grant/
transaction checks and existing Mailbox operations remain trusted. Those
Mailbox operations retain their own separately checked Aurora transitions.
The adapter still copies/clears the receipt, revokes grants and sets its tombstone
only after the required effects succeed. First terminal outcome is preserved.

A delivered client is normally selected and fails the original pre-policy check;
no authority path is relaxed to exercise the delivered truth-table case.
Quiescence remains an adapter attestation after a verified user exit, never a
fact inferred from user words or from the pure plan.

Producer refusal/malformed output commits nothing. Individual downstream
Mailbox calls retain their established failure semantics: cancellation can
commit before a later consume refusal. Such a composite failure returns no
disposition, does not revoke grants or retire a domain, and does not roll back
previously successful effects. Peer state, grants, transaction, selection and
round-robin cursor remain unchanged. No composite rollback is introduced.

## Terminal classification

### Copied relation

`kernel.terminal_event` receives three u64 words: interrupt vector, a five-bit
matched-site mask (return, bounds, overflow, division-zero, shift-count), and a
canonical 0/1 fact that the stack equals its expected top. Vector >255, mask >31,
multiple matched sites, or a noncanonical boolean refuse. Zero mask refuses.
Vector 129 at the return site and stack top returns `returned`. Vector 6 at
exactly one of the four fault sites returns that fault regardless of stack-top
fact. Every other combination refuses.

The private scalar wrapper explicitly maps nominal enum results to wire words
0 rejected, 1 returned, 2 bounds, 3 overflow, 4 division-zero, 5 shift-count.
No enum ordinal is a wire contract. The independent C++ decoder checks each
positive proposed event against the original copied facts and rejects all
other words, including high bits. It never supplies success for native refusal.

### Trusted boundary

The image/layout validity checks, exact address comparisons, absent-site rules,
frame bounds/alignment, selectors, flags and error word remain C++. Existing
active-run, active-domain/root, role, phase, timer and authenticated continuation
checks remain unchanged in their callers. No address, frame, handle, capability,
image, payload or mutable state crosses into this policy. `ProgramRun` commits
its event/value and clears its active contract only after accepted classification.

The shared classifier is also called by BIOS `IntegerContext::terminal` and
UEFI `ServiceContext::terminal`; these paths must be included in new linked
stack analysis, not just direct `ProgramRun::accept`. Generated Aurora code is
not instrumented by hosted C++ sanitizers.

### Roots and controls

The normal UEFI root, normal BIOS root and BIOS console root export the copied
wrapper. The UEFI console shares that source root but does not execute the
user-runtime classifier. The separate owned-byte root has no dependency.
Previously compiler-free host classifier routes now link genuine generated
code and join the controlled shared-compiler workflow.

BIOS `--program-terminal-input`/`--program-terminal-output` and UEFI
`runtime-terminal-input`/`runtime-terminal-output` alter only a local copied
vector or the real returned word. The invalid vector is UINT64_MAX; the output
control uses a volatile high reserved bit after the genuine call. Decoding uses
original facts. The normal authenticated clean return must fail at the existing
site-authority/fatal boundary with no accepted event or supervisor continuation.
Both new UEFI modes retain the original runtime clock, not timed-service clocks.

No compiler semantics, authority widening, source-language foreign ABI,
performance parity, complete native aggregate, physical-hardware support or
self-hosting is claimed. Selected guest and host qualification is recorded below.

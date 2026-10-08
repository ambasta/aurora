# Copied client-disposal recovery plan

## Dependency and observable gate

This narrow port uses existing copied classes, nominal enums and checked u64
values. `Dispatcher::dispose_client` must obtain an accepted Aurora plan before
any mailbox effect, receipt clearing, grant revocation or disposal commit.
Substituting producer refusal must prevent disposal in the actual adapter.
It is not a full dispatcher/kernel rewrite or a new authority/foreign ABI.

## Copied relation

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

## Trusted boundary and ordering

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

## Integration and qualification

`examples/kernel.au` supplies the private copied scalar wrapper. The separate
BIOS and owned-byte language roots are unchanged. Existing user-run request
fault/budget and completion fault/budget paths call the production recovery
function; completion recovery must retain its original reply value and receipt.

Two additional UEFI modes, `user-disposal-input` and `user-disposal-output`, use
the existing authenticated request-bounds fault path and supervisor restoration.
They change only a local copied phase to UINT64_MAX or the actual returned word
with a volatile high bit. Decode uses the original phase/state. Both must fail
at `user terminal disposition` before a disposition, revocation, retirement or
rebind marker. Their clock is explicitly the existing fixed-zero instruction
clock used for user-run profiles. They do not bypass genuine authority checks.

Required evidence includes an independent finite/full-width policy oracle,
classified decoder and hostile actual-producer controls, existing disposal
models and committed-prefix controls, fatal hosted ASan/UBSan, original-mode
transcript compatibility, and independent source/ABI review. Generated Aurora
code is not instrumented by host C++ sanitizers. Before changed guest execution,
review exact current linked recovery and exception call paths, stack frames,
alignment and fault reserve, plus PIC/PE/image constraints and real call/output
guards. Historical stack receipts are not qualification of this graph.

Run existing user lifecycle, dispatcher, IPC/budget and corrupted-output paths
at the agreed integration scope, restoring actual normal images afterward.
Record exact source/compiler/tool/image identities and retain failed attempts.
Focused success does not imply a fresh complete root native/emulator aggregate,
physical hardware, DMA, self-hosting, production safety or performance parity.

Status: focused native, exact linked admission and actual guest gates passed.
Independent final source/evidence acceptance also passed; publication is separate. See
[focused results](kernel-client-disposal-results.md).

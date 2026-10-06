# Budgets and retirement for controlled user phases

The opt-in user-phase profile arms the admitted local timer for every controlled
client request, service execution and client completion. It contains a verified
client budget failure or exact known compiler trap, disposes only that client's
endpoint/record, retires its address space, and admits a fresh incarnation while
the healthy peer continues. This remains a bounded single-CPU integer-only harness,
not a general scheduler, arbitrary asynchronous IPC, calibrated time or a complete
process model. Unknown or malformed fault origins remain fatal.

## Run authority and interrupt boundary

RunAuthority is an immutable value snapshot, created only for a live active domain
whose role, phase, client index, transaction, owned root and ProgramContract agree
with the three-domain layout. It owns its metadata, not a pointer to caller storage.
Client roles map to domains0/2; service maps to domain1. Request transaction is zero;
service/completion transaction is nonzero. The source-phase scalar is separately
bound launch data and never grants a right by itself. Each run has a nonzero fresh
epoch and a bounded interrupt count. Ordinary phases use at most128 interrupts;
controlled non-yielding phases use3. Neither value is a wall-clock deadline.

Every user timer frame must match the immutable identity, role, phase, client,
transaction, source phase, actual CR3, contract and epoch before resumption. The
existing full fifteen-GPR/IRET frame validation applies to each domain. The client
context fixture loads distinct integer sentinels, sets DF, receives actual timer
interrupts, verifies restored registers/flags, clears DF, and then completes its
compiled request. Extended-state instructions remain unsupported.

All terminal paths restore the owned kernel root and stack, stop timer delivery,
acknowledge actual ISR state, drain pending interrupts under the old ready owner,
and clear the saved run authority before another phase starts. Kernel drain frames
use a separate exact PC/stack/SS=0x10 contract; ready-owner matching cannot authorize
a user frame or supply a kernel continuation. Wrong role/phase/transaction/epoch/root
injections fail closed. The earlier service-only and two-domain profiles remain
separate unchanged behavior profiles and retain their historical gates.

## Client disposal and reply disposition

Dispatcher disposal requires the exact live ready bound offender, inactive kernel
phase, a live ready service and trusted adapter quiescence. Selected offender work
must first be terminal and finish its selection after quiescence. Peer selection,
mailbox, endpoint generation, request transaction and round-robin cursor are not
changed by disposal.

Idle clients have no result. Pending/delivered requests become cancelled; existing
replies remain replied. A completion-stage failure can occur after consumption,
so Dispatcher retains a copied terminal receipt until recycle/disposal/revocation.
This receipt preserves the original transaction, outcome and value. It uses fixed
live storage explicitly zeroed when discarded; optional disengagement alone is not
treated as evidence of byte scrubbing. No committed reply is retroactively changed
into cancellation merely because its client failed to process the completion.

After the offender's grants and copied record are disposed, the adapter requires
its old CR3 to be inactive, retires the registry handle, clears all sixteen root
pool pages, scrubs/releases its four leased stack frames and verifies the kernel
root still owns execution. Only then can it create and bind a fresh incarnation.
The old live identity cannot be rebound, old grants remain invalid, reused stack
frames must be zero, and the peer's grant/transaction must remain exactly unchanged.
PCID/PGE remain disabled and all domain mappings nonglobal; root changes flush the
old translation context before page-table storage is cleared or reused.

The program-visible boundary still carries only fixed copied scalars. Disposal,
root management and the quiescence attestation are temporary trusted C++/assembly
adapter operations, not a user-language unsafe or destruction interface.

## Observable gates

- user-phases: all normal request/service/completion stages receive run authorities
  and timer budgets; distinct replies42/73 and final cleanup still succeed.
- user-context: actual client interrupts preserve all15 GPRs and DF before compiled
  execution completes; this supplements the historical service-context probe.
- user-request-budget / user-completion-budget: independently compiled client loops
  never yield; exactly3 verified interrupts abort the offender, followed by disposal,
  root revocation/scrub/rebind and healthy-peer73 then fresh-client42.
- user-request-bounds / user-completion-bounds and the corresponding overflow modes:
  only the exact retained compiler UD2 is contained, in its validated user context.
- user-retire-pending: a pending interrupt is forced at the completion bounds trap;
  it drains under the old role/phase/incarnation before replied42 disposal and reuse.
- user-pending: pending interrupts at ordinary terminal returns cannot be charged
  to subsequently selected phases.
- user-role / user-phase / user-transaction / user-epoch / user-root: a real offender
  timer frame rejects a mismatched immutable authority or actual root.
- user-unknown: a controlled non-retained UD2 remains fatal; no generic fault
  recovery or safe continuation after an unknown origin is claimed.
- user-stale-grant: a retired client's old grant fails under the fresh incarnation.

Run scripts/kernel-uefi-user-phases-tests.sh (SANITIZE=1 for fatal ASan/UBSan) and
scripts/kernel-uefi-user-phases-all.sh. Exact source manifests, all prior122 modes,
independent review and final receipt validation remain necessary for acceptance.
No device DMA, storage activation or physical-hardware qualification is added.

## Executed candidate evidence

On 2026-10-03, the final 139-mode run passed all 37 BIOS and 102 UEFI modes with
compiler 02771e0d94ad9fe9821041ee10081d31a4f4114dde81b7d476e16cba8d5c75d2.
All 122 preceding gates remain passing. The 202 executable/test/build input hashes
captured before the first build matched after completion, and normal images were
restored. Parent fresh aggregate, sanitizer tools and selected actual BIOS/client-budget/
retirement-drain checks also passed; see the milestone013 verification record.

Independent review passed all 17 new modes on the immutable preceding compiler
a6de1e89e307b076672a1e2ee8a5e848625ac92e386622c1fa5fe7c6ab675026, plus the
new hosted suites. That run is distinguished from the final 139-mode integration
with the new compiler. Hosted checks passed 20,611 immutable-authority cases,
65,536 exhaustive disposal sequences and 4,096 independent 128-operation model
traces under fatal ASan/UBSan. Image tests passed 12 positive/127 negative cases;
receipt tests passed 34 positive/25,222 negative cases under Python optimization.

The clean protected program additionally checks two-byte packed std::array<u8,2>
storage, preserves a neighboring 255 byte while narrowing 42, and widens the result
to i64. Prior nominal-enum, copied class-method result and composition checks are
retained. Its 3,658-byte RX image fits the unchanged 4,096-byte bound.

Initial adapter compilation caught an inconsistent auto declaration and an unused
function warning; the failed build output is preserved separately from successful
gates. Receipt review narrowed the wrong-root injection to client 0 before final
acceptance so an earlier peer interrupt cannot change that negative gate's origin.

## Provisional emulator clock qualification

The 17 user-phase modes are included in the explicit 51-mode UEFI clock candidate.
The original retirement aggregate failed when its finite service exhausted 128
interrupts; a traced success did not resolve that failure. The proposed scheduling
contract preserves budgets 128/3, both context countdowns, compiled service hits,
real old-owner pending drains and every disposal/rebind/cleanup gate. No changed
clock qualification is claimed. See the
[clock contract](../../docs/kernel-emulator-clock-contract.md).

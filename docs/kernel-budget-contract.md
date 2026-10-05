# Aurora-authored interrupt-count transition (verified checkpoint)

This checkpoint moves the UEFI service/client interrupt-budget next state and
resume/exhaust choice into the pure Aurora `kernel.interrupt_budget` policy.
It uses accepted language features without a source pointer, foreign-call API or
new compiler feature. Verification uses the accepted ordinary-function-overload
compiler. Aurora-native kernel, general scheduler, calibrated time and hardware
support remain outside this bounded policy checkpoint.

## API and complete input behavior

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

## Disposable transport and independent decoder

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

## Actual runtime path and trusted authority

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

## Acceptance gates and final result

1. The isolated source/native/focused evidence pins accepted M022 compiler
   `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`. The reconciled
   checkpoint selects the independently passed overload compiler
   `8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631`; the fresh
   combined native and emulator acceptance is recorded below.
2. Native full-width observations for all 8,256 valid source states, small boundary
   violations and adversarial high-bit/maximum triples; invalid inputs must return
   zero normally, never SIGILL. Prove unique successful encodings by enumeration.
3. Exhaust low 18-bit transport encodings and mutate all 64 bits of every valid
   output. Check actual C++ decoding against an independent arithmetic/set oracle.
4. Independent source/native/transport/kernel review before new QEMU modes.
5. Existing service-budget, dispatcher and client-budget QEMU modes must preserve
   strict tick, exhaustion, context, pending-drain and recovery receipts. Added
   malformed-input/output modes must fail-stop before count commit, resume or
   cancellation. Preserve source, binaries, actual logs and failure results.
6. Fresh full `make test`, all 166 baseline QEMU modes plus added modes, and actual
   normal BIOS and UEFI restoration boots. Archive exact source/tool identities,
   resource bounds, observations and independent review before final acceptance.

These gates passed in a fresh isolated run on 2026-10-05: a rebuilt exact compiler,
complete native `make test`, all 170 distinct modes, and two additional actual
normal BIOS/UEFI boots. Independent native and emulator terminal audits verified
the complete input closure, raw observations, immutable seals, original-build
preservation and closed owned-process leases. The four policy modes all produced
the required exit35; the output-fault mode also matched all five independently
reviewed linked-image members before QEMU. See the
[exact evidence index](evidence/kernel-budget-policy/README.md).

The initial full-170 attempt remains failed, and its continuation remains
interrupted/unclosed. Neither supplies mode credit to the successful fresh run.
All emulator work used regular disposable images, with no physical hardware,
device activation, host bootloader modification or unreviewed firmware adoption.

## Fault-mode and native evidence

The historical pre-QEMU source/native boundary passed independent review on the
frozen 527-file candidate. Author native observations cover 104,120 policy cases and
815,301 decoder cases plus ten diagnostic/output-preservation rejections. An
independent probe covers 3,844,874 policy/ABI calls and 177,745,472 decoder cases,
repeated under fatal C++ UBSan; these overlapping counts are not additive. The
review measured a 320-byte generated call-chain contribution, preserved callee
saves/alignment and no native-object relocations. The later 533-file reconciled
freeze passed fresh full native and actual emulator acceptance. Its final review
also replayed stack checks and verified the actual linked output-fault image.
Historical and fresh counts overlap and are not additive.

Four additional QEMU modes inject only trusted local snapshots after the existing
real frame/ISR checks. They do not alter live domain/frame/epoch authority:

- `budget-policy-zero`: zero initial count must return rejected.
- `budget-policy-counts`: first-tick used=1 conflicts with full remaining count.
- `budget-policy-wide`: maximum-u64 remaining/used must reject normally.
- `budget-policy-output`: a reserved high bit in the produced word must fail decode.

Each requires exit35, an exact real user-timer frame and the sole transition
failure, with no charged tick, rearm, cancellation, completion or success marker.
The service-budget gate now configures nineteen modes, bringing the full suite to
170 modes. All 170 passed in the fresh run, followed by two additional normal
restoration boots. The final policy-mode results are actual QEMU observations.

## Source-only reconciliation on the passed overload checkpoint

The kernel delta was reconciled in a separate tree onto exactly the 527 source
files in overload final manifest
`4e2d69937a761ffc773e668bcb0ed0b85f8dc38847bbd4ba802a82f0ee5a4156`.
This did not copy build outputs or replace overlapping compiler changes. Fresh
same-root compiler, full native and full-170+2 acceptance subsequently completed
on the reconciled source. Publication remains a separate action.

The qualified clean-firmware CODE pin
`24b30416142749dd60ac241fe755df6232fc5b10663a8b799501659b796d0268` is
already present in that exact source and is preserved unchanged. The earlier
M022 source/focused evidence remains frozen in its original archive.

The final output-fault injection now reads a local const-volatile u64 mask before
OR-ing the high bit into the actual Aurora result. It is entirely inside the
test-only macro and adds no persistent state, privilege or production behavior.
Independent isolated probes retain a stack load, data-dependent OR, conditional
ordinary decoding and the accepted path. The final fresh run checked the exact
reviewed linked-image members before QEMU, passed the actual output-fault mode,
and completed both normal restoration boots; independent review replayed the
stack and image checks. The old focused output-fault rejection was constant-folded;
its result remains historical and is not relabeled as dynamic decoder coverage.

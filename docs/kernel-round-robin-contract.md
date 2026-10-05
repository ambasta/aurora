# Aurora two-slot round-robin policy (candidate)

This candidate moves the actual `Dispatcher::select` next-client choice from C++
into `kernel.round_robin`. Its existing consumers are the bounded UEFI service
dispatcher and interrupt-budgeted client recovery profiles. It uses accepted
language features; no compiler change or pending readonly-window feature is
required. The BIOS three-task scheduler is unchanged. This is a two-slot policy
port, not a general scheduler, Aurora-native kernel, SMP or physical-device claim.

## Dependency and observable gate stated before implementation

The baseline is accepted PR22 main `3d85ef4ec24fa7f879106f1803df0931d9b386f4`,
535 source files, source manifest
`fe069ac102d9393a6266761356fa24913aa55b8dcfbc5fd133026a82737d2394`.
Initial native tests must use accepted compiler
`8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631`.
The independent read-only-window compiler lane may become the final integration
baseline only after its own acceptance; no divergent main or copied build output
is used to claim combined verification.

Before implementation, the selected consumer, copied contract, hardware boundary,
stack/ABI review and actual-QEMU gates were recorded. Source preparation and the
first native lane have a 128 MiB candidate allocation cap and 1 GiB free floor.
Heavy native or emulator stages require separately admitted bounded plans and
must not overlap the compiler integration lane. Failed outputs are retained.

## Total copied API

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

## Private transport and decoding

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

## Authority and commit ordering

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

## Stack, ABI and linked-image gate

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

## Acceptance gates, not yet acceptance results

1. All eight valid source inputs; hostile full-width boundary/high-bit/random
   inputs; invalid source inputs reject normally, without SIGILL.
2. Decoder enumeration, all 64 output-bit mutations, independent literal-set
   expectations, copied class-result probes, negative diagnostics and output
   preservation. A substituted-producer test uses the actual Dispatcher and
   checks that rejected outputs preserve every dispatcher object byte.
3. Existing dispatcher and client-disposal models linked to the real Aurora
   object, continuous two-pending fairness, idle cursor0/cursor1 preservation,
   dead-client skipping, exact copies, stale identities and cancellation recovery.
   Repeat relevant hosted C++ code with fatal ASan/UBSan.
4. Independent source, native oracle, copy, IR-boundary, stack/ABI and linked
   fault-image review before emulator admission.
5. Actual existing twelve dispatcher modes and seventeen user-phase modes.
   Three new dispatcher modes change local copied cursor, mask or a reserved bit
   of actual output. Each must exit35 after both real clients submit, before any
   selection commit, service launch/timer, completion or success marker.
   Normal selection order remains0,1,0, with real frames and quiescence validated.
6. Fresh full `make test`, all170 baseline emulator modes plus the three new
   modes, the three separately counted BIOS capacity probes, then actual normal
   BIOS and UEFI restoration boots on the final source.
   Preserve failed attempts, exact input/tool pins, complete raw observations,
   terminal quiescence and independent reviews before publication/acceptance.

Source preparation alone does not satisfy native or emulator gates. This document
will record exact accepted evidence only when those stages actually complete.


## Preserved initial native failure

The initial author-native stage stopped at its copied-result test because that
fixture used unsupported logical-OR syntax. The production policy had already
matched17,672 full-width inputs, the decoder matched1,051,016 vectors, and10
negative/output-preservation checks passed. These are partial observations, not
stage or kernel acceptance. The entire failed candidate, raw vectors and failed
compiler diagnostic are retained with a verified terminal seal and closed owned
process lease. The replay only splits the copy fixture into supported individual
if statements; it adds no compiler feature. All required gates must run again on
the corrected freeze; no failed-run prefix earns acceptance credit.


## Earlier reconciliation on accepted readonly-window compiler

An earlier final-integration candidate adopted the independently accepted543-file
readonly-window source checkpoint with manifest
`885612126e53d92010fb1f65289de75824c41c0580327e123824157e7f4d17ce`.
Its compiler was
`b3c8d58565844e1b671d1589975985374b17387b405543e05762631b95552580`.
The25-path kernel delta was reconciled by exact baseline comparison and clean
three-way documentation merges. Compiler, library and storage inputs were
unchanged from that accepted checkpoint. No build outputs were copied.

Earlier native evidence on the accepted8d compiler comprises a clean15-command
author replay and explicitly composed17 independent commands plus3 IR-recovery
commands. The original independent stage remains failed: its host-only -O0 IR
scanner hit a32MiB file-size limit. A separately admitted -O1 scanner passed the
same layout and five malformed-IR controls and produced byte-identical assembly.
The generated policy chain uses304 bytes including its initial return address;
this is not a whole-kernel stack-margin result. All original failures are retained.

Those historical native results do not qualify this newly combined source. A
fresh rebuilt compiler, focused native/ABI/IR and final linked fault-image review,
full native aggregate, all173 unique emulator modes and2 actual normal restoration
boots are required. Both existing budget-policy-output and new
dispatch-policy-output image proofs must be requalified on the changed root graph.

## Preserved full-aggregate BIOS graph failure

The first combined full aggregate failed its real BIOS image-size gate. The
BIOS build imported the full UEFI policy root despite calling only
`aurora_kernel_value`. The unused new selection graph added 1,379 bytes to text,
crossing a 4 KiB alignment boundary. The image grew from 45,808 to 49,904 bytes,
exceeding the fixed 96-sector (49,152-byte) payload budget by 752 bytes. Its failure
and all 14,760 generated records remain sealed; later aggregate recipes did not run.

The intermediate replay used `examples/kernel-bios.au` solely for the BIOS build. It preserved
the existing value/ownership probe byte-for-byte and imports neither UEFI policy.
The UEFI root, policy implementations, compiler, BIOS loader and linker limits
were unchanged. The image gate checks exact probe-source equality, the actual
Aurora object entry set, and absence of both policy graphs in the object and final
ELF; 27 negative controls cover source drift and accidental graph relinking. The
final ELF's existing C++ `aurora_kernel_main` entry remains allowed. This correction
requires a new source freeze and fresh native/image/emulator acceptance; it does
not turn the preserved failed aggregate into a pass.

That replay also incorporated the separately reviewed seven-path BIOS
host-toolchain portability correction. Its explicit boot-sector linker contract,
production helper and layout regressions are preserved unchanged. This fixes
host-generated metadata entering the boot sector; it is independent of removing
unused policies from the kernel payload. The standalone portability results in
the kernel instructions describe that checkpoint's original root. Fresh combined
focused builds, full aggregate and all 173 emulator modes plus two restoration
boots remained required for that replay.

## Final combined source, acceptance pending

The final source incorporates the separately reviewed eight-path 127-sector
transport correction on PR25, preserving its explicit 65,024-byte limit and
stricter ELF/raw-image and transfer-padding checks. The BIOS-only root checks
remain separate and intact. It also includes the twelve-path exact-bool
short-circuit compiler candidate, whose expected fresh release compiler hash is
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
The earlier unsupported-logical-OR fixture failure is historical evidence on the
older compiler, not a current language restriction.

The earlier 560-file source passed all 44 focused commands and independent
terminal/linked-image review. That evidence remains an intermediate checkpoint;
it does not accept this changed compiler/source graph. The final focused plan
adds ordinary and optimized boot-layout/capacity tests immediately after the BIOS
build. A fresh compiler pin, native/ABI/IR checks, both linked output-fault proofs
and caller-stack review must be established on the final graph. Complete native
`make test` and actual 173 production modes, three capacity probes and two normal
restoration boots remain required. All prior failed stages stay failed and
preserved. None of these gates establishes physical AMD qualification or a
general Aurora scheduler/kernel.

Acceptance commands explicitly supply the reviewed `66bb719d...` compiler pin
to every relevant native gate. Existing older reference-hash defaults are
retained rather than silently replaced or bypassed with self-derived hashes.
This leaves a known public `make test` portability gap across legitimate host
GCC builds. A separate supported developer-test workflow is required after the
combined checkpoint, while release/acceptance receipt validation keeps external
reference pins. A configured acceptance pass must not be presented as solving
that workflow gap.

## Preserved aggregate configuration block

The combined 565-file source passed all 45 focused commands and independent
linked/stack qualification. Before its full aggregate child was launched, a
separate read-only audit caught an inconsistent storage configuration: Make and
the admitted command selected 1024 MiB, but three package harnesses still rejected
values above 512 MiB. The issued admission and successful identity preflight are
preserved as blocked-before-execution evidence; no full aggregate result exists
for that attempt.

The cap-consistent replay changes test harnesses only. All five actual consumers
now require integer caps within their existing focused minimum and 1024 MiB;
focused defaults remain 128 or 256 MiB. Compiler/source pins, behavioral cases,
per-process address-space and file/source bounds, reserves and free-space floors
remain unchanged. Selected caps are recorded in native summaries. The explicit
`--check-cap-only` path produces configuration-only output, never a native PASS
receipt, and does not read or run a compiler or change requested output files.
`make test-native-cap-contracts` checks the real five entrypoints in ordinary and
optimized Python and mocks allocation/reserve/floor boundaries without large
allocations. This configuration gate cannot replace any native behavioral gate.
The final source still requires fresh reviewed aggregate and emulator acceptance.

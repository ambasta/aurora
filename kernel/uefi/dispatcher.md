# Bounded staged service dispatcher

This bootstrap runs two compiled clients and one compiled service in three private
UEFI address spaces. The kernel copies fixed scalar requests and replies and
selects the service's next mailbox. Client A expects 42; client B expects 73.
A completed client can submit again, but cannot overtake its already waiting peer.
The scope remains finite cooperative client stages plus interrupt-budgeted service
runs. It is not a general scheduler, arbitrary suspended-call IPC, storage driver,
DMA authority, or physical Framework qualification.

## Ownership and layout

The default RuntimeLayoutProfile<2> retains its prior exact mappings. The explicit
trusted dispatcher profile selects RuntimeLayoutProfile<3>. In the existing owned
1 MiB arena, the third root pool occupies offsets 0xd0000..0xe0000 and the third
RX image occupies 0xb2000..0xb3000. The existing 16-frame pool at 0xc0000..0xd0000
supplies twelve leased user-stack frames. Each root pool remains sixteen pages.
No allocation or image budget is expanded. Both profiles check all intervals,
canonical addresses, guards, disjointness and capacity before mapping.

The third user code page is at 0x10000002000; its guarded four-page stack is at
0x10000600000..0x10000604000. Each domain maps only its own user image and stack.
All privileged mappings are identical, supervisor-only, and checked against the
profile's exact leaf oracle. User image backing has no writable alias. Firmware
and ECAM windows remain absent from user roots. The admitted supervisor UC APIC
mapping is unchanged. CR3 restoration, guarded RSP0/IST, fifteen saved integer
registers, integer-only execution and strict kernel SS restoration retain the
service-budget contract.

## Transaction and scheduling contract

Dispatcher owns two Mailboxes and a bounded round-robin cursor. There is at most
one outstanding request per client and one selected service transaction. Actual
live DomainHandle identity resolves the submitting client; endpoint words do not
choose a mailbox. Even a valid service grant for the other client cannot redirect
a reply: reply is confined to the kernel-selected mailbox and transaction.
Work contains copied request words, with no shared pointer or caller memory.

The kernel selects each request/service/completion phase. Validated CPL3 entry,
actual CR3, exact return/trap PC, stack/frame bounds and the current domain handle
precede policy calls. Client completion receives a copied result and a kernel-held
transaction identity after consumption has erased the mailbox record. No source
language syscall, pointer or general unsafe escape was introduced.

Selection survives a terminal reply until the adapter establishes the kernel root,
interrupts disabled, stopped timer, no ISR/IRR work, cleared saved continuation and
completed pending-interrupt drain. Every service run has a fresh timer epoch;
interrupts count against that run, never a subsequently selected transaction.
Budgets count verified interrupts, not elapsed time. Arbitrary non-yielding client
code is not preempted by this profile; the fairness claim applies only to these
bounded cooperative client phases.

Service fault or budget exhaustion cancels only pending/delivered transactions.
A replied transaction remains replied, including when the other selected request
fails. Clients consume the appropriate reply or cancellation, grants are revoked,
and only then is the service retired, scrubbed and recreated. Clients explicitly
submit new requests under fresh grants after restart. Global generation allocation
fails closed on exhaustion and cannot be reset by rebind or object reconstruction.
A client destroyed before consuming its cancellation leaves an orphan that blocks
revocation; no orphan-discard or general process lifecycle is claimed.

## Acceptance gates

- dispatch: two replies with selection order 0,1,0 despite client0 resubmission.
- dispatch-budget and dispatch-fault: actual compiled non-yielding loop or exact
  bounds UD2 cancels both affected transactions, then fresh service replies succeed.
- dispatch-mixed: committed client0 reply survives cancellation of client1 after
  its service budget expires; both observe their distinct outcomes before restart.
- dispatch-pending: real pending APIC delivery drains under the old run before the
  next selected transaction; strict saved SS=0x10 remains mandatory.
- dispatch-cross-reply, dispatch-client-owner and dispatch-stale: valid foreign
  mailbox rights, wrong actual client and retired grants respectively fail closed.
- dispatch-duplicate: second request from a client already pending, before its
  peer submits, is denied. dispatch-full repeats admission with both slots occupied.
  Neither mode claims a third client exists; hosted tests check unchanged records.
- dispatch-root: an actual timer under the wrong CR3 is rejected.
- dispatch-peer-code: the third client actually faults reading another client's
  absent user code mapping, at the exact controlled probe site.

Every mode boots the one `dispatch-fixture` image and picks its case from the
serial selector; `dispatch` is the baseline selector, which runs the ordinary flow. dispatch-peer-code used to have its own image whose
third client always ran the read. The fixture's third client now carries the
shared selectable probe set (see [service-budget.md](service-budget.md)), and the
launcher selects the peer-code probe for that client only when the mode asks.

Run `meson test -C build/meson --suite full` for layout, policy, image and transcript
checks (SANITIZE=1 enables fatal ASan/UBSan), and
`meson test -C build/meson --suite guest-dispatch` for the twelve actual OVMF modes. Existing
kernel-uefi-smoke.sh restores a normal image after every non-normal mode.

The strict transcript gate checks the complete ordered transaction trace against
an independent expected sequence, and separately validates each timer frame,
accounting record, terminal transition, kernel restoration and drain. It rejects
missing, duplicate, reordered and altered records and malformed image metadata.
Image validation retains exact RX bounds and PIC relocation checks. Source and
receipt manifests, independent review and historical gates are required separately
before accepting a milestone.

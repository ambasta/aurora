# Sealed synchronous services

This is a bounded bootstrap service mode,
not general references, source FFI, arbitrary host imports or a process API.

```cpp
auto write_byte(builtin::ConsoleSession& session, u8 byte) -> builtin::ConsolePutResult {
    return session.put(byte);
}
auto receive(builtin::ConsoleSession& session) -> builtin::ConsoleSample {
    const builtin::ConsoleSample sample = session.next();
    return sample;
}
```

## Source and lifetime

`ConsoleSession`, `DisplaySession` and `IommuEventSession` are distinct
compiler-owned sealed service kinds. An explicit contiguous leading group of one or two exclusive service
reference free-function formals is accepted. The explicit group allowlist is Console, Display or Event alone, Console+Display
in either order, and Event+Console in either order. Event+Display, duplicate kinds
and all triples are rejected. There is no
by-value or const variant. It cannot be constructed, copied, moved, assigned, stored in a
local/field/array, returned, reflected or converted. A reference is a parameter
mode, never an ordinary reference value. Service methods, constructors, templates,
overloads, mixed regions/owners and recursion in the reachable service graph are
rejected. Later parameters are copied scalars/enums, ordinary non-owning copied
classes or readonly byte spans, with the existing source-root lifetime and loan
checks. Copied inputs use independent readonly argument snapshots under the same
nominal, complete-initialization and bounded-layout rules as ordinary copied calls.
Owners, authority-bearing fields and escaping views remain excluded. The existing
six-formal limit includes the leading service group. Helper results are scalars/enums
or ordinary non-owning classes under the [copied-value boundary rules](VALUES.md).
Copied service results still require an explicitly typed local before being
passed into another call; direct service-result argument expressions are unchanged.
Exact nominal type, layout, private visibility and complete initialization apply.
No result carries a capability, owner, span or escaping reference. Copied data,
including ConsoleSample and IommuEventSample, is independent of service kind.
Native operations retain exact canonical report types; Display has no host input
or copied class-report operation. Duplicate kinds, non-leading capabilities and
forwarding one kind into a formal of the other kind are rejected. No owner/region
mixture is added.

Named forwarding acquires one independent synchronous child loan for each
forwarded capability before evaluating later value/span arguments, suspending
those parent roots. Each parent resumes only after its matching call and release.
A helper may forward either singleton subset or the pair in either formal order.
An unrelated, unforwarded capability remains usable and may be independently
forwarded while another root is suspended. This deliberately rejects `helper(session, session.put(byte))`.
A caller without its own service parameter cannot supply authority. Ordinary copied
result enums remain data and can cross helpers/modules independently of authority.

The closed compiler operation table in `services.hpp` owns host linkage:

- `next()` returns `ConsoleSample`: public `byte_present: bool`, `byte: u8`,
  `damaged: bool`. Absent byte is canonical zero. The sample is an ordinary copied
  observation, never an authority token. Named-field construction, ordinary
  copies, class storage/return and module-visible reflection preserve that data
  distinction. Direct builtin-report template arguments are outside this bounded
  increment. Production transport waits until a byte
  or damage is observed.
- `put(u8)` returns `ConsolePutResult::success` or `::timeout`. Partial output is
  neither rolled back nor silently retried.
- The Console entry returns `ConsoleCompletion::requested_exit` or `::output_failure`.
- `DisplaySession.pixel(u64 x, u64 y, u8 red, u8 green, u8 blue)` returns
  `DisplayPutResult::success` (0) or `::out_of_bounds` (1).
- The Display entry returns `DisplayCompletion::rendered` (0) or `::output_failure`
  (1). Width and height are copied `u64` entry arguments. The trusted host validates
  them against its live grant; Aurora receives no framebuffer address or mapping.
  Invalid/stale/reentrant grants or malformed raw channels fail before any store;
  valid out-of-range coordinates return 1 with zero writes. Native transport owns
  completion ordering. This compiler contract does not qualify a display driver.

## Bounded IOMMU event observation

`IommuEventSession.poll()` is a nonblocking, argument-free operation returning
`builtin::IommuEventSample`. Its public fields, in exact order, are
`result: builtin::EventPollResult`, `word0: u64`, `word1: u64`, and
`status_low: u64`. The closed poll results are `empty` (0), `record` (1),
`overflow` (2), and `transport_failure` (3). The copied report occupies exactly
four qwords. Host-produced non-record reports require both record words to be
zero; `status_low` is limited to `0x1f`. The trusted transport separately validates
its full raw hardware status before masking. A copied report can be constructed,
copied, stored, returned through ordinary helpers, and reflected as data. Those
operations never construct authority or redirect acknowledgement.

`IommuEventSession.acknowledge()` takes no source arguments and returns the closed
`builtin::EventAckResult`: `committed` (0), `overflow` (1), or
`transport_failure` (2). It carries no caller-selected address, sequence, record
or offset. The trusted adapter must require its one internally pending copied
record, permit at most one head-write attempt, and retain an absorbing failure
state after uncertainty. The compiler capability itself does not enforce printing
before acknowledgement; that is an audited property of the bounded consumer.

The copied `builtin::EventIntakeCompletion` cases are `drained` (0),
`budget_exhausted` (1), `loss_detected` (2), `unsupported_event` (3),
`command_error` (4), `transport_failure` (5), and `output_failure` (6). No result
carries completion, reclamation, publication or restart authority. Ordinary
methods consume copied observations; no mixed object/service borrowing is added.

## Typed IR and private native boundary

`BindServiceParameter` is the sole provenance root. Its distinct bindings must
form the leading entry parameter group in exact source order, each with its own
kind, source-position identity and disjoint spill. `AcquireServiceLoan`, `ServiceCall` and
`ReleaseServiceLoan` record exclusive forwarding explicitly. `ServiceOperation`
selects a closed operation identity. Binding, active identity, loan, helper call,
release and operation all carry/check exact kind; a generic service predicate
cannot authorize a different kind. A service spill is a private sixteen-byte
opaque grant/generation pair, disjoint from scalar, object, array, span and owner
storage. Ordinary loads/stores, aggregate/resource calls and metadata cannot mint
service authority. Join/backedge loan states agree exactly; returns have no child
loan. The independent verifier rejects unknown kinds/operations, simultaneous
reuse of a live loan ID, IDs reused for a different static root/kind, ordinary-call
bypass and recursive reachable call cycles. After release, the same ID may name
the same root/kind again. Source admission checks static declarations and ID
consistency before native live-state verification; it does not require textual
acquisition order. This migration remains source-only pending execution qualification.

The existing private packed argument convention remains: R11 holds a borrowed
argument record; R10 holds a copied result address when needed. Service authority
occupies sixteen record bytes per formal, in source order. The complete opaque
grant/generation pair follows its argument even when helper formal order differs
from the caller. A `(Console&, Display&, u64 width, u64 height)` record therefore
has Console grant/generation at +0/+8, Display at +16/+24, width at +32 and height
at +40; a reversed signature places Display first. There is no ambient combined
grant. The six-formal source limit remains unchanged. Existing non-service parameter modes,
stack alignment, probes, saved-register rules and stack budgets are unchanged.
Compiler-generated host operations validate full-width booleans, the raw byte
range, absent-byte zero and closed status values before exposing source values.
Canonical report layout/enum cardinality is checked independently in typed IR.
Ordinary class-returning `ServiceCall` reuses the hidden R10 destination and full
nominal copied layout, with exact active, pristine, disjoint result storage.
`ReturnObject` requires complete results, including nested/empty completion;
repeated empty initialization also rejects. Library `console::WriteResult` carries
only copied count/status data, retaining no service loan or byte-span argument.

`ServiceCall` records copied input offsets separately from span offsets. Every
copied argument is an exact, live, readonly, nominally typed and fully initialized
snapshot; snapshots are distinct and cannot alias a copied result. Capability,
scalar and span positions cannot name object storage. Existing copied-value
packing and `BindObjectParameter` move the canonical physical value without
copying service authority. A Console grant plus an 80-byte copied record has a
predicted 96-byte private argument record. Generic ABI metadata describes copied
parameters; the narrower scalar-only `service_record` facts remain unchanged.
This copied-input extension and its protected-console consumer are source-only
candidates until generated ABI and execution qualification.

The Display entry record is exactly grant at +0, generation at +8, width at +16,
height at +24. `__au_runtime_display_pixel` receives seven full SysV qwords:
RDI grant, RSI generation, RDX x, RCX y, R8 red, R9 green, and blue at 8(RSP) on
host entry. The emitter reserves outgoing stack storage with correct alignment
for both even and odd surrounding evaluation depth, then validates RAX <= 1.
No general foreign-call syntax or new authority representation is introduced.

The Event host symbols are closed compiler choices:
`__au_runtime_iommu_event_poll` receives RDI grant, RSI generation, and RDX a
private 32-byte output address. Generated code clears all four output qwords,
then validates the full-width result and status plus absent-record zero words
before exposing the object. `__au_runtime_iommu_event_acknowledge` receives RDI
grant and RSI generation and returns RAX in 0..2. Every operation dispatch is
explicit; unknown operations cannot fall through to Console `next`.

An `(Event&, Console&, u64 poll_budget, u64 record_budget)` private R11 record has
Event grant/generation at +0/+8, Console at +16/+24, and budgets at +32/+40.
Reversed helpers forward both complete pairs in target order. Copied helper
results use the existing hidden R10 destination, independently of formal order.
The trusted entry bridge must atomically admit both exact grants, validate budgets
(0..256 polls and 0..255 records), and validate the closed completion result in
0..6. The compiler preserves opaque authority; it does not perform native grant
admission, interpret hardware status, or qualify an IOMMU device.

Service graphs require private source-symbol linkage. That requirement is
separate from owned-byte runtime linkage, so a console graph does not acquire an
allocator dependency. Only the trusted assembly entry bridge can enter the
compiler-private service graph. Generated source cannot select a host symbol,
callback, port, pointer, syscall or device address.

## Verification

Source/editor/host-report cases live in `tests/compiler/console_service.py`,
including copied service inputs/results and `console::write` success/timeout prefixes.
Independently constructed hostile IR lives in `console_service_ir.cpp`. Acceptance
requires the applicable gates on final integrated source; host-grant and UART
tests remain separate from generated-code tests.
`display_service.py`, `display_service_ir.cpp` and the handwritten
`display_service_abi.S` add second-kind source, cross-module copied reflection,
forged-kind/slot/operation/loan and seven-argument ABI coverage, while retaining
Console regression. The Display gates are in Meson dev/slow and the compiler
native test graph. Native Display grant/transport and guest qualification remain
separate from these compiler tests. See the
[kernel migration contract](../docs/native-console-service.md) for required
linked-stack, image, emulator, restoration and final developer gates. Qualification must match the exact final source and built images.

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

`ConsoleSession` and `DisplaySession` are distinct compiler-owned sealed service
kinds. Only one leading exclusive service reference free-function formal is accepted. There is no by-value
or const variant. It cannot be constructed, copied, moved, assigned, stored in a
local/field/array, returned, reflected or converted. A reference is a parameter
mode, never an ordinary reference value. Service methods, constructors, templates,
overloads, mixed regions/owners and recursion in the reachable service graph are
rejected. Later parameters are copied scalars/enums or readonly byte spans, with
the existing source-root lifetime and loan checks. Console additionally permits
its approved copied sample result. Display has no host input or copied class-report
operation. Mixing capabilities of either kind,
including forwarding one kind to a helper of the other, is rejected.

Named forwarding acquires one synchronous child loan before evaluating later
arguments, suspending parent use. The parent resumes only after the matching
call and release. This deliberately rejects `helper(session, session.put(byte))`.
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

## Typed IR and private native boundary

`BindServiceParameter` is the sole provenance root and must uniquely begin the
entry parameter prefix. `AcquireServiceLoan`, `ServiceCall` and
`ReleaseServiceLoan` record exclusive forwarding explicitly. `ServiceOperation`
selects a closed operation identity. Binding, active identity, loan, helper call,
release and operation all carry/check exact kind; a generic service predicate
cannot authorize a different kind. A service spill is a private sixteen-byte
opaque grant/generation pair, disjoint from scalar, object, array, span and owner
storage. Ordinary loads/stores, aggregate/resource calls and metadata cannot mint
service authority. Join/backedge loan states agree exactly; returns have no child
loan. The independent verifier rejects unknown kinds/operations, duplicate or
reused loans, ordinary-call bypass and recursive reachable call cycles.

The existing private packed argument convention remains: R11 holds a borrowed
argument record; R10 holds a copied result address when needed. Service authority
occupies the first sixteen record bytes. Existing non-service parameter modes,
stack alignment, probes, saved-register rules and stack budgets are unchanged.
Compiler-generated host operations validate full-width booleans, the raw byte
range, absent-byte zero and closed status values before exposing source values.
Canonical report layout/enum cardinality is checked independently in typed IR.

The Display entry record is exactly grant at +0, generation at +8, width at +16,
height at +24. `__au_runtime_display_pixel` receives seven full SysV qwords:
RDI grant, RSI generation, RDX x, RCX y, R8 red, R9 green, and blue at 8(RSP) on
host entry. The emitter reserves outgoing stack storage with correct alignment
for both even and odd surrounding evaluation depth, then validates RAX <= 1.
No general foreign-call syntax or new authority representation is introduced.

Service graphs require private source-symbol linkage. That requirement is
separate from owned-byte runtime linkage, so a console graph does not acquire an
allocator dependency. Only the trusted assembly entry bridge can enter the
compiler-private service graph. Generated source cannot select a host symbol,
callback, port, pointer, syscall or device address.

## Verification

Source/editor/host-report cases live in `tests/compiler/console_service.py`;
independently constructed hostile IR lives in `console_service_ir.cpp`. The
host-grant and UART tests are separate from generated-code tests.
`display_service.py`, `display_service_ir.cpp` and the handwritten
`display_service_abi.S` add second-kind source, cross-module copied reflection,
forged-kind/slot/operation/loan and seven-argument ABI coverage, while retaining
Console regression. The Display gates are in Meson dev/slow and the compiler
native test graph. Native Display grant/transport and guest qualification remain
separate from these compiler tests. See the
[kernel migration contract](../docs/native-console-service.md) for required
linked-stack, image, emulator, restoration and final developer gates. No gate is
claimed passed until its exact final source and receipts are recorded there.

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
kinds. An explicit contiguous leading group of one or two exclusive service
reference free-function formals is accepted. A pair must contain distinct kinds;
both Console-then-Display and Display-then-Console are supported. There is no
by-value or const variant. It cannot be constructed, copied, moved, assigned, stored in a
local/field/array, returned, reflected or converted. A reference is a parameter
mode, never an ordinary reference value. Service methods, constructors, templates,
overloads, mixed regions/owners and recursion in the reachable service graph are
rejected. Later parameters are copied scalars/enums or readonly byte spans, with
the existing source-root lifetime and loan checks. A group containing Console additionally permits its approved copied sample
result, regardless of formal order. Display has no host input or copied class-report
operation. Duplicate kinds, non-leading capabilities, and forwarding one kind into
a formal of the other kind are rejected. No owner/region mixture is added.

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
loan. The independent verifier rejects unknown kinds/operations, duplicate or
reused loans, loan IDs reused for a different static root/kind, ordinary-call bypass and recursive reachable call cycles.

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

## Distinct-group checkpoint status

The new leading-group implementation and tests are an **unqualified source
checkpoint** with focused checks only: the release compiler build, 146 cumulative
Console/Display/group hostile-IR checks, the existing Console source/editor gate,
and Display plus group source/private-ABI gates passed. These results are not
final integrated dev/slow/full Make acceptance or a proof of soundness; see the
[focused checkpoint record](../docs/distinct-service-groups.md). `service_group.au` is a small
sample-to-pixel private-ABI consumer, not the finished graphical editor. Its
reversed six-formal helper exercises copied samples, readonly spans, singleton
subsets, independent suspension and distinct host generations. `service_group.py`
adds source rejection controls to the existing Display source runner;
`service_group_ir.cpp` includes the full previous Console/Display hostile-IR suites
and group-specific controls, under the existing Make and Meson display gates.

The compiler preserves and forwards opaque authority; it does not authenticate a
combined native entry. Native code must independently authenticate both exact
kinds/grants/generations before running a graphical consumer, including stale,
crossed and partially valid no-write entry controls. No mixed timer/framebuffer
mapping, atomic combined grant admission, native stack budget or guest behavior is
qualified by this compiler-only increment.

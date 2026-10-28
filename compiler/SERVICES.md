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

`ConsoleSession`, `DisplaySession`, `IommuEventSession`, `CallSession`, `Com1UartGrant`, `ServeSession` and
`HostFiles` ([below](#hosted-files)) are distinct compiler-owned sealed service kinds. An explicit contiguous leading group of one or two exclusive service
reference free-function formals is accepted. The explicit group allowlist is Console, Display, Event, Call, Port, Serve or HostFiles alone, Console+Display
in either order, and Event+Console in either order. Call, Port, Serve and HostFiles cannot mix with any other kind. Event+Display, duplicate kinds
and all triples are rejected. There is no
by-value or const variant. It cannot be constructed, copied, moved, assigned, stored in a
local/field/array, returned, reflected or converted. A reference is a parameter
mode, never an ordinary reference value. Service methods, constructors, templates,
overloads, owner parameters and recursion in the reachable service graph are
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
forwarding one kind into a formal of the other kind are rejected.

Two mixed capability prefixes are accepted: `builtin::ConsoleSession& session,
builtin::ByteRegion region` and `builtin::HostFiles& files, builtin::ByteRegion
region`, followed by the same copied values or readonly byte spans. The order and
kinds are exact; other services, service pairs, repeated or misplaced regions and
owner parameters/results remain rejected. Ordinary helpers
may forward this prefix, call Console-only helpers or call region-only helpers.
Local owners retain their original region identity across these calls; service
loans remain exclusive and cannot escape. The region has an explicit authenticated
IR operand, never a scalar argument. The private packed record starts with a
16-byte Console grant and an 8-byte region; its 24-byte prefix requires a 32-byte
aligned reservation when there are no later arguments. ABI facts identify both
nominal capability kinds, widths and offsets, including copied/span signatures.
The hosted test links the existing console and byte adapters. This language
feature adds no protected runtime adapter, combined trap admission or CPL3 console
wait contract.

Named forwarding acquires one independent synchronous child loan for each
forwarded capability before evaluating later value/span arguments, suspending
those parent roots. Each parent resumes only after its matching call and release.
A helper may forward either singleton subset or the pair in either formal order.
An unrelated, unforwarded capability remains usable and may be independently
forwarded while another root is suspended. This deliberately rejects `helper(session, session.put(byte))`.
A caller without its own service parameter cannot supply authority. Ordinary copied
result enums remain data and can cross helpers/modules independently of authority.

The closed operation table in `builtin_catalog.au` owns these contracts:

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

## Fixed COM1 UART grant

`builtin::Com1UartGrant&` is a singleton exclusive service parameter for the fixed
COM1 UART at base `0x3f8`, count 8. It is not a general port-range capability.
It has the same non-constructible, non-storable, non-copyable and non-reflectable
capability contract as the other sealed services. It never exposes a numeric port, pointer,
grant constructor, revocation operation, generic I/O intrinsic or wider I/O width.
Ordinary helpers may forward it with copied scalar/class inputs and results.
Offsets are checked at runtime, not compile time: `read8(1000u64)` typechecks but
fails closed at the native grant before I/O. Read offsets are 0/2/5; write offsets
are 0/2. BIOS and standalone UEFI console UART policies have migrated;
protected/graphical UEFI UART and early-boot serial consumers remain.

- `read8(u64 offset) -> u8` requests one byte from an allowed offset in the live grant.
- `write8(u64 offset, u8 value) -> builtin::PortWriteResult` has the sole copied
  result `issued` (0): exactly one OUT instruction was issued. It does not mean
  device acknowledgement, successful transmission, a retry, or completion.

The closed runtime symbols are `__au_runtime_port_read8(grant, generation, offset)`
and `__au_runtime_port_write8(grant, generation, offset, value)`. All channels are
full-width qwords; the compiler passes arguments in RDI, RSI, RDX and (for writes)
RCX. Before exposing the typed result, generated code rejects a raw read above
255 or a raw write result other than zero. Trusted native adapters validate live
grant identity/generation, byte width, offset and direction before an I/O
instruction. Source cannot mint or revoke authority. No mixed Port service group,
Port+ByteRegion prefix, u16/u32 operation or device-address escape is admitted.

Permanent wire identities append Port kind 4, read operation 6, write operation 7
and metadata type 19 without changing existing values. The Port copied enum and
service contracts activate only when admitted syntax references `Com1UartGrant` or
`PortWriteResult`, including imported and unused-template syntax and enum-case
expressions. Comments, strings and unrelated user names do not activate them.
Call and Port activate independently: selected contract row positions are not
permanent operation/kind IDs. Port-free descriptor/reflection/ABI output retains
the legacy catalog. Port ABI parameters name `builtin::Com1UartGrant` explicitly.
The Port-only stack record distinguishes copied class parameters with
`copied_class` and copied results with `result_kind: copied_class`; their widths
come from admitted canonical class layouts, including padding, rather than a
scalar-width approximation. The corresponding ABI record retains nominal class
names and complete layouts for native admission to cross-check. Legacy non-Port
stack records are unchanged. This contract is pending focused and full qualification.

## Copied request/reply call

`CallSession.call(u64 request)` returns `builtin::CallResult`, with public fields
`status: builtin::CallStatus` and `value: u64` in that order. The closed status
cases are `replied` (0), `cancelled` (1), and `rejected` (2). Failure values must
be zero. The copied result has two qwords and carries no wait or wake authority.
Helpers may forward the singleton exclusive session and return copied results;
all ordinary lifetime, initialization and nominal layout checks still apply.

The compiler-selected `__au_runtime_call` boundary receives the opaque grant,
generation and request in RDI, RSI and RDX. It returns status in RAX and value in
RDX. Generated code checks both full-width channels before storing them in local
result storage. No result pointer crosses this boundary. Native source/ABI and
hostile IR tests establish this compiler contract. The bounded UEFI `user-call`
consumer links it to an exact `INT 0x82; ret` stub. Its private wait record binds
both incarnations, endpoint, mailbox transaction, integer frame and original run
authority. Publication and parking occur with interrupts disabled; the caller's
kernel entry unwinds and pending interrupts drain before the peer executes.
Completion consumes the durable reply or cancellation once, then restores the
original epoch and remaining quota, changing only RAX/RDX in the retained frame.
A second call in the same incarnation returns rejected/zero without publication.
Retirement cancels outstanding work and scrubs retained authority before reuse.
This is one fixed client/service pair, not general scheduling or concurrent calls.

## Retained service exchange

`ServeSession.exchange(u64 reply)` returns `builtin::ServeRequest`, with public
`status: builtin::ServeStatus` and `value: u64` fields at offsets 0 and 8. Its
closed statuses are `request` (0) and `cancelled` (1); cancelled requires zero
value. The exact 16-byte sealed capability is a singleton exclusive parameter,
not a copied value or an endpoint. Existing synchronous helper forwarding and
copied-value rules apply; no construction, storage, return, reflection, mixed
capability group, escaping borrow or asynchronous language feature is admitted.

`__au_runtime_serve_exchange` receives grant, generation and reply in RDI, RSI
and RDX, then returns status in RAX and value in RDX. Full-width status and
cancelled-value checks run before any typed local write. Its stack fact is
`sysv_arguments: 3, result_max: 1`. The protected entry is exactly
`aurora_user_main(builtin::ServeSession&) -> u64`; an ordinary return is service
death rather than successful completion. Only the separately admitted exchange
trap parks the runtime service with its ordinary locals retained.

Permanent identities append kind 5, operation 8 and metadata type 20. The
singleton group mask is 32, so its catalogue bit is the full-width value
4294967296. Parser admission permits restrictive subsets of the closed group
allowlist; lowering accepts exactly the eight old/base plus optional Call,
Port and Serve catalogue combinations. No mixed Serve bit is authorized.
Only admitted graph syntax referencing ServeSession, ServeRequest or ServeStatus
activates the family, including unused templates; comments, strings and unrelated
names do not. Serve-free catalogue, reflection, assembly and ABI behavior stays
unchanged. Serve helper facts identify copied classes and exact layout widths,
while the runtime entry remains the exact singleton 16-byte prefix.

This boundary supports only the separately qualified opt-in bounded volatile
RAM-file profile. It is not a general daemon, scheduler or filesystem API.
Source, hostile IR, full-width raw ABI, image/stack and guest qualification are
required independently; implementing the primitive alone establishes no retained
file functionality.

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

## Hosted files

`builtin::HostFiles` is a sealed service kind for hosted programs. The entry is
exactly `auto main(builtin::HostFiles& files, builtin::span<const u8> arguments)
-> builtin::HostExit` in the root module, or the same with a
`builtin::ByteRegion region` after `files` ([hosted memory](#hosted-memory));
any root `main` naming HostFiles or HostExit with another signature is rejected. `arguments` is the command line as
one readonly block of NUL-terminated arguments (data, not authority).
`builtin::HostExit` is `success`, `failure`, `usage`, the exit status 0, 1, 2.
The ordinary service rules apply: one leading exclusive `&` formal, no
construction, copy, move, assignment, storage, return, reflection or conversion,
child-loan forwarding to helpers, and a singleton group (no Console, Display,
Event, Call, Port or Serve beside it). Its group bit is bit 0, the empty kind set,
because the singleton set 64 has no bit in the 64-bit group word.

Operations copy data only; `builtin::HostStatus` is `success`, `invalid_handle`,
`not_found`, `denied`, `escape`, `not_regular`, `exhausted`, `too_large`,
`invalid_path`, `failed`:

| Operation | Result |
|---|---|
| `open_directory(span path)` | `HostDirectoryResult {status, id, device, inode}`; any no-symlink path |
| `open_beneath(u64 directory, span relative)` | `HostFileResult {status, id, size, device, inode}`; regular files beneath the directory, no symlinks, `..` or absolute path |
| `open_file(span path)` | `HostFileResult`; a regular file at any no-symlink path |
| `close(u64 handle)` | `HostStatus`; closes a directory or file |
| `read(u64 file, u64 offset)` | `HostChunk {status, count, bytes}`; `count == 0` at end of file |
| `create_output(span path)` | `HostOutputResult {status, id, device, inode, directory_device, directory_inode}`; an exclusive temporary beside the destination |
| `write(u64 output, span bytes)` | `HostStatus`; at most 64 MiB per output |
| `commit(u64 output)`, `discard(u64 output)` | `HostStatus`; atomic rename into place, or removal |
| `print(HostStream stream, span bytes)` | `HostStatus`; `stdout` or `stderr` |

`HostChunk.bytes` is `array<u8, 504>`: with the two leading words that is the
whole 520-byte copied-class bound (506 of 513 leaves). It is the one sealed class
with a public array; a program copies it to a local (`const array<u8, 504> bytes
= chunk.bytes;`), and only the read primitive produces a chunk. Ids are plain
numbers, `generation * 64 + slot + 1`, checked against the session's own tables:
32 open directories and files (slots 0..31) and 4 outputs (slots 32..35), each slot with a generation that
advances on reuse. An id that does not name a live handle of the right kind
(stale, foreign, mistyped or made up) yields `invalid_handle`; a full table
yields `exhausted`. `close` frees a directory or file slot (files opened
beneath a closed directory stay open); outputs end only by commit or discard.
Device and inode identify what was opened: the directory, the file, and for an
output its directory and the existing destination (0 and 0 when absent), so a
program can refuse to replace one of its inputs or to name one destination
twice. Ids are deterministic data: guessing a live id
grants only what the session already holds. Uncommitted outputs are discarded
and every descriptor closed after `main` returns, but not when the process dies
by a signal or trap, which leaves its `.aurora-output-*` temporaries behind;
destination names in that namespace are rejected. Committed files have mode
0600. Like the module loader, `open_beneath` and `open_file` open before
they check for a regular file (nonblocking, so a FIFO cannot hang them).

The operations are implemented in Aurora by a binding module, imported as
`aurora.host`. Every `aurora.*` module name is reserved to the compiler except
its own sources (`aurora.compiler.*`, `aurora.tests.*`, which every bootstrap
stage reads through ordinary module roots): a reserved import resolves only
from the compiler's runtime root (`runtime/linux`, fixed when aurorac is
configured, or the directory `--runtime-root` names, as for a relocated
compiler; whoever runs the compiler chooses its trusted runtime, as they
choose the compiler: the memory entries trust the addresses `aurora.memory`
returns, so another runtime decides the program's memory safety too, and
nothing in the output records which root was used), never from a
`--module-root` or an overlay, and is
rejected if a module root also holds it; a root module declaring a reserved name is rejected. `files.NAME(...)` calls the exported
`host::files_NAME(files, ...)` of that module (`read` and `write` are reserved
function names) as an ordinary service-helper call. The Linux binding,
`runtime/linux/aurora/host.au`, uses twelve private HostFiles primitives that
only an imported module named `aurora.host` may name: `load`, `store`, `load8`
and `store8` over the zeroed 16384-byte session block the grant addresses, and
the system calls `system_open` (openat2 under one of six compiler-fixed open
modes: directory, regular file, O_PATH probe and exclusive create without
symlinks, the last three beneath their directory, read-write for `/dev/null`,
and regular file at any path), `system_chunk` (pread64 into a cleared
HostChunk), `system_write`, `system_rename` (renameat), `system_unlink`
(unlinkat), `system_close`, `system_stat` (fstat) and `system_identity`
(getpid). The compiler emits each inline with a `syscall` instruction after
checking every offset and length against the session block (failure traps);
paths are NUL-terminated in the block, and only scalar results return. The
typed-IR verifier admits the primitives only in functions whose native name
belongs to module `aurora.host`. Every primitive is an operation on a held
HostFiles loan, which only `main` receives (and the compiler's byte runtime
entries, from `main`'s region, for [hosted memory](#hosted-memory)), so even the
binding reaches the system only on behalf of a program that was handed the
capability; a library
importing `aurora.host` cannot name the primitives or the binding's private
helpers. The binding is trusted code of the compiler. A binding
over Aurora kernel services (Call/Serve or the file namespace service) would be
another `aurora.host` with its own primitives and the same ten functions.

For a hosted entry the backend emits a global `_start`: it reads argc/argv from
the initial stack, requires the argument strings to be contiguous, reserves and
zeroes the session block, calls `host::start` (which puts `/dev/null` in place
of a closed descriptor 0, 1 or 2, so no output can take a standard stream's
number; failure exits 1), then `main` with the grant and the arguments span,
then `host::finish`, and exits with `exit_group`. A hosted `main` whose graph
lacks the runtime hooks is rejected. One aurorac object therefore
links with `ld -static -e _start` and no C or C++ startup, libc or runtime (see
`hosted_programs` in `meson.build`), including programs whose owners use the
[hosted memory runtime](#hosted-memory). Stack facts record a
`__au_linux_system_call` call for every function that makes one, and
`kernel_stack_check.py` rejects it in every kernel and user image profile.
aurorac itself is such a program (`compiler/aurorac.au`, see
[README](README.md)), with a region.

## Hosted memory

A hosted `main(builtin::HostFiles& files, builtin::ByteRegion region,
builtin::span<const u8> arguments)` receives one region with a fixed quota of
4 GiB of payload; the program must import `aurora.memory`, the memory runtime
(`runtime/linux/aurora/memory.au`), as it imports `aurora.host`. The region follows the
ordinary [ownership rules](OWNERSHIP.md): only parameter binding introduces it,
helpers take it first or after `files` in the mixed prefix above, and owners stay
in the generated code's 32-byte descriptors. The region word is the session
block's address; nothing else can name the session.

Generated owner code is unchanged: it still calls the private C-convention
entries `__au_runtime_bytes_{allocate,at,set,resize,drop,borrow_length,borrow_span}`
and `__au_runtime_values_{allocate,at,set,resize}`. For a hosted entry with a
region the compiler defines them locally in the program (`x86_module.au`). Each
entry checks that the descriptor's region word names the session (the word at
`host_session_self()` from it is itself), calls one function of the private
namespace `memory` with the session as its HostFiles grant and the descriptor's
words as scalars, traps (UD2) on its fail-stop result `u64` max, and then
updates the descriptor or copies one element (or the fill, element by element)
to or from the address the runtime returned. The runtime decides everything
else: descriptor validation, quotas, ids and mappings. The hot entries (bytes
`at`, `set` and `borrow_span`, values `at` and `set`) first take an inline fast
path with no frame or call: it makes exactly the checks of the runtime's own
fast path and of the access primitive behind it (success word, session
self-word, the state mapping's length, the slot record's id, length and stride
or liveness, index and element bounds against the length and the slot's
mapping), reading the runtime's state directly, and otherwise falls through to
the call above, which validates again and traps or fails as before. The state
layout it reads is one contract, `host_memory_record` in `x86_helpers.au` and
the state comment in `memory.au`. The entries trust the
addresses the runtime returns and the region word of the descriptor they are
given (a word that does not name a session faults or traps on the self-word
read): like `aurora.host`, `aurora.memory` and these entries are trusted code
of the compiler, and source and typed IR cannot forge a descriptor, a region
or a runtime function (the verifier admits the primitives by the runtime's
native names, and `aurora.*` modules load only from the runtime root).

Each nonempty allocation is its own private anonymous read-write mapping; empty
ones have none. `_start` reserves, after the session block, a table of 16384
(base, length) entries and the session's own address, which only the memory
primitives write. HostFiles operations 21..28 are those primitives, admitted (in
lowering and in typed IR) only in functions of `aurora.memory` and emitted only
when the entry takes a region: `map_memory(slot, length)` (mmap),
`remap_memory(slot, length)` (mremap with MREMAP_MAYMOVE), `unmap_memory(slot)`
(munmap), which return 0 or the negative errno and change the entry only on
success, and `memory_load`, `memory_store`, `memory_load8`, `memory_store8` and
`memory_address(slot, offset, count)`, which trap unless the slot is below 16384
and offset plus width lies within the slot's length. Session primitives cannot
reach the table (their offsets stay below 16384), so the runtime reaches only
memory it mapped. Slot 0 maps the runtime's state: bytes in use, live count, the
free-slot list and one record (latest id, stride while live, length, dirty
mark) per slot. An allocation id is `generation * 16384 + slot`; the generation advances
on every allocation and resize of the slot and a slot whose generation is
exhausted is retired, so ids are never reused and a stale or forged descriptor
traps. `memory::start` (after `host::start`) maps the state, failing the
process with exit 1 before main; after main, a live allocation traps.

Semantics are those of the [hosted adapter](OWNERSHIP.md#hosted-bootstrap-boundary):
the same final-logical-quota checks for allocation and resize, inert failures for
negative, unrepresentable or over-quota sizes, exhausted slots and failed
mappings, zeroed (or filled) new bytes, a fresh id for every changed size, same
size unchanged, prefix kept and shrunk bytes never resurfacing (a per-slot dirty
mark zeroes the kept page's tail on regrowth), contiguous kind-0 views, and
bounds failures as false results or traps where the adapter has them. The
differences: faults are UD2 traps (SIGILL) without the adapter's message; an
element access must use the stride its allocation was made with (the adapter
checks only that the length is a multiple of it);
resizing moves pages with mremap instead of copying, so no staging block
coexists; at most 16383 allocations are live (reachable only through ~16k owner
bindings at once); physical memory is committed on first touch, so host memory
exhaustion after a successful mapping kills the process; and there are no
metrics, test allocator or fault injection. Runtime cost is one system call per
nonempty allocation, resize and drop and a page per nonempty allocation; the
table makes `_start` reserve 272 KiB of stack, so a stack limit below about
300 KiB faults before `main`. Element copies move whole qwords for strides that
are a multiple of eight. With the entries' fast path a compiler built by this
emitter compiles the compiler in 0.57x the instructions and 0.63x the cycles
of one built without it. C1 gains this (and aurorac stops being about 1.6x
slower than over the C++ adapter) when its first compiler has it: always from
the seed, and from a cached compiler built from `a62c3c45` or later.
`memory.au` keeps its own fast paths for older ones.

Cases: the memory probe over `tests/host-files/memory.golden` (every fast path,
including a three-byte stride, and the fall-through of bytes `set`, `borrow_span`
and values `set` for failed owners, indices outside an owner and empty views;
generated code bounds-checks `at` before the call, so its fall-through is
reached only by a descriptor source cannot make) and the
`host-sort` example in `tests/host-files/cases.golden`; rejections (region entry,
prefix, primitives, private runtime functions) in `rejections.golden`; and the
memory-primitive IR cases in `tests/compiler/ir/host-files-service-ir/`. The C++
adapter `runtime/hosted_bytes.cpp` remains only in the C++ test drivers, their
hosts and the optional language server.

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
including copied service inputs/results and `console::write_bytes` success/timeout prefixes.
Independently constructed hostile IR lives in the textual IR cases under
`tests/compiler/ir/*-service-ir/`, run by the one `aurora-ir-check` driver; each
service has its own directory and Meson test.
HostFiles runs its example tool and hostile-case driver over
`tests/host-files/cases.golden` and its source rejections over
`tests/host-files/rejections.golden`. Acceptance
requires the applicable gates on final integrated source; host-grant and UART
tests remain separate from generated-code tests.
`display_service.py`, `tests/compiler/ir/display-service-ir/` and the handwritten
`display_service_abi.S` add second-kind source, cross-module copied reflection,
forged-kind/slot/operation/loan and seven-argument ABI coverage. The Display
gates are in the Meson merge suite and the compiler
native test graph. Native Display grant/transport and guest qualification remain
separate from these compiler tests. See the
[kernel migration contract](../docs/native-console-service.md) for required
linked-stack, image, emulator, restoration and final developer gates. Qualification must match the exact final source and built images.

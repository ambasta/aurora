# Readonly whole-array byte spans: milestone014

This development candidate adds a narrow synchronous borrowing boundary, not a
general reference, slice, heap-buffer or lifetime-generic system. Independent compiler review and complete author release/sanitizer targets passed
on the corrected candidate. Final parent aggregate and 147-mode kernel integration passed; see docs/verification.md. Milestone013 archives are unchanged.

## Source contract

A named local `builtin::array<u8,N>` (including its fixed `array` alias) may be
borrowed with `const builtin::span<const u8> bytes = borrow_bytes(storage);`.
Local builtin arrays retain their existing 1..4096 element limit. Private array
fields and std::array wrappers retain their existing limits and cannot supply
origins for this span operation.

A span provides readonly `size() -> i64` and bounds-checked `at(i64) -> u8`.
It covers the whole array; there is no subspan or zero-length construction.
A local span copy reborrows readonly storage instead of copying bytes. Its lifetime
is conservatively bounded by the source span binding's lexical scope, even when
an underlying owner might live longer. Local bindings must be const, initialized
and non-rebindable. Multiple readonly reborrows coexist.

While a span or any descendant reborrow is live, original-owner element mutation
is rejected. Owner reads and independent by-value array copies remain allowed.
After all corresponding borrows end, a mutable owner may be written again.
There is no runtime borrow counter or GC: the analyzer checks lexical borrow
state and IR validates explicit capability lifetimes before native emission.

Ordinary functions may receive `builtin::span<const u8>` parameters and forward
reborrows synchronously. A parameter's capability lasts only for its invocation.
Span values cannot be returned, stored in classes, assigned into outer bindings,
passed as class-method/constructor parameters, used as template arguments,
reflected, compared, converted or treated as scalar values. No global storage,
mutable span, raw base address or arbitrary pointer/length constructor exists.
Const class receivers do not create exceptions to private-field borrowing rules.

Arguments evaluate left-to-right. Acquiring a direct temporary borrow at an
argument position keeps it live through later argument evaluation and the complete
call. Callee forwarding cannot widen that authority. Current source syntax has
statement-only array assignment and no shared global/array-reference mutation
path, so a valid later argument cannot directly mutate that local owner. Direct
IR nevertheless rejects a write during that interval. A source assignment-expression
syntax rejection is not evidence that a lifetime checker analyzed such an expression.

Branches and loop backedges must preserve the same continuing borrow state.
Branch-local borrows end before joins; returning paths release invocation borrows
before return and do not constrain a continuing sibling. Scope exit releases
children before parents, then ends local array lifetimes. Unsupported escaping or
divergent states reject rather than extending a borrow by inference.

## Typed IR and private invocation representation

Local byte-array origins have explicit metadata and BeginArray/EndArray lifetimes.
BorrowSpan requires a fully initialized active array; ReborrowSpan requires an
active parent capability. The verifier preserves exact local-array or parameter
origin, static creation sites and direct-parent authority, and refuses to end a parent with live descendants or an
array with outstanding borrows. Writes to any borrowed owner byte reject.

SpanLength reveals only the length. SpanLoad combines signed-index bounds checking
and a typed byte load: negative/out-of-range indices fail at the existing bounds
UD2 before loading the base pointer or calculating the payload address. Span
capabilities never inhabit scalar value/operand slots. A declared spill alone
cannot manufacture a capability or establish initialized entry authority.

The private call record gives each span a typed sixteen-byte pointer/length
reservation. Spill bytes are disjoint from scalar, object and other capability
storage. The signature still permits at most six source parameters; spans do not
expand into extra scalar argument registers. Scalar positions retain their existing
indexed registers before packing; class and span positions use explicit record
offsets. Complete mixed records are passed through the existing internal hidden
record convention. BindSpanParameter must appear in the canonical entry prefix
and match an exact span parameter/spill. No plain scalar Call/BindParameter can
substitute for this boundary. Class results retain separate complete result storage.

Span-bearing functions have native value-boundary names and local linkage. They
are unavailable through the global host/kernel scalar bootstrap entry seam. All
callers establishing span records belong to the validated Aurora module graph;
this is not a foreign-language ABI accepting externally supplied pointer pairs.
Reflection and value conversions cannot observe capability spill contents.

## Runnable binary reader

`import std.binary;` exports `std::ByteReadStatus { success, out_of_range }`,
`std::ByteReadResult`, and `std::read_le32`/`std::read_be32`. Reader arguments are a
readonly span and signed offset; results are independent class values containing
status and a u64 number. Checks occur in this order: nonnegative offset, length
at least four, then offset no greater than length minus four. Only then are four
bytes read and explicitly widened/combined. Invalid offsets produce a recoverable
report rather than an artificial arithmetic trap. No u32 type is needed.

`status()` and eager `value_or(u64 fallback)` expose the result. A publicly
constructed error report never exposes its stored number through value_or; report
construction is not a parsing certificate. The example binary_reader.au forwards
an eight-byte owner, reads two endian words, returns42 and mutates the owner after
the temporary borrow has ended. No whole input buffer is copied at the span call;
this is a mechanism statement, not a throughput or zero-cost benchmark claim.

## Acceptance boundaries

Required evidence includes native byte/endian models for lengths1/3/4/8/64/4096,
all relevant offset boundaries and signed extremes; exact bounds sites; independent
copies and post-release mutation; multiple shared reborrows and nested forwarding;
six mixed argument positions with class results; branch/loop/return cleanup; source
visibility/type/lifetime rejection and malformed IR origin/extent/spill/entry/
initialization/call/end-order/join rejection. Preserve every earlier language,
IR, sanitizer and native gate. Tests do not prove Rust-equivalent memory safety.

Ordinary recursion and stack exhaustion remain possible. Existing frame, graph and
array caps are not global compiler or target resource guarantees. Owned dynamic
allocation, drop insertion, mutable views, async lifetimes, interprocedural returned
borrows, arbitrary resource classes and safe runtime text remain separate work.

## Review finding under correction

Independent review reproduced an exact-lifetime verifier-contract gap in the
initial candidate: one IR branch could end/restart the same array/span slots and
join a branch retaining their earlier lifetimes because active origin/parent maps
compared equal. No invalid-memory behavior was reproduced. Ending still required
all descendants gone, rebegin cleared initialization, and reborrow required fully
initialized storage. The stronger promised join restriction nevertheless requires
explicit creation-site evidence, rather than relying on source syntax being unable
to express the IR example.

The corrected candidate retains static Begin/Borrow/Reborrow/parameter
creation sites and root/parent provenance. Three permanent restart/join rejection
cases and two accepted wholly closed loop-reuse cases pass, and the original
reviewer fixture now rejects. These are static control-flow identities,
not unique dynamic generation numbers for every loop iteration. Wholly closed
loop-local lifetimes may reuse the same static sites. The initial pins and passing
regression receipts are preserved as pre-strengthening evidence; the corrected release/sanitizer pins, dedicated rejection/closed-loop regressions
and complete reruns now pass. Milestone014 aggregate and all147 emulator gates subsequently passed; the evidence below identifies that verified checkpoint.

## Corrected compiler evidence

Release `2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`
and sanitizer `ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa`
pass the complete compiler target. This includes 91 new source native cases
(25 exact bounds sites), 69 source rejection fixtures, 950 direct IR cases, ten
exhaustive-dispatch checks and fourteen new native span checks (four bounds sites),
plus every prior language/IR/native/module/depth/host-I/O suite. Independent review
rechecked those new groups and 64 extra mixed-argument/class-result ABI cases on
both compilers. Source lifetime diagnostics are distinguished from syntax/privacy
rejection and from malformed-IR rejection. Alternate seeds overlap coverage.

Scalar oracles pass 630 default and 1,526 seed404 cases on both compiler builds,
and 64 comparisons against milestone013 agree. The binary-reader example emits
byte-identical assembly before/after the verifier-only site strengthening; this
one example is not a general equivalence or performance proof. Initial and
corrected receipts are kept separately in the compiler-review evidence directory.

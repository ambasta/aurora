# Copied ordinary method parameters (verified milestone022)

Status: complete release/fatal host ASan/UBSan compiler targets, independent
frozen-source review, parent adoption/rebuild, fresh aggregate and all 166 existing
emulator modes passed. Separate normal BIOS/UEFI boots restored both images.
[M022 evidence](../docs/evidence/milestone-022/README.md) identifies exact pins,
failures and review limits. This changes a private native calling convention even
though it reuses existing typed IR instructions.

## Source and lifetime contract

Ordinary methods accept concrete class values alongside scalar and enum explicit
parameters. Six explicit parameters remain the maximum. Every boundary class has
at most 64 flattened scalar leaves. Nominal identity, class-depth four, template
instance/definition limits, literal capacities and the source frame cap remain
unchanged. Private signatures and direct-import visibility are checked as before.

Receiver identity resolves first. Arguments then evaluate left-to-right; each
class argument must be a complete named local and is copied immediately into a
fresh readonly snapshot at its argument position. Later arguments can mutate the
source or receiver without changing earlier snapshots. Repeated arguments and a
receiver supplied as an argument are legal because their snapshots are distinct.
Only after all argument evaluation is synchronous receiver authority acquired.

The callee binds each class argument into its own immutable complete local copy.
Const methods and explicit independent mutable copies are allowed. Mutating a
parameter or calling a mutable method on it is rejected. Copying never reruns a
constructor. Class results copy a complete named local or parameter into a fresh,
exact-type destination, disjoint from receiver and argument snapshots. The result
binding becomes visible only after all arguments are evaluated. Checked faults
are fail-stop and do not promise rollback of earlier receiver side effects.

Sibling calls preserve current const/exclusive forwarding rules and suspend then
resume the caller's receiver authority. All constructor rules remain: complete
initialization, readonly snapshots, empty body, field-declaration-order
initializers, and no receiver access during initialization. Any call-graph cycle
containing a method or constructor is still rejected.

No temporary/chained receiver or class argument, direct returned call expression,
reference, resource/span method parameter, generic method, overload, class-field
reassignment or new template-body grammar is added. Use a named local for an
intermediate projection/result. This is bounded value transport, not a general
heap/lifetime or optional/expected implementation.

## Typed IR contract

MethodCall retains objectArguments and resultOffset. When any parameter is a
class, objectArguments has one position per explicit parameter; scalar/enum
positions are zero. Otherwise the vector is empty. Every class position denotes
an active, complete, exact nominal, readonly, distinct snapshot. No snapshot may
alias the receiver. A class result must be an exact active pristine object slot,
separate from receiver and every argument snapshot. Logical completion remains
required for nested and empty classes, independently of payload bytes.

BindObjectParameter remains in the parameter entry prefix and creates an
immutable local lifetime. ReturnObject requires a complete exact-type local and
balanced scalar operand stack. Constructor forwarding, const-authority widening,
ordinary/scalar calls targeting receiver entrypoints and forged physical storage
continue to reject. Lexical privacy remains a trusted frontend responsibility.

## Frozen private x86-64 convention

All ordinary scalar/aggregate function conventions are unchanged. All constructor
conventions are unchanged, including their internal i64 result. Existing methods
with only scalar/enum parameters retain positional scalar registers and R10 as
receiver. Such a method returning a class continues to use R11 as result address.

A NEW class-parameter method returning scalar/enum uses R10 for receiver and R11
for a packed explicit-argument record. All its explicit parameters, including
scalars/enums, bind from that record using existing record offsets/padding.

A NEW method combining class parameters and a class result uses three hidden
inputs simultaneously: R10 receiver, R11 argument record, RAX result destination.
The caller finishes scalar pops and record packing before loading R10 and then
RAX. The record remains live until the call returns. Scalar argument positions
are not compacted around class entries. Existing call-site alignment is retained.

The callee saves hidden inputs before any binding/body operation. With source
frame size F, receiver is saved at F+8 and argument record at F+16. Combined mode
saves result at F+24, reserves 32 hidden bytes and preserves 16-byte alignment.
Noncombined receiver modes reserve the existing 16 bytes. A result-only method
retains F+8 receiver/F+16 result; ordinary aggregate saves remain unchanged.
The hidden overhead is separate from the unchanged 65,536-byte source frame cap.
No private capability is source-addressable, a scalar IR value, reflection data,
or an externally advertised scalar-callable symbol. There is no C ABI promise.

## Library deliverable

std::array<T,N> gains mutable exchange(array replacement) -> array, using the
existing qualified injected self-type spelling std::array without template
arguments, including std::array previous = std::array(). Bare array retains
its builtin reservation; array<T,N> always names builtin storage, and
builtin::array is never callable. No parser or template-grammar change is made. It returns an independent copy of the old
contents and replaces every receiver element from the replacement snapshot. The
caller's replacement stays unchanged. Self-exchange returns the original value
and leaves contents unchanged. The implementation constructs a fresh old-value
array and copies checked elements through a loop; no class-field assignment,
heap allocation, reference or escaping element capability is used.

This is an Aurora member inspired by std::exchange, not a standard C++ std::array
member, atomic operation, general lexer API or performance claim. Four Scalar
element types and literal capacities 1..64 retain their existing restrictions.

## Acceptance and limits

Required evidence includes source success/rejections and independent array model,
malformed direct IR, source-independent native ABI tests with handwritten entry
and exit sides, exact traps, full release/fatal host ASan/UBSan compiler suites,
old-library M021 differential controls, and independent frozen-source review.
The old-library differential must use unchanged M021 module inputs, because the
new exchange member legitimately changes emitted std.array instance bodies.

Host compiler instrumentation does not instrument emitted Aurora programs.
Coverage/model steps and overlapping seeds are not additive proof counts. No
whole-program stack/resource bound, Rust-equivalent safety, binary compatibility
or equivalent-C performance is claimed. Parent aggregate and all 166 existing
emulator modes passed as a separate integration gate, with independent retained
validator replay and normal-image restoration. No physical AMD qualification or
new kernel functionality follows from that regression result.

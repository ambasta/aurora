# Bounded checked readonly byte windows

Status: the bounded feature passed isolated compiler/provenance gates and fresh
combined native plus all170+2 actual emulator gates, with independent review.
Development began from PR21; integration used the accepted PR22 kernel checkpoint
at main `3d85ef4ec24fa7f879106f1803df0931d9b386f4`, tree
`4687cf171d1098349c46bee7158b90ff85719d82`. Existing whole-array borrowing and
single-span library signatures remain unchanged. The feature adds no mutable view.

## Dependency and observable acceptance gate

Filesystem and kernel parsers need to limit a helper's byte-reading authority to
one validated region without copying that region or repeatedly passing independent
base offsets. Checked readonly child windows supply this narrow capability.
Positive/negative source and direct IR tests, independent native byte/length models
and exact trap PCs, span/overload regressions, complete release and fatal host
ASan/UBSan compiler targets, independent provenance/native review, a fresh combined
aggregate and all170+2 actual emulator gates passed. The
[integration record](../docs/readonly-windows-integration-results.md) distinguishes
the isolated sanitizer corpus from the combined release/native/emulator chain.
Leak checking remains unavailable. These finite gates do not prove whole-language
memory safety, global stack/resource bounds, physical support or performance parity.

## Source semantics

    const builtin::span<const u8> region = bytes.subspan(offset, count);
    const std::ByteReadResult word = std::read_le32(bytes.subspan(offset, 4), 0);

The receiver must be a named live readonly byte span. Both arguments must be
exactly i64. Parent validation happens first, then offset and count evaluate
left-to-right exactly once. Both evaluations finish before window bounds checks;
an arithmetic failure in count precedes an invalid-offset bounds failure. Parent
borrow authority remains live throughout. Call argument evaluation remains
left-to-right, and a temporary child lives through later arguments and the call.

Required conditions are 0 <= offset <= parent.size() and
0 <= count <= parent.size() - offset. No offset+count arithmetic is used. Violations
trap at the existing named bounds UD2 before loading or adjusting the payload base
address. The new window reads exactly the selected bytes, with index zero relative
to its own start. The subtraction cannot overflow after the offset check because
all internally established lengths lie in 0..4096.

Zero-length windows are valid, including at the parent endpoint. They retain
parent/root provenance; they provide no byte-access authority. Every at() on an
empty window traps before any payload load. There is no null pointer convention
or source-visible address, and an empty window cannot be widened.

## Lifetimes and restrictions

Each child is an immutable reborrow, conservatively bounded by its direct parent's
lexical scope, and transitively by the local-array or invocation root. A window
may itself be forwarded, copied as a readonly reborrow, or be a named receiver for
another window. Descendants must end before parents. All parent and root borrows
exclude owner mutation, including empty views, until their release. Branch and
loop joins retain exact static lifetime sites just as whole-span reborrows do.

Windows can be initialized only into const span locals or passed directly as
ordinary-function span arguments. They cannot be returned, stored in class fields,
assigned into outer bindings, compared, reflected, converted, passed to class
methods/constructors, or used as generic type arguments. Temporary-receiver chains
are intentionally rejected; name the intermediate view. No mutable authority,
raw pointer, heap, reference-return or C ABI is introduced.

The builtin operation is recognized only on actual span receivers. User-defined
class methods named subspan and ordinary overload sets keep their previous meaning.
Explicit single-span and multiple-span function signatures are unchanged.

## Typed IR and native implementation

Subspan{sourceOffset,resultOffset} requires an active exact typed source spill, a
fresh exact typed destination spill, current i64 count, and a saved i64 offset on
the scalar operand stack. It consumes the offset, preserves the scalar count but
clears its unrelated bounds evidence, and creates no scalar capability. The
result records the parent's exact root kind, root slot/site and direct parent
slot/site, plus its own creation site. No malformed source scalar, spill interior,
ended parent, overlapping reservation, return escape, borrowed-owner write or
incompatible control-flow lifetime is accepted.

Native emission uses unsigned comparisons to reject negative signed operands as
well as excessive positive values. The parent length is loaded first; offset is
checked against it, count against the remainder. Only then is the parent base
loaded/adjusted and the readonly pointer/length pair written into the disjoint
capability spill. It uses the same private validated call records as whole spans.
No externally supplied pointer/length record can enter this language boundary.

## Reproducible focused gates

    make -C compiler test-readonly-windows OUT=../build/aurorac

Each focused run creates a fresh artifact directory under the compiler output
directory. Failed source/assembly/native products remain there. Source validation
uses independent Python slice arithmetic, complete 64-bit results and exact named
trap PCs. Direct-IR tests bypass parsing and native emission is then executed
against independent offset/count/index expectations.

## Limits

These bounded tests are evidence, not a proof of memory safety, global stack
safety, Rust equivalence, device qualification or C-equivalent performance.
Parsing failure remains the responsibility of existing recoverable parser APIs;
subspan is a checked operation, not an optional or result-valued range constructor.
General returned borrows, mutable views, resource fields, heap buffers and async
lifetimes remain separate work.

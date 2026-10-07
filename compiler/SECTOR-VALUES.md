# Bounded owned sector-sized byte values

Status: the [focused executable composite](../docs/sector-values-results.md)
and independent final artifact review passed. This contract supersedes
earlier 64-total-leaf copied-value limits only as specified below. Historical
milestone results do not qualify this extension.

## Representation and ownership

A concrete private `builtin::array<u8,512>` field can own a complete 512-byte
sector-sized payload. Its constructor must explicitly zero every byte with an
empty-brace initializer. Checked signed-i64 indices, exact-u8 stores, private
state and complete independent class copies retain their existing semantics.
The array itself cannot escape as a view, reference, pointer or direct argument.

A composed class, or a class used as an ordinary function, constructor or method
parameter/result, must satisfy all of these independent limits:

- At most 512 u8 leaves
- At most 64 non-u8 scalar leaves, including bool and enum leaves
- At most 513 total scalar leaves
- At most 520 canonical reserved storage bytes, including padding

This admits a 512-byte owned class and a copied report with one eight-byte status
enum plus that class. Either declaration order has 520-byte canonical storage.
The report can expose a recoverable status and copied success-or-zero payload
without an allocation, mutable span, raw reinterpretation or new unsafe operation.
Status masking remains a library responsibility; this compiler contract preserves
complete values and does not invent persistence, I/O or failure semantics.

Private non-u8 array fields and all class-template capacity arguments remain
1..64. Local builtin arrays retain 1..4096, class containment depth remains four,
and signatures retain six explicit parameters. A standalone noncomposed local
class retains its separate 8,192-leaf/65,536-byte layout limits. The source frame
is still limited to 65,536 bytes. No constant-sized class creates a heap object.

## One canonical layout and two checked boundaries

The parser and semantic analyzer apply the element-specific private-array bound.
Semantic class composition and every copied signature use the shared logical
leaf predicate and the canonical storage extent. Direct typed-IR validation
independently checks those same bounds, exact nominal nested ranges, initialized
leaves, object reservations, readonly argument snapshots and pristine results.
The canonical layout builder rejects a field with an invalid element-specific
extent before computing offsets. Supplied physical metadata must still exactly
match the shape-derived canonical layout.

U8 stride remains one byte. Earlier scalar/bool/enum storage remains eight bytes.
No IR instruction, private calling convention, ABI register assignment or x86
emitter operation changes. Copies remain explicit complete typed-leaf copies;
there is no new copy-elision or bulk-copy optimization and no C ABI promise.

## Stack and compiler-resource scope

The backend's argument size is each class's canonical reserved byte extent,
not eight bytes per logical leaf. Six maximum 520-byte reports occupy exactly
3,120 bytes in the outgoing argument record, already a multiple of 16. Their
callee-local parameter copies occupy a further 3,120 source-frame bytes. The
caller also reserves six independent 520-byte argument snapshots. Each result
reserves a 520-byte caller destination; return writes that existing destination
and does not create a second outgoing result record.

These reservations are additive. The backend adds up to 32 hidden save bytes to
a source frame; saved rbp, return addresses, live scalar operands and at most an
eight-byte call alignment adjustment add further runtime stack usage. Every
nested live call retains its callers' storage. Ordinary-function recursion has
no finite whole-program stack bound. The 65,536-byte source-frame limit is a
compiler resource bound, not a runtime stack guard or a kernel admission rule.
The current emitter does not probe each intervening page when reserving stack
storage; guard pages alone do not prove that large reservations cannot skip one.
Representative finite call-chain measurements and their exact fixture identity
must accompany native acceptance. Kernel use requires separate review against
its smaller stack budget and existing protected-image/guard contracts. No kernel
stack limit changes or automatic admission follow from hosted compiler tests.

Lengths, offsets and record sums use int. Validated objects and six-parameter
records remain far below its limit. Class layout/frame extent checks remain
fail-closed before native emission. Dense initialization facts support more than
64 leaves already; receiver initialization sets and emitted copy/zero sequences
still grow with the number of leaves. This change is not a compiler-wide memory,
complexity, denial-of-service or whole-program memory-safety proof.

## Deliberate legacy test changes

The following old byte-only/mixed-byte rejections become positive coverage:

- `packed_values.py`: 65 mixed leaves cross a value boundary; private byte-array
  capacity 65 becomes supported and its negative boundary moves to 513
- `nested_values.py`: 65 byte leaves in copied and unused composed values
- `function_templates.py`: a copied generic result with 65 byte leaves

Existing 65 i64/u64/bool leaf rejections and non-byte array/template capacity-65
rejections remain. New tests explicitly cover private array 512/513, u8 leaf
512/513, total leaf 513/514 and canonical reserved extent 520/528. Padding must
not bypass the storage budget, and scalar byte fields must not bypass leaf caps.

The focused source suite also covers complete 512-byte patterns, upper-offset
reads/writes, zeroing, full-u64 observations, recoverable failure masking,
constructor/function/method/generic/nested copies, six arguments, snapshot
ordering, privacy, readonly values, source-frame exhaustion and exact bounds
traps. Direct-IR and handwritten ABI fixtures provide an independent boundary
check rather than relying only on two mutually agreeing compiler paths.

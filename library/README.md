# Aurora libraries

These are real Aurora modules. Fixed values compile freestanding; allocating
collections use explicitly granted regions and a trusted hosted adapter. Imports
are direct, including public signature types; dependencies are not re-exported.
No complete libc/POSIX/C++ compatibility library or native process runtime exists.

```sh
build/aurorac --module-root library application.au -o build/application.s
```

## Scalar and fixed-value modules

- `std.core`: i64 `min`, `max`, checked `abs`; abs(I64_MIN) fail-stops.
- `std.numeric`: independent `Accumulator(initial)` with checked `add`/`value`;
  `minmax` returns copied `MinMax` with `min`/`max`; `range_width` checks overflow.
- `std.integer`: i64 `gcd`, `lcm`, `div` and copied `DivResult.quot/rem`.
  Gcd/lcm are nonnegative when representable; lcm with zero is zero. Division
  truncates toward zero. Zero divisors and unrepresentable quotients trap;
  I64_MIN % -1 is zero.
- `std.bit`: u64 `popcount`, `bit_width`, `has_single_bit`. Zero count/width is
  zero; maximum u64 has count/width 64. Loops are bounded by 64 iterations.
- `std.utility`: explicit `pair<T,U>` and `make_pair<T,U>` over admitted Value
  types. Public first/second fields are complete independent values; no deduction
  or reference pairs. Fully concrete nested specializations are bounded.
- `std.array`: `array<T,N>` for Scalar T and explicit N=1..64; zero construction,
  fixed `size`, checked copied `at`, mutable `set` and `exchange`. Exchange snapshots
  replacement before mutation and returns independent old contents; self-exchange
  works. This is not concurrency atomicity or the C++ std::array ABI.
- `std.decimal`: `DecimalAccumulator.push_digit` accepts 0..9 with checked
  value/count and sticky invalid_digit/out_of_range failure; `reset` restores
  empty state. `finish` copies status, accepted-digit position and eager
  `value_or`. `format_decimal_i64/u64` return bounded canonical decimal bytes.
  `format_decimal_width_u64` returns 1..20; `format_decimal_digit_at_u64` projects an ASCII
  digit by units-based place, returning NUL for absent or invalid places.

All arguments evaluate left-to-right. Fallbacks are eager, reports are ordinary
forgeable copied data, and no report grants access to source or a resource.
See [value semantics](../compiler/VALUES.md) and [scalar rules](../compiler/SCALARS.md).

## Bytes and codecs

`std.bytes` provides private copied `Bytes2`, `Bytes4`, `Bytes8` and LE/BE
16/32/64 encode/decode functions. 16/32-bit encoders reject values outside their
width through copied Encode16Result/Encode32Result and mask failure bytes to zero;
all u64 values fit the direct Bytes8 encoder. Decoders accept every exact-width
byte pattern. `ByteCodecStatus` and checked byte access preserve explicit failure.

`std.binary` supplies `ByteReadStatus`, `ByteReadResult` and readonly-span `read_le16/be16/le32/be32/le64/be64` readers. They reject negative offsets, short spans and offset beyond size-minus-
width before reading, return a copied u64 and mask failures through `value_or`.
`std::starts_with` and `std::equal` compare readonly byte spans exactly without
allocation or retained views; empty prefixes match, equality also checks length.
There is no normalization or textual meaning assigned to NUL/non-ASCII bytes.

## Console input and output

`console.line` supplies the shared `Line64` editor and `ConsoleEvent` values for
BIOS, simple UEFI, graphical and protected sessions. Its constructor accepts the initial
CR carry; protected readers preserve that bit across command execution. Its
private 64-byte ASCII state owns no
transport authority; [input and submission behavior](../docs/native-console-service.md#input-behavior)
is shared while each consumer handles its own output.

`console.io` supplies `write_bytes(ConsoleSession&, span<const u8>)`. Its copied
`WriteResult` exposes `written()` successful bytes, `status()` (`WriteStatus::complete`
or `::timeout`) and `complete()`. Empty input completes with zero transport calls.
The first timeout stops output, preserving the emitted prefix and excluding the
failed byte from the count; nothing is retried or rolled back. Results are ordinary
forgeable data with no authority or retained span. Console and IOMMU consumers use
the helper while keeping their existing failure/acknowledgement policy.

`console.program_input` reads one protected-console submission through a sealed
ConsoleSession and returns copied bytes, an action and CR carry. Native command
execution and publication remain outside that input capability.
`console.program_output` presents a bounded copied response and prompt through
the same capability. It validates the count, kind and zero suffix before writing,
preserves every payload byte including NUL/non-ASCII values, stops at the first
failed output byte and never retries a command or committed update.

## Living component references

- [ByteBuffer](../docs/byte-buffer.md): logical size, capacity, failure-safe growth and readonly views
- [Binary records and sector I/O](../docs/storage.md): fixed records, copied sectors, runtime-capacity RAM device and scoped windows
- [UTF-8](../docs/utf8.md): strict scalar codecs, scalar ranges and line scanning
- [ASCII token scanner](../docs/token-scan.md): final-window copied token observations
- [JSON](../docs/json.md): bounded validation, scalar/integer codecs, lookup and transactional string encoding/decoding
- [Package metadata](../docs/packages.md): identity, manifest grammar and catalog ordering
- [Offline XFS](../docs/xfs.md): narrow integrity/geometry/directory/file interpretation
- `console.file_namespace` is the canonical typed four-record owner, immediately
  used by the ordinary and protected console adapters without command parsing or
  reply presentation in its core; protected storage remains supervisor-held.
- Named RAM files support atomic `append_file` and `append NAME TEXT` through the
  shared session/protected store, with a 49-byte total limit and no creation on missing names.
- Named RAM files also support atomic `copy_file` and `copy SOURCE DESTINATION`,
  preserving the source and replacing an existing destination even in a full store.
- [Console session policy](../docs/native-console-service.md): volatile note/named-file grammar, limits and lifetime
- [Protected command ledger](../docs/program-console-contract.md#shared-copied-command-ledger):
  `console.command_stream` owns copied bytes and request/reply/ack, read-terminal,
  finish/cancel and scrub transitions; native identity, run and publication authority stay private

The [runtime/library roadmap](../docs/library-stack.md) distinguishes freestanding,
kernel and user layers. A bounded `std.utf8_text` owner supports empty construction, checked initialization,
Unicode scalar append and readonly bytes. General strings/containers/algorithms, threading,
locale, process startup and persistent filesystem services remain open. A hosted
allocation pass is not native runtime or kernel qualification. Test scope follows
[development and qualification](../docs/developer-test-contract.md); use existing
oracles and complete byte observations, and report missing gates honestly.

The protected `tests/kernel-programs/call-snapshot-service.au` consumer uses
`std.checksum` to compute CRC32C over a bounded readonly copied RAM snapshot.
Its caller resumes through the sealed CallSession into live Aurora locals; the
integer request carries no pointer or file authority.

## Owned UTF-8 text

The `std.utf8_text` module exports `std::Utf8Text`. Construct it with an explicit region and moved `OwnedBytes`;
allocation contents start hidden and logical text is empty. Check `ok()` before
borrowing. `try_initialize(span)` accepts only empty text, validates final UTF-8,
and copies it transactionally. Successful empty initialization may repeat.
`try_append_scalar(u64)` uses the existing checked UTF-8 encoder. Recoverable
failures preserve bytes, length, capacity and committed region accounting.

`bytes()` exposes only a readonly logical prefix tied to the owner lifetime;
live views prevent mutation or movement. There is no mutable-byte access,
substring owner, normalization, locale or general string API. Direct OwnedBytes
storage deliberately duplicates the small ByteBuffer reserve/commit mechanism
because nested owning fields remain unsupported; encoding/validation is shared.

`std::append_json_text(output, text)` returns `JsonStringAppendStatus`. It reserves
one complete output transaction, reuses ASCII escaping and copies valid UTF-8
bytes without revalidation. A private singleton borrow helper supplies bytes
within the existing multi-owner rules; no span escapes that helper. The existing
JSON string example uses this API. Hosted allocation is not protected userspace
allocation or filesystem authority.

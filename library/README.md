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
- [JSON](../docs/json.md): bounded validation, scalar/integer codecs, lookup and transactional string append
- [Package metadata](../docs/packages.md): identity, manifest grammar and catalog ordering
- [Offline XFS](../docs/xfs.md): narrow integrity/geometry/directory/file interpretation
- [Console session policy](../docs/native-console-service.md): volatile note/named-file grammar, limits and lifetime
- [Protected command ledger](../docs/program-console-contract.md#shared-copied-command-ledger):
  `console.command_stream` owns copied bytes and request/reply/ack, read-terminal,
  finish/cancel and scrub transitions; native identity, run and publication authority stay private

The [runtime/library roadmap](../docs/library-stack.md) distinguishes freestanding,
kernel and user layers. Owned strings, general containers/algorithms, threading,
locale, process startup and persistent filesystem services remain open. A hosted
allocation pass is not native runtime or kernel qualification. Test scope follows
[development and qualification](../docs/developer-test-contract.md); use existing
oracles and complete byte observations, and report missing gates honestly.

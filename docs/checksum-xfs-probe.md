# CRC32C and a bounded XFS header probe

This library candidate uses the unchanged milestone014 compiler and its
readonly whole-array byte spans. It adds original Aurora implementations of a
recoverable checksum and a small 512-byte header probe. It performs no I/O,
heap allocation, mounting, journal replay or writes to the borrowed input. It changes no compiler
grammar, kernel or driver.

The acceptance gate is native execution against independent checksum and binary
field oracles, including signed range extremes, split checksums, malformed
headers and input preservation, followed by independent review. A successful
compile or one fixture does not establish that this gate passed. See the package's
test evidence for the actual verification status.

## Checksum API

`import std.checksum;` exports these Aurora-specific names in namespace `std`:

```text
enum class ChecksumStatus { success, out_of_range, invalid_previous };

ChecksumResult(ChecksumStatus status, u64 number)
ChecksumResult.status() const -> ChecksumStatus
ChecksumResult.value_or(u64 fallback) const -> u64

crc32c(builtin::span<const u8> bytes, i64 offset, i64 count) -> ChecksumResult
crc32c_extend(u64 previous_finalized, builtin::span<const u8> bytes,
              i64 offset, i64 count) -> ChecksumResult
```

`ChecksumResult` is an independent copied value with private fields. `value_or`
returns the stored value only for `success`; either error returns the supplied
fallback, including for an error report publicly constructed with a nonzero
payload. Arguments, including the fallback, are evaluated eagerly under the
ordinary language rules. A public result constructor is a report constructor,
not a validation certificate: a caller can construct a success report containing
an arbitrary u64. Every successful result produced by these checksum functions
is in the range 0 through 4294967295.

Both functions process exactly `count` bytes beginning at `offset`. Validation
precedes all byte reads. `crc32c_extend` first rejects `previous_finalized` above
4294967295 as `invalid_previous`, including when the requested range is empty or
also invalid. Range validation then checks, in order:

1. `offset >= 0`;
2. `count >= 0`;
3. `offset <= bytes.size()`;
4. `count <= bytes.size() - offset`.

Failure at any range check produces `out_of_range`. The checks do not compute
`offset + count`, so extreme signed inputs cannot overflow validation arithmetic.
An empty range is valid at every offset from zero through the span's length,
inclusive. A span remains a readonly whole-array borrow; allowing a zero count
does not add empty-array construction or a subspan operation to the language.

The checksum is reflected Castagnoli CRC32C, using the reflected polynomial
0x82f63b78 (decimal 2197175160), a 32-bit all-ones seed, and a 32-bit all-ones
final XOR. The recurrence uses u64 shifts and XORs while preserving a 32-bit
remainder. There is no u32 type, unsigned wraparound or full-width complement.
`crc32c` is `crc32c_extend(0, bytes, offset, count)`.

`crc32c_extend` takes the previous *finalized* checksum. It removes the final XOR,
processes the new bytes, and applies the same final XOR again. Consequently:

- CRC32C of an empty range is zero.
- Extending any valid prior checksum with an empty range returns that prior value.
- Extending the checksum of A with B equals the checksum of A followed by B.
- ASCII `123456789` has checksum 0xe3069283 (decimal 3808858755).

The implementation is a straightforward eight-bit-steps-per-byte recurrence. It
does not allocate heap storage or copy the borrowed input. Ordinary function and checked-span
access overhead remains; there is no throughput or equivalent-C performance claim.
CRC32C detects accidental corruption within its limits. It is not authentication,
a cryptographic integrity guarantee, or evidence that an input is trustworthy.

## XFS probe API

`import fs.xfs_probe;` exports these names in namespace `fs`:

```text
enum class XfsProbeStatus {
    wrong_length, unrecognized, unsupported_profile, checksum_mismatch,
    header_integrity_valid
};

XfsProbeResult(XfsProbeStatus status, u64 compat_bits, u64 ro_compat_bits,
               u64 incompat_bits, u64 log_incompat_bits)
XfsProbeResult.status() const -> XfsProbeStatus
XfsProbeResult.features_compat() const -> u64
XfsProbeResult.features_ro_compat() const -> u64
XfsProbeResult.features_incompat() const -> u64
XfsProbeResult.features_log_incompat() const -> u64

probe_xfs_v5_512(builtin::span<const u8> bytes) -> XfsProbeResult
```

The report and its four scalar observations are copied. It stores no span and
confers no capability. Its public constructor permits arbitrary reports; a status
alone is not proof that the function inspected any bytes.

The function checks the following conditions in order and stops on failure:

| Condition | Failure status |
|---|---|
| Input length is exactly 512 bytes | `wrong_length` |
| Big-endian u32 at byte 0 is 0x58465342 (`XFSB`) | `unrecognized` |
| Low four bits of big-endian u16 at byte 100 equal 5 | `unsupported_profile` |
| Big-endian u16 at byte 102 equals 512 | `unsupported_profile` |
| Byte 121 equals 9, the sector-size logarithm for 512 bytes | `unsupported_profile` |
| Computed CRC equals little-endian u32 at byte 224 | `checksum_mismatch` |

Only after these checks does the function report `header_integrity_valid`.
Version bits above the low four are not interpreted or rejected. Lengths above
512 are rejected rather than silently checking a prefix. Other XFS sector sizes
are outside this deliberately narrow profile.

Checksum coverage is the complete 512-byte input, including the bytes after the
defined superblock fields. Bytes 224 through 227 are treated as four zero bytes.
The implementation obtains the same CRC without mutating or copying the input:

1. `crc32c(bytes, 0, 224)` processes bytes 0 through 223.
2. `crc32c_extend(prefix, borrow_bytes(local_four_zeros), 0, 4)` inserts the zeros.
3. `crc32c_extend(zeroed, bytes, 228, 284)` processes bytes 228 through 511.

The stored checksum at 224 is decoded little-endian, independently of the
big-endian fields around it. The preceding exact-length check establishes every
fixed reader and checksum range. The checksum API cannot report a range or prior
error for those fixed calls when its stated contract holds.

After length and magic match, the result preserves four raw big-endian u32
observations, widened to u64:

| Accessor | Byte offset |
|---|---:|
| `features_compat()` | 208 |
| `features_ro_compat()` | 212 |
| `features_incompat()` | 216 |
| `features_log_incompat()` | 220 |

`wrong_length` and `unrecognized` results contain zero for all four observations.
Other results contain the raw field values, even for an unsupported version or a
checksum mismatch. Such values are untrusted diagnostic observations. The
function neither interprets their bits nor decides feature compatibility. All
bit patterns are preserved, and none changes the result by itself.

`header_integrity_valid` means only that this bounded profile and its CRC matched.
It does not mean the superblock is valid under the full XFS specification, that
the filesystem is supported or mountable, that geometry or metadata relationships
are consistent, that a log is clean, or that replay, recovery, writable access,
or durability is safe. Feature support, geometry checks, device size, UUIDs,
allocation groups, log state and all other filesystem acceptance conditions
remain outside this API. A deliberately recomputed CRC can accompany arbitrary
or malicious contents; the status must never authorize filesystem use.

## Pinned format reference

Field facts were checked against Linux v6.16, exact commit
`038d61fd642278bab63ee8ef722c50d10ab01e8f`. The source is a format/reference
resource only. No upstream implementation code is copied into this package.

- [xfs_format.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_format.h)
  has blob SHA `9566a76233654004d54f47aac17ac60dd8a6629a`. Magic and the
  low-four-bit version mask are at lines 29 through 35. `XFSLABEL_MAX` is 12 at
  line 90. The disk fields begin at line 193; version, sector size and inode
  fields occupy bytes 100 through 107, the twelve-byte name occupies 108 through
  119, blocklog is byte 120, and sectlog is byte 121. The feature fields and
  little-endian checksum follow at their documented disk offsets.
- [xfs_cksum.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_cksum.h)
  has blob SHA `999a290cfd722b306c9944a61b8eeb4516f31b86`. The reference
  describes the all-ones seed, zeroed checksum field, finalized complement and
  little-endian storage.
- [xfs_buf.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_buf.h)
  passes the complete buffer length to checksum verification;
  [xfs_mount.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_mount.c)
  rereads using the declared sector size. The exact-512 restriction here is a
  local probe restriction, not a claim that XFS requires all sectors to be 512.

The package provenance records the coherent reference set and immutable compiler
identity. Native tests exercise this original library implementation rather than
calling the Linux implementation or mounting a filesystem.

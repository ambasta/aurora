# Isolated storage-library validation

This is library development against the immutable corrected M014 compiler.
No compiler source, grammar, ABI, kernel or shared image was changed.
`baseline-m014.json` records copied input hashes before edits; integration must
apply and review the library/test delta, preserving any later main-branch work.

Compiler identities are in `../compiler-provenance.json`. The instrumented
compiler was built for M014 with C++23, `-O1 -g`, address/undefined-behavior
sanitizers, frame pointers, nonrecovering sanitizer errors and strict warnings.
Runs here use `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. This instruments the
host compiler. Generated native Aurora code retains its normal checked
operations; it is not ASan-instrumented machine code. No leak-sanitizer or general
resource-bound claim is made.

The 16 copied baseline source/native suites run individually with each compiler:
run, classes, value_calls, templates, fixed_containers, composed_values,
decimal_values, enum_composition, integers, unsigned, u8_numeric, byte_codec,
packed_values, readonly_spans, unsigned_oracle and integer_oracle.
This is not a rerun of compiler-internal IR, host-I/O, module-loader or kernel
suites. Those components have no implementation changes in this workspace.

Release baseline aggregate passed (40.29 seconds), and the same 16 suites
passed through the instrumented compiler (88.74 seconds). These elapsed times
are run receipts, not controlled performance comparisons. The new storage_fields example
returns42 with both compilers, verifying CRC32C("123456789") and a BE64 field.
Exact native execution receipts are in the development receipt set; new-library author acceptance passed as listed below. Independent source, functional and offline-fixture review passed; the full
report is `independent-storage-review.md`.

## New-library author results

The test is `tests/compiler/storage_binary.py`; its frozen input identity is
recorded in `candidate-inputs.json`. Run it with the immutable compiler path.
The normal-polynomial GF(2) reference is independent of the source recurrence.
The harness self-test also passed under `python3 -O`.

- Default seed15015/random-count8: 254 native cases and 1,186 API calls, passing
  with both release and address/undefined-behavior instrumented compilers.
- Alternate seed20261003/random-count16: 254 native cases and 1,478 API calls,
  passing with the release compiler.
- Every run has 91 endian, 107 CRC and 56 XFS native cases. API call totals count
  operations within cases and overlap the case counts; these are not additional
  independent tests.
- Six fixed CRC vectors, split continuation, full-u64 decoding, signed range
  errors, prior-checksum range checks, input byte comparisons and the documented
  XFS recognition/integrity distinctions are exercised.

Exact command lines and author receipts are in `evidence/storage-library`.
These 56 XFS cases use synthetic headers. Additional real mkfs-generated header
coverage is recorded below.

## Real offline header fixture

`docs/offline-xfs-fixture.md` records the official Debian xfsprogs6.13.0 packages,
locally extracted executables, loaded dependencies, sparse regular-file creation
command and read-only xfs_db observations. No filesystem was mounted and no
physical device was accessed. Only the first512 bytes are retained in the source
artifact tree; the larger disposable image and extracted tools remain in /tmp.

The preserved header has SHA256
`55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586`.
The native driver passes15 observations with release, optimized-Python release,
and instrumented compilers. It verifies facts, complete-sector CRC, input bytes
and corruption responses. Its explicit guards remain active under python -O;
the initial assert-based guards were strengthened before final acceptance.

The first instrumented attempt omitted the established leak-sanitizer setting
and stopped under the environment's tracing before any native case ran. That
receipt is preserved; the successful rerun uses detect_leaks=0:halt_on_error=1.
The original single mkfs process exit code was not separately retained and is
marked unknown. The generated fixture, captured format output, read-only xfs_db
exit0 with correct CRC and independent native results are the retained evidence.
These observations do not claim a mounted or usable filesystem.

## Independent review

The independent report and separate receipts are in
`independent-storage-review.md` and `review-evidence/`:

- Alternate seed39059/random-count24: 254 native cases and1,702 API calls on each
  compiler; 64 additional cases on each, including arbitrary prior checksums,
  profile/feature distinctions, corruption and caller-constructed reports.
- Twelve separate real-fixture cases and the final15-observation CLI driver pass
  on both compiler pins.
- Ninety independent inputs through4096 bytes match the GF(2) model and hardware
  SSE4.2 CRC32C; this checks the oracle, not an Aurora performance claim.
- Read-only xfs_db verification and before/after whole-image hashes confirm the
  fixture remained unchanged during independent examination.

No unresolved library defect was reproduced. Case sets overlap; counts are
reported separately rather than summed into a coverage claim. Main Aurora
integration and parent acceptance remain pending explicit archive clearance.

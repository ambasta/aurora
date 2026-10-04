# Independent canonical-hex fixture transport review

Result: **PASS** for the pinned transport verifier and fixture. No blocking defect
was found. Review date: 2026-10-03. Scope was limited to the new canonical-hex
transport, its failure behavior, preserved raw identity, and replay of the existing
15 native fixture observations. This is not a repeat of the full library review.

## Exact identities

- `fixtures/xfs-offline/verify_native.py`:
  `f5a1d552b56f92c9e974b0e09e485613483a05a192e694ce2841f9f439547069`
- `fixtures/xfs-offline/superblock-v5-512.hex`, 1728 bytes:
  `d1d3fbc3f8b693d1c0ddf395e92b136a81b2a5d30b9e3cdec36addd580d42986`
- Preserved raw file, 512 bytes, at
  `/workspace/scratch/48c5de6446f8/aurora-fixture-originals/m015/superblock-v5-512.bin`:
  `55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586`
- Release compiler `/tmp/aurora-m014-compiler-corrected`:
  `2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`
- Sanitized compiler `/tmp/aurora-m014-compiler-corrected-sanitized`:
  `ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa`

The supplied workspace has no Git repository metadata discoverable by `git
status`. Content hashes, including all reused source files, identify this review.
`independent-run-summary.json` records before/after hashes and sizes for every
regular file in `fixtures/xfs-offline`, both compiler binaries, the preserved raw
file, the three library modules and the two native-runner sources. Every recorded
input remained unchanged. The former in-tree `.bin` path is absent.

## Static review

`read_fixture_hex` opens in binary mode and makes one `read(1729)` request. The
decoder then requires exactly 1728 bytes and 32 rows. Each row must contain a
four-digit lowercase hexadecimal offset, two ASCII spaces, sixteen two-digit
lowercase hexadecimal byte cells with single-space separators, and a final LF.
Offsets must equal the row index times 16. It requires exactly 512 decoded bytes,
then verifies the raw SHA256 and transport SHA256. Explicit `require` calls,
rather than Python assertions, enforce these guards under `-O`.

The native path reads only the canonical `.hex` beside the verifier; no `.bin`
fallback exists. No text decoder, replacement encoding or Unicode normalization
can turn malformed transport bytes into accepted bytes. Native compilation uses
the checked decoded byte sequence. No source code changes were necessary.

## Reproduced gates

All six invocations exited zero, with empty stderr:

| Invocation | Outcome |
|---|---|
| Transport self-tests, normal Python | 17 rejection controls passed |
| Transport self-tests, Python `-O` | 17 rejection controls passed |
| Release compiler, normal Python | 17 controls and 15 native observations passed |
| Release compiler, Python `-O` | 17 controls and 15 native observations passed |
| Sanitized compiler, normal Python | 17 controls and 15 native observations passed |
| Sanitized compiler, Python `-O` | 17 controls and 15 native observations passed |

The four native receipts have identical scalar output, expected/observed cases,
generated source and assembly hashes, fixture identities and reused source
hashes. Each records a normal zero exit with no terminal signal. The CRC result
is `0xb67113c7`, represented by bytes `c7 13 71 b6`; raw feature masks are
`0`, `0xf`, `0x2b`, `0`. Counts overlap across modes and must not be added as
independent semantic coverage.

Sanitized runs used exactly
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. Leak checking was disabled to match
the established environment setting. This instruments the compiler; the emitted
native fixture program is not itself sanitizer-instrumented.

Exact commands, environment additions, stdout, stderr, duration and exit status
are preserved in `independent-self-tests.log`,
`independent-self-tests-optimized.log`, `independent-release.log`,
`independent-release-optimized.log`, `independent-sanitized.log` and
`independent-sanitized-optimized.log`. Each native log names its separate
`independent-*.json` output receipt. No historical receipt was rewritten.

## Additional independent checks

The corner-check driver passed **17,604 checks in each Python mode**. These are
repeated normal/optimized executions of the same corpus, not 35,208 distinct
cases. Its explicit checks also survive `-O`.

- Independently reconstruct the canonical text from the preserved original raw
  bytes, and compare all 512 decoded bytes with that original.
- Reject all 15,360 one-nibble data alternatives: 1024 data-nibble positions times
  15 alternative hexadecimal values. Every case retains exact canonical syntax
  and size, and fails specifically at the decoded raw SHA256 guard.
- Reject a non-ASCII byte at each of the 1728 transport positions.
- Reject all 496 distinct row-pair swaps specifically at the row-offset guard.
- Reject uppercase text, CRLF/CR line endings, a UTF-8 BOM, UTF-16 in both byte
  orders, embedded NUL, trailing space, leading/duplicate newline, missing row
  newlines and raw binary content supplied as hex.
- Exercise each identity guard independently by changing only its expected
  constant in the temporary in-memory imported module. Production source files
  remain unchanged.
- Instrument the reader with an exact-input stream and an oversized stream.
  Both receive exactly one binary-mode open and exactly one 1729-byte read
  request; oversized data is rejected.
- Execute an isolated verifier copy with an adjacent valid old `.bin` fixture.
  Missing `.hex` and binary-content `.hex` both fail without printing a pass.
  Correct `.hex` succeeds. This proves the old raw path cannot rescue absent or
  malformed canonical transport in the exercised entry point.

See `independent-corners.json` and `independent-corners-optimized.json` for exact
category counts and rejection reasons. Drivers were kept under `/tmp`, as
requested:

```sh
python3 -B /tmp/aurora-m015-independent-transport-review.py
python3 -B /tmp/aurora-m015-independent-transport-corners.py
python3 -B -O /tmp/aurora-m015-independent-transport-corners.py
```

`independent-cross-checks.json` records their SHA256 values and host tools:
Python 3.12.14, Debian GCC 14.2.0-19, GNU assembler/linker/nm 2.44.

## Documentation and limits

An initially stale opening link in `docs/offline-xfs-fixture.md` still referenced
the removed in-tree `.bin`. The author corrected it during review to the existing
canonical `.hex` and explicitly referenced the externally preserved original.
The corrected text was re-read; this documentation nit is resolved.

This review did not edit the verifier, compiler, library, kernel or historical
receipts. It made no filesystem image, invoked no mkfs tool, mounted no device,
and ran no image build or emulator gate. It verifies the current preserved raw
bytes and recorded content identities; it does not independently witness the
historical file creation or rename operation. The existing provenance remains
historical evidence of those operations. Passing these transport checks does not
establish filesystem mounting, full XFS support or a general security proof.

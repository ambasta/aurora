> Historical checkpoint. These APIs were removed by the
> [storage consolidation](../storage-consolidation.md).

# Bounded writer focused results — 2026-10-07

The source adds only the owned writer library, its example and tests, the existing
compiler-test recipe entry and documentation. Compiler implementation and existing
codec/reader implementation files are unchanged from main `f458620b325c4f17c32b32c3c4a09b2771a472b8`.

## Executed gates

A reused, read-only compiler had SHA256
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298` before and after every gate.
This is an explicitly pinned focused run, not a fresh compiler build.

- `python -B tests/compiler/binary_writer.py <compiler>`: 278 native cases,
  eight compile rejections, three exact read-bounds traps and the record example.
- The same writer gate under `python -B -O`: the same complete checks passed.
- Existing `byte_codec.py`: 789 native cases, 19 rejections, packed-layout checks
  and the storage-field example passed.
- Existing `storage_binary.py` under `python -B -O`: 254 native cases and 1,186
  API calls passed, covering binary readers, CRC32C and the restricted XFS probe.

Writer cases compare all destination bytes to Python-produced vectors, including
all bytes immediately after failed operations in mixed sequences. Independent
byte expectations are primary; reader roundtrips are additional integration
checks. Offset precedence, both signed endpoints, value-width limits, overlapping
writes, copied argument/result storage, zero initialization, size and API
visibility/const/type restrictions are exercised.

All four commands and the outer launch exited zero. The immutable source map and
compiler identity matched at completion; owned child cleanup was quiescent after
every command. Elapsed child times were 2.131, 2.380, 1.718 and 12.155 seconds.
The sampled peak was 161,202,176 bytes including the launch allowance; the source
and run root peaked at 10,895,360 bytes. These are engineering observations,
not kernel-enforced aggregate resource quotas.

The frozen tested tree has 614 source files. Three existing candidate documents
receive result wording afterward, and this results document is added; no tested
implementation, example, Make recipe or test bytes change in that overlay.
Independent review accepted the implementation, test contract and focused
results. Publication is tracked separately.

## Deliberate limits

No full native aggregate, sanitizer, emulator or broad-host run was performed
for this leaf-library change. Historical results retain their exact prior-source
scope. No mutable borrowing, heap allocation, sector-sized buffer, filesystem
mount, NVMe operation, persistence or physical-machine support is established.
The per-call failure contract is not concurrent atomicity or durable storage.

## Incremental composition check

The writer was then composed on main
`55d84c85657c82ff5fcddbe9ad2211fabe93ef13` (tree
`b37fec080002d1b71ac40b9d2f0645b206d5b420`), preserving the Meson and console
changes. The 629-file composed tree
`8cd9f4c85eff383fe943c7faa0a5760809d8cbff` passed the complete focused writer
gate again: 278 native cases, eight rejections, three exact bounds traps and the
example, in 2.250 seconds. The compiler remained unchanged. The outer process
exited zero and owned cleanup was quiescent. Only this result paragraph was added
after that replay. Other earlier gates were not rerun for the unrelated join.

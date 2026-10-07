# Owned sector-sized values: focused results, 2026-10-07

The focused executable composite and independent final artifact review passed.
This is hosted compiler/value-boundary qualification, not a complete native
aggregate, sanitizer run, kernel admission or device/filesystem result.

## Exact scope and identities

Base: merged PR47 main `010767baf5a21b8f5e6dd97dbec21b48eac22298`, tree
`0b9f99b758de8e23b2e270aff54c6db69154e449`.
The executable test snapshot has tree
`02f8c10daf5071eb6bc053bbe30054aef1cac726` and SHA-256 source manifest
`eb4a2c0cb63cac00e604d7015195d6ee981fae81a3e7e89bdc4628da41358f6a`.
Later contract/results/completeness edits are documentation only.

Compiler SHA-256:
`1a4a8dbd67250c236b6cdd9216221d19b2af08d54593a4a923d95f088b18801d`.
Direct-IR/ABI fixture SHA-256:
`238766ae7bee610087385d14a91bd360c45ad2624c26feb8368e8ab82a11629c`.
Both use GCC 14.2.0 with C++23, O2, Wall, Wextra, Wpedantic and Werror.
No x86 emitter, IR instruction schema, template-capacity or initialization-fact
implementation changed. The [contract](../compiler/SECTOR-VALUES.md) defines the
separate byte/non-byte/leaf/padded-storage limits and intentional old-test changes.

The compiler built warning-clean in 40.262 seconds with observed peak RSS
724,880 KiB. The corrected standalone fixture built in 31.203 seconds with peak
RSS 632,736 KiB. Later continuations reused these exact binaries only after their
complete quoted source-input closures and binary hashes were verified. A test
fixture or controller change did not trigger an unrelated compiler rebuild.

## Passed executable gates

- `sector_values.py`: 17 full-width native cases, 21 source rejections and six
  exact bounds traps, repeated in normal and optimized Python modes. This includes
  all 512 payload bytes, closed status plus payload, zero-masked failure,
  constructor/function/method/generic/nested copies, evaluation ordering and all
  new exact limits. Source rejections preserve absent and preexisting output.
- `sector_values_ir.cpp`: 67 direct-IR cases, comprising 14 valid shapes/programs
  and 53 malformed-input rejections. These include independent canonical storage,
  closed enum identity, byte/non-byte/storage limits, incomplete final bytes,
  nominal identity, overlap, result freshness and checked-index evidence.
- `sector_values_abi.py`: all 21 independent native cases passed. Handwritten
  entry or exit sides check every status/payload byte, copied input isolation,
  six-report packing, hidden registers, odd-depth alignment, full results and
  corruption controls. Canaries cover the handwritten global input/result/
  receiver records; disjointness and exact addresses separately check generated
  outgoing storage. No claim is made that every generated local has a canary.
- Eleven existing source/native runners passed: classes, value_calls,
  fixed_containers, composed_values, method_values, nested_values,
  function_templates, packed_values, byte_codec, binary_writer and storage_binary.
  Existing 65-wide-leaf and non-byte/template-capacity negatives remain rejections.
- All 28 existing valid examples emitted byte-identical assembly against the
  exact PR47 compiler `fa426eb231c90e32a9739b46b8398d46aa3e0031e8270ca54323878e68772ef2`.
  Both compilers had to succeed without diagnostics. Library and required
  kernel-policy module roots were explicit, and all example/module bytes matched
  the base. New sector-only programs were excluded from this comparison.

These case counts overlap different representations and replay modes; they are
not additive proof counts. Existing complete direct-IR/method-ABI suites, full
compiler/root aggregates, host sanitizers and QEMU were not rerun.

## Measured emitted stack reservations

The ABI runner reads actual emitted prologues, hidden saves and outgoing stack
adjustments and checks them against independent literal fixture expectations.
It records exact finite-fixture stack sums, not runtime high-water instrumentation
or a bound on arbitrary user programs.

- A single 512-byte Block uses a 512-byte packed argument record. Its measured
  generated caller/callee chain is 2,128 bytes including rbp/return addresses.
- Six maximum 520-byte reports use a 3,120-byte packed argument record, not
  24,624 bytes from treating all 3,078 logical leaves as eight-byte slots.
  Callee parameter storage is another
  3,120 bytes. Ordinary/constructor prologues reserve 3,136 bytes; a combined
  copied-result method reserves 3,152 bytes, including 32 hidden bytes.
- The generated six-report caller/callee chain is 9,968 bytes for ordinary and
  constructor modes and 9,984 bytes for the combined method. The caller retains
  one scalar operand and an eight-byte alignment adjustment in these fixtures.
- Returns fill existing caller destinations and allocate no separate result
  record. Additional nesting retains each caller's reservations.

The unchanged 65,536-byte source-frame limit is only a compiler resource limit.
Ordinary recursion has no finite global stack bound. Kernel integration needs
separate admission against its smaller stacks and guards; these hosted results
never change kernel limits or authorize recursive large kernel calls.

## Retained failures and the accepted composite

The first source-only review corrected an unexecuted ABI fixture whose success
and failure blocks had inconsistent linear-emission operand depth. Both paths
now keep the sentinel until a shared merge/consume; the verifier was unchanged.
The source runner also gained a retained work directory and failure preservation.

Three executed unsuccessful attempts remain distinct from the passing components:

1. The compiler build passed, but the fixture build failed Werror because one
   structured-binding loop copied a pair. Changing only `const auto` to
   `const auto&` fixed the fixture warning; Werror remained enabled.
2. The corrected fixture and both source modes plus direct IR passed, but the
   128 MiB output estimate was insufficient for all retained ABI assembly,
   objects and executables. The controller stopped the gate after 20 of 21
   cases, with a sampled retained size of 137,723,904 bytes. That gate is failed.
3. An explicitly approved fresh 256 MiB continuation completed all 21 unchanged
   ABI cases, retaining 138,444,800 bytes including its later partial controller
   state. The following first legacy suite hit a controller FileNotFoundError
   when its temporary file disappeared during live output accounting. The
   controller failed and stopped that process group; no legacy pass is inferred.

The controller was narrowly corrected to ignore only entries vanishing during
live sampling. A compiler-free control verifies other I/O errors remain fatal.
A fresh continuation then passed all eleven pending regressions without repeating
the completed ABI gate. The final differential imported that corrected sampler.
Strict terminal inventories subsequently hashed all retained files without
ignoring missing entries and checked stable identity, size and modification time.
Original failure roots and receipts were not rewritten or relabeled as passes.

Each build retained 2 GiB address-space, 120/130-second CPU, 180-second wall,
32 MiB per-file and zero-core limits. Later runs retained these limits; only the
fresh ABI output allowance was explicitly changed from 128 to 256 MiB after
measuring the complete-artifact cost. Fresh shared memory/free-space admission
preceded continuations. The complete composite, original failures, stack JSON,
strict inventories and binary/source joins are retained with the dated handoff.

## PR49 joined consumer check

The reviewed value change was composed with current PR49 main
`61fa3d30158a107ef04f40f3c2c41b8210664854`, preserving its package profiles,
formatter/overlay support, storage modules and Make/Meson registrations. The
joined executable tree was `2022ba92810c6581b7ac76fe0b0a3b4c1175c20d`, with
manifest `3c01493fa9256bca9d7c86d97f521b63d38b81d789aad3c73cc5940b853038f3`.
All 16 compiler source inputs and three sector-test inputs matched the accepted
focused candidate. Final result wording after this check is documentation only.

One fresh serialized Meson build produced the compiler, initialization-fact test
and both codec/RAM example assemblies. The joined Meson compiler is separately
identified by SHA-256
`e97baada523ec30ac49e7f3e4c17b13ae6d30b79d9f157f07f9a87c2bd4ab8ba`.
All 17 current-main dev tests passed with two workers in 39.70 seconds, including
RAM/block-value and all three named package developer profiles. Those package
profiles remain deliberately partial. All 20 registrations were present; the
three previously completed, input-identical sector gates were explicitly
excluded from this dependency replay and their fixture was not rebuilt.

The fresh formatter compatibility target also passed 81 corpus sources,
128 trivia variants and 30 CLI cases. Native commands all exited zero, but the
outer post-run audit initially expected bare test names rather than Meson's
suite/project-qualified names. That outer exit 1 is preserved. A read-only
correction using the already established PR49 interpretation checked every exact
qualified registration, actual command and successful result; no native test was
rerun or retrospectively relabeled. Independent joined evidence review passed.

Entry admission required 7.5 GiB available memory and 1 GiB free disk. The owned
output cap remained 256 MiB, builds were serialized, and compiler/test children
kept 2 GiB address-space, 120/130-second CPU, 32 MiB file and zero-core limits.
The reused controller applied a 180-second per-command wall envelope. No root
aggregate, emulator, sanitizer or new kernel admission was added.

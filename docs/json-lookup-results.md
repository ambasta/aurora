# Bounded JSON lookup: focused qualification (2026-10-08)

Status: fresh focused source/native gates and independent raw-evidence review
passed. Final publication reconciles a documentation-only qualification overlay;
no implementation bytes changed after the passing gates.

## Scope and identities

The library-only increment adds decoded-name root-member and root-array-index
lookup through one shared iterative validator. Complete document validation wins
over every candidate; matching decoded duplicate names report ambiguity. No DOM,
new compiler semantics, stored borrow, buffer abstraction, host JSON replacement
or measured-performance claim is made. The [contract](json-lookup.md) fixes limits,
error precedence, copied-result shape and lifetime boundaries.

Base is PR83 main `ec8cfe43d3cc31a4eb71ff4a892bb71907d1a974`, following accepted
numeric PR82. All compiler implementation files, the original scanner/scalar/numeric mechanisms
and other standard-library implementation files remain unchanged. Independent
source comparison verifies the validator's grammar/stack/statistics core is
unchanged after only failure-report packaging and optional observation are removed.

- Selected unchanged compiler SHA256:
  `512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`
- `library/std/json.au`:
  `a4167ae4208eaab926efc927e6903094d9a8fbdcd44cdb7b70e767b8482360c5`
- `library/examples/json_lookup.au`:
  `7a7eadae9da104a97a8ed8e4f15257c75e67444d84a806335390cb156ced2473`
- `tests/compiler/json_lookup.py`:
  `8d23a19b631228639aa3928d12690fb23e8a58573a9cfb283c8b301984d43f33`

## Completed direct gates

Fresh normal and optimized Python runs each passed 4,996 cases, 25,020 complete
64-bit observations, 320 batches, 67 source/type/privacy/lifetime rejection
controls and 211 hosted owner/example observations with exact cleanup. Independent
raw audits decoded every native stdout field and checked retained source/output
hashes, rejection exits/diagnostics, hosted cleanup identities and compiler/input
stability. Ordered object pairs preserve duplicates; independent byte ranges are
checked against decoded selected slices. No native semantic-mutant coverage is
claimed; 51 compiler-free comparator controls separately passed.

The actual ByteBuffer example exposes every nested extent and Unicode scalar,
including NUL and a surrogate pair, through the same live input span. Hosted
checks include real 8,193-byte sources and queries, hidden truncated document
suffixes and UTF-8 continuations, logical-capacity separation, copied observations
after owner mutation/destruction, later-argument borrow rejection, and allocation
failure/cleanup. Result shapes include full-width coordinates and overflow edges.

Original regressions on these exact formatted library bytes passed in both modes:

- JSON profile: 2,111 cases, 10,768 observations, 60 rejections per mode.
- Scalar codecs: 1,942 cases, 19,781 observations, 53 rejections and 431 hosted
  checks per mode.
- Integer codecs: 4,687 cases, 91,079 observations, 88 rejections and 407 hosted
  checks per mode.
- Owned JSON: 16 programs, 230 native observations, 23 report vectors,
  six rejections and two exact hosted bounds aborts per mode.

Direct lookup commands used `python3 -B tests/compiler/json_lookup.py COMPILER
--compiler-sha256 DIGEST --artifacts FRESH_DIRECTORY`, repeated with `-O`.
Normal lookup manifest SHA256 is
`2e6c2acbc0bcee5e103e0bcad905c80ec2f1143566ce479fc4aa9a8f65f6af57`;
optimized is
`ff7f678d59ecff595142951d6cc9a0e6e93b34bf687066a535f2d09a00c835c6`.

## Public routing and acceptance

`make -C compiler test-json-lookup` passed with explicit
ACCEPTANCE_COMPILER/ACCEPTANCE_COMPILER_SHA256 controls. Its run-owned compiler
was copied from the selected artifact: zero bootstrap builds, focused scope,
`native_complete=false`. All 395 gate compiler invocations targeted that owned
copy. The public gate repeated the complete optimized lookup corpus and hosted
checks. Supervisor terminal SHA256:
`03b648122480497a58b7d7e835bb3c104d3a843aca11ddfe849e23532dcab74d`.

Fresh Meson configuration/introspection verified bytes/dev registration and all
six transitive example module dependencies; this is not a Meson native-suite
run. Independent review verified all 717 supervisor source inputs and all 865
pre-public manifest files before the final documentation-only overlay. Selected
tools were Python 3.12.14, GCC 14.2.0, GNU binutils 2.44, GNU Make 4.4.1 and Meson
1.12.1. Public dispatch/context/aggregate routing, source masking/lifetimes,
independent oracles and every retained lookup observation received separate
source and raw-evidence review.

## Preserved failures and limits

Initial admission attempts exposed existing reserved-name, six-parameter and
named-copied-result rules; source was corrected without compiler changes.
The first full native corpus passed all fields, then a negative fixture expected
"unknown" instead of the correct "private type is not imported". Two fixture
replays corrected the precise owner-move diagnostic and replaced an unsupported
copied-aggregate resource-function return with supported nested-scope owner
expiry. Fresh complete final modes replaced no historical evidence. The initial
independent receipt auditor needed diagnostic-case normalization matching the
harness; its original attempt remains retained and was not a native failure.
The first Meson setup could not find Ninja with only the absolute Meson binary;
a fresh setup using the existing tool environment PATH passed. No installation
or source change was needed, and both setup attempts remain retained.

Original failed attempts, generated sources, complete observations, manifests and
independent review reports remain in retained external evidence, not repository
log dumps. Early PR84 and its source backup were explicitly unverified checkpoints.

This is focused source/native/library qualification, not a fresh full-native
aggregate, sanitizer, emulator, hardware, kernel-stack, speed or production-safety
qualification. The compiler is an independently selected existing artifact, not
a freshly rebuilt bootstrap compiler. Copied coordinates certify neither source
identity nor the continued validity of mutable storage.

# Independent XFS header geometry review

Result: **PASS for the reviewed pure-library scope. No blocking implementation defect found.**

Reviewed module: `aurora-xfs-geometry-next/library/fs/xfs_geometry.au`, SHA256
`c67c03928e0d4cf5896178906bd447523ec15b57cc95c4ade8b8330305a77864`.
The implementer explicitly froze this source before the full native runs. The
module hash was checked after each successful native batch and again at review
completion. This verdict does not replace the author's complete aggregate gate
or a later exact-source integration gate.

## Scope and preserved baseline

- Original proposal SHA256:
  `40021cf66fba001094c9f0762475075967b64bd4f55b8be845490ddf37fc5b86`.
- Existing `fs.xfs_probe` remains byte-identical, SHA256
  `9474dceea9c3dda66d5566396480e88979c6ea28c8d857b944f24e2e70603284`.
- No compiler implementation changes. Every copied compiler source present in
  the isolated candidate matches main. The candidate contains no kernel tree.
- All 4,954 main-tree non-build files in the before/after snapshot are unchanged:
  no additions, removals or modified bytes. This snapshot excludes `build` and
  `.git`; it is not a claim about unrecorded build artifacts.
- Reviewer outputs and deliberately corrupted mutation copies are private to
  this review directory. Main and candidate source were never mutated by review.
- No disk/device/image mounts, formatting, new mkfs, repair, log replay, driver
  access, raw-pointer API or C implementation port were used.

## Exact primary sources

Read-only GitHub retrieval pinned to Linux v6.16 commit
`038d61fd642278bab63ee8ef722c50d10ab01e8f`, 2026-10-03. Each local research file's
Git blob hash was independently recomputed from the complete bytes.

| File | Git blob SHA |
|---|---|
| fs/xfs/libxfs/xfs_format.h | 9566a76233654004d54f47aac17ac60dd8a6629a |
| fs/xfs/libxfs/xfs_sb.c | 711e180f9ebb835296afda1949f320d3425ecca6 |
| fs/xfs/libxfs/xfs_types.h | f6f4f2d4b5dbf50012d0041cc6685421a3e2e07b |
| fs/xfs/libxfs/xfs_fs.h | 12463ba766da053530e19b34c6a8344c67da3cd8 |
| fs/xfs/libxfs/xfs_ag.c | e6ba914f6d060711806cd60d9e6a77c6c02b835b |
| fs/xfs/libxfs/xfs_types.c | 1faf04204c5ddca5f45ff00c5dfaf893b5848b1c |
| fs/xfs/xfs_log.c | 793468b4d30d42dc368602770be97eda424919cc |

Source URL prefix:
https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/

`SOURCE-REVIEW.md` records specific line ranges and conclusions;
`evidence/sources.json` records verified complete-file identities. These upstream
files are research references only and are not target-library implementation.

## Contract clarifications resolved before native acceptance

The original proposal was not rewritten. The separate candidate contract pins:

1. Required version bits, required features2 bits, excluded version bits, excluded
   features2 bits, NEEDSREPAIR, then other extended feature exclusions/missing
   FTYPE. Complete diagnostics are computed even when an earlier error wins.
2. `imax_pct` / `shared_vn` are `inconsistent_header/misc_geometry` after log
   geometry and before success.
3. Present SECTORBIT: every pair other than512/9 is
   `unsupported_layout/log_geometry`. Absent SECTORBIT: a nonzero pair is
   `inconsistent_header/log_geometry`. The present-bit rule intentionally performs
   profile admission, not a general scalar-coherence diagnosis of excluded pairs.
4. Guards redundant under prior u32/range invariants are source-audited; no claim
   is made that deleting each such guard can be killed by a fixed512 input.

The reviewer initially recommended distinguishing coherent/noncoherent excluded
log-sector pairs. The final parent-selected blanket profile rule is explicit,
consistent and not a blocking issue within this limited API.

## Independent native/oracle result

Two runs passed the **same 2,016 byte-distinct input cases**. This is not4,032
unique cases. Corpus seed:193706. Deduplication occurs on complete input bytes;
all descriptive aliases are retained. Pilot and repeated runs do not increase
coverage counts.

| Compiler | SHA256 | Result |
|---|---|---|
| release | 14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980 | 2,016/2,016, no mismatch or fault |
| ASan/UBSan bootstrap | 805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf | 2,016/2,016, no mismatch or fault |

Of the2,016 inputs,451 produce the narrow success status and1,565 produce a
recoverable failure. Exactly one input is the preserved real mkfs header;450
other admitted inputs are synthetic header variations, not real filesystems.
The remaining inputs are synthetic mutations or malformed lengths. The corpus
includes8 `size_unrepresentable` cases and all old probe outcomes. Native lengths
are1,224,264,511,512,513,1024 and4096; no claim is made for a native empty span,
which the current nonempty fixed-array construction does not expose.

For every input the freestanding observer records all42 report leaves as full
64-bit results, plus repeated-call status equality and report size336. Closed
status/issue/probe enums are compared by named predicates rather than assuming
numeric enum representation. Exact input equality is checked after repeated
calls. No trap, signal, nonzero process exit, timeout or compiler error counts
as an acceptable malformed-header response.

The schema/math oracle was authored before reading the candidate implementation
and imports none of the author's tests. It uses Python unbounded integers and a
whole-message GF(2) CRC32C calculation; ceiling uses mathematical `(D+A-1)//A`,
independent of the production overflow-avoiding quotient/remainder expression.
The GF(2) known-answer vector and canonical fixture CRC were checked. Expected
outputs cover raw observations, every unsupported/unknown mask and every fact;
failure facts are all zero.

### Distinct coverage

- Canonical raw/transport hashes and all24 canonical geometry facts.
- Every admitted block/inode exponent pair, directory endpoints, inode==block,
  zero sparse alignment including expected full-chunk alignment0, SECTORBIT
  absence/presence and logsunit0/1.
- Non-power-of-two AGs including encoded addresses greater than D but valid under
  AG-relative decoding, encoded gaps, first/last AGs, short tails64/A-1/A and
  maximum nominal AG byte sizes.
- U64_MAX counts and encoded addresses, quotient/u32 overflow boundaries, exact
  data-byte representability boundary and the proposal's huge consistent witness.
- Every bit of every extended mask, high bits, required/excluded legacy features,
  required features2, mirror mismatch, NEEDSREPAIR and pairwise first-error faults.
- Block/inode/log exponents63/64/255, wrong scalar pairs, zero divisors, directory
  limits, realtime-zero contradictions, stripes, quota and miscellaneous bytes.
- AG-header-sector boundaries for every block exponent, same-AG and whole-data
  range endpoints, last-AG shortening and maximum log count/byte boundaries.
- Nonzero rt inode numbers remain uninterpreted and accepted where other fields
  pass. Repaired mutations of other uninterpreted bytes are not newly rejected.
- Deterministic hostile field samples with paired unrepaired-CRC variants.

Full expectations, input bytes and aliases:
`evidence/native-release/corpus.json`, SHA256
`9a26058f4a178298729ff12ce7c5819dfe9601eee1ffbd41d2735e47f81a34fa`.
Both compiler runs retain generated source, assembly, binaries and raw stdout by
batch. `evidence/corpus-summary.json` gives disjoint status/issue counts.

## API, layout and lifetime checks

Both compiler pins pass:

- A complete report returned beyond the lifetime of its local input array;
  independent copied projections reproduce all42 leaves afterward.
- Static and actual native runtime metadata for10 public classes. Report336
  bytes =42 scalar leaves; facts192 bytes; all exposed field counts0. The source
  containment tree has depth3 and constructors have at most6 parameters.
- Eight distinct rejection fixtures, each exercised with absent and pre-existing
  output artifacts. Specific diagnostics are checked. Direct private builder,
  validator type and zero-helper access reject; private report/fact access,
  missing direct `fs.xfs_probe` import, span storage and span escape reject.
- Fabricated success reports preserve arbitrary high-bit copied facts and can
  contain an invalid nested probe: success remains plain data, not authority.
  Fabricated non-success reports mask all24 facts to zero as documented.

The re-read builder is private and reached only after both checks succeed on the
same unchanged readonly span. This is safe within the current owned-array borrow
subset, with no callback or mutation in between. It is not an assertion about
asynchronously mutable or device-backed memory. No span is stored in a result.

## Arithmetic/source audit

Every dangerous operation is guarded before evaluation or dominated by a proved
prior invariant. Block/inode exponents are checked before shifts; directory
exponents are bounded using subtraction after blocklog<=16; A/N/D are nonzero
before divisors/subtractions; expected count is not narrowed; final-AG length is
checked before log decoding; AG shift is validated against bit_width(A-1) and<=30;
log AG stays u64 until checked; extent tests use subtraction before addition;
linear address and byte products have checked preconditions. Builder re-reads
only the already validated immutable fields.

Some explicit product guards cannot fail after earlier invariants: A and N are
u32, inode size<=2048, B<=65536, tailBase<=D, validated log range<=D. These are
retained source checks, not fabricated mutation kills. The bit-width loop is
bounded independently of the declared data or AG count.

## Independent mutation controls

Ten reviewer-created mutants in separate library copies were all detected:
encoded address used as linear; forgotten short-tail fact; ceiling changed to
floor; unknown extended bits admitted; removed data-product guard; removed shift
upper bound; removed sparse zero-divisor guard; ignored required legacy bits;
removed AG-header exclusion; removed same-AG extent bound.

The overflow, shift and division mutants terminate abnormally as intended and
are rejected by the observer. Those deliberate failures are negative controls,
not acceptable outcomes of the original module and not extra original-input
coverage. Exact mutant sources, input identities and outputs are retained in
`evidence/mutations/`; `result.json` identifies each changed source hash.

## Preserved existing probe/transport regression evidence

Independently reran the existing storage suite on each pin:254 native functional
cases /1,186 existing API calls pass. Independently reran canonical fixture
verification:15 native observations plus17 strict transport rejection controls
pass on each pin. These existing suite counts are separate from the new corpus
and are not added into a headline total. No original source or fixture changed.

## Failures and environment limits

The initial two instrumented baseline attempts failed during compiler invocation
because LeakSanitizer cannot operate under this environment's ptrace. Both full
failure logs and nonzero status files remain retained:
`old-storage-sanitized.log` and `old-fixture-sanitized.log`. No native case passed
in those attempts. Retrying disabled **only leak detection**:
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`, `UBSAN_OPTIONS=halt_on_error=1`.
The selected compiler binary and its frame-pointer/instrumentation settings did
not change. ASan/UBSan remain fatal. This is not leak-safety evidence.

The instrumented bootstrap compiler does not instrument generated Aurora code.
Native results are finite differential evidence, not an exhaustive no-trap proof,
Rust-equivalent safety proof, general compiler proof or performance claim.
Reviewer subprocesses have finite timeouts and disable core dumps in ordinary
runner execution; subprocess output pipes are captured and not memory-bounded
by a regular-file size limit. No address-space cap was installed or relaxed.

The author aggregate `make test` and any integration/emulator checks were not
run by this reviewer. Their results must be reported separately for their exact
source identities. This pure-library review does not expand kernel scope.

## Reproduction commands

From `/workspace/scratch/48c5de6446f8`, with output paths chosen not to overwrite
retained receipts:

```sh
ROOT=/workspace/scratch/48c5de6446f8/aurora-xfs-geometry-next
REVIEW=/workspace/scratch/48c5de6446f8/aurora-xfs-geometry-review
REL=/tmp/aurora-resource-main-compiler-frozen
SAN=/tmp/aurora-resource-sanitizer/aurorac
python3 -O "$REVIEW/review_native.py" --root "$ROOT" --compiler "$REL" \
  --compiler-sha 14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980 \
  --out "$REVIEW/evidence/native-release"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
python3 -O "$REVIEW/review_native.py" --root "$ROOT" --compiler "$SAN" \
  --compiler-sha 805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf \
  --out "$REVIEW/evidence/native-sanitized"
python3 -O "$REVIEW/review_api.py" --root "$ROOT" --compiler "$REL" \
  --out "$REVIEW/evidence/api-release-final"
python3 -O "$REVIEW/review_fabricated.py" --root "$ROOT" --compiler "$REL" \
  --out "$REVIEW/evidence/fabricated-release"
python3 -O "$REVIEW/review_mutations.py" --root "$ROOT" --compiler "$REL" \
  --out "$REVIEW/evidence/mutations"
PYTHONDONTWRITEBYTECODE=1 python3 -O aurora/tests/compiler/storage_binary.py "$REL"
PYTHONDONTWRITEBYTECODE=1 python3 -O aurora/fixtures/xfs-offline/verify_native.py \
  --compiler "$REL" \
  --compiler-sha256 14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980
```

The API/fabricated and existing baseline suites also ran with `$SAN` and the same
ASan/UBSan environment shown above. Python3.12.14; GNU assembler/linker2.44;
x86-64 Linux. Reviewer script, dependency, compiler and receipt hashes are in
`evidence/review-manifest.json`.

## Meaning of the result

The admitted status means only that the specified bounded header facts passed.
It does not mean mountable, clean log, read-only compatible, sufficient log
reservation, non-overlapping metadata allocation, valid secondary-header usage,
observed device size, active filesystem support or physical hardware support.
The canonical fixture's historical provenance limitations remain unchanged.

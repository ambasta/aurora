# Independent review: readonly `std.utf8`

## Disposition

**PASS, limited to the identified pure-library candidate and the evidence below.**
No implementation defect was reproduced and no implementation change was requested.
The author’s final stable-input regression aggregate is separately recorded as passed;
its receipt and input hashes were inspected after the independent runs. This does not
accept an entire compiler/kernel milestone or authorize main-tree integration.

Reviewed tree: `/workspace/scratch/48c5de6446f8/aurora-utf8-next`.
All review artifacts are separate in `/workspace/scratch/48c5de6446f8/aurora-utf8-review`.
The main `aurora` tree was not edited. The unrelated mutable-byte work was not inspected.
No publication, filesystem implementation, device, hardware or kernel action occurred.
The normal review harness necessarily writes its own local source and result artifacts.

Exact candidate identities:

- `library/std/utf8.au`: `6ad8d1c11ce26197932e2118151a7761e518ea2db7dc64a1fd1a3e956761f31c`
- Final `docs/utf8-contract.md`: `304b8467b2be396b5345a6f324d15d7e1eeabc28846c3986adb6d192f4f83bb5`
- Earlier reviewed contract snapshot: `77207e9eba469db28a8943317c1e92ea93a516212b0342a901ed67311314d131`; final prose appends acceptance evidence, not API changes.
- `candidate-inputs.json` (all 76 final files): `5f00a29b53e34e83b3f880574096dbebac5312d494081be71ede51e90a6b9dcc`
- `integration-delta.json`: `926870545174154f26f84234b139fc3626e8719306db28a0713d65be3192011d`
- `compiler/Makefile`: `514e1a6573adc3fe96eca24ec866f26219b928449d0d4afe6ec5b28818855513`
- Author test `tests/compiler/utf8.py`: `c30c913e6f5a81b724002a112acfdf7dc98b7c4dc4b9165f0a0999f005e9df84`
- `library/examples/utf8_scalars.au`: `fae18647e76acff29504fec0fb80dcc419e732952f9ef04b426c783b8eb93fed`
- `candidate-library.json`: `9d92d753fa964fbd90e9f33e3e9ee0c7f943b29033840432603dc84d85c8e5b5`
- Release compiler `/tmp/aurora-resource-main-compiler-frozen`: `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`
- Instrumented compiler `/tmp/aurora-resource-sanitizer/aurorac`: `805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf`

All 72 baseline files matched at the initial check. A final guard detected the
author’s expected `compiler/Makefile` change: UTF8_TEST_FLAGS, a full-test recipe
line and a dedicated test-utf8 target. The diff was inspected and the author
confirmed it. Exactly 71 old files remain identical; there is no compiler
implementation, syntax or mutable-span change. All 76 final files match
candidate-inputs.json. candidate-library.json is the earlier library snapshot.
Final review inputs and outputs are hashed in manifest.json.

## Primary reference and static review

Reference checked through the web tool on 2026-10-03:
[Unicode Standard 17.0.0, chapter 3, section 3.9.3, D92, Table 3-7](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/).
The version is pinned; the test oracle does not use assignment or Unicode-age data.

Source inspection confirms the nine permitted lead/continuation classes, including
the special second-byte bounds for E0, ED, F0 and F4. Shortest form follows from these
bounds; surrogates and values beyond U+10FFFF cannot pass. ASCII/NUL, unassigned
scalars, noncharacters and U+FEFF have no additional rejection or stripping path.

Both entry points check signed negatives before subtracting; then offset <= size and
count <= size-offset before loading. Current valid spans have bounded array lengths.
Each later offset/index is established inside the checked count. Scalar arithmetic
stays below 0x110000. Validator progress adds a complete width only after success;
its byte and scalar counters stay within the selected count. Empty decoder ranges
return end_of_input; empty validator ranges succeed in either final mode.

Available invalid continuation bytes are checked before a subsequent missing byte.
A proper partial scalar returns truncated or need_more, with zero decode width and
no partial-byte contribution to validator prefix/scalar counts. The API has no saved
state or mutation path; replay must include the retained incomplete prefix.

Public constructors create ordinary reports. Manual widths/counts can be negative,
oversized or inconsistent and are not certificates. `scalar_or` additionally masks
manual surrogate/out-of-range payloads; an arbitrary fallback remains arbitrary data.
Private fields and unexported helpers are inaccessible. There is no validated-string,
normalization, grapheme, path, locale or text-rendering authority here.

## Independent native corpus

`review.py` does not import the author’s UTF-8 test module or translate the candidate
branches. The oracle uses Python’s strict UTF-8 codec on successive prefixes for the
first scalar and on the whole selected window for validation. Only an `unexpected
end of data` error maps to truncated/need_more. Other errors map to invalid_sequence.
Python incremental decoding is never used: it can defer a known-invalid ED A0 prefix.

To anchor the API’s immediate-invalid precedence independently of codec timing,
self-tests explicitly require invalid_sequence in both final modes for every ED A0..BF,
E0 80..9F, F0 80..8F and F4 90..BF two-byte prefix. These are Table 3-7 boundary anchors.
All such cases also execute in the exhaustive native two-byte corpus. There was no
oracle-correction failure in this independent review.

The Aurora harness is one small scalar-argument entry point that constructs an
8-byte owner, borrows it readonly, invokes both public APIs twice, checks identical
reports, compares every input byte and writes the owner after the borrow’s scope.
All result fields are compared, via a collision-free bounded 64-bit encoding;
field bounds are checked before packing. A C++ test-only host bridge feeds scalar
arguments and returns full 64-bit values. It does not pass host-created spans or
introduce a language C ABI.

Per compiler, the identical corpus includes:

- 242 signed-range cases, including i64 minimum/maximum and empty end windows
- 131,586 cases covering every 0-, 1- and 2-byte string in both final modes
- All 1,112,064 Unicode scalar values, varying padding offset and final flag
- 66,240 longer boundary/continuation cases
- 6,928 partial-scalar replay, valid-prefix and nonzero-window cases
- 50,000 deterministic random windows, seed 0x17C0FFEE

Total: **1,367,060 cases per compiler**, not a disjoint sum across compiler runs.
Corpus SHA-256: `f4cbbd7c74413e144cd0388929bb6e7caaba7362940a0ac77bb7ff02a1c24b66`.
Release and instrumented compilers emit byte-identical harness assembly.
Both compiled native programs pass the full corpus and require normal exit.

## Additional native and rejection fixtures

`fixtures.py` passes, under Python `-O`, on both compiler pins:

- Seven native groups: report-constructor semantics and capacities 1, 3, 4, 8, 64, 4096
- Maximum-capacity ASCII validation, end-of-span emptiness, trailing incomplete and
  malformed sequences, U+0800/U+10FFFF, complete-prefix counts, and owner reuse
- Manual success reports with surrogate/above-range payloads and extreme signed
  widths; valid payload with arbitrary width; manual validator extreme counts
- Nine semantically rejected sources: unsigned offset/count, numeric final flag,
  private decoder/validator fields, unexported helper, mutation during a live span,
  non-byte owner, missing final argument

Every rejection is normal compiler exit 1 with its specific semantic diagnostic,
and is checked twice: absent output stays absent, existing sentinel output remains
byte-identical. These are 16 groups per compiler, 32 overlapping-build groups total.
They are not a new independent proof of the unchanged span compiler.

## Reproduction commands

Run from any directory; all paths are explicit:

```sh
D=/workspace/scratch/48c5de6446f8/aurora-utf8-review
R=/workspace/scratch/48c5de6446f8/aurora-utf8-next
/tmp/aurora-resource-main-compiler-frozen --module-root "$R/library" "$D/native.au" -o "$D/native-release.s"
env ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 /tmp/aurora-resource-sanitizer/aurorac --module-root "$R/library" "$D/native.au" -o "$D/native-instrumented.s"
cmp "$D/native-release.s" "$D/native-instrumented.s"
c++ -O2 -Wall -Wextra -Werror -no-pie "$D/driver.cpp" "$D/native-release.s" -o "$D/native-release"
c++ -O2 -Wall -Wextra -Werror -no-pie "$D/driver.cpp" "$D/native-instrumented.s" -o "$D/native-instrumented"
python3 -O "$D/review.py" --self-test-only
python3 -O "$D/review.py" "$D/native-release"
python3 -O "$D/review.py" "$D/native-instrumented"
python3 -O "$D/fixtures.py"
```

Native inputs are at most 8,192 cases per subprocess (262,144 input bytes and 65,536
expected result bytes). Each corpus subprocess has 20 s wall, 15 s CPU, 256 MiB
address-space, 64 MiB regular-file and zero-core limits. Fixture commands have 30 s
wall, 20 s CPU, 64 MiB regular-file and zero-core limits; fixture native executions
also have 256 MiB address-space limits. Fixture compiler processes do not have an
address-space cap, to preserve ASan shadow reservation. The single harness
compilation commands had no additional OS process limits and succeeded on the
bounded-size source. No compiler-bootstrap build
was performed. The largest generated capacity source is 19,397 bytes; the main
runtime harness stays under 3 KiB.

Instrumented means the bootstrap compiler was ASan/UBSan instrumented. Emitted Aurora
code itself is not sanitizer-instrumented. LeakSanitizer is explicitly disabled;
ASan/UBSan fatal error checks remain enabled. Host: Linux x86-64; Python 3.12.14;
GCC 14.2.0; GNU assembler 2.44. Signals, nonzero exits, timeouts, missing bytes,
extra bytes and mismatched values all fail. Harness controls confirm detection of
wrong values, short output and a signal result, including under `-O`.

## Failures, strengthening and limits

One early read-only shell call failed before execution with an exec-server transport
disconnect/recovery timeout. It was not an access denial. A later read-only retry
succeeded. No uncertain native run was repeated due to that failure. No native,
compiler-sanitizer or semantic test failed in this independent review. The final
baseline-identity guard intentionally stopped when the Makefile changed; the exact
diff and author confirmation resolved it as the test-registration delta, not a
compiler-source drift.

Initial passing runs preceded added explicit native process resource caps and
pre-packing field-range guards. The full corpus was rerun after these harness-only
strengthenings; pre-guard binaries/assembly and initial logs are retained. This did
not change the candidate or expected outcomes. Repeat runs overlap and do not add
coverage. The author’s interrupted aggregate is not treated as passed. The later receipt
`aurora-utf8-next/build/final-acceptance/result.json` records eight commands with
known exit zero: normal/-O self-tests plus UTF-8, readonly-span and storage suites
on both compiler pins. Its inputs.json and current source hashes match. The two
UTF-8 manifests record passed outcomes. This is inspected author evidence, not a
claim that this reviewer reran the full compiler target.

The byte-string corpus is exhaustive only through length two; longer malformed
inputs are bounded classes and deterministic samples. Every valid scalar encoding
is covered, but not every placement, concatenation or split of every scalar.
Readonly/native functional evidence is not a whole-compiler memory-safety proof,
Unicode certification, resource/performance guarantee, or operating-system/hardware
qualification. Any subsequent main-tree integration and full milestone acceptance
remain separate decisions.

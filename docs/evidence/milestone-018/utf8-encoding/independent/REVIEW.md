# Independent owned UTF-8 encoder review

Verdict: **PASS for the isolated, pinned pure-library implementation.** No
implementation defect was found. Main integration, whole-project milestone
acceptance and builder aggregate status are separate decisions.

Reviewed candidate: `/workspace/scratch/48c5de6446f8/aurora-utf8-encoding-next`.
All independent artifacts live beside this report in `aurora-utf8-encoding-review`.
Review date: 2026-10-03 UTC. No candidate implementation edits were made.

## Exact identities

- `library/std/utf8.au`: `a9448bed52974ca1e690b9a10e86a5f879c5b24f475a12ab1ec079e4e97bc646`
- Frozen release compiler: `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`
- Frozen instrumented compiler: `805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf`
- Author test reviewed: `e35b66182a56c8f7e87622d6ab65b74fa3e4a0199eb1c56f165a838c808ae1f5`

The compiler executables and library were hash-checked before each independent
run and again at review finalization. Compiler `.cpp`/`.hpp` inputs remain
identical to the baseline manifest. The existing decoder is byte-identical after
removing the single new `std.array` import and appended encoding declarations.
The build recipe adds the encoding gate; that is not a compiler-mechanism change.
No heap, mutable span, pointer, constructor grammar, IR or kernel change is added.
No main-repository writes, shared image builds, hardware or publication actions
were performed by this review.

## Independent evidence, per compiler

1. **1,122,439 exact-output factory observations** in 138 bounded runtime batches:
   every 1,112,064 Unicode scalar and 10,375 invalid input observations. Invalid
   coverage contains all 2,048 surrogates, 4,096 consecutive above-range values,
   u64 maximum/neighbors, power-of-two boundaries and deterministic wide values.
   Counts describe observations, not a promise of distinct random inputs.
2. Every scalar's actual native status, width and four copied bytes are compared
   directly with Python's strict UTF-8 encoder. An independently written
   division/remainder positional encoder and all nine rows of Unicode 17.0.0
   Table 3-7 independently check the Python expectations. No Aurora decoder is
   used by this oracle. Valid-byte access and fallback behavior at negative,
   extreme, size and fixed-capacity indices are checked within every observation.
3. **8,784 native report/copy cases** exercise both statuses, widths including
   signed minimum/maximum, all legal widths, zero/negative/oversized widths,
   extreme indices, malformed success prefixes, all 256 byte/fallback values,
   nonzero unused tails, constructor input mutation, copied report transport,
   nested class transport and mutation of independently returned arrays.
4. **One additional native ABI fixture** returns each of six different reports
   through all six ordinary aggregate argument positions. It also verifies that
   a constructor's array argument is snapshotted before a later scalar argument
   mutates that same source array.
5. **16 actual exact-site bounds traps**: copied arrays from valid and failed
   factories, read/write access, index -1, 4, i64 minimum and maximum. Every case
   terminates with actual SIGILL at the retained `.Laurora_bounds_trap` address,
   with a kernel-generated fault record and UD2 instruction. Generic crashes,
   wrong trap addresses/signals and timeouts are rejected by harness controls.
6. **18 ordinary compile rejections** cover private fields, wrong scalar/index/
   fallback/width/status types, wrong array element/capacity, nominal result
   substitution, numeric enum forgery/conversion, const-copy mutation and
   unsupported reference/chained receiver forms. The latter forms are syntax/
   receiver restrictions, not claims of new ownership-specific diagnostics.

That is 1,131,240 native case/fixture observations and 18 compile rejections on
each compiler. These overlap author tests and must not be added to author counts
as distinct coverage. Canonical output-stream SHA-256 is identical on both:
`5332739f104327df82132036f84db047e999fdcd146d35202f2b4f65b06e7b0b`.
Independent generated Aurora assembly is identical between compiler variants.

## Source and layout conclusions

The canonical factory rejects invalid scalars before narrowing or shifting,
selects the shortest width, initializes all four bytes, and extracts only
representable u8 values. The reviewed format is Unicode 17.0.0 D92, Tables 3-6
and 3-7: <https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/>.
The versioned chapter was opened and the exact table rows inspected during review.
NUL, BOM, unassigned scalars and noncharacters are ordinary scalar inputs.

Report accessors normalize failure/invalid width, guard index before storage
access, and copy only the logical prefix into fresh zeroed storage. Public
constructors can deliberately make successful, well-bounded reports containing
ill-formed UTF-8. Passing these tests does not make reports provenance certificates.

Static/runtime size and caller-visible field checks agree: owned array 4 bytes,
result 24 bytes, tested enclosing mixed-width class 40 bytes, result public field
count zero. Runtime canaries and independent copies exercise the existing private
aggregate calling convention. There is no external stable C ABI. These checks
observe logical bytes and alignment-sensitive sizes, not all native padding or a
whole-compiler layout proof. The host C++ I/O driver is test machinery; it does
not add an Aurora C ABI or heap dependency to the library.

## Commands, retained evidence and limits

From this review directory, all passed using Python `-O`:

```
python3 -O review.py release
python3 -O review.py instrumented
python3 -O reports.py release
python3 -O reports.py instrumented
python3 -O boundaries.py release
python3 -O boundaries.py instrumented
python3 -O abi.py release
python3 -O abi.py instrumented
```

Each run directory retains generated source/assembly, executable, exact commands,
exit statuses, stderr, inputs and native outputs. Each has `results.json`.
Canonical batches contain at most 8,192 inputs; report batches at most 2,048.
The largest standalone generated Aurora source is 3,921 bytes. Child limits are
10/11 seconds CPU, 30 seconds wall, 8 MiB per regular file, no core dump, 128 MiB
address space for native/tools and 512 MiB for the release compiler. Only the
instrumented compiler address-space cap is omitted for ASan shadow reservation.
Inputs and outputs are bounded files/blocks; no timeout or signal counts as a
positive result. Control validators remain active under optimized Python.

Instrumented compiler runs use `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`.
This tests the already instrumented compiler; generated Aurora machine code and
the ordinary host I/O driver are not thereby sanitizer-instrumented. LeakSanitizer
was not run. No compiler rebuild was needed. Tools were Python 3.12.14, GNU C++
14.2.0, GNU assembler/linker 2.44, Linux x86-64.

The final author aggregate receipt was inspected: all eleven commands have known
exit zero. Author encoding tests pass 186 native checks in 35 fixtures and 24
rejection compilations; complete decoder regressions pass 406 checks in 39
fixtures, on both compiler pins. Independent review inspected the new author test
and retained receipts, but those are author evidence, not new independently
rerun full-compiler or kernel gates.

This is exhaustive scalar functionality and bounded adversarial evidence, not
exhaustive u64 failure coverage, whole-program safety, production qualification,
performance equivalence, normalization, strings, graphemes, terminal support,
mutable-view completion or physical-device qualification.

## Finalization receipt

All 79 entries of the final candidate input manifest and all five integration
changes were independently rehashed successfully. The initially stale contract
hash in the early library-only manifest was corrected; its original was preserved
as `candidate-library-initial.json`. Runtime implementation and tests did not
change during finalization. No independent execution test failed.

- Final candidate manifest: `11500dc9c1e05d9005e77ca928f9fb34c25559e8af6bd8144bec9d6e011f239a`
- Five-file integration delta: `44f153fd0461e17cd5486cfc6c1af2ccc8350ba135f009b119f3337f2c5fa83b`
- Current library-only manifest: `edd2b1425d4b2132a4300f53eee705019b9546c9b147ae35d8a1e675d9dc2620`
- Final contract: `99a9f5a38d74557f3f442b769563e59a98079beb30edff05ccc09b2069e33509`

`manifest.json` seals this report, independent test sources and every retained
independent artifact. `validation-summary.json` collects the eight passing run
receipts. Generated files remain isolated from the proposed five-file source
integration delta.

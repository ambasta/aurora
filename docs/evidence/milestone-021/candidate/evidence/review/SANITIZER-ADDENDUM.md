# Independent M021 fatal-sanitizer replay addendum

Completed 2026-10-03 UTC. This supplements, and does not replace or modify,
REVIEW.md and its release evidence.

## Result

All **46 of the same independently authored fixtures** pass using the final
ASan/UBSan-instrumented compiler: 24 native-positive fixtures and 22 rejection
fixtures. The 22 negatives were also replayed with absent output paths. Thus this
replay performs 68 compiler invocations and 24 native executions. It is explicitly
overlapping coverage of the existing 46 fixtures, not 46 new cases.

- Instrumented compiler SHA-256, verified unchanged before/after:
  `423db8bcf0642263e445582107c73f967decdc13132f2bd98a973fce2db03d0f`.
- Same final implementation source as the reviewed release compiler:
  `d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64`.
  Every entry in `final-implementation.sha256` verified before replay.
- `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:abort_on_error=1`
- `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1:abort_on_error=1`

Every positive compiler invocation exited zero without diagnostics; each native
observer returned the expected full eight-byte value. Every negative compiler
invocation exited one with the exact expected release diagnostic, preserved the
pre-existing sentinel output, and created no output in the absent-output replay.
Fixture and module bytes were checked unchanged. No sanitizer finding was observed.

## Evidence and reproduction

- `sanitized-replay.py`: independent replay driver, using only the existing
  instrumented compiler and the previously reviewed freestanding assembler observer.
- `sanitized-replay/results.json`: complete commands, compiler/environment hashes,
  input hashes, diagnostics, native observations, publication checks and counts.
- `sanitized-replay.log`: console result for each fixture and summary.
- `sanitized-replay/{independent,extra,member-regression}/`: separate per-fixture
  assembly, native executable, diagnostic and JSON artifacts.

From the candidate root, run:

`python3 evidence/review/sanitized-replay.py`

The script's default evidence destination is the retained replay directory. To
perform another replay while preserving this completed one, select a fresh OUT
path in a copied review driver first; its absent-output assertions intentionally
reject reusing files from a prior run.

No C++ build was invoked by this replay. The release review and all original
release/historical evidence remain intact. The independent review directory is
below the authorized 25 MiB cap.

## Limits

Only the compiler host process is ASan/UBSan-instrumented. The emitted native
programs are observed through the same uninstrumented full-width assembly harness.
Leak detection was intentionally disabled exactly as requested; ASan/UBSan errors
were fatal. This bounded replay is not the complete owner-run sanitizer/regression
suite, a proof of memory safety, or a kernel/emulator integration result. The
reviewed semantic limits and deferred-validity contract remain unchanged.

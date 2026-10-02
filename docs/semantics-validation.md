# Bounded independent executable-semantics validation

This gate checks an explicitly limited language subset against a separate Python
reference evaluator. It does not import the compiler, inspect its AST, or derive
expected answers from its emitted assembly. Passing is evidence against concrete
implementation defects, not a soundness proof, formal verification, Rust-equivalent
safety, complete language coverage, or an OS/hardware qualification result.

## Run

From the repository root, with an already built compiler:

```sh
python3 tests/semantics/test_runner.py
python3 tests/semantics/run.py build/aurorac
python3 tests/semantics/run.py build/aurorac --seed 404 --cases 1024
```

Dependencies: Python 3 standard library, GNU `as` and `ld`, x86-64 Linux. Missing
tools and unsupported hosts fail rather than silently skipping. The compiler CLI
must be `aurorac INPUT.au -o OUTPUT.s`. No C runtime or foreign source-level API is
introduced. The small Linux syscall assembly bridge is trusted test machinery.
The compiler executable is copied to a temporary directory before the run, so a
subsequent rebuild cannot silently substitute a different compiler halfway through.
The run prints the tested executable's SHA-256, seed, generated-case count, and
observed outcome totals. Record compiler source identity and tool versions alongside
these receipts when integrating changes.

Default seed is 20261002, with 128 randomized programs plus 502 deterministic
boundary, ownership, and rejection cases. `--cases` ranges from zero to 10000.
To repeat a failure use the same executable, seed, case count, and Python version.
On failure, `build/semantics-failure/repro.au` and `failure.json` contain the failing
source, expected outcome, observed failure, ordinal, seed, and executable hash.
Override this destination with `--failure-dir PATH`. This directory holds only the
latest failure; preserve meaningful reproductions as named permanent cases before
running another investigation. The runner stops at the first failure.

## Independent model and generated subset

- Python mathematical integers with explicit signed-i64 range checks after each
  addition, subtraction, multiplication and negation. No host signed overflow and
  no implicit modulo arithmetic is used as an oracle.
- Typed i64 arithmetic trees of depth at most three, comparisons returning bool,
  negated bool conditions, conditional branches, mutable scalar locals, bounded
  loops, indexed array reads and writes, and independent array copies.
- Generated arrays have one to eight elements. Loops traverse those elements once;
  no generated recursion, input, arbitrary loop bounds, process creation, or
  unbounded reference evaluation occurs. At most four randomized conditionals are
  followed by one bounded traversal. Random cases include signed extrema and
  invalid indexes. Fixed cases additionally exercise bool-array mutation/traversal.
- Operands are evaluated left to right in the model; stores evaluate/check their
  index before their RHS. The reference evaluator tests those rules independently,
  but native tests do not comprehensively establish observable side-effect ordering.
- Every pair from nine boundary-focused integer values is tested for each binary
  arithmetic operation, plus unary negation. Fixed load/store cases include negative,
  zero, last-element, upper-bound and signed-extreme indexes for three array sizes.
- A separate tiny ownership state machine enumerates all 64 length-three traces
  over owner read, shared borrow, exclusive borrow and move. Ten traces are valid;
  54 must reject. All borrows in these traces last until the function block ends.
  Six additional cases cover scope release and continuing versus returning loop
  moves. This is intentionally not a complete borrow checker or lifetime calculus.
- Structured invalid scalar/array/type cases and every proper character prefix of
  a valid loop/array program test fail-closed rejection. A small malformed-token
  corpus includes an embedded NUL. These are bounded robustness checks, not a
  general parser fuzzer or a denial-of-service audit.

## Result and failure discrimination

The native bridge writes the entire signed 64-bit result as eight little-endian
bytes. The harness compares the decoded result, not an eight-bit process exit
status, and also requires successful exit and exactly eight output bytes.

Expected fail-stop cases must terminate with **exactly SIGILL** and no result
output. SIGSEGV, SIGABRT, SIGKILL, exit 132, ordinary nonzero exit, and timeout all
fail the gate. The model records whether it expected overflow or bounds failure,
but both compiled failures use UD2/SIGILL: the native observation alone cannot
distinguish those two causes or prove the precise trapping instruction. A different
bug causing SIGILL on an expected-trapping path could therefore evade this gate.

Invalid source must cause a positive compiler exit code, a nonempty diagnostic,
and no emitted assembly. Compiler termination by a signal or timeout never counts
as successful rejection. Diagnostic wording is deliberately not coupled to the
compiler's internal implementation. Rejection checks do not prove the compiler
rejected for the intended reason; acceptance cases alongside them reduce, but do
not eliminate, this ambiguity.

Each subprocess has a five-second wall deadline, three-second CPU limit, 512 MiB
address-space limit, eight-MiB file-size limit, and disabled core dumps. These
bounds can reject a particularly slow or instrumented compiler; that is a visible
failed gate rather than a hidden pass. Temporary source/object/native products are
reused per case and removed at run completion; only explicit failure receipts
persist. They are ordinary test executables, not an isolation sandbox for hostile
arbitrary compiler code.

Seven runner self-tests check reference range/bounds/order facts, ownership model
counts, full-width result handling, and that wrong signals/ordinary exits/compiler
crashes cannot masquerade as success. These tests mock subprocess results and do
not replace the actual native execution gate.

## Scope still missing

Random programs do not cover class layout/privacy, function-call conventions,
recursion, reflection, nested ownership joins, reference writes, or complete bool
expression generation. Fixed/model cases provide only narrow coverage outside the
randomized subset. There is no optimization-equivalence testing, adversarial stack
exhaustion proof, general grammar shrinking, resource-complexity theorem, concurrency,
heap/provenance model, formal progress/preservation proof, or self-hosted execution.
The independent compiler suite and QEMU gates remain required for their own scopes.

## Initial local receipts (2026-10-02)

Python 3.12.14; GNU assembler/linker 2.44; x86-64 Linux. Tested executable SHA-256:
`12150503845322d26d92c501142d8e7c243c943fcd30cbdaf5c54a46a6f076e0`.
These receipts identify that executable and must be rerun after compiler changes.

- Runner self-tests: 7 passed.
- Seed 20261002, 128 generated: 630 total passed; 285 values, 96 overflow traps,
  50 bounds traps, 199 rejections.
- Seed 404, 1024 generated: 1526 total passed; 893 values, 205 overflow traps,
  229 bounds traps, 199 rejections.

The two runs repeat the same 502-case deterministic corpus; their totals should
not be represented as that many unique programs. No compiler defect was found by
these runs, so there is no new compiler-bug regression claimed here.

## Typed-IR candidate receipts (2026-10-02, 22:41 UTC)

The candidate executable was independently rerun using the same commands and
seeds above. Seven harness self-tests, all 630 default cases, and all 1526 stress
cases passed. The outcome totals exactly match the baseline totals above; no
semantic discrepancy was found in this bounded corpus. Both native runs reported:

```text
compiler_sha256=765ed87efa9c28909217f0ab01bacc97ef2fbdea6fd76547db778726b18a8918
seed=20261002 generated=128
PASS 630 cases {"bounds": 50, "overflow": 96, "rejected": 199, "value": 285}
seed=404 generated=1024
PASS 1526 cases {"bounds": 229, "overflow": 205, "rejected": 199, "value": 893}
```

Source hashes observed alongside that candidate were unchanged before and after
these runs. This workspace has no local Git metadata, so the source identity is
the following SHA-256 manifest rather than an invented commit ID. Tool versions
remain Python 3.12.14 / GNU binutils 2.44; host g++ is Debian 14.2.0-19 (14.2.0).
These results cover this candidate executable, not later edits or rebuilds.

```text
6dface349f7c37eb8ced87cae85dff0b73fb9c7ea9ac04484d226a07aa89a632  compiler/main.cpp
6d8c4c63377369d574ad83d9f63e45e0883b4662e3b5b52784e7c299c16a36c7  compiler/ir.hpp
90bedc895ce67fcd4bcbc5f3a44c1ad42adb02d5c7951b6198ae150390e6af04  compiler/ir_verify.hpp
7be04e56cc830145844902a9e9d6304337035950c589a5911e6b54feed2966ab  compiler/lexer.hpp
a21606a10ca283d2f60be29696501ec5154d04f4bf3ac646004feedf16be03c8  compiler/parser.hpp
80f759754b96d4aa5b9c20b2241464270406f9c735967ff5db6509655e7d0ccf  compiler/semantics.hpp
1fac8414ded251ece05981436adae2370d45ea44ffb420c07657eb9ff5973140  compiler/syntax.hpp
f97ab142ba2f1fca930107f237079558a7e9f061c26b79adf069c16e203f10a4  compiler/types.hpp
208fc296f8258d35394eb0c729af2775d7ae5fdbadd7e6dbc8b68470a9c2de2b  compiler/x86.hpp
5b7b0c31f17617be53aed4ac50054e91b4689e5745e6fc6d543fc2800dcd4cb3  compiler/Makefile
```

## Final aggregate after resource correction

The coordinating fresh build repeated the default 630-case run, stress
1,526-case run and seven harness checks against corrected release SHA-256
`753845632fa5361f7262266c5b74b75927393403cf86c1d84a3ba34bc86ebf53`.
All passed with the same outcome counts. See
[final aggregate receipts](verification.md#typed-ir-runtime-containment-and-resource-correction--2026-10-02).
The earlier candidate receipt above remains a historical pre-resource-fix result.

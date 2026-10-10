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

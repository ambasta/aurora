# Bounded executable-semantics validation

`meson test native-semantics` (or `python3 tests/semantics/run.py build/aurorac`)
checks an explicitly limited language subset against reviewed golden results.
Passing is evidence against concrete implementation defects, not a soundness
proof, formal verification, Rust-equivalent safety, complete language coverage,
or an OS/hardware qualification result.

## Cases and expected results

`tests/semantics/run.py` generates the deterministic families; the 128 random
programs (seed 20261002, from the former generator) are checked in as
`tests/semantics/generated.cases`. `tests/semantics/run.golden` holds every
case's expected result: a full 64-bit value, a trap with its exact UD2 site
(`overflow` or `bounds`), or a rejection. The golden results were produced once
by the former Python reference evaluator and ownership state machine, which are
gone; an intended change edits the golden line.

- Random programs: typed i64 arithmetic trees of depth at most three,
  comparisons, negated conditions, conditional branches, mutable scalar locals,
  one bounded traversal of a one-to-eight element array, indexed reads and
  writes, independent array copies, signed extrema and invalid indexes.
- Every pair from nine boundary-focused integer values for each binary
  arithmetic operation, plus unary negation; load/store bounds at negative,
  zero, last-element, upper-bound and signed-extreme indexes for three array
  sizes; one bool-array mutation/traversal.
- All 64 length-three traces over owner read, shared borrow, exclusive borrow
  and move (ten valid, 54 rejected), plus scope release and continuing versus
  returning loop moves. This is not a complete borrow checker or lifetime calculus.
- Structured invalid scalar/array/type cases, every proper character prefix of a
  valid loop/array program, and a small malformed-token corpus with an embedded
  NUL must be rejected.

## Execution

The shared native runner (`tests/compiler/native_runner.py`) packs the accepted
cases into one compiled program, compares the complete 64-bit result of each
value case, and requires a kernel SIGILL at the exact named trap label for each
trap case. Each rejection is compiled once and must exit 1 with a diagnostic,
creating no output and leaving an existing output unchanged.

## Scope still missing

Random programs do not cover class layout/privacy, function-call conventions,
recursion, reflection, nested ownership joins, reference writes, or complete bool
expression generation. Fixed/model cases provide only narrow coverage outside the
randomized subset. There is no optimization-equivalence testing, adversarial stack
exhaustion proof, general grammar shrinking, resource-complexity theorem, concurrency,
heap/provenance model, formal progress/preservation proof, or self-hosted execution.
The independent compiler suite and QEMU gates remain required for their own scopes.

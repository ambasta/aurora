# Exact-bool short-circuit semantics

## Dependency and acceptance

Kernel policy expressions exposed the missing `&&`/`||` language mechanism.
The declared gates were independent source/IR/native review, complete release
and fatal ASan/UBSan compiler targets, and fresh combined integration. These
passed: isolated release/fatal host sanitizer suites were followed by a fresh
combined compiler, complete native aggregate and 173 production QEMU modes plus
three capacity probes and two actual normal restoration boots. See the
[integration record](../docs/kernel-round-robin-integration-results.md).
LeakSanitizer was disabled because of executor ptrace limitations; the large IR
translation unit used the documented -O1/-g1 sanitizer build. ASan/UBSan failures
remained fatal. No leak-clean, whole-kernel sanitizer or broad safety claim follows.

## Source behavior

Both operands must be exactly `bool`; the result is canonical `bool`. No numeric,
enum, class, owner or span truthiness or overloaded operator is provided. Operands
evaluate once, left to right. `a && b` executes `b` only if `a` is true; `a || b`
executes `b` only if `a` is false. Executed calls, writes and checks retain their
existing order. A skipped runtime arithmetic/bounds failure does not trap.

From lowest to highest binary precedence: `||`, `&&`, bitwise `|`, `^`, `&`,
`== !=`, `< > <= >=`, `<< >>`, `+ -`, `* / %`. Each level is left associative.
Existing unary `!`, numeric unary operators and postfix operations retain their
higher precedence and exact typing. Parentheses override grouping.

The complete RHS is always parsed and semantically checked, including after
literal `false &&` or `true ||`. Unknown/private names, type errors, illegal
borrows/moves, invalid literals and unsupported expressions still reject.
`static_assert` admits logical combinations of its existing closed constant
subset (literals, reflection, comparisons and `!`). Both constant operands are
checked; skipped arithmetic/calls do not become allowed constant expressions.

## Ownership and initialization

No ownership constructor becomes a general expression. Outer locals keep equal
shared/exclusive borrow counts, owner and span-origin facts across continuing
paths; live state is intersected. Unsupported conditional authority changes fail
closed. Synchronous readonly span arguments and copied class argument snapshots
created by RHS calls close before the join. Values may be mutated only through
existing authorized mutable receivers/references. Logical conditions do not
relax surrounding `if`/loop move rules, constness, initialization or privacy.

## Verified IR contract

Lowering uses existing `BranchFalse`, `Jump`, and `Label`. Both paths leave a bool
current value and preserve the prior operand-stack prefix. Nonempty expression
stacks may cross control flow only with exact ordered type and bounds-evidence
equality at joins. Active object lifetimes, array creation sites and complete span
origin/direct-parent/site facts must still agree; must-initialization intersects
and may-initialization unions. Returns still require empty operand stacks.

The verifier also records only transient incoming/outgoing depths per reachable
instruction. After convergence it checks the actual filtered emission sequence,
starting at zero: every instruction's incoming depth must match the previous
emitted instruction's outgoing depth. Unreachable semantic instructions reject;
only the previously allowed unreachable labels/jumps are filtered. Depth is never
reset at a label. This explicitly certifies unchanged backend linear stack/call
alignment accounting. Arbitrarily reordered stack-carrying CFGs may reject even
when CFG-valid; no general nonlinear IR support is claimed. No opcode, public IR
metadata, x86 implementation, source pointer or ABI is added.

## Bounded snapshot retention

Each function permits at most 65536 retained block-entry states (including entry)
and 262144 operand Values summed across those states. Both limits are checked
before a first snapshot is allocated, using overflow-safe subtraction. Existing
snapshot stack equality is checked before a merge copy, and revisits do not charge
again. Enforcement is independent of diagnostic metrics. Overflowing either bound
produces an explicit compiler diagnostic and preserves existing output files.

These aggregate limits coexist with array capacity and source/frame limits.
Straight-line 4096-element initialization is unchanged; a large initializer with
many logical branches can exceed retained-operand limits. Operand payload depends
on host type layout. Current/merge copies, vector capacity, strings, lifetime and
initialization sets, instruction-sized arrays and other compilation state remain
outside this count limit. This is not a whole-compiler memory/time bound, denial-
of-service guarantee, safety proof or equivalent-C performance claim.

## Validation scope

The source oracle independently models booleans and call traces, observes all 64
native return bits, and checks exact named trap sites and absent/preserved output
on rejection. It covers mixed precedence, later arguments, class snapshots,
readonly span/subspan cleanup, checked local/receiver index assignments, templates,
constructor initialization, loops, skipped bad RHS and explicit retention failure.
Direct IR/native gates must additionally validate unequal stack/guard joins,
conditional initialization, lifetime mismatches, non-linear physical stack layouts,
resource boundaries and handwritten odd/even call-alignment probes.

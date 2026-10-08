# Distinct service groups: focused, unqualified checkpoint

2026-10-08. This isolated compiler increment supports the next graphical console's
need to synchronously borrow separate sealed ConsoleSession and DisplaySession
capabilities. It does not modify the frozen framebuffer candidate or publish a
qualified milestone. Full integrated dev, slow and root Make gates are pending.

## Mechanism and scope

The parser admits one leading service reference or a contiguous pair of distinct
service references, in either order. Semantic admission retains six formals,
readonly-span and scalar tail restrictions, no owners/regions, and no capability
storage, construction, return or reflection. A group containing Console may return
the approved copied ConsoleSample, even with Console second.

Each binding has a distinct private sixteen-byte grant/generation spill. Each
forwarded root acquires its own loan before later arguments run. Only those roots
are suspended. Singleton subsets, paired forwarding and reordered helpers retain
exact kind and source provenance. IR joins preserve every loan independently;
operations cannot use a suspended root, calls cannot duplicate/cross roots, and a
loan cannot call twice without release. Legacy released loan IDs may be reused for
the same static root/kind; cross-root reuse is rejected. The backend precomputes
that mapping, so code-layout order cannot change authority.

Private record offsets follow formal order. Both qwords travel together to each
formal's offset. The existing R11 record, R10 copied-result pointer, six-formal
limit and outgoing stack alignment remain. No generic combined capability, public
source FFI or ambient authority is introduced.

## Focused results

- Release compiler build with GNU C++23, O2, Wall/Wextra/Wpedantic/Werror: passed.
- Grouped hostile IR: 146 cumulative checks passed (125 in the first checkpoint), including the full historical
  Console (34) and Display (71 cumulative) suites. New cases cover both orders,
  subset forwarding, independent suspension, copied reports, loop/nonlexical CFG
  behavior, and forged binding/loan/call/storage/join cases.
- Existing Console generated-editor/source/ABI gate: passed, including exhaustive
  rejected input bytes, 288 output-timeout prefixes and 22 source rejections.
- Existing Display source/ABI gate: passed, including copied metadata and malformed
  host status controls. Its former distinct-pair rejection is now a positive probe;
  same-kind duplication remains rejected.
- Group source/private ABI: passed, including 19 clean source rejections (exit 1),
  reversed six-formal forwarding with spans, unequal grants and generations,
  singleton subsets, an odd-depth paired call, input-derived pixel values, and
  symmetric independent suspension and exact cross-service traces for success, absent input, damaged input and first
  output failure. The ABI envelope checks stack and callee-save canaries.

The first grouped hosted probe failed to compile because a test counter named
`puts` conflicted with stdio; it was renamed and the original failure retained.
Source review also caught the parser's initial singleton guard before source
execution; the corrected release rebuild is separately recorded. These are
retained development results, not suppressed failures or transferred acceptance.
The final grouped source/ABI replay includes stricter rejection codes and complete
cross-service trace assertions.

## Independent-review controls, focused replay 002

The independently reviewed 972-file checkpoint is preserved unchanged separately;
all first-checkpoint evidence, including its failed probe, is retained. Only tests,
test routing and documentation changed for this follow-up; compiler implementation
and the reviewed release compiler binary are unchanged.

The added 21 IR checks cover Console operation and reborrowing while Display is
loaned, rejection of Display use during that loan, and grouped copied-result
ServiceCalls in both formal orders. Destination mutations reject zero/wrong offsets,
inactive object lifetimes, each preinitialized field, complete preinitialization,
and a wrong nominal class with identical physical layout.

The IR binary also exports a validated nonlexical CFG whose reversed pair call is
textually before its acquisitions, then reacquires the released IDs for a second
call. The new hosted driver compiles and executes that generated assembly. Its
oracle requires separate exact grants, generations 43 and 101, all operation
arguments, return zero and trace `WPWP`; the assembly envelope checks alignment and
callee-save/stack canaries. Both existing Make and Meson display-IR routes run the
cumulative suite and this executed control.

Focused replay 002 passed the strict release IR build, all 146 cumulative checks,
the executed CFG/reused-ID probe, and the Display/group source/ABI runner. The
source probe now directly exercises both directions of independent suspension,
including singleton reborrow, and its full success trace is `NPPWNPPWWPWPWP`.
Absent/damaged input and first-pixel failure still stop at `N` and `NP`. No new
compiler semantics, full-suite acceptance or native/guest claim is added.

## Bounded generated-assembly regression

Current output is byte-identical to the retained frozen-snapshot assembly for the
real Console editor (68,829 bytes), Display ABI/metadata probe (21,241 bytes), and
real framebuffer renderer (45,619 bytes). The framebuffer output was freshly
regenerated with the current compiler and original module-root arguments. This
is exact equivalence for these consumers, not a proof for all admitted programs.

## Remaining acceptance

This is a small sample-to-pixel compiler consumer, not the completed Line64
editor/display application. The host seam checks the exact grants and generations
received at operations; it does not qualify atomic combined native entry admission.
The native entry must authenticate both grants before any consumer execution and
prove stale/crossed/partially valid no-write behavior. Combined mappings, timer
quietness, mixed stack/page budgets, store bounds and actual guest captures remain
separate. No physical-device access, dependencies, native kernel changes, guests,
full aggregate gates or publication were performed for this checkpoint.

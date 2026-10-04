# Ordinary overload candidate: isolated verification passed

Base: 513 sealed source files from PR19, accepted main commit
1e3499e6a72c6a392a74e70c770724a3ec019080, tree
db79101fe6f0dc45a21625594396bade8ea2c2ff.
No accepted workspace was written and nothing was published.

Release V2 compiler SHA256:
8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631

Fatal ASan/UBSan compiler SHA256:
5799267c6d9eb31511e06181e057a8c02fa68cf926d2f853b260165ca85ac9e2

Baseline M022 compiler SHA256:
e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e

## Completed checks

- Complete fatal ASan/UBSan compiler target: sanitizer-full-1/result.json records
  exit 0, 605.198 seconds, 601,423,872 peak candidate allocated bytes, empty stderr
  and unchanged recorded inputs. The bounded IR build passed at 1,662,860 KiB
  peak RSS in 78.815 seconds, without signal or deadline termination.

- Complete release compiler target: release-full-2/result.json records exit 0,
  284.017 seconds, 559,816,704 peak candidate allocated bytes and unchanged input
  identities. Includes 964 direct typed-IR cases, exhaustive dispatch/native
  boundary controls, numeric oracles, module/depth and host-I/O gates.
- Author focused suite: 63 fixture names / 83 executions, 41 native returns,
  two exact native traps and 20 negative fixtures checked with absent and saved
  output. It is also included in both full compiler targets.
- Independent review: 123 fixture names / 168 execution checks, 45 negative
  fixtures each checked with absent and saved output, three exact traps, five
  artifact/differential checks, and 25 private symbol order/result controls.
  Five valid and 27 corrupted typed-IR modules check selected call boundaries.
  Release and instrumented source/IR replays passed. Author/independent fixture
  behavior overlaps; their counts are not combined into disjoint coverage.
- All 60 sealed Aurora files: exact baseline/V2 status, diagnostics and assembly
  comparison (57 compile successfully, three identically reject). Another 64
  bounded differential programs agree on native returns/traps/rejection status.
- New documented example executes natively and returns exact i64 42.
- Package runner expected-pin review: invalid/wrong pin gates fail before their
  designated artifact directory exists; historical M022 default remains intact;
  explicit candidate quick checks pass. Quick checks are not full package gates.

## Failed attempts preserved

- release-full-1 found changed duplicate-function diagnostic wording. V2 restores
  the exact previous duplicate-name message; all compiler source checks reran.
- Independent test fixture used reserved builtin name read and was corrected;
  direct IR fixtures needed strict-warning/enum-constant/diagnostic fixes. Failed
  sources and logs remain in the independent directory.
- Package compatibility repeats encountered their enforced 128/512 MiB candidate
  limits during other artifact growth. Failures remain distinct from later passes.
- The first V2 static-source comparison accidentally reused the prior artifact
  directory and rejected before compiling; its source and error are preserved.
- Initial gzip archive verification used backward seeks and repeated decompression.
  It completed exact inventory/byte/mode verification before removal. Later
  compaction uses a single streaming pass with the same checks. No failed run
  or failed fixture directory was selected for compaction.

## Resource and sanitizer limits

Initial candidate storage cap was 384 MiB with a 1 GiB free-space floor. After
measured growth, the parent explicitly approved a 1 GiB candidate cap while
retaining that global floor. run_gate.py records commands, inputs, limits,
statuses and peak allocated bytes. Completed successful build artifacts are kept
in byte/mode-verified lossless archives with full inventories; original failures
remain uncompressed in their recorded locations.

Compiler/source/host tests use full -g; only the existing large IR-test translation
unit uses the previously specified -g1 accommodation. That compilation has a 2 GiB
address cap, CPU 120/130 seconds, wall 180 seconds, file 512 MiB and core 0 limits.
Instrumented runtime runs do not inherit an address-space cap. ASan is fatal with
detect_leaks=0:halt_on_error=1:abort_on_error=1; UBSan is fatal with
halt_on_error=1:print_stacktrace=1. Emitted Aurora programs are not ASan-instrumented.
Leak detection is disabled; no leak-proof or general memory-safety claim follows.

## Pending

A separate parent integration must verify source delta identities, rebuild,
run the aggregate with the explicit
recorded compiler pins, and apply its selected existing kernel/emulator gates.
No compiler milestone, main adoption, publication, whole-program resource bound,
C-equivalent performance or physical hardware qualification is claimed here.

Suggested parent aggregate pin arguments (all expected values recorded above):

make test UTF8_RANGE_COMPILER_SHA256=8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631 UTF8_LINES_COMPILER_SHA256=8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631 PACKAGE_IDENTITY_COMPILER_SHA256=8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631 PACKAGE_MANIFEST_COMPILER_SHA256=8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631

If the package-graph checkpoint is accepted first, preserve all its files and
Make additions rather than replacing whole files from this older base. Supply
PACKAGE_GRAPH_COMPILER_SHA256 with the same reviewed release pin for its gate.
The delta manifest identifies exact baseline/candidate bytes for deliberate
integration; no unlisted file is authorized for replacement.

Only the listed post-gate documentation status edits occurred after the complete
compiler targets. Compiler implementation/header and test/library inputs still
match the gate receipts. Parent integration is required before final acceptance.

Source and verification are separate archives. The source archive contains the
complete 518-file candidate tree; the verification archive retains commands,
receipts, snapshots, binaries, independent review and original failures. Receipt
paths above are relative to the preserved candidate/evidence layout.


## Parent integration update (2026-10-04)

The isolated status above is retained as historical evidence. Fresh integration
over the accepted package.graph checkpoint has now completed the full native
test recipes and all 166 emulator modes plus two actual normal restoration boots,
with independent final review. The original aggregate bookkeeping failure remains
failed and is accepted only through its exact reviewed supplement. See
[the integrated results, receipt identities and limits](../../docs/function-overloads-integration-results.md).

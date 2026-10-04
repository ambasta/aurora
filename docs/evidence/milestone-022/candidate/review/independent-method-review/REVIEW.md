# Independent M022 implementation review

Result: no remaining implementation defect reproduced in this review. Final source review and independent release/fatal host-sanitizer source replay pass for the pins in final-reviewed-manifest.json. This is finite review evidence, not a general safety proof, full compiler-suite receipt, or kernel integration acceptance.

## Scope and identities

Compared candidate compiler/library delta with accepted Aurora M021 under AGENTS.md and compiler/METHOD-VALUES.md. No implementation edits or C++ builds were performed by this reviewer. Tests used existing compiler/IR-driver binaries plus GNU as/ld and independent assembly entrypoints; no kernel images were touched.

- Release compiler: e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e
- Fatal-sanitized compiler: d3033d68ad6308030a057c9eaf2b2e258b15e245ca84a22cc2fce1873847adcd
- Direct-IR driver: 498c2d2aab7c1440a86cd0ff33b34ea6e2d2af1ceead774eabd2e42dcffec739
- std.array: 22bdc89a253e471f170b0d03fe2ad1290036b9d4fc06b55399f375329b344c51
- Parser: 7734b18afde18556be2eb5ef04a35b5575375c292ef12f9ba3d7a3fe52acee75, unchanged from M021

Exact final source/test/binary pins are in final-reviewed-manifest.json. Tool versions are in tool-versions.txt.

## Independent executions

1. 17 source probes pass on both release and fatal-sanitized compilers: eight complete native i64 executions and nine diagnostic-specific rejections. Logs are final-release-probe.log and final-sanitized-probe.log. Full sources/modules/assembly/binaries/diagnostics and hashes are retained under final-release/ and final-sanitized/.
2. 15 array-name/self-type controls pass on both compiler pins: four native successes and eleven diagnostic-specific rejections. Logs are array-self-probe.log and array-self-sanitized-probe.log; complete artifacts are under array-self/ and array-self-sanitized/.
3. Independent Python-list oracle passes all capacities 1 through 64 for i64/u64/u8/bool, 256 source/native cases on each compiler pin. Every case verifies self-exchange, old-result contents, complete receiver replacement, unchanged replacement input, and independent result/input mutation using scalar edge values. Full native results are read as 64-bit outputs, not exit-code truncations. Logs/artifacts are array-capacities-release.log, array-capacities-sanitized.log, and corresponding directories.
4. Frozen existing IR driver replays 51 direct-IR cases (5 accepted, 46 diagnostic-specific rejections): direct-ir-final.log.
5. Frozen handwritten native harness replays 21 ABI cases: native-abi-final.log and native-abi-final/. These include both new directions/modes, six mixed positional arguments, 3,072-byte maximum records, poisoned legacy scalar registers, nested hidden-register clobbers, overwritten original input records after binding, composed/empty payloads, padding/canaries, disjoint ranges, odd operand-stack alignment, exact hidden-save locations/overhead, private symbols, historical ABI controls and an intentionally wrong-record detector control.

The two compiler runs and any earlier exploratory repetitions overlap and must not be summed as disjoint coverage. Reviewer IR-driver replay used the pinned release-host driver; the separate complete instrumented IR/ABI build/run is the owner’s aggregate gate.

Sanitized source commands used ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:abort_on_error=1 and UBSAN_OPTIONS=halt_on_error=1:abort_on_error=1:print_stacktrace=1. No address-space cap was applied to sanitized compiler runtime; ordinary commands retained 384 MiB limits, CPU/time/output/core limits. Host instrumentation does not instrument emitted Aurora programs. All reviewer processes finished before the owner's isolated stress investigation.

## Reviewed implementation invariants

- Method lowering resolves receiver identity first, evaluates explicit arguments left-to-right, copies each complete named class local at its position, and stages distinct readonly snapshots. Class-result binding is introduced only after argument evaluation.
- Class parameters bind independent readonly local lifetimes. Existing declaring-class privacy, exact nominal identity, exported public signature closure and direct-import visibility continue to apply. Template exact-type authority does not authorize private member access or unrelated caller names.
- MethodCall vectors are exact positional length when a class parameter exists, with zero scalar/enum positions. Class sources must be active, complete, readonly, exact-nominal and distinct; receiver and fresh result cannot alias argument storage. Global physical slot-overlap checks and recursive logical completion remain, including empty child fields.
- Complete constructor initialization, no initialization-time receiver forwarding, readonly receiver permission, six explicit arguments, 64 leaves, depth four, template graph caps and receiver-containing call-cycle rejection retain their previous paths. New owner/reference/span method parameters and generic methods remain excluded.
- New scalar/enum-result mode uses R10 receiver and R11 all-argument record. Combined mode uses RAX result address after record packing and receiver setup. Entry saves hidden inputs at F+8/F+16/F+24 before parameter binding, with 32-byte combined overhead; historical modes preserve earlier saves and 16-byte overhead.
- Packed scalar positions are not compacted around class positions. Byte payload/padding and class reservations use validated existing layout. The record remains live through the call. Nested calls reload private saved receiver/result/record capabilities.
- std.array.exchange is ordinary Aurora code: construct a fresh old-value array, copy every old element, replace every receiver element from the readonly snapshot, return an independent old value. No class-field assignment, reference, heap operation or special backend library case is added.

## Corrected findings and final scope

The initial library used bare `array` as its injected self type, which conflicts with the deliberate builtin storage reservation. A temporary parser exception was considered, then fully reverted. This review recommended the already-supported qualified injected spelling `std::array` without explicit template arguments; the final library uses it for parameter/result/local/construction. This preserves existing grammar and builtin reservation. Independent checks cover qualification, import identity, same-name ambiguity rejection, scalar/capacity mismatch, builtin/storage separation and shadow rejection.

In-progress test issues were reported to their owners and corrected: reserved `read` method names, a privacy rejection reached through an unrelated old ordinary-function helper, an accepted IR forwarding fixture that accidentally recursed, and a caller-helper collision fixture whose names did not actually collide. Fixture-authoring corrections for this review are recorded in fixture-development-errors.txt. These are not mislabeled compiler defects.

The xfs_geometry.py sanitizer-options change was independently reviewed: it accepts only the historical exact fatal-halt setting or that exact setting plus abort_on_error=1. It does not disable sanitizer checks or permit arbitrary option strings.

## Remaining gates

Complete frozen release/fatal compiler targets, isolated investigation of the owner's stress SIGKILL, historical diagnostic-fixture migration, parent adoption, fresh aggregate tests, and all required 166 emulator modes remain separately owned. No result here establishes those gates, production safety, a whole-program stack/resource bound, a stable external ABI, physical hardware support or equivalent-C performance.

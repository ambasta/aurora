# Final independent audit addendum

Result: both focused test-quality gaps are closed by diagnostic-specific independent evidence on the final release and fatal-sanitized compiler pins. The previously frozen source-suite files were not edited. No implementation defect was reproduced. These gaps are nonblocking with this addendum attached; the original two fixtures should not themselves be credited as proof of the intended mutable-reference/existing-method-extraction cases.

## Exact gap probes

- Actual `mutref<i64>` ordinary-method parameter: rejected with `only scalar or enum method parameters are supported`. This parses the real mutable-reference type rather than rejecting the unrelated spelling `mut<i64>`.
- Extraction of the existing `inspect` method: `i64 extracted = receiver.inspect;` is rejected with `unknown field`. Explicit scalar binding avoids an earlier inferred-binding syntax rejection. The same declared method is successfully called in the positive control and returns a complete native i64 value of 42.
- Each negative runs with both absent output and byte-exact preexisting output; rejection leaves both states unchanged. Each compiler therefore runs four diagnostic-specific rejection invocations plus one native positive control. Counts describe two negative fixtures, not four distinct semantic rules.

The two final compiler pins are unchanged:

- Release: e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e
- Fatal-sanitized: d3033d68ad6308030a057c9eaf2b2e258b15e245ca84a22cc2fce1873847adcd

`audit-probes.py`, `audit-probes.log`, `results.json` and the release/fatal-sanitized fixture directories preserve full sources, exact diagnostics, output-preservation checks, native control artifacts and source-suite hashes checked unchanged before/after these probes.

## Final independent instrumented IR/ABI replay

The final prebuilt ASan/UBSan IR driver is `build/san/method-values-ir-tests`, SHA256 48be725f38dd75da77b94d7f2c10527f98fd12d150f4a2f1ec851fa99a5c6f67.

- 51 direct IR cases pass: 5 accepted and 46 diagnostic-specific rejections. Receipt: sanitized-direct-ir.log.
- 21 independently handwritten native ABI cases pass. Receipt: sanitized-native-abi.log. This is the same finite ABI corpus as the release-driver replay, not an additional 21 disjoint cases and not the separate 256-case array-capacity oracle.
- Driver and fixture/harness pins remained unchanged through replay: sanitized-abi-pins.txt and pins-unchanged.log.
- ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:abort_on_error=1; UBSAN_OPTIONS=halt_on_error=1:abort_on_error=1:print_stacktrace=1. Sanitized runtime had no address-space cap. No C++ build was started by this reviewer; emitted Aurora programs are not themselves host-sanitizer-instrumented.

Successful generated ABI trees are retained losslessly in completed-successful-output.tar.gz within this addendum directory. The complete relative path/type/mode/file-byte manifest was verified before removing only expanded recoverable duplicates; see completed-successful-output.manifest.json, archive-receipt.log and archive-native-abi.py. Authored probes, report and diagnostics remain expanded.

This addendum supplements REVIEW.md without changing its earlier recorded evidence or claiming parent/kernel integration gates.

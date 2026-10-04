# Author geometry validation receipts

The frozen module is c67c03928e0d4cf5896178906bd447523ec15b57cc95c4ade8b8330305a77864.
The final generic test is fe375d75a7726a538f404f5d2b3f4240065f7d41c3334c104b535b5db2e1c95c.
The final aggregate records twelve known exit-zero commands and stable inputs in
final-acceptance/result.json and inputs.json. Release and instrumented compilers
are the unchanged M016 pins 14cbaa33… and 805567b1….

Each new geometry run passes 586 header cases and 25,198 full-width observations,
40 layout observations, eight copy/fabrication checks and 17 specific-stage
negative fixtures with existing-output preservation. Absent-output behavior is
separately covered by the independent eight-fixture/two-mode suite; it was not
run by these author rejection fixtures. Counts overlap across runs and suites.

The 51 deliberate source mutations are test controls in isolated copied module
roots. Seven produce retained SIGILL failures, 44 output mismatches. No ordinary
unmodified-library input signals or times out. Twenty-four redundant guards are
explicitly source-audited rather than called single-deletion mutation kills.
All control outcomes, including the initial sparse-chunk witness failure, remain
in the original archive and per-run consolidated JSON. The initial span-result
negative expected the wrong diagnostic; its failed input/diagnostic is separately
copied under retained-development-failures. Neither required a library change.

Earlier pinned-hash-only harness runs remain historical. The final generic CLI
records actual compiler identity, optionally enforces --compiler-sha256, and
checks unchanged compiler plus 13 source/helper/fixture inputs through the run.
Current test hooks also work for a future legitimate compiler binary.

Old test-storage gates passed both pins: 254 storage cases, 15 real-header native
observations and 17 strict text-transport controls. The running example returns
exactly 42 with identical release/instrumented compiler output. No device/image
is opened by the target program and no mounting or read/write support is claimed.

Limits are recorded per command and run: CPU 10/11 seconds, tools wall 30 seconds,
native wall 15 seconds, 8 MiB regular files, core0, release compiler AS512 MiB and
native/tool AS128 MiB. Only instrumented compiler AS is omitted for shadow memory;
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 disables unsupported leak checking.
Emitted Aurora code is not thereby sanitizer-instrumented. Pipes have no separate
memory cap. The final outer aggregate wall limit is 300 seconds per whole target.

Consolidated *-receipts.json files preserve parsed original records, not whitespace.
The byte-exact original archive identified in distribution.json preserves every
raw receipt, generated input, assembly, object, executable and native output.
Those generated artifacts are intentionally omitted from distributed source;
none is normalized or re-encoded into text. Additional redundant text copies
remain in the isolated build directory. Historical archive hashes are unchanged.

# Incremental bootstrap prototype

This is a focused developer path alongside Make. It builds the native C++23
`aurorac` once per changed compiler input and runs three existing byte/storage
scripts directly. It does not enter `compiler_contract.py`, create a fresh
compiler per test invocation, or change any existing Make or firmware command.

## Run

On x86-64 Linux, install Meson 1.12.1 or newer and Ninja using your usual package
manager. The existing C++23 compiler, Python 3.10 or newer and GNU binutils are also required.
The minimum Meson version is deliberately the tested version for this prototype;
older-version compatibility has not been qualified.
Choose a compiler when configuring a new build directory:

```sh
CXX=g++ meson setup build/meson --backend=ninja
meson compile -C build/meson -j 2
meson test -C build/meson --suite bytes --num-processes 2 --print-errorlogs
```

Use a separate build directory to compare a different compiler or flags. No
formatter or optional style package is needed. Meson stores the configured C++
command and supplies it to the existing native-observer scripts.

`meson compile` builds `aurorac`, the existing C++ initialization-facts fixture,
and the storage-codec example assembly. Repeating it without input changes does
no compilation. The compiler's C++ include dependencies come from the compiler's
generated dependency file. The example declares its Aurora source, the compiler
target, `library/std/bytes.au` and `library/std/binary.au` as inputs. Those modules
currently import no other modules; future imports must be added to this dependency declaration
until the compiler can emit dependency files itself.

## Tests and scope

The `bytes` suite has three named tests, with their existing default case counts:

- `byte-codec`: owned byte encodings, layouts, rejections and the storage example
- `packed-values`: copied values, bounds traps and rejection cases
- `storage-binary`: readonly readers, CRC32C and offline XFS header cases

The `compiler` suite contains the existing initialization-facts C++ model test.
`meson test -C build/meson` runs all four registered tests. Select an individual
test by name, or use `--suite bytes` for the byte/storage feedback loop. Test
invocations always rerun the selected tests; a successful previous run is never
used as a cache of current correctness. A library-only edit does not require
rebuilding the native compiler, but a selected test run reads the edited library.
The existing Python oracles still compile their small C++ signal observer once
per test process and compile/assemble generated Aurora cases. The no-compilation
claim applies to an unchanged `meson compile`, not to these executable tests.

Tests run in parallel by default. Each byte/storage script already owns a unique
temporary directory; Meson places those below `build/meson/tests` by setting
`TMPDIR`. The source tree and other build directories are not output destinations.
Meson's normal test logs are in `build/meson/meson-logs`. Existing temporary-output
cleanup remains unchanged; these focused logs are not the historical native
acceptance receipts and do not preserve every generated binary.

Only these targets are migrated. The existing full native, sanitizer, firmware,
QEMU and independently pinned qualification workflows remain separate. A pass
here is focused developer evidence, not full-system or hardware qualification.

## Implementation references

- [Meson build targets](https://mesonbuild.com/Build-targets.html)
- [Meson generated sources](https://mesonbuild.com/Generating-sources.html)
- [Meson unit tests and suites](https://mesonbuild.com/Unit-tests.html)
- [Meson custom-target dependency options](https://mesonbuild.com/Reference-manual_functions.html#custom_target)

## Measured validation — 2026-10-07

The additive graph was tested on the PR37 source
`f458620b325c4f17c32b32c3c4a09b2771a472b8`, with GCC 14.2.0, GNU binutils 2.44,
Python 3.12, Meson 1.12.1 and the pinned Ninja 1.13.2 wheel. The latter reports
`1.13.2.git.kitware.jobserver-pipe-1`. Wheels were checked against the SHA256 values
from their versioned PyPI registry records and installed in an isolated directory.
Only this GNU/Linux toolchain combination was run.

- Cold `meson compile -j 2`: 33.28 seconds, two C++ compilations, two links and
  the example assembly generation. Ninja's build log records the two independent
  C++ compilations starting together.
- Unchanged `meson compile -j 2`: 0.80 seconds, `ninja: no work to do`, with no
  compiler or linker command.
- Appending a comment to `compiler/lexer.hpp`: 35.94 seconds, rebuilding and
  linking `aurorac` and regenerating its dependent example. The unrelated C++
  fixture did not rebuild. The resulting compiler hash was unchanged.
- Appending a comment to `library/std/bytes.au`: 0.43 seconds, regenerating only
  the example assembly. Compiler bytes, size and modification time were unchanged.
- The `bytes` suite passed twice with two workers: 19.37 and 20.81 seconds wall.
  On the first run, byte-codec and packed-values began 4.2 milliseconds apart
  and overlapped for 2.40 seconds. On both runs, Meson performed no bootstrap
  rebuild before running the tests.
- The C++ initialization-facts fixture passed 7,405,472 checks in 0.69 seconds.
- After restoring the original header/library bytes and timestamps, another
  actual `meson compile` was a no-op in 0.36 seconds.

Before publication, dependency review caught the example's second direct import,
`std.binary`, missing from the custom target. It was added, and a recursive scan
confirmed the example imports exactly `std.bytes` and `std.binary`, with no further
imports from either module. After graph regeneration, a separate `std.binary`
comment edit regenerated only the example in 0.52 seconds; restoring the input
produced another no-op. The codec test passed again with the corrected graph.

Each bytes run covered 789 codec cases plus 19 rejections, 100 packed-value cases
including 54 exact traps plus 18 rejections, and 254 storage cases with 1,186 API
calls. The existing codec test also assembled and executed the storage example;
the Meson example build target itself produces assembly only. Logs use Meson's
standard output and test formats. These are single-host measurements, not stable
performance guarantees or a repeat of the full native qualification.

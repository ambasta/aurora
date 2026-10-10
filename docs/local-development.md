# Local development

These commands run on an x86-64 Linux development host. They build disposable
emulator images; they do not install Aurora or change the host bootloader.
Run only one build/test command at a time in a checkout: the existing scripts
share `build/`. Use a checkout path without whitespace: the inherited Make/test
recipes do not consistently quote every repository/output path. Invoking a script
from another working directory does not remove that checkout-path limitation.
Never write the images to a physical disk or attach user data.

## Quick start

For ordinary compiler and core/byte library edits, configure the
[incremental Meson developer path](meson-bootstrap.md) and select `core`, `bytes`, partial `packages`
or combined `dev` with two test workers. Those tests own isolated outputs and can run in
parallel. The one-command-at-a-time warning above applies to the inherited shared
Make/script paths, not independent tests within one Meson invocation. Full native
qualification and the emulator workflows below remain explicit broader gates.

From the repository root:

```sh
make help
make                         # compiler + BIOS image, without QEMU
make kernel-uefi             # separate UEFI loader/payload, without QEMU
make run                     # normal BIOS build and verified QEMU boot
make run-uefi                # discovers installed non-Secure-Boot firmware
make capture-framebuffer     # build/check and save an emulator-only PNG preview
./scripts/compiler-test.sh   # configure/build incrementally, compiler-only suite
CXX=g++ make test            # configure/build incrementally, complete native suite
```

The executable scripts also work when invoked from another directory:

```sh
/path/to/aurora/scripts/kernel-run.sh bios
OVMF=/path/to/OVMF.fd /path/to/aurora/scripts/kernel-run.sh uefi
/path/to/aurora/scripts/compiler-test.sh
```

The [framebuffer preview](framebuffer-console.md#developer-preview) saves its PNG
and logs in a fresh directory under `build/`, uses Python standard-library image
encoding, and needs no externally pinned manifest or review receipt. It is not
qualified evidence. Its launcher also supports `--help`.

Both run/compiler wrappers support `--help`. The run wrapper calls the existing normal smoke
runner rather than maintaining a second QEMU recipe. It rejects inherited,
nonempty `KERNEL_TEST_*`, `KERNEL_USER_PROBE_MODE` and `UEFI_MODE` controls so that
an earlier fault-injection setting cannot silently change a normal boot.

The convenience wrappers are **standalone entrypoints**. They reject a nonempty
inherited `AURORA_TEST_CONTEXT` before dispatch, even if a context might be valid;
they do not join or override an existing supervised run. Start them outside that
run. When a context is present, Make validates it before the `run`, `run-uefi`
or `kernel-uefi` recipe can proceed. The wrappers still reject an inherited context after that check.
No shortcut promises unsupervised execution using an active sealed compiler.

## Dependencies and overrides

Install dependencies using your normal host package-management workflow:
GCC 16 with C++23 support, GNU Make, GNU binutils (`as`, `ld`, `objcopy`,
`objdump`, `nm`, `readelf`), Python 3 and Bash. The complete native graph also
uses GNU coreutils and ripgrep. QEMU boots additionally need GNU `timeout`,
QEMU system x86-64 and its matching PC firmware/data files. UEFI needs a
readable x86-64 OVMF firmware: a combined ROM or a matching CODE/VARS pair.
The canonical native tests require Meson 1.12.1+ and Ninja as well.

The scripts do not download or install tools. Missing dependencies fail with a
nonzero status. The run wrapper checks QEMU, timeout and requested firmware
paths before building; both image builders check their required tools before
creating output directories. UEFI also checks PE-linker support before compiling. A tool being present does not establish that its
version or configuration is qualified.

```sh
CXX=g++-16 make
CXX=g++-16 ./scripts/compiler-test.sh
make run CXX=g++-16 QEMU=/path/to/qemu-system-x86_64
make run-uefi OVMF_DIR=/path/to/firmware QEMU_DATA=/path/to/qemu/share
make run-uefi OVMF_CODE=/path/to/OVMF_CODE.fd OVMF_VARS=/path/to/OVMF_VARS.fd
```

`CXX` selects one GNU compiler executable, not a command containing flags or a
wrapper. The supervised test contract also rejects whitespace in the selected
`CXX` path; choose a simple executable name/path. It selects the bootstrap compiler and the trusted C++ compilation in
both image builders. Some inherited hosted-kernel tests still invoke `g++` from
`PATH`; `CXX` does not replace every host compiler invocation in the full graph.
GNU binutils are selected through `PATH`. See the [host-toolchain boot contract](../kernel/README.md#host-toolchain-boot-layout)
for required capabilities. UEFI needs GNU `ld`'s `i386pep` PE/COFF backend in
addition to the native ELF linker. `UEFI_LD` selects that PE linker explicitly;
otherwise the builder checks native `ld`, then `x86_64-w64-mingw32-ld`.
On Gentoo, `sys-devel/binutils[multitarget]` or `dev-util/mingw64-toolchain`
provides the additional target. Missing support fails with a dependency error,
not a request to replace the system compiler. For example:

```sh
make kernel-uefi UEFI_LD=x86_64-w64-mingw32-ld
```

`QEMU` selects one executable; quote shell values containing spaces. QEMU,
firmware and data paths with spaces are forwarded as single arguments.
`QEMU_DATA` optionally selects its matching
firmware/data directory (`-L`); it is useful for nonstandard installations.
With no override, UEFI searches conventional Debian/Ubuntu, Gentoo, Fedora and
Arch firmware directories for a matching non-Secure-Boot x86-64 pair, then a
combined ROM. `OVMF_DIR` searches only the specified directory. `OVMF` selects an
explicit combined ROM; alternatively set both `OVMF_CODE` and `OVMF_VARS` from the
same firmware build. Conflicting selectors and invalid paths fail before building.
Raw `.fd` files and split `.qcow2` files are supported. Automatic discovery only
selects named matching pairs; it never substitutes a Secure Boot image.

Combined ROMs use `-bios`. Split firmware uses read-only CODE pflash and a
disposable QEMU snapshot of the VARS template; installed files are never changed.
No firmware downloads, conversions or persistent variable store are performed.
Firmware paths are interpreted from the repository root unless absolute. These
path conventions are discovery support, not qualification of every distribution.

## Repeating host build checks

Run the same build-only check on each x86-64 Linux host:

```sh
CXX=g++ ./scripts/host-build-check.sh
CXX=g++ UEFI_LD=x86_64-w64-mingw32-ld ./scripts/host-build-check.sh
```

It checks dependencies, prints compiler/linker versions, refreshes the bootstrap
compiler and runs the existing BIOS/UEFI builders, image validators, hosted UEFI
and command-routing tests. Any failed gate stops the check. It does not download
tools, start QEMU or replace the full `make test` graph. Use a separate checkout
per host/toolchain; QEMU/firmware checks are a separate step. The standalone
check rejects inherited compiler pins, output selectors, Make control flags and
interactive or fault-injection settings so they cannot silently reduce or change
the run.

Checked on 2026-10-06:
- Debian 13: GCC 14.2 and binutils 2.44; complete `make test` native aggregate,
  compiler/BIOS/UEFI host-build check and normal split-firmware boot.
- Gentoo stage3 20261004: GCC 16.2.1_p20260926, binutils 2.47 and an explicit
  Gentoo-packaged PE linker 2.46.0.20260210; compiler, BIOS and UEFI builds;
  normal combined/split firmware, ACPI and write/execute-protection fault boots.
- Gentoo with Clang 22.1.8: bootstrap compiler builds; BIOS/UEFI image builds are
  unsupported and fail on GCC-only flags. The full native test driver remains GNU-only.

On 2026-10-07, the same GCC 16.2.1/binutils 2.47 and explicit PE-linker tuple
passed a fresh compiler build and `host-build-check.sh` on PR61 (`ead198439`).
Normal BIOS/UEFI images and the existing hosted/routing/firmware-selection checks
passed, followed by the complete optimized-Python frontend, class, signed-integer
and unsigned runners (207/74/84/95 checks). All 730 source hashes stayed unchanged.
The official Gentoo stage and PE package signatures were verified before use.
Independent retained-evidence review accepted this focused gate. No new guest
boot, full GCC 16 native aggregate or Clang qualification is claimed.

The Gentoo checks use an isolated Gentoo userland on the same Linux kernel as
the Debian host. They establish host-toolchain behavior, not a third distribution,
physical hardware support or complete emulator-matrix qualification. Assembly
memory primitives supply the freestanding calls emitted by GCC 16; no warning
or image-validation check is disabled.

## What the run commands do

The ordinary UEFI builder keeps disposable object files and compiler stack/callgraph
sidecars in `build/uefi/objects`. Each build clears that owned namespace by output
type, so future profile objects need no cleanup-name registration. Linkers and
image/stack admission read objects only there; unexpected objects in the admitted
inventory still fail closed. Published ELF/EFI paths are unchanged. Common kernel
objects are rebuilt on each invocation; compiler caches, logs and unrelated files
outside the namespace stay in place. Legacy top-level objects from older builders
are left untouched and are no longer link/admission inputs.

Graphical smoke stages only required current image/admission artifacts. Once all
guests and shared normal-image restoration pass, it discards that run's known
physical/PPM dumps and viewport probes. Summaries, logs, staged images and unknown
files remain. Failures and explicit keep-all/`.keep` preserve raw captures.
All cleanup paths are checked first; held no-follow directory handles anchor
deletion, and pins are rechecked before each removal.
A late pin or interruption preserves remaining dumps, but cannot recover deleted
ones. Cleanup errors only warn; no screen-hash receipt or availability state is
maintained. Standalone output and historical windows are not adopted for cleanup.
By default it retains the latest two successful and two failed run directories;
a failed build's available objects/artifacts are
moved within the same filesystem before normal restoration; small image/receipt
files are copied. Snapshot failures are reported, but restoration still runs and
may replace inputs that could not be retained. `AURORA_GRAPHICAL_KEEP_RUNS=N` changes each limit
(1..999); `all` skips pruning and pins the new run. An existing run can be pinned
with a `.keep` file inside its directory. Use this for independent-review windows,
including build-only images waiting for separate use. A separate runner invocation
pins a completed image window in this checkout before reading it; remove its
`.keep` only when review/use is finished. Managed images from another checkout
require an existing regular `.keep` pin created there before use; the reader does
not change that checkout's retention files. Pruning errors warn without changing the build/guest
result. Pins, unmarked older
runs, malformed records and unfinished runs (for example after SIGKILL) are not
pruned automatically and need deliberate manual cleanup. Retention serializes its
updates and never prunes an active/current window; builds still require one command
at a time as described above. See the [graphical smoke contract](framebuffer-console.md#current-source-graphical-smoke).

BIOS uses `pc`/TCG, `qemu64`, one CPU, 32 MiB RAM and the generated
`build/aurora.img`. UEFI uses `q35`/TCG, `qemu64`, one CPU, 128 MiB RAM and a
read-only generated FAT directory with a disposable snapshot overlay. Both run
without root or KVM, disable networking and graphical display, and capture
serial output. They boot the existing self-test payload and automatically exit;
there is no interactive shell or desktop. QEMU's stdin is always `/dev/null`, so
the same commands work from an interactive terminal and never change its mode.

The inherited limits are 15 seconds for BIOS and 30 seconds for UEFI. Serial
output is printed after QEMU exits and retained in `build/kernel-serial.log`
(BIOS) or `build/uefi/normal.log` (UEFI). The existing validators check the exact
expected serial sequence and QEMU status. QEMU's debug-exit success status is
33; the scripts return zero only after validation. Timeout, missing firmware,
unexpected exits or invalid transcripts fail. A BIOS success does not establish
UEFI success, and neither establishes physical AMD/Framework support.

## Reclaiming old local output explicitly

Stop builds, tests, guests and separate image readers before cleanup; do not start
another command while it runs. Preview the exact products and byte counts first:

```sh
make clean-dry-run
make clean
# Select one older configuration instead of the ordinary defaults:
make clean-dry-run MESON_BUILD_DIR=build/gcc16-retired
make clean MESON_BUILD_DIR=build/gcc16-retired
```

Without a selector, these targets visit only ordinary `build/meson-<16 hex digits>`
configurations whose Meson source/build metadata matches this checkout. There is
no compiler/toolchain hashing, configuration, compilation or test execution.
An explicit `MESON_BUILD_DIR` may select an external configured build belonging to
this checkout; another checkout's build, source-tree directories outside `build/`,
symlink paths and unknown ownership are refused. Default discovery reports and
skips rejected builds; an explicit rejected selection exits nonzero.

The command previews with `ninja -n -t clean`, validates every removal stays inside
the selected build, then invokes `ninja -t clean` without generator cleanup.
This removes tracked objects, depfiles, executables and native test binaries;
subsequent builds regenerate them. Counts include logical and allocated file
bytes, not a guarantee of freed disk blocks when files are shared or hardlinked.
Configuration, raw Meson logs, all untracked test scratch and outside output stay
in place. In particular, historical `aurora-meson-*` scratch has no durable
success/keep marker: cleanup cannot safely distinguish it from failed or explicitly
retained runs, so it does not delete it. Root bootstrap `build/aurorac`, BIOS/UEFI
output and user-supplied runner output are also outside this Meson product scope.

Cleanup honors `.keep` markers, the existing Aurora test lock and Meson configure
lock, and rejects observed direct processes using the selected output. The Linux
process check is best-effort: it inspects same-UID cwd/argv, not open file
descriptors or all users. It can spot direct Meson/Ninja commands that do not take
the Make wrapper lock, but cannot prevent a new command starting afterward; these
commands retain the repository's one-command-at-a-time requirement.
The generated Ninja graph is trusted and must remain unchanged between preview
and cleanup; these checks do not protect against concurrent graph mutation.

The scratch target currently retires older successful managed graphical smoke
windows. It does not classify or remove unmarked historical Meson scratch:

```sh
make clean-scratch-dry-run
make clean-scratch
```

This removes complete older successful windows, including their logs and receipts,
while keeping the newest two eligible successes. It uses the existing ownership
marker and retention lock, preserving every failed, running, unknown, malformed or
`.keep` window. Symlinks, nonregular files, nested keep markers and observed active
readers prevent removal. It does not touch Event evidence or other output roots.
The preview prints selected directories and their logical byte totals. These are
intentional local deletions: preserve any successful-run evidence needed for review
with `.keep` before cleanup. Neither target sweeps the whole `build` tree or adopts
unmarked historical output; retiring that evidence requires a separate explicit
ownership/review decision.

## Choosing tests

To exercise the actual Aurora Event consumer on hosted synthetic transport, use
an already [configured Meson build](meson-bootstrap.md):

```sh
meson test -C build/gcc16 iommu-event-source-native --print-errorlogs
```

Replace `build/gcc16` with your configured build directory. This incrementally
builds the selected test's dependencies and exercises sealed Event/Console
sessions; it does not run a guest or qualify live DMA. Build-only Event images
remain available through `UEFI_MODE=iommu-event-success ./scripts/kernel-uefi-build.sh`.
For an actual current-source developer guest, use the separate opt-in target:

```sh
make smoke-iommu-event EVENT_BUILD_RECEIPT=/absolute/BUILD-RECEIPT.json \
  EVENT_CODE=/absolute/OVMF_CODE_4M.fd EVENT_VARS=/absolute/OVMF_VARS_4M.fd \
  EVENT_DATA=/absolute/qemu-data
```

This requires the [supported custom model and initial firmware bytes](../tools/qemu-amdvi/README.md#developer-event-runtime),
GNU mtools 4.0.48 with no system config, and ordinary QEMU/OVMF for normal
restoration. `MTOOLS_DIR` selects an installed tool directory; `EVENT_ESP_DIR`
is a validated raw-ESP alternative on unsupported mtools hosts. Missing tools,
files or required configuration and insufficient reserved space report `BLOCKED`
(exit 2), before building or allocating a run. Present but malformed, unsupported
or mismatched runtime inputs report `FAIL` (runner exit 1), as do actual build,
image-admission and guest defects.
GNU Make itself returns 2 for an unsuccessful recipe, so use the diagnostic label
when interpreting `make smoke-iommu-event`. Evidence is
retained outside source under `EVENT_OUTPUT_PARENT` (default system temporary
directory), with fixed budgets and a 1 GiB free floor. Remove only completed runs
you no longer need. `scripts/kernel-iommu-event-smoke.sh --build-only` checks fresh
images/ESPs and restores normal bytes without guests. See the
[developer scope and qualification boundary](iommu-dma-conformance.md#supported-local-developer-execution).
The generic UEFI launcher still rejects Event profiles; the fast hosted test
and default `smoke-all` remain unchanged.

- `./scripts/compiler-test.sh` or `make -C compiler test`: complete compiler-only
  Meson suite with dependency-tracked compiler and fixture builds.
- `make test-compiler`: the same compiler-only Meson selection.
- `make test`: complete Meson `full` suite. This does not run QEMU.
- `make run` and `make run-uefi`: one normal emulator gate each.
- `make smoke-console` and `make smoke-console-uefi`: automated BIOS/UEFI
  console acceptance through the existing private-PTY test. Both also run in
  `make smoke-all`. `make test-console` is native console-policy coverage only.
- `make smoke`, `make smoke-fault`, `make smoke-page-fault` and `make smoke-all`:
  existing targeted/fault/full emulator gates. Use these directly for injected
  modes; the normal wrapper deliberately rejects fault controls.
- `SANITIZE=1 ./scripts/kernel-tests.sh`: inherited hosted allocator sanitizer
  checks, not the complete native or emulator suite.

Ordinary developer tests do not require a historical compiler checksum or a prior
Meson setup. The Make/compiler shortcuts configure a fresh directory automatically,
then reuse dependency-tracked builds. With no `MESON_BUILD_DIR`, they choose a
stable directory keyed by toolchain and `CXXFLAGS`. An explicit directory may be
fresh or already configured for the same compiler and flags; mismatches fail before
building. Keep matching `gcc`/`g++` on PATH. Setup, compile and test failures stop
the command and return nonzero. Meson test logs stay under that build directory's
`meson-logs/`; these are not fresh-build qualification receipts.

See [the Meson guide](meson-bootstrap.md) for focused suites, flags and worker
controls, and the [developer-test contract](developer-test-contract.md) for the
separate pinned `make test-acceptance` workflow and historical `run.json` receipts.
These shortcuts do not add language, kernel, hardware or broad-host qualification
claims.

## Testing these shortcuts

`make test-developer-commands` runs the normal and optimized command-routing,
console-smoke routing, BAR-runner routing and firmware-selection Python checks.
`python3 -B tests/developer-commands.py` checks command routing, argument rejection,
dependency failures, inherited-context rejection, environment selectors and Make aliases in disposable fake-tool
fixtures. One case runs the real BIOS and UEFI smoke runners with a pseudo-terminal
stdin and a fake QEMU that records whether it received that terminal.
It never builds Aurora or starts real QEMU, and is not native/emulator
acceptance. Run it under `python3 -B -O` too; the tests use `unittest` assertions.
These checks remain separate from the existing compiler and native aggregate graphs.
`tests/kernel-console-routing.py` records the exact BIOS/UEFI PTY entrypoint
commands with fake builders and Python dispatch. It checks public Make routes,
preflight rejection, primary failure propagation and normal-image restoration;
failure-path cases run the real PTY entrypoint against fake failing/interrupted
emulators and check propagation/restoration, child cleanup and the original-clock
command.
These synthetic tests do not qualify guest behavior.

See [the focused verification record](local-development-results.md) for the
actual compiler-only and normal BIOS/UEFI checks, preserved failures and limits.

## Troubleshooting

- Missing executable: install/select that dependency on the host, then retry.
  Use `QEMU` and `CXX` for nondefault executable names.
- Firmware missing: set `OVMF_DIR`, `OVMF`, or both `OVMF_CODE`/`OVMF_VARS`; check `QEMU_DATA`
  belongs to the selected QEMU installation if PC BIOS lookup fails.
- Fault-control rejection: unset the named variable, or intentionally use the
  underlying smoke script for that fault mode.
- `FAIL: QEMU exit status 124` with an empty serial log, only from a terminal:
  checkouts before the stdin correction let QEMU inherit the terminal, and
  `timeout`'s background process group was stopped by `SIGTTOU`. Update, or run
  the older command with `</dev/null`.
- Build or boot failure: retain the terminal output, serial log and generated
  files. Report `g++ --version` (or your selected `CXX`), `as --version`,
  `ld --version`, QEMU version, the exact command and firmware path. Do not treat
  a blocked/failed gate as a pass or bypass image/serial checks.

## Interactive BIOS console

`make console` opens an opt-in QEMU serial prompt after the boot self-tests.
Commands are `help`, `status` and `exit`; the session has a five-minute limit.
The [console contract](kernel-console-contract.md) explains its 64-byte ASCII
editor, interrupt-driven idle wait and emulator-only limits. `make run` and
`make run-uefi` still complete automatically as before.

## Automated console acceptance

Run the bounded acceptance tests without typing into an interactive terminal:

```sh
make smoke-console
make smoke-console-uefi OVMF_DIR=/path/to/firmware
./scripts/kernel-console-smoke.sh bios
./scripts/kernel-console-smoke.sh uefi
```

The standalone wrapper rejects inherited native-test context and nonempty
`KERNEL_TEST_*`, `KERNEL_USER_PROBE_MODE`, `KERNEL_CONSOLE`, `UEFI_MODE` and
`UEFI_CONSOLE_HANDOFF` controls. It checks QEMU, Python, the image-builder tools,
requested QEMU data and, for UEFI, firmware and PE-linker selection before
starting any build or restoration. Missing prerequisites fail rather than skip.

The wrapper builds the console image (`KERNEL_CONSOLE=1` for BIOS,
`UEFI_MODE=console` for UEFI) and invokes `tests/kernel-console-pty.py`, adding
`--uefi` only for UEFI. That existing test owns the private PTY, 30-second
deadline, exact boot transcript validation, editing/rejection/recovery probes,
latency and idle-wait checks, clean exit-status check and UEFI original-clock
receipt. The wrapper does not replace validators or add clock acceleration.

After a console-image build starts, success, failure and handled interruption
all attempt to rebuild that platform's normal image. The PTY driver handles
SIGTERM by exiting through its cleanup, terminating and joining its detached
QEMU process before the wrapper restores. A failed prerequisite
does not trigger restoration. A test/build failure stays nonzero even if
restoration succeeds; a restoration failure also makes an otherwise successful
run fail. Logs and metrics remain in `build/kernel-console-pty.*` for BIOS or
`build/uefi/kernel-console-pty.*` for UEFI, with the UEFI command receipt in
`build/uefi/console-pty.clock.json`. Restoration builds an image; it is not an
additional normal guest-boot gate.

### Merge gates and retained test artifacts

Every merge or release requires the complete Meson `full` suite with GCC 16 on
the final integrated source, including after conflict resolution. `full` covers
`dev`, `slow` and the complete native root inventory; `make test` selects the
same graph, so a duplicate aggregate is not required. GCC 14 is optional targeted
compatibility evidence. Focused checks do not replace full coverage, independent
review or the separate normal BIOS/UEFI and affected-profile guest gates in the
[developer-test contract](developer-test-contract.md#gcc-16-merge-gates).

Retain Meson logs under the configured build directory and per-command artifacts
in their recorded run-owned locations, with source and actual tool identities.
The separate legacy supervised acceptance path retains its
`build/test-contract-*/tmp` and matching `run.json` contract.
Failed-run evidence is preserved; unrelated temporary directories are not cleaned.

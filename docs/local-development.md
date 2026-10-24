# Local development

The digest-pinned container is the supported reproducible development route.
Native GNU/Linux x86-64 setup is an advanced route requiring the exact pinned
tools below; other native tool versions are unsupported. Final qualification
still requires the GCC 16 `merge` suite, independent review, normal BIOS/UEFI boots and
affected image/fault/recovery/restoration gates. The GitHub Actions workflow only
packages the dependency image; it does not run product validation.

## Quick start

With Docker or Podman installed, start from the repository root.

Run `python3 scripts/bootstrap.py build --container` from the host checkout first.
Then open the pinned shell with `./scripts/container.sh bash` and configure both
current Meson graphs with the printed `-Dbootstrap_receipt` option, following the
[source-bootstrap recipe](../compiler/README.md#source-bootstrap). Then run:

```sh
make
make test
make run-uefi
```

The wrapper uses Docker when available, otherwise Podman. It recognizes Podman's
`docker` compatibility command by its version output and uses `--userns=keep-id`
for Podman, preserving the invoking user's ownership on the checkout mount.
Docker keeps its explicit `--user UID:GID` selection. Run as the checkout owner;
the wrapper does not change host ownership or permissions.

The wrapper forwards `MESON_BUILD_DIR`, `AURORA_BUILD_JOBS` and `AURORA_TEST_JOBS`
when set. Build paths are relative to the checkout inside `/workspace`, for example:

```sh
MESON_BUILD_DIR=build/container AURORA_BUILD_JOBS=2 ./scripts/container.sh make test
```

The default build refreshes missing old kernel options automatically without
wiping its files. Explicitly chosen builds keep their configuration; use a fresh
matching directory or reconfigure them yourself. `make clean` removes products
and preserves configuration.

## Advanced native setup

Select matching real `gcc` and `g++` on PATH, plus the reviewed binutils, Python,
Meson and Ninja. Check their actual versions; the name `g++` is not a version pin.
Run from the repository root in a path without whitespace. Do not mutate source,
a configured toolchain or a profile's products while they are being qualified.

```sh
make                         # native compiler and normal image graph
make kernel                  # normal BIOS image
make kernel-uefi              # normal UEFI image
make run                     # actual normal BIOS boot
make run-uefi                 # actual normal UEFI boot
make capture-framebuffer     # output-only PNG preview, not qualification
./scripts/compiler-test.sh   # compiler-only Meson suite
make test                    # normal native Meson full; does not start QEMU
make test-exhaustive         # separate whole-space library enumeration
```

Use `MESON_BUILD_DIR=build/gcc16` to select a stable configuration.
`AURORA_BUILD_JOBS` and `AURORA_TEST_JOBS` separately cap compilation and test
concurrency. The wrapper also sizes jobs from observed CPU/memory headroom;
see the [sizing policy and its containment limits](meson-bootstrap.md).
The [Meson guide](meson-bootstrap.md) specifies native targets, setup options,
profile selection, dependency tracking and full-suite coverage.

Run/compiler wrappers accept `--help` and work from another working directory.
They are standalone entrypoints: inherited `AURORA_TEST_CONTEXT` is rejected.
Normal launchers also reject nonempty fault/profile controls rather than silently
changing a normal boot. Explicit supervised/pinned workflows remain separate.

## Tools and explicit selections

The setup gate requires GCC and G++ 16.2.0, binutils 2.47, Meson 1.12.1 and
Ninja 1.13.2 exactly. Other GCC 16 patch versions are rejected too; major-version
compatibility is not a substitute for these pins. Required tools also include
GNU Make, Python 3, Bash, coreutils and ripgrep. Image-enabled configurations require a GNU PE
linker with `i386pep`, including for BIOS-only selection. Select the reviewed
linker explicitly with `UEFI_LD` or Meson's `-Duefi_ld`; do not rely on an implicit
host fallback. Hosted-only configurations use `-Dkernel_images=false` and cannot
qualify a full image-enabled pass.

`CXX` accepts one executable, not a command with flags. Some hosted checks invoke
bare `gcc`/`g++`, so changing `CXX` alone does not select the complete toolchain.
Changing compiler, linker, flags or runtime identity requires a separate matching
build directory. Implicit include/library environment variables are rejected;
see [build identity](meson-bootstrap.md).

Boots need QEMU system x86-64, its matching data/firmware and GNU `timeout`.
Set `QEMU` and, when needed, `QEMU_DATA` explicitly. Select a reviewed combined
OVMF ROM with `OVMF`, or a matching pair with both `OVMF_CODE` and `OVMF_VARS`.
`OVMF_DIR` is an optional directory selector; conflicting selectors reject.
Split firmware uses readonly CODE and a disposable snapshot of VARS. Installed
firmware is never modified; paths with spaces remain single arguments. No script
downloads tools or firmware. Missing inputs are blocked, not silently skipped.

Patched AMD-IOMMU Event QEMU and clean BAR/IVRS firmware have separate device
and trace oracles. The clean firmware package lives under
`/opt/aurora-fixtures/firmware`, with its fixed `VERSION` and reviewed policy patch.
An explicit `AURORA_BOOT_FIXTURE_PREFIX` selects an equivalent local package
prefix; receipts cannot choose that trust root.
The dependency image pins its distributed bytes; every smoke still checks cold
VARS, exact device/clock arguments, and the real serial and hardware traces.
Explicit `AURORA_BAR_FIRMWARE`/`AURORA_IVRS_FIRMWARE` fixture overrides retain the
existing external byte pins. Ordinary stock OVMF cannot replace clean firmware.

Without an explicit coverage input, BAR/IVRS runs generate real local coverage
inside their fresh output directory: one stock-firmware `bar-state` boot and a
stopped-CPU MSI-X probe, plus a stopped-CPU AMD-Vi probe for IVRS. The stopped-CPU probes
exercise only the existing reviewed same-value writes, with no namespace or BME.
The separate stock-firmware boot deliberately initializes NVMe to demonstrate
queue, doorbell and interrupt trace coverage.
They validate exact trace inventories and raw protocol/register/topology evidence.
No archived logs, copied control scripts or self-reported pass summary are needed.
Family wrappers reuse this newly validated coverage through the existing explicit
`AURORA_BAR_COVERAGE` or `AURORA_IVRS_COVERAGE` path for the rest of that invocation.
There is no persistent control cache. Explicit external coverage is revalidated;
a malformed or mismatching input fails rather than becoming a missing prerequisite.

For a combined local qualification, start with one IVRS case, then explicitly
reuse its generated BAR and IVRS coverage for the remaining family cases:

```sh
python3 scripts/kernel-uefi-device-run.py ivrs-default --output "$run/setup-ivrs"
export AURORA_IVRS_COVERAGE="$run/setup-ivrs/controls/ivrs-coverage.json"
export AURORA_BAR_COVERAGE="$run/setup-ivrs/controls/bar-coverage.json"
AURORA_BAR_RECEIPTS="$run/bar" scripts/kernel-run.sh bar
AURORA_IVRS_RECEIPTS="$run/ivrs" scripts/kernel-run.sh ivrs
python3 scripts/kernel-uefi-device-run.py bar-prepare --output "$run/bar-prepare"
```

Choose a fresh absolute `$run` and the selected QEMU/data/stock OVMF first. This
uses one setup stock boot, one MSI-X probe and one AMD-Vi probe total; family
cases still perform all their own cold boots. A new clean-firmware build remains
unqualified until the final-source local real guest gates pass. See
[IOMMU conformance](iommu-dma-conformance.md) and
[BAR admission](../kernel/uefi/BAR-RESOURCE-CONTRACT.md).

## Parallel guest validation

Build and admit the selected native profiles in one dependency-tracked build
phase before starting parallel guests. Keep that source/tool selection and those image directories unchanged
until all workers settle. Ordinary developer commands still build by default.
Explicit `--run-only` skips compilation, like Meson's `--no-rebuild`; it is an
orchestration contract, not permission to skip build dependencies or admission.

```sh
build="$(realpath build/meson)"
run="$(mktemp -d "$PWD/build/guests.XXXXXX")"
./scripts/kernel-uefi-smoke.sh --run-only "$build/kernel-images/uefi/dispatch" \
    --output-dir "$run/dispatch" dispatch
```

The BIOS smoke wrapper has the same options. Each output directory must be new
and outside the input profile. Serial logs, clock records and copied metadata
are private; BIOS uses a snapshot and UEFI retains read-only ESP/private VARS.
Existing independent validators, clocks and timeouts still run. Up to four
separate guest processes can use different admitted profiles after staging;
there is no concurrent Ninja writer or new scheduler.

BAR/IVRS runners also accept `--run-only "$profile" --output "$fresh_output"`.
That route requires explicit validated coverage from the setup phase and never
regenerates setup controls. Protected-console PTY already takes `--build-dir`
and allocates private evidence. Simple console PTY accepts `--output-dir` too.
Console-service qualification accepts `--normal-build-dir "$normal_profile"`
so each fault worker performs its actual normal restoration with private logs
and no build. Event orchestration uses `capture_staged` in separate processes,
then the existing normal boot after all owned children settle; admission state
is process-local. A staged Event ESP master and its private guest copy consume
64 MiB each, so select Event concurrency from disk headroom rather than CPU count.

## Packaged development environment

The dependency-only `ci/Containerfile` pins GCC 16.2.0, binutils 2.47, QEMU 10.0.13,
OVMF 2025.02, Meson 1.12.1, Ninja 1.13.2, nlohmann_json 3.11.3, clang-format and
clangd 22.1.8, Ruff 0.16.7 and mtools 4.0.48. The packaging workflow records
package manifests during its build and retrieves the actual registry digest.
The public image is published and selected by its exact digest in `ci/image`.
Packaging performs no product validation; final product checks run locally.

`scripts/container.sh` supports anonymous pulls of that public digest. It uses
a container with dropped capabilities, a readonly root filesystem, a writable
checkout mount for build outputs, and no runtime network. Advanced native
validation uses explicitly selected exact tool versions; it does not claim
byte-identical container execution. The container removes
its `/etc/mtools.conf` for the deterministic ESP contract; it never edits the host's
configuration. The image includes the Event runtime and clean BAR/IVRS firmware.
Their source archives, reviewed patches and build recipes remain under
`/opt/aurora-event/share/source` and `/opt/aurora-fixtures/share/source`.
BAR/IVRS launchers validate the selected firmware and device configuration.

The Event-capable package exports `EVENT_TOOL_PREFIX=/opt/aurora-event`.
An explicitly selected equivalent local prefix is also supported. Its fixed
`runtime.json` marker names model `aurora-amdvi-command-stop-v1`, QEMU 10.0.13
and OVMF `2025.02-8+deb13u1`; fixed tool paths and versions are checked once at
startup. The pinned package/image is the tool trust boundary: normal packaged
smokes do not rehash executables, libraries or source files, copy installed tools,
or emit new tool-provenance records. This does not establish guest correctness;
current image/FAT admission and the actual Event serial/RAM oracles still apply.
The optional external `EVENT_BUILD_RECEIPT`, `EVENT_CODE`, `EVENT_VARS` and
`EVENT_DATA` route retains its selected-input integrity checks. A contradictory
provided manifest fails; missing prerequisites block. Do not combine the two
selectors. A stock-only image remains incomplete for Event.

## Native images and guest transport

`scripts/kernel-run.sh PROFILE [--console|--smoke]` owns normal and console
launch routing; existing Make and console-script commands remain aliases.
`bios`/`uefi` default to normal smoke; `--console` selects the ordinary interactive
console. `bios-console`/`uefi-console` default to interactive sessions, or select
`--smoke` for their existing PTY acceptance checks. Protected `program-console`
(an alias of `production`, the one production UEFI image) and existing
`program-*` fault profiles default to their protected PTY smoke; only
`program-console --console` (or `production --console`) opens an interactive
protected session.

The shared launcher uses the existing profile builders and semantic oracles.
Lower-level serial smoke adapters retain fault modes, clock plans and isolated
run-only contracts. Specialized workflows share the public entrypoint:
`iommu-event` and `graphical-console` run their existing smoke/restoration gates,
with `--build-only` retaining their separate build-only behavior. `framebuffer`
defaults to one unqualified PNG preview; `--smoke` or `--full-smoke` runs all four
cases and normal restoration. `bar`/`ivrs` run their coverage-reusing families;
individual `bar-*`/`ivrs-*` profiles retain required `--output DIR` and optional
`--run-only IMAGE` arguments after `--smoke`. These routes reject `--console`.
Their existing admission, pixel, trace and behavioral oracle adapters remain separate.
Images use `<build>/kernel-images/<bios|uefi>/<profile>` from the native builder.
Normal and specialized outputs coexist; there is no shared-image restoration
build. Each profile exports exact object, `.su`, `.ci` and `.source.json` inputs
from one compilation for current source/object/link admission.

Six Python entrypoints share `scripts/qemu_transport.py`: BAR, IVRS, framebuffer
probe/capture, graphical smoke and IOMMU Event smoke. Ordinary BIOS/UEFI smokes,
the BIOS/program console PTY tests and all three interactive wrappers also share
its argv/lifecycle. Interactive wrappers retain
`timeout --foreground --kill-after=2` to preserve terminal ownership.

BIOS keeps pc/TCG/qemu64, one CPU and 32 MiB. UEFI keeps q35/TCG/qemu64, one CPU
and 128 MiB. The helper centralizes bounded serial/QMP I/O, timeouts, owned-process
startup/reaping and failure classification. It does not merge pixel, protocol,
clock or authority oracles. Event supplies its explicit patched-model/device/
firmware tuple. Preview reuses capture transport and its production firmware
builder. Compiler-free controls establish transport behavior only.

Normal smoke stdin is `/dev/null`; no root, KVM, network or physical-device access
is needed. Normal BIOS/UEFI wall limits are 15/30 seconds. Exact serial validation
and QEMU debug-exit status 33 are required; logs stay beside the selected image.
Missing prerequisites are BLOCKED; malformed/tampered inputs and runtime failures
are FAIL. An image build, timeout or skipped guest is never a boot pass.

BAR/IVRS have isolated profile outputs and need no final normal rebuild. Graphical
and Event qualification still actually boot a separately staged normal image.
They retain failures and explicit keeps. Within retained graphical windows,
only successful disposable pixel dumps/probes may be discarded; logs, summaries
and staged images remain. Default managed-window retention is the two newest
successful runs and all failed or active runs, with `AURORA_GRAPHICAL_KEEP_RUNS=all` and `.keep` protection.
See [graphical retention](framebuffer-console.md#restoration-and-retention).
Event retains its diagnostic artifacts. None of these gates qualifies hardware.

## Reclaiming old local output explicitly

Stop builds, tests, guests and image readers before cleanup, and do not start
another command while it runs. Cleanup does not scan processes or coordinate locks.

```sh
make clean-dry-run
make clean
make clean MESON_BUILD_DIR=build/gcc16
make clean-scratch-dry-run CLEAN_PATHS='build/review-old build/old-build'
make clean-scratch CLEAN_PATHS='build/review-old build/old-build'
```

Product cleanup uses ordinary `meson compile --clean` for a selected build, or
existing `build/meson` and `build/meson-compiler` configurations by default. Meson source/build
metadata must match the checkout. Configuration, logs and untracked scratch stay;
future builds regenerate tracked products.

Scratch cleanup removes only explicit `CLEAN_PATHS`, including their logs and
historical/failed evidence. Review the paths and preserve needed evidence first.
Selections must stay below this checkout's `build/`; its root and escaping
symlinks reject. `.keep` at or under the selection, or in its build ancestry,
blocks deletion. An explicit current `MESON_BUILD_DIR` and its configuration are
protected. This is caller-stopped local deletion, without concurrent-race or
open-file guarantees.

## Choosing tests and consoles

- `make test`: the `merge` suite; `make test-release`: the opt-in `release`
  suite (releases, compiler bumps); `make -C compiler test`
  and `scripts/compiler-test.sh` select the same compiler-only Meson suite.
- `make test-exhaustive`: the separate whole-space UTF-8 library sweeps; see
  [normal and exhaustive scope](meson-bootstrap.md#coverage-and-limits).
- Use `meson test -C BUILD --suite compiler` for compiler-only selection, or
  `--suite dev`, `--suite core`, `--suite bytes`, `--suite packages` or exact test
  names for focused feedback.
  Partial profiles never become full acceptance by accumulation.
- `make smoke`, `make smoke-fault`, `make smoke-page-fault`, `make smoke-all` and
  the affected profile commands exercise actual emulator behavior.
- `meson test -C build/meson --suite full` covers hosted allocator checks, not all
  native code and not generated Aurora assembly.
- `make test-developer-commands` checks command routing with fake tools, without
  compiling Aurora or starting a real guest. It is not native acceptance.

Developer shortcuts reuse the matching predecessor-configured dependency graph. Setup, compile and test failures stop the command. Raw test logs stay in
`<build>/meson-logs`; a selected compiler hash proves stability, not a fresh-build
or external-pin claim. The [test contract](developer-test-contract.md) defines
identity, bounds and the historical receipt boundary.

`make console`, `make console-uefi` and `make program-console-uefi` provide bounded
interactive serial sessions. Read the [console guide](native-console-service.md)
and [protected command guide](program-console-contract.md) for grammar, capacities,
authority and limitations. These are emulator diagnostics, not a general terminal
or shell. `make smoke-console` / `make smoke-console-uefi` run the existing private
PTY acceptance with 30-second deadlines and editing/rejection/recovery checks.

Simple console smoke uses isolated products and performs no normal rebuild or
normal boot afterward. The PTY driver terminates and joins its owned QEMU on exit
or handled interruption. Its log/metrics and UEFI clock receipt live in
`<build>/kernel-images/<bios|uefi>/console/`. Protected PTY evidence stays under
`build/program-console-evidence/`; explicit retained qualification commands can
still use its selected `build/uefi` inputs. Final normal BIOS/UEFI boots remain
separate merge/release requirements.

## Emulator clock policy

`scripts/kernel_emulator_clock.py` is the explicit family/mode map. Bounded UEFI
service-budget/dispatch/user-phase timer profiles select
`-icount shift=0,align=off,sleep=off`; excluded profiles retain their original
clock. Unknown, empty or conflicting options reject. There is no adaptive retry
or arbitrary clock override. Exact argv, CPU count, firmware/device identity and
timeout are part of qualification.

Instruction-clock success establishes that emulator profile only. The original
wall-clock `user-retire-pending` exhaustion remains an unresolved stress limitation;
an isolated success did not establish a fix or cause. BIOS wall-clock scheduling
and physical timers require separate qualification. Restoring image bytes is
not the same as successfully booting that image.

# Local development

Use the selected pinned GNU/Linux x86-64 toolchain. Final qualification runs
locally: GCC 16 `full`, independent review, normal BIOS/UEFI boots and affected
image/fault/recovery/restoration gates. Container packaging does not replace them.

## Quick start

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
make test                    # complete native Meson full; does not start QEMU
```

Use `MESON_BUILD_DIR=build/gcc16` to select a stable configuration.
`AURORA_BUILD_JOBS` and `AURORA_TEST_JOBS` separately control compilation and tests.
The [Meson guide](meson-bootstrap.md) specifies native targets, setup options,
profile selection, dependency tracking and full-suite coverage.

Run/compiler wrappers accept `--help` and work from another working directory.
They are standalone entrypoints: inherited `AURORA_TEST_CONTEXT` is rejected.
Normal launchers also reject nonempty fault/profile controls rather than silently
changing a normal boot. Explicit supervised/pinned workflows remain separate.

## Tools and explicit selections

Required tools include GCC 16/C++23, GNU Make/binutils, Python 3, Bash, coreutils,
ripgrep, Meson 1.12.1+ and Ninja. Image-enabled configurations require a GNU PE
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

Patched AMD-IOMMU Event QEMU and clean BAR firmware are separate tuples with
separate device/trace oracles. Ordinary installed QEMU/OVMF cannot stand in for
them. See [IOMMU conformance](iommu-dma-conformance.md) and
[BAR admission](../kernel/uefi/BAR-RESOURCE-CONTRACT.md).

## Packaged development environment

The dependency-only `ci/Containerfile` pins GCC 16.2.0, binutils 2.47, QEMU 10.0.13,
OVMF 2025.02, Meson 1.12.1, Ninja 1.13.2, nlohmann_json 3.11.3, clang-format and
clangd 22.1.8, Ruff 0.16.7 and mtools 4.0.48. The packaging workflow records
package manifests during its build and retrieves the actual registry digest.
The public image is published and selected by its exact digest in `ci/image`.
Packaging performs no product validation; final product checks run locally.

`scripts/container.sh` supports anonymous pulls of that public digest. It uses
a nonprivileged container with a readonly root filesystem, a writable checkout
mount for build outputs, and no runtime network. Local validation uses explicitly selected comparable
tools; it does not claim byte-identical container execution. The container removes
its `/etc/mtools.conf` for the deterministic ESP contract; it never edits the host's
configuration. The image includes the Event runtime; BAR/IVRS launchers still validate their
selected firmware and device configuration.

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

Thin build/smoke/console launchers select a named native Meson profile and use its
returned image directory under `<build>/kernel-images/<bios|uefi>/<profile>`.
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
and staged images remain. Default managed-window retention is two successful and
two failed windows, with `AURORA_GRAPHICAL_KEEP_RUNS=all` and `.keep` protection.
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

- `make test`: final native `full`; `make test-compiler`, `make -C compiler test`
  and `scripts/compiler-test.sh` select the same compiler-only Meson suite.
- Meson `dev`, `core`, `bytes`, `packages` or exact test names give focused feedback.
  Partial profiles never become full acceptance by accumulation.
- `make smoke`, `make smoke-fault`, `make smoke-page-fault`, `make smoke-all` and
  the affected profile commands exercise actual emulator behavior.
- `SANITIZE=1 ./scripts/kernel-tests.sh` covers hosted allocator checks, not all
  native code and not generated Aurora assembly.
- `make test-developer-commands` checks command routing with fake tools, without
  compiling Aurora or starting a real guest. It is not native acceptance.

Developer shortcuts configure when needed and reuse matching dependency-tracked
builds. Setup, compile and test failures stop the command. Raw test logs stay in
`<build>/meson-logs`; a selected compiler hash proves stability, not a fresh-build
or external-pin claim. The [test contract](developer-test-contract.md) defines
identity, bounds and the separate legacy pinned acceptance workflow.

`make console`, `make console-uefi` and `make console-programs` provide bounded
interactive serial sessions. Read the [console guide](native-console-service.md)
and [protected command guide](program-console-contract.md) for grammar, capacities,
authority and limitations. These are emulator diagnostics, not a general terminal
or shell. `make smoke-console` / `make smoke-console-uefi` run the existing private
PTY acceptance with 30-second deadlines and editing/rejection/recovery checks.

Simple console smoke uses isolated products and performs no normal rebuild or
normal boot afterward. The PTY driver terminates and joins its owned QEMU on exit
or handled interruption. Its log/metrics and UEFI clock receipt live in
`<build>/kernel-images/<bios|uefi>/console/`. Protected PTY evidence stays under
`build/program-console-evidence/`; explicit reviewed legacy qualification can
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

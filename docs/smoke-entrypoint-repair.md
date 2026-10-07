# BAR and console smoke entrypoints

The public emulator entrypoints are separate from `make test`, which remains a
native-only aggregate. Missing emulator prerequisites fail; they are never
silently skipped or credited as a successful guest run.

## CPU-only NVMe preparation

`make smoke-nvme-prepare` builds `bar-prepare`, runs the namespace-free QEMU
fixture, validates its complete serial, hardware trace and provenance receipts,
and rebuilds the normal UEFI image afterward. This prepares CPU-owned queue
pages only. It does not enable DMA, publish queues, submit commands, attach a
namespace backend or read a disk.

This specialized qualification gate needs the existing exact BAR fixture, not
just an arbitrary QEMU/OVMF installation. Select these retained inputs:

- `QEMU`: the executable matching the existing BAR provenance SHA-256. If unset,
  the runner searches `PATH` for `qemu-system-x86_64`, then still checks that pin.
- `QEMU_DATA`: the matching QEMU data directory, explicitly bound to `-L`.
- `LD_LIBRARY_PATH`: the qualified runtime library directory, required by the
  existing provenance contract.
- `AURORA_BAR_FIRMWARE`: the qualified clean firmware fixture root containing
  `output/OVMF_CODE.fd`, `output/OVMF_VARS.fd` and
  `provenance/policy-three-file.patch`. All three existing pins must match.
- `AURORA_BAR_COVERAGE`: retained coverage JSON with `events`, `available_events`,
  `stock_trace` and `msix_control` paths. Relative paths resolve beside the JSON.
  The complete enabled inventory and both retained controls must validate.
- `AURORA_NVME_RECEIPTS`: a fresh, absent output directory outside the shared
  `build/uefi` image tree. Files, existing directories and dangling symlinks reject.

For example, after obtaining the separately qualified fixture and control
artifacts, run from the repository root:

```sh
LD_LIBRARY_PATH=/qualified/qemu/lib make smoke-nvme-prepare \
    QEMU=/qualified/qemu/bin/qemu-system-x86_64 \
    QEMU_DATA=/qualified/qemu/share/qemu \
    AURORA_BAR_FIRMWARE=/qualified/clean-firmware \
    AURORA_BAR_COVERAGE=/qualified/controls/coverage.json \
    AURORA_NVME_RECEIPTS=/new/receipts/nvme-prepare
```

These are placeholders for already qualified inputs, not downloadable packages
or a way to qualify a new installation. See the immutable pins in
[the provenance validator](../tests/kernel-uefi-bar-provenance.py), the
[BAR contract](../kernel/uefi/BAR-RESOURCE-CONTRACT.md) and
[preparation results](nvme-queue-preparation-results.md). Ordinary stock firmware
cannot replace the clean fixture. A different QEMU binary, missing control
artifact or incomplete trace coverage rejects before the build. No pins or
validators are disabled to make this command run.

`make smoke-uefi-bar` uses the same runner for its existing BAR controls. It also
requires `OVMF` to select the separately pinned stock combined ROM and
`AURORA_BAR_RECEIPTS` as the parent of fresh per-mode receipt directories.
`make smoke-all` retains those specialized prerequisites as well as its other
emulator dependencies. The independent normal `make run-uefi` entrypoint can
still discover installed non-Secure-Boot firmware; that discovery does not
qualify a clean BAR fixture.

Use the ordinary build dependencies documented in
[local development](local-development.md). `AURORAC`, when supplied directly to
the BAR runner, must name an executable compiler; otherwise the UEFI builder
builds the compiler normally. Run only one build or emulator command at a time
per checkout. Unset inherited fault/console/native-supervisor controls before a
standalone BAR run. Paths embedded in comma-separated QEMU options cannot contain
commas or line breaks.

Preflight failures create no receipt directory and never start restoration.
Once an image builder starts, both success and failure attempt one normal-image
restoration. `build.log` and `restore.log` remain in the exact requested directory;
serial, trace and provenance receipts remain mandatory. A restoration failure
cannot produce a PASS. If validation and restoration both fail, the original
validation error remains visible and the restoration error is reported too.
A rebuilt normal image is not itself evidence of a normal restoration boot.

## Automated console acceptance

- `make smoke-console`: build the BIOS console, run the existing real private-PTY
  acceptance test and restore the normal BIOS image.
- `make smoke-console-uefi`: the corresponding UEFI console gate, using installed
  firmware discovery or the explicit selectors from local development.
- `make smoke-all`: includes both console gates alongside its existing emulator
  matrix. This does not make console tests part of the native-only `make test`.

The acceptance oracle remains `tests/kernel-console-pty.py`, with `--uefi` for
UEFI. Its startup/serial/status, editing/rejection/recovery, latency, idle wait
and clean-exit checks remain intact. The original TCG clock and bounded private
PTY are unchanged. `make console` and `make console-uefi` remain interactive
sessions; use the smoke targets for automated acceptance.

## Focused regression controls

`make test-developer-commands` includes synthetic BAR preflight/lifecycle and
console-routing tests in ordinary and optimized Python. These use disposable
fixtures/stub tools and do not build Aurora or launch QEMU. They are wiring and
rejection evidence only, not a substitute for the actual emulator gates above.

## Focused repair evidence — 2026-10-07

The defect was reproduced against PR69 source using the public
`make smoke-nvme-prepare` target in a disposable fixture with a recording stub
builder. It raised `KeyError: 'AURORA_BAR_FIRMWARE'`, created the output directory
and invoked a normal-image build despite never beginning the requested build.
The repaired public target reports the missing variable and qualified-fixture
requirement, creates no output directory and starts no builder.

Independent review found two interruption lifecycle defects during repair:
an interrupted BAR builder could overlap normal restoration, and a killed PTY
runner could leave its detached QEMU alive. The BAR runner now kills/joins only
its owned build process group before restoration and handles SIGTERM through
that lifecycle. The PTY runner handles SIGTERM through its existing emulator
cleanup. Synthetic delayed-child and process-group termination controls verify
that stale builders/QEMU cannot outlive restoration. The PTY oracle and clock
logic are unchanged; their function ASTs match the original despite formatting.

The first emulator-clock dependency run rejected a stale historical BAR runner
whole-file hash. That pin already differed from PR69 after NVMe preparation.
It is replaced by executing the real BAR launch assembly against recording
substitutes for all eight modes: exact complete argv, original clock, namespace-free
devices, detached stdin, deadline and mandatory serial/trace/provenance calls.
This is behavioral coverage, not an updated historical source pin. Qualified
QEMU, firmware and trace-event hashes remain unchanged. Other clock-gate pins
remain unchanged. The original failed gate log is retained.

Compiler-free checks passed in both ordinary and optimized Python:

- 26 BAR prerequisite, output, launch-array and restoration controls
- 19 public console route, rejection, status and process-lifetime controls
- Existing 30 developer-command and 15 firmware-selection controls

The qualified retained QEMU/firmware/coverage inputs also passed read-only
preflight. The complete 15-method emulator-clock suite passed in both modes.
Pinned Ruff 0.16.7 formatting/lint and shell/Python syntax checks passed.
The initial synthetic test run had a fixture-import error; its failed log is
retained separately from corrected results.

### Actual focused guests and final-source continuity

The six-step focused guest gate completed with exit zero on a frozen 782-file
PR69-based candidate. It used the qualified QEMU 10.0.13 binary and clean/stock
firmware/control artifacts, with the existing exact provenance pins. It reused
the qualified PR69 compiler SHA-256
`b7b3de01cf86910650f9da9324549e36c388896a04a0fcbb31d5b89b13acdd1d`;
all 55 compiler-source files matched. This is not a fresh compiler build.
Source and compiler identities remained stable during the gate.

Passed public commands, in order:

1. `make smoke-nvme-prepare` with a fresh receipt directory and documented inputs
2. `make run-uefi` for a subsequent normal UEFI rebuild and boot
3. `make smoke-console`
4. `make run` for a subsequent normal BIOS rebuild and boot
5. `make smoke-console-uefi`
6. `make run-uefi` for a subsequent normal UEFI rebuild and boot

Preparation passed the complete unchanged serial, trace and provenance validators,
including five unpublished pages, scrubbed cancellation and zero held/pool pages.
Both console PTY sessions passed the existing editing, rejection, recovery,
latency, idle-wait and exit checks with QEMU status 33. Both used the original
TCG clock. UEFI retained polling count 1,250,000; its bounded idle sample and the
BIOS sample each recorded zero CPU ticks. Those observations are not performance
or physical-hardware qualification.

After the actual guest run, final source review added one cancellation-only guard:
if the interrupted wait already reaped the builder, do not signal that released
PID. The guest-tested runner hash was
`75b07b48e2447129fd1a6e6ebe755e1358e9424cb268b324612a6d1dad67e525`;
the final runner hash is
`d3c9ee0ba4523840d59ef98f0f932d248421791d77d19cc97bc230123ce9598a`.
The exact reconstructed guest-tested bytes match the retained source manifest.
All functions except the exceptional cleanup in `run` are AST-identical,
including preflight and the complete launch/validator function. The final 26-case
suite covers the already-reaped child plus real SIGINT/SIGTERM descendant cleanup.
This is a reviewed composite with unchanged ordinary guest paths, not a claim
that final cleanup bytes were rerun in QEMU. All three subsequent normal rebuild-and-boot checks
and the original successful guest receipts remain retained.

No full `smoke-all`, full native aggregate, new firmware compatibility, device
activation, disk access or physical-hardware qualification is claimed.

### Composition with PR71

The publication candidate preserves merged PR70 formatter and PR71 diagnostic
changes. Its compiler sources exactly match reviewed PR71. Build-only comparison
used the qualified PR69 compiler above and the reviewed PR71 compiler SHA-256
`11bf0b84ec4aec1a404cb4f557f4984b51a088e7a2843006bbd9d2e51483a816`.
Five profile pairs were rebuilt in the joined source: BIOS normal/console and
UEFI normal/console/preparation. All 50 selected image, assembly and metadata
pairs were byte-identical. The preparation loader/payload/metadata also match
the retained actual guest receipt. Final BIOS and UEFI images were rebuilt normal
with the PR71 compiler and matched those normal-profile comparison artifacts.
This preserves exact-image evidence through the compiler-only join; it is not a
new guest run or fresh compiler build. Compiler-free public routing and clock
checks were repeated on the joined source. Independent review covers the scoped
source, image-continuity and retained-guest composite.

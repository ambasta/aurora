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
./scripts/compiler-test.sh   # fresh compiler, complete compiler-only tests
make test                    # fresh compiler, complete native aggregate
```

The executable scripts also work when invoked from another directory:

```sh
/path/to/aurora/scripts/kernel-run.sh bios
OVMF=/path/to/OVMF.fd /path/to/aurora/scripts/kernel-run.sh uefi
/path/to/aurora/scripts/compiler-test.sh
```

Both wrappers support `--help`. The run wrapper calls the existing normal smoke
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
GNU C++ with C++23 support, GNU Make, GNU binutils (`as`, `ld`, `objcopy`,
`objdump`, `nm`, `readelf`), Python 3 and Bash. The complete native graph also
uses GNU coreutils and ripgrep. QEMU boots additionally need GNU `timeout`,
QEMU system x86-64 and its matching PC firmware/data files. UEFI needs a
readable x86-64 OVMF firmware: a combined ROM or a matching CODE/VARS pair.

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

## Choosing tests

- `./scripts/compiler-test.sh` or `make -C compiler test`: complete compiler-only
  suite, through the existing fresh-build shared-compiler contract.
- `make test-compiler`: existing root compiler-test target; compiler scope only.
- `make test`: full native aggregate. This does not run QEMU.
- `make run` and `make run-uefi`: one normal emulator gate each.
- `make smoke`, `make smoke-fault`, `make smoke-page-fault` and `make smoke-all`:
  existing targeted/fault/full emulator gates. Use these directly for injected
  modes; the normal wrapper deliberately rejects fault controls.
- `SANITIZE=1 ./scripts/kernel-tests.sh`: inherited hosted allocator sanitizer
  checks, not the complete native or emulator suite.

Ordinary developer tests do not require a historical compiler checksum. They
build current compiler source once and retain receipts beneath
`build/test-contract-*`. Follow the [developer-test contract](developer-test-contract.md)
for supported `CXXFLAGS`/`IR_TEST_CXXFLAGS`, externally reviewed acceptance pins,
and interpreting a newly completed matching `run.json`. Exit zero or a printed
command alone is not aggregate acceptance. These shortcuts do not add new
language, kernel, hardware or broad-host qualification claims.

## Testing these shortcuts

`make test-developer-commands` runs the normal and optimized command-routing and
firmware-selection Python checks.
`python3 -B tests/developer-commands.py` checks command routing, argument rejection,
dependency failures, inherited-context rejection, environment selectors and Make aliases in disposable fake-tool
fixtures. One case runs the real BIOS and UEFI smoke runners with a pseudo-terminal
stdin and a fake QEMU that records whether it received that terminal.
It never builds Aurora or starts real QEMU, and is not native/emulator
acceptance. Run it under `python3 -B -O` too; the tests use `unittest` assertions.
It remains separate from the existing compiler and native aggregate graphs.

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

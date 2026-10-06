# Local development

These commands run on an x86-64 Linux development host. They build disposable
emulator images; they do not install Aurora or change the host bootloader.
Run only one build/test command at a time in a checkout: the existing scripts
share `build/`. Use a checkout path without whitespace: the inherited Make/test
recipes do not consistently quote every repository/output path. Invoking a script
from another working directory does not remove that checkout-path limitation.
Never write the images to a physical disk or attach user data.

## Quick start

From the repository root:

```sh
make help
make                         # compiler + BIOS image, without QEMU
make kernel-uefi             # separate UEFI loader/payload, without QEMU
make run                     # normal BIOS build and verified QEMU boot
OVMF=/path/to/OVMF.fd make run-uefi
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
or `kernel-uefi` recipe can proceed (`kernel-uefi` through its compiler
prerequisite). The wrappers still reject an inherited context after that check.
No shortcut promises unsupervised execution using an active sealed compiler.

## Dependencies and overrides

Install dependencies using your normal host package-management workflow:
GNU C++ with C++23 support, GNU Make, GNU binutils (`as`, `ld`, `objcopy`,
`objdump`, `nm`, `readelf`), Python 3 and Bash. The complete native graph also
uses GNU coreutils and ripgrep. QEMU boots additionally need GNU `timeout`,
QEMU system x86-64 and its matching PC firmware/data files. UEFI needs a
readable **combined OVMF ROM**, commonly named `OVMF.fd`.

The scripts do not download or install tools. Missing dependencies fail with a
nonzero status. The run wrapper checks QEMU, timeout and requested firmware
paths before building; both image builders check their required tools before
creating output directories. A tool being present does not establish that its
version or configuration is qualified.

```sh
CXX=g++-16 make
CXX=g++-16 ./scripts/compiler-test.sh
make run CXX=g++-16 QEMU=/path/to/qemu-system-x86_64
make run-uefi OVMF=/path/to/OVMF.fd QEMU_DATA=/path/to/qemu/share
```

`CXX` selects one GNU compiler executable, not a command containing flags or a
wrapper. The supervised test contract also rejects whitespace in the selected
`CXX` path; choose a simple executable name/path. It selects the bootstrap compiler and the trusted C++ compilation in
both image builders. Some inherited hosted-kernel tests still invoke `g++` from
`PATH`; `CXX` does not replace every host compiler invocation in the full graph.
GNU binutils are selected through `PATH`. See the [host-toolchain boot contract](../kernel/README.md#host-toolchain-boot-layout)
for required capabilities, including `ld`'s ELF and PE/COFF backends.

`QEMU` selects one executable; quote shell values containing spaces. QEMU,
firmware and data paths with spaces are forwarded as single arguments.
`QEMU_DATA` optionally selects its matching
firmware/data directory (`-L`); it is useful for nonstandard installations.
`OVMF` defaults to `/usr/share/ovmf/OVMF.fd`, but distribution paths differ.
The normal UEFI runner uses `-bios` with a combined ROM. A split
`OVMF_CODE.fd`/`OVMF_VARS.fd` pair is not a supported substitute for this command;
no automatic firmware conversion, download or persistent variable-store setup
is performed. Firmware paths supplied to these commands are interpreted from
the repository root unless absolute.

## What the run commands do

BIOS uses `pc`/TCG, `qemu64`, one CPU, 32 MiB RAM and the generated
`build/aurora.img`. UEFI uses `q35`/TCG, `qemu64`, one CPU, 128 MiB RAM and a
read-only generated FAT directory with a disposable snapshot overlay. Both run
without root or KVM, disable networking and graphical display, and capture
serial output. They boot the existing self-test payload and automatically exit;
there is no interactive shell or desktop.

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

`make test-developer-commands` runs the normal and optimized Python checks.
`python3 -B tests/developer-commands.py` checks command routing, argument rejection,
dependency failures, inherited-context rejection, environment selectors and Make aliases in disposable fake-tool
fixtures. It never builds Aurora or starts real QEMU, and is not native/emulator
acceptance. Run it under `python3 -B -O` too; the tests use `unittest` assertions.
It remains separate from the existing compiler and native aggregate graphs.

See [the focused verification record](local-development-results.md) for the
actual compiler-only and normal BIOS/UEFI checks, preserved failures and limits.

## Troubleshooting

- Missing executable: install/select that dependency on the host, then retry.
  Use `QEMU` and `CXX` for nondefault executable names.
- Firmware missing: set `OVMF` to an installed combined ROM; check `QEMU_DATA`
  belongs to the selected QEMU installation if PC BIOS lookup fails.
- Fault-control rejection: unset the named variable, or intentionally use the
  underlying smoke script for that fault mode.
- Build or boot failure: retain the terminal output, serial log and generated
  files. Report `g++ --version` (or your selected `CXX`), `as --version`,
  `ld --version`, QEMU version, the exact command and firmware path. Do not treat
  a blocked/failed gate as a pass or bypass image/serial checks.

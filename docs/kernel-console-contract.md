# Opt-in BIOS serial console

This first interactive profile runs the existing BIOS boot self-tests, then opens
a COM1 prompt inside QEMU instead of automatically exiting. `make console` builds
the separate profile and starts a five-minute foreground session. Type `exit` to
close QEMU sooner. `make run` and `make run-uefi` retain their self-test behavior.

The commands are exact, lowercase ASCII words:

- `help`: list the three commands
- `status`: report that boot self-tests passed and show the fixed line capacity
- `exit`: signal the disposable QEMU debug-exit device

There are no arguments, memory inspection, memory writes, process creation,
filesystem commands, keyboard/GPU support or physical-machine qualification.
The UEFI payload has no interactive profile yet. Do not write these images to a
physical disk or change a host bootloader.

## Input and trust boundary

Aurora's `kernel.console` module decides byte actions and classifies copied
command prefixes. The temporary C++ adapter owns a 64-byte array, validates each
storage action independently and provides UART/PIC I/O. No pointer or device
authority crosses the scalar policy seam. This is not an Aurora-native kernel.

Printable ASCII bytes are echoed. Backspace and DEL erase one byte, with an empty
line as a no-op. CR, LF and CRLF each finish one line. An empty line opens another
prompt. Exact 64-byte lines are valid input; a 65th printable byte rejects the
entire line. All other control bytes, non-ASCII bytes and observed UART receive
errors also reject the entire line. Rejection stays latched through backspaces
and suffixes until the next delimiter; the following line can proceed normally.
Unsupported bytes are never echoed as terminal escapes.

Only COM1's received-data interrupt is enabled. A private IRQ4 gate acknowledges
the remapped legacy PIC; the foreground loop drains bytes with interrupts masked.
When no input is ready, `sti; hlt; cli` waits atomically for the next IRQ instead
of polling continuously. Sustained input still consumes CPU; buffer storage,
per-byte policy, serial writes and host-session duration are bounded. This is a
single-CPU QEMU PC transport, not a general interrupt controller or device driver.

## Focused checks

    ./scripts/kernel-console-tests.sh
    SANITIZE=1 ./scripts/kernel-console-tests.sh
    KERNEL_CONSOLE=1 ./scripts/kernel-build.sh
    python3 -B tests/kernel-console-pty.py
    ./scripts/kernel-smoke.sh

The hosted test links real Aurora-generated policy and exercises all input byte
classes, editing, exact/over-capacity input, malformed lines and recovery. Its
optional sanitizer instruments the C++ adapter, not generated Aurora assembly.
The PTY test starts its own QEMU and private terminal, validates the original boot
self-tests, sends deterministic paced input and checks commands, CRLF, editing,
rejection, recovery, idle host CPU and exit within 30 seconds. The final normal
smoke rebuilds and verifies the default image. These are focused gates, not the
full native aggregate or full emulator matrix. Independent review is required.

## Focused prototype results — 2026-10-07

The hosted policy/editor test and fatal C++ AddressSanitizer/UBSan run passed.
The interactive image passed existing image/layout checks at 49,904 payload bytes,
below the 65,024-byte BIOS transport limit, with no unresolved symbols. The actual
QEMU PTY test passed all commands, CRLF/editing, exact and oversized input, invalid
control/non-ASCII rejection, recovery, idle CPU check and explicit exit status 33.
A subsequent normal rebuild/boot passed the existing serial validator and had no
console/serial-IRQ symbols or console prompt. Independent source and retained-
evidence review accepted this focused prototype; the reviewer did not rerun the
compiler, native tests or QEMU.

The first link attempt found duplicate compiler-generated reflection helpers when
two Aurora objects were linked. The console now compiles one combined entry,
preserving the BIOS language-value self-test. The first PTY validator run found
QEMU's stdio setup re-enabled terminal newline translation. The test preserves
raw evidence, normalizes startup carriage returns and resets its private PTY
before input; it also drains buffered output before interpreting process exit.
Those earlier failed attempts are not counted as passing gates.

The tested compiler SHA-256 is
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
QEMU 10.0.13 uses software emulation, the `pc` machine, `qemu64`, one CPU and
32 MiB RAM. This checkpoint does not qualify UEFI interaction, other host/firmware
combinations or physical hardware. Sanitizers cover the hosted C++ adapter only.

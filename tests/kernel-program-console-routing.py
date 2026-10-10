#!/usr/bin/env python3
"""Source routing guard for the real program runtime's UART diagnostic path."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def need(okay, reason):
    if not okay:
        raise ValueError(reason)


def clean(text):
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", text, flags=re.S)


def verify(runtime, program, timer):
    runtime, program, timer = map(clean, (runtime, program, timer))
    route = re.compile(
        r"(?:#ifdef AURORA_UEFI_PROGRAM_CONSOLE|"
        r"#ifdef AURORA_UEFI_SNAPSHOT\s*"
        r"class SnapshotDiagnostics final\s*\{\s*public:\s*"
        r"\[\[gnu::noinline\]\] static void text\(std::string_view value\)\s*\{\s*"
        r"hardware::Serial::text\(value\);\s*\}\s*"
        r"\[\[gnu::noinline\]\] static void number\(unsigned long long value\)\s*\{\s*"
        r"hardware::Serial::number\(value\);\s*\}\s*\};\s*"
        r"using Serial\s*=\s*SnapshotDiagnostics;\s*"
        r"#elif defined\(AURORA_UEFI_PROGRAM_CONSOLE\))\s*"
        r"using Serial\s*=\s*console::Uart<hardware::Io,\s*console::FifoTrigger::fourteen>;\s*"
        r"#else\s*using hardware::Serial;\s*#endif"
    )
    need(len(route.findall(runtime)) == 1, "Runtime and input must select the same sticky UART specialization")
    runtime = route.sub("", runtime)
    need(re.search(r"using ProgramSerial\s*=\s*Serial;", program), "Program input must alias runtime diagnostics")
    for name, text in (("runtime.cpp", runtime), ("program-console.inc", program), ("service-timer.inc", timer)):
        need(
            not re.search(r"hardware\s*::\s*Serial|0x0*3fd\b|\b1021\b", text, re.I),
            "Raw serial/error-clearing LSR access in program runtime include chain: " + name,
        )
    need(
        re.search(r"program_console_interrupt\(vector,\s*error,\s*pc,\s*cs,\s*frame\)", runtime),
        "Shared IRQ dispatcher must route console ownership before runtime handling",
    )


def main():
    runtime = (ROOT / "kernel/uefi/runtime.cpp").read_text()
    program = (ROOT / "kernel/uefi/program-console.inc").read_text()
    timer = (ROOT / "kernel/uefi/service-timer.inc").read_text()
    verify(runtime, program, timer)
    # Formatting changes preserve the exact specialization and ordered arguments.
    formatted = """
#ifdef AURORA_UEFI_PROGRAM_CONSOLE
using Serial = console::Uart<hardware::Io, console::FifoTrigger::fourteen>;
#else
using hardware::Serial;
#endif
if (program_console_interrupt(vector, error, pc, cs, frame)) return;
"""
    alias = "using ProgramSerial = Serial;"
    verify(formatted, alias, "")
    verify(formatted.replace(" = ", "=").replace(", ", ","), alias.replace(" = ", "="), "")
    # Only the exact output-only helper in the mutually exclusive snapshot arm
    # may use raw serial. The active console arm still owns the sticky latch.
    snapshot = """
#ifdef AURORA_UEFI_SNAPSHOT
class SnapshotDiagnostics final {
public:
    [[gnu::noinline]] static void text(std::string_view value) { hardware::Serial::text(value); }
    [[gnu::noinline]] static void number(unsigned long long value) { hardware::Serial::number(value); }
};
using Serial = SnapshotDiagnostics;
#elif defined(AURORA_UEFI_PROGRAM_CONSOLE)
"""
    combined = formatted.replace("#ifdef AURORA_UEFI_PROGRAM_CONSOLE", snapshot)
    verify(combined, alias, "")
    verify(combined.replace(" = ", "=").replace(", ", ","), alias, "")
    invalid = (
        (formatted.replace("FifoTrigger::fourteen", "FifoTrigger::one"), alias, ""),
        (formatted.replace("error, pc", "pc, error"), alias, ""),
        (formatted.replace("#ifdef AURORA_UEFI_PROGRAM_CONSOLE", "#ifndef AURORA_UEFI_PROGRAM_CONSOLE"), alias, ""),
        (formatted + formatted, alias, ""),
        (formatted + " hardware::Serial::put(42);", alias, ""),
        (formatted, "using ProgramSerial = Other;", ""),
        (formatted, alias + " read(0x3fd);", ""),
        (formatted, alias, "read(1021);"),
        (combined.replace("#ifdef AURORA_UEFI_SNAPSHOT", "#ifndef AURORA_UEFI_SNAPSHOT"), alias, ""),
        (combined.replace("#elif defined(AURORA_UEFI_PROGRAM_CONSOLE)", "#else"), alias, ""),
        (combined.replace("using Serial = SnapshotDiagnostics;", "using Serial = hardware::Serial;"), alias, ""),
        (combined.replace("hardware::Serial::text(value);", "hardware::Serial::read();"), alias, ""),
        (combined.replace("hardware::Serial::number(value);", "read(0x3fd);"), alias, ""),
        (combined + " hardware::Serial::put(42);", alias, ""),
    )
    for inputs in invalid:
        try:
            verify(*inputs)
        except ValueError:
            continue
        raise ValueError("Accepted changed UART routing contract")
    print("PASS: program UART routing, four formatting variants and fourteen negative controls")


if __name__ == "__main__":
    main()

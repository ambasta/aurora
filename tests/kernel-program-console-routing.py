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
        r"(?:#ifdef AURORA_UEFI_SNAPSHOT|"
        r"#if defined\(AURORA_UEFI_SNAPSHOT\) \|\| (?:defined\(AURORA_BLOCKING_CALL\)|"
        r"\(defined\(AURORA_BLOCKING_CALL\) && !defined\(AURORA_FILE_CALL\)\)))\s*"
        r"class SnapshotDiagnostics final\s*\{\s*public:\s*"
        r"\[\[gnu::noinline\]\] static void text\(std::string_view value\)\s*\{\s*"
        r"hardware::Serial::text\(value\);\s*\}\s*"
        r"\[\[gnu::noinline\]\] static void number\(unsigned long long value\)\s*\{\s*"
        r"hardware::Serial::number\(value\);\s*\}\s*\};\s*"
        r"using Serial\s*=\s*SnapshotDiagnostics;\s*"
        r"#elif defined\(AURORA_UEFI_PROGRAM_CONSOLE\))\s*"
        r"(?:using Serial\s*=\s*console::Uart<hardware::Io,\s*console::FifoTrigger::fourteen>;|"
        r"class ProgramSerialAdapter final\s*\{\s*"
        r"using Uart\s*=\s*console::Uart<hardware::Io,\s*console::FifoTrigger::fourteen>;\s*public:\s*"
        r"static void initialize_input\(\)\s*\{\s*Uart::initialize_input\(\);\s*\}\s*"
        r"static auto next\(\)\s*->\s*console::Sample\s*\{\s*return Uart::next\(\);\s*\}\s*"
        r"static auto try_put\(std::uint8_t byte\)\s*->\s*console::PutResult\s*\{\s*"
        r"return Uart::try_put\(byte\);\s*\}\s*"
        r"static void put\(std::uint8_t byte\)\s*\{\s*Uart::put\(byte\);\s*\}\s*"
        r"\[\[gnu::noinline\]\] static void text\(std::string_view value\)\s*\{\s*Uart::text\(value\);\s*\}\s*"
        r"\[\[gnu::noinline\]\] static void number\(U64 value\)\s*\{\s*Uart::number\(value\);\s*\}\s*\};\s*"
        r"using Serial\s*=\s*ProgramSerialAdapter;)\s*"
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
    call_snapshot = combined.replace(
        "#ifdef AURORA_UEFI_SNAPSHOT", "#if defined(AURORA_UEFI_SNAPSHOT) || defined(AURORA_BLOCKING_CALL)"
    )
    verify(call_snapshot, alias, "")
    adapter = """
class ProgramSerialAdapter final {
    using Uart = console::Uart<hardware::Io, console::FifoTrigger::fourteen>;
public:
    static void initialize_input() { Uart::initialize_input(); }
    static auto next() -> console::Sample { return Uart::next(); }
    static auto try_put(std::uint8_t byte) -> console::PutResult { return Uart::try_put(byte); }
    static void put(std::uint8_t byte) { Uart::put(byte); }
    [[gnu::noinline]] static void text(std::string_view value) { Uart::text(value); }
    [[gnu::noinline]] static void number(U64 value) { Uart::number(value); }
};
using Serial = ProgramSerialAdapter;
"""
    factored = combined.replace("using Serial = console::Uart<hardware::Io, console::FifoTrigger::fourteen>;", adapter)
    verify(factored, alias, "")
    invalid = (
        (call_snapshot.replace("defined(AURORA_BLOCKING_CALL)", "defined(AURORA_UEFI_PROGRAM_CONSOLE)"), alias, ""),
        (call_snapshot.replace("||", "&&"), alias, ""),
        (factored.replace("Uart::text(value)", "hardware::Serial::text(value)"), alias, ""),
        (factored.replace("Uart::number(value)", "hardware::Serial::number(value)"), alias, ""),
        (factored.replace("return Uart::next()", "return Other::next()"), alias, ""),
        (factored.replace("return Uart::try_put(byte)", "return Other::try_put(byte)"), alias, ""),
        (factored.replace("Uart::put(byte)", "read(0x3fd)"), alias, ""),
        (factored.replace("FifoTrigger::fourteen", "FifoTrigger::one"), alias, ""),
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
    print("PASS: program UART routing, formatting variants, shared sticky Console adapter and negative controls")


if __name__ == "__main__":
    main()

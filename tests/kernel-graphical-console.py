#!/usr/bin/env python3
"""Complete hosted graphical consumer gate, shared by root Make and Meson slow.

--run selects an existing compiler; this runner never builds aurorac. Direct and
Make runs require an explicit compiler pin or controlled developer-build receipt.
Meson uses --developer-selected-compiler, recording observed stability only.
The earlier 67-case hosted result remains scoped to its historical source. A new
run retains compact comparisons and generated artifacts, not guest qualification.
"""

from pathlib import Path
import argparse
import json
import re
import sys
import os
import shlex
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "scripts"))
from compiler_contract import add_identity_arguments, digest, file_record, resolve_identity, validate_identity_selection
from package_profiles import SelectedCompiler

SOURCE_INPUTS = (
    "tests/kernel-graphical-console.py",
    "tests/kernel-graphical-console.cpp",
    "tests/kernel_graphical_oracle.py",
    "examples/kernel-graphical-console.au",
    "examples/kernel-display-service.au",
    "library/graphics/font5x7.au",
    "library/console/line.au",
    "library/console/session_note.au",
    "library/console/session_files.au",
    "library/std/binary.au",
    "library/std/binary_buffer.au",
    "library/std/bytes.au",
    "kernel/uefi/graphical-console-entry.S",
    "scripts/compiler_contract.py",
    "scripts/package_profiles.py",
)


def source_inputs():
    """Account for the observer's complete local quoted-header closure."""
    pending = [ROOT / name for name in SOURCE_INPUTS]
    paths = set()
    while pending:
        path = pending.pop().resolve(strict=True)
        require(path.is_relative_to(ROOT), "source dependency escapes repository")
        if path in paths:
            continue
        paths.add(path)
        if path.suffix in (".cpp", ".hpp"):
            for name in re.findall(r'^\s*#include\s+"([^\"]+)"', path.read_text(), re.MULTILINE):
                pending.append(path.parent / name)
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(paths)}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, metavar="COMPILER")
    add_identity_arguments(parser)
    parser.add_argument("--developer-selected-compiler", action="store_true")
    parser.add_argument("--artifacts", type=Path, help="fresh output directory; defaults below TMPDIR")
    args = parser.parse_args(argv)
    if args.developer_selected_compiler:
        require(
            args.compiler_sha256 is None and args.developer_build_receipt is None,
            "developer-selected compiler cannot claim a pin or fresh-build receipt",
        )
        require(
            not os.environ.get("AURORA_TEST_CONTEXT"), "developer-selected compiler cannot enter an aggregate context"
        )
    else:
        validate_identity_selection(args)
    return args


def command(argv, work, name, check=True):
    argv = [str(item) for item in argv]
    write_json(work / (name + ".command.json"), dict(argv=argv, status="running"))
    try:
        result = subprocess.run(argv, check=False, capture_output=True, timeout=180)
    except BaseException as error:
        (work / (name + ".stdout")).write_bytes(getattr(error, "stdout", None) or b"")
        (work / (name + ".stderr")).write_bytes(getattr(error, "stderr", None) or b"")
        write_json(
            work / (name + ".command.json"),
            dict(argv=argv, status="failed", error=str(error), exception_type=type(error).__name__),
        )
        raise
    (work / (name + ".stdout")).write_bytes(result.stdout)
    (work / (name + ".stderr")).write_bytes(result.stderr)
    write_json(work / (name + ".command.json"), dict(argv=argv, status="completed", returncode=result.returncode))
    if check:
        require(result.returncode == 0, f"{name} failed; see retained stderr")
    return result


def retain_case(work, records, **data):
    out = data.pop("output")
    data["output_sha256"] = {path.name: digest(path) for path in sorted(out.iterdir()) if path.is_file()}
    data.update(status="passed", raw_outputs="compacted after match")
    data["comparison"] = (
        "pre-entry no-service/no-store denial" if "returncode" in data else "complete bytes and ordered stores"
    )
    write_json(work / f"case-{len(records):03}.json", data)
    records.append({key: data[key] for key in ("name", "geometry", "status")})


def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))


def drift_checks():
    graphical = (ROOT / "examples/kernel-graphical-console.au").read_text()
    display = (ROOT / "examples/kernel-display-service.au").read_text()
    for consumer in (graphical, display):
        require("import graphics.font5x7;" in consumer, "shared font import missing")
        require("auto glyph_bits(" not in consumer, "duplicated base font")


def samples(text):
    return [(1, byte, 0) for byte in text.encode("ascii")]


def cases():
    exit_tail = samples("exit\rSHOULD-NOT-BE-CONSUMED")
    yield "exit", exit_tail
    yield "editing", samples("hez\blp\r\nstatus\nx\x7fy\n\b\x7f\n") + exit_tail
    yield "commands", samples("help\nstatus\runknown\r\n\nwrite note x\ncat note\n") + exit_tail
    yield "note-replace", samples("cat note\nwrite note old suffix\ncat note\nwrite note x\ncat note\n") + exit_tail
    yield "note-empty", samples("write note old suffix\ncat note\nwrite note \ncat note\n") + exit_tail
    yield "note-edit-crlf", samples("write notf\be fixX\x7f! \r\ncat note\r\n") + exit_tail
    yield "note-malformed", samples("write note saved\nwrite notes x\nwrite note\ncat note\n") + exit_tail
    yield "note-control", samples("write note saved\nwrite note bad\x01\ncat note\n") + exit_tail
    yield (
        "note-nonascii",
        samples("write note saved\nwrite note bad") + [(1, 255, 0)] + samples("\ncat note\n") + exit_tail,
    )
    for name, damage in (("absent", (0, 0, 1)), ("byte", (1, ord("x"), 1)), ("enter", (1, 13, 1))):
        yield (
            "note-damage-" + name,
            samples("write note saved\nwrite note bad") + [damage] + samples("\ncat note\n") + exit_tail,
        )
    yield (
        "note-damaged-crlf",
        samples("write note saved\r") + [(1, 10, 1)] + samples("write note bad\ncat note\n") + exit_tail,
    )
    yield "note-maximum", samples("write note " + "Ab9 !" * 10 + "xyz" + "\ncat note\nexit\n")
    yield "note-overlong", samples("write note " + "x" * 54 + "\ncat note\nexit\n")
    yield "files-copy", samples("write a saved\ncopy a b\nwrite a x\ncat b\ncat a\ncopy b b\nexit\n!")
    yield "files-copy-full", samples("write a X\nwrite b \nwrite c \nwrite d \ncopy a e\ncopy a b\ncat b\nexit\n!")
    yield "files-copy-invalid", samples("write a x\ncopy a b c\ncopy a  b\ncopy a note\ncopy absent a\ncat a\nexit\n!")
    yield "files-demo", samples("write todo Ship Aurora\nwrite ideas Safer drivers\nls\ncat todo\nrm ideas\nexit\n!")
    yield (
        "files-capacity",
        samples("write a \nwrite b \nwrite c \nwrite d \nwrite e E\nwrite b X\nrm a\nwrite e E\nls\nexit\n!"),
    )
    yield "files-replace-empty", samples("write a old suffix\ncat a\nwrite a x\ncat a\nwrite a \ncat a\n") + exit_tail
    yield "files-missing", samples("ls\ncat a\nrm a\nwrite a x\nrm a\nls\ncat a\n") + exit_tail
    yield (
        "files-grammar",
        samples("write a x\nwrite a\ncat a x\nrm a x\nls a\nrm note\nrm .\ncat ..\ncat a\n") + exit_tail,
    )
    yield (
        "files-names",
        samples("write A._-09 y\ncat a._-09\ncat A._-09\nwrite a/b x\nwrite 123456789 x\nls\n") + exit_tail,
    )
    yield "files-maximum-content", samples("write a " + "Ab9 !" * 9 + "xyz!\ncat a\nexit\n!")
    yield "files-maximum-name", samples("write A1234567 " + "x" * 45 + "\ncat A1234567\nexit\n!")
    yield "files-overlong-content", samples("write a x\nwrite a " + "y" * 50 + "\ncat a\nexit\n!")
    yield (
        "files-rejected",
        samples("write a keep\nwrite a bad\x01\nwrite a bad")
        + [(1, 255, 0)]
        + samples("\nwrite a bad")
        + [(0, 0, 1)]
        + samples("\ncat a\n")
        + exit_tail,
    )
    # The combined limits take 83 bytes through exit, so this must exhaust the
    # unchanged 80-event budget after the successful read, before exit completes.
    yield "files-combined-budget", samples("write A1234567 " + "x" * 49 + "\ncat A1234567\nexit\n!")
    yield "capacity64", samples("x" * 64 + "\n") + exit_tail
    yield "overflow65", samples("x" * 65 + "\b\n") + exit_tail
    yield "bad-control", samples("abc") + [(1, 1, 0), (1, 255, 0)] + samples("help\n") + exit_tail
    yield "damage", [(0, 0, 1)] + samples("help\n") + [(1, ord("x"), 1), (1, 13, 1)] + exit_tail
    yield "damaged-crlf", samples("abc\r") + [(1, 10, 1)] + samples("help\n") + exit_tail
    yield "events80", samples("a" * 81)
    yield "samples96", [(0, 0, 1)] * 97
    # All printable glyphs must occur while editable, before capacity/event caps.
    for number, start in enumerate((32, 72, 112)):
        text = "".join(chr(byte) for byte in range(start, min(start + 40, 127)))
        yield f"printable-{number}", samples(text + "\n") + exit_tail


def check_case(binary, work, records, name, script, geometry, fail_after=None, sessions=1):
    from kernel_graphical_oracle import reference

    width, height, pitch, fmt = geometry
    out = work / name
    source = work / "script.txt"
    source.write_text("".join(f"{a} {b} {c}\n" for a, b, c in script))
    limit = (1 << 64) - 1 if fail_after is None else fail_after
    command([binary, *geometry, out, source, limit, "normal", sessions], work, f"case-{len(records):03}")
    expected = reference(
        script, width=width, height=height, pitch=pitch, pixel_format=fmt, fail_after=fail_after, sessions=sessions
    )
    report = json.loads((out / "report.json").read_text())
    require(report["completion"] == expected["completion"], (name, report))
    require(report["consumed"] == expected["consumed"], (name, report))
    require(report["entries"] == sessions and report["put_calls"] == 0, (name, report))
    require(report["next_calls"] == report["consumed"], (name, report))
    require(report["frames"] == len(expected["frames"]) == report["next_calls"] + sessions, (name, report))
    actual_stores = list(struct.iter_unpack("<QI", (out / "stores.bin").read_bytes()))
    require(actual_stores == expected["stores"], f"{name}: exact store sequence mismatch")
    require(report["stores"] == len(actual_stores), (name, report))
    failed = int(expected["completion"] == 2)
    require(report["pixel_calls"] == len(actual_stores) + failed, f"{name}: failed pixel retried")
    for index, frame in enumerate(expected["frames"]):
        require((out / f"frame-{index:03}.bin").read_bytes() == frame, f"{name}: frame {index} mismatch")
    require((out / "pixels.bin").read_bytes() == expected["pixels"], f"{name}: terminal framebuffer mismatch")
    count = len(actual_stores)
    retain_case(
        work,
        records,
        name=name,
        script=script,
        geometry=geometry,
        fail_after=fail_after,
        sessions=sessions,
        report=report,
        output=out,
    )
    shutil.rmtree(out)  # Successful raw buffers are compacted only after complete comparisons.
    print(f"PASS {name}: completion={report['completion']} samples={report['consumed']} stores={count}")
    return count


def check_font(compiler, work):
    from kernel_graphical_oracle import FONT

    source, assembly, harness, binary = (work / ("font-probe" + suffix) for suffix in (".au", ".s", ".cpp", ""))
    source.write_text(
        "module font_probe;\nimport graphics.font5x7;\n"
        "auto font_glyph(u8 byte) -> u64 { return graphics::glyph_bits(byte); }\n"
    )
    command([compiler, "--module-root", ROOT / "library", source, "-o", assembly], work, "font-compile")
    harness.write_text(
        "#include <cstdint>\n#include <cstdio>\n"
        'extern "C" std::uint64_t font_glyph(std::uint8_t);\n'
        "int main() { for (unsigned b = 0; b != 256; ++b) "
        'std::printf("%llu\\n", static_cast<unsigned long long>(font_glyph(b))); }\n'
    )
    command(shlex.split(os.environ.get("CXX", "g++")) + [harness, assembly, "-o", binary], work, "font-link")
    actual = [int(line) for line in command([binary], work, "font-run").stdout.splitlines()]
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :-"
    fallback = "11111/10000/10000/10000/10001/11010/11111"
    expected = []
    for byte in range(256):
        rows = FONT[chr(byte)] if chr(byte) in alphabet else fallback
        expected.append(sum((bit == "1") << index for index, bit in enumerate(rows.replace("/", ""))))
    require(actual == expected, "shared font: exhaustive byte mapping differs from independent visual rows")
    print("PASS shared font: all 256 byte mappings, including unsupported-byte fallback")


def execute_cases(compiler, work, records):
    check_font(compiler, work)
    assembly, obj, binary = work / "consumer.s", work / "consumer.o", work / "consumer"
    command(
        [compiler, "--module-root", ROOT / "library", ROOT / "examples/kernel-graphical-console.au", "-o", assembly],
        work,
        "compile",
    )
    command(["as", "--64", assembly, ROOT / "kernel/uefi/graphical-console-entry.S", "-o", obj], work, "assemble")
    command(
        shlex.split(os.environ.get("CXX", "g++"))
        + [
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-no-pie",
            str(ROOT / "tests/kernel-graphical-console.cpp"),
            str(obj),
            "-o",
            str(binary),
        ],
        work,
        "link",
    )
    for geometry in [(440, 146, 443, 0), (800, 600, 803, 1), (1024, 768, 1024, 0)]:
        for name, script in cases():
            check_case(binary, work, records, name, script, geometry)
    check_case(
        binary,
        work,
        records,
        "note-reset",
        samples("write note secret\nexit\ncat note\nexit\n"),
        (440, 146, 443, 1),
        sessions=2,
    )
    check_case(
        binary,
        work,
        records,
        "files-reset",
        samples("write a secret\nexit\ncat a\nls\nexit\n"),
        (440, 146, 443, 1),
        sessions=2,
    )
    geometry = (440, 146, 443, 1)
    for name, script in (
        ("failure", samples("hez\blp\nstatus\nexit\nUNCONSUMED")),
        ("note-failure", samples("write note saved\ncat note\nwrite note \ncat note\nexit\nUNCONSUMED")),
        ("files-failure", samples("write a saved\ncat a\nrm a\nls\nexit\nUNCONSUMED")),
    ):
        total = check_case(binary, work, records, name + "-baseline", script, geometry)
        positions = (0, 1, 53, 55, total // 2, total - 1) if name == "failure" else (total // 2, total - 1)
        for index in positions:
            check_case(binary, work, records, f"{name}-{index}", script, geometry, index)
    modes = [
        "null-record",
        "copied-record",
        "null-console",
        "null-display",
        "forged-console",
        "forged-display",
        "crossed",
        "duplicate-console",
        "duplicate-display",
        "zero-console",
        "zero-display",
        "max-console",
        "max-display",
        "width",
        "height",
        "not-quiet",
        "stale-console",
        "stale-display",
        "stale-both",
        "reentry",
    ]
    source = work / "script.txt"
    source.write_text("1 120 0\n")
    for mode, geometry in [(mode, (440, 146, 443, 1)) for mode in modes] + [
        ("geometry", (439, 146, 443, 1)),
        ("geometry", (440, 145, 443, 1)),
    ]:
        out = work / "denied"
        result = command(
            [binary, *geometry, out, source, (1 << 64) - 1, mode], work, f"case-{len(records):03}", check=False
        )
        require(result.returncode == 77, f"{mode}: pre-entry denial was not side-effect-free: {result.returncode}")
        require(
            not list(out.glob("frame-*.bin")) and (not (out / "report.json").exists()),
            "Acceptance condition failed: not list(out.glob('frame-*.bin')) and (not (out / 'report.json').exists())",
        )
        require(
            (out / "stores.bin").stat().st_size == 0,
            "Acceptance condition failed: (out / 'stores.bin').stat().st_size == 0",
        )
        retain_case(
            work,
            records,
            name="denied-" + mode,
            script=[(1, 120, 0)],
            geometry=geometry,
            returncode=result.returncode,
            output=out,
        )
        shutil.rmtree(out)
        print(f"PASS denied {mode}: no consumer entry or service operation")


def run_gate(args):
    compiler = args.run.resolve(strict=True)
    identity = (
        SelectedCompiler(compiler) if args.developer_selected_compiler else resolve_identity(args, compiler, ROOT)
    )
    inputs = source_inputs()
    host_argv = shlex.split(os.environ.get("CXX", "g++"))
    require(host_argv, "host compiler command is empty")
    tools = {name: file_record(shutil.which(name) or name) for name in (host_argv[0], "as")}
    drift_checks()
    if args.artifacts is None:
        work = Path(tempfile.mkdtemp(prefix="aurora-graphical-hosted-"))
    else:
        work = args.artifacts.absolute()
        require(not work.exists(), "artifacts directory must be fresh")
        require(not any(path.is_symlink() for path in (work, *work.parents)), "artifact symlink denied")
        work.mkdir(parents=True)
    print("Retained hosted graphical evidence: " + str(work), flush=True)
    records = []
    report = dict(
        schema="aurora-graphical-hosted-v1",
        status="running",
        scope="hosted-generated-consumer",
        compiler_identity=identity.record(),
        source_sha256=inputs,
        tools=tools,
        host_cxx_argv=host_argv,
        cases=records,
        native_complete=False,
        guest_executed=False,
        image_qualified=False,
    )
    write_json(work / "run.json", report)
    primary = None
    try:
        execute_cases(compiler, work, records)
        require(len(records) == 154, "incomplete hosted graphical case inventory")
    except BaseException as error:
        primary = error
        report.update(error=str(error), exception_type=type(error).__name__)
    try:
        identity.verify()
        require(source_inputs() == inputs, "hosted graphical source changed during gate")
        require(
            {name: file_record(record["path"]) for name, record in tools.items()} == tools,
            "host tools changed during gate",
        )
    except BaseException as error:
        report["finalization_error"] = str(error)
        if primary is None:
            primary = error
    report.update(
        status="failed" if primary else "passed",
        compiler_identity=identity.record(),
        case_count=len(records),
        expected_cases=dict(transcript_geometry=117, session_reset=2, output_failure=13, denial=22),
        generated_sha256={
            name: digest(work / name) for name in ("consumer.s", "consumer.o", "consumer") if (work / name).is_file()
        },
    )
    write_json(work / "run.json", report)
    if primary is not None:
        raise primary
    print("PASS: 154 hosted generated-consumer cases; no native image or guest qualification")
    return work


def main(argv=None):
    run_gate(arguments(argv))


if __name__ == "__main__":
    main()

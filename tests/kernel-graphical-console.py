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
    "examples/kernel-console-service.au",
    "examples/kernel-display-service.au",
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


def source_block(text, marker):
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def drift_checks():
    graphical = (ROOT / "examples/kernel-graphical-console.au").read_text()
    console = (ROOT / "examples/kernel-console-service.au").read_text()
    display = (ROOT / "examples/kernel-display-service.au").read_text()
    for marker in ("enum class ConsoleEvent", "class Line64"):
        require(source_block(graphical, marker) == source_block(console, marker), f"copied {marker} drift")
    marker = "auto glyph_bits(u8 byte)"
    require(source_block(graphical, marker) == source_block(display, marker), "legacy font drift")


def samples(text):
    return [(1, byte, 0) for byte in text.encode("ascii")]


def cases():
    exit_tail = samples("exit\rSHOULD-NOT-BE-CONSUMED")
    yield "exit", exit_tail
    yield "editing", samples("hez\blp\r\nstatus\nx\x7fy\n\b\x7f\n") + exit_tail
    yield "commands", samples("help\nstatus\runknown\r\n\n") + exit_tail
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


def check_case(binary, work, records, name, script, geometry, fail_after=None):
    from kernel_graphical_oracle import reference

    width, height, pitch, fmt = geometry
    out = work / name
    source = work / "script.txt"
    source.write_text("".join(f"{a} {b} {c}\n" for a, b, c in script))
    limit = (1 << 64) - 1 if fail_after is None else fail_after
    command([binary, *geometry, out, source, limit, "normal"], work, f"case-{len(records):03}")
    expected = reference(script, width=width, height=height, pitch=pitch, pixel_format=fmt, fail_after=fail_after)
    report = json.loads((out / "report.json").read_text())
    require(report["completion"] == expected["completion"], (name, report))
    require(report["consumed"] == expected["consumed"], (name, report))
    require(report["entries"] == 1 and report["put_calls"] == 0, (name, report))
    require(report["next_calls"] == report["consumed"], (name, report))
    require(report["frames"] == len(expected["frames"]) == report["next_calls"] + 1, (name, report))
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
        work, records, name=name, script=script, geometry=geometry, fail_after=fail_after, report=report, output=out
    )
    shutil.rmtree(out)  # Successful raw buffers are compacted only after complete comparisons.
    print(f"PASS {name}: completion={report['completion']} samples={report['consumed']} stores={count}")
    return count


def execute_cases(compiler, work, records):
    assembly, obj, binary = work / "consumer.s", work / "consumer.o", work / "consumer"
    command([compiler, ROOT / "examples/kernel-graphical-console.au", "-o", assembly], work, "compile")
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
    script = samples("hez\blp\nstatus\nexit\nUNCONSUMED")
    geometry = (440, 146, 443, 1)
    total = check_case(binary, work, records, "failure-baseline", script, geometry)
    for index in (0, 1, 53, total // 2, total - 1):
        check_case(binary, work, records, f"failure-{index}", script, geometry, index)
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
        require(len(records) == 67, "incomplete hosted graphical case inventory")
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
        expected_cases=dict(transcript_geometry=39, output_failure=6, denial=22),
        generated_sha256={
            name: digest(work / name) for name in ("consumer.s", "consumer.o", "consumer") if (work / name).is_file()
        },
    )
    write_json(work / "run.json", report)
    if primary is not None:
        raise primary
    print("PASS: 67 hosted generated-consumer cases; no native image or guest qualification")
    return work


def main(argv=None):
    run_gate(arguments(argv))


if __name__ == "__main__":
    main()

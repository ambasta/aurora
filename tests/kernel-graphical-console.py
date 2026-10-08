#!/usr/bin/env python3
"""UNRUN source-only preparation. Opt-in real generated graphical consumer gate.

Invocation (only after lane allocation): python3 tests/kernel-graphical-console.py
  --run /absolute/path/to/reviewed/aurorac
Not registered in Make/Meson. Does not execute unless --run is explicit.
"""
from pathlib import Path
import argparse
import json
import os
import shlex
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
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
        require(source_block(graphical, marker) == source_block(console, marker), f'copied {marker} drift')
    marker = "auto glyph_bits(u8 byte)"
    require(source_block(graphical, marker) == source_block(display, marker), 'legacy font drift')



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


def check_case(binary, work, name, script, geometry, fail_after=None):
    from kernel_graphical_oracle import reference
    width, height, pitch, fmt = geometry
    out = work / name
    source = work / "script.txt"
    source.write_text("".join(f"{a} {b} {c}\n" for a, b, c in script))
    limit = (1 << 64) - 1 if fail_after is None else fail_after
    subprocess.run([str(binary), *map(str, geometry), str(out), str(source), str(limit), "normal"], check=True)
    expected = reference(script, width=width, height=height, pitch=pitch, pixel_format=fmt, fail_after=fail_after)
    report = json.loads((out / "report.json").read_text())
    require(report['completion'] == expected['completion'], (name, report))
    require(report['consumed'] == expected['consumed'], (name, report))
    require(report['entries'] == 1 and report['put_calls'] == 0, (name, report))
    require(report['next_calls'] == report['consumed'], (name, report))
    require(report['frames'] == len(expected['frames']) == report['next_calls'] + 1, (name, report))
    actual_stores = list(struct.iter_unpack("<QI", (out / "stores.bin").read_bytes()))
    require(actual_stores == expected['stores'], f'{name}: exact store sequence mismatch')
    require(report['stores'] == len(actual_stores), (name, report))
    failed = int(expected["completion"] == 2)
    require(report['pixel_calls'] == len(actual_stores) + failed, f'{name}: failed pixel retried')
    for index, frame in enumerate(expected["frames"]):
        require((out / f'frame-{index:03}.bin').read_bytes() == frame, f'{name}: frame {index} mismatch')
    require((out / 'pixels.bin').read_bytes() == expected['pixels'], f'{name}: terminal framebuffer mismatch')
    count = len(actual_stores)
    shutil.rmtree(out)  # Bound scratch storage; this opt-in runner is not an evidence archive.
    print(f"PASS {name}: completion={report['completion']} samples={report['consumed']} stores={count}")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, metavar="COMPILER")
    args = parser.parse_args()
    compiler = args.run.resolve(strict=True)
    drift_checks()
    with tempfile.TemporaryDirectory(prefix="aurora-graphical-hosted-") as temporary:
        work = Path(temporary)
        assembly, obj, binary = work / "consumer.s", work / "consumer.o", work / "consumer"
        subprocess.run([str(compiler), str(ROOT / "examples/kernel-graphical-console.au"), "-o", str(assembly)], check=True)
        subprocess.run(["as", "--64", str(assembly), str(ROOT / "kernel/uefi/graphical-console-entry.S"), "-o", str(obj)], check=True)
        subprocess.run(shlex.split(os.environ.get("CXX", "g++")) + ["-std=c++23", "-O1", "-Wall", "-Wextra", "-Werror", "-no-pie", str(ROOT / "tests/kernel-graphical-console.cpp"), str(obj), "-o", str(binary)], check=True)
        for geometry in [(440, 146, 443, 0), (800, 600, 803, 1), (1024, 768, 1024, 0)]:
            for name, script in cases():
                check_case(binary, work, name, script, geometry)
        script = samples("hez\blp\nstatus\nexit\nUNCONSUMED")
        geometry = (440, 146, 443, 1)
        total = check_case(binary, work, "failure-baseline", script, geometry)
        for index in (0, 1, 53, total // 2, total - 1):
            check_case(binary, work, f"failure-{index}", script, geometry, index)
        modes = ["null-record", "copied-record", "null-console", "null-display", "forged-console", "forged-display", "crossed", "duplicate-console", "duplicate-display", "zero-console", "zero-display", "max-console", "max-display", "width", "height", "not-quiet", "stale-console", "stale-display", "stale-both", "reentry"]
        source = work / "script.txt"
        source.write_text("1 120 0\n")
        for mode, geometry in [(mode, (440, 146, 443, 1)) for mode in modes] + [("geometry", (439, 146, 443, 1)), ("geometry", (440, 145, 443, 1))]:
            out = work / "denied"
            result = subprocess.run([str(binary), *map(str, geometry), str(out), str(source), str((1 << 64) - 1), mode], check=False)
            require(result.returncode == 77, f'{mode}: pre-entry denial was not side-effect-free: {result.returncode}')
            require(not list(out.glob('frame-*.bin')) and (not (out / 'report.json').exists()), "Acceptance condition failed: not list(out.glob('frame-*.bin')) and (not (out / 'report.json').exists())")
            require((out / 'stores.bin').stat().st_size == 0, "Acceptance condition failed: (out / 'stores.bin').stat().st_size == 0")
            shutil.rmtree(out)
            print(f"PASS denied {mode}: no consumer entry or service operation")
    print("PASS: hosted generated consumer only; no native image or guest qualification")


if __name__ == "__main__":
    main()

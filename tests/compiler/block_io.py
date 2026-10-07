#!/usr/bin/env python3
"""Checked one-sector I/O against independent complete Python byte models."""

import argparse
import hashlib
from pathlib import Path
import random
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection, command, require, validate_values


ROOT = Path(__file__).resolve().parents[2]
IMPORTS = ("storage.block", "storage.sector", "storage.block_io", "storage.ram_sector")
SIZE = 512
ZERO = bytes(SIZE)
INITIAL = bytes((index * 53 + index // 256 * 31 + 7) % 256 for index in range(SIZE))
INVALID = (-(1 << 63), -1, 1, 2, 512, (1 << 63) - 1)


def byte_array(name, values):
    elements = ", ".join(f"{value}u8" for value in values)
    return f"const builtin::array<u8, {len(values)}> {name} = {{{elements}}};"


def make_sector(name, values):
    return (
        byte_array(name + "_bytes", values)
        + f"""
        storage::Sector512 {name} = storage::Sector512();
        i64 {name}_offset = 0;
        while ({name}_offset < 512) {{
            if ({name}.write_byte({name}_offset, {name}_bytes[{name}_offset]) != storage::BlockStatus::success) {{
                return 0u64;
            }}
            {name}_offset = {name}_offset + 1;
        }}
    """
    )


def check_sector(name, expected):
    return (
        "{"
        + byte_array("expected", expected)
        + f"""
        i64 offset = 0;
        while (offset < 512) {{
            const storage::BlockByteResult byte = {name}.read_byte(offset);
            if (byte.status() != storage::BlockStatus::success || byte.value_or(0u8) != expected[offset]) {{
                return 0u64;
            }}
            offset = offset + 1;
        }}
    """
        + "}"
    )


def check_device(expected, name="device"):
    return (
        "{"
        + f"""
        const storage::SectorReadResult report = {name}.read_sector(0);
        if (report.status() != storage::SectorIoStatus::success) {{
            return 0u64;
        }}
        const storage::Sector512 actual = report.sector_or_zero();
    """
        + check_sector("actual", expected)
        + "}"
    )


def seeded_device(read_only=False):
    body = (
        make_sector("initial", INITIAL)
        + """
        storage::RamSectorDevice device = storage::RamSectorDevice();
        if (device.write_sector(0, initial) != storage::SectorIoStatus::success) {
            return 0u64;
        }
    """
    )
    if read_only:
        body += """
            if (device.make_read_only() != storage::SectorIoStatus::success) {
                return 0u64;
            }
        """
    return body


def geometry_cases():
    yield Case(
        "exact geometry, zero initialization and canonical layouts",
        """
        const storage::RamSectorDevice device = storage::RamSectorDevice();
        const storage::SectorGeometry geometry = device.geometry();
        if (geometry.sector_size_bytes() != 512u64 || geometry.sector_count() != 1u64 || !geometry.can_write()) {
            return 0u64;
        }
        if (size_of(storage::Sector512) != 512 || size_of(storage::SectorReadResult) != 520 ||
            size_of(storage::RamSectorDevice) != 520 || size_of(storage::SectorGeometry) != 16 ||
            size_of(storage::SectorIoStatus) != 8 || size_of(storage::SectorFlushMode) != 8 ||
            size_of(storage::SectorFlushStatus) != 8) {
            return 0u64;
        }
        if (device.flush(storage::SectorFlushMode::visibility) != storage::SectorFlushStatus::volatile_complete ||
            device.flush(storage::SectorFlushMode::durable) != storage::SectorFlushStatus::unsupported) {
            return 0u64;
        }
    """
        + check_device(ZERO)
        + "return 42u64;",
        42,
        imports=IMPORTS,
    )
    for count in (0, 1, (1 << 63), (1 << 64) - 1):
        yield Case(
            f"geometry retains full-width count {count}",
            f"""
            const storage::SectorGeometry geometry = storage::SectorGeometry({count}u64, false);
            const storage::SectorGeometry saved = copy_geometry(geometry);
            if (saved.sector_size_bytes() != 512u64 || saved.can_write()) {{
                return 0u64;
            }}
            return saved.sector_count();
        """,
            count,
            imports=IMPORTS,
            prelude="""
            auto copy_geometry(storage::SectorGeometry value) -> storage::SectorGeometry {
                return value;
            }
        """,
        )
    for read_only in (False, True):
        yield Case(
            f"checked seeding copies all bytes, readonly={read_only}",
            seeded_device(read_only)
            + f"""
            initial.write_byte(0, 0u8);
            initial.write_byte(511, 0u8);
            const storage::SectorGeometry geometry = device.geometry();
            if (geometry.can_write() != {str(not read_only).lower()}) {{
                return 0u64;
            }}
        """
            + check_device(INITIAL)
            + "return 42u64;",
            42,
            imports=IMPORTS,
        )


def transfer_cases():
    rng = random.Random(512520)
    patterns = [
        ZERO,
        bytes([255]) * SIZE,
        INITIAL,
        bytes((index // 256) for index in range(SIZE)),
        bytes([0, 255, 128, 1]) * 128,
        bytes(rng.randrange(256) for _ in range(SIZE)),
    ]
    for index, pattern in enumerate(patterns):
        yield Case(
            f"complete sector write pattern {index}",
            seeded_device()
            + make_sector("input", pattern)
            + """
            if (device.write_sector(0, input) != storage::SectorIoStatus::success) {
                return 0u64;
            }
            input.write_byte(0, 3u8);
            input.write_byte(511, 9u8);
        """
            + check_device(pattern)
            + "return 42u64;",
            42,
            imports=IMPORTS,
        )
    yield Case(
        "every single byte position survives full-sector transport",
        """
        storage::RamSectorDevice device = storage::RamSectorDevice();
        i64 selected = 0;
        while (selected < 512) {
            storage::Sector512 input = storage::Sector512();
            input.write_byte(selected, 255u8);
            if (device.write_sector(0, input) != storage::SectorIoStatus::success) {
                return 0u64;
            }
            const storage::SectorReadResult report = device.read_sector(0);
            if (report.status() != storage::SectorIoStatus::success) {
                return 0u64;
            }
            const storage::Sector512 actual = report.sector_or_zero();
            i64 offset = 0;
            while (offset < 512) {
                u8 expected = 0u8;
                if (offset == selected) {
                    expected = 255u8;
                }
                const storage::BlockByteResult byte = actual.read_byte(offset);
                if (byte.status() != storage::BlockStatus::success || byte.value_or(0u8) != expected) {
                    return 0u64;
                }
                offset = offset + 1;
            }
            selected = selected + 1;
        }
        return 42u64;
    """,
        42,
        imports=IMPORTS,
    )
    yield Case(
        "read report and extracted copy survive overwrite",
        seeded_device()
        + """
        const storage::SectorReadResult saved = device.read_sector(0);
        const storage::SectorReadResult returned = copy_report(saved);
        const storage::Sector512 zero = storage::Sector512();
        device.write_sector(0, zero);
        storage::Sector512 changed = returned.sector_or_zero();
        changed.write_byte(0, 0u8);
        changed.write_byte(511, 0u8);
        const storage::Sector512 snapshot = returned.sector_or_zero();
        if (saved.status() != storage::SectorIoStatus::success ||
            returned.status() != storage::SectorIoStatus::success) {
            return 0u64;
        }
    """
        + check_sector("snapshot", INITIAL)
        + check_device(ZERO)
        + "return 42u64;",
        42,
        imports=IMPORTS,
        prelude="""
        auto copy_report(storage::SectorReadResult report) -> storage::SectorReadResult {
            return report;
        }
    """,
    )
    for read_only in (False, True):
        yield Case(
            f"device copies retain independent bytes and readonly flag {read_only}",
            seeded_device(read_only)
            + """
            storage::RamSectorDevice copy = copy_device(device);
            const storage::SectorGeometry before = device.geometry();
            const storage::SectorGeometry copied = copy.geometry();
            if (before.can_write() != copied.can_write()) {
                return 0u64;
            }
            const storage::Sector512 zero = storage::Sector512();
        """
            + (
                """
            if (copy.write_sector(0, zero) != storage::SectorIoStatus::read_only) {
                return 0u64;
            }
        """
                + check_device(INITIAL, "copy")
                if read_only
                else """
            if (copy.write_sector(0, zero) != storage::SectorIoStatus::success) {
                return 0u64;
            }
            copy.make_read_only();
            const storage::SectorGeometry unchanged = device.geometry();
            if (!unchanged.can_write()) {
                return 0u64;
            }
        """
                + check_device(ZERO, "copy")
            )
            + check_device(INITIAL)
            + "return 42u64;",
            42,
            imports=IMPORTS,
            prelude="""
            auto copy_device(storage::RamSectorDevice value) -> storage::RamSectorDevice {
                return value;
            }
        """,
        )


def failure_cases():
    for read_only in (False, True):
        for index in INVALID:
            yield Case(
                f"range error {index} precedes readonly {read_only} and preserves every byte",
                seeded_device(read_only)
                + make_sector("input", bytes([255]) * SIZE)
                + f"""
                if (device.write_sector({index}, input) != storage::SectorIoStatus::out_of_range) {{
                    return 0u64;
                }}
                const storage::SectorReadResult failed = device.read_sector({index});
                if (failed.status() != storage::SectorIoStatus::out_of_range) {{
                    return 0u64;
                }}
                const storage::Sector512 masked = failed.sector_or_zero();
                const storage::SectorGeometry geometry = device.geometry();
                if (geometry.can_write() != {str(not read_only).lower()}) {{
                    return 0u64;
                }}
            """
                + check_sector("masked", ZERO)
                + check_device(INITIAL)
                + "return 42u64;",
                42,
                imports=IMPORTS,
            )
    yield Case(
        "readonly is one-way, idempotent and preserves data and prior geometry",
        seeded_device()
        + """
        const storage::SectorGeometry before = device.geometry();
        if (device.make_read_only() != storage::SectorIoStatus::success ||
            device.make_read_only() != storage::SectorIoStatus::success) {
            return 0u64;
        }
        const storage::SectorGeometry after = device.geometry();
        if (!before.can_write() || after.can_write()) {
            return 0u64;
        }
        const storage::Sector512 zero = storage::Sector512();
        if (device.write_sector(0, zero) != storage::SectorIoStatus::read_only) {
            return 0u64;
        }
    """
        + check_device(INITIAL)
        + "return 42u64;",
        42,
        imports=IMPORTS,
    )
    for status in ("out_of_range", "read_only"):
        yield Case(
            f"public {status} report masks every nonzero payload byte",
            make_sector("input", INITIAL)
            + f"""
            const storage::SectorReadResult failed =
                storage::SectorReadResult(storage::SectorIoStatus::{status}, input);
            input.write_byte(0, 0u8);
            const storage::Sector512 masked = failed.sector_or_zero();
            if (failed.status() != storage::SectorIoStatus::{status}) {{
                return 0u64;
            }}
        """
            + check_sector("masked", ZERO)
            + "return 42u64;",
            42,
            imports=IMPORTS,
        )


def flush_cases():
    for read_only in (False, True):
        yield Case(
            f"visibility and rejected durable flush preserve every byte readonly={read_only}",
            seeded_device(read_only)
            + """
            i64 repeat = 0;
            while (repeat < 3) {
                if (device.flush(storage::SectorFlushMode::visibility) !=
                    storage::SectorFlushStatus::volatile_complete ||
                    device.flush(storage::SectorFlushMode::durable) != storage::SectorFlushStatus::unsupported) {
                    return 0u64;
                }
                repeat = repeat + 1;
            }
        """
            + check_device(INITIAL)
            + f"""
            const storage::SectorGeometry geometry = device.geometry();
            if (geometry.can_write() != {str(not read_only).lower()}) {{
                return 0u64;
            }}
            return 42u64;
        """,
            42,
            imports=IMPORTS,
        )
    rng = random.Random(512001)
    for sequence in range(4):
        body = seeded_device()
        model = INITIAL
        readonly = False
        for operation in range(9):
            if operation == 5:
                body += "device.make_read_only();"
                readonly = True
            elif operation % 3 == 2:
                body += """
                    if (device.flush(storage::SectorFlushMode::visibility) !=
                        storage::SectorFlushStatus::volatile_complete ||
                        device.flush(storage::SectorFlushMode::durable) != storage::SectorFlushStatus::unsupported) {
                        return 0u64;
                    }
                """
            else:
                index = rng.choice((-1, 0, 0, 1))
                pattern = bytes(rng.randrange(256) for _ in range(SIZE))
                status = "out_of_range" if index != 0 else "read_only" if readonly else "success"
                body += (
                    "{"
                    + make_sector("input", pattern)
                    + f"""
                    if (device.write_sector({index}, input) != storage::SectorIoStatus::{status}) {{
                        return 0u64;
                    }}
                """
                    + "}"
                )
                if status == "success":
                    model = pattern
            body += check_device(model)
        yield Case(
            f"modeled mixed write, flush and readonly sequence {sequence}",
            body + "return 42u64;",
            42,
            imports=IMPORTS,
            prelude="\n",
        )


def rejections():
    prefix = "module test; " + " ".join(f"import {module};" for module in IMPORTS)
    prefix += " auto test() -> u64 { storage::RamSectorDevice device = storage::RamSectorDevice();"
    bodies = (
        "return u64(device.elements[0]);",
        "device.locked = false; return 0u64;",
        "device.read_sector(0u64); return 0u64;",
        "const storage::Block64 record = storage::Block64(); device.write_sector(0, record); return 0u64;",
        "const storage::Sector512 sector = storage::Sector512(); device.write_sector(0u64, sector); return 0u64;",
        "device.flush(true); return 0u64;",
        "device.flush(storage::SectorFlushStatus::unsupported); return 0u64;",
        "const storage::RamSectorDevice frozen = device; const storage::Sector512 sector = storage::Sector512();"
        "frozen.write_sector(0, sector); return 0u64;",
        "const storage::RamSectorDevice frozen = device; frozen.make_read_only(); return 0u64;",
        "const storage::SectorReadResult report = device.read_sector(0);"
        "const storage::Sector512 secret = report.payload; return 0u64;",
        "const storage::SectorGeometry geometry = device.geometry(); geometry.writable = true; return 0u64;",
        "borrow_bytes(device); return 0u64;",
        "return u64(storage::SectorFlushStatus::volatile_complete);",
    )
    for index, body in enumerate(bodies):
        yield Rejection(f"block-I/O privacy, const and exact-type rejection {index}", prefix + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    require(compiler.is_file(), "compiler must exist")
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    corpus = list(geometry_cases()) + list(transfer_cases()) + list(failure_cases()) + list(flush_cases())
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-block-io-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 15)
        batch = []
        for case in corpus:
            if case.prelude:
                if batch:
                    runner.cases(batch)
                    batch = []
                runner.cases([case])
            else:
                batch.append(case)
                if len(batch) == 2:
                    runner.cases(batch)
                    batch = []
        if batch:
            runner.cases(batch)
        for case in rejected:
            runner.rejection(case)
        assembly = Path(temporary) / "ram-sector-record.s"
        command(
            [
                compiler,
                "--module-root",
                ROOT / "library",
                ROOT / "library/examples/ram_sector_record.au",
                "-o",
                assembly,
            ]
        )
        observed, _ = runner.assemble(assembly.read_text(), ["main"])
        validate_values(observed, [Case("RAM sector record example", "", 42, result_type="i64")])
    print(f"PASS block I/O: {len(corpus)} native cases, {len(rejected)} rejections; example=passed", flush=True)


if __name__ == "__main__":
    main()

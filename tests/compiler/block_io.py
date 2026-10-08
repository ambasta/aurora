#!/usr/bin/env python3
"""Runtime-sized owned RAM sector I/O with complete independent byte models."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import tempfile

from contextlib import nullcontext
from dataclasses import dataclass

from owned_bytes import Suite, command
from unsigned_oracle import Case as ScalarCase, Rejection, require


ROOT = Path(__file__).resolve().parents[2]
IMPORTS = ("std.binary", "std.binary_buffer", "storage.sector", "storage.block_io", "storage.ram_sector")
SIZE = 512
ZERO = bytes(SIZE)
INITIAL = bytes((index * 53 + index // 256 * 31 + 7) % 256 for index in range(SIZE))
INVALID = (-(1 << 63), -1, 1, 2, 512, (1 << 63) - 1)


@dataclass(frozen=True)
class Case(ScalarCase):
    quota: int = 512
    length: int = 1
    flag: int = 0
    allocations: int = 1
    peak: int = 1
    fail_after: int | None = None


class StorageRunner(Suite):
    """Reuse the owner adapter, scalar bridge and exact allocation/free checks."""

    def __init__(self, directory, compiler):
        super().__init__(compiler, directory, ROOT / "library", entry_name="entry")
        self.sequence = 0
        self.compiled_sources = {}

    def cases(self, cases):
        for case in cases:
            self.sequence += 1
            print(f"storage_case={self.sequence}: {case.name}", flush=True)
            source = "module storage_test;\n"
            source += "".join(f"import {module};\n" for module in case.imports)
            source += case.prelude
            source += f"auto entry(builtin::ByteRegion region, i64 n, i64 flag) -> {case.result_type} {{"
            source += case.body + "}"
            executable = self.compiled_sources.get(source)
            if executable is None:
                executable = self.compile(f"case-{self.sequence}", source)
                self.compiled_sources[source] = executable
            self.run(
                executable,
                case.quota,
                case.length,
                case.flag,
                case.expected,
                case.allocations,
                case.peak,
                case.fail_after,
            )

    def run(self, executable, quota, length, flag, expected, allocations, peak, fail_after=None, release_order=None):
        record = {
            "executable": str(executable.relative_to(self.directory)),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "quota": quota,
            "length": length,
            "flag": flag,
            "expected": expected,
            "allocations": allocations,
            "peak": peak,
            "fail_after": fail_after,
            "release_order": release_order,
            "passed": False,
        }
        self.last_observation = None
        try:
            super().run(executable, quota, length, flag, expected, allocations, peak, fail_after, release_order)
            record["passed"] = True
        except BaseException as error:
            record["error"] = str(error)
            raise
        finally:
            observation = self.last_observation
            if observation is not None:
                record.update(
                    returncode=observation.returncode,
                    stdout=observation.stdout.decode(errors="replace"),
                    stdout_hex=observation.stdout.hex(),
                    stderr=observation.stderr.decode(errors="replace"),
                    stderr_hex=observation.stderr.hex(),
                )
            with (self.directory / "native-results.jsonl").open("a") as output:
                output.write(json.dumps(record, sort_keys=True) + "\n")

    def rejection(self, case):
        self.sequence += 1
        folder = self.directory / f"reject-storage-{self.sequence}"
        folder.mkdir()
        source = folder / "input.au"
        source.write_text(case.source)
        output = folder / "output.s"
        sentinel = b"preserve existing output\n"
        for existing in (False, True):
            output.unlink(missing_ok=True)
            if existing:
                output.write_bytes(sentinel)
            result = command([self.compiler, *self.module_args, source, "-o", output])
            (folder / f"stderr-{int(existing)}").write_bytes(result.stderr)
            (folder / f"stdout-{int(existing)}").write_bytes(result.stdout)
            (folder / f"exit-{int(existing)}").write_text(str(result.returncode) + "\n")
            require(
                result.returncode == 1
                and re.fullmatch(
                    rf"(?:{re.escape(str(source))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
                    r"AU(?:100[12]|200[123]|3001|4001): [^\n]+\n",
                    result.stderr.decode(errors="strict"),
                )
                is not None,
                f"{case.name}: expected structured compiler rejection, got {result.stderr!r}",
            )
            require(source.read_text() == case.source, f"{case.name}: compiler modified input")
            require(
                output.read_bytes() == sentinel if existing else not output.exists(),
                f"{case.name}: rejection changed output",
            )
        self.rejections += 1


def make_device(name="device", count="1", const=False):
    qualifier = "const " if const else ""
    return f"""
        builtin::OwnedBytes {name}_bytes = region.try_allocate(({count}) * 512);
        {qualifier}storage::RamSectorDevice {name} = storage::RamSectorDevice(region, move({name}_bytes));
        if ({name}.status() != storage::SectorIoStatus::success) {{ return 0u64; }}
    """


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
            if ({name}.write_byte({name}_offset, {name}_bytes[{name}_offset]) != std::ByteWriteStatus::success) {{
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
            const std::ByteReadResult byte = {name}.read_byte(offset);
            if (byte.status() != std::ByteReadStatus::success || u8(byte.value_or(0u64)) != expected[offset]) {{
                return 0u64;
            }}
            offset = offset + 1;
        }}
    """
        + "}"
    )


def check_device(expected, name="device", index=0):
    return (
        "{"
        + f"""
        const storage::SectorReadResult report = {name}.read_sector({index});
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
        + make_device()
        + """
        if (device.write_sector(0, initial) != storage::SectorIoStatus::success) { return 0u64; }
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
        make_device(const=True)
        + """
        const storage::SectorGeometry geometry = device.geometry();
        if (geometry.sector_size_bytes() != 512u64 || geometry.sector_count() != 1u64 || !geometry.can_write()) {
            return 0u64;
        }
        if (size_of(storage::Sector512) != 512 || size_of(storage::SectorReadResult) != 520 ||
            size_of(storage::SectorGeometry) != 16 ||
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
            allocations=0,
            peak=0,
            prelude="""
            auto copy_geometry(storage::SectorGeometry value) -> storage::SectorGeometry {
                return value;
            }
        """,
        )
    for read_only in (False, True):
        yield Case(
            f"sector seeding copies all bytes, readonly={read_only}",
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
        make_device()
        + """
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
                const std::ByteReadResult byte = actual.read_byte(offset);
                if (byte.status() != std::ByteReadStatus::success || u8(byte.value_or(0u64)) != expected) {
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
            f"explicit device transfers preserve bytes and readonly {read_only}",
            seeded_device(read_only)
            + """
            const storage::SectorReadResult saved = device.read_sector(0);
            const storage::SectorGeometry before = device.geometry();
            storage::RamSectorDevice intermediate = move(device);
            storage::RamSectorDevice transferred = transfer_device(region, move(intermediate));
            const storage::SectorGeometry after = transferred.geometry();
            if (before.can_write() != after.can_write() || after.sector_count() != 1u64) {
                return 0u64;
            }
            const storage::Sector512 zero = storage::Sector512();
        """
            + (
                """
            if (transferred.write_sector(0, zero) != storage::SectorIoStatus::read_only) {
                return 0u64;
            }
        """
                + check_device(INITIAL, "transferred")
                if read_only
                else """
            if (transferred.write_sector(0, zero) != storage::SectorIoStatus::success) {
                return 0u64;
            }
            transferred.make_read_only();
        """
                + check_device(ZERO, "transferred")
            )
            + "const storage::Sector512 snapshot = saved.sector_or_zero();"
            + check_sector("snapshot", INITIAL)
            + "return 42u64;",
            42,
            imports=IMPORTS,
            prelude=(
                "\n            auto transfer_device(builtin::ByteRegion region, "
                "storage::RamSectorDevice value) -> storage::RamSectorDevice {\n"
                "                return move(value);\n"
                "            }\n        "
            ),
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
    for status in ("out_of_range", "read_only", "invalid_source"):
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
            allocations=0,
            peak=0,
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


def runtime_cases():
    body = (
        make_device(count="n")
        + """
        const storage::SectorGeometry geometry = device.geometry();
        if (geometry.sector_count() != u64(n) || !geometry.can_write()) { return 0u64; }
        i64 index = 0;
        while (index < n) {
            const storage::SectorReadResult empty_read = device.read_sector(index);
            if (empty_read.status() != storage::SectorIoStatus::success) { return 0u64; }
            const storage::Sector512 empty = empty_read.sector_or_zero();
            storage::Sector512 pattern = storage::Sector512();
            i64 offset = 0;
            while (offset < 512) {
                const std::ByteReadResult byte = empty.read_byte(offset);
                if (byte.value_or(1u64) != 0u64) { return 0u64; }
                pattern.write_byte(offset, u8((index * 31 + offset * 53 + 7) % 256));
                offset = offset + 1;
            }
            if (device.write_sector(index, pattern) != storage::SectorIoStatus::success) { return 0u64; }
            index = index + 1;
        }
        const storage::SectorReadResult saved = device.read_sector(n - 1);
        const storage::SectorReadResult report_copy = saved;
        const storage::Sector512 zero = storage::Sector512();
        if (device.write_sector(n - 1, zero) != storage::SectorIoStatus::success) { return 0u64; }
        storage::Sector512 mutated = report_copy.sector_or_zero();
        mutated.write_byte(0, 0u8);
        const storage::Sector512 snapshot = saved.sector_or_zero();
        const storage::Sector512 snapshot_copy = report_copy.sector_or_zero();
        index = 0;
        while (index < n) {
            const storage::SectorReadResult read = device.read_sector(index);
            if (read.status() != storage::SectorIoStatus::success) { return 0u64; }
            const storage::Sector512 actual = read.sector_or_zero();
            i64 offset = 0;
            while (offset < 512) {
                u64 expected = u64((index * 31 + offset * 53 + 7) % 256);
                if (index == n - 1) { expected = 0u64; }
                const std::ByteReadResult byte = actual.read_byte(offset);
                const std::ByteReadResult prior = snapshot.read_byte(offset);
                const std::ByteReadResult copied = snapshot_copy.read_byte(offset);
                if (byte.value_or(256u64) != expected ||
                    prior.value_or(256u64) != u64(((n - 1) * 31 + offset * 53 + 7) % 256) ||
                    copied.value_or(256u64) != prior.value_or(257u64)) { return 0u64; }
                offset = offset + 1;
            }
            index = index + 1;
        }
        if (device.make_read_only() != storage::SectorIoStatus::success ||
            device.write_sector(n - 1, zero) != storage::SectorIoStatus::read_only) { return 0u64; }
    """
    )
    for index in ("-9223372036854775808", "-1", "n", "9223372036854775807"):
        body += (
            f"""
            if (device.write_sector({index}, zero) != storage::SectorIoStatus::out_of_range) {{ return 0u64; }}
            {{
                const storage::SectorReadResult failed = device.read_sector({index});
                if (failed.status() != storage::SectorIoStatus::out_of_range) {{ return 0u64; }}
                const storage::Sector512 masked = failed.sector_or_zero();
        """
            + check_sector("masked", ZERO)
            + "}"
        )
    body += """
        if (device.flush(storage::SectorFlushMode::visibility) != storage::SectorFlushStatus::volatile_complete ||
            device.flush(storage::SectorFlushMode::durable) != storage::SectorFlushStatus::unsupported) { return 0u64; }
        return 42u64;
    """
    for count in (1, 2, 3, 17, 129):
        yield Case(
            f"runtime {count}-sector full-byte oracle, last-sector snapshot and overflow ordering",
            body,
            42,
            imports=IMPORTS,
            length=count,
            quota=count * 512,
        )

    # Seed linear owned bytes before the device exists, so a matching but wrong
    # read/write sector mapping cannot satisfy the transport round trip alone.
    seeded = """
        builtin::OwnedBytes bytes = region.try_allocate(n * 512);
        if (!bytes.ok()) { return 0u64; }
        i64 linear = 0;
        while (linear < n * 512) {
            if (!bytes.set(linear, u8((linear / 512 * 31 + linear % 512 * 53 + 7) % 256))) { return 0u64; }
            linear = linear + 1;
        }
        storage::RamSectorDevice device = storage::RamSectorDevice(region, move(bytes));
        i64 index = 0;
        while (index < n) {
            const storage::SectorReadResult read = device.read_sector(index);
            if (read.status() != storage::SectorIoStatus::success) { return 0u64; }
            const storage::Sector512 actual = read.sector_or_zero();
            i64 offset = 0;
            while (offset < 512) {
                const std::ByteReadResult byte = actual.read_byte(offset);
                if (byte.value_or(256u64) != u64((index * 31 + offset * 53 + 7) % 256)) { return 0u64; }
                offset = offset + 1;
            }
            index = index + 1;
        }
        return 42u64;
    """
    for count in (3, 129):
        yield Case(
            f"linear backing establishes physical sector mapping for {count} sectors",
            seeded,
            42,
            imports=IMPORTS,
            length=count,
            quota=count * 512,
        )

    # Two independently allocated owners must never alias, including after transfer.
    body = make_device(count="n") + make_device("other", "n") + make_sector("initial", INITIAL)
    body += (
        """
        if (device.write_sector(n - 1, initial) != storage::SectorIoStatus::success) { return 0u64; }
        storage::RamSectorDevice transferred = move(device);
    """
        + check_device(INITIAL, "transferred", "n - 1")
        + check_device(ZERO, "other", "n - 1")
    )
    body += (
        """
        if (other.write_sector(n - 1, initial) != storage::SectorIoStatus::success) { return 0u64; }
        const storage::Sector512 zero = storage::Sector512();
        if (transferred.write_sector(n - 1, zero) != storage::SectorIoStatus::success) { return 0u64; }
    """
        + check_device(ZERO, "transferred", "n - 1")
        + check_device(INITIAL, "other", "n - 1")
    )
    yield Case(
        "two runtime allocations remain independent after device transfer",
        body + "return 42u64;",
        42,
        imports=IMPORTS,
        length=3,
        quota=3072,
        allocations=2,
        peak=2,
    )

    yield Case(
        "successful empty owner is a valid zero-sector device",
        make_device(count="0")
        + """
        const storage::SectorGeometry geometry = device.geometry();
        const storage::Sector512 zero = storage::Sector512();
        const storage::SectorReadResult read = device.read_sector(0);
        if (geometry.sector_count() != 0u64 || !geometry.can_write() ||
            read.status() != storage::SectorIoStatus::out_of_range ||
            device.write_sector(0, zero) != storage::SectorIoStatus::out_of_range ||
            device.make_read_only() != storage::SectorIoStatus::success ||
            device.write_sector(0, zero) != storage::SectorIoStatus::out_of_range ||
            device.flush(storage::SectorFlushMode::visibility) != storage::SectorFlushStatus::volatile_complete ||
            device.flush(storage::SectorFlushMode::durable) != storage::SectorFlushStatus::unsupported) { return 0u64; }
        const storage::Sector512 masked = read.sector_or_zero();
        """
        + check_sector("masked", ZERO)
        + "return 42u64;",
        42,
        imports=IMPORTS,
        quota=0,
    )

    invalid = """
        builtin::OwnedBytes bytes = region.try_allocate(n);
        storage::RamSectorDevice device = storage::RamSectorDevice(region, move(bytes));
        const storage::SectorGeometry geometry = device.geometry();
        if (device.status() != storage::SectorIoStatus::invalid_source ||
            geometry.sector_count() != 0u64 || geometry.can_write() ||
            device.make_read_only() != storage::SectorIoStatus::invalid_source ||
            device.flush(storage::SectorFlushMode::visibility) != storage::SectorFlushStatus::unsupported ||
            device.flush(storage::SectorFlushMode::durable) != storage::SectorFlushStatus::unsupported) { return 0u64; }
        const storage::Sector512 zero = storage::Sector512();
    """
    for index in ("-9223372036854775808", "-1", "0", "1", "9223372036854775807"):
        invalid += (
            f"""
            if (device.write_sector({index}, zero) != storage::SectorIoStatus::invalid_source) {{ return 0u64; }}
            {{
                const storage::SectorReadResult failed = device.read_sector({index});
                if (failed.status() != storage::SectorIoStatus::invalid_source) {{ return 0u64; }}
                const storage::Sector512 masked = failed.sector_or_zero();
        """
            + check_sector("masked", ZERO)
            + "}"
        )
    invalid += "return 42u64;"
    for length in (1, 511, 513, 1023):
        yield Case(
            f"unaligned allocation {length} is invalid source without rounding",
            invalid,
            42,
            imports=IMPORTS,
            length=length,
            quota=length,
        )
    for length, quota, fail_after, label in (
        (-1, 0, None, "negative allocation"),
        (512, 511, None, "quota exhaustion"),
        ((1 << 63) - 1, 0, None, "maximum signed allocation"),
        (512, 512, 0, "injected allocator failure"),
        (0, 0, 0, "failed empty metadata allocation"),
    ):
        yield Case(
            label + " propagates invalid source",
            invalid,
            42,
            imports=IMPORTS,
            length=length,
            quota=quota,
            allocations=0,
            peak=0,
            fail_after=fail_after,
        )


def rejections():
    prefix = "module test; " + " ".join(f"import {module};" for module in IMPORTS)
    prefix += " auto test(builtin::ByteRegion region, i64 n, i64 flag) -> u64 {"
    prefix += make_device()
    bodies = (
        "const builtin::OwnedBytes leaked = device.payload; return 0u64;",
        "device.locked = false; return 0u64;",
        "const storage::SectorReadResult result = device.read_sector(0u64); return 0u64;",
        "const std::BinaryBuffer64 record = std::BinaryBuffer64(); device.write_sector(0, record); return 0u64;",
        "const storage::Sector512 sector = storage::Sector512(); device.write_sector(0u64, sector); return 0u64;",
        "device.flush(true); return 0u64;",
        "device.flush(storage::SectorFlushStatus::unsupported); return 0u64;",
        "const storage::RamSectorDevice frozen = move(device); const storage::Sector512 sector = storage::Sector512();"
        "frozen.write_sector(0, sector); return 0u64;",
        "const storage::RamSectorDevice frozen = move(device); frozen.make_read_only(); return 0u64;",
        "const storage::SectorReadResult report = device.read_sector(0);"
        "const storage::Sector512 secret = report.payload; return 0u64;",
        "storage::SectorGeometry geometry = device.geometry(); geometry.writable = true; return 0u64;",
        "const builtin::span<const u8> leaked = borrow_bytes(device); return 0u64;",
        "return u64(storage::SectorFlushStatus::volatile_complete);",
        "storage::RamSectorDevice copy = device; return 0u64;",
        "storage::RamSectorDevice moved = move(device); device.geometry(); return 0u64;",
        "storage::RamSectorDevice first = move(device); storage::RamSectorDevice second = move(device); return 0u64;",
        "storage::RamSectorDevice other = move(device); device = move(other); return 0u64;",
        "const builtin::OwnedBytes leaked = move(device.payload); return 0u64;",
    )
    for index, body in enumerate(bodies):
        yield Rejection(f"block-I/O privacy, const and exact-type rejection {index}", prefix + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifacts", type=Path, help="retain this run in a new directory")
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    require(compiler.is_file(), "compiler must exist")
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    corpus = (
        list(geometry_cases())
        + list(transfer_cases())
        + list(failure_cases())
        + list(flush_cases())
        + list(runtime_cases())
    )
    rejected = list(rejections())
    if args.artifacts is not None:
        args.artifacts.mkdir(parents=True, exist_ok=False)
    context = (
        tempfile.TemporaryDirectory(prefix="aurora-block-io-")
        if args.artifacts is None
        else nullcontext(args.artifacts)
    )
    with context as temporary:
        runner = StorageRunner(Path(temporary), compiler)
        runner.cases(corpus)
        for case in rejected:
            runner.rejection(case)
        executable = runner.compile(
            "ram-sector-record", (ROOT / "library/examples/ram_sector_record.au").read_text(), entry_name="main"
        )
        for count in (1, 3, 17):
            runner.run(executable, count * 512, count, 0, 42, 1, 1)
        runner.run(executable, 511, 1, 0, 14, 0, 0)
        runner.run(executable, 0, 0, 0, 13, 0, 0)
        runner.run(executable, 0, (1 << 63) - 1, 0, 13, 0, 0)

    print(f"PASS block I/O: {len(corpus)} native cases, {len(rejected)} rejections; example=passed", flush=True)


if __name__ == "__main__":
    main()

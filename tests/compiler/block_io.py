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

COPIED_RESULT_DRIVER = r"""
#include "runtime/hosted_bytes.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace aurora::hosted::bytes;
extern "C" void __au_runtime_bytes_test_produce(void *, void *);
static void check(bool value, const char *message) {
    if (!value) { std::fprintf(stderr, "copied record failure: %s\n", message); std::exit(90); }
}
struct Trace {
    std::int64_t remaining;
    std::array<void *, 2> allocations{};
    std::array<std::size_t, 2> sizes{};
    std::array<std::size_t, 2> released{};
    std::size_t allocated_count = 0, released_count = 0;
    static void *allocate(void *context, std::size_t size) noexcept {
        auto &self = *static_cast<Trace *>(context);
        if (self.remaining == 0) return nullptr;
        if (self.remaining > 0) --self.remaining;
        check(self.allocated_count < 2, "bounded producer allocations");
        void *memory = std::malloc(size);
        if (memory != nullptr) {
            self.allocations[self.allocated_count] = memory;
            self.sizes[self.allocated_count++] = size;
        }
        return memory;
    }
    static void release(void *context, void *memory) noexcept {
        auto &self = *static_cast<Trace *>(context);
        for (std::size_t i = 0; i < self.allocated_count; ++i) {
            if (self.allocations[i] == memory) {
                check(self.released_count < 2, "no duplicate releases");
                self.released[self.released_count++] = i + 1;
                std::memset(memory, 0xdd, self.sizes[i]);
                self.allocations[i] = nullptr;
                std::free(memory);
                return;
            }
        }
        check(false, "release matches a live allocation");
    }
};
int main(int argc, char **argv) {
    check(argc == 3, "failure countdown and sector count");
    const std::int64_t fail_after = std::strtoll(argv[1], nullptr, 10);
    const std::uint64_t count = std::strtoull(argv[2], nullptr, 10);
    Trace trace{fail_after};
    Region region(count * 512 + 1, Allocator{&trace, Trace::allocate, Trace::release});
    alignas(16) std::array<std::uint64_t, 2> input{region.id(), count};
    const auto input_before = input;
    alignas(16) std::array<unsigned char, 96> output;
    output.fill(0xa5);
    auto *result = output.data() + 8;
    __au_runtime_bytes_test_produce(input.data(), result);
    const std::size_t allocations = fail_after < 0 ? 2 : static_cast<std::size_t>(fail_after);
    const auto metrics = region.metrics();
    check(metrics.used == 0 && metrics.live_allocations == 0, "producer closes all owners before return");
    check(metrics.successful_allocations == allocations && metrics.releases == allocations &&
          trace.allocated_count == allocations && trace.released_count == allocations,
          "exact allocation and release counts before region close");
    for (std::size_t i = 0; i < allocations; ++i)
        check(trace.released[i] == allocations - i, "exact reverse release order");
    check(region.close(), "host region closes before reading copied output");
    // No returned field was inspected before the authority and all its owners closed.
    check(input == input_before, "region and scalar argument record unchanged");
    std::uint64_t status = 99;
    std::memcpy(&status, result, sizeof(status));
    check(status == (fail_after < 0 ? 0u : 3u), "success or invalid_source status survives region close");
    for (std::size_t i = 0; i < 64; ++i) {
        const auto expected = fail_after < 0 ? static_cast<unsigned char>((i * 53 + 7) % 256) : 0;
        check(result[8 + i] == expected, "every copied record byte survives region close");
    }
    // The canonical report is 8 status bytes plus 64 payload bytes, with no internal padding.
    for (std::size_t i = 0; i < output.size(); ++i)
        if (i < 8 || i >= 80) check(output[i] == 0xa5, "both result-buffer canaries preserved");
    auto independent = output;
    independent[16] ^= 255;
    check(independent[16] != output[16], "independent snapshot can change after region close");
    std::printf("PASS copied resource record after region.close: fail_after=%lld sectors=%llu releases=%zu\n",
                static_cast<long long>(fail_after), static_cast<unsigned long long>(count), allocations);
}
"""

COPIED_RESULT_BRIDGE = r"""
.text
.globl __au_runtime_bytes_test_produce
.type __au_runtime_bytes_test_produce, @function
__au_runtime_bytes_test_produce:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    movq %rsi, %r10
    call PRODUCER
    leave
    ret
.size __au_runtime_bytes_test_produce, .-__au_runtime_bytes_test_produce
"""


@dataclass(frozen=True)
class Case(ScalarCase):
    quota: int = 512
    length: int = 1
    flag: int = 0
    allocations: int = 1
    peak: int = 1
    fail_after: int | None = None
    release_order: tuple[int, ...] | None = None


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
                None if case.release_order is None else list(case.release_order),
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

    def copied_result_after_region_close(self):
        """Observe the producer's real copied record only after closing host authority."""
        folder = self.directory / "copied-result-after-region-close"
        folder.mkdir()
        case = next(copied_resource_result_cases())
        source = folder / "input.au"
        source.write_text(
            "module storage_test;\n" + "".join(f"import {module};\n" for module in IMPORTS) + case.prelude
        )
        assembly = folder / "output.s"
        compiled = command([self.compiler, *self.module_args, source, "-o", assembly])
        require(compiled.returncode == 0, f"direct copied producer compile failed: {compiled.stderr!r}")
        text = assembly.read_text()
        producers = re.findall(r"^\.type ([A-Za-z_][A-Za-z_0-9]*__d7produce), @function$", text, re.M)
        require(len(producers) == 1, "one nominal private resource producer entry")
        require(f".local {producers[0]}\n" in text, "copied producer remains private")
        assembly.write_text(text + COPIED_RESULT_BRIDGE.replace("PRODUCER", producers[0]))
        driver = folder / "driver.cpp"
        driver.write_text(COPIED_RESULT_DRIVER)
        executable = folder / "native"
        linked = command(
            [
                *self.cxx,
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-I",
                ROOT,
                driver,
                ROOT / "runtime/hosted_bytes.cpp",
                assembly,
                "-o",
                executable,
            ],
            timeout=60,
        )
        require(linked.returncode == 0, f"direct copied producer host link failed: {linked.stderr!r}")
        for index, (fail_after, count) in enumerate(((-1, 1), (-1, 3), (0, 1), (1, 1))):
            observed = command([executable, fail_after, count])
            (folder / f"observation-{index}.stdout").write_bytes(observed.stdout)
            (folder / f"observation-{index}.stderr").write_bytes(observed.stderr)
            require(observed.returncode == 0, f"copied result after region close failed: {observed.stderr!r}")
            require(observed.stdout.startswith(b"PASS copied resource record after region.close:"), "host observation")
            print(observed.stdout.decode().strip(), flush=True)


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


def copied_resource_result_cases():
    """The returned record outlives the producer's real sector-device backing."""
    prelude = """
        class ProducedRecord {
            storage::SectorIoStatus outcome;
            std::BinaryBuffer64 payload;
        public:
            ProducedRecord(storage::SectorIoStatus status, std::BinaryBuffer64 record)
                : outcome(status), payload(record) {}
            auto status() const -> storage::SectorIoStatus { return outcome; }
            auto record() const -> std::BinaryBuffer64 {
                const std::BinaryBuffer64 result = payload;
                return result;
            }
        };
        auto produce(builtin::ByteRegion region, i64 count) -> ProducedRecord {
            builtin::OwnedBytes guard = region.try_allocate(1);
            builtin::OwnedBytes backing = region.try_allocate(count * 512);
            storage::RamSectorDevice device = storage::RamSectorDevice(region, move(backing));
            const std::BinaryBuffer64 zero = std::BinaryBuffer64();
            if (device.status() != storage::SectorIoStatus::success) {
                const ProducedRecord failed = ProducedRecord(storage::SectorIoStatus::invalid_source, zero);
                return failed;
            }
            std::BinaryBuffer64 original = std::BinaryBuffer64();
            i64 index = 0;
            while (index < 64) {
                original.write_u8(index, u8((index * 53 + 7) % 256));
                index = index + 1;
            }
            storage::Sector512 sector = storage::Sector512();
            sector.write_record(448, original);
            device.write_sector(count - 1, sector);
            const storage::SectorReadResult saved = device.read_sector(count - 1);
            const storage::Sector512 zero_sector = storage::Sector512();
            device.write_sector(count - 1, zero_sector);
            sector.write_record(448, zero);
            original.write_u8(0, 99u8);
            const storage::Sector512 snapshot = saved.sector_or_zero();
            const storage::RecordReadResult tail = snapshot.read_record(448);
            const std::BinaryBuffer64 record = tail.record_or_zero();
            const ProducedRecord result = ProducedRecord(saved.status(), record);
            return result;
        }
    """
    body = (
        byte_array("expected_record", bytes((index * 53 + 7) % 256 for index in range(64)))
        + """
        const ProducedRecord report = produce(region, n);
        const std::BinaryBuffer64 record = report.record();
        if (flag == 0) {
            if (report.status() != storage::SectorIoStatus::success) { return 0u64; }
            // The producer must have dropped both owners before this quota-sized allocation.
            builtin::OwnedBytes replacement = region.try_allocate(n * 512 + 1);
            if (!replacement.ok()) { return 0u64; }
            i64 index = 0;
            while (index < replacement.size()) {
                replacement.set(index, 238u8);
                index = index + 1;
            }
            std::BinaryBuffer64 changed = report.record();
            changed.write_u8(0, 99u8);
            if (changed.at(0) != 99u8) { return 0u64; }
            const std::BinaryBuffer64 unchanged = report.record();
            index = 0;
            while (index < 64) {
                const u8 expected = expected_record[index];
                if (record.at(index) != expected || unchanged.at(index) != expected) { return 0u64; }
                index = index + 1;
            }
        } else {
            if (report.status() != storage::SectorIoStatus::invalid_source) { return 0u64; }
            // record() exposes the actual copied payload, so no accessor can mask bad failure bytes.
            i64 index = 0;
            while (index < 64) {
                if (record.at(index) != 0u8) { return 0u64; }
                index = index + 1;
            }
        }
        return 42u64;
    """
    )
    for count in (1, 3):
        yield Case(
            f"resource-produced record survives device cleanup and quota reuse {count}",
            body,
            42,
            imports=IMPORTS,
            prelude=prelude,
            quota=count * 512 + 1,
            length=count,
            allocations=3,
            peak=2,
            release_order=(2, 1, 3),
        )
    for quota, fail_after, allocations, label in (
        (512, None, 1, "quota exhausted after guard"),
        (513, 0, 0, "allocator rejects first allocation"),
        (513, 1, 1, "allocator rejects device backing"),
    ):
        yield Case(
            "resource-produced zero failure record: " + label,
            body,
            42,
            imports=IMPORTS,
            prelude=prelude,
            quota=quota,
            flag=1,
            allocations=allocations,
            peak=allocations,
            fail_after=fail_after,
            release_order=(1,) if allocations else (),
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
        + list(copied_resource_result_cases())
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
        runner.copied_result_after_region_close()

    print(
        f"PASS block I/O: {len(corpus)} native cases, {len(rejected)} rejections; "
        "example=passed; copied-result-after-region-close=4 passed",
        flush=True,
    )


if __name__ == "__main__":
    main()

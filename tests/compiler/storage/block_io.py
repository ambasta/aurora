#!/usr/bin/env python3
"""storage.block_io and storage.ram_sector through the real hosted region adapter.

The driver is compiled once and linked with the owned-bytes host, which grants one
quota-limited region per invocation, injects allocator failures and reports exact
allocation, release and peak counts. Each case selects a self-checking scenario.
"""

from __future__ import annotations

import sys

import harness

sys.path.insert(0, str(harness.ROOT / "tests/compiler"))
import owned_bytes  # noqa: E402  (the shared hosted-region driver and bridge)

MAX_I64 = (1 << 63) - 1
MOUNT_BYTES = 1536 + 4095 + 512  # Cached metadata, bounded path and directory scratch.
INVALID = (-(1 << 63), -1, 1, 2, 512, MAX_I64)


def case(label, selector, quota=512, length=1, allocations=1, peak=1, fail_after=None, order=None):
    return label, selector, quota, length, allocations, peak, fail_after, order


def cases():
    yield case("mount rejects started topology", 46, MOUNT_BYTES, 6, 3, 3)
    for mode, label in enumerate(("zero size", "oversized", "accept before begin", "second begin", "short sector")):
        yield case("log topology sticky rejection " + label, 47, 0, mode, 0, 0)
    yield case("mount cache allocation failure", 46, 1535, 4, 1, 1)
    yield case("mount path allocation failure releases cache", 46, MOUNT_BYTES, 4, 1, 1, fail_after=1)
    yield case("mount directory scratch failure releases prior owners", 46, MOUNT_BYTES, 4, 2, 2, fail_after=2)
    yield case("mount cache wrong length", 46, MOUNT_BYTES, 5, 3, 3)
    for mode, label in enumerate(
        ("read before admission", "wrong reply LBA", "backend short/failed read", "short successful reply")
    ):
        yield case("mount protocol " + label, 46, MOUNT_BYTES, mode, 3, 3)
    yield case("exact geometry, zero initialization and canonical layouts", 0)
    for code, count in enumerate((0, 1, 1 << 63, (1 << 64) - 1)):
        yield case(f"geometry retains full-width count {count}", 1 + code, allocations=0, peak=0)
    for read_only in (False, True):
        yield case(f"sector seeding copies all bytes, readonly={read_only}", 5 + read_only)
    for pattern in range(6):
        yield case(f"complete sector write pattern {pattern}", 7 + pattern)
    yield case("every single byte position survives full-sector transport", 13)
    yield case("read report and extracted copy survive overwrite", 14)
    for read_only in (False, True):
        yield case(f"explicit device transfers preserve bytes and readonly {read_only}", 15 + read_only)
    for read_only in (False, True):
        for code, index in enumerate(INVALID):
            label = f"range error {index} precedes readonly {read_only} and preserves every byte"
            yield case(label, 17 + 6 * read_only + code)
    yield case("readonly is one-way, idempotent and preserves data and prior geometry", 29)
    for code, status in enumerate(("out_of_range", "read_only", "invalid_source")):
        yield case(f"public {status} report masks every nonzero payload byte", 30 + code, allocations=0, peak=0)
    for read_only in (False, True):
        label = f"visibility and rejected durable flush preserve every byte readonly={read_only}"
        yield case(label, 33 + read_only)
    for number in range(4):
        yield case(f"modeled mixed write, flush and readonly sequence {number}", 35 + number)
    for count in (1, 2, 3, 17, 129):
        label = f"runtime {count}-sector full-byte oracle, last-sector snapshot and overflow ordering"
        yield case(label, 39, quota=count * 512, length=count)
    for count in (3, 129):
        yield case(f"linear backing establishes physical sector mapping for {count} sectors", 40, count * 512, count)
    yield case("two runtime allocations remain independent after device transfer", 41, 3072, 3, 2, 2)
    yield case("successful empty owner is a valid zero-sector device", 42, quota=0)
    for length in (1, 511, 513, 1023):
        yield case(f"unaligned allocation {length} is invalid source without rounding", 43, length, length)
    for length, quota, fail_after, label in (
        (-1, 0, None, "negative allocation"),
        (512, 511, None, "quota exhaustion"),
        (MAX_I64, 0, None, "maximum signed allocation"),
        (512, 512, 0, "injected allocator failure"),
        (0, 0, 0, "failed empty metadata allocation"),
    ):
        yield case(label + " propagates invalid source", 43, quota, length, 0, 0, fail_after)
    for count in (1, 3):
        label = f"resource-produced record survives device cleanup and quota reuse {count}"
        yield case(label, 44, count * 512 + 1, count, 3, 2, order=(2, 1, 3))
    for quota, fail_after, allocations, label in (
        (512, None, 1, "quota exhausted after guard"),
        (513, 0, 0, "allocator rejects first allocation"),
        (513, 1, 1, "allocator rejects device backing"),
    ):
        order = (1,) if allocations else ()
        yield case(
            "resource-produced zero failure record: " + label, 45, quota, 1, allocations, allocations, fail_after, order
        )


def observe(executable, quota, length, selector, fail_after, order):
    """result, allocations, releases and peak; release order when the case fixes one."""
    arguments = [executable, quota, length, selector] + ([] if fail_after is None else [fail_after])
    result = owned_bytes.command(arguments)
    if result.returncode != 0 or result.stderr:
        return f"exit {result.returncode} {result.stderr!r}"
    words = [int(part) for part in result.stdout.split()]
    released = words[4:]
    text = f"result={words[0]} allocations={words[1]} releases={words[2]} peak={words[3]}"
    if order is not None:
        return text + " order=" + ",".join(map(str, released))
    return text + (" order=permutation" if sorted(released) == list(range(1, words[1] + 1)) else f" order={released}")


PREFIX = "module test; import std.binary; import std.binary_buffer; import storage.sector; import storage.block_io;"
PREFIX += " import storage.ram_sector; auto test(builtin::ByteRegion region, i64 n, i64 flag) -> u64 {"
PREFIX += "builtin::OwnedBytes device_bytes = region.try_allocate((1) * 512);"
PREFIX += "storage::RamSectorDevice device = storage::RamSectorDevice(region, move(device_bytes));"
PREFIX += "if (device.status() != storage::SectorIoStatus::success) { return 0u64; }"
REJECTIONS = (
    "const builtin::OwnedBytes leaked = device.payload; return 0u64;",
    "device.locked = false; return 0u64;",
    "const storage::SectorReadResult result = device.read_sector(0u64); return 0u64;",
    "const std::BinaryBuffer64 record = std::BinaryBuffer64(); device.write_sector(0, record); return 0u64;",
    "const storage::RamSectorDevice frozen = move(device); const storage::Sector512 sector = storage::Sector512();"
    "frozen.write_sector(0, sector); return 0u64;",
    "const builtin::span<const u8> leaked = borrow_bytes(device); return 0u64;",
    "return u64(storage::SectorFlushStatus::volatile_complete);",
    "storage::RamSectorDevice copy = device; return 0u64;",
    "storage::RamSectorDevice moved = move(device); device.geometry(); return 0u64;",
    "storage::RamSectorDevice other = move(device); device = move(other); return 0u64;",
    "const builtin::OwnedBytes leaked = move(device.payload); return 0u64;",
)
BRIDGE = """
.text
.globl __au_runtime_bytes_test_produce
__au_runtime_bytes_test_produce:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    movq %rsi, %r10
    call PRODUCER
    leave
    ret
"""


def copied_after_close(suite, directory, driver):
    """Link the same driver assembly with a host that reads the record after region.close()."""
    assembly = driver.parent / "output.s"
    text = assembly.read_text()
    producers = [line.split()[1].rstrip(",") for line in text.splitlines() if line.startswith(".type ")]
    producers = [name for name in producers if name.endswith("__d7produce")]
    harness.require(len(producers) == 1 and f".local {producers[0]}\n" in text, "one private producer")
    bridged = directory / "copied.s"
    bridged.write_text(text + BRIDGE.replace("PRODUCER", producers[0]))
    program = directory / "copied"
    flags = (*owned_bytes.HOST_FLAGS, "-I", harness.ROOT)
    host = (harness.HERE / "copied_record_host.cpp", harness.ROOT / "runtime/hosted_bytes.cpp")
    result = owned_bytes.command([*suite.cxx, *flags, *host, bridged, "-o", program], timeout=120)
    harness.require(result.returncode == 0, f"copied-record host link failed: {result.stderr.decode()}")
    for fail_after, count in ((-1, 1), (-1, 3), (0, 1), (1, 1)):
        result = owned_bytes.command([program, fail_after, count])
        observed = "passed" if result.returncode == 0 and result.stdout.startswith(b"PASS ") else f"{result!r}"
        yield f"copied record after region close fail_after={fail_after} sectors={count}", observed


def describe(compiler, directory):
    suite = owned_bytes.Suite(compiler, directory, harness.ROOT / "library", entry_name="entry")
    driver = suite.compile("driver", (harness.HERE / "block_io.au").read_text())
    for label, selector, quota, length, allocations, peak, fail_after, order in cases():
        yield label, observe(driver, quota, length, selector, fail_after, order)
    example = suite.compile("example", (harness.ROOT / "library/examples/ram_sector_record.au").read_text(), "main")
    for quota, length in ((512, 1), (1536, 3), (8704, 17), (511, 1), (0, 0), (0, MAX_I64)):
        yield (
            f"ram_sector_record example quota={quota} sectors={length}",
            observe(example, quota, length, 0, None, None),
        )
    yield from copied_after_close(suite, directory, driver)
    sources = [(str(index), PREFIX + body + "}") for index, body in enumerate(REJECTIONS)]
    yield from harness.rejections(compiler, directory, sources)


if __name__ == "__main__":
    harness.main("block_io", describe)

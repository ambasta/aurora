#!/usr/bin/env python3
"""std.binary fixed-width readers and std.checksum CRC32C over owned byte views.

Published CRC32C check vectors anchor the golden values; every read and checksum
observation keeps the full 64 bits of value_or(0) and value_or(2^64-1).
"""

from __future__ import annotations

import random

import harness

MIN_I64, MAX_I64 = -(1 << 63), (1 << 63) - 1
MAX_U32, MAX_U64 = (1 << 32) - 1, (1 << 64) - 1
READ, CHECKSUM, SPLIT, FABRICATED = range(4)
VECTORS = (
    ("empty", b"", 0x00000000),
    ("123456789", b"123456789", 0xE3069283),
    ("32 zero bytes", bytes(32), 0x8A9136AA),
    ("32 ff bytes", bytes([255]) * 32, 0x62A8AB43),
    ("ascending 0..31", bytes(range(32)), 0x46DD794E),
    ("descending 31..0", bytes(reversed(range(32))), 0x113FDB5C),
)


def data(values, operation, **fields):
    values = bytes(values)
    return {"operation": operation, "length": len(values), **harness.spread("data", values, 8), **fields}


def read_cases(seed=15015, random_count=8):
    rng = random.Random(seed)
    for size in (1, 2, 3, 4, 7, 8, 9, 16, 31, 64, 4096):
        values = [rng.randrange(256) for _ in range(size)]
        values[0], values[-1] = 255, 128
        for width in (2, 4, 8):
            offsets = sorted(
                {MIN_I64, -1, 0, 1, size - width, size - width + 1, size - 1, size, size + 1, MAX_I64}
                | {rng.randrange(size + 1) for _ in range(random_count)}
            )
            for big in (0, 1):
                for offset in offsets:
                    name = f"{'be' if big else 'le'}{width * 8} size {size} offset {offset}"
                    yield name, data(values, READ, width=width, big_endian=big, offset=offset), 3
    for width in (2, 4, 8):
        for big in (0, 1):
            for values in ([0] * width, [255] * width, [128, 255, 1, 2, 3, 4, 5, 129][:width]):
                name = f"{'be' if big else 'le'}{width * 8} direct full-width {values}"
                yield name, data(values, READ, width=width, big_endian=big), 3
    yield "failed byte read result masks a nonzero payload", {"operation": FABRICATED, "selector": 0}, 3


def crc_case(name, values, offset, count, previous=None):
    stored = values or [171]
    fields = dict(offset=offset, count=count, previous=previous or 0, extend=int(previous is not None))
    return name, data(stored, CHECKSUM, **fields), 3


def crc_cases(seed=15015, random_count=8):
    for name, values, _ in VECTORS:
        yield crc_case("published " + name, list(values), 0, len(values))
    rng = random.Random(seed ^ 0xC32C)
    for size in (1, 2, 3, 7, 8, 31, 32, 255, 256, 511, 512, 1024, 4096):
        values = [rng.randrange(256) for _ in range(size)]
        yield crc_case(f"seed {seed}: full size {size}", values, 0, size)
        offset = rng.randrange(size + 1)
        count = rng.randrange(size - offset + 1)
        yield crc_case(f"seed {seed}: subrange {offset}+{count} size {size}", values, offset, count)
        # Native first results continue natively; no expected value is substituted.
        splits = sorted({0, 1, size // 2, size - 1, size} | {rng.randrange(size + 1) for _ in range(random_count)})
        for split in splits:
            yield f"seed {seed}: size {size}, continuation split {split}", data(values, SPLIT, offset=split), 4
    values = [0, 128, 255, 17, 90, 221, 3, 42]
    for offset, count in (
        (MIN_I64, 0),
        (-1, 0),
        (MAX_I64, 0),
        (0, MIN_I64),
        (0, -1),
        (0, MAX_I64),
        (MAX_I64, MAX_I64),
        (1, MAX_I64),
        (8, 1),
        (9, 0),
        (7, 2),
        (0, 9),
        (8, 0),
        (0, 0),
        (7, 1),
    ):
        yield crc_case(f"signed range {offset}+{count}", values, offset, count)
        yield crc_case(f"continuation signed range {offset}+{count}", values, offset, count, 0x89ABCDEF)
    for previous in (0, 1, 0x80000000, 0xE3069283, MAX_U32):
        for offset, count in ((0, 0), (8, 0), (0, 8), (3, 2)):
            yield crc_case(f"finalized prior {previous:#x}, {offset}+{count}", values, offset, count, previous)
    for previous in (1 << 32, 1 << 63, MAX_U64):
        for offset, count in ((0, 8), (0, 0), (MIN_I64, MAX_I64)):
            name = f"invalid prior {previous:#x}, precedence {offset}+{count}"
            yield crc_case(name, values, offset, count, previous)
    for selector, status in ((1, "out_of_range"), (2, "invalid_previous")):
        yield f"{status} checksum result masks a nonzero payload", {"operation": FABRICATED, "selector": selector}, 3


def format_result(driver, values, words):
    operation = values["operation"]
    if operation == READ or (operation == FABRICATED and values["selector"] == 0):
        status = driver.name("ByteReadStatus", words[0])
    else:
        status = driver.name("ChecksumStatus", words[0])
    if operation == SPLIT:
        return f"{status} {words[1]:#010x} {driver.name('ChecksumStatus', words[2])} {words[3]:#010x}"
    value = (
        f"{words[1]:#x}"
        if operation == READ or operation == FABRICATED and values["selector"] == 0
        else f"{words[1]:#010x}"
    )
    return f"{status} {value} {words[2]:#x}"


def describe(compiler, directory):
    driver = harness.Driver(compiler, directory, harness.HERE / "storage_binary.au", "BinaryInput")
    corpus = list(read_cases()) + list(crc_cases())
    for (label, values, _), words in zip(corpus, driver.run([(values, slots) for _, values, slots in corpus])):
        if label.startswith("published "):
            published = {f"published {name}": crc for name, _, crc in VECTORS}[label]
            harness.require(words[0] == 0 and words[1] == published, label + ": published CRC32C check value")
        yield label, format_result(driver, values, words)


if __name__ == "__main__":
    harness.main("storage_binary", describe)

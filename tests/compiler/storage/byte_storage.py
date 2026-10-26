#!/usr/bin/env python3
"""std.bytes, std.binary_buffer, storage.sector and storage.sector_window as data cases.

Write and read statuses, decoded values and scenario results are golden. Byte
contents after every operation are checked against a replay of the observed
statuses with Python's int.to_bytes, so the golden lines stay short. Bounds
traps run the same driver binary with a case selector.
"""

from __future__ import annotations

import random
import struct

import harness
from harness import require

MIN_I64, MAX_I64, MAX_U64 = -(1 << 63), (1 << 63) - 1, (1 << 64) - 1
BUFFER, SECTOR, WINDOW, CODEC, SCENARIO = range(5)
WRITE, READ_U8, AT, WRITE_BYTE, READ_BYTE, WRITE_RECORD, READ_RECORD = range(1, 8)
OUTPUTS = {WRITE: 1, READ_U8: 3, AT: 1, WRITE_BYTE: 1, READ_BYTE: 3, WRITE_RECORD: 1, READ_RECORD: 9}
BUFFER_INITIAL = bytes(range(128, 192))
SECTOR_INITIAL = bytes((index * 37 + index // 256 * 19 + 11) % 256 for index in range(512))


def window_pattern(length):
    return bytes((index * 53 + index // 256 * 31 + 7) % 256 for index in range(length))


class Ops:
    """An operation list: (kind, width, big-endian, offset, value, pattern index)."""

    def __init__(self):
        self.entries = []

    def add(self, kind, offset, value=0, width=1, big=False, pattern=0):
        self.entries.append((kind, width, int(big), offset, value, pattern))
        return self

    def encode(self):
        raw = b"".join(
            struct.pack("<BBBBBxxxqQ", kind, width, big, pattern, value & 255, offset, value)
            for kind, width, big, offset, value, pattern in self.entries
        )
        require(len(raw) <= 1024, "operation list fits ops0/ops1")
        return {"ops0": raw[:512], "ops1": raw[512:], "op_count": len(self.entries)}

    def slots(self, dump, words):
        count = sum(OUTPUTS[entry[0]] for entry in self.entries)
        dumps = len(self.entries) if dump else 1
        return count + dumps * words


def ops_case(label, target, ops, initial=None, patterns=(), dump=False):
    data = (initial or b"").ljust(512, b"\0") + b"".join(patterns)
    values = {"operation": target, "seeded": int(initial is not None), "dump": int(dump), **ops.encode()}
    values.update(harness.spread("data", data, 8))
    words = 8 if target == BUFFER else 64
    meta = {"ops": ops, "initial": initial, "patterns": patterns, "dump": dump}
    return label, values, ops.slots(dump, words), meta


def scenario(label, selector, slots=1, data=b"", ops=None, **values):
    record = {"operation": SCENARIO, "selector": selector, **values, **harness.spread("data", data, 8)}
    if ops is not None:
        record.update(ops.encode())
    return label, record, slots, {"data": data}


# --- std.binary_buffer ---------------------------------------------------------------


def buffer_write(label, offset, width, endian, value):
    ops = Ops().add(WRITE, offset, value, width // 8, endian == "be")
    return ops_case(label, BUFFER, ops, BUFFER_INITIAL)


def buffer_cases(seed=24024, count=2):
    yield ops_case("size, exact representation and zero initialization", BUFFER, Ops())
    for offset in (MIN_I64, -1, 0, 63, 64, MAX_I64):
        for value in (0, 42, 255):
            yield buffer_write(f"u8 offset {offset} value {value}", offset, 8, "le", value)
    yield scenario("ordinary copied argument and return remain independent", 3)
    for width in (16, 32, 64):
        for endian in ("le", "be"):
            value = 0x0123456789ABCDEF & ((1 << width) - 1)
            ops = Ops().add(WRITE, 3, value, width // 8, endian == "be")
            yield scenario(
                f"readonly reader interoperation {endian}{width}",
                4,
                ops=ops,
                width=width // 8,
                big_endian=int(endian == "be"),
            )
    rng = random.Random(seed)
    for width in (16, 32, 64):
        maximum, size = (1 << width) - 1, width // 8
        values = [0, 1, 1 << (width - 1), maximum, 0x0123456789ABCDEF & maximum]
        values += [rng.randrange(1 << width) for _ in range(count)]
        for endian in ("le", "be"):
            for value in values:
                for offset in (0, 1, 7, 64 - size):
                    yield buffer_write(f"{endian}{width} value {value} offset {offset}", offset, width, endian, value)
            failures = [(offset, maximum) for offset in (MIN_I64, -1, 64 - size + 1, 63, 64, MAX_I64)]
            if width < 64:
                failures += [(o, v) for o in (-1, 0, 64 - size, 64, MAX_I64) for v in (maximum + 1, MAX_U64)]
            for offset, value in failures:
                yield buffer_write(
                    f"unchanged {endian}{width} offset {offset} value {value}", offset, width, endian, value
                )
    rng = random.Random(seed)
    for sequence in range(8):
        ops = Ops()
        for _ in range(20):
            width = rng.choice((16, 32, 64))
            endian = rng.choice(("le", "be"))
            offset = rng.choice((-1, 0, 1, 5, 7, 8, 31, 56, 60, 62, 63, 64))
            value = rng.choice((0, 42, (1 << width) - 1, MAX_U64))
            ops.add(WRITE, offset, value, width // 8, endian == "be")
        yield ops_case(f"overlapping sequence {sequence}", BUFFER, ops, BUFFER_INITIAL, dump=True)
    for offset in range(64):
        for value in (0, 1, 128, 255):
            yield buffer_write(f"independent byte {offset} value {value}", offset, 8, "le", value)
    for offset in (MIN_I64, -1, 64, MAX_I64):
        ops = Ops().add(WRITE, offset, 255).add(READ_U8, offset)
        yield ops_case(f"signed read/write boundary {offset} preserves all bytes", BUFFER, ops, BUFFER_INITIAL)
    yield scenario("failed byte reports mask nonzero u64 payloads", 5)
    yield scenario("copied byte report survives source mutation", 6, data=BUFFER_INITIAL, seeded=1)
    yield scenario("copied values and function boundaries preserve all bytes", 7, data=BUFFER_INITIAL, seeded=1)
    yield scenario("copied record codecs preserve independent wire bytes", 8)


# --- storage.sector --------------------------------------------------------------------


def sector_cases():
    yield ops_case("zero initialization and exact sector layout", SECTOR, Ops())
    for offset in range(512):
        ops = Ops().add(WRITE_BYTE, offset, 255 - SECTOR_INITIAL[offset])
        yield ops_case(f"byte {offset} is independently writable", SECTOR, ops, SECTOR_INITIAL)
    for offset in (MIN_I64, -1, 512, MAX_I64):
        ops = Ops().add(WRITE_BYTE, offset, 255).add(READ_BYTE, offset)
        yield ops_case(f"invalid byte {offset} is recoverable and unchanged", SECTOR, ops, SECTOR_INITIAL)
    yield scenario("whole-sector argument and return copies", 9, data=SECTOR_INITIAL, seeded=1)
    yield scenario("retained byte result survives overwrite", 10, data=SECTOR_INITIAL, seeded=1)
    for offset in range(449):
        ops = Ops().add(READ_RECORD, offset)
        yield ops_case(f"valid window {offset} reads all 64 bytes", SECTOR, ops, SECTOR_INITIAL)
    pattern = bytes((index * 17 + 203) % 256 for index in range(64))
    for offset in range(449):
        ops = Ops().add(WRITE_RECORD, offset)
        yield ops_case(f"valid window {offset} write preserves neighbors", SECTOR, ops, SECTOR_INITIAL, [pattern])
    for offset in (MIN_I64, -1, 449, 511, 512, MAX_I64):
        ops = Ops().add(WRITE_RECORD, offset).add(READ_RECORD, offset)
        label = f"invalid window {offset} masks the read and preserves all sector bytes"
        yield ops_case(label, SECTOR, ops, SECTOR_INITIAL, [bytes([255]) * 64])
    for offset in (0, 1, 255, 448):
        label = f"window {offset} report and extracted copies survive sector mutation"
        yield scenario(label, 11, data=SECTOR_INITIAL, seeded=1, offset=offset)
    yield scenario("write takes a complete copied block", 12, data=SECTOR_INITIAL + pattern, seeded=1)
    for width in (16, 32, 64):
        size = width // 8
        for endian in ("le", "be"):
            for offset in (0, 1, 448):
                value = 0x89ABCDEF01234567 & ((1 << width) - 1)
                ops = Ops().add(WRITE, 64 - size, value, size, endian == "be")
                label = f"{endian}{width} codec at window {offset} with independent wire bytes"
                yield scenario(
                    label,
                    13,
                    65,
                    SECTOR_INITIAL,
                    ops,
                    seeded=1,
                    offset=offset,
                    width=size,
                    big_endian=int(endian == "be"),
                )
    rng = random.Random(51264)
    for sequence in range(4):
        ops, patterns = Ops(), []
        for operation in range(12):
            offset = rng.choice((-1, 0, 1, 63, 64, 255, 256, 447, 448, 449, 511, MAX_I64))
            if operation % 3 == 0:
                ops.add(WRITE_BYTE, offset, rng.randrange(256))
            else:
                patterns.append(bytes(rng.randrange(256) for _ in range(64)))
                ops.add(WRITE_RECORD, offset, pattern=len(patterns) - 1)
        yield ops_case(f"mixed overlapping writes sequence {sequence}", SECTOR, ops, SECTOR_INITIAL, patterns, True)
    record = bytes((index * 29 + 7) % 256 for index in range(64))
    for selector, status in ((0, "success"), (1, "out_of_range")):
        label = f"record report layout, copying and masking {status}"
        yield scenario(label, 14, 10, bytes(512) + record, offset=selector)
    ops, patterns = Ops(), []
    for position in (0, 64, 128, 192, 64, 0):
        patterns.append(bytes((position + index * 11 + 3) % 256 for index in range(64)))
        ops.add(WRITE_RECORD, position, pattern=len(patterns) - 1)
    label = "four records share one sector without changing other records or unused bytes"
    yield ops_case(label, SECTOR, ops, None, patterns, True)


# --- storage.sector_window -------------------------------------------------------------


def window_case(length, base, requested, offset=0, owner_length=None, constant=False):
    owner_length = max(1, length) if owner_length is None else owner_length
    source = window_pattern(owner_length)
    label = f"window length={length}, base={base}, request={requested}, offset={offset}, const={constant}"
    values = dict(operation=WINDOW, length=length, length2=owner_length, offset=offset, base=base)
    values.update(requested=requested, constant=int(constant), **harness.spread("data", source, 8))
    return label, values, 65, {"window": source[offset : offset + length]}


def window_cases():
    for count in range(1, 9):
        for index in range(count):
            yield window_case(count * 512, 19, 19 + index, constant=count % 2 == 0)
    for length in (0, 1, 511, 513, 1023, 1025, 4095):
        for base, requested in ((0, 0), (MAX_U64, MIN_I64), (MAX_U64, MAX_I64)):
            yield window_case(length, base, requested)
    yield window_case(0, MAX_U64, MIN_I64, offset=4096, owner_length=4096)
    for offset, length, requested in ((1, 512, 7), (17, 1024, 8), (511, 512, 7), (1, 3584, 13)):
        yield window_case(length, 7, requested, offset=offset, owner_length=4096)
    for base in (0, 1, 1 << 32, MAX_I64 - 7, MAX_I64, 1 << 63, MAX_U64 - 7, MAX_U64):
        requests = {MIN_I64, -1, 0, MAX_I64}
        requests.update(value for value in (base - 1, base, base + 7, base + 8) if 0 <= value <= MAX_I64)
        for requested in sorted(requests):
            yield window_case(4096, base, requested)
    yield window_case(512, 0, 1)
    yield window_case(512, MAX_I64, MAX_I64)
    yield scenario(
        "retained window report and copies survive complete owner replacement", 15, data=window_pattern(4096)
    )
    yield scenario("owned window report outlives local source array", 16, data=window_pattern(1024))


# --- std.bytes -------------------------------------------------------------------------


def codec_case(label, width, endian, value=0, data=None):
    values = dict(operation=CODEC, width=width, big_endian=int(endian == "be"), value=value)
    return label, {**values, **harness.spread("data", data or b"", 8)}, 5, {"input": data is not None}


def codec_cases(seed=13013, count=16):
    rng = random.Random(seed)
    values = [0, 1, 42, 127, 128, 255, 256, 65535, 65536, 0x12345678, 0x80000000, 0xFFFFFFFF, 1 << 32, MAX_U64]
    values += [rng.randrange(1 << 32) for _ in range(count)]
    for value in values:
        for endian in ("le", "be"):
            yield codec_case(f"{endian}32 encode {value}", 4, endian, value)
    yield scenario("32-bit failure masks a deliberately nonzero public report", 17)
    yield scenario("32-bit success report and output copies are independent", 18)
    yield scenario("all byte values remain valid data", 19)
    rng = random.Random(seed)
    for width in (16, 64):
        size, maximum = width // 8, (1 << width) - 1
        values = [0, 1, 42, 127, 128, 255, 256, 0x1234, 0x8000, 65535]
        values += [65536, 1 << 32, MAX_U64] if width == 16 else [1 << 32, 1 << 63, 0x0123456789ABCDEF, maximum]
        values += [rng.randrange(1 << width) for _ in range(count)]
        for value in values:
            for endian in ("le", "be"):
                yield codec_case(f"{endian}{width} encode {value}", size, endian, value)
        patterns = [bytes(size), bytes([255]) * size, bytes([128]) + bytes(size - 1), bytes(size - 1) + bytes([128])]
        patterns += [bytes(range(1, size + 1))]
        patterns += [bytes(rng.randrange(256) for _ in range(size)) for _ in range(count)]
        for index, pattern in enumerate(patterns):
            for endian in ("le", "be"):
                yield codec_case(f"{endian}{width} independent input {index}", size, endian, 0, pattern)
        for endian in ("le", "be"):
            value = 0x1234 if width == 16 else 0x0123456789ABCDEF
            label = f"{endian}{width} owned encoding to readonly reader"
            yield scenario(label, 26, width=size, big_endian=int(endian == "be"), value=value)
    yield scenario("16-bit failure masks all nonzero public payload bytes", 20)
    yield scenario("16-bit report constructor and accessors copy independently", 21)
    yield scenario("64-bit encoded results and copies are independent", 22)
    yield scenario("Bytes2 and Bytes8 zero initialization", 23)
    yield scenario("Bytes2 copied function value and result", 24)
    yield scenario("Bytes8 copied function value and result", 25)
    yield scenario("layout and runtime metadata", 0, 16)
    for capacity in (1, 3, 4, 7, 8, 9, 64):
        yield scenario(f"compact wrapper capacity {capacity}", 1, offset=capacity)
    yield scenario("natural mixed widths nested empty and copied results", 2)


# --- formatting and replay -------------------------------------------------------------


def replay(driver, meta, target, observed):
    """Status words, then whether every dump and read matches the replayed bytes."""
    state = bytearray(meta["initial"] or bytes(64 if target == BUFFER else 512))
    size = len(state)
    names, cursor, mismatch = [], 0, None
    entries = meta["ops"].entries
    for index, (kind, width, big, offset, value, pattern) in enumerate(entries):
        status = observed[cursor]
        if kind in (WRITE, WRITE_BYTE, WRITE_RECORD):
            names.append(driver.name("ByteWriteStatus", status))
            if status == 0:
                encoded = (value & 255).to_bytes(1, "little") if width == 1 else None
                if kind == WRITE and width > 1:
                    encoded = value.to_bytes(width, "big" if big else "little") if value < 1 << (8 * width) else b""
                if kind == WRITE_RECORD:
                    encoded = meta["patterns"][pattern]
                if not encoded or not 0 <= offset <= size - len(encoded):
                    mismatch = mismatch or f"write{index}"
                else:
                    state[offset : offset + len(encoded)] = encoded
            cursor += 1
        elif kind in (READ_U8, READ_BYTE):
            names.append(driver.name("ByteReadStatus", status) + f":{observed[cursor + 1]}:{observed[cursor + 2]:#x}")
            expected = state[offset] if status == 0 and 0 <= offset < size else None
            if (
                status == 0
                and observed[cursor + 1] != expected
                or status != 0
                and observed[cursor + 1 : cursor + 3] != [42, MAX_U64]
            ):
                mismatch = mismatch or f"read{index}"
            cursor += 3
        elif kind == READ_RECORD:
            names.append(driver.name("ByteReadStatus", status))
            record = b"".join(word.to_bytes(8, "little") for word in observed[cursor + 1 : cursor + 9])
            expected = bytes(state[offset : offset + 64]) if status == 0 and 0 <= offset <= size - 64 else bytes(64)
            if record != expected:
                mismatch = mismatch or f"record{index}"
            cursor += 9
        if meta["dump"] or index == len(entries) - 1:
            words = size // 8
            dumped = b"".join(word.to_bytes(8, "little") for word in observed[cursor : cursor + words])
            if dumped != state:
                mismatch = mismatch or f"bytes{index}"
            cursor += words
    if not entries:
        dumped = b"".join(word.to_bytes(8, "little") for word in observed)
        names.append("zero" if dumped == bytes(size) else "nonzero")
    return " ".join(names + ["bytes=" + ("ok" if mismatch is None else "differ@" + mismatch)])


def format_result(driver, values, meta, observed):
    operation = values["operation"]
    if operation in (BUFFER, SECTOR):
        return replay(driver, meta, operation, observed)
    if operation == WINDOW:
        sector = b"".join(word.to_bytes(8, "little") for word in observed[1:])
        return f"{driver.name('SectorIoStatus', observed[0])} {harness.describe_sector(meta['window'], sector)}"
    if operation == CODEC:
        if meta["input"]:
            return f"decoded={observed[4]:#x}"
        status = driver.name("ByteCodecStatus", observed[0]) if values["width"] != 8 else "unchecked"
        return f"{status} bytes={observed[1]:#x} same={observed[2]:#x} opposite={observed[3]:#x}"
    selector = values["selector"]
    if selector == 13:
        sector = b"".join(word.to_bytes(8, "little") for word in observed[1:65])
        return f"{observed[0]:#x} sector={'ok' if sector_codec_ok(values, sector) else 'differ'}"
    if selector == 14:
        record = b"".join(word.to_bytes(8, "little") for word in observed[2:10])
        expected = meta["data"][512:576] if observed[1] == 0 else bytes(64)
        status = driver.name("ByteReadStatus", observed[1])
        return f"size={observed[0]} {status} record={'ok' if record == expected else 'differ'}"
    return " ".join(f"{word:#x}" for word in observed)


def sector_codec_ok(values, sector):
    """The record lands at `offset`: zeros, then the value encoded with int.to_bytes at its end."""
    _, width, big, _, _, _, value = struct.unpack("<BBBBBxxxqQ", values["ops0"][:24])
    state = bytearray(SECTOR_INITIAL)
    record = bytearray(64)
    record[64 - width :] = value.to_bytes(width, "big" if big else "little")
    state[values["offset"] : values["offset"] + 64] = record
    return bytes(state) == sector


BUFFER_PREFIX = "module test; import std.binary_buffer; import std.binary;"
BUFFER_PREFIX += "auto consume(builtin::span<const u8> input) -> u64 { return u64(input.size()); }"
BUFFER_PREFIX += "auto test() -> u64 {std::BinaryBuffer64 buffer = std::BinaryBuffer64();"
SECTOR_PREFIX = "module test; import std.binary; import std.binary_buffer; import storage.sector; auto test() -> u64 {"
SECTOR_PREFIX += "storage::Sector512 sector = storage::Sector512();"
WINDOW_IMPORTS = "module test; import std.binary; import std.binary_buffer; import storage.sector;"
WINDOW_IMPORTS += " import storage.block_io; import storage.sector_window;"
WINDOW_PREFIX = WINDOW_IMPORTS + " auto test() -> u64 { builtin::array<u8, 512> bytes = {"
WINDOW_PREFIX += ", ".join(f"{value}u8" for value in window_pattern(512)) + "};\n"
CODEC_PREFIX = "module test;import std.bytes;auto test()->u64{const std::Encode32Result result=std::encode_le32(42u64);"


def rejections():
    """One rejection per rule the storage API relies on; the rules themselves are
    the compiler-semantics tests'."""
    for body in (
        "return u64(buffer.elements[0]);",
        "const std::BinaryBuffer64 frozen = buffer; frozen.write_u8(0, 1u8); return 0u64;",
        "buffer.write_u8(0, 1u64); return 0u64;",
        "return consume(borrow_bytes(buffer));",
    ):
        yield "buffer", BUFFER_PREFIX + body + "}"
    yield "sector", SECTOR_PREFIX + "sector.write_record(0, sector); return 0u64;}"
    call = "const storage::SectorReadResult report = storage::read_sector_window(bytes, 0u64, 0); return 0u64; }"
    yield "window array needs an explicit borrow", WINDOW_PREFIX + call
    yield (
        "window report payload stays private",
        WINDOW_PREFIX
        + (
            "const storage::SectorReadResult report = storage::read_sector_window(borrow_bytes(bytes), 0u64, 0);"
            "const storage::Sector512 leaked = report.payload; return 0u64; }"
        ),
    )
    oversized = "builtin::array<u8, 4097> bytes = {" + ", ".join(f"{v}u8" for v in window_pattern(4097)) + "};\n"
    yield "window source array cannot exceed 4096", "module test; auto test() -> u64 {" + oversized + "return 0u64; }"
    for body in (
        "return result.value();",
        "return std::encode_le32(42);",
        "const std::Bytes4 bytes=std::Bytes4{.elements={0u8,0u8,0u8,0u8}};return 0u64;",
    ):
        yield "codec", CODEC_PREFIX + body + "}"


TRAPS = (-1, 64, MAX_I64)
EXAMPLES = ("binary_buffer.au", "storage_codec.au")


def cases():
    return [*buffer_cases(), *sector_cases(), *window_cases(), *codec_cases()]


def describe(compiler, directory):
    driver = harness.Driver(compiler, directory, harness.HERE / "byte_storage.au", "ByteInput")
    corpus = cases()
    observed = driver.run([(values, slots) for _, values, slots, _ in corpus])
    for (label, values, _, meta), words in zip(corpus, observed):
        yield label, format_result(driver, values, meta, words)
    for offset in TRAPS:
        _, values, slots, _ = ops_case("trap", BUFFER, Ops().add(AT, offset))
        yield f"buffer read bounds {offset}", driver.trap(values, slots)
    for example in EXAMPLES:
        yield (
            f"example {example}",
            harness.run_example(compiler, directory, harness.ROOT / "library/examples" / example),
        )
    sources = [(f"{index} {label}", source) for index, (label, source) in enumerate(rejections())]
    yield from harness.rejections(compiler, directory, sources)


if __name__ == "__main__":
    harness.main("byte_storage", describe)

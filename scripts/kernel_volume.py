#!/usr/bin/env python3
"""Write a boot volume (kernel/uefi/process.md#boot-volume), or a bundle of cases.

    kernel_volume.py --output FILE [--root DIR] [ENTRY...] [EDIT...]
    kernel_volume.py --cases FILE --output BUNDLE [--root DIR]

Entries: --file PATH (the repository file PATH under --root, stored as PATH) and
--text PATH=CONTENT, and --entries N adds entry/0000.. each holding its number.
Entries are sorted unless --raw-order keeps their order.
--set OFFSET:WIDTH:VALUE edits a little-endian field before the checksum is
computed; --corrupt OFFSET:VALUE edits one byte after it; --truncate N and
--append N shorten or extend the written volume; --empty writes zero bytes.
This is the volume's writer, not a checker: the kernel admits volumes in
Aurora, and hostile cases are made by editing a canonical one.

A case file holds one case per line, `NAME ARGUMENT...` (shell words; --query
PATH adds a lookup for the hosted driver). The bundle repeats: u32 name length,
name, u32 query count, (u32 length, query) each, u64 volume length, volume.
"""

import argparse
from pathlib import Path
import shlex
import struct
import sys

MAGIC = b"AURORAVL"
HEADER, ENTRY = 64, 32


def _crc_row(value):
    for _ in range(8):
        value = (value >> 1) ^ (0x82F63B78 & -(value & 1))
    return value


CRC_TABLE = [_crc_row(value) for value in range(256)]


def crc32c(data, crc=0):
    crc ^= 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ CRC_TABLE[(crc ^ byte) & 255]
    return crc ^ 0xFFFFFFFF


def align8(value):
    return (value + 7) // 8 * 8


def volume(entries, raw_order=False, sets=()):
    if not raw_order:
        entries = sorted(entries)
    names = b"".join(path for path, _ in entries)
    names_offset = HEADER + ENTRY * len(entries)
    data_offset = align8(names_offset + len(names))
    index, data, name_cursor = b"", b"", 0
    for path, content in entries:
        index += struct.pack("<QIIQQ", name_cursor, len(path), 0, len(data), len(content))
        name_cursor += len(path)
        data += content + bytes(align8(len(content)) - len(content))
    header = struct.pack(
        "<8sIIIIQQQQII",
        MAGIC,
        1,
        HEADER,
        len(entries),
        ENTRY,
        names_offset,
        len(names),
        data_offset,
        len(data),
        0,
        0,
    )
    result = bytearray(header + index + names + bytes(data_offset - names_offset - len(names)) + data)
    for offset, width, value in sets:
        result[offset : offset + width] = value.to_bytes(width, "little")
    result[56:60] = struct.pack("<I", crc32c(result[64:], crc32c(result[:56])))
    return result


def number(text):
    return int(text, 0)


def parser():
    result = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument("--file", action="append", default=[], dest="files")
    result.add_argument("--text", action="append", default=[], dest="texts")
    result.add_argument("--entries", type=number, default=0)
    result.add_argument("--raw-order", action="store_true")
    result.add_argument("--set", action="append", default=[], dest="sets")
    result.add_argument("--corrupt", action="append", default=[])
    result.add_argument("--truncate", type=number, default=0)
    result.add_argument("--append", type=number, default=0)
    result.add_argument("--empty", action="store_true")
    result.add_argument("--query", action="append", default=[])
    return result


def build(args, root):
    if args.empty:
        return b""
    entries = [(path.encode(), (root / path).read_bytes()) for path in args.files]
    entries += [(text.partition("=")[0].encode(), text.partition("=")[2].encode()) for text in args.texts]
    entries += [(b"entry/%04d" % index, b"%d" % index) for index in range(args.entries)]
    sets = [tuple(number(part) for part in edit.split(":")) for edit in args.sets]
    result = volume(entries, args.raw_order, sets)
    for edit in args.corrupt:
        offset, value = map(number, edit.split(":"))
        result[offset] = value
    if args.truncate:
        del result[-args.truncate :]
    return bytes(result) + bytes(args.append)


def main(argv):
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--output", type=Path, required=True)
    top.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    top.add_argument("--cases", type=Path)
    known, rest = top.parse_known_args(argv)
    if known.cases is None:
        known.output.write_bytes(build(parser().parse_args(rest), known.root))
        return 0
    if rest:
        top.error("--cases takes no entry arguments")
    bundle = bytearray()
    for line in known.cases.read_text().splitlines():
        words = shlex.split(line, comments=True)
        if not words:
            continue
        name, args = words[0], parser().parse_args(words[1:])
        data = build(args, known.root)
        bundle += struct.pack("<I", len(name)) + name.encode() + struct.pack("<I", len(args.query))
        for query in args.query:
            bundle += struct.pack("<I", len(query.encode())) + query.encode()
        bundle += struct.pack("<Q", len(data)) + data
    # Zero runs (the oversize case's tail) stay holes in a sparse file.
    with known.output.open("wb") as output:
        for at in range(0, len(bundle), 1 << 20):
            chunk = bundle[at : at + (1 << 20)]
            if chunk.count(0) == len(chunk):
                output.seek(len(chunk), 1)
            else:
                output.write(chunk)
        output.truncate()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

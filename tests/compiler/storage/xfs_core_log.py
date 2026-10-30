#!/usr/bin/env python3
"""Complete CORE transactions: preserved Linux bytes and CRC-repaired hostile inputs."""

import json

import harness
from xfs_inputs import hex_fixture


def describe(compiler, directory):
    hashes = json.loads((harness.ROOT / "fixtures/xfs-core-redo/hashes.json").read_text())

    def fixture(name):
        return hex_fixture("xfs-core-redo", name + ".hex", hashes[name + ".hex"])

    rows = []

    def case(label, header, payload, index=0, expected=None, **fields):
        values = dict(header=header, header_length=len(header), payload_length=len(payload), index=index)
        values.update(harness.spread("payload", payload, 2))
        values.update(fields)
        rows.append((label, values, expected))

    def crc(header, payload):
        changed = bytearray(header)
        changed[32:36] = bytes(4)
        changed[32:36] = harness.crc32c(changed[:328] + payload).to_bytes(4, "little")
        return bytes(changed)

    for record, inodes in ((2, (100, 99)), (5, (99,))):
        header, payload = (fixture(f"log-record-{record}-{part}") for part in ("header", "stamped"))
        for index, inode in enumerate(inodes):
            core = fixture(f"log-record-{record}-inode-{inode}-core") + bytes(336)
            case(f"Linux record {record} item {index}", header, payload, index, core)
        for index in (-1, len(inodes), 9223372036854775807):
            case(f"record {record} invalid index {index}", header, payload, index, bytes(512))
        case(f"record {record} short header", header, payload, expected=bytes(512), header_length=511)
        case(f"record {record} short body", header, payload, expected=bytes(512), payload_length=len(payload) - 1)
        bad = bytearray(payload)
        bad[120] ^= 1
        case(f"record {record} bad checksum", header, bytes(bad), expected=bytes(512))
        for offset in range(0, len(payload), 512):
            bad = bytearray(payload)
            bad[offset + 3] ^= 1
            case(
                f"record {record} wrong stamp sector {offset // 512}", crc(header, bad), bytes(bad), expected=bytes(512)
            )
        for offset, width, value in (
            (36, 4, 0),
            (36, 4, 1),
            (36, 4, 34),
            (68, 8, 0),
            (92, 8, 1 << 63),
            (100, 4, 0),
            (100, 4, 129),
            (104, 4, 1),
            (104, 4, 16384),
        ):
            bad = bytearray(payload)
            bad[offset : offset + width] = value.to_bytes(width, "little")
            case(f"record {record} invalid field {offset}={value}", crc(header, bad), bytes(bad), expected=bytes(512))
        bad_header = bytearray(header)
        bad_header[40:44] = (99).to_bytes(4, "big")
        case(f"record {record} wrong operation count", crc(bad_header, payload), payload, expected=bytes(512))
        # Every operation's reserved fields, flags and client, plus item format and
        # transaction headers. Inputs are repaired; expected refusal is reviewed.
        offsets = [8, 9, 10, 20, 21, 22, 24, 28, 32, 36]
        for item in range(len(inodes)):
            at = 40 + item * 256
            offsets += [at, at + 4, at + 8, at + 9, at + 10]
            offsets += [at + 12, at + 14, at + 16, at + 20, at + 24, at + 36, at + 44]
            offsets += [at + 68, at + 72, at + 76, at + 77, at + 78]
        end = 40 + len(inodes) * 256
        offsets += [end, end + 4, end + 8, end + 9, end + 10]
        for offset in offsets:
            bad = bytearray(payload)
            bad[offset] ^= 1
            case(f"record {record} malformed byte {offset}", crc(header, bad), bytes(bad), expected=bytes(512))
    driver = harness.Driver(compiler, directory, harness.HERE / "xfs_core_log.au", "LogInput")
    results = driver.run([(values, 71) for _, values, _ in rows])
    for (label, _, expected), result in zip(rows, results):
        core = b"".join(word.to_bytes(8, "little") for word in result[7:])
        harness.require(core == expected, f"{label}: unexpected CORE bytes or nonzero failure")
        yield label, " ".join([driver.name("XfsCoreLogStatus", result[0]), *map(str, result[1:7])])


if __name__ == "__main__":
    harness.main("xfs_core_log", describe)

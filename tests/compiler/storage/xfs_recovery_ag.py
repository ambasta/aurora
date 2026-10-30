#!/usr/bin/env python3
"""Bounded recovery AG summaries over preserved Linux headers and mutations."""

import json
import os
import struct
from concurrent.futures import ThreadPoolExecutor
import harness
from xfs_inputs import hex_fixture, set_fields


def describe(compiler, directory):
    hashes = json.loads((harness.ROOT / "fixtures/xfs-recovery-ag/hashes.json").read_text())

    def fixture(name):
        return hex_fixture("xfs-recovery-ag", name + ".hex", hashes[name + ".hex"])

    sb = fixture("superblock")
    rows = []

    def case(label, agf, agi, number=0, head=(1 << 32) | 7, length=512):
        rows.append((label, dict(sb=sb, agf=agf, agi=agi, number=number, head=head, length=length)))

    for ag in range(4):
        case(f"Linux AG {ag}", fixture(f"agf-{ag}"), fixture(f"agi-{ag}"), ag)
    agf, agi = fixture("agf-0"), fixture("agi-0")
    for number in (4, (1 << 64) - 1):
        case(f"invalid AG number {number}", agf, agi, number)
    case("short AGF", agf, agi, length=511)
    case("invalid head", agf, agi, head=0)
    for target, source, crc in (("AGF", agf, 216), ("AGI", agi, 312)):
        for at in (0, crc, 511):
            bad = bytearray(source)
            bad[at] ^= 1
            case(f"torn {target} {at}", bytes(bad) if target == "AGF" else agf, bytes(bad) if target == "AGI" else agi)
    for at, size, value in (
        (0, 4, 0),
        (4, 4, 2),
        (8, 4, 1),
        (12, 4, 32767),
        (16, 4, 0),
        (20, 4, 32768),
        (24, 4, 1),
        (28, 4, 2),
        (36, 4, 1),
        (40, 4, 119),
        (44, 4, 5),
        (48, 4, 120),
        (52, 4, 32769),
        (56, 4, 32768),
        (60, 4, 32768),
        (64, 1, 0),
        (80, 4, 1),
        (208, 8, (1 << 32) | 8),
        (220, 4, 1),
    ):
        case(f"AGF rejected field {at}", set_fields(agf, (at, size, value), crc=216), agi)
    for at, size, value in (
        (0, 4, 0),
        (4, 4, 2),
        (8, 4, 1),
        (12, 4, 32767),
        (16, 4, 262145),
        (20, 4, 0),
        (24, 4, 2),
        (28, 4, 65),
        (32, 4, 1),
        (36, 4, 262144),
        (296, 1, 0),
        (316, 4, 1),
        (320, 8, (1 << 32) | 8),
        (328, 4, 0),
        (332, 4, 2),
        (336, 4, 1),
        (511, 1, 1),
    ):
        case(f"AGI rejected field {at}", agf, set_fields(agi, (at, size, value), crc=312))
    for bucket in range(64):
        case(f"unlinked bucket {bucket}", agf, set_fields(agi, (40 + bucket * 4, 4, 99), crc=312))

    def inode_case(label, leaf, inode=99, ag=0, agi_bytes=None, length=4096):
        rows.append(
            (
                label,
                dict(
                    sb=sb,
                    agf=agf,
                    agi=fixture(f"agi-{ag}") if agi_bytes is None else agi_bytes,
                    leaf=leaf,
                    operation=1,
                    inode=inode,
                    number=ag,
                    head=(1 << 32) | 7,
                    length=length,
                ),
            )
        )

    leaf = fixture("inobt-0")
    for inode in (0, 95, 96, 97, 98, 99, 100, 101, 159, 160, (1 << 64) - 1):
        inode_case(f"Linux allocated inode {inode}", leaf, inode)
    for ag in (1, 2, 3):
        inode_case(f"Linux empty INOBT AG {ag}", fixture(f"inobt-{ag}"), ag=ag)
    inode_case("short INOBT", leaf, length=4095)
    for at in (0, 52, 56, 4095):
        bad = bytearray(leaf)
        bad[at] ^= 1
        inode_case(f"torn INOBT {at}", bytes(bad))
    for at, size, value in (
        (0, 4, 0),
        (4, 2, 1),
        (6, 2, 253),
        (8, 4, 3),
        (12, 4, 3),
        (16, 8, 25),
        (24, 8, (1 << 32) | 8),
        (32, 1, 0),
        (48, 4, 1),
        (56, 4, 97),
        (56, 4, 262136),
        (60, 4, 58),
        (60, 4, 65),
        (64, 8, (1 << 64) - 1),
    ):
        inode_case(f"INOBT rejected field {at} value {value}", set_fields(leaf, (at, size, value), crc=52))
    inode_case("INOBT AGI count mismatch", leaf, agi_bytes=set_fields(agi, (16, 4, 128), crc=312))
    inode_case("INOBT AGI free count mismatch", leaf, agi_bytes=set_fields(agi, (28, 4, 60), crc=312))
    two_agi = set_fields(agi, (16, 4, 128), (28, 4, 123), crc=312)
    two = set_fields(leaf, (6, 2, 2), (72, 4, 160), (76, 4, 64), (80, 8, (1 << 64) - 1), crc=52)
    inode_case("synthetic two ordered chunks", two, agi_bytes=two_agi)
    inode_case(
        "later overlapping record rejects allocated target", set_fields(two, (72, 4, 152), crc=52), agi_bytes=two_agi
    )
    inode_case(
        "later malformed count rejects allocated target", set_fields(two, (76, 4, 63), crc=52), agi_bytes=two_agi
    )
    mounted_hashes = json.loads((harness.ROOT / "fixtures/xfs-staged-replace/hashes.json").read_text())

    def mounted(name):
        filename = "mounted-" + name + ".hex"
        return hex_fixture("xfs-staged-replace", filename, mounted_hashes[filename])

    mounted_sb = mounted("superblock")
    mounted_agf, mounted_agi, mounted_agfl = (mounted(name) for name in ("agf", "agi", "agfl"))

    def ownership(label, operation, expected=False, **fields):
        values = dict(
            sb=mounted_sb,
            agf=mounted_agf,
            agi=mounted_agi,
            leaf=mounted_agfl + bytes(3584),
            operation=operation,
            head=(1 << 32) | 33,
            length=512,
            expected=int(expected),
        )
        values.update(fields)
        rows.append(("mounted ownership " + label, values))

    ownership("complete headers", 2, True)
    for target, source, crc, mutations in (
        ("sb", mounted_sb, 224, ((128, 8, 128), (136, 8, 123), (16, 8, 1), (64, 8, 99))),
        ("agf", mounted_agf, 216, ((16, 4, 9), (20, 4, 20), (40, 4, 0), (48, 4, 3), (52, 4, 32748), (60, 4, 1))),
        ("agi", mounted_agi, 312, ((16, 4, 128), (28, 4, 123), (20, 4, 9), (328, 4, 20))),
    ):
        for at, width, value in mutations:
            ownership(f"headers {target} field{at}", 2, **{target: set_fields(source, (at, width, value), crc=crc)})
    for at, width, value in ((40, 4, 9), (44, 4, 20), (36, 4, 5), (4, 4, 1), (8, 1, 0), (24, 8, (1 << 32) | 34)):
        bad = set_fields(mounted_agfl, (at, width, value), crc=32)
        ownership(f"AGFL field{at}", 2, leaf=bad + bytes(3584))
    for kind in range(1, 5):
        leaf = mounted(f"leaf-{kind}")
        ownership(f"complete leaf{kind}", 3, True, leaf=leaf, number=kind, length=4096)
        mutations = [
            (0, 4, 0),
            (4, 2, 1),
            (6, 2, 0),
            (8, 4, 1),
            (16, 8, 72),
            (24, 8, (1 << 32) | 34),
            (32, 1, 0),
            (48, 4, 1),
            (72, 1, 1),
            (4095, 1, 1),
        ]
        if kind <= 2:
            mutations += [(56, 4, 9), (56, 4, 12), (64, 4, 20), (68, 4, 32748)]
        else:
            mutations += [(56, 4, 104), (60, 4, 58), (64, 8, (1 << 64) - 64)]
        for at, width, value in mutations:
            ownership(
                f"leaf{kind} field{at}", 3, leaf=set_fields(leaf, (at, width, value), crc=52), number=kind, length=4096
            )
        ownership(
            f"leaf{kind} torn checksum",
            3,
            leaf=set_fields(leaf, (52, 1, leaf[52] ^ 1), crc=None),
            number=kind,
            length=4096,
        )
    for inode in (97, 98):
        home = mounted(f"empty-{inode}")
        ownership(f"empty special{inode}", 4, True, agf=home, inode=inode)
        for at, width, value in (
            (56, 8, 1),
            (64, 8, 1),
            (76, 4, 1),
            (78, 2, 1),
            (82, 1, 1),
            (83, 1, 1),
            (120, 8, 1),
            (152, 8, 99),
            (176, 8, 9),
            (184, 8, 20),
            (112, 8, (1 << 32) | 34),
        ):
            ownership(f"special{inode} field{at}", 4, agf=set_fields(home, (at, width, value), crc=100), inode=inode)
    ownership("short leaf", 3, leaf=mounted("leaf-1"), number=1, length=4095)
    ownership("unknown leaf", 3, leaf=mounted("leaf-1"), number=5, length=4096)
    assembly, obj, program = (directory / name for name in ("ag.s", "ag.o", "ag"))
    for command in (
        [
            compiler,
            "--module-root",
            harness.ROOT / "library",
            "--runtime-root",
            harness.ROOT / "runtime/linux",
            harness.HERE / "xfs_recovery_ag.au",
            "-o",
            assembly,
        ],
        ["as", "-o", obj, assembly],
        ["ld", "-o", program, obj],
    ):
        result = harness.command(command, timeout=120)
        harness.require(result.returncode == 0, result.stderr.decode())

    def run(row):
        index, (label, values) = row
        words = [values.get(name, 0) for name in ("operation", "inode", "number", "head", "length")]
        packet = struct.pack("<5Q", *words)
        packet += values["sb"] + values["agf"] + values["agi"] + values.get("leaf", bytes(4096))
        path = directory / f"case-{index}.bin"
        path.write_bytes(packet)
        result = harness.command([program, path])
        harness.require(
            result.returncode == 0 and not result.stderr and len(result.stdout) == 32,
            f"{label}: {result.returncode}: {result.stderr!r}",
        )
        words = struct.unpack("<4Q", result.stdout)
        if "expected" in values:
            harness.require(words == (values["expected"], 0, 0, 0), f"{label}: incorrect ownership admission {words}")
        return label, ",".join(str(value) for value in words)

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        yield from pool.map(run, enumerate(rows))


if __name__ == "__main__":
    harness.main("xfs_recovery_ag", describe)

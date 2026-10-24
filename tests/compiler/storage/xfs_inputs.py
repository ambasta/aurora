"""Preserved XFS fixture bytes and synthetic header/inode builders (inputs only).

Only the canonical preserved slices are mkfs output. Every mutated variant is a
synthetic input whose CRC is repaired so the intended later branch is reached;
none establishes anything about unseen disk contents.
"""

from __future__ import annotations

import hashlib
import importlib.util

from harness import ROOT, repair, require

# Superblock field offsets and widths, authored from the on-disk format.
SCHEMA = {
    "magic": (0, 4),
    "blocksize": (4, 4),
    "dblocks": (8, 8),
    "rblocks": (16, 8),
    "rextents": (24, 8),
    "logstart": (48, 8),
    "rbmino": (64, 8),
    "rsumino": (72, 8),
    "rextsize": (80, 4),
    "agblocks": (84, 4),
    "agcount": (88, 4),
    "rbmblocks": (92, 4),
    "logblocks": (96, 4),
    "versionnum": (100, 2),
    "sectsize": (102, 2),
    "inodesize": (104, 2),
    "inopblock": (106, 2),
    "blocklog": (120, 1),
    "sectlog": (121, 1),
    "inodelog": (122, 1),
    "inopblog": (123, 1),
    "agblklog": (124, 1),
    "rextslog": (125, 1),
    "inprogress": (126, 1),
    "imax_pct": (127, 1),
    "frextents": (152, 8),
    "qflags": (176, 2),
    "flags": (178, 1),
    "shared_vn": (179, 1),
    "inoalignmt": (180, 4),
    "unit": (184, 4),
    "width": (188, 4),
    "dirblklog": (192, 1),
    "logsectlog": (193, 1),
    "logsectsize": (194, 2),
    "logsunit": (196, 4),
    "features2": (200, 4),
    "bad_features2": (204, 4),
    "compat": (208, 4),
    "ro_compat": (212, 4),
    "incompat": (216, 4),
    "log_incompat": (220, 4),
    "spino_align": (228, 4),
}
SUPERBLOCK_CRC = 224
INODE_CRC = 100


def be(data, offset, count):
    return int.from_bytes(data[offset : offset + count], "big")


def change(data, repair_crc=True, **changes):
    """Set named superblock fields; repair the superblock CRC unless told not to."""
    result = bytearray(data)
    for name, value in changes.items():
        offset, width = SCHEMA[name]
        require(0 <= value < (1 << (width * 8)), "field mutation width " + name)
        result[offset : offset + width] = value.to_bytes(width, "big")
    return repair(result, SUPERBLOCK_CRC) if repair_crc else bytes(result)


def set_fields(data, *fields, crc=INODE_CRC):
    """Set (offset, width, value) big-endian fields; repair the CRC at `crc` unless None."""
    result = bytearray(data)
    for offset, count, value in fields:
        result[offset : offset + count] = value.to_bytes(count, "big")
    return repair(result, crc) if crc is not None else bytes(result)


def fix_inode(data):
    return repair(data, INODE_CRC)


def hex_fixture(directory, name, digest):
    transport = (ROOT / "fixtures" / directory / name).read_bytes()
    require(transport.endswith(b"\n") and transport.count(b"\n") == 1, "one-line canonical fixture " + name)
    require(all(c in b"0123456789abcdef" for c in transport[:-1]), "lowercase canonical fixture " + name)
    data = bytes.fromhex(transport.decode())
    require(hashlib.sha256(data).hexdigest() == digest, "fixture identity: " + name)
    return data


def offline_superblock():
    """The preserved real mkfs superblock, decoded by its fixture's own transport reader."""
    spec = importlib.util.spec_from_file_location(
        "xfs_offline_transport", ROOT / "fixtures/xfs-offline/verify_native.py"
    )
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    return transport.read_fixture_hex(ROOT / "fixtures/xfs-offline/superblock-v5-512.hex")


ROOT_FIXTURES = {
    "empty-superblock.hex": "55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586",
    "empty-root.hex": "963d4d1ae9f5821528cdeaac5dbc65abc0a4146a737dab84ade621a12d2c326e",
    "named-superblock.hex": "9fd8b9f7bfa7d12c99ae6e7b3a7633cc3ab48c45ff5facde79c36ad69503edb7",
    "named-root.hex": "283d31448057d3a9b1406cf655274b799e0636abb32e466b40c15bf3df9d265b",
}


def root_fixture(name):
    return hex_fixture("xfs-root", name, ROOT_FIXTURES[name])


def shortform(base, entries, parent=128):
    """A CRC-repaired root inode whose local directory holds (name, inode, type, offset) entries."""
    payload = bytes([len(entries), 0]) + parent.to_bytes(4, "big")
    for name, number, kind, offset in entries:
        payload += bytes([len(name)]) + offset.to_bytes(2, "big") + name + bytes([kind]) + number.to_bytes(4, "big")
    require(len(payload) <= 336, "synthetic payload bound")
    result = bytearray(base)
    result[176:] = bytes(336)
    result[176 : 176 + len(payload)] = payload
    result[56:64] = len(payload).to_bytes(8, "big")
    return fix_inode(result)

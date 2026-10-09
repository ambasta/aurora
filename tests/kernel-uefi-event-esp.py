#!/usr/bin/env python3
"""Small in-memory FAT controls. No disk images, mtools invocation or guests."""

from pathlib import Path
import hashlib
import importlib.util
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("event_esp", ROOT / "scripts/kernel_iommu_event_esp.py")
ESP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ESP)
LOADER = b"MZ" + bytes(range(256)) * 2 + bytes(range(186))
LOADER_SHA256 = hashlib.sha256(LOADER).hexdigest()


def entry(name, attributes, first=0, size=0):
    result = bytearray(32)
    result[:11] = name
    result[11] = attributes
    struct.pack_into("<H", result, 20, first >> 16)
    struct.pack_into("<H", result, 26, first & 0xFFFF)
    struct.pack_into("<I", result, 28, size)
    return result


class Fixture:
    """Sparse sector map for parser tests; never written as an image."""

    def __init__(self):
        self.fat_sectors = 1009
        self.data_sector = 32 + 2 * self.fat_sectors
        self.count = ESP.TOTAL_SECTORS - self.data_sector
        boot = bytearray(512)
        boot[:3] = b"\xeb\x58\x90"
        boot[13] = 1
        boot[16] = 2
        boot[21] = 0xF8
        boot[64] = 0x80
        boot[66] = 0x29
        boot[71:82] = ESP.LABEL
        boot[82:90] = b"FAT32   "
        boot[510:] = b"\x55\xaa"
        for offset, value in ((11, 512), (14, 32), (24, 32), (26, 64), (48, 1), (50, 6)):
            struct.pack_into("<H", boot, offset, value)
        for offset, value in ((32, ESP.TOTAL_SECTORS), (36, self.fat_sectors), (44, 2), (67, 0x41555241)):
            struct.pack_into("<I", boot, offset, value)
        info = bytearray(512)
        for offset, value in ((0, 0x41615252), (484, 0x61417272), (488, self.count - 5), (492, 7), (508, 0xAA550000)):
            struct.pack_into("<I", info, offset, value)
        self.blocks = {0: boot, 512: info, 6 * 512: bytearray(boot)}
        for offset in (32 * 512, (32 + self.fat_sectors) * 512):
            self.blocks[offset] = bytearray(self.fat_sectors * 512)
        for cluster, value in (
            (0, 0x0FFFFFF8),
            (1, 0xFFFFFFFF),
            (2, 0x0FFFFFFF),
            (3, 0x0FFFFFFF),
            (4, 0x0FFFFFFF),
            (5, 6),
            (6, 0x0FFFFFFF),
        ):
            self.fat(cluster, value)
        self.directory(2, [entry(ESP.LABEL, 0x08), entry(b"EFI        ", 0x10, 3)])
        self.directory(3, [entry(b".          ", 0x10, 3), entry(b"..         ", 0x10), entry(b"BOOT       ", 0x10, 4)])
        self.directory(
            4,
            [
                entry(b".          ", 0x10, 4),
                entry(b"..         ", 0x10, 3),
                entry(b"BOOTX64 EFI", 0x20, 5, len(LOADER)),
            ],
        )
        self.blocks[self.cluster_offset(5)] = bytearray(LOADER[:512])
        self.blocks[self.cluster_offset(6)] = bytearray(LOADER[512:].ljust(512, b"\0"))

    def cluster_offset(self, cluster):
        return (self.data_sector + cluster - 2) * 512

    def directory(self, cluster, entries):
        self.blocks[self.cluster_offset(cluster)] = bytearray(b"".join(entries).ljust(512, b"\0"))

    def fat(self, cluster, value, both=True):
        offsets = (32 * 512, (32 + self.fat_sectors) * 512) if both else (32 * 512,)
        for offset in offsets:
            struct.pack_into("<I", self.blocks[offset], cluster * 4, value)

    def boot(self, offset, value, width=2, both=True):
        for start in (0, 6 * 512) if both else (0,):
            struct.pack_into({1: "<B", 2: "<H", 4: "<I"}[width], self.blocks[start], offset, value)

    def info(self, offset, value):
        struct.pack_into("<I", self.blocks[512], offset, value)

    def read(self, offset, length):
        result = bytearray(length)
        for start, block in self.blocks.items():
            begin = max(start, offset)
            end = min(start + len(block), offset + length)
            if begin < end:
                result[begin - offset : end - offset] = block[begin - start : end - start]
        return bytes(result)

    def validate(self, digest=LOADER_SHA256, size=len(LOADER)):
        return ESP.Fat32(self.read, ESP.IMAGE_BYTES).validate(digest, size)


class FatAdmission(unittest.TestCase):
    def test_exact_manifest_and_readback(self):
        result = Fixture().validate()
        self.assertEqual(result["allocated_clusters"], 5)
        self.assertEqual(result["files"], [dict(path="EFI/BOOT/BOOTX64.EFI", bytes=len(LOADER), sha256=LOADER_SHA256)])

    def test_bpb_rejections(self):
        for offset, value, width in (
            (0, 0, 1),
            (510, 0, 2),
            (11, 4096, 2),
            (13, 2, 1),
            (14, 0, 2),
            (16, 1, 1),
            (17, 1, 2),
            (19, 1, 2),
            (21, 0, 1),
            (21, 0xF0, 1),
            (22, 1, 2),
            (24, 1, 2),
            (26, 1, 2),
            (28, 2048, 4),
            (32, ESP.TOTAL_SECTORS - 1, 4),
            (36, 0, 4),
            (36, 70000, 4),
            (36, 40000, 4),
            (36, 1, 4),
            (40, 0x80, 2),
            (42, 1, 2),
            (44, 3, 4),
            (48, 32, 2),
            (50, 32, 2),
            (52, 1, 1),
            (64, 0, 1),
            (65, 1, 1),
            (66, 0, 1),
            (67, 0, 4),
            (71, 0, 1),
            (82, 0, 1),
        ):
            with self.subTest(offset=offset, value=value):
                candidate = Fixture()
                candidate.boot(offset, value, width)
                with self.assertRaises(ValueError):
                    candidate.validate()

    def test_backup_and_fsinfo_rejections(self):
        candidate = Fixture()
        candidate.boot(100, 1, width=1, both=False)
        with self.assertRaisesRegex(ValueError, "Backup boot"):
            candidate.validate()
        for offset, value in ((0, 0), (484, 0), (508, 0), (4, 1), (496, 1), (488, 1), (492, 1), (492, 0xFFFFFFFE)):
            with self.subTest(offset=offset, value=value):
                candidate = Fixture()
                candidate.info(offset, value)
                with self.assertRaises(ValueError):
                    candidate.validate()
        candidate = Fixture()
        candidate.info(488, 0xFFFFFFFF)
        candidate.info(492, 0xFFFFFFFF)
        candidate.validate()

    def test_fat_rejections(self):
        for cluster, value, both in (
            (0, 0, True),
            (0, 0x0FFFFFF0, True),
            (0, 0xFFFFFFF8, True),
            (1, 0, True),
            (1, 0x0FFFFFFF, True),
            (1, 0xF7FFFFFF, True),
            (5, 7, False),
            (5, 0xFFFFFFFF, True),
            (5, 0x10000006, True),
            (5, 1, True),
            (5, 0x0FFFFFF7, True),
            (5, 200000, True),
            (5, 5, True),
            (6, 5, True),
            (5, 0, True),
            (5, 0x0FFFFFFF, True),
            (6, 3, True),
            (7, 0x0FFFFFFF, True),
            (129024, 0x0FFFFFFF, True),
        ):
            with self.subTest(cluster=cluster, value=value, both=both):
                candidate = Fixture()
                candidate.fat(cluster, value, both)
                candidate.info(488, 0xFFFFFFFF)
                with self.assertRaises(ValueError):
                    candidate.validate()

    def test_directory_rejections(self):
        for cluster, offset, value in (
            (2, 32, 0xE5),
            (2, 32 + 11, 0x0F),
            (2, 32 + 12, 8),
            (2, 32 + 20, 0xFF),
            (2, 64 + 1, 1),
            (2, 32, 0),
            (3, 26, 4),
            (3, 32 + 26, 2),
            (3, 64 + 11, 0x20),
            (4, 64 + 11, 0x21),
            (4, 64 + 28, 0),
            (2, 28, 1),
            (2, 32 + 28, 1),
            (4, 64 + 26, 2),
        ):
            with self.subTest(cluster=cluster, offset=offset):
                candidate = Fixture()
                candidate.blocks[candidate.cluster_offset(cluster)][offset] = value
                with self.assertRaises(ValueError):
                    candidate.validate()
        for extra in (entry(b"EXTRA   TXT", 0x20), entry(b"EFI        ", 0x10, 3)):
            candidate = Fixture()
            candidate.blocks[candidate.cluster_offset(2)][64:96] = extra
            with self.assertRaises(ValueError):
                candidate.validate()

    def test_loader_identity_and_bounds(self):
        for digest, size in (("0" * 64, len(LOADER)), (LOADER_SHA256, len(LOADER) + 1), ("bad", len(LOADER))):
            with self.assertRaises(ValueError):
                Fixture().validate(digest, size)
        candidate = Fixture()
        candidate.blocks[candidate.cluster_offset(6)][1] ^= 1
        with self.assertRaisesRegex(ValueError, "Loader SHA256"):
            candidate.validate()
        with self.assertRaisesRegex(ValueError, "64-MiB"):
            ESP.Fat32(candidate.read, ESP.IMAGE_BYTES - 1)
        with self.assertRaisesRegex(ValueError, "Short image read"):
            ESP.Fat32(lambda offset, length: b"", ESP.IMAGE_BYTES)
        reader = ESP.Fat32(Fixture().read, ESP.IMAGE_BYTES)
        with self.assertRaisesRegex(ValueError, "bounds"):
            reader.read(ESP.IMAGE_BYTES, 1)

    def test_builder_rejects_unadmitted_input_before_mutation(self):
        with (
            patch.object(ESP, "regular", side_effect=ValueError("unadmitted")),
            patch.object(ESP, "verify_tools") as tools,
            patch.object(ESP.Path, "mkdir") as mkdir,
        ):
            with self.assertRaisesRegex(ValueError, "unadmitted"):
                ESP.build(Path("loader"), LOADER_SHA256, Path("tools"), Path("output"))
            tools.assert_not_called()
            mkdir.assert_not_called()

    def test_regular_input_rejects_symlink_and_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "loader.efi"
            source.write_bytes(LOADER)
            self.assertEqual(ESP.regular(source), source)
            alias = directory / "alias.efi"
            alias.symlink_to(source)
            for invalid in (alias, directory):
                with self.assertRaises(ValueError):
                    ESP.regular(invalid)
            with patch.object(ESP, "verify_tools") as tools:
                with self.assertRaisesRegex(ValueError, "loader SHA256"):
                    ESP.build(source, "0" * 64, directory, directory / "new")
                tools.assert_not_called()
            self.assertFalse((directory / "new").exists())

    def test_builder_output_and_reservation_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "loader.efi"
            source.write_bytes(LOADER)
            existing = directory / "existing"
            existing.mkdir()
            (existing / "preserved").write_bytes(b"unchanged")
            with (
                patch.object(ESP, "verify_tools", return_value=directory),
                patch.object(ESP.subprocess, "run") as command,
            ):
                for output, reason in ((existing, "already exists"), (ROOT / "forbidden-esp", "outside author source")):
                    with self.assertRaisesRegex(ValueError, reason):
                        ESP.build(source, LOADER_SHA256, directory, output)
                free = ESP.FREE_FLOOR_BYTES + ESP.RESERVATION_BYTES - 1
                with patch.object(ESP.shutil, "disk_usage", return_value=SimpleNamespace(free=free)):
                    with self.assertRaisesRegex(ValueError, "disk reservation"):
                        ESP.build(source, LOADER_SHA256, directory, directory / "new")
                command.assert_not_called()
            self.assertFalse((directory / "new").exists())
            self.assertEqual((existing / "preserved").read_bytes(), b"unchanged")


if __name__ == "__main__":
    unittest.main()

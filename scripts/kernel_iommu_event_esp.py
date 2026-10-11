#!/usr/bin/env python3
"""Build/reproduce a pinned mtools ESP; inspect FAT read-only, without mounting.

The sole file is EFI/BOOT/BOOTX64.EFI. This is a 64-MiB FAT32 superfloppy,
not a partitioned disk. Admission establishes format and input identity only;
it does not launch a guest, establish independent review, or qualify hardware.
"""

from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SECTOR_BYTES = 512
IMAGE_BYTES = 64 * 1024 * 1024
TOTAL_SECTORS = IMAGE_BYTES // SECTOR_BYTES
RESERVATION_BYTES = 256 * 1024 * 1024
FREE_FLOOR_BYTES = 1024 * 1024 * 1024
MTOOLS_SHA256 = "0fcd90361bb5077f1289342f6e7713f98269847dbda25d6f1657018f42c53e85"
MTOOLS_BYTES = 214336
MTOOLS_COMMANDS = ("mformat", "mmd", "mcopy", "minfo", "mdir")
DEVELOPER_MTOOLS_VERSION = "4.0.48"
LABEL = b"AURORA_ESP".ljust(11)
EOC = 0x0FFFFFF8


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def check_hash(value):
    need(isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value), "Expected lowercase SHA256")


def regular(path):
    path = Path(path).absolute()
    need(path.resolve(strict=True) == path, "Symlink input path: " + str(path))
    need(stat.S_ISREG(path.lstat().st_mode), "Expected regular file: " + str(path))
    return path


def sha256(path):
    with regular(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Fat32:
    """Bounded reader. read_at(offset, length) must return exactly length bytes."""

    def __init__(self, read_at, size):
        need(size == IMAGE_BYTES, "Expected exact 64-MiB image")
        self.read_at = read_at
        self.size = size
        boot = self.read(0, SECTOR_BYTES)
        need(boot[510:] == b"\x55\xaa", "Missing boot signature")
        need(boot[0] == 0xE9 or (boot[0] == 0xEB and boot[2] == 0x90), "Invalid boot jump")
        need(u16(boot, 11) == SECTOR_BYTES and boot[13] == 1, "Expected 512-byte sectors and clusters")
        need(u16(boot, 14) == 32 and boot[16] == 2, "Expected reserved region and two FATs")
        need(u16(boot, 17) == 0 and u16(boot, 19) == 0 and u16(boot, 22) == 0, "Non-FAT32 BPB fields")
        need(boot[21] == 0xF8, "Unexpected media descriptor")
        need(u16(boot, 24) == 32 and u16(boot, 26) == 64, "Changed fixed geometry")
        need(u32(boot, 28) == 0 and u32(boot, 32) == TOTAL_SECTORS, "Partition offset or size mismatch")
        need(u16(boot, 40) == 0 and u16(boot, 42) == 0, "FAT mirroring/version mismatch")
        need(u32(boot, 44) == 2, "Unexpected root cluster")
        need(u16(boot, 48) == 1 and u16(boot, 50) == 6, "FSInfo/backup location mismatch")
        need(
            boot[52:64] == bytes(12) and boot[64] == 0x80 and boot[65] == 0 and boot[66] == 0x29, "Invalid extended BPB"
        )
        need(u32(boot, 67) == 0x41555241 and boot[71:82] == LABEL, "Changed serial/volume label")
        need(boot[82:90] == b"FAT32   ", "Changed filesystem label")
        need(self.read(6 * SECTOR_BYTES, SECTOR_BYTES) == boot, "Backup boot differs")
        self.fat_sectors = u32(boot, 36)
        self.data_sector = 32 + 2 * self.fat_sectors
        need(self.fat_sectors > 0 and self.data_sector < TOTAL_SECTORS, "FAT/data bounds exceed image")
        self.cluster_count = TOTAL_SECTORS - self.data_sector
        need(65525 <= self.cluster_count < 0x0FFFFFF5, "Cluster count does not classify as FAT32")
        fat_bytes = self.fat_sectors * SECTOR_BYTES
        need((self.cluster_count + 2) * 4 <= fat_bytes, "FAT cannot address data region")
        fat = self.read(32 * SECTOR_BYTES, fat_bytes)
        need(self.read((32 + self.fat_sectors) * SECTOR_BYTES, fat_bytes) == fat, "FAT copies differ")
        self.fat = [item[0] for item in struct.iter_unpack("<I", fat)]
        # Pinned mtools emits all 32 bits set in reserved entry 1. Allocation
        # entries retain the strict 28-bit check; no input bits are masked.
        need(self.fat[:2] == [0x0FFFFFF8, 0xFFFFFFFF], "Invalid reserved FAT entries or dirty volume")
        need(all(value <= 0x0FFFFFFF for value in self.fat[2:]), "Reserved high FAT bits are nonzero")
        need(not any(self.fat[self.cluster_count + 2 :]), "Allocation beyond data region")
        self.allocated = set()
        for cluster in range(2, self.cluster_count + 2):
            value = self.fat[cluster]
            need(value == 0 or 2 <= value < self.cluster_count + 2 or value >= EOC, "Invalid FAT allocation")
            if value:
                self.allocated.add(cluster)
        info = self.read(SECTOR_BYTES, SECTOR_BYTES)
        need(u32(info, 0) == 0x41615252 and u32(info, 484) == 0x61417272, "Invalid FSInfo signatures")
        need(u32(info, 508) == 0xAA550000, "Invalid FSInfo trailer")
        need(not any(info[4:484]) and not any(info[496:508]), "Invalid FSInfo reserved bytes")
        free = self.cluster_count - len(self.allocated)
        need(u32(info, 488) in (free, 0xFFFFFFFF), "FSInfo free count disagrees with FAT")
        hint = u32(info, 492)
        need(hint == 0xFFFFFFFF or 2 <= hint < self.cluster_count + 2, "FSInfo next-cluster hint out of bounds")
        self.claimed = set()

    def read(self, offset, length):
        need(0 <= offset <= self.size and 0 <= length <= self.size - offset, "Read exceeds image bounds")
        result = self.read_at(offset, length)
        need(len(result) == length, "Short image read")
        return result

    def chain(self, first):
        chain = []
        while True:
            need(2 <= first < self.cluster_count + 2, "Chain cluster outside data region")
            need(first not in self.claimed, "Loop or cross-linked allocation")
            need(len(chain) < self.cluster_count, "Unbounded chain")
            self.claimed.add(first)
            chain.append(first)
            next_cluster = self.fat[first]
            if next_cluster >= EOC:
                return chain
            need(next_cluster != 0, "Chain references free cluster")
            first = next_cluster

    def cluster(self, number):
        return self.read((self.data_sector + number - 2) * SECTOR_BYTES, SECTOR_BYTES)

    def directory(self, first, expected, parent=None):
        chain = self.chain(first)
        need(len(chain) == 1, "Profile directory exceeds one cluster")
        data = self.cluster(first)
        entries = {}
        ended = False
        for offset in range(0, len(data), 32):
            entry = data[offset : offset + 32]
            if entry[0] == 0:
                need(not any(data[offset:]), "Data after directory terminator")
                ended = True
                break
            name = entry[:11]
            need(name not in entries, "Duplicate directory name")
            need(name in expected and entry[11] == expected[name], "Unexpected directory entry or attributes")
            need(entry[12] == 0 and u16(entry, 20) < 0x1000, "Case alias or reserved cluster bits")
            start = (u16(entry, 20) << 16) | u16(entry, 26)
            size = u32(entry, 28)
            entries[name] = (start, size)
            if entry[11] == 0x08:
                need(start == 0 and size == 0, "Allocated volume label")
            elif entry[11] == 0x10:
                need(size == 0, "Nonzero directory size")
        need(ended and set(entries) == set(expected), "Missing entry or directory terminator")
        if parent is not None:
            need(entries[b".          "] == (first, 0), "Invalid dot directory")
            need(entries[b"..         "] == (parent, 0), "Invalid parent directory")
        return entries

    def validate(self, loader_sha256, loader_bytes=None):
        check_hash(loader_sha256)
        root = self.directory(2, {LABEL: 0x08, b"EFI        ": 0x10})
        efi_cluster = root[b"EFI        "][0]
        dots = {b".          ": 0x10, b"..         ": 0x10}
        efi = self.directory(efi_cluster, {**dots, b"BOOT       ": 0x10}, parent=0)
        boot = self.directory(efi[b"BOOT       "][0], {**dots, b"BOOTX64 EFI": 0x20}, parent=efi_cluster)
        first, size = boot[b"BOOTX64 EFI"]
        need(0 < size <= self.cluster_count * SECTOR_BYTES, "Invalid loader size")
        need(loader_bytes is None or size == loader_bytes, "Loader size mismatch")
        chain = self.chain(first)
        need(len(chain) == (size + SECTOR_BYTES - 1) // SECTOR_BYTES, "Loader size/chain mismatch")
        digest = hashlib.sha256()
        remaining = size
        for cluster in chain:
            data = self.cluster(cluster)[:remaining]
            digest.update(data)
            remaining -= len(data)
        need(digest.hexdigest() == loader_sha256, "Loader SHA256 mismatch")
        need(self.claimed == self.allocated, "Unreferenced allocation outside exact manifest")
        return dict(
            schema="aurora-iommu-event-fat32-v1",
            image_bytes=self.size,
            sector_bytes=SECTOR_BYTES,
            cluster_bytes=SECTOR_BYTES,
            cluster_count=self.cluster_count,
            fat_sectors=self.fat_sectors,
            data_sector=self.data_sector,
            allocated_clusters=len(self.allocated),
            files=[dict(path="EFI/BOOT/BOOTX64.EFI", bytes=size, sha256=loader_sha256)],
        )


def validate_image(path, loader_sha256, loader_bytes=None):
    path = regular(path)
    with path.open("rb") as stream:

        def read_at(offset, length):
            stream.seek(offset)
            return stream.read(length)

        before = os.fstat(stream.fileno())
        result = Fat32(read_at, before.st_size).validate(loader_sha256, loader_bytes)
        stream.seek(0)
        result["image_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        after = os.fstat(stream.fileno())
        need(
            (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "Image changed while validating",
        )
    return result


def verify_tools(root):
    root = Path(root).absolute()
    need(root.resolve(strict=True) == root and root.is_dir(), "Invalid mtools root")
    executable = regular(root / "mtools")
    need(
        executable.stat().st_size == MTOOLS_BYTES and sha256(executable) == MTOOLS_SHA256,
        "Unreviewed mtools executable",
    )
    for name in MTOOLS_COMMANDS:
        path = root / name
        need(
            path.is_symlink() and os.readlink(path) == "mtools" and path.resolve() == executable,
            "Unexpected mtools command: " + name,
        )
    for path in (Path("/etc/mtools.conf"), Path("/etc/default/mtools.conf")):
        need(not os.path.lexists(path), "Unreviewed system mtools configuration: " + str(path))
    return root


def same_bytes(first, second):
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            block = left.read(1024 * 1024)
            if block != right.read(1024 * 1024):
                return False
            if not block:
                return True


def developer_tool_identity(root, home=None, *, hash_tools=True):
    """Bind installed tools, without inheriting the historical executable pin.

    GNU mtools reads system configuration, then ~/.mtoolsrc, then MTOOLSRC;
    MTOOLSRC=/dev/null alone is not isolation. This bounded contract supports
    GNU 4.0.48 with the standard system configuration locations only.
    """
    for path in (Path("/etc/mtools.conf"), Path("/etc/default/mtools.conf")):
        need(not os.path.lexists(path), "Developer system mtools configuration exists: " + str(path))
    if home is not None:
        need(home.resolve(strict=True) == home and home.is_dir(), "Invalid private mtools home")
        need(not os.path.lexists(home / ".mtoolsrc"), "Developer private mtools configuration exists")
    root = Path(root).absolute()
    need(root.is_dir(), "Invalid developer mtools root")
    identities = {}
    for name in MTOOLS_COMMANDS:
        selected = root / name
        executable = regular(selected.resolve(strict=True))
        need(os.access(executable, os.X_OK), "Developer mtools is not executable: " + name)
        identities[name] = dict(
            command_path=str(selected),
            resolved_path=str(executable),
        )
        if hash_tools:
            identities[name].update(bytes=executable.stat().st_size, sha256=sha256(executable))
    return identities


def build(loader, loader_sha256, mtools_root, output_dir, *, developer=False, run_command=None, packaged=False):
    need(not packaged or developer, "Packaged tools require developer ESP mode")
    need(run_command is None or developer, "Command callback requires developer ESP mode")
    need(not developer or callable(run_command), "Developer ESP mode requires a bounded command callback")
    check_hash(loader_sha256)
    loader = regular(loader)
    need(0 < loader.stat().st_size < IMAGE_BYTES // 2, "Invalid admitted loader size")
    need(sha256(loader) == loader_sha256, "Admitted loader SHA256 mismatch")
    if developer:
        tools = Path(mtools_root).absolute()
        tool_identity = developer_tool_identity(tools, hash_tools=not packaged)
    else:
        tools = verify_tools(mtools_root)
    output = Path(output_dir).absolute()
    need(output.parent.resolve(strict=True) == output.parent and output.parent.is_dir(), "Invalid output parent")
    need(output != ROOT and ROOT not in output.parents, "ESP output must be outside author source")
    need(not os.path.lexists(output), "Output directory already exists")
    reservation = max(RESERVATION_BYTES, 3 * IMAGE_BYTES + 3 * loader.stat().st_size + 16 * 1024 * 1024)
    need(shutil.disk_usage(output.parent).free >= FREE_FLOOR_BYTES + reservation, "ESP disk reservation failed")
    output.mkdir(mode=0o700)
    # Keep a pinned private input: mcopy never depends on a mutable source path.
    admitted = output / "admitted-loader.efi"
    with loader.open("rb") as source, admitted.open("xb") as target:
        shutil.copyfileobj(source, target)
    need(sha256(admitted) == loader_sha256, "Loader changed during input snapshot")
    admitted.chmod(0o400)
    commands = []
    results = []
    versions = {}
    for role in ("master", "rebuild"):
        home = output / (role + "-home")
        home.mkdir(mode=0o700)
        image = output / ("esp-" + role + ".raw")
        readback = output / ("loader-" + role + "-readback.efi")
        environment = dict(
            PATH="/usr/bin:/bin",
            LC_ALL="C",
            TZ="UTC",
            SOURCE_DATE_EPOCH="946684800",
            HOME=str(home),
            MTOOLSRC="/dev/null",
            MTOOLS_NO_VFAT="1",
        )

        def verify_developer_identity():
            need(
                developer_tool_identity(tools, home, hash_tools=not packaged) == tool_identity,
                "Developer mtools identity changed",
            )
            need(shutil.disk_usage(output).free >= FREE_FLOOR_BYTES, "ESP free-space floor failed")

        def run(name, *args):
            if developer:
                verify_developer_identity()
            command = [str(tools / name), *map(str, args)]
            commands.append(dict(command=command, environment=environment))
            (output / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
            log = output / (role + "-" + str(len(commands)) + "-" + name + ".log")
            if developer:
                run_command(command, log, environment)
            else:
                with log.open("xb") as stream:
                    subprocess.run(
                        command,
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        timeout=60,
                        check=True,
                        umask=0o077,
                    )
            if developer:
                verify_developer_identity()
            return log

        if developer and not packaged and role == "master":
            for name in MTOOLS_COMMANDS:
                log = run(name, "--version")
                with log.open("rb") as stream:
                    version = stream.read(4097)
                need(len(version) <= 4096, "Oversized developer mtools version output: " + name)
                expected = (name + " (GNU mtools) " + DEVELOPER_MTOOLS_VERSION).encode("ascii")
                need(
                    version.splitlines() and version.splitlines()[0] == expected,
                    "Unsupported developer mtools version: " + name + "; require GNU " + DEVELOPER_MTOOLS_VERSION,
                )
                versions[name] = version.decode("ascii")

        with image.open("xb") as stream:
            stream.truncate(IMAGE_BYTES)
        image.chmod(0o600)
        run(
            "mformat",
            "-i",
            image,
            "-F",
            "-T",
            "131072",
            "-h",
            "64",
            "-s",
            "32",
            "-c",
            "1",
            "-R",
            "32",
            "-d",
            "2",
            "-m",
            "0xf8",
            "-N",
            "0x41555241",
            "-v",
            "AURORA_ESP",
            "::",
        )
        run("mmd", "-i", image, "::/EFI")
        run("mmd", "-i", image, "::/EFI/BOOT")
        run("mcopy", "-i", image, admitted, "::/EFI/BOOT/BOOTX64.EFI")
        run("minfo", "-i", image, "::")
        run("mdir", "-i", image, "-/", "::")
        run("mcopy", "-i", image, "::/EFI/BOOT/BOOTX64.EFI", readback)
        need(same_bytes(admitted, readback), "mtools loader readback differs")
        results.append(validate_image(image, loader_sha256, admitted.stat().st_size))
        image.chmod(0o444)
    need(same_bytes(output / "esp-master.raw", output / "esp-rebuild.raw"), "Independent ESP rebuild differs")
    need(results[0] == results[1], "Independent FAT admission differs")
    if developer:
        verify_developer_identity()
    else:
        verify_tools(tools)
    need(sha256(loader) == loader_sha256 and sha256(admitted) == loader_sha256, "Admitted loader changed")
    result = dict(
        schema="aurora-iommu-event-esp-build-v1",
        status="requires-independent-review",
        loader_path=str(loader),
        mtools_root=str(tools),
        mtools_sha256=MTOOLS_SHA256,
        source_date_epoch=946684800,
        timezone="UTC",
        independent_byte_identity=True,
        reservation_bytes=reservation,
        master=str(output / "esp-master.raw"),
        rebuild=str(output / "esp-rebuild.raw"),
        fat32=results[0],
        commands=commands,
        builder_sha256=None if packaged else sha256(Path(__file__)),
    )
    if developer:
        result.update(
            schema="aurora-iommu-event-developer-esp-build-v1",
            status="developer-byte-identity-checked",
            independent_review=False,
            mtools={}
            if packaged
            else {name: dict(**tool_identity[name], version_output=versions[name]) for name in MTOOLS_COMMANDS},
        )
        del result["mtools_sha256"]
        if packaged:
            del result["mtools"]
            del result["builder_sha256"]
    with (output / "esp-admission.json").open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    builder = sub.add_parser("build")
    builder.add_argument("--loader", type=Path, required=True)
    builder.add_argument("--mtools-root", type=Path, required=True)
    builder.add_argument("--output-dir", type=Path, required=True)
    validator = sub.add_parser("validate")
    validator.add_argument("--image", type=Path, required=True)
    validator.add_argument("--loader-bytes", type=int)
    for item in (builder, validator):
        item.add_argument("--loader-sha256", required=True)
    args = parser.parse_args()
    if args.action == "build":
        result = build(args.loader, args.loader_sha256, args.mtools_root, args.output_dir)
    else:
        result = validate_image(args.image, args.loader_sha256, args.loader_bytes)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit("FAIL: Event ESP: " + str(error)) from error

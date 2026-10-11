#!/usr/bin/env python3
"""Package the fixed clean-NVMe firmware dependency; never boot Aurora guests."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request


# Debian's repack includes the required fixed submodules. Its retained main-tree
# sources match this upstream commit; it is not a verbatim recursive Git checkout.
COMMIT = "fbe0805b2091393406952e84724188f8c1941837"
SOURCE_URL = "https://snapshot.debian.org/archive/debian/20261009T120000Z/pool/main/e/edk2/edk2_2025.02.orig.tar.xz"
SOURCE_SHA256 = "b63b6053d6d89c74d9291f9e96fde1584be99e6fb9c169ba9511505129d6b049"
PATCH_SHA256 = "2a6e8f018d16fc1b4c0304bf7d1f3b56ca4962ca8ec204a19ff94b0e4790ad1f"
PREFIX = Path("/opt/aurora-fixtures")
WORK = Path("/tmp/aurora-clean-ovmf-build")
SOURCE_NAME = "edk2-2025.02"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path, expected):
    if digest(path) != expected:
        raise SystemExit("Dependency SHA256 mismatch: " + str(path))


def install(source, relative):
    target = PREFIX / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)


def main():
    os.umask(0o022)
    # Refuse stale scratch, and use a fixed path so compiler paths are stable.
    WORK.mkdir()
    archive = WORK / "edk2_2025.02.orig.tar.xz"
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, archive.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    verify(archive, SOURCE_SHA256)
    install(archive, "share/source/edk2_2025.02.orig.tar.xz")
    with tarfile.open(archive) as source_archive:
        # This unrelated Unix emulator link escapes the tree. Keep the safe
        # extraction filter for every OVMF input instead of weakening it globally.
        members = (
            member for member in source_archive if member.name != SOURCE_NAME + "/EmulatorPkg/Unix/Host/X11IncludeHack"
        )
        source_archive.extractall(WORK, members=members, filter="data")
    source = WORK / SOURCE_NAME
    # Both upstream Brotli gitlinks are f4153a09f87cbb9c826d8fc12c74642bb2d879ea.
    # Debian omits the host duplicate; all its required C sources remain here.
    host_brotli = source / "BaseTools/Source/C/BrotliCompress/brotli"
    if host_brotli.exists():
        host_brotli.rmdir()  # Only an empty gitlink placeholder is acceptable.
    host_brotli.symlink_to(
        "../../../../MdeModulePkg/Library/BrotliCustomDecompressLib/brotli",
        target_is_directory=True,
    )
    patch = Path("/tmp/clean-nvme-policy.patch")
    verify(patch, PATCH_SHA256)
    install(patch, "firmware/policy-three-file.patch")
    # GCC 16 diagnoses upstream counters that were never read.
    # Remove only that dead state; retain warning-as-error enforcement.
    # Backports: https://github.com/tianocore/edk2/pull/12079
    for name, expected in {
        "clean-nvme-policy.patch": PATCH_SHA256,
        "edk2-host-gcc16.patch": "2cbe5376c7350c33e143e63749dd4f0cea05230c5ace75a94e40559b7c4b42a5",
        "edk2-display-gcc16.patch": "afafd28c09c2c1e39ed22e8cc4092eb76c902823b9ad5f2876a71efcf4c84b8c",
    }.items():
        patch = Path("/tmp") / name
        verify(patch, expected)
        install(patch, "share/source/" + name)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)], cwd=source, check=True)
    env = os.environ | {
        "SOURCE_DATE_EPOCH": "1740099036",  # Upstream commit timestamp.
        "PYTHONHASHSEED": "0",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PYTHON_COMMAND": "/usr/bin/python3",
        "GCC_BIN": "/usr/bin/",
    }
    subprocess.run(
        [
            "bash",
            "-ec",
            ". ./edksetup.sh; "
            # The older host source expects C11; retain its complete CFLAGS.
            "make -C BaseTools/Source/C -j2 CC='/usr/bin/gcc-16 -std=gnu11'; "
            "build -a X64 -b DEBUG -t GCC -p OvmfPkg/OvmfPkgX64.dsc -D FD_SIZE_4MB -n 2",
        ],
        cwd=source,
        env=env,
        check=True,
        timeout=1200,
    )
    volume = source / "Build/OvmfX64/DEBUG_GCC/FV"
    hashes = []
    for name, size in (("OVMF_CODE.fd", 3653632), ("OVMF_VARS.fd", 540672)):
        firmware = volume / name
        if firmware.stat().st_size != size:
            raise SystemExit("Unexpected clean firmware layout: " + name)
        install(firmware, "firmware/" + name)
        hashes.append(digest(firmware) + "  " + name + "\n")
    (PREFIX / "firmware/VERSION").write_text("edk2-" + COMMIT + "-clean-nvme-v1\n")
    (PREFIX / "firmware/SHA256SUMS").write_text("".join(hashes))
    print("Clean firmware package (guest qualification is separate):\n" + "".join(hashes), end="")
    for name in (
        "License.txt",
        "License-History.txt",
        "OvmfPkg/License.txt",
        "CryptoPkg/Library/OpensslLib/openssl/LICENSE.txt",
        "CryptoPkg/Library/MbedTlsLib/mbedtls/LICENSE",
        "MdeModulePkg/Library/BrotliCustomDecompressLib/brotli/LICENSE",
        "MdePkg/Library/MipiSysTLib/mipisyst/LICENSE",
        "SecurityPkg/DeviceSecurity/SpdmLib/libspdm/LICENSE.md",
    ):
        install(source / name, "share/doc/licenses/" + name)
    # The retained complete orig archive also includes per-file copyright notices.
    install(Path(__file__), "share/source/build-clean-ovmf.py")
    shutil.rmtree(WORK)


if __name__ == "__main__":
    main()

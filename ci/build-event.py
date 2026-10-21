#!/usr/bin/env python3
"""Build the fixed optional Event emulator dependency; never run Aurora guests."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


SOURCE_URL = "https://snapshot.debian.org/archive/debian/20261009T120000Z/pool/main/q/qemu/qemu_10.0.13+ds.orig.tar.xz"
SOURCE_SHA256 = "6a0888e806c2ffc0c5f0733e974f9aea55491950d3c47c98669c8b236dde59ae"
PATCHES = {
    "0001-event-record-transport.patch": "28ce96258f888457a937e204327326512a7b269291d12366bdb0567663b217e0",
    "0002-mode1-requester-permissions-v2.patch": "54cbc3e2555f15ad925c8be710284046135997956fee4edd50f2f2d2942d9641",
    "0003-command-stop-v1.patch": "0f3e51a4dea545092114a049a4781a01fe909f759b39cb6580cf9d41ef63c360",
}
# Packaging-only Debian correction, independent of the three reviewed model patches.
PACKAGING_PATCH = "qemu-skip-unpack-edk2-blobs.patch"
PACKAGING_SHA256 = "02df62768b12f1b60ad769fce6080269c859054b4dcd64509122ba09439fbda2"
PACKAGING_TARGET = "pc-bios/meson.build"
PACKAGING_PREIMAGE = "45378c725d02525d02bb9cc2ca81ba235e6654c91cd66f02e015188106209de2"
PACKAGING_POSTIMAGE = "122c64d6eb9d27c32ced8257613af3460e0ec3b946015f78b6e3b0580a261966"
# Imported source-chain identities, not signatures verified by this builder.
DEBIAN_SNAPSHOT = "https://snapshot.debian.org/archive/debian/20261009T120000Z/"
PACKAGING_ORIGIN = {
    "source_package": "qemu",
    "source_version": "1:10.0.13+ds-0+deb13u1",
    "upstream_version": "10.0.13",
    "authentication": "Imported pinned Debian source-chain provenance; no fresh signature check in this build",
    "inrelease": {
        "url": DEBIAN_SNAPSHOT + "dists/trixie/InRelease",
        "bytes": 140421,
        "sha256": "0584fba32e13e0ab8285fb16c27adea1ec03a73669c18702821094fd6ca86675",
    },
    "sources_index": {
        "url": DEBIAN_SNAPSHOT + "dists/trixie/main/source/Sources.xz",
        "bytes": 10540436,
        "sha256": "6002f81f463a2d976d84b34170367cc16da2d60bd0ba9ab9d868d6e1c1a935d9",
    },
    "orig_archive": {"url": SOURCE_URL, "bytes": 40010016, "sha256": SOURCE_SHA256},
    "packaging_archive": {
        "url": DEBIAN_SNAPSHOT + "pool/main/q/qemu/qemu_10.0.13+ds-0+deb13u1.debian.tar.xz",
        "bytes": 156096,
        "sha256": "da73c092f5684c551b0334d675eb16a3dec91e1edea94759cfb1102fa4a0364e",
    },
    "patch_member": "debian/patches/skip-unpack-edk2-blobs.patch",
    "copyright_member": "debian/copyright",
}
MODELS = {
    "hw/i386/amd_iommu.c": "a506dccf0c112cc791208724651b3aaca300f8b713362dfd07af2308e6f5a2d9",
    "hw/i386/amd_iommu.h": "94d50d0dd0548c533252b4fdff7ec3cf800aed8655ce38db24de837adf1785e4",
}
FIRMWARE = {
    "OVMF_CODE_4M.fd": "624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0",
    "OVMF_VARS_4M.fd": "5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e",
}
PREFIX = Path("/opt/aurora-event")


def verify(path, expected):
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise SystemExit("Dependency SHA256 mismatch: " + str(path))


def install(source, relative):
    target = PREFIX / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


with tempfile.TemporaryDirectory(prefix="aurora-event-build-") as temporary:
    work = Path(temporary)
    archive = work / "qemu.tar.xz"
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, archive.open("wb") as stream:
        shutil.copyfileobj(response, stream)
    verify(archive, SOURCE_SHA256)
    install(archive, "share/source/qemu_10.0.13+ds.orig.tar.xz")
    with tarfile.open(archive) as source_archive:
        source_archive.extractall(work, filter="data")
    source = work / "qemu-10.0.13"
    for name, digest in PATCHES.items():
        patch = Path("/tmp/event-patches") / name
        verify(patch, digest)
        install(patch, "share/source/patches/" + name)
        subprocess.run(["patch", "--fuzz=0", "-p1", "-i", str(patch)], cwd=source, check=True)
    packaging_patch = Path(__file__).with_name(PACKAGING_PATCH)
    verify(packaging_patch, PACKAGING_SHA256)
    verify(source / PACKAGING_TARGET, PACKAGING_PREIMAGE)
    subprocess.run(["patch", "--fuzz=0", "-p1", "-i", str(packaging_patch)], cwd=source, check=True)
    verify(source / PACKAGING_TARGET, PACKAGING_POSTIMAGE)
    install(packaging_patch, "share/source/packaging/" + PACKAGING_PATCH)
    (PREFIX / "share/source/packaging/provenance.json").write_text(
        json.dumps(
            {
                "schema": "aurora-event-packaging-v1",
                "origin": PACKAGING_ORIGIN,
                "patch_sha256": PACKAGING_SHA256,
                "target": PACKAGING_TARGET,
                "preimage_sha256": PACKAGING_PREIMAGE,
                "postimage_sha256": PACKAGING_POSTIMAGE,
                "application_order": list(PATCHES) + [PACKAGING_PATCH],
                "builder": "share/source/build-event.py",
                "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Build-system-only correction for absent Debian +ds EDK2 blobs; no model change",
            },
            indent=2,
        )
        + "\n"
    )
    for name, digest in MODELS.items():
        verify(source / name, digest)
        install(source / name, "model/" + name)
    config = "configs/devices/x86_64-softmmu/aurora-dma.mak"
    (source / config).write_text("CONFIG_Q35=y\nCONFIG_AMD_IOMMU=y\nCONFIG_EDU=y\nCONFIG_ISA_DEBUG=y\n")
    install(source / config, "model/" + config)
    build = work / "build"
    build.mkdir()
    subprocess.run(
        [
            str(source / "configure"),
            "--target-list=x86_64-softmmu",
            "--python=/usr/bin/python3",
            "--ninja=/usr/bin/ninja",
            "--without-default-features",
            "--without-default-devices",
            "--with-devices-x86_64=aurora-dma",
            "--enable-tcg",
            "--disable-kvm",
            "--disable-xen",
            "--disable-user",
            "--disable-docs",
            "--disable-tools",
            "--disable-guest-agent",
            "--disable-plugins",
            "--disable-install-blobs",
            "--disable-download",
            "--disable-fdt",
            "--disable-debug-info",
            "--prefix=" + str(PREFIX),
        ],
        cwd=build,
        check=True,
    )
    subprocess.run(["ninja", "-j2", "qemu-system-x86_64"], cwd=build, check=True, timeout=1200)
    install(build / "qemu-system-x86_64", "bin/qemu-system-x86_64")
    install(source / "COPYING", "share/doc/COPYING")

install(Path(__file__), "share/source/build-event.py")
(PREFIX / "share/qemu").symlink_to("/usr/share/qemu", target_is_directory=True)
for name, digest in FIRMWARE.items():
    firmware = Path("/usr/share/OVMF") / name
    verify(firmware, digest)
    install(firmware, "firmware/" + name)
(PREFIX / "runtime.json").write_text(
    json.dumps(
        {
            "schema": "aurora-event-runtime-v1",
            "model": "aurora-amdvi-command-stop-v1",
            "qemu_version": "10.0.13",
            "firmware_version": "2025.02-8+deb13u1",
        },
        indent=2,
    )
    + "\n"
)
version = subprocess.check_output([str(PREFIX / "bin/qemu-system-x86_64"), "--version"], text=True)
if version.splitlines()[0] != "QEMU emulator version 10.0.13":
    raise SystemExit("Unexpected packaged Event QEMU version: " + version)
print(version, end="")

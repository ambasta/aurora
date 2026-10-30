#!/usr/bin/env python3
"""Build the fixed Event model, or its separate optional NVMe device extension."""

import argparse
import hashlib
import os
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
# Debian attribution and the source archive verified below; no signature authentication.
PACKAGING_ORIGIN = {
    "source_package": "qemu",
    "source_version": "1:10.0.13+ds-0+deb13u1",
    "upstream_version": "10.0.13",
    "orig_archive": {"url": SOURCE_URL, "sha256": SOURCE_SHA256},
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
parser = argparse.ArgumentParser(description=__doc__)
models = parser.add_mutually_exclusive_group()
models.add_argument(
    "--nvme", action="store_true", help="build a separate NVMe-capable model from the packaged Event sources"
)
models.add_argument(
    "--nvme-graphics", action="store_true", help="build the separate NVMe+standard VGA production model"
)
parser.add_argument("--prefix", type=Path, help="new output prefix for the selected bounded model")
parser.add_argument(
    "--event-prefix",
    type=Path,
    default=Path("/opt/aurora-event"),
    help="verified packaged Event source inputs for either optional NVMe model",
)
parser.add_argument("--data-dir", type=Path, default=Path("/usr/share/qemu"), help="matching QEMU ROM/data directory")
args = parser.parse_args()
optional = args.nvme or args.nvme_graphics
PREFIX = args.prefix or Path(
    "/opt/aurora-nvme-graphics" if args.nvme_graphics else "/opt/aurora-nvme" if args.nvme else "/opt/aurora-event"
)
if optional and PREFIX.resolve() == args.event_prefix.resolve():
    raise SystemExit("NVMe output must not overwrite the reference Event prefix")
if optional and (PREFIX.is_symlink() or (PREFIX.exists() and (not PREFIX.is_dir() or any(PREFIX.iterdir())))):
    raise SystemExit("NVMe output prefix must be absent or an empty directory")


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
    if optional:
        # Offline extension: the same archive/patch/model hashes remain mandatory.
        shutil.copyfile(args.event_prefix / "share/source/qemu_10.0.13+ds.orig.tar.xz", archive)
    else:
        with urllib.request.urlopen(SOURCE_URL, timeout=120) as response, archive.open("wb") as stream:
            shutil.copyfileobj(response, stream)
    verify(archive, SOURCE_SHA256)
    install(archive, "share/source/qemu_10.0.13+ds.orig.tar.xz")
    with tarfile.open(archive) as source_archive:
        source_archive.extractall(work, filter="data")
    source = work / "qemu-10.0.13"
    for name, digest in PATCHES.items():
        patch = (args.event_prefix / "share/source/patches" if optional else Path("/tmp/event-patches")) / name
        verify(patch, digest)
        install(patch, "share/source/patches/" + name)
        subprocess.run(["patch", "--fuzz=0", "-p1", "-i", str(patch)], cwd=source, check=True)
    packaging_patch = Path(__file__).with_name(PACKAGING_PATCH)
    if optional and not packaging_patch.is_file():
        packaging_patch = args.event_prefix / "share/source/packaging" / PACKAGING_PATCH
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
    (source / config).write_text(
        "CONFIG_Q35=y\nCONFIG_AMD_IOMMU=y\nCONFIG_EDU=y\nCONFIG_ISA_DEBUG=y\n"
        + ("CONFIG_NVME_PCI=y\n" if optional else "")
        + ("CONFIG_VGA_PCI=y\n" if args.nvme_graphics else "")
    )
    install(source / config, "model/" + config)
    build = work / "build"
    build.mkdir()
    subprocess.run(
        [
            str(source / "configure"),
            "--target-list=x86_64-softmmu",
            "--python=" + (shutil.which("python3") if optional else "/usr/bin/python3"),
            "--ninja=" + (shutil.which("ninja") if optional else "/usr/bin/ninja"),
            "--without-default-features",
            "--without-default-devices",
            "--with-devices-x86_64=aurora-dma",
            "--enable-tcg",
            *(["--enable-pixman"] if args.nvme_graphics else []),
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
    # Optional all-core builds run under scripts/watchdog.sh; the established
    # Event packaging command is unchanged. No guest qualification is inferred.
    jobs = str(len(os.sched_getaffinity(0))) if optional else "2"
    subprocess.run(["ninja", "-j" + jobs, "qemu-system-x86_64"], cwd=build, check=True, timeout=1200)
    install(build / "qemu-system-x86_64", "bin/qemu-system-x86_64")
    install(source / "COPYING", "share/doc/COPYING")

install(Path(__file__), "share/source/build-event.py")
(PREFIX / "share/qemu").symlink_to(args.data_dir.resolve(), target_is_directory=True)
# NVMe deliberately does not inherit the stock Event firmware. Its guest
# runner selects AURORA_BOOT_FIXTURE_PREFIX's clean no-NvmExpressDxe pair.
for name, digest in ({} if optional else FIRMWARE).items():
    firmware = Path("/usr/share/OVMF") / name
    verify(firmware, digest)
    install(firmware, "firmware/" + name)
(PREFIX / "runtime.json").write_text(
    json.dumps(
        {
            "schema": "aurora-event-runtime-v1",
            "model": (
                "aurora-amdvi-command-stop-nvme-graphics-v1"
                if args.nvme_graphics
                else "aurora-amdvi-command-stop-nvme-v1"
                if args.nvme
                else "aurora-amdvi-command-stop-v1"
            ),
            "qemu_version": "10.0.13",
            "firmware_version": "separate clean-nvme-v1 package required" if optional else "2025.02-8+deb13u1",
        },
        indent=2,
    )
    + "\n"
)
version = subprocess.check_output([str(PREFIX / "bin/qemu-system-x86_64"), "--version"], text=True)
if version.splitlines()[0] != "QEMU emulator version 10.0.13":
    raise SystemExit("Unexpected packaged Event QEMU version: " + version)
print(version, end="")

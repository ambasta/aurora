#!/usr/bin/env python3
"""Exact fixture/patch identities and synthetic mocks; never launches an emulator."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_runtime_fixture_routes(source):
    # Only frozen IOMMU runtime fixtures are forbidden here. XFS native corpus
    # registrations are ordinary required tests, despite sharing the word fixtures.
    forbidden = ("iommu/fixtures/", "frozen-import.py", "transport-import-v1.py", "command-stop-diagnostic.py")
    require(not any(name in source for name in forbidden), "An IOMMU runtime fixture entered default test routing")


def check_integrity():
    manifest = json.loads((ROOT / "tools/qemu-amdvi/artifacts.json").read_text())["sha256"]
    expected_paths = {
        "tools/qemu-amdvi/patches/0001-event-record-transport.patch",
        "tools/qemu-amdvi/patches/0002-mode1-requester-permissions-v2.patch",
        "tools/qemu-amdvi/patches/0003-command-stop-v1.patch",
        "tests/iommu/fixtures/frozen-import.py",
        "tests/iommu/fixtures/transport-import-v1.py",
        "tests/iommu/fixtures/command-stop-diagnostic.py",
    }
    require(set(manifest) == expected_paths, "Expected three exact patches and three frozen diagnostic fixtures")
    for name, expected in manifest.items():
        path = ROOT / name
        require(path.is_relative_to(ROOT), "Artifact escaped repository")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, "Artifact identity changed: " + name)
        if path.suffix == ".py":
            ast.parse(path.read_text(), filename=name)
        if path.suffix == ".patch":
            for line in path.read_text().splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    require(line == line.rstrip(), "Trailing whitespace in added source: " + name)
    frozen = ROOT / "tests/iommu/fixtures/frozen-import.py"
    require(
        hashlib.sha256(frozen.read_bytes()).hexdigest()
        == "a380e4792cd50417b457e638fdfeb6e3f5efd3b8126dcf8915a0c88ef0c27e28",
        "Historical 17-case fixture or expectations changed",
    )
    make = (ROOT / "Makefile").read_text()
    meson = (ROOT / "tests/meson.build").read_text()
    require("files('iommu-diagnostics.py')" in meson, "Meson lost static diagnostics")
    check_runtime_fixture_routes(make + meson)
    check_runtime_fixture_routes("fixtures/xfs-root ../fixtures/xfs-offline/verify_native.py")
    for forbidden in (
        "tests/iommu/fixtures/unknown.py",
        "frozen-import.py",
        "transport-import-v1.py",
        "command-stop-diagnostic.py",
    ):
        try:
            check_runtime_fixture_routes(forbidden)
        except ValueError:
            pass
        else:
            raise ValueError("IOMMU runtime fixture routing rejection failed")
    require(not (frozen.parent / "TARGET-BINARY.json").exists(), "Runtime target must remain outside repository")
    print("PASS 6 exact artifacts and compiler-free routing; frozen 17-case expectations unchanged")


def check_patch_parser():
    spec = importlib.util.spec_from_file_location("iommu_patch_check", ROOT / "tools/qemu-amdvi/verify_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    patch = "--- a/a\n+++ b/a\n@@ -1,2 +1,2 @@\n one\n-two\n+three\n"
    inputs = {"a": b"one\ntwo\n"}
    require(module.apply_patch(inputs, patch) == {"a": b"one\nthree\n"}, "Valid patch was not reconstructed")
    require(inputs == {"a": b"one\ntwo\n"}, "Parser changed input mapping")
    for bad in (
        patch.replace("-two", "-wrong"),
        patch.replace("+1,2", "+2,2"),
        patch.replace("-1,2", "-1,3"),
        patch.replace("+++ b/a", "+++ b/other"),
    ):
        try:
            module.apply_patch(inputs, bad)
        except ValueError:
            continue
        raise ValueError("Malformed patch was accepted")
    print("PASS strict in-memory patch parser controls")


def check_packaging_patch():
    spec = importlib.util.spec_from_file_location("packaging_patch_check", ROOT / "tools/qemu-amdvi/verify_source.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    name = "qemu-skip-unpack-edk2-blobs.patch"
    target = "pc-bios/meson.build"
    digest = "02df62768b12f1b60ad769fce6080269c859054b4dcd64509122ba09439fbda2"
    data = (ROOT / "ci" / name).read_bytes()
    require(hashlib.sha256(data).hexdigest() == digest, "Debian packaging patch identity changed")
    # Keep the actual diff unchanged; only Debian's attribution/metadata precedes ---.
    patch = data.decode()[data.decode().index("--- a/") :]
    require(patch.count("--- a/") == 1, "Packaging patch must have one target")
    require(patch.startswith("--- a/" + target + "\n+++ b/" + target + "\n"), "Wrong packaging target")
    before = b"roms = []\nif unpack_edk2_blobs\n  fds = [\n    'edk2-aarch64-code.fd',\n"
    after = before.replace(b"if unpack_edk2_blobs\n", b"if unpack_edk2_blobs and false\n")
    require(module.apply_patch({target: before}, patch) == {target: after}, "Packaging diff reconstruction failed")
    for inputs, bad in (
        ({target: before.replace(b"roms = []", b"roms = ['changed']")}, patch),
        ({target: before}, patch.replace(target, "pc-bios/wrong.build")),
        ({target: after}, patch),
    ):
        try:
            module.apply_patch(inputs, bad)
        except ValueError:
            continue
        raise ValueError("Packaging patch negative control was accepted")

    # Parse only: importing this top-level builder would download and build QEMU.
    source = (ROOT / "ci/build-event.py").read_text()
    tree = ast.parse(source)
    assignments = {
        node.targets[0].id: node.value
        for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    constants = {
        "PACKAGING_PATCH": name,
        "PACKAGING_SHA256": digest,
        "PACKAGING_TARGET": target,
        "PACKAGING_PREIMAGE": "45378c725d02525d02bb9cc2ca81ba235e6654c91cd66f02e015188106209de2",
        "PACKAGING_POSTIMAGE": "122c64d6eb9d27c32ced8257613af3460e0ec3b946015f78b6e3b0580a261966",
        "SOURCE_URL": "https://snapshot.debian.org/archive/debian/20261009T120000Z/pool/main/q/qemu/qemu_10.0.13+ds.orig.tar.xz",
        "SOURCE_SHA256": "6a0888e806c2ffc0c5f0733e974f9aea55491950d3c47c98669c8b236dde59ae",
    }
    for key, expected in constants.items():
        require(ast.literal_eval(assignments[key]) == expected, "Builder pin changed: " + key)
    manifest = json.loads((ROOT / "tools/qemu-amdvi/artifacts.json").read_text())["sha256"]
    model_patches = ast.literal_eval(assignments["PATCHES"])
    require(
        model_patches == {Path(path).name: sha for path, sha in manifest.items() if path.endswith(".patch")},
        "Packaging patch entered or changed model patch inventory",
    )
    require(
        list(model_patches)
        == [
            "0001-event-record-transport.patch",
            "0002-mode1-requester-permissions-v2.patch",
            "0003-command-stop-v1.patch",
        ],
        "Model patch order changed",
    )
    require(
        ast.literal_eval(assignments["FIRMWARE"])
        == {
            "OVMF_CODE_4M.fd": "624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0",
            "OVMF_VARS_4M.fd": "5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e",
        },
        "Firmware identity changed",
    )
    require(
        ast.literal_eval(assignments["MODELS"])
        == {
            "hw/i386/amd_iommu.c": "a506dccf0c112cc791208724651b3aaca300f8b713362dfd07af2308e6f5a2d9",
            "hw/i386/amd_iommu.h": "94d50d0dd0548c533252b4fdff7ec3cf800aed8655ce38db24de837adf1785e4",
        },
        "Final model hashes changed",
    )
    ordered = (
        "for name, digest in PATCHES.items():",
        'subprocess.run(["patch", "--fuzz=0", "-p1", "-i", str(patch)], cwd=source, check=True)',
        "verify(packaging_patch, PACKAGING_SHA256)",
        "verify(source / PACKAGING_TARGET, PACKAGING_PREIMAGE)",
        'subprocess.run(["patch", "--fuzz=0", "-p1", "-i", str(packaging_patch)], cwd=source, check=True)',
        "verify(source / PACKAGING_TARGET, PACKAGING_POSTIMAGE)",
        'install(packaging_patch, "share/source/packaging/" + PACKAGING_PATCH)',
        "for name, digest in MODELS.items():",
    )
    positions = [source.index(item) for item in ordered]
    require(positions == sorted(positions), "Packaging verification/application order changed")
    for control in (
        '"application_order": list(PATCHES) + [PACKAGING_PATCH]',
        '"builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()',
        '"preimage_sha256": PACKAGING_PREIMAGE',
        '"postimage_sha256": PACKAGING_POSTIMAGE',
        '"share/source/packaging/provenance.json"',
        '"Imported pinned Debian source-chain provenance; no fresh signature check in this build"',
        '"copyright_member": "debian/copyright"',
        "CONFIG_Q35=y\\nCONFIG_AMD_IOMMU=y\\nCONFIG_EDU=y\\nCONFIG_ISA_DEBUG=y\\n",
        'subprocess.run(["ninja", "-j2", "qemu-system-x86_64"], cwd=build, check=True, timeout=1200)',
        'install(source / "COPYING", "share/doc/COPYING")',
        '"schema": "aurora-event-runtime-v1"',
        '"model": "aurora-amdvi-command-stop-v1"',
        '"qemu_version": "10.0.13"',
        '"firmware_version": "2025.02-8+deb13u1"',
    ):
        require(control in source, "Builder control missing: " + control)
    configure = next(
        node.args[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.args[0], ast.List)
        and any(isinstance(arg, ast.Constant) and arg.value == "--enable-tcg" for arg in node.args[0].elts)
    )
    flags = [arg.value for arg in configure.elts if isinstance(arg, ast.Constant)]
    require(
        flags
        == [
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
        ],
        "Event configure flags changed",
    )
    container = (ROOT / "ci/Containerfile").read_text()
    require("COPY build-event.py qemu-skip-unpack-edk2-blobs.patch /tmp/" in container, "Packaging COPY missing")
    print("PASS exact Debian packaging diff, negative controls and static builder contract; no build attestation")


def main():
    check_integrity()
    check_patch_parser()
    check_packaging_patch()
    # Command mocks install a live process-denial audit hook. Access mocks add
    # another hook afterward. Neither invokes main() or a frozen Guest/case.
    for name in ("mock_command.py", "mock_access.py"):
        try:
            runpy.run_path(str(ROOT / "tests/iommu" / name), run_name="__main__")
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise
    print("PASS static/mock IOMMU diagnostics; no native, QEMU or physical-device qualification")


if __name__ == "__main__":
    main()

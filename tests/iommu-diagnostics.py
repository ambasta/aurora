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


def main():
    check_integrity()
    check_patch_parser()
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

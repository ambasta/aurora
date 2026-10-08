#!/usr/bin/env python3
"""Compile-only rejection checks for unsupported kernel owner profile graphs."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "owned_admission", Path(__file__).with_name("kernel-uefi-owned-bytes-admission.py")
)
ADMISSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADMISSION)


def run(argv, output, expected=0):
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=60)
    output.write_text(result.stdout + result.stderr)
    if (result.returncode == 0) != (expected == 0):
        raise ValueError("Unexpected command result: " + " ".join(map(str, argv)))
    return result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    args = parser.parse_args()
    compiler, build, out = (path.resolve() for path in (args.compiler, args.build_dir, args.artifacts))
    out.mkdir(parents=True, exist_ok=False)
    inputs = [compiler, ROOT / "examples/kernel-owned-bytes.au", ROOT / "kernel/uefi/owned-bytes-entry.S"]
    object_names = (
        "payload-entry",
        "memory",
        "payload",
        "acpi",
        "pci",
        "runtime",
        "owned-bytes-runtime",
        "owned-bytes-profile",
    )
    objects = [build / (name + ".o") for name in object_names]
    inputs += objects + [build / "language.o", ROOT / "kernel/uefi/payload.ld"]
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    result = dict(status="running", native_executed=False, guest_executed=False, inputs=before)
    receipt = out / "run.json"
    try:
        positive = run(["nm", "-a", str(build / "language.o")], out / "positive-symbols.txt")
        ADMISSION.validate_symbols(positive)
        # The real resize helper must link. An unrelated runtime import remains
        # rejected at BOTH closed object admission and the actual freestanding link.
        if "__au_runtime_bytes_resize" not in positive:
            raise ValueError("Resize is not exercised by the admitted graph")
        linker = ["ld", "-nostdlib", "-T", str(ROOT / "kernel/uefi/payload.ld"), "-z", "max-page-size=0x1000"]
        run(
            linker + list(map(str, objects)) + [str(build / "language.o"), "-o", str(out / "accepted-resize.elf")],
            out / "resize-link.log",
        )
        if run(["nm", "-u", str(out / "accepted-resize.elf")], out / "resize-undefined.txt").strip():
            raise ValueError("Admitted resize has unresolved symbols")
        unknown = out / "unknown.s"
        unknown.write_text(
            (build / "language.s")
            .read_text()
            .replace("call __au_runtime_bytes_resize", "call __au_runtime_bytes_unknown")
        )
        run(
            ["as", "--64", str(unknown), str(ROOT / "kernel/uefi/owned-bytes-entry.S"), "-o", str(out / "unknown.o")],
            out / "unknown-assemble.log",
        )
        symbols = run(["nm", "-a", str(out / "unknown.o")], out / "unknown-symbols.txt")
        try:
            ADMISSION.validate_symbols(symbols)
        except ValueError as error:
            if "Unsupported kernel owned-byte runtime import: __au_runtime_bytes_unknown" not in str(error):
                raise ValueError("Unknown import failed for a different admission reason") from error
        else:
            raise ValueError("Unknown runtime import reached kernel admission")
        failed = run(
            linker + list(map(str, objects)) + [str(out / "unknown.o"), "-o", str(out / "rejected-unknown.elf")],
            out / "unknown-link.log",
            expected=1,
        )
        if "undefined reference to `__au_runtime_bytes_unknown'" not in failed:
            raise ValueError("Unknown import link failed for an unexpected reason")
        extra = out / "extra.au"
        extra.write_text("module extra;\nauto unrelated_scalar() -> i64 { return 42; }\n")
        run([str(compiler), str(extra), "-o", str(out / "extra.s")], out / "extra-compile.log")
        run(["as", "--64", str(out / "extra.s"), "-o", str(out / "extra.o")], out / "extra-assemble.log")
        failed = run(
            linker
            + list(map(str, objects))
            + [str(build / "language.o"), str(out / "extra.o"), "-o", str(out / "rejected-mixed.elf")],
            out / "mixed-link.log",
            expected=1,
        )
        if "multiple definition of `aurora_reflect_size'" not in failed:
            raise ValueError("Mixed graph link failed for an unexpected reason")
        if any(path.exists() for path in (out / "rejected-unknown.elf", out / "rejected-mixed.elf")):
            raise ValueError("Rejected link retained an executable output")
        if before != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}:
            raise ValueError("Compile-only rejection inputs changed")
        result.update(
            status="passed", positive_profiles=1, resize_links=1, unsupported_import_rejections=1, negative_links=2
        )
        print(
            "PASS: actual profile admission, real resize link and unsupported import rejection and two negative ELF links"
        )
    except BaseException as error:
        result.update(status="failed", error=str(error))
        raise
    finally:
        receipt.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

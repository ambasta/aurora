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
        source = (ROOT / "examples/kernel-owned-bytes.au").read_text()
        needle = "builtin::OwnedBytes second = region.try_allocate(length);"
        if source.count(needle) != 1:
            raise ValueError("Resize rejection fixture anchor changed")
        resize = out / "resize.au"
        resize.write_text(source.replace(needle, "first.try_resize(length + 1);\n    " + needle))
        run([str(compiler), str(resize), "-o", str(out / "resize.s")], out / "resize-compile.log")
        run(
            [
                "as",
                "--64",
                str(out / "resize.s"),
                str(ROOT / "kernel/uefi/owned-bytes-entry.S"),
                "-o",
                str(out / "resize.o"),
            ],
            out / "resize-assemble.log",
        )
        symbols = run(["nm", "-a", str(out / "resize.o")], out / "resize-symbols.txt")
        try:
            ADMISSION.validate_symbols(symbols)
        except ValueError as error:
            if "Unsupported kernel owned-byte runtime import: __au_runtime_bytes_resize" not in str(error):
                raise ValueError("Resize failed for a different admission reason") from error
        else:
            raise ValueError("Unsupported resize reached kernel runtime admission")
        linker = ["ld", "-nostdlib", "-T", str(ROOT / "kernel/uefi/payload.ld"), "-z", "max-page-size=0x1000"]
        failed = run(
            linker + list(map(str, objects)) + [str(out / "resize.o"), "-o", str(out / "rejected-resize.elf")],
            out / "resize-link.log",
            expected=1,
        )
        if "undefined reference to `__au_runtime_bytes_resize'" not in failed:
            raise ValueError("Resize kernel link failed for an unexpected reason")
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
        if any(path.exists() for path in (out / "rejected-resize.elf", out / "rejected-mixed.elf")):
            raise ValueError("Rejected link retained an executable output")
        if before != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}:
            raise ValueError("Compile-only rejection inputs changed")
        result.update(status="passed", positive_profiles=1, resize_admission_rejections=1, negative_links=2)
        print("PASS: actual profile admission, explicit resize import rejection and two negative ELF links")
    except BaseException as error:
        result.update(status="failed", error=str(error))
        raise
    finally:
        receipt.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

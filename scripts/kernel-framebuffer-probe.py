#!/usr/bin/env python3
"""Run an already-reviewed, non-rendering framebuffer probe in disposable QEMU.

This intentionally does not build an image or grant an omitted-aperture policy.
Firmware SetMode can clear the screen; Aurora performs no framebuffer stores.
A separate reviewed normal image must be booted afterward for restoration.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import qemu_transport as transport
import sys
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_manifest(filename, expected, root, source=False):
    transport.input_path(filename, "reviewed manifest")
    if digest(filename) != expected:
        raise ValueError("Manifest digest mismatch")
    rows = json.loads(Path(filename).read_text())
    actual = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not (source and any(part in {"build", ".git", "__pycache__"} for part in path.parts)):
            actual.append(dict(path=path.relative_to(root).as_posix(), sha256=digest(path)))
    if rows != actual:
        raise ValueError("Manifest content mismatch: " + str(root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True, type=Path, help="reviewed native framebuffer probe profile")
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--qemu-sha256", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--firmware", required=True)
    parser.add_argument("--firmware-sha256", required=True)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--payload-sha256", required=True)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--compiler-sha256", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--data-manifest", required=True)
    parser.add_argument("--data-manifest-sha256", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    build = transport.input_path(args.build_dir, "reviewed image directory", directory=True)
    image = build / "esp/EFI/BOOT/BOOTX64.EFI"
    for path, expected in (
        (args.qemu, args.qemu_sha256),
        (args.firmware, args.firmware_sha256),
        (image, args.image_sha256),
        (build / "payload.elf", args.payload_sha256),
        (args.compiler, args.compiler_sha256),
    ):
        transport.input_path(path, "reviewed input")
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(path) != expected:
            raise ValueError("Reviewed input digest mismatch: " + str(path))
    data = transport.input_path(args.data, "QEMU data", directory=True)
    verify_manifest(args.source_manifest, args.source_manifest_sha256, Path("."), source=True)
    verify_manifest(args.data_manifest, args.data_manifest_sha256, data)
    sys.path.insert(0, str(Path("tests").resolve()))
    from kernel_framebuffer_probe_oracle import validate

    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    command = transport.command(
        Path(args.qemu).resolve(),
        data,
        firmware=["-bios", str(Path(args.firmware).resolve())],
        boot=transport.fat_boot(build / "esp"),
        peripherals=["-vga", "std"],
    )
    receipt = dict(
        command=command,
        clock="tcg-original-clock",
        image_sha256=args.image_sha256,
        qemu_sha256=args.qemu_sha256,
        compiler_sha256=args.compiler_sha256,
        payload_sha256=args.payload_sha256,
        source_manifest_sha256=args.source_manifest_sha256,
        data_manifest_sha256=args.data_manifest_sha256,
        firmware_sha256=args.firmware_sha256,
        scope="GOP/final-map probe only; no Aurora framebuffer writes",
        status="started",
    )
    (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    start = time.monotonic()
    status = transport.run_logged(command, evidence / "serial.log", timeout=30)
    output = (evidence / "serial.log").read_bytes()
    text = output.decode("ascii", errors="replace")
    try:
        observation = validate(status, text)
        passed, error = True, None
    except ValueError as failure:
        observation = None
        passed, error = False, str(failure)
    receipt.update(
        status="passed" if passed else "failed",
        exit_status=status,
        elapsed_seconds=time.monotonic() - start,
        serial_sha256=digest(evidence / "serial.log"),
        observation=observation,
        validation_error=error,
        normal_restoration="pending separate reviewed normal boot",
    )
    (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(text)
    if not passed:
        raise SystemExit("FAIL: framebuffer probe; see preserved receipt")
    print("PASS: bounded GOP map probe; rendering and normal restoration not established")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(transport.failure_label(error) + ": framebuffer probe: " + str(error), file=sys.stderr)
        raise SystemExit(2 if isinstance(error, transport.MissingPrerequisite) else 1) from error

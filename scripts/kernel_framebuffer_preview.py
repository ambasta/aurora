#!/usr/bin/env python3
"""One bounded local preview, reusing qualification's PTY/QMP and pixel checks."""

import argparse
import json
import os
from pathlib import Path
import re
import signal
import struct
import sys
import tempfile
import tty
import zlib

import kernel_framebuffer_admission as admission
from framebuffer_capture_oracle import HEIGHT, WIDTH, need, parse_ppm
from qemu_transport import firmware_args as firmware_options

ROOT = Path(__file__).resolve().parents[1]
capture = admission.load("framebuffer_preview_capture", ROOT / "scripts/kernel-framebuffer-capture.py")


def preflight():
    # HMP pmemsave uses a quoted path, so retain the capture runner's restricted
    # output-path alphabet. No guest or build is started by this check.
    need(re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(ROOT)), "unsupported checkout path for capture")
    for path in (ROOT / "build", ROOT / "build/framebuffer-preview"):
        need(not path.is_symlink(), "capture output directory must not be a symlink")
    master = slave = None
    try:
        master, slave = os.openpty()
        tty.setraw(slave)
    except OSError as error:
        raise admission.common.Blocked("local PTY unavailable: " + str(error)) from error
    finally:
        for fd in (master, slave):
            if fd is not None:
                os.close(fd)


def png(ppm):
    """Encode the validated fixed RGB image using only the Python standard library."""
    rgb = parse_ppm(ppm)

    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))

    rows = b"".join(b"\0" + rgb[y * WIDTH * 3 : (y + 1) * WIDTH * 3] for y in range(HEIGHT))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def run(qemu, firmware, code, variables, data, *, build_dir):
    admission.configure_paths(build_dir, ROOT)
    preflight()
    admitted = admission.checked("framebuffer")
    firmware_args = firmware_options(firmware, code, variables)
    parent = ROOT / "build/framebuffer-preview"
    parent.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    # All capture artifacts are fresh, so a failed rerun cannot expose an old
    # screenshot as its successful result. Ordinary preview never mints reviews.
    (directory / "admission.json").write_text(json.dumps(admitted, indent=2) + "\n")
    manifest = {"cases": {"framebuffer": {"esp": str(admission.BUILD / "esp")}}}
    receipt = dict(schema="aurora-framebuffer-preview-v1", qualified=False, status="failed")
    try:
        result = capture.run_case(
            "framebuffer",
            manifest,
            {"qemu": qemu},
            {"data": data},
            os.environ.copy(),
            directory / "capture",
            firmware_args=firmware_args,
        )
        receipt["capture"] = result
        need(result["status"] == "passed", result.get("error", "capture cleanup failed"))
        admission.checked("framebuffer")
        image = directory / "framebuffer.png"
        image.write_bytes(png((directory / "capture/after.ppm").read_bytes()))
        receipt.update(status="passed", image=str(image), image_sha256=capture.digest(image))
    except (Exception, KeyboardInterrupt) as error:
        receipt["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        (directory / "preview.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("Framebuffer preview files: " + str(directory), flush=True)
    print("PASS: developer preview: " + str(image))
    print("Not independently qualified evidence; no negative guests or normal-restoration boot were run.")
    return receipt


def interrupted(signum, frame):
    raise KeyboardInterrupt("interrupted by signal " + str(signum))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--build-dir", type=Path, help="exact native framebuffer profile directory")
    parser.add_argument("inputs", nargs="*")
    args = parser.parse_args()
    if args.preflight:
        need(not args.inputs, "--preflight takes no inputs")
        preflight()
    else:
        need(len(args.inputs) == 5, "Expected QEMU OVMF CODE VARS DATA from kernel-framebuffer-preview.sh")
        signal.signal(signal.SIGTERM, interrupted)
        need(args.build_dir is not None, "capture requires --build-dir")
        run(*args.inputs, build_dir=args.build_dir)


if __name__ == "__main__":
    try:
        main()
    except admission.common.Blocked as error:
        print("BLOCKED: framebuffer preview: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (Exception, KeyboardInterrupt) as error:
        print("FAIL: framebuffer preview: " + str(error), file=sys.stderr)
        raise SystemExit(1) from error

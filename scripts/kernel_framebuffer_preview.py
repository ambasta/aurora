#!/usr/bin/env python3
"""Native framebuffer preview or four-case smoke using shared PTY/QMP capture."""

import argparse
import importlib.util
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

from framebuffer_capture_oracle import HEIGHT, MODES, WIDTH, need, parse_ppm
from qemu_transport import firmware_args as firmware_options
import qemu_transport as transport

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "framebuffer_preview_capture", ROOT / "scripts/kernel-framebuffer-capture.py"
)
capture = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = capture
_spec.loader.exec_module(capture)


class Blocked(Exception):
    pass


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
        raise Blocked("local PTY unavailable: " + str(error)) from error
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


def run(qemu, firmware, code, variables, data, *, build_dir, full_smoke=False):
    preflight()
    if full_smoke:
        need(
            build_dir.is_absolute() and build_dir.parts[-3:] == ("kernel-images", "uefi", "display-fixture"),
            "full smoke requires the native display-fixture profile directory",
        )
    # Every case boots the display fixture with its own fw_cfg row; 'G' releases it.
    modes = MODES if full_smoke else ("framebuffer",)
    profiles = {mode: build_dir for mode in modes}
    firmware_args = firmware_options(firmware, code, variables)
    parent = ROOT / "build/framebuffer-preview"
    parent.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    manifest = {"cases": {mode: {"esp": str(profiles[mode] / "esp")} for mode in modes}}
    receipt = dict(schema="aurora-framebuffer-preview-v1", qualified=False, status="failed", cases=[])
    primary, unsettled = None, False
    try:
        for mode in modes:
            destination = directory / (mode if full_smoke else "capture")
            result = capture.run_case(
                mode,
                manifest,
                {"qemu": qemu},
                {"data": data},
                os.environ.copy(),
                destination,
                firmware_args=firmware_args,
            )
            receipt["cases"].append(result)
            unsettled = bool(result.get("unsettled"))
            need(result["status"] == "passed", result.get("error", "capture cleanup failed"))
            if mode == "framebuffer":
                image = directory / "framebuffer.png"
                image.write_bytes(png((destination / "after.ppm").read_bytes()))
                receipt.update(image=str(image), image_sha256=capture.digest(image))
        receipt["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        primary = error
        receipt["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if full_smoke:
            restored = dict(status="failed")
            receipt["normal_restoration"] = restored
            try:
                need(
                    not unsettled and not isinstance(primary, transport.ChildNotReaped),
                    "unreaped guest blocks normal restoration",
                )
                status = transport.run_logged(
                    ["bash", ROOT / "scripts/kernel-uefi-smoke.sh", "normal"],
                    directory / "normal-restoration.log",
                    env=dict(os.environ, MESON_BUILD_DIR=str(build_dir.parents[2])),
                    cwd=ROOT,
                    timeout=180,
                )
                restored["exit_status"] = status
                need(status == 0, "normal UEFI smoke failed: " + str(status))
                restored.update(status="passed", exit_status=status)
            except (Exception, KeyboardInterrupt) as error:
                receipt["status"] = "failed"
                restored["error"] = type(error).__name__ + ": " + str(error)
                if primary is None:
                    primary = error
        (directory / "preview.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("Framebuffer preview files: " + str(directory), flush=True)
    if primary is not None:
        raise primary
    print(
        "PASS: developer framebuffer "
        + ("four-case smoke and normal boot: " if full_smoke else "preview: ")
        + str(image)
    )
    if not full_smoke:
        print("Not independently qualified evidence; no negative guests or normal-restoration boot were run.")
    return receipt


def interrupted(signum, frame):
    raise KeyboardInterrupt("interrupted by signal " + str(signum))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--full-smoke", action="store_true", help="four native framebuffer cases and a normal boot")
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
        run(*args.inputs, build_dir=args.build_dir, full_smoke=args.full_smoke)


if __name__ == "__main__":
    try:
        main()
    except Blocked as error:
        print("BLOCKED: framebuffer preview: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (Exception, KeyboardInterrupt) as error:
        print("FAIL: framebuffer preview: " + str(error), file=sys.stderr)
        raise SystemExit(1) from error

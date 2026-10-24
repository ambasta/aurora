#!/usr/bin/env python3
"""Boot the BAR and IVRS device profiles in QEMU and validate their serial oracles.

A family name (bar, ivrs) runs every mode of that family in order. Clean-firmware
modes use the patched OVMF fixture from AURORA_BAR_FIRMWARE / AURORA_IVRS_FIRMWARE
(<dir>/output/OVMF_{CODE,VARS}.fd) or <AURORA_BOOT_FIXTURE_PREFIX or
/opt/aurora-fixtures>/firmware/OVMF_{CODE,VARS}.fd; the others use stock OVMF.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

import qemu_transport as transport
from kernel_profiles import FIXTURE_MODES, canonical_profile

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = {
    "bar": ("bar-state", "bar-capture", "bar-inherited", "bar-read", "bar-write", "bar-revoked", "bar-alias"),
    "ivrs": ("ivrs-default", "ivrs-read", "ivrs-write", "ivrs-revoked", "ivrs-missing"),
}
MODES = FAMILIES["bar"] + ("bar-prepare",) + FAMILIES["ivrs"]
STOCK = ("bar-state", "bar-capture", "bar-inherited")
need = transport.need


def oracle(family):
    spec = importlib.util.spec_from_file_location(family + "_smoke", ROOT / "tests" / f"kernel-uefi-{family}-smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def firmware(mode, family, env, out):
    if mode in STOCK:
        return ["-bios", str(transport.input_path(env.get("OVMF") or "/usr/share/ovmf/OVMF.fd", "OVMF"))]
    selected = env.get("AURORA_" + family.upper() + "_FIRMWARE")
    root = (
        Path(selected) / "output"
        if selected
        else Path(env.get("AURORA_BOOT_FIXTURE_PREFIX") or "/opt/aurora-fixtures") / "firmware"
    )
    code = transport.input_path(root / "OVMF_CODE.fd", "clean firmware CODE")
    shutil.copy2(transport.input_path(root / "OVMF_VARS.fd", "clean firmware VARS"), out / "vars.fd")
    return [
        "-drive",
        f"if=pflash,format=raw,unit=0,file={code},readonly=on",
        "-drive",
        f"if=pflash,format=raw,unit=1,file={out}/vars.fd",
    ]


def image_directory(mode, out, env):
    with (out / "build.log").open("xb") as log:
        transport.run_logged(
            [
                sys.executable,
                "-B",
                ROOT / "scripts/meson_test.py",
                "--kernel",
                "uefi",
                "--profile",
                mode,
                "--print-image-dir",
            ],
            out / "image-directory.log",
            cwd=ROOT,
            env=env,
            stderr=log,
            timeout=1800,
            expected=0,
            timeout_status=False,
        )
    return Path((out / "image-directory.log").read_text().strip())


def run(mode, out, build=None):
    family = mode.split("-")[0]
    env = os.environ.copy()
    need(not out.exists() and not any(c in str(out) for c in ",\n\r"), f"Output must be a fresh plain path: {out}")
    out.mkdir(parents=True)
    out = out.resolve()
    qemu = shutil.which(env.get("QEMU") or "qemu-system-x86_64")
    if qemu is None:
        raise transport.MissingPrerequisite("QEMU unavailable")
    data = transport.input_path(env.get("QEMU_DATA") or "/usr/share/qemu", "QEMU_DATA", True)
    build = build or image_directory(mode, out, env)
    need(build.parts[-3:] == ("kernel-images", "uefi", canonical_profile("uefi", mode)), "Wrong image profile")
    shutil.copytree(build / "esp", out / "esp")
    argv = transport.command(
        qemu,
        data,
        firmware=firmware(mode, family, env, out),
        boot=transport.fat_boot(out / "esp"),
        peripherals=["-device", "nvme,serial=AURORA_READ_ONLY,bus=pcie.0,addr=02.0"],
        diagnostics=[
            "-chardev",
            f"file,id=firmware,path={out}/firmware.log",
            "-device",
            "isa-debugcon,iobase=0x402,chardev=firmware",
        ],
        extra=["-device", "amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off"]
        if family == "ivrs" and mode != "ivrs-missing"
        else [],
    )
    startup = FIXTURE_MODES.get(mode)
    status = transport.run_logged(
        argv, out / "serial.log", cwd=ROOT, env=env, timeout=60, startup_byte=startup[1] if startup else None
    )
    serial = (out / "serial.log").read_text()
    print(serial, end="")
    metadata = json.loads((build / f"{family}-metadata.json").read_text())
    oracle(family).validate(status, serial, mode, metadata)
    print(f"PASS: {mode} guest; output {out}")


def interrupted(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES + tuple(FAMILIES))
    parser.add_argument("--output", type=Path, help="fresh output directory (default: under build/)")
    parser.add_argument("--run-only", type=Path, help="already-built profile directory; never invokes Ninja")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.mode in FAMILIES:
            need(args.run_only is None, "--run-only selects one mode")
            parent = args.output or os.environ.get("AURORA_" + args.mode.upper() + "_RECEIPTS")
            parent = Path(parent) if parent else Path(tempfile.mkdtemp(prefix=args.mode + "-", dir=ROOT / "build"))
            for mode in FAMILIES[args.mode]:
                run(mode, parent / mode)
        else:
            output = args.output or Path(tempfile.mkdtemp(prefix=args.mode + "-", dir=ROOT / "build")) / "run"
            run(args.mode, output, args.run_only.resolve(strict=True) if args.run_only else None)
    except transport.MissingPrerequisite as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError, transport.ChildNotReaped) as error:
        print(f"{transport.failure_label(error)}: device runner: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

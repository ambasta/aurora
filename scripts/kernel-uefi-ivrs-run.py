#!/usr/bin/env python3
"""Cold, namespace-free emulator IVRS receipts; never used for historical gates."""

import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys
import qemu_transport as transport
from meson_test import selected_kernel_compiler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODES = (
    "ivrs-default",
    "ivrs-read",
    "ivrs-write",
    "ivrs-revoked",
    "ivrs-pair",
    "ivrs-alias",
    "ivrs-reserved",
    "ivrs-scope",
    "ivrs-capability",
    "ivrs-range",
    "ivrs-missing",
)


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"kernel-uefi-{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    return dict(path=str(Path(path).resolve()), sha256=digest(path))


def prerequisites(env):
    paths = {}
    for name, directory in (
        ("QEMU", False),
        ("QEMU_DATA", True),
        ("AURORA_IVRS_FIRMWARE", True),
        ("AURORA_IVRS_COVERAGE", False),
    ):
        paths[name] = transport.input_path(transport.required(env, name, "the qualified IVRS input"), name, directory)
    if not os.access(paths["QEMU"], os.X_OK):
        raise ValueError("QEMU must name an executable file")
    return paths


def command(mode, qemu, data, code, out, events):
    transport.need(mode in MODES, "Unknown IVRS mode")
    firmware = [
        "-drive",
        f"if=pflash,format=raw,unit=0,file={code},readonly=on",
        "-drive",
        f"if=pflash,format=raw,unit=1,file={out}/vars-runtime.fd",
    ]
    return transport.command(
        qemu,
        data,
        firmware=firmware,
        boot=transport.fat_boot(out / "esp"),
        peripherals=["-device", "nvme,serial=AURORA_READ_ONLY,bus=pcie.0,addr=02.0"],
        diagnostics=[
            "-trace",
            f"events={events},file={out}/trace.log",
            "-chardev",
            f"file,id=firmware,path={out}/firmware.log",
            "-device",
            "isa-debugcon,iobase=0x402,chardev=firmware",
        ],
        extra=[] if mode == "ivrs-missing" else ["-device", "amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off"],
    )


def run(mode, out, paths):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    qemu = paths["QEMU"]
    data = paths["QEMU_DATA"]
    fixture = paths["AURORA_IVRS_FIRMWARE"]
    coverage_path = paths["AURORA_IVRS_COVERAGE"]
    coverage = module("ivrs-trace").load_coverage(coverage_path)
    events = Path(json.loads(coverage_path.read_text())["events"])
    if not events.is_absolute():
        events = coverage_path.parent / events
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
            env=os.environ.copy(),
            stderr=log,
            timeout=1800,
            expected=0,
            timeout_status=False,
        )
    selected = (out / "image-directory.log").read_text()
    build = Path(selected.rstrip("\n"))
    transport.need(
        selected == str(build) + "\n" and selected.count("\n") == 1 and build.is_absolute(),
        "Invalid native image directory handoff",
    )
    transport.need(build.parts[-3:] == ("kernel-images", "uefi", mode), "Wrong native image profile")
    compiler = selected_kernel_compiler(build.parents[2])
    shutil.copytree(build / "esp", out / "esp")
    shutil.copy2(build / "ivrs-stack.json", out / "stack-usage.json")
    for name in ("pci", "acpi", "payload"):
        shutil.copy2(build / "objects" / (name + ".su"), out / (name + ".su"))
    files = {
        name: record(path)
        for name, path in [("qemu", qemu), ("events", events), ("compiler", compiler), ("coverage", coverage_path)]
    }
    for key, name in [
        ("payload", "payload.bin"),
        ("payload_elf", "payload.elf"),
        ("payload_metadata", "ivrs-metadata.json"),
    ]:
        shutil.copy2(build / name, out / name)
        files[key] = record(out / name)
    files["loader"] = record(out / "esp/EFI/BOOT/BOOTX64.EFI")
    code = fixture / "output/OVMF_CODE.fd"
    template = fixture / "output/OVMF_VARS.fd"
    for name in ("vars-initial.fd", "vars-runtime.fd"):
        shutil.copy2(template, out / name)
    files.update(
        firmware_code=record(code),
        vars_template=record(template),
        vars_initial=record(out / "vars-initial.fd"),
        firmware_patch=record(fixture / "provenance/policy-three-file.patch"),
    )
    argv = command(mode, qemu, data, code, out, events)
    invocation = dict(
        schema="aurora-ivrs-run-v1",
        mode=mode,
        argv=argv,
        cwd=str(ROOT),
        environment={"LD_LIBRARY_PATH": env.get("LD_LIBRARY_PATH", "")},
        firmware_profile="clean",
        boot_root=str(out / "esp"),
        stdio={"stdout": str(out / "serial.log"), "stderr": "stdout"},
        files=files,
    )
    invocation["iommu_profile"] = "architectural" if mode == "ivrs-default" else "qemu-10.0.13-cold"
    invocation["firmware_source_revision"] = "fbe0805b2091393406952e84724188f8c1941837"
    (out / "invocation-start.json").write_text(json.dumps(invocation, indent=2) + "\n")
    status = transport.run_logged(argv, out / "serial.log", cwd=ROOT, env=env, timeout=60)
    (out / "status").write_text(str(status) + "\n")
    invocation["status"] = status
    for key, name in [("serial", "serial.log"), ("trace", "trace.log"), ("firmware_log", "firmware.log")]:
        files[key] = record(out / name)
    files["vars_after"] = record(out / "vars-runtime.fd")
    (out / "receipt.json").write_text(json.dumps(invocation, indent=2) + "\n")
    serial = (out / "serial.log").read_text()
    print(serial, end="")
    metadata = json.loads((out / "ivrs-metadata.json").read_text())
    module("ivrs-smoke").validate(status, serial, mode, metadata)
    result = module("ivrs-trace").validate_trace(
        (out / "trace.log").read_text(), (out / "firmware.log").read_text(), serial, mode, coverage, metadata
    )
    (out / "trace-result.json").write_text(json.dumps(result, indent=2) + "\n")
    module("ivrs-provenance").validate(out / "receipt.json")
    print(f"PASS: actual cold IVRS gate {mode}; receipt {out}/receipt.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    paths = prerequisites(os.environ)
    run(args.mode, Path(args.output), paths)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(transport.failure_label(error) + ": IVRS runner: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error

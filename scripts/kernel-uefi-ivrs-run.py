#!/usr/bin/env python3
"""Cold, namespace-free emulator IVRS receipts; never used for historical gates."""

import argparse, hashlib, importlib.util, json, os, shutil, signal, subprocess, sys
import qemu_transport as transport
import kernel_trace_controls as controls
import kernel_profiles as profiles
from meson_test import selected_kernel_compiler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODES = (
    "ivrs-default",
    "ivrs-read",
    "ivrs-write",
    "ivrs-revoked",
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
    command = env.get("QEMU") or "qemu-system-x86_64"
    executable = shutil.which(command, path=env.get("PATH"))
    if executable is None:
        if os.sep in command and Path(command).exists():
            raise ValueError("QEMU must name an executable file")
        raise transport.MissingPrerequisite("Missing dependency: " + command)
    paths = dict(
        QEMU=transport.input_path(executable, "QEMU"),
        QEMU_DATA=transport.input_path(env.get("QEMU_DATA") or "/usr/share/qemu", "QEMU_DATA", True),
    )
    transport.need(digest(paths["QEMU"]) == module("ivrs-provenance").PINS["qemu"], "Unreviewed QEMU binary")
    paths["packaged"] = not bool(env.get("AURORA_IVRS_FIRMWARE"))
    if paths["packaged"]:
        paths["code"], paths["template"], paths["patch"] = controls.supported_firmware(env)
    else:
        fixture = transport.input_path(env["AURORA_IVRS_FIRMWARE"], "AURORA_IVRS_FIRMWARE", True)
        for key, relative, pin in (
            ("code", "output/OVMF_CODE.fd", "clean_code"),
            ("template", "output/OVMF_VARS.fd", "clean_vars"),
            ("patch", "provenance/policy-three-file.patch", "clean_patch"),
        ):
            path = transport.input_path(fixture / relative, "clean firmware " + key)
            transport.need(digest(path) == module("ivrs-provenance").PINS[pin], "Unreviewed clean firmware " + key)
            paths[key] = path
    paths["AURORA_IVRS_COVERAGE"] = None
    if env.get("AURORA_IVRS_COVERAGE"):
        path = transport.input_path(env["AURORA_IVRS_COVERAGE"], "AURORA_IVRS_COVERAGE")
        try:
            trace = module("ivrs-trace")
            coverage = trace.load_coverage(path)
            for name in ("msix_control", "amdvi_control"):
                transport.input_path(coverage[name], name, True)
            trace.validate_coverage(coverage)
        except transport.MissingPrerequisite:
            raise
        except (FileNotFoundError, PermissionError) as error:
            raise transport.MissingPrerequisite("Unavailable IVRS coverage: " + str(error)) from error
        except (KeyError, TypeError, OSError, ValueError) as error:
            raise ValueError("Invalid AURORA_IVRS_COVERAGE: " + str(error)) from error
        paths["AURORA_IVRS_COVERAGE"] = path
    else:
        paths["stock"] = controls.stock_firmware(env)
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


def run(mode, out, paths, build=None):
    paths = dict(paths)
    if build is not None:
        transport.need(
            paths["AURORA_IVRS_COVERAGE"] is not None, "--run-only requires explicit validated AURORA_IVRS_COVERAGE"
        )
        transport.need(
            build.is_absolute()
            and build.is_dir()
            and build.resolve(strict=True) == build
            and build.parts[-3:] == ("kernel-images", "uefi", profiles.canonical_profile("uefi", mode)),
            "Wrong prebuilt IVRS profile",
        )
    transport.need(not out.is_symlink() and not out.exists(), "Output directory must be fresh and absent")
    out = out.resolve()
    transport.need(build is None or not out.is_relative_to(build), "Output cannot modify the prebuilt IVRS profile")
    transport.need(not any(char in str(out) for char in (",", "\n", "\r")), "Invalid output option path")
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    qemu = paths["QEMU"]
    data = paths["QEMU_DATA"]
    coverage_path = paths["AURORA_IVRS_COVERAGE"]
    if coverage_path is None:
        coverage_path = controls.generate("ivrs", out / "controls", qemu, data, paths["stock"], env)
    paths["AURORA_IVRS_COVERAGE"] = coverage_path
    if build is None:
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
        transport.need(
            build.parts[-3:] == ("kernel-images", "uefi", profiles.canonical_profile("uefi", mode)),
            "Wrong native image profile",
        )
    execute(mode, out, paths, build, env)


def execute(mode, out, paths, build, env):
    """Run the already selected image with private ESP/VARS/logs and all oracles."""
    qemu, data = paths["QEMU"], paths["QEMU_DATA"]
    coverage_path = paths["AURORA_IVRS_COVERAGE"]
    coverage = module("ivrs-trace").load_coverage(coverage_path)
    events = Path(json.loads(coverage_path.read_text())["events"])
    if not events.is_absolute():
        events = coverage_path.parent / events
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
    code, template = paths["code"], paths["template"]
    for name in ("vars-initial.fd", "vars-runtime.fd"):
        shutil.copy2(template, out / name)
    files.update(
        firmware_code=record(code),
        vars_template=record(template),
        vars_initial=record(out / "vars-initial.fd"),
        firmware_patch=record(paths["patch"]),
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
    if paths["packaged"]:
        invocation["firmware_package"] = controls.FIRMWARE_VERSION
    invocation["iommu_profile"] = "architectural" if mode == "ivrs-default" else "qemu-10.0.13-cold"
    invocation["firmware_source_revision"] = "fbe0805b2091393406952e84724188f8c1941837"
    startup = profiles.FIXTURE_MODES.get(mode)
    if startup:
        invocation["startup_byte"] = startup[1]
    (out / "invocation-start.json").write_text(json.dumps(invocation, indent=2) + "\n")
    status = transport.run_logged(
        argv, out / "serial.log", cwd=ROOT, env=env, timeout=60, startup_byte=startup[1] if startup else None
    )
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
    if paths["packaged"]:
        module("ivrs-provenance").validate(
            out / "receipt.json", fixture_prefix=env.get("AURORA_BOOT_FIXTURE_PREFIX") or controls.DEFAULT_PREFIX
        )
    else:
        module("ivrs-provenance").validate(out / "receipt.json")
    print(f"PASS: actual cold IVRS gate {mode}; receipt {out}/receipt.json")


def interrupted(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-only", type=Path, help="explicit already-built native profile; never invokes Ninja")
    args = parser.parse_args()
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        paths = prerequisites(os.environ)
        run(args.mode, Path(args.output), paths, args.run_only)
    finally:
        signal.signal(signal.SIGTERM, previous_term)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, transport.ChildNotReaped) as error:
        print(transport.failure_label(error) + ": IVRS runner: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error

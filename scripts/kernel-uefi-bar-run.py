#!/usr/bin/env python3
"""Cold, namespace-free emulator BAR receipts; never used for historical gates."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import qemu_transport as transport
import kernel_trace_controls as controls
from meson_test import selected_kernel_compiler
from kernel_profiles import canonical_profile
from qemu_transport import MissingPrerequisite, input_path

ROOT = Path(__file__).resolve().parent.parent
MODES = (
    "bar-state",
    "bar-capture",
    "bar-inherited",
    "bar-read",
    "bar-prepare",
    "bar-write",
    "bar-revoked",
    "bar-alias",
)
CLEAN = ("bar-read", "bar-prepare", "bar-write", "bar-revoked", "bar-alias")


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"kernel-uefi-{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    return dict(path=str(Path(path).resolve()), sha256=digest(path))


def preflight(mode, output, env):
    """Check fresh output and the existing qualification contract before mutation."""
    if mode not in MODES:
        raise ValueError(f"Unsupported BAR mode: {mode}")
    if output.is_symlink() or output.exists():
        raise ValueError(f"Output directory must be fresh and absent: {output}")
    output = output.resolve()
    if output.is_relative_to((ROOT / "build/uefi").resolve()):
        raise ValueError("Output directory cannot be inside the shared build/uefi image directory")
    if any(character in str(output) for character in (",", "\n", "\r")):
        raise ValueError("Output directory cannot contain commas or line breaks in QEMU option paths")
    for name, value in env.items():
        if value and (
            name.startswith("KERNEL_TEST_")
            or name
            in ("KERNEL_USER_PROBE_MODE", "KERNEL_CONSOLE", "UEFI_MODE", "UEFI_CONSOLE_HANDOFF", "AURORA_TEST_CONTEXT")
        ):
            raise ValueError(f"Unset {name} before starting a standalone BAR receipt run")
    # A normal installed command name is supported, but its exact binary still
    # has to satisfy the existing provenance pin. Discovery is not qualification.
    command = env.get("QEMU") or "qemu-system-x86_64"
    if any(character in command for character in (",", "\n", "\r")):
        raise ValueError("QEMU cannot contain commas or line breaks in its executable path")
    executable = shutil.which(command, path=env.get("PATH"))
    if executable is None:
        # An explicitly selected existing path of the wrong kind/permission is
        # invalid configuration, not an absent executable discovered on PATH.
        if env.get("QEMU") and os.sep in command:
            try:
                selected = Path(command)
                if selected.exists():
                    raise ValueError(f"QEMU must name an executable file: {selected}")
            except (FileNotFoundError, PermissionError) as error:
                raise MissingPrerequisite(f"Unavailable QEMU prerequisite: {error}") from error
        raise MissingPrerequisite(f"Missing dependency: {command}; set QEMU to the qualified QEMU executable")
    qemu = input_path(executable, "QEMU")
    data = input_path(env.get("QEMU_DATA") or "/usr/share/qemu", "QEMU_DATA", True)
    provenance = module("bar-provenance")
    trace = module("bar-trace")
    coverage_path = coverage = events = None
    if env.get("AURORA_BAR_COVERAGE"):
        coverage_path = input_path(env["AURORA_BAR_COVERAGE"], "AURORA_BAR_COVERAGE")
        try:
            coverage = trace.load_coverage(coverage_path)
            if isinstance(coverage, dict) and "msix_control" in coverage:
                control = Path(coverage["msix_control"])
                if not control.exists() or not os.access(control, os.R_OK):
                    raise MissingPrerequisite(f"Coverage MSI-X control directory unavailable: {control}")
            trace.validate_coverage(coverage)
            events = input_path(
                coverage_path.parent / json.loads(coverage_path.read_text())["events"], "coverage events"
            )
        except MissingPrerequisite:
            raise
        except (FileNotFoundError, PermissionError) as error:
            raise MissingPrerequisite(f"Unavailable AURORA_BAR_COVERAGE prerequisite: {error}") from error
        except (KeyError, TypeError, OSError, ValueError) as error:
            raise ValueError(f"Invalid AURORA_BAR_COVERAGE: {error}") from error
    pinned = [("QEMU", qemu, "qemu")]
    if events is not None:
        pinned.append(("trace events", events, "events"))
    packaged = False
    clean = mode in CLEAN
    if clean:
        if env.get("AURORA_BAR_FIRMWARE"):
            fixture = input_path(env["AURORA_BAR_FIRMWARE"], "AURORA_BAR_FIRMWARE", True)
            code = input_path(fixture / "output/OVMF_CODE.fd", "clean firmware CODE")
            template = input_path(fixture / "output/OVMF_VARS.fd", "clean firmware VARS")
            patch = input_path(fixture / "provenance/policy-three-file.patch", "clean firmware patch")
            pinned += [
                ("clean firmware CODE", code, "clean_code"),
                ("clean firmware VARS", template, "clean_vars"),
                ("clean firmware patch", patch, "clean_patch"),
            ]
        else:
            code, template, patch = controls.supported_firmware(env)
            packaged = True
    else:
        code = input_path(env.get("OVMF") or "/usr/share/ovmf/OVMF.fd", "OVMF")
        template = patch = None
        pinned.append(("stock firmware CODE", code, "stock_code"))
    stock = controls.stock_firmware(env) if coverage_path is None else None
    for label, path, pin in pinned:
        if digest(path) != provenance.PINS[pin]:
            raise ValueError(f"Unreviewed {label}: SHA-256 differs from the existing BAR provenance pin")
    compiler = Path(env.get("AURORAC") or ROOT / "build/aurorac").resolve()
    if env.get("AURORAC") and not compiler.exists():
        raise MissingPrerequisite(f"AURORAC must name an executable compiler: {compiler}")
    if env.get("AURORAC") and (not compiler.is_file() or not os.access(compiler, os.X_OK)):
        raise ValueError(f"AURORAC must name an executable compiler: {compiler}")
    return dict(
        output=output,
        qemu=qemu,
        data=data,
        coverage_path=coverage_path,
        coverage=coverage,
        events=events,
        code=code,
        template=template,
        patch=patch,
        compiler=compiler,
        clean=clean,
        packaged=packaged,
        stock=stock,
    )


def execute(mode, config, env, build):
    out = config["output"]
    qemu, data = config["qemu"], config["data"]
    code, clean = config["code"], config["clean"]
    events, coverage = config["events"], config["coverage"]
    shutil.copytree(build / "esp", out / "esp")
    files = {
        name: record(path)
        for name, path in (
            ("qemu", qemu),
            ("events", events),
            ("compiler", config["compiler"]),
            ("coverage", config["coverage_path"]),
        )
    }
    for key, name in (
        ("payload", "payload.bin"),
        ("payload_elf", "payload.elf"),
        ("payload_metadata", "bar-metadata.json"),
    ):
        shutil.copy2(build / name, out / name)
        files[key] = record(out / name)
    files["loader"] = record(out / "esp/EFI/BOOT/BOOTX64.EFI")
    files["firmware_code"] = record(code)
    if clean:
        template = config["template"]
        for name in ("vars-initial.fd", "vars-runtime.fd"):
            shutil.copy2(template, out / name)
        files.update(
            vars_template=record(template),
            vars_initial=record(out / "vars-initial.fd"),
            firmware_patch=record(config["patch"]),
        )
        firmware = [
            "-drive",
            f"if=pflash,format=raw,unit=0,file={code},readonly=on",
            "-drive",
            f"if=pflash,format=raw,unit=1,file={out}/vars-runtime.fd",
        ]
    else:
        firmware = ["-bios", str(code)]
    argv = transport.command(
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
    )
    invocation = dict(
        schema="aurora-bar-run-v1",
        mode=mode,
        argv=argv,
        cwd=str(ROOT),
        environment={"LD_LIBRARY_PATH": env.get("LD_LIBRARY_PATH", "")},
        firmware_profile="clean" if clean else "stock",
        boot_root=str(out / "esp"),
        stdio={"stdout": str(out / "serial.log"), "stderr": "stdout"},
        files=files,
    )
    if config["packaged"]:
        invocation["firmware_package"] = controls.FIRMWARE_VERSION
    if clean:
        invocation["firmware_source_revision"] = module("bar-provenance").REVISION
    (out / "invocation-start.json").write_text(json.dumps(invocation, indent=2) + "\n")
    status = transport.run_logged(argv, out / "serial.log", cwd=ROOT, env=env, timeout=60)
    (out / "status").write_text(str(status) + "\n")
    invocation["status"] = status
    for key, name in (("serial", "serial.log"), ("trace", "trace.log"), ("firmware_log", "firmware.log")):
        files[key] = record(out / name)
    if clean:
        files["vars_after"] = record(out / "vars-runtime.fd")
    (out / "receipt.json").write_text(json.dumps(invocation, indent=2) + "\n")
    serial = (out / "serial.log").read_text()
    print(serial, end="")
    metadata = json.loads((out / "bar-metadata.json").read_text())
    module("bar-smoke").validate(status, serial, mode, metadata)
    result = module("bar-trace").validate_trace(
        (out / "trace.log").read_text(), (out / "firmware.log").read_text(), serial, mode, coverage, metadata
    )
    (out / "trace-result.json").write_text(json.dumps(result, indent=2) + "\n")
    if config["packaged"]:
        module("bar-provenance").validate(
            out / "receipt.json", fixture_prefix=env.get("AURORA_BOOT_FIXTURE_PREFIX") or controls.DEFAULT_PREFIX
        )
    else:
        module("bar-provenance").validate(out / "receipt.json")


def run(mode, output, build=None):
    env = os.environ.copy()
    config = preflight(mode, output, env)
    if build is not None:
        transport.need(
            config["coverage_path"] is not None, "--run-only requires explicit validated AURORA_BAR_COVERAGE"
        )
        profile = canonical_profile("uefi", mode)
        transport.need(
            build.is_absolute()
            and build.is_dir()
            and build.resolve(strict=True) == build
            and build.parts[-3:] == ("kernel-images", "uefi", profile),
            "Wrong prebuilt BAR profile",
        )
    out = config["output"]
    transport.need(build is None or not out.is_relative_to(build), "Output cannot modify the prebuilt BAR profile")
    out.mkdir(parents=True, exist_ok=False)
    if config["coverage_path"] is None:
        path = controls.generate("bar", out / "controls", config["qemu"], config["data"], config["stock"], env)
        config.update(
            coverage_path=path,
            coverage=module("bar-trace").load_coverage(path),
            events=path.parent / json.loads(path.read_text())["events"],
        )
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
                env=env,
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
        profile = canonical_profile("uefi", mode)
        transport.need(build.parts[-3:] == ("kernel-images", "uefi", profile), "Wrong native image profile")
    config["compiler"] = selected_kernel_compiler(build.parents[2])
    execute(mode, config, env, build)
    print(f"PASS: actual cold BAR gate {mode}; receipt {out}/receipt.json")


def interrupted(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--output", required=True, help="fresh, absent receipt directory")
    parser.add_argument("--run-only", type=Path, help="explicit already-built native profile; never invokes Ninja")
    args = parser.parse_args()
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        run(args.mode, Path(args.output), args.run_only)
    except (OSError, ValueError, subprocess.SubprocessError, transport.ChildNotReaped) as error:
        print(f"{transport.failure_label(error)}: BAR runner: {error}", file=sys.stderr)
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    return 0


if __name__ == "__main__":
    sys.exit(main())

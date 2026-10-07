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


def required(env, name, explanation):
    value = env.get(name, "")
    if not value:
        raise ValueError(f"Set {name}: {explanation}. See docs/smoke-entrypoint-repair.md.")
    return value


def input_path(value, label, directory=False):
    path = Path(value).resolve()
    if not (path.is_dir() if directory else path.is_file()) or not os.access(path, os.R_OK):
        raise ValueError(f"{label} must name a readable {'directory' if directory else 'file'}: {path}")
    if any(character in str(path) for character in (",", "\n", "\r")):
        raise ValueError(f"{label} cannot contain commas or line breaks in QEMU option paths")
    return path


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
    executable = shutil.which(command, path=env.get("PATH"))
    if executable is None:
        raise ValueError(f"Missing dependency: {command}; set QEMU to the qualified QEMU executable")
    qemu = input_path(executable, "QEMU")
    data = input_path(required(env, "QEMU_DATA", "the matching qualified QEMU data directory"), "QEMU_DATA", True)
    coverage_path = input_path(
        required(env, "AURORA_BAR_COVERAGE", "the retained trace-coverage JSON and its control artifacts"),
        "AURORA_BAR_COVERAGE",
    )
    provenance = module("bar-provenance")
    trace = module("bar-trace")
    try:
        coverage = trace.load_coverage(coverage_path)
        trace.validate_coverage(coverage)
        events = input_path(coverage_path.parent / json.loads(coverage_path.read_text())["events"], "coverage events")
    except (KeyError, TypeError, OSError, ValueError) as error:
        raise ValueError(f"Invalid AURORA_BAR_COVERAGE: {error}") from error
    pinned = [("QEMU", qemu, "qemu"), ("trace events", events, "events")]
    clean = mode in CLEAN
    if clean:
        fixture = input_path(
            required(env, "AURORA_BAR_FIRMWARE", "the qualified clean firmware fixture root; stock OVMF is unsuitable"),
            "AURORA_BAR_FIRMWARE",
            True,
        )
        code = input_path(fixture / "output/OVMF_CODE.fd", "clean firmware CODE")
        template = input_path(fixture / "output/OVMF_VARS.fd", "clean firmware VARS")
        patch = input_path(fixture / "provenance/policy-three-file.patch", "clean firmware patch")
        pinned += [
            ("clean firmware CODE", code, "clean_code"),
            ("clean firmware VARS", template, "clean_vars"),
            ("clean firmware patch", patch, "clean_patch"),
        ]
    else:
        code = input_path(required(env, "OVMF", "the qualified stock combined OVMF ROM"), "OVMF")
        template = patch = None
        pinned.append(("stock firmware CODE", code, "stock_code"))
    for label, path, pin in pinned:
        if digest(path) != provenance.PINS[pin]:
            raise ValueError(f"Unreviewed {label}: SHA-256 differs from the existing BAR provenance pin")
    # The retained provenance contract binds this runtime override explicitly.
    required(env, "LD_LIBRARY_PATH", "the qualified QEMU runtime library directory")
    compiler = Path(env.get("AURORAC") or ROOT / "build/aurorac").resolve()
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
    )


def execute(mode, config, env):
    out = config["output"]
    qemu, data = config["qemu"], config["data"]
    code, clean = config["code"], config["clean"]
    events, coverage = config["events"], config["coverage"]
    shutil.copytree(ROOT / "build/uefi/esp", out / "esp")
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
        shutil.copy2(ROOT / "build/uefi" / name, out / name)
        files[key] = record(out / name)
    files["loader"] = record(out / "esp/EFI/BOOT/BOOTX64.EFI")
    argv = [str(qemu), "-L", str(data), "-machine", "q35", "-accel", "tcg", "-cpu", "qemu64", "-smp", "1", "-m", "128M"]
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
        argv += [
            "-drive",
            f"if=pflash,format=raw,unit=0,file={code},readonly=on",
            "-drive",
            f"if=pflash,format=raw,unit=1,file={out}/vars-runtime.fd",
        ]
    else:
        argv += ["-bios", str(code)]
    argv += [
        "-drive",
        f"format=raw,file=fat:ro:{out}/esp,snapshot=on",
        "-device",
        "nvme,serial=AURORA_READ_ONLY,bus=pcie.0,addr=02.0",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "stdio",
        "-monitor",
        "none",
        "-no-reboot",
        "-trace",
        f"events={events},file={out}/trace.log",
        "-chardev",
        f"file,id=firmware,path={out}/firmware.log",
        "-device",
        "isa-debugcon,iobase=0x402,chardev=firmware",
        "-device",
        "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
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
    if clean:
        invocation["firmware_source_revision"] = module("bar-provenance").REVISION
    (out / "invocation-start.json").write_text(json.dumps(invocation, indent=2) + "\n")
    with (out / "serial.log").open("w") as log:
        try:
            status = subprocess.run(
                argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=60
            ).returncode
        except subprocess.TimeoutExpired:
            status = 124
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
    module("bar-provenance").validate(out / "receipt.json")


def run(mode, output):
    env = os.environ.copy()
    config = preflight(mode, output, env)
    out = config["output"]
    out.mkdir(parents=True, exist_ok=False)
    build_started = False
    failure = None
    try:
        with (out / "build.log").open("w") as log:
            process = subprocess.Popen(
                [ROOT / "scripts/kernel-uefi-build.sh"],
                cwd=ROOT,
                env=dict(env, UEFI_MODE=mode),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            build_started = True
            try:
                status = process.wait()
            except BaseException:
                # An interrupted build must not race the normal-image restore.
                # The builder and its descendants own this new process group.
                if process.poll() is None:
                    # An unreaped child retains its PID even if it exits before
                    # killpg. Never signal a PID already released by wait().
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
                raise
            if status:
                raise subprocess.CalledProcessError(status, process.args)
        execute(mode, config, env)
    except BaseException as error:
        failure = error
        raise
    finally:
        if build_started:
            try:
                with (out / "restore.log").open("w") as log:
                    subprocess.run(
                        [ROOT / "scripts/kernel-uefi-build.sh"],
                        cwd=ROOT,
                        env=dict(env, UEFI_MODE="normal"),
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
            except (OSError, subprocess.SubprocessError) as error:
                if failure is None:
                    raise
                print(f"FAIL: normal-image restoration also failed: {error}; see {out}/restore.log", file=sys.stderr)
    print(f"PASS: actual cold BAR gate {mode}; receipt {out}/receipt.json; normal image restored")


def interrupted(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--output", required=True, help="fresh, absent receipt directory")
    args = parser.parse_args()
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    try:
        run(args.mode, Path(args.output))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"FAIL: BAR runner: {error}", file=sys.stderr)
        return 2
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    return 0


if __name__ == "__main__":
    sys.exit(main())

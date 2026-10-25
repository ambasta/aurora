#!/usr/bin/env python3
"""Prebuilt native console PTY gate, followed by actual normal restoration.

The image and stack checks ran when the console profile was built. The normal
restoration uses the same configured native build.
"""

from pathlib import Path
import argparse
import errno
import json
import io
import os
import pty
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tty

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from kernel_profiles import canonical_profile, fixture_cases, fw_cfg_fixture
from kernel_uefi_oracle import loader_selection
import qemu_transport as transport

BUILD = None


def need(value, message):
    if not value:
        raise ValueError(message)


def run_bounded(argv, timeout, env=None):
    stdout, stderr = io.BytesIO(), io.BytesIO()
    status = transport.run_logged(argv, stdout, stderr=stderr, cwd=ROOT, env=env, timeout=timeout, timeout_status=False)
    return subprocess.CompletedProcess(argv, status, stdout.getvalue(), stderr.getvalue())


# Service faults are boot-selected device-fixture rows, each with its own oracle.
FAULT_MODES = fixture_cases("device-fixture", "console_service_")


def validate_fault(transcript, status, mode, sent):
    need(mode in FAULT_MODES, "Unknown console service fault")
    text = transcript.replace(b"\r", b"")
    # The loader reads the row once, before the trusted bootstrap and any timer,
    # IDT or UART input state, and echoes it before any other record.
    need(b"AURORA_FIXTURE_READY" not in text, "Unexpected serial fixture selector")
    text = loader_selection(text.decode("latin-1"), mode).encode("latin-1")
    bootstrap = b"AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"
    need(
        bootstrap + b"AURORA_UEFI_CONSOLE_TIMER_READY:" in text,
        "Missing or misplaced trusted bootstrap before the console service",
    )
    need(status == 35, "Fault did not exit fail-closed through the QEMU device")
    need(b"AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n" in text, "Fault preceded successful trusted bootstrap")
    need(
        b"AURORA_CONSOLE_EXIT" not in text and b"AURORA_UEFI_CONSOLE_QUIET:" not in text,
        "Fault falsely completed normally",
    )
    marker = b"AURORA_UEFI_CONSOLE_TIMER_READY: polling_count=1250000 uart_irq=0\n"
    pieces = text.split(marker)
    need(len(pieces) == 2, "Missing or repeated timer setup marker")
    tail = pieces[1]
    ready = b"AURORA_CONSOLE_READY: UEFI, ASCII, 64-byte lines\naurora> "
    rejected = b"AURORA_UEFI_CONSOLE_FAIL: console service authority\n"
    if mode == "console-service-stale":
        need(tail == rejected, "Stale descriptor caused an effect before rejection")
    elif mode == "console-service-reentry":
        need(tail == ready + rejected, "Reentry transmitted a byte, restarted or rejected before its active operation")
    elif mode == "console-service-timeout":
        need(tail == ready[:17], "Timeout retried or exceeded its exact emitted prefix")
    else:
        need(
            sent
            and tail.startswith(ready + b"AURORA_UEFI_EXCEPTION: vector=255 ")
            and tail.endswith(b"AURORA_UEFI_PAYLOAD_FAIL: exception\n"),
            "Noncanonical copied report did not trap before the editor saw its byte",
        )


def fault_guest(mode, work):
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    need(qemu, "QEMU is unavailable")
    selected = subprocess.check_output(
        [
            "bash",
            "-c",
            "source scripts/uefi-firmware.sh; uefi_firmware_select; "
            'printf "%s\\0" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" '
            '"$UEFI_FIRMWARE_VARS" "${UEFI_FIRMWARE_ARGS[@]}"',
        ],
        cwd=ROOT,
    )
    combined, code, variables, *firmware = selected.decode().split("\0")[:-1]
    argv = transport.command(
        qemu,
        os.environ.get("QEMU_DATA", ""),
        firmware=transport.firmware_args(combined, code, variables),
        prefix=fw_cfg_fixture(mode),
        boot=transport.fat_boot(BUILD / "esp"),
    )
    master, slave = pty.openpty()
    tty.setraw(slave)
    transcript = bytearray()
    process = None
    sent = False
    started = time.monotonic()
    try:
        with (work / "guest.stderr").open("wb") as stderr:
            process = transport.start(argv, cwd=ROOT, stdin=slave, stdout=slave, stderr=stderr)
            os.close(slave)
            slave = -1
            while True:
                need(time.monotonic() - started < 30, "Fault guest deadline exceeded")
                ready, _, _ = select.select([master], [], [], 0.05)
                if ready:
                    try:
                        data = os.read(master, 4096)
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
                        data = b""
                    if not data:
                        break
                    transcript.extend(data)
                    need(len(transcript) < 65536, "Fault transcript exceeded bound")
                    if mode == "console-service-report" and not sent and b"aurora> " in transcript:
                        tty.setraw(master)
                        os.write(master, b"x")
                        sent = True
                elif transport.exited(process):
                    break
            status = transport.wait_exit(process, 2)
        validate_fault(bytes(transcript), status, mode, sent)
        return dict(
            exit_status=status, elapsed_seconds=time.monotonic() - started, input_sent=sent, transcript_sha256=None
        )
    finally:
        errors, _, unsettled = transport.finish(process, fds=(master, slave if slave != -1 else None))
        (work / "guest.log").write_bytes(transcript)
        if unsettled:
            raise transport.ChildNotReaped("; ".join(errors))
        need(not errors, "; ".join(errors))


def restore_normal(work, env, result=None, normal_build=None):
    """Boot the selected isolated normal image and require this attempt's logs."""
    if normal_build is None:
        selected = run_bounded(
            [ROOT / "scripts/kernel-image.sh", "uefi", "normal"],
            env=env,
            timeout=180,
        )
        (work / "restoration-build.stdout").write_bytes(selected.stdout)
        (work / "restoration-build.stderr").write_bytes(selected.stderr)
        need(selected.returncode == 0, "Could not select the native normal restoration image")
        paths = selected.stdout.decode().splitlines()
        need(len(paths) == 1, "Ambiguous native normal image directory")
        directory = Path(paths[0])
    else:
        directory = normal_build
    need(
        directory.is_absolute()
        and directory.is_dir()
        and directory.resolve(strict=True) == directory
        and directory.parts[-3:] == ("kernel-images", "uefi", "normal"),
        "Unexpected native normal image directory",
    )
    names = ("normal.log",)
    outputs = work / "normal-restoration" if normal_build is not None else directory
    before = {}
    for name in names:
        path = outputs / name
        need(not path.is_symlink(), "Symlinked normal restoration output")
        before[name] = path.stat() if path.exists() else None
    # Pin the same configured build when the smoke wrapper selects its image.
    env = dict(env, MESON_BUILD_DIR=str(directory.parents[2]))
    command = ["bash", ROOT / "scripts/kernel-uefi-smoke.sh"]
    if normal_build is not None:
        command += ["--run-only", str(directory), "--output-dir", str(outputs)]
    restored = run_bounded([*command, "normal"], env=env, timeout=180)
    (work / "restoration.stdout").write_bytes(restored.stdout)
    (work / "restoration.stderr").write_bytes(restored.stderr)
    restoration = dict(
        exit_status=restored.returncode,
        image_directory=str(directory),
    )
    if result is not None:
        result["restoration"] = restoration
    need(restored.returncode == 0, "Actual normal-image restoration failed")
    for name in names:
        path = outputs / name
        need(path.is_file() and not path.is_symlink(), "Missing normal restoration output: " + name)
        current = path.stat()
        old = before[name]
        need(
            old is None
            or (current.st_ino, current.st_mtime_ns, current.st_ctime_ns)
            != (old.st_ino, old.st_mtime_ns, old.st_ctime_ns),
            "Stale normal restoration output: " + name,
        )
        shutil.copy2(path, work / ("restoration-" + name))
    return restoration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("console",) + FAULT_MODES, default="console")
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument(
        "--normal-build-dir", type=Path, help="prebuilt normal profile for private run-only restoration"
    )
    args = parser.parse_args()
    global BUILD
    BUILD = args.build_dir.resolve(strict=True)
    profile = canonical_profile("uefi", args.mode)
    need(
        BUILD.parts[-3:] == ("kernel-images", "uefi", profile),
        "Expected the selected native console profile directory",
    )
    need(
        not os.environ.get("AURORA_TEST_CONTEXT") and not os.environ.get("UEFI_MODE"),
        "Unset inherited test/profile controls",
    )
    need(shutil.which(os.environ.get("QEMU", "qemu-system-x86_64")), "QEMU unavailable")
    evidence_root = ROOT / "build"
    evidence_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=args.mode + "-qualified-", dir=evidence_root))
    result = dict(mode=args.mode, status="failed")
    primary_error = None
    try:
        if args.mode == "console":
            pty_output = work / "console-pty"
            replay = run_bounded(
                [
                    sys.executable,
                    "-B",
                    ROOT / "tests/kernel-console-pty.py",
                    "--uefi",
                    "--build-dir",
                    BUILD,
                    "--output-dir",
                    pty_output,
                ],
                timeout=40,
            )
            (work / "driver.stdout").write_bytes(replay.stdout)
            (work / "driver.stderr").write_bytes(replay.stderr)
            for name in (
                "kernel-console-pty.log",
                "kernel-console-pty.metrics.json",
                "kernel-console-pty.stderr",
            ):
                if (pty_output / name).exists():
                    shutil.copy2(pty_output / name, work / name)
            need(replay.returncode == 0, "Normal console PTY failed: " + replay.stderr.decode(errors="replace"))
            result["guest"] = json.loads((work / "kernel-console-pty.metrics.json").read_text())
        else:
            result["guest"] = fault_guest(args.mode, work)
    except BaseException as error:
        primary_error = error
        result["guest_error"] = str(error)
    finally:
        # A qualified attempt owns restoration even when its PTY gate failed.
        # This normal-profile command includes an actual validated QEMU boot.
        env = dict(os.environ, MESON_BUILD_DIR=str(BUILD.parents[2]))
        try:
            if isinstance(primary_error, transport.ChildNotReaped):
                raise primary_error
            restore_normal(work, env, result, args.normal_build_dir)
            if primary_error is None:
                result["status"] = "passed"
        except BaseException as error:
            result["restoration_error"] = str(error)
            if primary_error is None:
                primary_error = error
        (work / "qualification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if primary_error is not None:
        raise primary_error
    print("PASS prebuilt " + args.mode + " PTY and actual normal restoration: " + str(work))


def terminate(_number, _frame):
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()

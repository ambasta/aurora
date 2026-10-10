#!/usr/bin/env python3
"""Prebuilt native console PTY gate, followed by actual normal restoration.

The selected console image must pass automatic artifact admission before a guest
starts. The normal restoration uses the same configured native build.
"""

from pathlib import Path
import argparse
import errno
import json
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
import kernel_console_service_admission as admission
import kernel_uefi_console_clock as clock


def need(value, message):
    if not value:
        raise ValueError(message)


def run_bounded(argv, timeout, env=None):
    process = subprocess.Popen(
        argv, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        raise
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def validate_fault(transcript, status, mode, sent):
    text = transcript.replace(b"\r", b"")
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
    argv = [qemu]
    if os.environ.get("QEMU_DATA"):
        argv += ["-L", os.environ["QEMU_DATA"]]
    argv += [
        "-machine",
        "q35",
        "-accel",
        "tcg",
        "-cpu",
        "qemu64",
        "-smp",
        "1",
        "-m",
        "128M",
        *firmware,
        "-drive",
        "format=raw,file=fat:ro:" + str(admission.BUILD / "esp") + ",snapshot=on",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "stdio",
        "-monitor",
        "none",
        "-no-reboot",
        "-device",
        "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
    recipe = clock.receipt(
        argv, qemu, combined, code, variables, os.environ.get("QEMU_DATA", ""), esp=str(admission.BUILD / "esp")
    )
    recipe.update(timeout_argv=None, test_supervision="private PTY, 30-second deadline")
    (work / "clock.json").write_text(json.dumps(recipe, indent=2) + "\n")
    master, slave = pty.openpty()
    tty.setraw(slave)
    transcript = bytearray()
    process = None
    sent = False
    started = time.monotonic()
    try:
        with (work / "guest.stderr").open("wb") as stderr:
            process = subprocess.Popen(argv, cwd=ROOT, stdin=slave, stdout=slave, stderr=stderr, start_new_session=True)
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
                elif process.poll() is not None:
                    break
            status = process.wait(timeout=2)
        validate_fault(bytes(transcript), status, mode, sent)
        return dict(
            exit_status=status, elapsed_seconds=time.monotonic() - started, input_sent=sent, transcript_sha256=None
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        os.close(master)
        if slave != -1:
            os.close(slave)
        (work / "guest.log").write_bytes(transcript)


def restore_normal(work, env, result=None):
    """Boot the selected isolated normal image and require this attempt's logs."""
    selected = run_bounded(
        [
            sys.executable,
            "-B",
            ROOT / "scripts/meson_test.py",
            "--kernel",
            "uefi",
            "--profile",
            "normal",
            "--print-image-dir",
        ],
        env=env,
        timeout=180,
    )
    (work / "restoration-build.stdout").write_bytes(selected.stdout)
    (work / "restoration-build.stderr").write_bytes(selected.stderr)
    need(selected.returncode == 0, "Could not select the native normal restoration image")
    paths = selected.stdout.decode().splitlines()
    need(len(paths) == 1, "Ambiguous native normal image directory")
    directory = Path(paths[0])
    need(
        directory.is_absolute()
        and directory.is_dir()
        and directory.resolve(strict=True) == directory
        and directory.parts[-3:] == ("kernel-images", "uefi", "normal"),
        "Unexpected native normal image directory",
    )
    names = ("normal.log", "normal.clock.json")
    before = {}
    for name in names:
        path = directory / name
        need(not path.is_symlink(), "Symlinked normal restoration output")
        before[name] = path.stat() if path.exists() else None
    # Pin the same configured build when the smoke wrapper selects its image.
    env = dict(env, MESON_BUILD_DIR=str(directory.parents[2]))
    restored = run_bounded(["bash", ROOT / "scripts/kernel-uefi-smoke.sh", "normal"], env=env, timeout=180)
    (work / "restoration.stdout").write_bytes(restored.stdout)
    (work / "restoration.stderr").write_bytes(restored.stderr)
    restoration = dict(
        exit_status=restored.returncode,
        image_directory=str(directory),
        output_sha256=admission.digest(work / "restoration.stdout"),
    )
    if result is not None:
        result["restoration"] = restoration
    need(restored.returncode == 0, "Actual normal-image restoration failed")
    for name in names:
        path = directory / name
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
    parser.add_argument("--mode", choices=admission.MODES, default="console")
    parser.add_argument("--build-dir", type=Path, required=True)
    args = parser.parse_args()
    admission.configure_paths(args.build_dir, ROOT)
    need(
        admission.BUILD.parts[-3:] == ("kernel-images", "uefi", args.mode),
        "Expected the selected native console profile directory",
    )
    need(
        not os.environ.get("AURORA_TEST_CONTEXT") and not os.environ.get("UEFI_MODE"),
        "Unset inherited test/profile controls",
    )
    # Failed preflight must neither start a guest nor modify/restage its image.
    receipt = admission.checked(args.mode)
    need(shutil.which(os.environ.get("QEMU", "qemu-system-x86_64")), "QEMU unavailable")
    evidence_root = ROOT / "build"
    evidence_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=args.mode + "-qualified-", dir=evidence_root))
    shutil.copy2(admission.RECEIPT, work / "admission.json")
    for path in admission.build_files():
        target = work / "image" / path.relative_to(admission.BUILD)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    result = dict(
        schema="aurora-native-console-qualification-v1",
        mode=args.mode,
        status="failed",
        admission_sha256=admission.digest(admission.RECEIPT),
    )
    primary_error = None
    try:
        if args.mode == "console":
            replay = run_bounded(
                [sys.executable, "-B", ROOT / "tests/kernel-console-pty.py", "--uefi", "--build-dir", admission.BUILD],
                timeout=40,
            )
            (work / "driver.stdout").write_bytes(replay.stdout)
            (work / "driver.stderr").write_bytes(replay.stderr)
            for name in (
                "kernel-console-pty.log",
                "kernel-console-pty.metrics.json",
                "kernel-console-pty.stderr",
                "console-pty.clock.json",
            ):
                if (admission.BUILD / name).exists():
                    shutil.copy2(admission.BUILD / name, work / name)
            need(replay.returncode == 0, "Normal console PTY failed: " + replay.stderr.decode(errors="replace"))
            result["guest"] = json.loads((work / "kernel-console-pty.metrics.json").read_text())
        else:
            result["guest"] = fault_guest(args.mode, work)
            result["guest"]["transcript_sha256"] = admission.digest(work / "guest.log")
        need(
            admission.checked(args.mode) == receipt
            and admission.digest(admission.RECEIPT) == result["admission_sha256"],
            "Admitted image or report changed during guest execution",
        )
    except BaseException as error:
        primary_error = error
        result["guest_error"] = str(error)
    finally:
        # A qualified attempt owns restoration even when its PTY gate failed.
        # This normal-profile command includes an actual validated QEMU boot.
        env = dict(os.environ, MESON_BUILD_DIR=str(admission.BUILD.parents[2]))
        try:
            restore_normal(work, env, result)
            if primary_error is None:
                result["status"] = "passed"
        except BaseException as error:
            result["restoration_error"] = str(error)
            if primary_error is None:
                primary_error = error
        (work / "qualification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if primary_error is not None:
        raise primary_error
    print("PASS admitted prebuilt " + args.mode + " PTY and actual normal restoration: " + str(work))


def terminate(_number, _frame):
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()

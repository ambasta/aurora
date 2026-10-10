#!/usr/bin/env python3
"""Review-pinned prebuilt first-change PTY gate, then actual normal restoration.

This path never rebuilds the reviewed console image. Routine public console
commands instead run their reproducible automated image/stack checks.
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
        "format=raw,file=fat:ro:build/uefi/esp,snapshot=on",
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
    recipe = clock.receipt(argv, qemu, combined, code, variables, os.environ.get("QEMU_DATA", ""))
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=admission.MODES, default="console")
    args = parser.parse_args()
    need(
        not os.environ.get("AURORA_TEST_CONTEXT") and not os.environ.get("UEFI_MODE"),
        "Unset inherited test/profile controls",
    )
    # Failed preflight must neither start a guest nor modify/restage its image.
    receipt = admission.reviewed(args.mode)
    need(shutil.which(os.environ.get("QEMU", "qemu-system-x86_64")), "QEMU unavailable")
    work = Path(tempfile.mkdtemp(prefix=args.mode + "-qualified-", dir=ROOT / "build"))
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
        compiler=receipt["build"]["compiler"],
    )
    primary_error = None
    try:
        if args.mode == "console":
            replay = run_bounded([sys.executable, "-B", ROOT / "tests/kernel-console-pty.py", "--uefi"], timeout=40)
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
        admission.reviewed(args.mode)  # Prebuilt source/image stayed exact through execution.
    except BaseException as error:
        primary_error = error
        result["guest_error"] = str(error)
    finally:
        # A qualified attempt owns restoration even when its PTY gate failed.
        # This normal-profile command includes an actual validated QEMU boot.
        env = os.environ.copy()
        env.pop("CONSOLE_SERVICE_REVIEW_SHA256", None)
        try:
            restored = run_bounded(
                ["bash", ROOT / "scripts/kernel-uefi-smoke.sh", "--shared-normal", "normal"], env=env, timeout=180
            )
            (work / "restoration.stdout").write_bytes(restored.stdout)
            (work / "restoration.stderr").write_bytes(restored.stderr)
            result["restoration"] = dict(
                exit_status=restored.returncode, output_sha256=admission.digest(work / "restoration.stdout")
            )
            need(restored.returncode == 0, "Actual normal-image restoration failed")
            for name in ("normal.log", "normal.clock.json"):
                if (admission.BUILD / name).exists():
                    shutil.copy2(admission.BUILD / name, work / ("restoration-" + name))
            if primary_error is None:
                result["status"] = "passed"
        except BaseException as error:
            result["restoration_error"] = str(error)
            if primary_error is None:
                primary_error = error
        (work / "qualification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if primary_error is not None:
        raise primary_error
    print("PASS reviewed prebuilt " + args.mode + " PTY and actual normal restoration: " + str(work))


def terminate(_number, _frame):
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()

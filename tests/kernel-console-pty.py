#!/usr/bin/env python3
"""Real QEMU console acceptance through a fresh private PTY, within 30 seconds."""

from pathlib import Path
import importlib.util
import errno
import json
import os
import pty
import select
import signal
import shutil
import subprocess
import time
import sys
import re
import tty

ROOT = Path(__file__).resolve().parents[1]


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    need(sys.argv[1:] in ([], ["--uefi"]), "Expected no argument or --uefi")
    uefi = sys.argv[1:] == ["--uefi"]
    output = ROOT / ("build/uefi" if uefi else "build")
    metrics = {"platform": "uefi" if uefi else "bios", "latencies_ms": [], "clock": "tcg-original-clock"}
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    need(qemu, "QEMU is unavailable; console boot is not verified")
    command = [qemu]
    if os.environ.get("QEMU_DATA"):
        command += ["-L", os.environ["QEMU_DATA"]]
    if uefi:
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
        firmware, code, variables, *firmware_args = selected.decode().split("\0")[:-1]
        command += [
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
            *firmware_args,
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
        sys.path.insert(0, str(ROOT / "scripts"))
        import kernel_uefi_console_clock

        receipt = kernel_uefi_console_clock.receipt(
            command, qemu, firmware, code, variables, os.environ.get("QEMU_DATA", "")
        )
        receipt.update(timeout_argv=None, test_supervision="private PTY, 30-second deadline")
        (output / "console-pty.clock.json").write_text(json.dumps(receipt, indent=2) + "\n")
    else:
        command += [
            "-machine",
            "pc",
            "-accel",
            "tcg",
            "-cpu",
            "qemu64",
            "-smp",
            "1",
            "-m",
            "32M",
            "-drive",
            "file=build/aurora.img,format=raw,if=ide,snapshot=on",
            "-boot",
            "c",
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
    master, slave = pty.openpty()
    tty.setraw(slave)
    deadline = time.monotonic() + 30
    transcript = bytearray()
    process = None
    errors = output / "kernel-console-pty.stderr"
    try:
        with errors.open("wb") as stderr:
            process = subprocess.Popen(
                command, cwd=ROOT, stdin=slave, stdout=slave, stderr=stderr, start_new_session=True
            )
            os.close(slave)
            slave = -1

            def receive_until(marker, start=0):
                while marker not in transcript[start:]:
                    remaining = deadline - time.monotonic()
                    need(remaining > 0, "console timed out waiting for " + repr(marker))
                    ready, _, _ = select.select([master], [], [], min(remaining, 0.1))
                    if ready:
                        try:
                            data = os.read(master, 4096)
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                            data = b""
                        need(data, "QEMU closed its PTY before the expected console response")
                        transcript.extend(data)
                        need(len(transcript) < 65536, "console output exceeded its test bound")
                    else:
                        if process.poll() is not None:
                            pending, _, _ = select.select([master], [], [], 0)
                            need(pending, "QEMU exited before the expected console response")

            def exchange(payload, expected, burst=False, recovery=b""):
                begin = len(transcript)
                if burst:
                    os.write(master, payload)
                    sent = time.monotonic()
                else:
                    for byte in payload:
                        need(time.monotonic() < deadline, "console input deadline exceeded")
                        os.write(master, bytes([byte]))
                        sent = time.monotonic()
                        time.sleep(0.003)
                if recovery:
                    time.sleep(0.15)
                    os.write(master, recovery)
                    sent = time.monotonic()
                receive_until(expected, begin)
                receive_until(b"aurora> ", begin)
                latency = (time.monotonic() - sent) * 1000
                metrics["latencies_ms"].append({"burst": burst, "after_last_send_ms": latency})
                need(latency < (1000 if burst else 250), "console response latency exceeded bound")
                return bytes(transcript[begin:])

            receive_until(b"aurora> ")
            startup = bytes(transcript).decode("ascii")
            # QEMU's stdio initialization can re-enable terminal ONLCR. Preserve
            # raw startup evidence, then reset our private PTY before input.
            tty.setraw(master)
            if uefi:
                spec = importlib.util.spec_from_file_location("kernel_acpi_smoke", ROOT / "tests/kernel-acpi-smoke.py")
                smoke = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(smoke)
                prefix = startup.split("AURORA_UEFI_CONSOLE_TIMER_READY:")[0].replace("\r", "")
                smoke.validate(33, prefix, "acpi")
                need(
                    "AURORA_UEFI_CONSOLE_TIMER_READY: polling_count=1250000 uart_irq=0" in startup,
                    "Missing exact timer polling admission",
                )
                need(
                    "AURORA_UEFI_USER_" not in startup and "AURORA_UEFI_BUDGET_" not in startup,
                    "Console ran user service fixtures",
                )
            else:
                spec = importlib.util.spec_from_file_location("kernel_smoke", ROOT / "tests/kernel-smoke.py")
                smoke = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(smoke)
                # Validate the complete pre-console self-test transcript separately.
                smoke.validate(
                    33,
                    startup.split("AURORA_CONSOLE_READY:")[0].replace("\r", ""),
                    json.loads((ROOT / "build/user-metadata.json").read_text()),
                )
            if uefi:
                # With the fourteen-byte trigger and UART IRQs disabled, even
                # one byte must become visible to polling without waiting for
                # a full FIFO or a UART receive-timeout interrupt.
                exchange(b"\n", b"\r\naurora> ")
                begin = len(transcript)
                sent = time.monotonic()
                os.write(master, b"h")
                receive_until(b"h", begin)
                latency = (time.monotonic() - sent) * 1000
                metrics["latencies_ms"].append({"partial_echo": True, "after_last_send_ms": latency})
                need(latency < 250, "short FIFO input latency exceeded bound")
                time.sleep(0.05)
                exchange(b"elp\n", b"help    Show commands\r\n")
            exchange(b"help\r\n", b"help    Show commands\r\n")
            exchange(b"statuX\x7fs\n", b"status: boot self-tests passed;")
            exchange(b"helx\x08p\r", b"help    Show commands\r\n")
            exchange(b"\nHELP\n", b"Unknown command.")
            exchange(b"statusx\n", b"Unknown command.")
            exchange(b"x" * 64 + b"\n", b"Unknown command.")
            exchange(b"x" * 65 + b"\x08exit\r\n", b"Line rejected:")
            exchange(b"\x1bexit\n", b"Line rejected:")
            exchange(b"\xffstatus\n", b"Line rejected:")
            exchange(b"\x00help\n", b"Line rejected:")
            exchange(b"status\r\n", b"status: boot self-tests passed;")
            if uefi:
                # No pasted delimiter: an overrun may discard it. A later explicit
                # delimiter must reject the affected line before command recovery.
                exchange(b"z" * 256, b"Line rejected:", burst=True, recovery=b"\n")
                exchange(b"\nstatus\n", b"status: boot self-tests passed;")
            # Linux host check: idle QEMU should sleep, rather than spend a CPU
            # polling the UART. This is a bounded emulator observation only.
            stat = Path(f"/proc/{process.pid}/stat")
            before = stat.read_text().rsplit(")", 1)[1].split()
            idle_start = time.monotonic()
            time.sleep(0.6)
            idle_wall = time.monotonic() - idle_start
            after = stat.read_text().rsplit(")", 1)[1].split()
            ticks = sum(int(after[index]) - int(before[index]) for index in (11, 12))
            metrics.update(
                idle_wall_seconds=idle_wall,
                idle_cpu_seconds=ticks / os.sysconf("SC_CLK_TCK"),
                polling_count=1250000 if uefi else None,
            )
            need(ticks <= os.sysconf("SC_CLK_TCK") * 0.2 + 1, "console consumed excessive idle CPU")
            begin = len(transcript)
            os.write(master, b"exit\n")
            receive_until(b"AURORA_CONSOLE_EXIT\r\n", begin)
            need(process.wait(timeout=3) == 33, "console exit command did not close QEMU cleanly")
            text = bytes(transcript).decode("ascii")
            need(text.count("AURORA_CONSOLE_READY:") == 1, "console restarted unexpectedly")
            need(text.count("AURORA_CONSOLE_EXIT") == 1, "console exit was missing or duplicated")
            need(text.count("Line rejected:") == (5 if uefi else 4), "incorrect rejected-line count")
            need(
                "AURORA_BOOT_FAIL" not in text and "AURORA_EXCEPTION_FATAL" not in text,
                "kernel failed during the console session",
            )
            if uefi:
                matches = re.findall(
                    r"AURORA_UEFI_CONSOLE_QUIET: wakes=(\d+) "
                    r"timer=masked isr=0 irr=0 uart_irq=0",
                    text,
                )
                need(len(matches) == 1 and 0 < int(matches[0]) < 100000, "Missing quiescent timer shutdown")
                need("AURORA_UEFI_CONSOLE_FAIL" not in text, "Console failed closed")
                metrics["wakes"] = int(matches[0])
            metrics["exit_status"] = process.returncode
            print(
                "PASS: "
                + metrics["platform"].upper()
                + " console PTY, editing, rejection, recovery, prompt latency, idle wait and exit"
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
        (output / "kernel-console-pty.log").write_bytes(transcript)
        (output / "kernel-console-pty.metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")


def terminate(_signal_number, _frame):
    # SIGTERM must unwind main's finally block: QEMU owns a separate session
    # and would otherwise outlive its PTY driver while the wrapper restores.
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()

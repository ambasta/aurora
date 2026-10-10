#!/usr/bin/env python3
"""Real QEMU console acceptance through a fresh private PTY, within 30 seconds."""

from pathlib import Path
import argparse
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
sys.path.insert(0, str(ROOT / "scripts"))
import qemu_transport as transport


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uefi", action="store_true")
    parser.add_argument("--build-dir", type=Path)
    args = parser.parse_args()
    uefi = args.uefi
    output = ROOT / (args.build_dir or ("build/uefi" if uefi else "build"))
    metrics = {"platform": "uefi" if uefi else "bios", "latencies_ms": [], "clock": "tcg-original-clock"}
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    need(qemu, "QEMU is unavailable; console boot is not verified")
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
        command = transport.profile_command(
            "uefi",
            "console",
            qemu,
            output / "esp",
            os.environ.get("QEMU_DATA", ""),
            firmware=firmware,
            code=code,
            variables=variables,
        )
        sys.path.insert(0, str(ROOT / "scripts"))
        import kernel_uefi_console_clock

        receipt = kernel_uefi_console_clock.receipt(
            command, qemu, firmware, code, variables, os.environ.get("QEMU_DATA", ""), esp=str(output / "esp")
        )
        receipt.update(timeout_argv=None, test_supervision="private PTY, 30-second deadline")
        (output / "console-pty.clock.json").write_text(json.dumps(receipt, indent=2) + "\n")
    else:
        command = transport.profile_command(
            "bios", "console", qemu, output / "aurora.img", os.environ.get("QEMU_DATA", ""), snapshot=True
        )
    master, slave = pty.openpty()
    tty.setraw(slave)
    deadline = time.monotonic() + 30
    transcript = bytearray()
    process = None
    errors = output / "kernel-console-pty.stderr"
    try:
        with errors.open("wb") as stderr:
            process = transport.start(command, cwd=ROOT, stdin=slave, stdout=slave, stderr=stderr)
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
                        if transport.exited(process):
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
                # The named workspace and the legacy note belong only to the
                # Aurora UEFI consumer, not the BIOS diagnostic adapter.
                exchange(b"ls\n", b"\r\nfiles: empty (RAM-only).\r\n")
                exchange(b"write note separate\n", b"note: RAM-only; lost when session exits.")
                exchange(b"write todo Ship Aurora\n", b"wrote todo: 11 bytes")
                exchange(b"write ideas Safer drivers\n", b"wrote ideas: 13 bytes")
                exchange(b"cat todo\n", b"\r\nShip Aurora\r\n")
                exchange(b"write todo Done\n", b"wrote todo: 4 bytes")
                exchange(b"cat todo\n", b"\r\nDone\r\n")
                exchange(b"write a \n", b"wrote a: 0 bytes")
                exchange(b"write b \n", b"wrote b: 0 bytes")
                exchange(b"write c full\n", b"files: full (4 files).")
                exchange(b"cat todo\n", b"\r\nDone\r\n")
                exchange(b"rm ideas\n", b"files: removed (RAM-only).")
                exchange(b"write c reused\n", b"wrote c: 6 bytes")
                exchange(b"ls\n", b"\r\nfiles: todo c a b\r\n")
                exchange(b"rm note\n", b"files: note is reserved.")
                exchange(b"cat note\n", b"\r\nseparate\r\n")
                exchange(b"rm todo\n", b"files: removed (RAM-only).")
                exchange(b"cat todo\n", b"files: not found (RAM-only).")
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
            if uefi:
                receive_until(b" timer=masked isr=0 irr=0 uart_irq=0\r\n", begin)
            need(transport.wait_exit(process, 3) == 33, "console exit command did not close QEMU cleanly")
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
    finally:
        cleanup_errors, _, unsettled = transport.finish(process, fds=(master, slave if slave != -1 else None))
        (output / "kernel-console-pty.log").write_bytes(transcript)
        (output / "kernel-console-pty.metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        if unsettled:
            raise transport.ChildNotReaped("; ".join(cleanup_errors))
        need(not cleanup_errors, "; ".join(cleanup_errors))
    print(
        "PASS: "
        + metrics["platform"].upper()
        + " console PTY, editing, rejection, recovery, prompt latency, idle wait and exit"
    )


def terminate(_signal_number, _frame):
    # SIGTERM must unwind main's finally block: QEMU owns a separate session
    # and would otherwise outlive its PTY driver while the wrapper restores.
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    main()

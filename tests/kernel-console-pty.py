#!/usr/bin/env python3
"""Real QEMU console acceptance through a fresh private PTY, within 30 seconds."""
from pathlib import Path
import importlib.util
import errno
import json
import os
import pty
import select
import shutil
import subprocess
import time
import tty

ROOT = Path(__file__).resolve().parents[1]


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    need(qemu, "QEMU is unavailable; console boot is not verified")
    command = [qemu]
    if os.environ.get("QEMU_DATA"):
        command += ["-L", os.environ["QEMU_DATA"]]
    command += ["-machine", "pc", "-accel", "tcg", "-cpu", "qemu64", "-smp", "1", "-m", "32M",
                "-drive", "file=build/aurora.img,format=raw,if=ide,snapshot=on", "-boot", "c",
                "-nic", "none", "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot",
                "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    master, slave = pty.openpty()
    tty.setraw(slave)
    deadline = time.monotonic() + 30
    transcript = bytearray()
    process = None
    errors = ROOT / "build/kernel-console-pty.stderr"
    try:
        with errors.open("wb") as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdin=slave, stdout=slave, stderr=stderr,
                                       start_new_session=True)
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

            def exchange(payload, expected):
                begin = len(transcript)
                for byte in payload:
                    need(time.monotonic() < deadline, "console input deadline exceeded")
                    os.write(master, bytes([byte]))
                    time.sleep(0.003)
                receive_until(expected, begin)
                receive_until(b"aurora> ", begin)
                return bytes(transcript[begin:])

            receive_until(b"aurora> ")
            startup = bytes(transcript).decode("ascii")
            # QEMU's stdio initialization can re-enable terminal ONLCR. Preserve
            # raw startup evidence, then reset our private PTY before input.
            tty.setraw(master)
            spec = importlib.util.spec_from_file_location("kernel_smoke", ROOT / "tests/kernel-smoke.py")
            smoke = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(smoke)
            # Validate the complete pre-console self-test transcript separately.
            smoke.validate(33, startup.split("AURORA_CONSOLE_READY:")[0].replace("\r", ""),
                           json.loads((ROOT / "build/user-metadata.json").read_text()))
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
            # Linux host check: idle QEMU should sleep, rather than spend a CPU
            # polling the UART. This is a bounded emulator observation only.
            stat = Path(f"/proc/{process.pid}/stat")
            before = stat.read_text().rsplit(")", 1)[1].split()
            time.sleep(0.6)
            after = stat.read_text().rsplit(")", 1)[1].split()
            ticks = sum(int(after[index]) - int(before[index]) for index in (11, 12))
            need(ticks <= os.sysconf("SC_CLK_TCK") * 0.2 + 1, "console consumed excessive idle CPU")
            begin = len(transcript)
            os.write(master, b"exit\n")
            receive_until(b"AURORA_CONSOLE_EXIT\r\n", begin)
            need(process.wait(timeout=3) == 33, "console exit command did not close QEMU cleanly")
            text = bytes(transcript).decode("ascii")
            need(text.count("AURORA_CONSOLE_READY:") == 1, "console restarted unexpectedly")
            need(text.count("AURORA_CONSOLE_EXIT") == 1, "console exit was missing or duplicated")
            need(text.count("Line rejected:") == 4, "incorrect rejected-line count")
            need("AURORA_BOOT_FAIL" not in text and "AURORA_EXCEPTION_FATAL" not in text,
                 "kernel failed during the console session")
            print("PASS: BIOS console PTY, editing, rejection, recovery, idle wait and exit")
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
        (ROOT / "build/kernel-console-pty.log").write_bytes(transcript)


if __name__ == "__main__":
    main()

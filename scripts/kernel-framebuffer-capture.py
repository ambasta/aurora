#!/usr/bin/env python3
"""Shared framebuffer PTY/QMP capture for the native preview and graphical gates."""

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import time
import tty

import qemu_transport as transport

from framebuffer_capture_oracle import BASE, SIZE, GATE, need, validate_serial, validate_capture
from kernel_profiles import FIXTURE_MODES


def release_byte(mode):
    """'G' releases the normal frame; each fault mode sends its table selector."""
    if mode == "framebuffer":
        return 0x47
    image, value = FIXTURE_MODES[mode]
    need(image == "framebuffer" and value != 0x47, "unknown framebuffer release")
    return value


ROOT = Path(__file__).resolve().parents[1]
MAX_IO = 1024 * 1024


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Channel(transport.Qmp):
    def __init__(self, proc, serial, directory, deadline):
        self.proc, self.serial, self.directory, self.deadline = proc, serial, directory, deadline
        self.serial_bytes = b""
        self.qlog = open(directory / "qmp-transcript.log", "xb", buffering=0)
        self.slog = open(directory / "serial.log", "xb", buffering=0)
        try:
            super().__init__(proc, deadline, self.qlog, timeout=5, log_limit=4 * MAX_IO)
        except BaseException:
            self.close()
            raise

    def stop(self):
        self.command("stop")
        status = self.command("query-status")
        need(status.get("status") == "paused" and status.get("running") is False, "guest not paused")

    def drain_serial(self):
        while select.select([self.serial], [], [], 0)[0]:
            part = os.read(self.serial, 65536)
            need(part, "serial EOF")
            transport.capture_bytes(self.slog, part, len(self.serial_bytes), MAX_IO, "serial output limit")
            self.serial_bytes += part

    def wait_marker(self, terminal=False):
        while True:
            self.drain_serial()
            lines = self.serial_bytes.replace(b"\r", b"").split(b"\n")[:-1]
            if terminal:
                found = any(x.startswith((b"AURORA_DISPLAY_FRAME_COMPLETE:", b"AURORA_DISPLAY_FAIL:")) for x in lines)
            else:
                found = GATE.encode() in lines
            if found:
                return
            need(not transport.exited(self.proc), "premature guest process exit")
            need(not any(b"FAIL" in x or b"EXCEPTION" in x for x in lines), "unexpected guest failure before gate")
            select.select([self.serial], [], [], min(0.1, self.remaining()))

    def capture(self, stem):
        physical = self.directory / (stem + ".bin")
        screenshot = self.directory / (stem + ".ppm")
        need(not physical.exists() and not screenshot.exists(), "stale capture")
        # Address and length are independent immutable fixture constants, never
        # obtained from a negative-case handoff or serial observation.
        response = self.command("human-monitor-command", {"command-line": f'pmemsave 0x{BASE:x} {SIZE} "{physical}"'})
        need(response == "", "physical save failed: " + str(response))
        self.command("screendump", {"filename": str(screenshot)})
        need(
            physical.is_file() and physical.stat().st_size == SIZE and screenshot.is_file(), "missing/truncated capture"
        )
        return physical.read_bytes(), screenshot.read_bytes()

    def close(self):
        self.qlog.close()
        self.slog.close()


def command(pins, roots, esp, serial, qmp=False, firmware_args=None):
    return transport.command(
        pins["qemu"],
        roots.get("data"),
        firmware=firmware_args if firmware_args is not None else ["-bios", str(pins["firmware"])],
        boot=transport.fat_boot(esp),
        peripherals=["-vga", "std"],
        serial=serial,
        extra=["-qmp", "stdio", "-S"] if qmp else [],
    )


def run_case(mode, manifest, pins, roots, env, directory, *, firmware_args=None):
    directory.mkdir()
    proc = channel = None
    master = slave = None
    receipt = {"mode": mode, "status": "started", "clock": "tcg-original-clock"}
    start = time.monotonic()
    try:
        master, slave = os.openpty()
        tty.setraw(slave)
        argv = command(
            pins, roots, manifest["cases"][mode]["esp"], os.ttyname(slave), qmp=True, firmware_args=firmware_args
        )
        receipt["command"] = argv
        with open(directory / "qemu.stderr", "xb") as stderr:
            proc = transport.start(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, env=env, cwd=ROOT, bufsize=0
            )
            channel = Channel(proc, master, directory, start + 90)
            channel.command("cont")
            channel.wait_marker()
            channel.stop()
            channel.drain_serial()
            validate_serial(channel.serial_bytes, mode, gate_only=True)
            baseline, baseline_ppm = channel.capture("baseline")
            # Only the exact reviewed byte for this case is sent, once, while paused.
            release = release_byte(mode)
            need(os.write(master, bytes([release])) == 1, "serial release write failed")
            receipt["release_hex"] = format(release, "02x")
            channel.command("cont")
            channel.wait_marker(terminal=True)
            channel.stop()
            channel.drain_serial()
            after, screenshot = channel.capture("after")
            validate_serial(channel.serial_bytes, mode)
            receipt["observation"] = validate_capture(mode, baseline, after, screenshot, baseline_ppm)
            channel.command("quit")
            transport.wait_exit(proc, 5, expected=0)
            receipt["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        receipt.update(status="failed", error=type(error).__name__ + ": " + str(error))
    finally:
        drains = []
        if channel:
            drains.append(channel.drain_serial)
            if receipt["status"] == "passed":
                drains.append(lambda: validate_serial(channel.serial_bytes, mode))

            def drain_qmp():
                while select.select([proc.stdout], [], [], 0)[0]:
                    part = os.read(proc.stdout.fileno(), 65536)
                    if not part:
                        break
                    channel.qlog.write(part)

            drains.append(drain_qmp)
        errors, _, unsettled = transport.finish(
            proc,
            drains=drains,
            fds=(master, slave),
            streams=([channel.qlog, channel.slog] if channel else []) + ([proc.stdin, proc.stdout] if proc else []),
        )
        if proc:
            receipt["exit_status"] = proc.returncode
        if errors:
            receipt.update(status="failed", cleanup_errors=errors, unsettled=unsettled)
        receipt["elapsed_seconds"] = time.monotonic() - start
        receipt["files"] = {p.name: digest(p) for p in directory.iterdir() if p.is_file()}
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt

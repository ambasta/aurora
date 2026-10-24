#!/usr/bin/env python3
"""Production UEFI guest smoke: both consoles of the one production image.

1. The protected program console's complete PTY oracle
   (tests/kernel-program-console-pty.py) on the production image.
2. One original-clock q35/OVMF/std-VGA guest with QMP: program-console commands
   over serial, whose Console output must equal the reviewed transcript in
   tests/kernel-production-console.json (only whole native diagnostic lines may
   interleave), and the graphical terminal's framebuffer viewport, which must
   equal the real host painter's rendering of that transcript
   (tests/graphical-terminal-host --viewport), in physical memory and in the QMP
   screendump. QEMU's std-VGA identity is pinned by this harness, not by the
   kernel's admission.
3. Fail-closed firmware cases: no display (no GOP) and QEMU's ramfb, whose
   framebuffer lies in firmware-described RAM, must stop in the loader before
   ExitBootServices.
None of these establishes physical-hardware support.
"""

import argparse
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tty

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qemu_transport as transport  # noqa: E402
import importlib.util  # noqa: E402
from framebuffer_capture_oracle import BASE, HEIGHT, PITCH, SIZE, WIDTH, need, parse_ppm, ppm_rgb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/kernel-production-console.json"
_spec = importlib.util.spec_from_file_location("production_capture", ROOT / "scripts/kernel-framebuffer-capture.py")
capture = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = capture
_spec.loader.exec_module(capture)
# The painter's 80x24 cells of 6x9 pixels at (32,32).
VIEW_X, VIEW_Y, VIEW_WIDTH, VIEW_HEIGHT = 32, 32, 480, 216
READY = f"AURORA_GRAPHICAL_TERMINAL_READY: base={BASE} width={WIDTH} height={HEIGHT} pitch={PITCH} format=1"
PROMPT = b"aurora> "


# Firmware framebuffers the loader must refuse, with the exact refusal.
DEVICE_CASES = (
    ("no-display", ["-vga", "none"], "AURORA_UEFI_FAIL: bounded GOP capture"),
    ("ram-framebuffer", ["-vga", "none", "-device", "ramfb"], "AURORA_UEFI_FAIL: framebuffer final map authority"),
)


class Blocked(Exception):
    pass


def golden():
    data = json.loads(GOLDEN.read_text())
    need(set(data) == {"input", "console"}, "transcript golden keys")
    need(all(type(item) is str for item in data["input"] + data["console"]), "transcript golden values")
    return [item.encode("latin-1") for item in data["input"]], "\r\n".join(data["console"]).encode("latin-1")


def console_stream(serial, expected):
    """The Console bytes in serial: expected, with only whole AURORA_ diagnostic lines interleaved."""
    start = serial.find(b"AURORA_PROGRAM_CONSOLE_READY:")
    need(start >= 0 and serial[:start].endswith(b"\n"), "Console ready response")
    actual, wanted = serial[start:].split(b"\r\n"), expected.split(b"\r\n")
    index, skipped = 0, 0
    for line in actual[:-1]:
        if index < len(wanted) - 1 and line == wanted[index]:
            index += 1
        else:
            need(
                line.startswith(b"AURORA_") and line != b"AURORA_CONSOLE_EXIT", "Console output differs: " + repr(line)
            )
            skipped += 1
    need(index == len(wanted) - 1 and actual[-1] == wanted[-1], "Console transcript incomplete or differs")
    return skipped


def viewport(raw):
    return b"".join(
        raw[((VIEW_Y + y) * PITCH + VIEW_X) * 4 : ((VIEW_Y + y) * PITCH + VIEW_X + VIEW_WIDTH) * 4]
        for y in range(VIEW_HEIGHT)
    )


def probe(channel, stem):
    """Pause-time read of only the viewport rows from physical memory."""
    path = channel.directory / (stem + ".bin")
    need(not path.exists(), "stale viewport probe")
    first = BASE + (VIEW_Y * PITCH + VIEW_X) * 4
    size = ((VIEW_HEIGHT - 1) * PITCH + VIEW_WIDTH) * 4
    response = channel.command("human-monitor-command", {"command-line": f'pmemsave {first} {size} "{path}"'})
    need(response == "" and path.is_file() and path.stat().st_size == size, "viewport probe failed")
    raw = path.read_bytes()
    path.unlink()
    return b"".join(raw[y * PITCH * 4 : (y * PITCH + VIEW_WIDTH) * 4] for y in range(VIEW_HEIGHT))


def wait_for(channel, marker, begin):
    while marker not in channel.serial_bytes[begin:]:
        channel.drain_serial()
        need(b"_FAIL" not in channel.serial_bytes and b"EXCEPTION" not in channel.serial_bytes, "guest failure")
        need(not transport.exited(channel.proc), "premature QEMU exit")
        select.select([channel.serial], [], [], min(0.05, channel.remaining()))


def send(channel, data):
    for byte in data:
        need(select.select([], [channel.serial], [], channel.remaining())[1], "PTY write timeout")
        need(os.write(channel.serial, bytes([byte])) == 1, "short PTY input write")
        time.sleep(0.003)


def firmware():
    selected = subprocess.check_output(
        [
            "bash",
            "-c",
            "set -e; source scripts/uefi-firmware.sh; uefi_firmware_select; "
            'printf "%s\\0" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS"',
        ],
        cwd=ROOT,
    )
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    if not qemu:
        raise Blocked("QEMU unavailable")
    return qemu, transport.firmware_args(*selected.decode().split("\0")[:3])


def device_guests(args, directory):
    qemu, firmware_args = firmware()
    for name, devices, refusal in DEVICE_CASES:
        log = directory / (name + ".log")
        argv = transport.command(
            qemu,
            os.environ.get("QEMU_DATA", ""),
            firmware=firmware_args,
            boot=transport.fat_boot(args.build_dir / "esp"),
            peripherals=devices,
        )
        status = transport.run_logged(argv, log, timeout=30)
        lines = log.read_bytes().decode("ascii", "replace").replace("\r\n", "\n").split("\n")
        need(status == 35 and lines.count(refusal) == 1 and lines.count("AURORA_UEFI_ENTRY") == 1, name + " refusal")
        need(not any(line.startswith(("AURORA_UEFI_EXIT_OK", "AURORA_UEFI_PAYLOAD")) for line in lines), name + " exit")
        print("PASS: " + name + " fails closed in the loader: " + refusal)


def screen_guest(args, directory):
    commands, expected = golden()
    stream = directory / "console-expected.bin"
    stream.write_bytes(expected)
    model = directory / "viewport-expected.bin"
    subprocess.run([str(args.renderer), "--viewport", str(stream), str(model)], check=True, timeout=60)
    expected_view = model.read_bytes()
    need(len(expected_view) == VIEW_WIDTH * VIEW_HEIGHT * 4, "host viewport extent")
    qemu, firmware_args = firmware()
    master, slave = os.openpty()
    tty.setraw(slave)
    argv = capture.command(
        {"qemu": qemu},
        {"data": os.environ.get("QEMU_DATA", "")},
        str(args.build_dir / "esp"),
        os.ttyname(slave),
        qmp=True,
        firmware_args=firmware_args,
    )
    proc = channel = None
    record = dict(argv=argv, status="failed")
    try:
        with open(directory / "qemu.stderr", "xb") as stderr:
            proc = transport.start(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, bufsize=0)
        channel = capture.Channel(proc, master, directory, time.monotonic() + 150)
        channel.command("cont")
        wait_for(channel, PROMPT, 0)
        need(channel.serial_bytes.count(READY.encode() + b" columns=80 rows=24\r\n") == 1, "terminal readiness")
        for command in commands:
            begin = len(channel.serial_bytes)
            send(channel, command)
            wait_for(channel, PROMPT, begin)
        channel.drain_serial()
        skipped = console_stream(channel.serial_bytes, expected)
        # Painting follows the serial prompt; sample paused states until the viewport settles.
        for attempt in range(100):
            channel.stop()
            if probe(channel, f"probe-{attempt:03}") == expected_view:
                break
            channel.command("cont")
            time.sleep(0.1)
        else:
            raise ValueError("framebuffer viewport never matched the host painter")
        raw, ppm = channel.capture("terminal")
        need(len(raw) == SIZE and viewport(raw) == expected_view, "physical viewport differs")
        need(parse_ppm(ppm) == ppm_rgb(WIDTH, HEIGHT, PITCH, 1, raw), "physical/screenshot mismatch")
        channel.command("cont")
        begin = len(channel.serial_bytes)
        send(channel, b"exit\r")
        wait_for(channel, b"AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0\r\n", begin)
        need(transport.wait_exit(proc, 10) == 33, "QEMU did not exit cleanly")
        channel.drain_serial()
        need(b"\r\nAURORA_CONSOLE_EXIT\r\n" in channel.serial_bytes[begin:], "Console exit response")
        for path in (directory / "terminal.bin", directory / "terminal.ppm"):
            path.unlink()
        record.update(status="passed", diagnostics=skipped, probes=attempt + 1, exit_status=33)
    finally:
        errors, _, unsettled = transport.finish(
            proc,
            drains=[channel.drain_serial] if channel else [],
            fds=(master, slave),
            streams=([channel.qlog, channel.slog] if channel else []) + ([proc.stdin, proc.stdout] if proc else []),
        )
        record["cleanup_errors"] = errors
        (directory / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
        if unsettled:
            raise transport.ChildNotReaped("; ".join(errors))
        need(not errors, "guest cleanup: " + "; ".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True, help="kernel-images/uefi/production")
    parser.add_argument("--renderer", type=Path, required=True, help="Meson-built tests/graphical-terminal-host")
    args = parser.parse_args()
    args.build_dir = args.build_dir.resolve(strict=True)
    need(args.build_dir.name == "production" and args.renderer.is_file(), "production image and host painter")
    pty_oracle = [sys.executable, "-B", str(ROOT / "tests/kernel-program-console-pty.py")]
    status = subprocess.run(pty_oracle + ["--mode", "program-console", "--build-dir", str(args.build_dir)]).returncode
    if status:
        raise SystemExit(status)
    evidence = ROOT / "build/program-console-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="production-screen-", dir=evidence))
    print("Production screen guest evidence: " + str(directory))
    screen_guest(args, directory)
    print("PASS: production program console commands over serial and its graphical terminal framebuffer")
    device_guests(args, directory)


if __name__ == "__main__":
    try:
        main()
    except Blocked as error:
        print("BLOCKED: production smoke: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (Exception, KeyboardInterrupt) as error:
        raise SystemExit(transport.failure_label(error) + ": production smoke: " + str(error)) from error

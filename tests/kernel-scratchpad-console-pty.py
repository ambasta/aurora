#!/usr/bin/env python3
"""Real-input scratchpad PTY with exact trace validation and bounded supervision."""

import argparse
import errno
import json
import os
from pathlib import Path
import pty
import resource
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
import qemu_transport as transport
import kernel_scratchpad_console_oracle as oracle
from kernel_profiles import canonical_profile

need = oracle.need


def step(command, reply, exchanges=0, effect="local"):
    return dict(command=command, reply=reply, exchanges=exchanges, effect=effect)


def plans(case, payload):
    need(
        type(payload) is str and 1 <= len(payload) <= 32 and all(32 <= ord(c) <= 126 for c in payload),
        "Choose 1..32 printable ASCII payload bytes after building",
    )
    write = lambda value, effect="normal", reply="saved": step(
        "put" + (" " + value if value else ""), reply, len(value) + 2, effect
    )
    append = lambda value, effect="normal", reply="saved": step(
        "append" + (" " + value if value else ""), reply, 1 if reply == "rejected" else len(value) + 2, effect
    )
    read = lambda value, effect="normal", reply=None: step(
        "get",
        ("missing" if value is None else "data: " + value) if reply is None else reply,
        (0 if value is None else len(value)) + 2,
        effect,
    )
    if case == "normal":
        other = "".join("Q" if c != "Q" else "R" for c in payload)
        maximum = (payload + " / " + other + " 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 2)[:49]
        need(len(maximum) == 49, "Exact maximal payload")
        return [
            read(None),
            step("crc", "missing", 2, "normal"),
            append("missing", reply="rejected"),
            read(None),
            append("", reply="rejected"),
            read(None),
            write(payload),
            step("help", oracle.HELP),
            step("status", oracle.STATUS),
            read(payload),
            write(other),
            read(other),
            write(" x "),
            read(" x "),
            write(""),
            read(""),
            step("crc", "crc32c: 00000000", 2, "normal"),
            write("1234"),
            step("crc", "crc32c: f63af4ee", 6, "normal"),
            append("56789"),
            step("crc", "crc32c: e3069283", 11, "normal"),
            read("123456789"),
            write("x" * 49),
            step("crc", "crc32c: e0de1ddc", 51, "normal"),
            write(maximum),
            read(maximum),
            step("put " + "Z" * 50, oracle.INVALID),
            read(maximum),
            read(maximum),
            write("Hello"),
            append(", Aurora"),
            read("Hello, Aurora"),
            append(""),
            read("Hello, Aurora"),
            write(maximum[:24]),
            append(maximum[24:]),
            read(maximum),
            append("!", reply="rejected"),
            read(maximum),
            append(""),
            read(maximum),
            step("append " + "Z" * 50, oracle.INVALID),
            read(maximum),
            write(""),
            append(maximum),
            read(maximum),
        ]
    if case == "limit":
        value = payload[:3]
        return [write(value)] + [read(value) for _ in range(63)] + [step("get", oracle.LIMIT, effect="limit")]
    old, new = "old " + payload, "new " + payload
    baseline = write(old)
    suffix = " + " + payload[:10]
    if case == "1a":
        return [
            baseline,
            step("append " + suffix, oracle.ABORTED, 2, "preloss"),
            read(old),
            append(suffix),
            read(old + suffix),
        ]
    if case == "2c":
        return [baseline, step("crc", oracle.ABORTED, 3, "readloss"), read(old)]
    if case == "5c":
        return [baseline, step("crc", oracle.READ_FAILED, len(old) + 2, "badresult"), read(old)]
    if case == "6c":
        return [baseline, step("crc", oracle.RESET, len(old) + 2, "reset"), read(None)]
    if case == "3a":
        return [baseline, append(suffix, "commitloss", oracle.COMMITTED_FAILED), read(old + suffix)]
    if case == "4a":
        return [
            baseline,
            append("~i " + payload[:10], "servicefault", oracle.INDETERMINATE),
            read(None),
            write(new),
            read(new),
        ]
    if case == "1":
        return [baseline, step("put " + new, oracle.ABORTED, 2, "preloss"), read(old)]
    if case == "2":
        return [baseline, step("get", oracle.ABORTED, 3, "readloss"), read(old)]
    if case == "3":
        return [baseline, write(new, "commitloss", oracle.COMMITTED_FAILED), read(new)]
    if case == "4":
        return [
            baseline,
            write("~i " + payload, "servicefault", oracle.INDETERMINATE),
            read(None),
            write(new),
            read(new),
        ]
    if case == "5":
        return [baseline, read(old, "badresult", oracle.READ_FAILED), read(old)]
    if case == "6":
        return [baseline, read(old, "reset", oracle.RESET), read(None)]
    if case == "7":
        return [baseline, read(old, "backing", "")]
    if case == "8":
        return [baseline, write(new, "timeout", "sa")]
    raise ValueError("Unknown scratchpad test case")


def run(args):
    fixture = args.case not in {"normal", "limit"}
    mode = "ram-scratchpad-console" + ("-fixture" if fixture else "")
    build = args.build_dir.resolve(strict=True)
    need(
        build.parts[-3:] == ("kernel-images", "uefi", canonical_profile("uefi", mode)),
        "Exact native profile directory required",
    )
    if args.payload is None:
        args.payload = time.strftime("Scratchpad %H:%M:%S", time.gmtime())
    plan = plans(args.case, args.payload)
    # The storage image's bank: the images this row runs, by role.
    images = json.loads((build / "user-images.json").read_text())
    chosen = json.loads((build / "user-sets.json").read_text())[mode]
    metadata = dict(
        images={role: images[name] for role, name in chosen.items()},
        kernel=json.loads((build / "service-timer-metadata.json").read_text()),
    )
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    need(qemu is not None, "QEMU unavailable")
    selected = subprocess.check_output(
        [
            "bash",
            "-c",
            "set -e; source scripts/uefi-firmware.sh; uefi_firmware_select; "
            'printf "%s\\0" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS"',
        ],
        cwd=ROOT,
    )
    firmware, code, variables = selected.decode().split("\0")[:-1]
    argv = transport.profile_command(
        "uefi",
        mode,
        qemu,
        build / "esp",
        os.environ.get("QEMU_DATA", ""),
        firmware=firmware,
        code=code,
        variables=variables,
    )
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=False)
    else:
        parent = ROOT / "build/scratchpad-pty"
        parent.mkdir(exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=mode + "-", dir=parent))
    print("Scratchpad evidence:", output, flush=True)
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    master, slave = pty.openpty()
    tty.setraw(slave)
    transcript = bytearray()
    start = time.monotonic()
    deadline = start + 180
    process = None
    result = dict(verified=False, verified_teardown=False, case=args.case)
    try:
        with (output / "stderr.log").open("wb") as stderr:
            process = transport.start(argv, stdin=slave, stdout=slave, stderr=stderr)
            os.close(slave)
            slave = -1

            def pump():
                need(time.monotonic() < deadline, "Scratchpad external deadline, not verified teardown")
                if select.select([master], [], [], min(0.1, deadline - time.monotonic()))[0]:
                    try:
                        transcript.extend(os.read(master, 65536))
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
                need(len(transcript) < 8 * 1024 * 1024, "Scratchpad transcript cap")

            def until(marker, offset=0):
                while marker not in transcript[offset:]:
                    need(process.poll() is None, "Guest exited before " + repr(marker))
                    pump()

            def send(value):
                for byte in value:
                    os.write(master, bytes([byte]))
                    time.sleep(0.002)

            if fixture:
                until(b"AURORA_SCRATCHPAD_FIXTURE_READY")
                tty.setraw(master)
                send(args.case[0].encode("ascii"))
            until(b"aurora> ")
            # QEMU stdio may reenable ONLCR; retain raw startup, reset before input.
            tty.setraw(master)
            for item in plan:
                offset = len(transcript)
                send(item["command"].encode("ascii") + b"\r")
                if item["effect"] in {"backing", "timeout", "limit"}:
                    break
                until(b"\r\naurora> ", offset)
                if args.case == "normal" and item["command"] == "put " + args.payload:
                    # Leave source-owned locals parked through many Console wake IRQs.
                    delayed_until = time.monotonic() + 1.25
                    while time.monotonic() < delayed_until:
                        pump()
            if plan[-1]["effect"] not in {"backing", "timeout", "limit"}:
                send(b"exit\r")
            while process.poll() is None:
                pump()
            # Drain the PTY after the owned process exits, without requiring live guest.
            while select.select([master], [], [], 0)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not chunk:
                    break
                transcript.extend(chunk)
            result.update(
                oracle.validate(process.returncode, transcript.decode("ascii"), plan, metadata, fixture=fixture)
            )
            result["verified"] = True
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        if slave != -1:
            os.close(slave)
        os.close(master)
        (output / "serial.log").write_bytes(transcript)
        result.update(
            exit_code=process.returncode if process else None,
            seconds=time.monotonic() - start,
            max_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            full_qualification=False,
        )
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument(
        "--case", choices=["normal", "limit", *"12345678", "1a", "3a", "4a", "2c", "5c", "6c"], default="normal"
    )
    parser.add_argument("--payload", help="1..32 printable bytes chosen after building; default uses current UTC")
    parser.add_argument("--output", type=Path)
    run(parser.parse_args())


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fresh graphical-console smoke/captures; no historical approval or guest claim."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import resource
import select
import shutil
import signal
import stat
import subprocess
import sys
import time
import tty

import kernel_graphical_console_admission as admission
import kernel_uefi_oracle as normal
import qemu_transport as transport
import smoke_outputs
from framebuffer_capture_oracle import BASE, SIZE, VISIBLE, WIDTH, HEIGHT, PITCH, need, parse_ppm
from kernel_emulator_clock import ORIGINAL, validate_clock_options

ROOT = Path(__file__).resolve().parents[1]
capture = admission.load("graphical_smoke_capture", ROOT / "scripts/kernel-framebuffer-capture.py")
sys.path.insert(0, str(ROOT / "tests"))
from kernel_graphical_oracle import reference, byte_samples
from kernel_display_oracle import ppm_rgb

PREFIX = "AURORA_GRAPHICAL_"
NUMBER = r"(0|[1-9][0-9]{0,19})"
FIELDS = {
    "CAPTURE_GATE": ("base", "bytes"),
    "CAPTURE_RELEASED": ("selector",),
    "PRE_SAMPLE": ("completed", "stores"),
    "CONSOLE_COMPLETE": (
        "completion",
        "wakes",
        "stores",
        "entries",
        "samples",
        "output_attempts",
        "completed",
        "pixel_attempts",
    ),
    "CONSOLE_FAIL": ("entries", "samples", "output_attempts", "stores", "completed", "wakes", "pixel_attempts"),
}
CASES = [
    ("editing", b"G", b"hez\blp\r\nstatus\nx\x7fy\nabc\x01help\nexit\r!"),
    ("note-replace", b"G", b"cat note\nwrite note old suffix\ncat note\nwrite note x\ncat note\nexit\n!"),
    ("note-empty-edit", b"G", b"write notf\be oldX\x7f\r\ncat note\nwrite note \ncat note\nexit\n!"),
    ("note-preserve", b"G", b"write note saved\nwrite notes x\nwrite note bad\x01\ncat note\nexit\n!"),
    ("note-maximum", b"G", b"write note " + b"Ab9 !" * 10 + b"xyz\ncat note\nexit\n!"),
    ("files-demo", b"G", b"write todo Ship Aurora\nwrite ideas Safer drivers\nls\ncat todo\nrm ideas\nexit\n!"),
    (
        "files-capacity",
        b"G",
        b"write a \nwrite b \nwrite c \nwrite d \nwrite e E\nwrite b X\nrm a\nwrite e E\nls\nexit\n!",
    ),
    ("capacity64", b"G", b"x" * 64 + b"\nexit\r!"),
    ("overflow65", b"G", b"x" * 65 + b"\b\x7fhelp\nexit\r!"),
    ("event80", b"G", b"a" * 80 + b"!"),
    ("idle4096", b"G", b""),
    ("fixture-G", b"G", b"exit\r!"),
    *[("selector-" + byte, byte.encode(), b"") for byte in ("?", "C", "D", "c", "d", "F", "I")],
]
PRODUCTION = (
    b"help\r",
    b"status\r",
    b"write note hello\r",
    b"cat note\r",
    b"write a hi\r",
    b"cat a\r",
    b"rm a\r",
    b"ls\r",
    b"exX\b",
    b"it\r",
)


def child_limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))


def markers(raw, production=False, final=False):
    """Parse complete lines only while live; terminal validation rejects truncation."""
    need(len(raw) <= capture.MAX_IO, "serial output limit")
    text = raw.decode("ascii").replace("\r\n", "\n")
    need(not final or text.endswith("\n"), "truncated serial terminal")
    if PREFIX in text:
        boot = text.partition(PREFIX)[0]
        required = (
            "AURORA_UEFI_ENTRY\n",
            "AURORA_UEFI_EXIT_OK: attempts=1\n",
            "AURORA_UEFI_PAYLOAD_ENTRY\n",
            "AURORA_UEFI_OWNERSHIP_OK:",
            "AURORA_UEFI_PROTECTION_OK:",
            "AURORA_UEFI_LANGUAGE_OK: value=42\n",
            "AURORA_UEFI_OK\n",
        )
        need(all(boot.count(marker) == 1 for marker in required), "missing/duplicate bootstrap marker")
        positions = [boot.index(marker) for marker in required]
        need(positions == sorted(positions) and boot.endswith(required[-1]), "bootstrap marker order")
    rows = []
    for line in text.split("\n")[:-1]:
        need("\r" not in line, "embedded serial carriage return")
        need(not rows or rows[-1][0] not in ("CONSOLE_COMPLETE", "CONSOLE_FAIL"), "output after terminal")
        if not line.startswith(PREFIX):
            need(not rows, "unexpected output after capture boundary")
            need("_FAIL" not in line and "EXCEPTION" not in line, "unexpected boot failure")
            continue
        kind, separator, body = line[len(PREFIX) :].partition(": ")
        need(separator and kind in FIELDS, "unknown graphical marker")
        keys = FIELDS[kind][:3] if production and kind == "CONSOLE_COMPLETE" else FIELDS[kind]
        pattern = " ".join(key + "=" + NUMBER for key in keys)
        if kind == "CONSOLE_FAIL":
            pattern = r"(capture selector|paired service authority|NATIVE_IDLE_WAKE_DEADLINE: limit=4096) " + pattern
        match = re.fullmatch(pattern, body)
        need(match is not None, "malformed graphical marker: " + kind)
        values = list(match.groups())
        reason = values.pop(0) if kind == "CONSOLE_FAIL" else None
        row = dict(zip(keys, map(int, values)))
        need(all(value < 2**64 for value in row.values()), "counter overflow")
        if reason:
            row["reason"] = reason
        rows.append((kind, row))
    return rows


def compare(baseline, raw, ppm, frame=None, stores=None):
    need(len(baseline) == len(raw) == SIZE, "physical extent")
    expected = bytearray(baseline)
    if stores is not None:  # Exact successful prefix, on the real captured baseline.
        for offset, value in stores:
            expected[offset : offset + 4] = value.to_bytes(4, "little")
    elif frame is not None:
        need(len(frame) == 408 * 18 * 4, "model viewport extent")
        for row, y in enumerate(range(128, 146)):
            expected[(y * PITCH + 32) * 4 : (y * PITCH + 440) * 4] = frame[row * 1632 : (row + 1) * 1632]
    need(raw[VISIBLE:] == baseline[VISIBLE:], "1024-byte resource tail changed")
    need(raw == expected, "viewport or outside-resource pixels differ")
    need(parse_ppm(ppm) == ppm_rgb(WIDTH, HEIGHT, PITCH, 1, raw), "physical/screenshot mismatch")


def validate(rows, selector, model, idle=False, production=False):
    terminal, result = rows[-1]
    if production:
        need([kind for kind, _ in rows] == ["CONSOLE_COMPLETE"], "production marker inventory")
    else:
        expected = [("CAPTURE_GATE", dict(base=BASE, bytes=SIZE))]
        if selector != b"?":
            expected.append(("CAPTURE_RELEASED", dict(selector=b"GCDcdFI".index(selector) + 1)))
        if selector == b"G":
            counts = [0] if idle else range(model["consumed"])
            expected.extend(("PRE_SAMPLE", dict(completed=n, stores=model["frame_stores"][n])) for n in counts)
        need(rows[:-1] == expected, "gate/release/sample order or counters")
    denied = selector in (b"?", b"C", b"D", b"c", b"d") and not production
    if denied:
        reason = "capture selector" if selector == b"?" else "paired service authority"
        need(
            terminal == "CONSOLE_FAIL" and result == dict.fromkeys(FIELDS[terminal], 0) | {"reason": reason},
            "denied service had effects",
        )
        return
    stores = model["frame_stores"][0] if idle else len(model["stores"])
    need(result["stores"] == stores, "terminal stores")
    if idle:
        need(
            terminal == "CONSOLE_FAIL"
            and result
            == dict(
                entries=1,
                samples=4097,
                output_attempts=0,
                stores=stores,
                completed=0,
                wakes=4096,
                pixel_attempts=stores,
                reason="NATIVE_IDLE_WAKE_DEADLINE: limit=4096",
            ),
            "native idle deadline counters",
        )
    else:
        need(terminal == "CONSOLE_COMPLETE" and result["completion"] == model["completion"], "completion")
        need(0 <= result["wakes"] <= 4096, "wake bound")
        if model["completion"] == 2:
            need(result["wakes"] == result["samples"] == result["completed"] == 0, "pixel failure sampled input")
        if not production:
            need(
                result["entries"] == 1
                and result["completed"] == model["consumed"]
                and result["samples"] == model["consumed"] + result["wakes"]
                and result["output_attempts"] == 0
                and result["pixel_attempts"] == stores + (model["completion"] == 2),
                "terminal service counters",
            )


def wait(channel, predicate, production=False):
    while True:
        channel.drain_serial()
        rows = markers(channel.serial_bytes, production)
        if predicate(rows):
            return rows
        need(not rows or not rows[-1][0].startswith("CONSOLE_"), "unexpected terminal")
        need(not transport.exited(channel.proc), "premature QEMU exit")
        select.select([channel.serial], [], [], min(0.01, channel.remaining()))


def send(channel, data):
    need(select.select([], [channel.serial], [], channel.remaining())[1], "PTY write timeout")
    need(os.write(channel.serial, data) == len(data), "short PTY input write")
    with open(channel.directory / "input.log", "ab") as log:
        log.write(data.hex().encode() + b"\n")


@contextmanager
def guest(args, mode, directory, record):
    verify_images(args, mode)
    directory.mkdir()
    master = slave = proc = channel = None
    try:
        master, slave = os.openpty()
        tty.setraw(slave)
        argv = capture.command(
            {"qemu": args.qemu},
            {"data": args.data},
            str(args.images / mode / "esp"),
            os.ttyname(slave),
            qmp=True,
            firmware_args=args.firmware,
        )
        validate_clock_options("uefi", "normal", ORIGINAL, argv)
        record["argv"] = argv
        with open(directory / "qemu.stderr", "xb") as stderr:
            proc = transport.start(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, bufsize=0, preexec_fn=child_limits
            )
        channel = capture.Channel(proc, master, directory, time.monotonic() + 90)
        channel.command("cont")
        yield channel
    except (Exception, KeyboardInterrupt) as error:
        record["guest_error"] = str(error)
        raise
    finally:
        errors, _, unsettled = transport.finish(
            proc,
            drains=[channel.drain_serial] if channel else [],
            fds=(master, slave),
            streams=([channel.qlog, channel.slog] if channel else []) + ([proc.stdin, proc.stdout] if proc else []),
        )
        if proc:
            record["exit_status"] = proc.returncode
        record["cleanup_errors"] = errors
        if unsettled:
            raise transport.ChildNotReaped("; ".join(errors))
        need(not errors, "guest cleanup: " + "; ".join(errors))


def capture_case(args, case, directory, record):
    name, selector, data = case
    idle = name == "idle4096"
    fail_after = {b"F": 0, b"I": 55}.get(selector)
    model = reference(byte_samples(data or b"exit\r"), fail_after=fail_after)
    with guest(args, "graphical-console-capture", directory, record) as channel:
        wait(channel, lambda rows: bool(rows))
        channel.stop()
        need(markers(channel.serial_bytes) == [("CAPTURE_GATE", dict(base=BASE, bytes=SIZE))], "capture gate")
        baseline, ppm = channel.capture("baseline")
        compare(baseline, baseline, ppm)
        send(channel, selector)  # Editor bytes here would be discarded by initialize_input().
        channel.command("cont")
        if selector == b"G":
            for n in range(1 if idle else model["consumed"]):
                rows = wait(
                    channel,
                    lambda rows: (
                        bool(rows) and rows[-1] == ("PRE_SAMPLE", dict(completed=n, stores=model["frame_stores"][n]))
                    ),
                )
                if idle:  # One continuous unpaused, input-free interval until native terminal.
                    break
                channel.stop()
                # State-changing controls plus capacity/budget edges; every sample marker is still checked.
                if n in (0, 63, 64, 65, 79) or data[n - 1] in (1, 8, 10, 13, 127):
                    raw, ppm = channel.capture(f"sample-{n:02}")
                    compare(baseline, raw, ppm, frame=model["frames"][n])
                send(channel, data[n:] if n + 1 == model["consumed"] else data[n : n + 1])
                channel.command("cont")
        wait(channel, lambda rows: bool(rows) and rows[-1][0].startswith("CONSOLE_"))
        channel.stop()
        channel.drain_serial()
        rows = markers(channel.serial_bytes, final=True)
        validate(rows, selector, model, idle)
        raw, ppm = channel.capture("terminal")
        compare(
            baseline,
            raw,
            ppm,
            frame=model["frames"][0] if idle else None,
            stores=None if idle else model["stores"] if selector in (b"G", b"F", b"I") else [],
        )
        channel.command("quit")
        transport.wait_exit(channel.proc, 5, expected=0)
        channel.drain_serial()
        validate(markers(channel.serial_bytes, final=True), selector, model, idle)
        record.update(termination="qmp-quit", terminal=rows[-1], sent_hex=(selector + data).hex())


def probe(channel, stem):
    # Only 56,032 physical bytes per paused probe; keep full pairs at matched states.
    path = channel.directory / (stem + ".bin")
    size = (17 * PITCH + 408) * 4
    need(not path.exists(), "stale viewport probe")
    response = channel.command(
        "human-monitor-command", {"command-line": f'pmemsave {BASE + (128 * PITCH + 32) * 4} {size} "{path}"'}
    )
    need(response == "" and path.is_file() and path.stat().st_size == size, "viewport probe failed")
    raw = path.read_bytes()
    return b"".join(raw[y * PITCH * 4 : (y * PITCH + 408) * 4] for y in range(18))


def production_case(args, directory, record):
    model = reference(byte_samples(b"".join(PRODUCTION)))
    with guest(args, "graphical-console", directory, record) as channel:
        while b"AURORA_UEFI_OK\r\n" not in channel.serial_bytes:
            channel.drain_serial()
            markers(channel.serial_bytes, production=True)
            need(not transport.exited(channel.proc), "production boot exited early")
            select.select([channel.serial], [], [], min(0.01, channel.remaining()))
        baseline, consumed = None, 0
        for chunk in PRODUCTION:
            for attempt in range(80):
                channel.remaining()
                channel.stop()
                if probe(channel, f"probe-{consumed:02}-{attempt:02}") == model["frames"][consumed]:
                    raw, ppm = channel.capture(f"state-{consumed:02}")
                    if baseline is None:
                        baseline = raw  # Production has no pre-store gate or PRE_SAMPLE marker.
                    compare(baseline, raw, ppm, frame=model["frames"][consumed])
                    send(channel, chunk)
                    channel.command("cont")
                    consumed += len(chunk)
                    break
                channel.command("cont")
                time.sleep(0.1)
            else:
                raise ValueError("production viewport did not reach the expected input boundary")
        transport.wait_exit(channel.proc, channel.remaining(), expected=33)
        channel.drain_serial()
        rows = markers(channel.serial_bytes, production=True, final=True)
        validate(rows, b"G", model, production=True)
        record.update(termination="native-debug-exit", terminal=rows[-1])


def restoration(args, directory, record):
    verify_images(args, "normal")
    directory.mkdir()
    argv = capture.command(
        {"qemu": args.qemu}, {"data": args.data}, str(args.images / "normal/esp"), "stdio", firmware_args=args.firmware
    )
    validate_clock_options("uefi", "normal", ORIGINAL, argv)
    record["argv"] = argv
    status = transport.run_logged(
        argv,
        directory / "serial.log",
        timeout=30,
        preexec_fn=child_limits,
        limit=4 * 1024 * 1024,
    )
    normal.validate(status, (directory / "serial.log").read_text(), "normal")
    record.update(termination="native-debug-exit", exit_status=status)
    verify_images(args)


def window(args):
    args.evidence.mkdir()
    results = []

    def run(name, action):
        record = dict(name=name, status="failed")
        results.append(record)
        try:
            action(args.evidence / name, record)
            record["status"] = "passed"
        except (Exception, KeyboardInterrupt) as error:
            record["error"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            (args.evidence / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
            print(record["status"] + ": " + name, flush=True)

    primary = None
    try:
        run("production", lambda directory, record: production_case(args, directory, record))
        for case in CASES:
            run(case[0], lambda directory, record: capture_case(args, case, directory, record))
    except (Exception, KeyboardInterrupt) as error:
        primary = error
        raise
    finally:
        try:
            if isinstance(primary, transport.ChildNotReaped):
                raise primary
            run("normal-restoration", lambda directory, record: restoration(args, directory, record))
        except (Exception, KeyboardInterrupt):
            if primary is None:
                raise
            print("FAIL: normal restoration also failed; see summary.json", file=sys.stderr)


def stage(mode, destination, build):
    admission.configure_paths(build, ROOT)
    checked = admission.checked(mode) if mode != "normal" else None
    target = destination / mode
    build = admission.BUILD
    files = admission.build_files(mode)
    admitted = list(files)
    if mode == "normal":
        admission.common.verify_object_exports(files)
    if mode != "normal":
        files += [admission.RECEIPT]
    for path in files:
        need(
            path.is_file()
            and not path.is_symlink()
            and not any(parent.is_symlink() for parent in path.parents if parent.is_relative_to(build)),
            "missing artifact or symlink in image build: " + str(path),
        )
    expected = admission.common.hashes(files)
    if checked:
        for path in admitted:
            key = "build:" + path.relative_to(build).as_posix()
            need(expected[key] == checked["sha256"][key], "Admitted image changed before staging")
    target.mkdir(parents=True)
    for path in files:
        copied = target / path.relative_to(build)
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, copied)
        need(
            capture.digest(copied) == expected["build:" + path.relative_to(build).as_posix()],
            "Image changed during staging",
        )
    record = dict(
        mode=mode,
        files={str(p.relative_to(target)): capture.digest(p) for p in target.rglob("*") if p.is_file()},
    )
    (target / "smoke-image.json").write_text(json.dumps(record, indent=2) + "\n")


def verify_images(args, mode=None):
    for mode in (mode,) if mode else ("normal", *admission.MODES):
        folder = args.images / mode
        need(not any(p.is_symlink() for p in folder.rglob("*")), "symlink in staged images")
        record = json.loads((folder / "smoke-image.json").read_text())
        need(
            record["mode"] == mode,
            "staged image profile mismatch",
        )
        need(
            record["files"]
            == {
                str(p.relative_to(folder)): capture.digest(p)
                for p in folder.rglob("*")
                if p.is_file() and p.name != "smoke-image.json"
            },
            "staged image drift",
        )


RUN_MARKER = ".graphical-smoke-run.json"
RUN_SCHEMA = "aurora-graphical-smoke-run-v1"


def retained_runs():
    return smoke_outputs.retained_runs("AURORA_GRAPHICAL_KEEP_RUNS")


def output_policy():
    return smoke_outputs.SmokeOutputs(ROOT / "build/graphical-smoke", "run-", RUN_MARKER, RUN_SCHEMA, retained_runs())


def run_directory(directory):
    return output_policy().run_directory(directory)


def start_run(directory):
    output_policy().start(directory)


def discard_captures(directory):
    """Discard known dumps from this successful run; leave logs and review files."""
    guests = directory / "guests"
    need(not guests.is_symlink(), "symlink in smoke capture path")
    files = []
    for case in ("production", *(case[0] for case in CASES)):
        folder = guests / case
        need(not folder.is_symlink(), "symlink in smoke capture path")
        for path in sorted(folder.glob("*")):
            if re.fullmatch(
                r"(?:(?:baseline|terminal|sample-[0-9]{2}|state-[0-9]{2})\.(?:bin|ppm)"
                r"|probe-[0-9]{2}-[0-9]{2}\.bin)",
                path.name,
            ):
                files.append(path)
    smoke_outputs.discard_files(directory, files)


def finish_run(directory, status):
    output_policy().finish(directory, status, discard_captures)


def pin_reused_images(images):
    directory = images.parent
    if images.name != "images":
        return
    if directory.parent != ROOT / "build/graphical-smoke":
        # A foreign checkout owns its lock and retention policy. Do not mutate it.
        marker = directory / RUN_MARKER
        if (
            directory.parent.name != "graphical-smoke"
            or directory.parent.parent.name != "build"
            or not directory.name.startswith("run-")
            or not (marker.exists() or marker.is_symlink())
        ):
            return  # Unmanaged external images retain their read-only behavior.
        need(not marker.is_symlink() and marker.is_file(), "invalid foreign smoke ownership marker")
        record = admission.read_json(marker)
        need(
            record == dict(schema=RUN_SCHEMA, status="running")
            or (
                type(record) is dict
                and set(record) == {"schema", "status", "finished_ns"}
                and record["schema"] == RUN_SCHEMA
                and record["status"] in ("passed", "failed")
                and type(record["finished_ns"]) is int
            ),
            "invalid foreign smoke marker",
        )
        try:
            pinned = stat.S_ISREG((directory / ".keep").lstat().st_mode)
        except FileNotFoundError:
            pinned = False
        need(
            pinned,
            "Pin foreign managed images with a regular .keep file in the owning checkout before use: " + str(directory),
        )
        return
    with smoke_outputs.retention_lock(directory.parent):
        run_directory(directory)  # A pruner that won the lock may already have removed it.
        marker = directory / RUN_MARKER
        if not marker.exists():
            return
        need(not marker.is_symlink(), "symlink in smoke ownership marker")
        record = admission.read_json(marker)
        if record == dict(schema=RUN_SCHEMA, status="running"):
            return  # The invoking shell owns this active window until the child exits.
        need(
            type(record) is dict
            and record.get("schema") == RUN_SCHEMA
            and record.get("status") in ("passed", "failed"),
            "invalid completed smoke marker",
        )
        pin = directory / ".keep"
        if not pin.exists() and not pin.is_symlink():
            with pin.open("x"):
                pass
            print("Pinned reused graphical images until manual removal: " + str(directory), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("normal", *admission.MODES))
    parser.add_argument("--images", type=Path)
    lifecycle = parser.add_mutually_exclusive_group()
    lifecycle.add_argument("--start-run", type=Path)
    lifecycle.add_argument("--finish-run", type=Path)
    parser.add_argument("--status", type=int)
    parser.add_argument("--build-dir", type=Path, help="exact native profile directory for --stage")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("inputs", nargs="*")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda signum, frame: (_ for _ in ()).throw(KeyboardInterrupt("SIGTERM")))
    if args.start_run:
        start_run(args.start_run)
        return
    if args.finish_run:
        need(args.status is not None, "run exit status required")
        finish_run(args.finish_run, args.status)
        return
    need(args.images is not None, "images required")
    args.images = args.images.resolve()
    if args.stage:
        need(args.build_dir is not None, "--stage requires --build-dir")
        stage(args.stage, args.images, args.build_dir)
        return
    pin_reused_images(args.images)
    need(
        args.evidence and not args.evidence.exists() and len(args.inputs) == 5,
        "fresh evidence and QEMU OVMF CODE VARS DATA required",
    )
    args.evidence = args.evidence.resolve()
    need(all(re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(p)) for p in (args.evidence, args.images)), "unsafe capture path")
    args.qemu, firmware, code, variables, args.data = args.inputs
    args.firmware = transport.firmware_args(firmware, code, variables)
    verify_images(args)
    window(args)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        raise SystemExit(transport.failure_label(error) + ": graphical smoke: " + str(error)) from error

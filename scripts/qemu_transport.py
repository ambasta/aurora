#!/usr/bin/env python3
"""Shared disposable QEMU transport, not a boot, pixel or authority oracle.

Callers supply admitted inputs and explicit device/clock options. This module
does not admit images, choose tests, build receipts or infer guest success.
"""

import argparse
from contextlib import contextmanager, nullcontext
import json
import math
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

MAX_IO = 1024 * 1024


def need(value, reason):
    if not value:
        raise ValueError(reason)


class MissingPrerequisite(ValueError):
    """An unavailable external input, before any build or guest starts."""


def required(env, name, explanation):
    value = env.get(name, "")
    if not value:
        raise MissingPrerequisite(f"Set {name}: {explanation}. See docs/local-development.md.")
    return value


def input_path(value, label, directory=False):
    try:
        path = Path(value).resolve()
        if any(character in str(path) for character in (",", "\n", "\r")):
            raise ValueError(f"{label} cannot contain commas or line breaks in QEMU option paths")
        unavailable = f"{label} must name a readable {'directory' if directory else 'file'}: {path}"
        if not path.exists():
            raise MissingPrerequisite(unavailable)
        if not (path.is_dir() if directory else path.is_file()):
            raise ValueError(unavailable)
        if not os.access(path, os.R_OK):
            raise MissingPrerequisite(unavailable)
    except (FileNotFoundError, PermissionError) as error:
        raise MissingPrerequisite(f"Unavailable {label} prerequisite: {error}") from error
    return path


def failure_label(error):
    return "BLOCKED" if isinstance(error, MissingPrerequisite) else "FAIL"


def retain_artifacts(status, explicit_keep=False):
    """Only successful, explicitly disposable artifacts may be discarded."""
    return status != 0 or explicit_keep


class DeadlineExpired(ValueError):
    pass


def remaining(deadline, cap=None):
    left = deadline - time.monotonic()
    if left <= 0:
        raise DeadlineExpired("Child/global deadline expired")
    return left if cap is None else min(left, cap)


def command(
    qemu,
    data="",
    *,
    platform="uefi",
    cpu="qemu64",
    cpus=1,
    prefix=(),
    firmware=(),
    boot=(),
    peripherals=(),
    serial="stdio",
    debug_exit=True,
    diagnostics=(),
    extra=(),
):
    """The common BIOS/UEFI TCG profiles with explicit specialized devices.

    No clock override is added here. Independent clock oracles must never use
    this constructor to compute their expected command.
    """
    args = [str(qemu)]
    if data:
        args += ["-L", str(data)]
    machine, memory = {"bios": ("pc", "32M"), "uefi": ("q35", "128M")}[platform]
    args += [*prefix, "-machine", machine, "-accel", "tcg", "-cpu", cpu, "-smp", str(cpus), "-m", memory]
    args += list(firmware) + list(boot) + list(peripherals)
    args += ["-nic", "none", "-display", "none", "-serial", serial, "-monitor", "none", "-no-reboot"]
    args += list(diagnostics)
    if debug_exit:
        args += ["-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    args += list(extra)
    return args


def firmware_args(combined="", code="", variables=""):
    need(all(type(path) is str and "\0" not in path for path in (combined, code, variables)), "Invalid firmware path")
    if combined and not code and not variables:
        return ["-bios", combined]
    need(not combined and code and variables and code != variables, "Expected combined firmware or CODE/VARS pair")
    args = []
    for unit, path in enumerate((code, variables)):
        image_format = "qcow2" if path.endswith(".qcow2") else "raw"
        policy = "snapshot=on" if unit else "readonly=on"
        args += ["-drive", f"if=pflash,unit={unit},format={image_format},{policy},file=" + path.replace(",", ",,")]
    return args


def fat_boot(esp):
    return ["-drive", "format=raw,file=fat:ro:" + str(esp) + ",snapshot=on"]


def profile_command(
    platform,
    mode,
    qemu,
    image,
    data="",
    *,
    firmware="",
    code="",
    variables="",
    clock="tcg-original-clock",
    snapshot=False,
):
    """Small ordinary smoke/console profile data, separate from clock oracles."""
    mode = mode.removeprefix("--")
    cpu = {
        "no-nx": "qemu64,-nx",
        "schedule-no-apic": "qemu64,-apic",
        "runtime-sysenter": "qemu64,vendor=GenuineIntel,+sep",
    }.get(mode, "qemu64")
    cpus = 2 if mode in ("schedule-smp", "acpi-two", "budget-smp") else 1
    prefix, firmware_options = [], []
    if platform == "bios":
        need(clock == "tcg-original-clock", "BIOS clock override is unsupported")
        boot = [
            "-drive",
            "file=" + str(image) + ",format=raw,if=ide" + (",snapshot=on" if snapshot else ""),
            "-boot",
            "c",
        ]
    else:
        firmware_options = firmware_args(firmware, code, variables)
        boot = fat_boot(image)
        devices = {
            "bar-state": ["nvme,serial=AURORA_READ_ONLY"],
            "pci-devices": ["nvme,serial=AURORA_READ_ONLY", "qemu-xhci", "e1000e,romfile="],
            "pci-bridge": [
                "pcie-root-port,id=aurora_port,chassis=1,slot=2",
                "nvme,bus=aurora_port,serial=AURORA_READ_ONLY",
            ],
            "pci-cycle": [
                "pcie-root-port,id=aurora_port,chassis=1,slot=2",
                "nvme,bus=aurora_port,serial=AURORA_READ_ONLY",
            ],
        }
        prefix = [arg for device in devices.get(mode, ()) for arg in ("-device", device)]
        need(clock in ("tcg-original-clock", "tcg-fixed0-noalign-nosleep"), "Unknown emulator clock profile")
        if clock == "tcg-fixed0-noalign-nosleep":
            prefix += ["-icount", "shift=0,align=off,sleep=off"]
    return command(
        qemu, data, platform=platform, cpu=cpu, cpus=cpus, prefix=prefix, firmware=firmware_options, boot=boot
    )


def start(argv, **options):
    """Own a separate session so cleanup cannot signal an unrelated caller."""
    return subprocess.Popen(argv, start_new_session=True, **options)


def check_exit(status, expected):
    need(status == expected, f"Child exited {status}; expected {expected}")
    return status


def json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def finite(value):
        number = float(value)
        need(math.isfinite(number), "nonfinite JSON")
        return number

    result = json.loads(
        raw, object_pairs_hook=unique, parse_float=finite, parse_constant=lambda _: need(False, "nonfinite JSON")
    )
    need(type(result) is dict, "QMP non-object response")
    return result


class Qmp:
    def __init__(self, process, deadline, log, *, timeout=2, log_limit=65536):
        self.deadline, self.log = deadline, log
        self.timeout, self.log_limit = timeout, log_limit
        self.buffer, self.total, self.sequence = b"", 0, 0
        self.reader, self.writer = process.stdout, process.stdin
        os.set_blocking(self.reader.fileno(), False)
        os.set_blocking(self.writer.fileno(), False)
        greeting = self.receive()
        need(set(greeting) == {"QMP"} and type(greeting["QMP"]) is dict, "Missing QMP greeting")
        self.command("qmp_capabilities")

    def remaining(self, response_deadline=None):
        return remaining(min(self.deadline, response_deadline or self.deadline), self.timeout)

    def record(self, data):
        self.total += len(data)
        need(self.total <= self.log_limit, "QMP transcript limit")
        self.log.write(data)

    def receive(self):
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self.buffer:
            need(select.select([self.reader], [], [], self.remaining(deadline))[0], "QMP response timeout")
            chunk = os.read(self.reader.fileno(), 4096)
            need(chunk, "QMP connection closed")
            self.record(chunk)
            self.buffer += chunk
            need(len(self.buffer) <= MAX_IO, "QMP response size")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json_object(line)

    def command(self, name, arguments=None):
        self.sequence += 1
        request = dict(execute=name, id=self.sequence)
        if arguments is not None:
            request["arguments"] = arguments
        encoded = json.dumps(request).encode() + b"\n"
        self.record(b"SEND " + encoded)
        pending, deadline = memoryview(encoded), time.monotonic() + self.timeout
        while pending:
            need(select.select([], [self.writer], [], self.remaining(deadline))[1], "QMP request timeout")
            count = os.write(self.writer.fileno(), pending)
            need(count > 0, "QMP request pipe closed")
            pending = pending[count:]
        while True:
            response = self.receive()
            if "event" in response:
                need("id" not in response and "error" not in response, "Malformed QMP event")
                continue
            need(
                set(response) == {"id", "return"} and type(response["id"]) is int and response["id"] == self.sequence,
                "QMP command failed: " + repr(response),
            )
            return response["return"]


class ChildNotReaped(RuntimeError):
    """Restoration must not race an owned child whose exit cannot be established."""


def exited(process):
    return os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def reap_completed(process, deadline):
    while not exited(process):
        remaining(deadline)
        time.sleep(0.01)
    # Keep the zombie leader unreaped while checking this Linux session's group.
    # A successful wrapper must not leave a background compiler/helper running.
    need(os.getpgid(process.pid) == os.getsid(process.pid) == process.pid, "Owned child session changed")
    for path in Path("/proc").iterdir():
        remaining(deadline)
        if not path.name.isdecimal() or int(path.name) == process.pid:
            continue
        try:
            raw = (path / "stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        fields = raw[raw.rfind(")") + 2 :].split()
        need(len(fields) >= 4, "Malformed process group observation")
        need((int(fields[2]), int(fields[3])) != (process.pid, process.pid), "Owned child left descendants")
    return process.wait(timeout=max(0.001, deadline - time.monotonic()))


def cleanup(process):
    """Hold an unreaped session leader until all forced signals are sent.

    WNOWAIT avoids reusing a numeric group ID after reaping its leader. Builds
    may have compiler children; TERM/KILL applies only to this owned session.
    """
    forced = process.returncode is None
    if not forced:
        return False
    need(os.getpgid(process.pid) == process.pid, "Owned child process group changed")
    os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
            break
        time.sleep(0.01)
    # The unreaped leader still binds this group, even if it exited after TERM.
    need(os.getpgid(process.pid) == process.pid, "Owned child process group changed")
    os.killpg(process.pid, signal.SIGKILL)
    deadline = time.monotonic() + 2
    process.wait(timeout=2)
    while True:
        try:
            os.killpg(process.pid, 0)  # Probe only; never signal a reaped numeric ID.
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            raise ChildNotReaped("Owned process group has not settled")
        time.sleep(0.01)


@contextmanager
def defer_interrupts():
    old = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        yield
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)


def finish(process, *, drains=(), streams=(), fds=(), require_natural=False):
    """Reap before draining/closing owned channels, retaining every cleanup error."""
    errors, forced, unsettled = [], False, False
    with defer_interrupts():
        if process:
            try:
                forced = process.returncode is None
                cleanup(process)
                need(not forced or not require_natural, "Forced child cleanup")
            except BaseException as error:
                errors.append("cleanup: " + type(error).__name__ + ": " + str(error))
                unsettled = isinstance(error, ChildNotReaped) or process.returncode is None
        actions = list(drains)
        actions += [stream.close for stream in streams if stream is not None]
        actions += [lambda fd=fd: os.close(fd) for fd in fds if fd is not None]
        for action in actions:
            try:
                action()
            except (Exception, KeyboardInterrupt) as error:
                errors.append(type(error).__name__ + ": " + str(error))
    return errors, forced, unsettled


def wait_exit(process, timeout, expected=None):
    status = reap_completed(process, time.monotonic() + timeout)
    return status if expected is None else check_exit(status, expected)


def capture_bytes(output, data, count, limit, reason):
    left = limit - count
    output.write(data[:left])
    need(len(data) <= left, reason)
    return count + len(data)


def run_logged(
    argv,
    log,
    *,
    env=None,
    cwd=None,
    timeout=30,
    expected=None,
    limit=32 * MAX_IO,
    preexec_fn=None,
    timeout_status=True,
    stderr=subprocess.STDOUT,
):
    """Drain bounded serial/output to the caller's retained log, then reap.

    Timeout is status 124 for ordinary smoke or an exception for callers whose
    process protocol requires natural exit. Every other error remains a failure.
    """
    process, failure = None, None
    try:
        with log.open("xb") if isinstance(log, Path) else nullcontext(log) as stream:
            process = start(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT if stderr == subprocess.STDOUT else subprocess.PIPE,
                preexec_fn=preexec_fn,
            )
            deadline, count = time.monotonic() + timeout, 0
            outputs = {process.stdout: stream}
            if process.stderr is not None:
                outputs[process.stderr] = stderr
            for reader in outputs:
                os.set_blocking(reader.fileno(), False)
            while outputs:
                ready = select.select(list(outputs), [], [], remaining(deadline))[0]
                if not ready:
                    raise DeadlineExpired("Child output deadline expired")
                for reader in ready:
                    data = os.read(reader.fileno(), 65536)
                    if not data:
                        del outputs[reader]
                        continue
                    count = capture_bytes(outputs[reader], data, count, limit, "Child output limit")
            status = reap_completed(process, deadline)
    except DeadlineExpired as error:
        if not timeout_status:
            failure = error
            raise
        status = 124
    except BaseException as error:
        failure = error
        raise
    finally:
        errors, _, unsettled = finish(process, streams=[process.stdout, process.stderr] if process else [])
        if errors:
            reason = "; ".join(([str(failure)] if failure else []) + errors)
            raise (ChildNotReaped if unsettled else ValueError)(reason)
    return status if expected is None else check_exit(status, expected)


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    argv_parser = commands.add_parser("argv", help="emit fully constructed NUL-separated ordinary QEMU arguments")
    argv_parser.add_argument("--platform", choices=("bios", "uefi"), required=True)
    for name in ("mode", "image", "qemu"):
        argv_parser.add_argument("--" + name, required=True)
    for name in ("data", "firmware", "code", "vars"):
        argv_parser.add_argument("--" + name, default="")
    argv_parser.add_argument("--clock", default="tcg-original-clock")
    argv_parser.add_argument("--snapshot", action="store_true")
    run_parser = commands.add_parser("run", help="capture a bounded ordinary guest using shared lifecycle")
    run_parser.add_argument("--timeout", type=float, required=True)
    output = run_parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--log", type=Path)
    output.add_argument("--foreground", action="store_true", help="preserve the interactive foreground terminal policy")
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == "argv":
            argv = profile_command(
                args.platform,
                args.mode,
                args.qemu,
                args.image,
                args.data,
                firmware=args.firmware,
                code=args.code,
                variables=args.vars,
                clock=args.clock,
                snapshot=args.snapshot,
            )
            need(all("\0" not in arg for arg in argv), "NUL in QEMU argument")
            sys.stdout.buffer.write(b"".join(arg.encode() + b"\0" for arg in argv))
            return 0
        need(args.timeout > 0, "Expected a positive guest timeout")
        argv = args.command[1:] if args.command[:1] == ["--"] else args.command
        need(argv, "Missing QEMU command")
        if args.foreground:
            # Keep the established terminal/session semantics; timeout replaces
            # this process and directly supervises the interactive foreground guest.
            os.execvp("timeout", ["timeout", "--foreground", "--kill-after=2", format(args.timeout, "g"), *argv])

        def terminate(signum, frame):
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, terminate)
        # These are the existing caller-selected build logs, intentionally replaced
        # on rerun; fresh retained evidence callers still use exclusive creation.
        with args.log.open("wb") as log:
            status = run_logged(argv, log, timeout=args.timeout)
            return 128 - status if status < 0 else status
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"{failure_label(error)}: QEMU transport: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(cli())

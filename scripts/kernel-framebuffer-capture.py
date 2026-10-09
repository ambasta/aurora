#!/usr/bin/env python3
"""Capture prebuilt, independently admitted framebuffer images. Never builds.

Inputs are a SHA-pinned JSON manifest, three SHA-pinned independent receipts,
and a root quiet-window release. No manifest is generated or approved here.
All modes always attempt an actual prebuilt normal boot after guest execution.
QMP uses anonymous stdio pipes and the serial channel uses an existing local PTY
mechanism; no network sockets, host devices, or host memory captures are used.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import time
import tty

from framebuffer_capture_oracle import BASE, SIZE, GATE, MODES, need, validate_serial, validate_capture

ROOT = Path(__file__).resolve().parents[1]
MAX_IO = 1024 * 1024


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_path(value):
    p = Path(value)
    need(re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(p)), "unsafe input path")
    need(p.is_absolute() and p == p.resolve(strict=True), "noncanonical/stale path: " + str(p))
    return p


def pin(row):
    need(set(row) == {"path", "sha256"}, "pin schema")
    p = exact_path(row["path"])
    need(
        re.fullmatch("[0-9a-f]{64}", row["sha256"]) and p.is_file() and digest(p) == row["sha256"],
        "input digest mismatch: " + str(p),
    )
    return p


def tree(row, source=False):
    need(set(row) == {"root", "manifest"}, "tree schema")
    root = exact_path(row["root"])
    expected = json.loads(pin(row["manifest"]).read_text())
    actual = []
    for p in sorted(root.rglob("*")):
        relative = p.relative_to(root)
        if source and any(x in {"build", ".git", "__pycache__", ".ruff_cache"} for x in relative.parts):
            continue
        need(
            not p.is_symlink() or (not source and p.resolve(strict=True).is_file()),
            "unadmitted directory/source symlink: " + str(p),
        )
        if p.is_file():
            actual.append(dict(path=relative.as_posix(), sha256=digest(p)))
    need(actual == expected, "tree content drift: " + str(root))
    return root


def verify(manifest):
    need(set(manifest) == {"schema", "pins", "trees", "library_path", "cases", "normal"}, "manifest schema")
    need(manifest["schema"] == "aurora-framebuffer-capture-v1", "manifest version")
    required = {"python", "qemu", "firmware", "compiler", "cxx", "runner", "oracle", "scene", "normal_oracle"}
    need(set(manifest["pins"]) == required, "missing/extra tool pin")
    pins = {key: pin(row) for key, row in manifest["pins"].items()}
    need(
        pins["python"] == Path(sys.executable).resolve() and pins["runner"] == Path(__file__).resolve(),
        "runner/interpreter identity",
    )
    need(
        pins["oracle"] == ROOT / "scripts/framebuffer_capture_oracle.py"
        and pins["scene"] == ROOT / "tests/kernel_display_oracle.py"
        and pins["normal_oracle"] == ROOT / "tests/kernel-uefi-smoke.py",
        "helper identity",
    )
    need(set(manifest["trees"]) == {"source", "data", "runtime"}, "tree inventory")
    roots = {key: tree(row, key == "source") for key, row in manifest["trees"].items()}
    need(roots["source"] == ROOT, "source root mismatch")
    libraries = manifest["library_path"]
    need(isinstance(libraries, list) and libraries, "runtime library path missing")
    for value in libraries:
        p = exact_path(value)
        need(p.is_dir() and p.is_relative_to(roots["runtime"]), "unmanifested runtime library directory")
    need(set(manifest["cases"]) == set(MODES), "case coverage inventory")
    for mode, row in list(manifest["cases"].items()) + [("normal", manifest["normal"])]:
        need(set(row) == {"esp", "elf", "pe", "admission"}, "image schema: " + mode)
        esp = exact_path(row["esp"])
        elf, pe = pin(row["elf"]), pin(row["pe"])
        pin(row["admission"])
        need(pe == esp / "EFI/BOOT/BOOTX64.EFI" and elf.suffix == ".elf", "image layout")
        need(
            [p for p in esp.rglob("*") if p.is_file()] == [pe] and not any(p.is_symlink() for p in esp.rglob("*")),
            "ESP contains unadmitted files",
        )
    return pins, roots


def review(path, expected, manifest_sha, role):
    p = pin(dict(path=str(path), sha256=expected))
    row = json.loads(p.read_text())
    need(
        row.get("schema") == "aurora-framebuffer-review-v1"
        and row.get("role") == role
        and row.get("status") == "approved"
        and row.get("manifest_sha256") == manifest_sha,
        "missing/stale independent " + role + " admission",
    )
    if role == "release":
        now = time.time()
        need(
            isinstance(row.get("issued_unix"), (int, float))
            and isinstance(row.get("expires_unix"), (int, float))
            and row["issued_unix"] <= now < row["expires_unix"] <= row["issued_unix"] + 3600,
            "expired/malformed root quiet-window release",
        )
    return dict(path=str(p), sha256=expected)


class Channel:
    def __init__(self, proc, serial, directory, deadline):
        self.proc, self.serial, self.directory, self.deadline = proc, serial, directory, deadline
        self.buffer = b""
        self.serial_bytes = b""
        self.seq = 0
        self.qlog = open(directory / "qmp-transcript.log", "xb", buffering=0)
        self.slog = open(directory / "serial.log", "xb", buffering=0)

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        need(remaining > 0, "guest wall timeout")
        return min(remaining, 5)

    def receive(self):
        while b"\n" not in self.buffer:
            need(select.select([self.proc.stdout], [], [], self.remaining())[0], "QMP response timeout")
            part = os.read(self.proc.stdout.fileno(), 65536)
            need(part, "QMP EOF")
            self.qlog.write(b"RX " + part)
            self.buffer += part
            need(len(self.buffer) <= MAX_IO, "QMP response size")
        line, self.buffer = self.buffer.split(b"\n", 1)
        value = json.loads(line)
        need(isinstance(value, dict), "QMP non-object response")
        return value

    def command(self, execute, arguments=None):
        self.seq += 1
        request = dict(execute=execute, id=self.seq)
        if arguments is not None:
            request["arguments"] = arguments
        data = json.dumps(request).encode() + b"\n"
        self.qlog.write(b"TX " + data)
        need(select.select([], [self.proc.stdin], [], self.remaining())[1], "QMP write timeout")
        need(self.proc.stdin.write(data) == len(data), "short QMP write")
        self.proc.stdin.flush()
        while True:
            row = self.receive()
            if "event" in row:
                continue
            need(
                row.get("id") == self.seq and "return" in row and "error" not in row, "QMP command failed: " + str(row)
            )
            return row["return"]

    def stop(self):
        self.command("stop")
        status = self.command("query-status")
        need(status.get("status") == "paused" and status.get("running") is False, "guest not paused")

    def drain_serial(self):
        while select.select([self.serial], [], [], 0)[0]:
            part = os.read(self.serial, 65536)
            need(part, "serial EOF")
            self.serial_bytes += part
            self.slog.write(part)
            need(len(self.serial_bytes) <= MAX_IO, "serial output limit")

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
            need(self.proc.poll() is None, "premature guest process exit")
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
    args = [str(pins["qemu"])]
    if roots.get("data"):
        args += ["-L", str(roots["data"])]
    args += [
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
    ]
    args += firmware_args if firmware_args is not None else ["-bios", str(pins["firmware"])]
    args += [
        "-drive",
        "format=raw,file=fat:ro:" + esp + ",snapshot=on",
        "-vga",
        "std",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        serial,
        "-monitor",
        "none",
        "-no-reboot",
        "-device",
        "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
    if qmp:
        args += ["-qmp", "stdio", "-S"]
    return args


def terminate(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    need(proc.poll() is not None, "QEMU not reaped")


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
            proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, env=env, cwd=ROOT, bufsize=0
            )
            channel = Channel(proc, master, directory, start + 90)
            need("QMP" in channel.receive(), "missing QMP greeting")
            channel.command("qmp_capabilities")
            channel.command("cont")
            channel.wait_marker()
            channel.stop()
            channel.drain_serial()
            validate_serial(channel.serial_bytes, mode, gate_only=True)
            baseline, baseline_ppm = channel.capture("baseline")
            # Only the exact reviewed byte is sent, once, while paused.
            need(os.write(master, b"G") == 1, "serial release write failed")
            receipt["release_hex"] = "47"
            channel.command("cont")
            channel.wait_marker(terminal=True)
            channel.stop()
            channel.drain_serial()
            after, screenshot = channel.capture("after")
            validate_serial(channel.serial_bytes, mode)
            receipt["observation"] = validate_capture(mode, baseline, after, screenshot, baseline_ppm)
            channel.command("quit")
            need(proc.wait(timeout=5) == 0, "QMP quit process status")
            receipt["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        receipt.update(status="failed", error=type(error).__name__ + ": " + str(error))
    finally:
        cleanup_errors = []

        def cleanup(action):
            try:
                action()
            except (Exception, KeyboardInterrupt) as error:
                cleanup_errors.append(type(error).__name__ + ": " + str(error))

        if proc:
            cleanup(lambda: terminate(proc))
            receipt["exit_status"] = proc.returncode
        if channel:
            cleanup(channel.drain_serial)
            if receipt["status"] == "passed":
                cleanup(lambda: validate_serial(channel.serial_bytes, mode))
            # Preserve any unread QMP tail after the child has been reaped.
            if proc and proc.poll() is not None:

                def drain_qmp():
                    while select.select([proc.stdout], [], [], 0)[0]:
                        part = os.read(proc.stdout.fileno(), 65536)
                        if not part:
                            break
                        channel.qlog.write(b"RX " + part)

                cleanup(drain_qmp)
            cleanup(channel.qlog.close)
            cleanup(channel.slog.close)
        for fd in (master, slave):
            if fd is not None:
                cleanup(lambda fd=fd: os.close(fd))
        if proc:
            for stream in (proc.stdin, proc.stdout):
                if stream:
                    cleanup(stream.close)
        if cleanup_errors:
            receipt.update(status="failed", cleanup_errors=cleanup_errors)
        receipt["elapsed_seconds"] = time.monotonic() - start
        receipt["files"] = {p.name: digest(p) for p in directory.iterdir() if p.is_file()}
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def restore(manifest, pins, roots, env, directory):
    directory.mkdir()
    argv = command(pins, roots, manifest["normal"]["esp"], "stdio")
    receipt = dict(command=argv, status="started")
    # Recheck normal and tools; restoration must not execute drifted bytes.
    proc = None
    try:
        verify(manifest)
        with open(directory / "serial.log", "xb") as log:
            proc = subprocess.Popen(
                argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=ROOT
            )
            status = proc.wait(timeout=30)
        spec = importlib.util.spec_from_file_location("normal_capture_restoration", pins["normal_oracle"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate(status, (directory / "serial.log").read_text(), "normal")
        receipt.update(status="passed", exit_status=status)
    except (Exception, KeyboardInterrupt) as error:
        receipt.update(status="failed", error=type(error).__name__ + ": " + str(error))
    finally:
        if proc:
            try:
                terminate(proc)
            except Exception as error:
                receipt.update(status="failed", cleanup_error=str(error))
        receipt["files"] = {p.name: digest(p) for p in directory.iterdir() if p.is_file()}
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    for role in ("image", "core", "capture", "release"):
        parser.add_argument("--" + role + "-receipt", required=True)
        parser.add_argument("--" + role + "-sha256", required=True)
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    # Explicit admitted library search only. Never inherit build, firmware,
    # QEMU, loader or Python injection overrides.
    forbidden = [key for key in os.environ if key.startswith(("QEMU", "UEFI_", "AURORA_", "PYTHON", "LD_"))]
    need(not forbidden, "environment overrides present: " + ", ".join(sorted(forbidden)))
    path = pin(dict(path=args.manifest, sha256=args.manifest_sha256))
    manifest = json.loads(path.read_text())
    pins, roots = verify(manifest)
    receipts = {}
    for role in ("image", "core", "capture", "release"):
        receipts[role] = review(
            getattr(args, role + "_receipt"), getattr(args, role + "_sha256"), args.manifest_sha256, role
        )
    directory = Path(args.evidence)
    need(
        re.fullmatch(r"/[A-Za-z0-9_./+\-]+", str(directory)) and directory.is_absolute() and not directory.exists(),
        "evidence must be fresh absolute directory",
    )
    need(directory.parent.resolve(strict=True).is_relative_to(ROOT.parent), "evidence outside task workspace")
    directory.mkdir()
    (directory / "manifest.json").write_bytes(path.read_bytes())
    for role, row in receipts.items():
        (directory / (role + "-review.json")).write_bytes(Path(row["path"]).read_bytes())
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "LD_LIBRARY_PATH": ":".join(manifest["library_path"])}
    receipt = dict(manifest_sha256=args.manifest_sha256, reviews=receipts, cases=[], status="started")
    try:
        for mode in MODES:
            for role in ("image", "core", "capture", "release"):
                review(getattr(args, role + "_receipt"), getattr(args, role + "_sha256"), args.manifest_sha256, role)
            verify(manifest)
            result = run_case(mode, manifest, pins, roots, env, directory / mode)
            receipt["cases"].append(result)
            need(result["status"] == "passed", "capture case failed: " + mode)
        verify(manifest)
        receipt["status"] = "passed"
    except (Exception, KeyboardInterrupt) as error:
        receipt.update(status="failed", error=type(error).__name__ + ": " + str(error))
    finally:
        receipt["normal_restoration"] = restore(manifest, pins, roots, env, directory / "normal-restoration")
        if receipt["normal_restoration"]["status"] != "passed":
            receipt["status"] = "failed"
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    need(receipt["status"] == "passed", "framebuffer qualification failed; preserved evidence: " + str(directory))
    print("PASS: full physical/real screenshot capture, 3 no-write failures, actual normal restoration")


if __name__ == "__main__":
    main()

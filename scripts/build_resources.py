#!/usr/bin/env python3
"""Run owned build/test process groups with a best-effort Linux memory watchdog."""

import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

HOST_RESERVE_MIB = 2048
POLL_SECONDS = 0.25


def available_memory_mib():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            fields = line.split()
            if fields[:1] == ["MemAvailable:"] and fields[2:] == ["kB"]:
                return max(0, int(fields[1]) // 1024)
    except (OSError, ValueError):
        pass
    return None


def cgroup_memory_mib():
    """Read visible cgroup-v2 headroom, including bounded ancestors; set no limits."""
    try:
        membership = Path("/proc/self/cgroup").read_text().splitlines()
        mounts = Path("/proc/self/mountinfo").read_text().splitlines()
    except OSError:
        return None
    group = next((Path(line[3:]) for line in membership if line.startswith("0::/")), None)
    if group is None:
        return None
    for line in mounts:
        fields, separator, filesystem = line.partition(" - ")
        fields = fields.split()
        if not separator or filesystem.split()[:1] != ["cgroup2"] or len(fields) < 5:
            continue
        root, mount = (Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), p)) for p in fields[3:5])
        try:
            relative = group.relative_to(root)
        except ValueError:
            continue
        if not mount.is_absolute() or ".." in relative.parts:
            continue
        current = mount / relative
        limits = []
        while True:
            try:
                maximum = (current / "memory.max").read_text().strip()
            except FileNotFoundError:
                maximum = "max"
            except OSError:
                return 0  # A visible but unreadable controller is not free headroom.
            if maximum != "max":
                try:
                    limit = int(maximum)
                    used = int((current / "memory.current").read_text())
                    if min(limit, used) < 0:
                        return 0
                    limits.append(max(0, limit - used) // (1024 * 1024))
                except (OSError, ValueError):
                    return 0
            if current == mount:
                return min(limits, default=None)
            current = current.parent
    return None


def jobs(selection="auto", label="jobs"):
    """Use nproc, with an optional positive numeric ceiling."""
    try:
        cpus = int(subprocess.check_output(["nproc"], text=True, timeout=10).strip())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError("Cannot read nproc for build/test concurrency") from error
    if cpus < 1:
        raise ValueError("nproc must report a positive CPU count")
    try:
        ceiling = cpus if selection == "auto" else int(selection)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be auto or a positive integer") from error
    if ceiling < 1:
        raise ValueError(f"{label} must be auto or a positive integer")
    count = min(cpus, ceiling)
    print(f"Aurora {label}: {count} jobs (nproc={cpus}, selection={selection}).", file=sys.stderr)
    return count


def check_memory():
    available = available_memory_mib()
    if available is None:
        raise ValueError("Memory watchdog: cannot read MemAvailable from /proc/meminfo")
    cgroup = cgroup_memory_mib()
    headroom = min(available, cgroup) if cgroup is not None else available
    if headroom <= HOST_RESERVE_MIB:
        raise ValueError(
            f"Memory watchdog: MemAvailable={available} MiB, cgroup-v2 headroom={cgroup} MiB; "
            f"need more than {HOST_RESERVE_MIB} MiB reserve"
        )


def run(argv, **kwargs):
    """Check memory before launch and while the owned process group runs.

    This does not reserve memory or contain children that leave the group.
    It cannot prevent an OOM between samples. Streams must be inherited or files,
    not PIPEs, because this runner deliberately does not buffer command output.
    """
    check_memory()
    print(
        f"Aurora memory watchdog: {HOST_RESERVE_MIB} MiB reserve, {POLL_SECONDS}s polling; "
        "stops this command's process group on low or unreadable memory.",
        file=sys.stderr,
    )

    pending_signal = None

    def interrupted(signum, frame):
        nonlocal pending_signal
        pending_signal = signum

    def check_interruption():
        if pending_signal is not None:
            raise InterruptedError(f"Memory-guarded command interrupted by signal {pending_signal}")

    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    process = None
    try:
        for sig in previous:
            signal.signal(sig, interrupted)
        check_interruption()
        process = subprocess.Popen(argv, start_new_session=True, **kwargs)
        while True:
            check_interruption()
            try:
                code = process.wait(timeout=POLL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                check_memory()
        check_interruption()
        if code:
            raise subprocess.CalledProcessError(code, argv)
        return subprocess.CompletedProcess(argv, code)
    except BaseException:
        if process is not None:
            # Do not let another interrupt skip cleanup, or a leader's early
            # exit hide still-running compilers/test descendants in the group.
            for sig in previous:
                signal.signal(sig, signal.SIG_IGN)
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            time.sleep(0.5)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

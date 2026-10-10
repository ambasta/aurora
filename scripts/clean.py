#!/usr/bin/env python3
"""Explicit local cleanup: Ninja products, or old successful managed smoke runs."""

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

RUN_MARKER = ".graphical-smoke-run.json"
RUN_SCHEMA = "aurora-graphical-smoke-run-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(path):
    """Do not resolve away evidence of a symlink, including a dangling one."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        require(not part.is_symlink(), "symlink in cleanup path: " + str(part))
    return path


def unpinned(path, root):
    for part in (path, *path.parents):
        pin = part / ".keep"
        require(not pin.exists() and not pin.is_symlink(), "kept output: " + str(part))
        if part == root:
            break


@contextmanager
def open_directory(path):
    """Anchor deletion to the owned parent, refusing symlinks in every component."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for name in path.parts[1:]:
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


@contextmanager
def lock(path, dry_run=False, meson=False):
    safe_path(path)
    if dry_run and not path.exists():
        yield
        return
    flags = os.O_RDWR | os.O_NOFOLLOW | (0 if dry_run else os.O_CREAT)
    with os.fdopen(os.open(path, flags, 0o600), "r+") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "nonregular lock: " + str(path))
        # Meson uses POSIX record locks; the Aurora Make wrapper uses flock.
        locking = fcntl.lockf if meson else fcntl.flock
        try:
            locking(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("active/locked output: " + str(path.parent)) from error
        yield


def idle(path):
    """Best-effort same-UID cwd/argv check, not an open-FD or all-UID scan.

    This is an idle check, not a scheduler: do not start new work during cleanup.
    Linux is already the supported native build host.
    """
    ancestors = set()
    pid = os.getpid()
    while pid and pid not in ancestors:
        ancestors.add(pid)
        status = Path(f"/proc/{pid}/status").read_text()
        pid = int(re.search(r"^PPid:\s+(\d+)$", status, re.M)[1])
    require(Path("/proc/self").exists(), "cannot check active processes without /proc")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal() or int(proc.name) in ancestors:
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            cwd = Path(os.readlink(proc / "cwd"))
            arguments = (proc / "cmdline").read_bytes().split(b"\0")
        except FileNotFoundError:
            continue  # Process exited during observation.
        except PermissionError as error:
            raise ValueError("cannot check process " + proc.name + " for active output") from error
        used = cwd == path or path in cwd.parents
        for argument in arguments:
            value = os.fsdecode(argument)
            used |= str(path) in value and bool(re.search(re.escape(str(path)) + r"(?:/|$|[,\s])", value))
            # Direct `ninja -C build/meson-...` from the source directory.
            if value and not value.startswith("-"):
                candidate = Path(os.path.abspath(cwd / value))
                used |= candidate == path or path in candidate.parents
        require(not used, "active process " + proc.name + " uses " + str(path))


def read_json(path):
    safe_path(path)
    require(path.is_file(), "missing ownership metadata: " + str(path))
    return json.loads(path.read_text())


def scan_error(error):
    raise error


def clean_build(root, build, ninja, dry_run):
    build = safe_path(build)
    require(build != root and build not in root.parents, "build cannot contain the source checkout")
    require(
        root not in build.parents or root / "build" in build.parents,
        "in-checkout builds must be beneath build/: " + str(build),
    )
    unpinned(build, root)
    identity = build.stat()
    info = read_json(build / "meson-info/meson-info.json")
    require(
        type(info) is dict
        and type(info.get("directories")) is dict
        and info.get("directories", {}).get("source") == str(root)
        and info.get("directories", {}).get("build") == str(build),
        "Meson source/build ownership mismatch: " + str(build),
    )
    project = read_json(build / "meson-info/intro-projectinfo.json")
    require(
        type(project) is dict and project.get("descriptive_name") == "aurora-bootstrap",
        "not an Aurora Meson build: " + str(build),
    )
    safe_path(build / "build.ninja")
    require((build / "build.ninja").is_file(), "missing Ninja build: " + str(build))
    with (
        open_directory(build) as build_fd,
        lock(build / ".aurora-test.lock", dry_run),
        lock(build / "meson-private/meson.lock", dry_run, meson=True),
    ):
        require(os.path.samestat(identity, os.fstat(build_fd)), "build directory changed during validation")
        # Both standard Ninja commands use the same no-follow opened directory.
        # A later pathname/ancestor replacement cannot redirect their working dir.
        command_context = dict(cwd=f"/proc/self/fd/{build_fd}", pass_fds=(build_fd,))
        idle(build)
        # Ninja's clean tool never configures, regenerates, builds or runs tests.
        # Its own dry run includes depfiles as well as tracked objects/binaries.
        preview = subprocess.check_output([ninja, "-n", "-t", "clean"], text=True, **command_context)
        lines = preview.splitlines()
        require(
            len(lines) >= 2 and lines[0] == "Cleaning..." and re.fullmatch(r"\d+ files\.", lines[-1]),
            "unrecognized Ninja clean plan",
        )
        files = []
        for line in lines[1:-1]:
            if line.startswith("Remove "):
                path = safe_path(build / line.removeprefix("Remove "))
                require(path != build and build in path.parents, "Ninja output escapes build: " + str(path))
                require(
                    path.relative_to(build).parts[0] not in ("meson-logs", "meson-info", "meson-private"),
                    "Ninja clean would remove configuration/evidence: " + str(path),
                )
                unpinned(path.parent, build)
                require(path.name != ".keep" and path.is_file(), "kept/nonregular Ninja output: " + str(path))
                files.append(path)
            else:
                raise ValueError("unrecognized Ninja clean plan: " + line)
        require(
            len(files) == int(lines[-1].split()[0]) and len(set(files)) == len(files), "inconsistent Ninja clean plan"
        )
        size = sum(path.stat().st_size for path in files)
        allocated = sum(path.stat().st_blocks * 512 for path in files)
        print(
            f"{'Would clean' if dry_run else 'Cleaning'} {build}: {len(files)} files, "
            f"{size} bytes ({allocated} allocated)",
            flush=True,
        )
        for path in files:
            print("  " + str(path), flush=True)
        if not dry_run:
            subprocess.run([ninja, "-t", "clean"], check=True, **command_context)
        print("Preserved configuration, Meson logs and all untracked test scratch.", flush=True)


def smoke_runs(root, dry_run):
    base = safe_path(root / "build/graphical-smoke")
    if not base.exists():
        print("No managed graphical smoke output.")
        return
    unpinned(base, root)
    require(shutil.rmtree.avoids_symlink_attacks, "symlink-safe directory cleanup is unavailable")
    with open_directory(base) as base_fd, lock(base / ".retention.lock", dry_run):
        passed = []
        for folder in sorted(base.glob("run-*")):
            try:
                safe_path(folder)
                require(folder.is_dir() and re.fullmatch(r"run-[A-Za-z0-9]+", folder.name), "unknown run directory")
                unpinned(folder, base)
                item = read_json(folder / RUN_MARKER)
                require(
                    type(item) is dict
                    and set(item) == {"schema", "status", "finished_ns"}
                    and item["schema"] == RUN_SCHEMA
                    and item["status"] == "passed"
                    and type(item["finished_ns"]) is int,
                    "not a completed successful managed run",
                )
                passed.append((item["finished_ns"], folder))
            except (ValueError, OSError) as error:
                print(f"Preserved {folder}: {error}")
        # Match the existing retention default, but never prune failed runs here.
        for _, folder in sorted(passed, reverse=True)[2:]:
            try:
                unpinned(folder, base)
                idle(folder)
                size = 0
                for directory, dirs, files in os.walk(folder, followlinks=False, onerror=scan_error):
                    for name in [*dirs, *files]:
                        path = safe_path(Path(directory) / name)
                        require(name != ".keep", "keep marker inside run: " + str(path))
                        mode = path.lstat().st_mode
                        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "nonregular run output: " + str(path))
                        if stat.S_ISREG(mode):
                            size += path.stat().st_size
                print(
                    f"{'Would remove' if dry_run else 'Removing'} {folder}: "
                    f"{size} bytes (including successful-run logs)",
                    flush=True,
                )
                safe_path(folder)
                unpinned(folder, base)
            except (ValueError, OSError) as error:
                print(f"Preserved {folder}: {error}")
                continue
            if not dry_run:
                # Propagate deletion failures; do not call a partially removed
                # window preserved or report a successful cleanup command.
                shutil.rmtree(folder.name, dir_fd=base_fd)
        print("Preserved newest two eligible successes, all failed/running/unknown/kept runs and outside output.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="show paths and bytes without deleting or creating files"
    )
    parser.add_argument(
        "--scratch", action="store_true", help="retire old successful smoke windows, keeping newest two"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.scratch:
        print("Scratch scope: older successful managed graphical windows only; unmarked Meson scratch is preserved.")
        smoke_runs(root, args.dry_run)
        return
    supplied = os.environ.get("MESON_BUILD_DIR")
    if supplied is not None:
        require(bool(supplied), "MESON_BUILD_DIR must not be empty")
        builds = [root / supplied]
    else:
        safe_path(root / "build")
        builds = sorted(
            path for path in (root / "build").glob("meson-*") if re.fullmatch(r"meson-[0-9a-f]{16}", path.name)
        )
    if not builds:
        print("No default Meson builds; set MESON_BUILD_DIR to select an existing configured build.")
        return
    ninja = shutil.which("ninja")
    require(ninja is not None, "Ninja is required on PATH for product cleanup")
    for build in builds:
        try:
            clean_build(root, build, ninja, args.dry_run)
        except (ValueError, OSError) as error:
            if supplied is not None:
                raise
            print(f"Preserved {build}: {error}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))

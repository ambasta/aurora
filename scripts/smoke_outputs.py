"""Shared retention for runner-owned smoke outputs, after all work has stopped."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

from qemu_transport import json_object, need


def retained_runs(variable):
    value = os.environ.get(variable, "2")
    need(value == "all" or re.fullmatch(r"[1-9][0-9]{0,2}", value), variable + " must be 1..999 or all")
    return None if value == "all" else int(value)


def pinned(directory):
    pin = directory / ".keep"
    return pin.exists() or pin.is_symlink()


@contextmanager
def retention_lock(parent):
    # Image readers use the same lock when pinning a completed graphical run.
    with os.fdopen(os.open(parent / ".retention.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def discard_files(directory, files):
    """Validate all runner-named files before dropping any; never follow links."""
    files = list(files)
    for path in files:
        need(
            path.is_relative_to(directory) and ".." not in path.relative_to(directory).parts, "not a smoke output file"
        )
        need(
            not any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(directory)),
            "symlink in smoke output path",
        )
        need(not path.exists() or path.is_file(), "nonregular smoke output")
    for path in files:
        path.unlink(missing_ok=True)


class SmokeOutputs:
    def __init__(self, parent, prefix, marker, schema, keep):
        self.parent = Path(parent)
        self.prefix, self.marker, self.schema, self.keep = prefix, marker, schema, keep

    def run_directory(self, directory):
        need(
            directory.parent == self.parent
            and re.fullmatch(re.escape(self.prefix) + r"[A-Za-z0-9_-]+", directory.name),
            "not a smoke run directory",
        )
        need(directory.resolve() == directory, "symlink in smoke run path")
        need(directory.is_dir(), "missing smoke run directory")
        return directory

    def read_marker(self, directory):
        marker = directory / self.marker
        need(not marker.is_symlink() and marker.is_file(), "missing regular smoke ownership marker")
        return json_object(marker.read_bytes())

    def start(self, directory):
        self.run_directory(directory)
        with (directory / self.marker).open("x") as output:
            json.dump(dict(schema=self.schema, status="running"), output)
        if self.keep is None:
            (directory / ".keep").touch(exist_ok=False)

    def finish(self, directory, status, discard):
        self.run_directory(directory)
        with retention_lock(self.parent):
            need(
                self.read_marker(directory) == dict(schema=self.schema, status="running"), "missing active smoke marker"
            )
            # Build, guest cleanup and normal restoration finish before retention.
            (directory / self.marker).write_text(
                json.dumps(
                    dict(schema=self.schema, status="passed" if status == 0 else "failed", finished_ns=time.time_ns())
                )
                + "\n"
            )
            if status == 0 and self.keep is not None and not pinned(directory):
                try:
                    discard(directory)
                except (OSError, ValueError) as error:
                    print("WARN: could not discard successful smoke outputs: " + str(error), file=sys.stderr)
                except KeyboardInterrupt:
                    print("WARN: successful-run cleanup interrupted; remaining outputs preserved", file=sys.stderr)
                    return
            if self.keep is None:
                return
            runs = []
            for folder in self.parent.glob(self.prefix + "*"):
                if folder.is_symlink() or not folder.is_dir() or pinned(folder):
                    continue
                try:
                    self.run_directory(folder)
                    item = self.read_marker(folder)
                except (ValueError, OSError):
                    continue  # Never adopt unknown or incomplete historical output.
                if (
                    set(item) == {"schema", "status", "finished_ns"}
                    and item["schema"] == self.schema
                    and item["status"] == "passed"
                    and type(item["finished_ns"]) is int
                ):
                    runs.append((item["finished_ns"], folder.name, folder))
            for _, _, folder in sorted(runs, reverse=True)[self.keep :]:
                if folder != directory:
                    try:
                        shutil.rmtree(folder)
                    except OSError as error:
                        print("WARN: could not prune " + str(folder) + ": " + str(error), file=sys.stderr)
                    else:
                        print("Pruned older smoke files: " + str(folder), flush=True)

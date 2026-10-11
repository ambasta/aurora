"""Keep the newest successful smoke runs after their builds and guests stop."""

import json
import os
from pathlib import Path
import re
import shutil
import sys

from qemu_transport import need


def retained_runs(variable):
    value = os.environ.get(variable, "2")
    need(value == "all" or re.fullmatch(r"[1-9][0-9]{0,2}", value), variable + " must be 1..999 or all")
    return None if value == "all" else int(value)


def pinned(directory):
    pin = directory / ".keep"
    return pin.exists() or pin.is_symlink()


def discard_files(directory, files):
    """Drop only the named regular files within this run; never follow links."""
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
    def __init__(self, parent, prefix, marker, keep):
        self.parent = Path(parent)
        self.prefix, self.marker, self.keep = prefix, marker, keep

    def run_directory(self, directory):
        need(directory.parent == self.parent and directory.name.startswith(self.prefix), "not a smoke run directory")
        need(directory.is_dir() and not directory.is_symlink(), "missing regular smoke run directory")

    def start(self, directory):
        self.run_directory(directory)
        with (directory / self.marker).open("x") as output:
            json.dump(dict(status="running"), output)
        if self.keep is None:
            (directory / ".keep").touch(exist_ok=False)

    def finish(self, directory, status, discard):
        self.run_directory(directory)
        marker = directory / self.marker
        need(
            marker.is_file() and not marker.is_symlink() and json.loads(marker.read_text()).get("status") == "running",
            "missing active smoke marker",
        )
        if status == 0 and self.keep is not None and not pinned(directory):
            try:
                discard(directory)
            except (OSError, ValueError) as error:
                print("WARN: could not discard successful smoke outputs: " + str(error), file=sys.stderr)
            except KeyboardInterrupt:
                print("WARN: successful-run cleanup interrupted; remaining outputs preserved", file=sys.stderr)
                return
        # Publish completion only after this run no longer needs its captures.
        marker.write_text(json.dumps(dict(status="passed" if status == 0 else "failed")) + "\n")
        if self.keep is None:
            return
        runs = []
        for folder in self.parent.glob(self.prefix + "*"):
            if folder.is_symlink() or not folder.is_dir() or pinned(folder):
                continue
            marker = folder / self.marker
            if marker.is_symlink() or not marker.is_file():
                continue
            try:
                record = json.loads(marker.read_text())
                if isinstance(record, dict) and record.get("status") == "passed":
                    runs.append((marker.stat().st_mtime_ns, folder.name, folder))
            except (ValueError, OSError):
                continue  # Unmarked, malformed, active and failed runs are preserved.
        for _, _, folder in sorted(runs, reverse=True)[self.keep :]:
            if folder == directory:
                continue
            try:
                shutil.rmtree(folder)
            except OSError as error:
                print("WARN: could not prune " + str(folder) + ": " + str(error), file=sys.stderr)
            else:
                print("Pruned older smoke files: " + str(folder), flush=True)

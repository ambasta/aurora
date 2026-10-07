"""Disk accounting for explicitly owned test outputs, including subprocess scratch."""
import json
import os
from pathlib import Path
import shutil
import stat
import sys


def allocated_bytes(*roots):
    """Count allocated blocks once per inode; never follow symbolic links."""
    total = 0
    seen = set()
    pending = []
    for root in roots:
        path = Path(root)
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        pending.append(path)
    while pending:
        path = pending.pop()
        info = path.lstat()
        identity = (info.st_dev, info.st_ino)
        if identity in seen:
            continue
        seen.add(identity)
        total += info.st_blocks * 512
        if stat.S_ISDIR(info.st_mode):
            pending.extend(path.iterdir())
    return total


def free_bytes(root):
    """Use the output filesystem, including before a fresh output root exists."""
    path = Path(root)
    while not path.exists():
        path = path.parent
    return shutil.disk_usage(path).free


def temporary_environment(root, **overrides):
    """Keep child-process temporary files inside this invocation's budget."""
    temporary = Path(root) / 'tmp'
    if temporary.is_symlink():
        raise RuntimeError('owned temporary directory must not be a symlink')
    temporary.mkdir(exist_ok=True)
    return dict(os.environ, **overrides, TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))


def write_checked_receipt(path, record, guard):
    """Charge the receipt itself and never replace an active primary exception."""
    active_error = sys.exc_info()[0] is not None
    try:
        path.write_text(json.dumps(record, indent=2) + '\n')
        guard()
    except Exception as exc:
        record.update(status='failed', receipt_error=str(exc))
        try:
            path.write_text(json.dumps(record, indent=2) + '\n')
        except Exception as write_error:
            print('Failed receipt could not be written: ' + str(write_error), file=sys.stderr)
        if not active_error:
            raise
        print('Secondary receipt/budget failure; primary failure preserved: ' + str(exc), file=sys.stderr)

#!/usr/bin/env python3
"""Retain legacy native gates with selected host tools and kernel-only locking."""

import argparse
from contextlib import nullcontext
import fcntl
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--cxx", required=True)
    parser.add_argument("--compiler", type=Path)
    parser.add_argument("--shared-output", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = args.repo.resolve(strict=True)
    args.build_root.mkdir(parents=True, exist_ok=True)
    cxx = shlex.split(args.cxx)
    if not cxx:
        parser.error("Configured C++ command is empty")
    # Resolve against the incoming PATH before adding a wrapper with the same
    # name. Meson may record a bare g++, which would otherwise exec itself.
    original_path = os.environ.get("PATH", os.defpath)
    executable = shutil.which(cxx[0], path=original_path)
    if executable is None:
        parser.error("Configured C++ executable was not found: " + cxx[0])
    cxx[0] = os.path.abspath(executable)
    # The checked-in wrappers hardcode g++; pin that invocation to the configured
    # Meson native compiler rather than accidentally selecting another GCC on PATH.
    work = Path(tempfile.mkdtemp(prefix="native-tools-", dir=args.build_root))
    completed_successfully = False
    try:
        wrapper = work / "g++"
        # Restore the search path inside the wrapper too, so compiler launchers
        # that look up g++ cannot re-enter this wrapper.
        wrapper.write_text(
            "#!/bin/sh\nPATH=" + shlex.quote(original_path) + "\nexport PATH\nexec " + shlex.join(cxx) + ' "$@"\n'
        )
        wrapper.chmod(0o755)
        env = os.environ.copy()
        env.update(
            CXX=str(wrapper),
            PATH=str(work) + os.pathsep + env.get("PATH", ""),
            TMPDIR=str(work),
            TMP=str(work),
            TEMP=str(work),
            PYTHONDONTWRITEBYTECODE="1",
        )
        compiler = args.compiler.resolve(strict=True) if args.compiler else None
        if compiler:
            env["AURORAC"] = str(compiler)
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if not command:
            parser.error("A native command is required")
        lock = nullcontext()
        if args.shared_output:
            (root / "build").mkdir(exist_ok=True)
            lock = (root / "build/.meson-native.lock").open("a")
        with lock as locked:
            if locked is not None:
                fcntl.flock(locked, fcntl.LOCK_EX)
            status = 0
            status = subprocess.run(command, cwd=root, env=env).returncode
            if status:
                sys.exit(status if status > 0 else 128 - status)
            completed_successfully = True
    finally:
        if completed_successfully and os.environ.get("AURORA_MESON_KEEP_ARTIFACTS") != "1":
            try:
                shutil.rmtree(work)
            except OSError as error:
                print(
                    "Native scratch cleanup incomplete: " + str(work) + ": " + str(error), file=sys.stderr, flush=True
                )
        else:
            print("Retained native scratch: " + str(work), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Retain legacy native gates with selected host tools and kernel-only locking."""

import argparse
from contextlib import nullcontext
import fcntl
import hashlib
import json
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
    parser.add_argument("--bios-image", action="store_true")
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
    with tempfile.TemporaryDirectory(prefix="native-tools-", dir=args.build_root) as temporary:
        work = Path(temporary)
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
        before = hashlib.sha256(compiler.read_bytes()).hexdigest() if compiler else None
        if compiler:
            env["AURORAC"] = str(compiler)
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        if args.bios_image:
            if command or compiler is None:
                parser.error("--bios-image requires --compiler and no command")
            # A normal root native image must never inherit a fault/console profile.
            inherited = [
                name
                for name, value in env.items()
                if value and (name.startswith("KERNEL_TEST_") or name in ("KERNEL_CONSOLE", "KERNEL_USER_PROBE_MODE"))
            ]
            if inherited:
                raise RuntimeError("Unset kernel profile controls for normal BIOS image: " + ", ".join(inherited))
            commands = [["bash", str(root / "scripts/kernel-build.sh")]]
            # kernel-build.sh already invokes the exact kernel-image.py gate.
        else:
            if not command:
                parser.error("A native command is required")
            commands = [command]
        lock = nullcontext()
        if args.shared_output:
            (root / "build").mkdir(exist_ok=True)
            lock = (root / "build/.meson-native.lock").open("a")
        with lock as locked:
            if locked is not None:
                fcntl.flock(locked, fcntl.LOCK_EX)
            status = 0
            try:
                for command in commands:
                    status = subprocess.run(command, cwd=root, env=env).returncode
                    if status:
                        break
            finally:
                if compiler and hashlib.sha256(compiler.read_bytes()).hexdigest() != before:
                    raise RuntimeError("Meson-selected compiler changed during native gate")
            print(
                json.dumps(
                    dict(
                        scope="meson-native-gate",
                        compiler=str(compiler) if compiler else None,
                        observed_compiler_sha256=before,
                        status=status,
                        assurance="Observed artifact only; not an acceptance pin or fresh build",
                    )
                ),
                flush=True,
            )
            if status:
                sys.exit(status if status > 0 else 128 - status)


if __name__ == "__main__":
    main()

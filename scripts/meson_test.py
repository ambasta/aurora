#!/usr/bin/env python3
"""Thin Make convenience entrypoint; Meson/Ninja owns the incremental native graph."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shlex
import shutil

import meson_toolchain

import compiler_contract as contract


def execute(root, scope):
    root = root.resolve(strict=True)
    env = os.environ.copy()
    # Preserve rejecting public controls. This does not build a fresh compiler,
    # produce a qualification receipt, select a historical pin or run old Make.
    controls = argparse.Namespace(goal="test", entry="root", repo_root=root)
    mode, _, _, _ = contract.prepare_controls(controls, env)
    contract.require(
        mode == "developer" and not env.get("AURORA_TEST_CONTEXT"),
        "Use test-acceptance for the separately pinned legacy workflow",
    )
    contract.require(
        not any(env.get(name) for name in (*contract.CAP_CONTROLS, "IR_TEST_CXXFLAGS")),
        "Canonical Meson uses registered full caps and fixture flags; remove legacy overrides",
    )
    contract.require(
        not env.get("SANITIZE") or env["SANITIZE"] == "0",
        "SANITIZE cannot configure fixed Meson targets; use a separate explicit sanitizer build/gate",
    )
    contract.require(
        not env.get("CPPFLAGS") and not env.get("LDFLAGS"),
        "Configure nondefault CPPFLAGS/LDFLAGS directly in a separate Meson build",
    )
    meson = shutil.which("meson")
    contract.require(
        meson,
        "Meson was not found on PATH; install Meson 1.12.1+ and Ninja, then retry (see docs/meson-bootstrap.md)",
    )
    meson = str(Path(meson).absolute())
    cxx = contract.tool_record(contract.parse_cxx(env.get("CXX", "g++")))
    # Reject unsupported search paths before setup without hashing the toolchain.
    for name in meson_toolchain.IMPLICIT_SEARCH_ENV:
        if name in env:
            raise ValueError("Unset " + name + "; use explicit Meson include/link flags in a fresh build directory")
    config = dict(cxx=cxx["resolved"], compiler_sha256=cxx["sha256"], cpp_flags=env.get("CXXFLAGS", ""))
    key = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    # Compiler/flag changes select a new default; backend/runtime changes are
    # rejected by the complete identity check below and need a fresh directory.
    supplied = env.get("MESON_BUILD_DIR")
    build = Path(supplied) if supplied else root / "build" / ("meson-" + key)
    build = (root / build).resolve() if not build.is_absolute() else build.resolve()
    build_jobs = int(env.get("AURORA_BUILD_JOBS", "3"))
    test_jobs = int(env.get("AURORA_TEST_JOBS", "4"))
    contract.require(
        1 <= build_jobs <= 64 and 1 <= test_jobs <= 64,
        "AURORA_BUILD_JOBS and AURORA_TEST_JOBS must be between 1 and 64",
    )
    for name in contract.MAKE_CONTROL:
        env.pop(name, None)
    env["CXX"] = cxx["resolved"]
    try:
        build.mkdir(parents=True, exist_ok=True)
        lock = (build / ".aurora-test.lock").open("a")
    except OSError as error:
        raise contract.ContractError(
            f"Cannot prepare build directory/lock at {build}: {error}. Select a writable MESON_BUILD_DIR."
        ) from error
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise contract.ContractError(
                f"Build directory is already in use: {build}. "
                "Wait for its active build/test command to finish, or set MESON_BUILD_DIR to a different directory."
            ) from error
        except OSError as error:
            raise contract.ContractError(f"Cannot lock {build}: {error}. Check directory/lock permissions.") from error
        if not (build / "build.ninja").exists():
            subprocess.run(
                [meson, "setup", str(build), str(root), "--backend=ninja", "-Dlsp=false"],
                cwd=root,
                env=env,
                check=True,
            )
        configured = json.loads(
            subprocess.check_output([meson, "introspect", str(build), "--compilers"], cwd=root, env=env)
        )
        command = configured["build"]["cpp"]["exelist"]
        contract.require(
            len(command) == 1 and contract.tool_record(command[0])["sha256"] == cxx["sha256"],
            "Configured compiler differs from CXX; select the matching build directory",
        )
        options = json.loads(
            subprocess.check_output([meson, "introspect", str(build), "--buildoptions"], cwd=root, env=env)
        )
        cpp_args = next(item["value"] for item in options if item["name"] == "cpp_args")
        contract.require(
            cpp_args == shlex.split(env.get("CXXFLAGS", "")),
            "Configured cpp_args differ from CXXFLAGS; select matching flags/build directory",
        )
        identity_path = build / "aurora-toolchain.json"
        try:
            configured_identity = json.loads(identity_path.read_text())
        except OSError as error:
            raise contract.ContractError(
                f"Cannot read configured toolchain identity {identity_path}: {error}. "
                "Check read permissions or select a fresh MESON_BUILD_DIR."
            ) from error
        # One complete observation in this wrapper, immediately before compile.
        # Setup and direct Meson builds retain their own independent guards.
        contract.require(
            configured_identity == meson_toolchain.snapshot(command),
            f"Host toolchain changed for {build}; set MESON_BUILD_DIR to a fresh directory to avoid stale objects",
        )
        subprocess.run([meson, "compile", "-C", str(build), "-j", str(build_jobs)], cwd=root, env=env, check=True)
        subprocess.run(
            [
                meson,
                "test",
                "-C",
                str(build),
                "--suite",
                scope,
                "--no-rebuild",
                "--num-processes",
                str(test_jobs),
                "--print-errorlogs",
            ],
            cwd=root,
            env=env,
            check=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--suite", choices=["full", "compiler", "dev", "slow", "integration", "boot"], default="full")
    args = parser.parse_args()
    try:
        execute(args.repo_root, args.suite)
    except OSError as error:
        target = error.filename or os.environ.get("MESON_BUILD_DIR") or args.repo_root
        raise SystemExit(
            f"Cannot run Meson setup/build/test at {target}: {error}. "
            "Check path/tool availability and permissions, or select a fresh writable MESON_BUILD_DIR."
        ) from error


if __name__ == "__main__":
    try:
        main()
    except (contract.ContractError, subprocess.CalledProcessError, ValueError) as error:
        raise SystemExit(str(error))

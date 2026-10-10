#!/usr/bin/env python3
"""Thin Make convenience entrypoint; Meson/Ninja owns the incremental native graph."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
import tempfile

import meson_toolchain
import kernel_profiles

import compiler_contract as contract


def execute(root, scope, targets=(), output=None):
    root = root.resolve(strict=True)
    env = os.environ.copy()
    selected_compiler = None
    if scope is None:
        # Kernel selection is also used by independently supervised acceptance
        # runners. Validate their context before isolating hosted compiler flags.
        if env.get("AURORA_TEST_CONTEXT"):
            context = contract.read_context(env["AURORA_TEST_CONTEXT"], root, env.get("AURORAC"))
            selected_compiler = Path(context["compiler"]["resolved"])
        elif env.get("AURORAC"):
            selected_compiler = Path(env["AURORAC"]).resolve(strict=True)
        if selected_compiler:
            contract.require(
                selected_compiler.is_file() and os.access(selected_compiler, os.X_OK),
                "AURORAC must select an executable compiler",
            )
            # Legacy image recipes never inherited hosted CXXFLAGS. The native
            # graph likewise uses its exact fixed freestanding options.
            env.pop("CXXFLAGS", None)
    else:
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
    cxx = meson_toolchain.selected_tool(contract.parse_cxx(env.get("CXX", "g++")))
    meson_toolchain.explicit_search()
    kernel_images = scope != "compiler"
    # One normal build and one hosted-only compiler build. Other configurations
    # require an explicit directory; Meson/Ninja owns dependency invalidation.
    supplied = env.get("MESON_BUILD_DIR")
    default = "meson" if kernel_images else "meson-compiler"
    build = Path(supplied) if supplied else root / "build" / default
    build = (root / build).resolve() if not build.is_absolute() else build.resolve()
    build_jobs = int(env.get("AURORA_BUILD_JOBS", "3"))
    test_jobs = int(env.get("AURORA_TEST_JOBS", "4"))
    contract.require(
        1 <= build_jobs <= 64 and 1 <= test_jobs <= 64,
        "AURORA_BUILD_JOBS and AURORA_TEST_JOBS must be between 1 and 64",
    )
    for name in contract.MAKE_CONTROL:
        env.pop(name, None)
    env["CXX"] = cxx
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
                [
                    meson,
                    "setup",
                    str(build),
                    str(root),
                    "--backend=ninja",
                    "-Dlsp=false",
                    "-Dkernel_images=" + str(kernel_images).lower(),
                    "-Dkernel_compiler=" + str(selected_compiler or ""),
                ]
                + (["-Duefi_ld=" + env["UEFI_LD"]] if env.get("UEFI_LD") else []),
                cwd=root,
                env=env,
                check=True,
                stdout=output,
            )
        configured = json.loads(
            subprocess.check_output([meson, "introspect", str(build), "--compilers"], cwd=root, env=env)
        )
        command = configured["build"]["cpp"]["exelist"]
        contract.require(
            len(command) == 1 and meson_toolchain.selected_tool(command[0]) == cxx,
            "Configured compiler differs from CXX; select the matching build directory",
        )
        options = json.loads(
            subprocess.check_output([meson, "introspect", str(build), "--buildoptions"], cwd=root, env=env)
        )
        if scope is not None:
            contract.require(
                not next(item["value"] for item in options if item["name"] == "kernel_compiler"),
                "Native aggregate tests require their own compiler; use a separate kernel-only build for AURORAC",
            )
        if selected_compiler:
            contract.require(
                selected_kernel_compiler(build).resolve(strict=True) == selected_compiler,
                "Configured kernel compiler differs from AURORAC; select a fresh matching build directory",
            )
        selected_images = next(item["value"] for item in options if item["name"] == "kernel_images")
        contract.require(
            scope is not None or selected_images,
            "Kernel images disabled: select a build configured with -Dkernel_images=true",
        )
        if env.get("UEFI_LD"):
            selected_pe = next(item["value"] for item in options if item["name"] == "uefi_ld")
            contract.require(
                selected_pe == env["UEFI_LD"],
                "Configured UEFI linker differs from UEFI_LD; select the matching build directory",
            )
        cpp_args = next(item["value"] for item in options if item["name"] == "cpp_args")
        contract.require(
            cpp_args == shlex.split(env.get("CXXFLAGS", "")),
            "Configured cpp_args differ from CXXFLAGS; select matching flags/build directory",
        )
        subprocess.run(
            [meson, "compile", "-C", str(build), "-j", str(build_jobs), *targets],
            cwd=root,
            env=env,
            check=True,
            stdout=output,
        )
        if scope is None:
            if os.environ.get("AURORA_TEST_CONTEXT"):
                contract.read_context(os.environ["AURORA_TEST_CONTEXT"], root, selected_compiler)
            return build
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


def selected_kernel_compiler(build):
    """Read the configured kernel compiler after Meson refreshes introspection."""
    build = Path(build).resolve(strict=True)
    options = json.loads((build / "meson-info/intro-buildoptions.json").read_text())
    values = [entry["value"] for entry in options if entry["name"] == "kernel_compiler"]
    contract.require(
        len(values) == 1 and isinstance(values[0], str),
        "Missing/ambiguous kernel compiler option",
    )
    selected = Path(values[0]) if values[0] else build / "aurorac"
    contract.require(selected.is_absolute(), "Configured kernel compiler must be absolute")
    return selected


def publish_compatibility_compiler(root, build):
    """Keep the ordinary make-all compiler output without a second compilation."""
    directory = root.resolve() / "build"
    contract.require(not directory.is_symlink(), "Refusing a symlinked compatibility build directory")
    directory.mkdir(exist_ok=True)
    destination = directory / "aurorac"
    contract.require(not destination.is_symlink(), "Refusing a symlinked compatibility compiler")
    compiler = selected_kernel_compiler(build)
    if destination.is_file() and destination.read_bytes() == compiler.read_bytes():
        return
    with tempfile.NamedTemporaryFile(prefix=".aurorac-", dir=directory, delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        shutil.copy2(compiler, pending)
        pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--kernel",
        choices=["bios", "uefi"],
        help="Build one native kernel image profile",
    )
    parser.add_argument("--profile", help="Exact named profile; defaults to normal")
    parser.add_argument(
        "--publish-compiler",
        action="store_true",
        help="With --kernel, retain build/aurorac compatibility output",
    )
    parser.add_argument(
        "--print-image-dir",
        action="store_true",
        help="With --kernel, print only its output directory on stdout",
    )
    selection.add_argument(
        "--suite",
        choices=["full", "compiler", "dev", "slow", "integration", "boot"],
        default="full",
    )
    args = parser.parse_args()
    try:
        if args.kernel:
            profile = kernel_profiles.select(args.kernel, os.environ, args.profile or "normal")
            canonical = kernel_profiles.canonical_profile(args.kernel, profile)
            build = execute(
                args.repo_root,
                None,
                ["kernel-" + args.kernel + "-" + profile],
                sys.stderr if args.print_image_dir else None,
            )
            if args.publish_compiler:
                publish_compatibility_compiler(args.repo_root, build)
            directory = build / "kernel-images" / args.kernel / canonical
            contract.require(
                not any(character in str(directory) for character in (",", "\n", "\r")),
                "Kernel image paths cannot contain QEMU drive delimiters or line breaks",
            )
            print(
                str(directory)
                if args.print_image_dir
                else "Built " + args.kernel.upper() + " " + profile + " image in " + str(directory)
            )
        else:
            contract.require(
                not args.print_image_dir and not args.publish_compiler and args.profile is None,
                "--profile/--print-image-dir/--publish-compiler require --kernel",
            )
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

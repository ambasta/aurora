#!/usr/bin/env python3
"""Make convenience entrypoint for the incremental Meson graph and kernel outputs."""

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
        contract.prepare_controls(argparse.Namespace(goal="test", entry="root", repo_root=root), env)
        contract.require(
            not env.get("AURORA_TEST_CONTEXT"),
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
    kernel_images = scope != "compiler"
    # Fail before Meson's setup transcript or any build-directory mutation.
    # Direct Meson setup retains the same independent toolchain gate.
    try:
        meson = meson_toolchain.selected_tool("meson")
        cxx = meson_toolchain.selected_tool(contract.parse_cxx(env.get("CXX", "g++")))
        meson_toolchain.check([cxx], env.get("UEFI_LD") if kernel_images else None)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        reason = str(error)
        if not reason.startswith("BLOCKED:"):
            reason = "BLOCKED: Cannot inspect selected development tools: " + reason
        raise contract.ContractError(
            reason + "\nUse ./scripts/container.sh make test for the supported pinned environment; "
            "see docs/local-development.md."
        ) from error
    # One normal build and one hosted-only compiler build. Other configurations
    # require an explicit directory; Meson/Ninja owns dependency invalidation.
    supplied = env.get("MESON_BUILD_DIR")
    default = "meson" if kernel_images else "meson-compiler"
    build = (root / supplied if supplied else root / "build" / default).resolve()
    defaults = {
        "kernel_images": kernel_images,
        "kernel_compiler": str(selected_compiler or ""),
        "uefi_ld": env.get("UEFI_LD", ""),
    }
    option_args = {
        name: "-D" + name + "=" + (str(value).lower() if isinstance(value, bool) else value)
        for name, value in defaults.items()
    }
    build_jobs = int(env.get("AURORA_BUILD_JOBS", "3"))
    test_jobs = int(env.get("AURORA_TEST_JOBS", "4"))
    contract.require(
        1 <= build_jobs <= 64 and 1 <= test_jobs <= 64,
        "AURORA_BUILD_JOBS and AURORA_TEST_JOBS must be between 1 and 64",
    )
    for name in contract.MAKE_CONTROL:
        env.pop(name, None)
    env["CXX"] = cxx

    def run(*arguments, **kwargs):
        return subprocess.run([meson, *map(str, arguments)], cwd=root, env=env, check=True, **kwargs)

    def introspect(option):
        return json.loads(subprocess.check_output([meson, "introspect", str(build), option], cwd=root, env=env))

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
            run(
                "setup",
                build,
                root,
                "--backend=ninja",
                "-Dlsp=false",
                *option_args.values(),
                stdout=output,
            )
        options = {item["name"]: item["value"] for item in introspect("--buildoptions")}
        missing = {"kernel_compiler", "kernel_images", "uefi_ld", "cpp_args"} - options.keys()
        migrate = not supplied and missing and missing <= {"kernel_compiler", "kernel_images", "uefi_ld"}
        contract.require(
            not missing or migrate,
            "Missing Meson build options: " + ", ".join(sorted(missing)) + "; select a fresh matching MESON_BUILD_DIR",
        )
        command = introspect("--compilers")["build"]["cpp"]["exelist"]
        contract.require(
            len(command) == 1 and meson_toolchain.selected_tool(command[0]) == cxx,
            "Configured compiler differs from CXX; select the matching build directory",
        )
        contract.require(
            options.get("kernel_compiler", defaults["kernel_compiler"]) == defaults["kernel_compiler"],
            "Native aggregate tests require their own compiler; use a separate kernel-only build for AURORAC"
            if scope is not None
            else "Configured kernel compiler differs from the requested AURORAC/native selection; "
            "select a fresh matching MESON_BUILD_DIR",
        )
        contract.require(
            scope is not None or options.get("kernel_images", kernel_images),
            "Kernel images disabled: select a build configured with -Dkernel_images=true",
        )
        if env.get("UEFI_LD"):
            contract.require(
                options.get("uefi_ld", env["UEFI_LD"]) == env["UEFI_LD"],
                "Configured UEFI linker differs from UEFI_LD; select the matching build directory",
            )
        contract.require(
            options["cpp_args"] == shlex.split(env.get("CXXFLAGS", "")),
            "Configured cpp_args differ from CXXFLAGS; select matching flags/build directory",
        )
        if migrate:
            # New project options need regeneration, not deletion of the build,
            # its held lock, retained scratch, or user files. Keep existing options.
            # Meson must discover new options before accepting their -D values.
            run("setup", build, root, "--reconfigure", stdout=output)
            options = {item["name"]: item["value"] for item in introspect("--buildoptions")}
            changes = [option_args[name] for name in sorted(missing) if options.get(name) != defaults[name]]
            if changes:
                run("setup", build, root, "--reconfigure", *changes, stdout=output)
                options = {item["name"]: item["value"] for item in introspect("--buildoptions")}
            contract.require(
                all(options.get(name) == defaults[name] for name in missing),
                "Meson reconfiguration did not restore requested build options",
            )
        # Meson's generated aggregate covers declared test dependencies, including
        # non-default fixtures. Build it with our explicit jobs bound before tests.
        build_targets = list(targets) if scope is None else ["--ninja-args=meson-test-prereq"]
        run("compile", "-C", build, "-j", build_jobs, *build_targets, stdout=output)
        if scope is None:
            if os.environ.get("AURORA_TEST_CONTEXT"):
                contract.read_context(os.environ["AURORA_TEST_CONTEXT"], root, selected_compiler)
            return build
        run(
            "test",
            "-C",
            build,
            "--suite",
            scope,
            "--no-rebuild",
            "--num-processes",
            test_jobs,
            "--print-errorlogs",
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

#!/usr/bin/env python3
"""Make convenience entrypoint for the incremental Meson graph and kernel outputs."""

import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import subprocess
import shlex
import shutil
import sys
import tempfile

import meson_toolchain
import bootstrap
import kernel_profiles

import compiler_contract as contract


HOST_RESERVE_MIB = 2048
# Sizing allowances, not limits: measured compiler peaks approach 1.7 GiB;
# native-test child peaks approach 0.5 GiB and their compilers run sequentially.
JOB_MEMORY_MIB = {"build": 2048, "test": 1024}


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


def admitted_jobs(phase, ceiling):
    try:
        cpus = max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        cpus = 1
    available = available_memory_mib()
    cgroup = cgroup_memory_mib()
    allowance = JOB_MEMORY_MIB[phase]
    headroom = min((value for value in (available, cgroup) if value is not None), default=None)
    if headroom is None:
        jobs = 1
        observation = "MemAvailable unavailable; serial fallback"
    else:
        usable = headroom - HOST_RESERVE_MIB
        contract.require(
            usable >= allowance,
            f"Insufficient observed memory for {phase}: {headroom} MiB headroom; "
            f"need {HOST_RESERVE_MIB} MiB host reserve plus {allowance} MiB per job",
        )
        jobs = min(ceiling, cpus, usable // allowance)
        observation = f"MemAvailable={available} MiB, reserve={HOST_RESERVE_MIB} MiB, estimate={allowance} MiB/job"
        if available is None:
            jobs = 1
            observation += "; host observation unavailable, serial fallback"
    observation += f", cgroup-v2 headroom={cgroup} MiB" if cgroup is not None else ", no visible finite cgroup-v2 bound"
    print(
        f"Aurora {phase}: {jobs} jobs (CPU affinity={cpus}, ceiling={ceiling}; {observation}). "
        "Sizing only, not an aggregate memory cap.",
        file=sys.stderr,
    )
    return jobs


def execute(root, scope, targets=(), output=None, *, build_only=False, tests=()):
    root = root.resolve(strict=True)
    env = os.environ.copy()
    contract.require(not (build_only and tests), "Choose build-only targets or named tests")
    contract.require(not build_only or scope == "compiler", "Build-only targets require compiler scope")
    contract.require(
        not build_only or bool(targets) and set(targets) <= {"aurorac", "aurora-fmt"},
        "Build-only targets are aurorac and aurora-fmt",
    )
    contract.require(
        all(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) for name in tests),
        "Named tests require exact Meson names; patterns and options are unsupported",
    )
    selected_compiler = None
    if scope is None:
        # A supervising caller owns its receipt checks and supplies AURORAC.
        if env.get("AURORAC"):
            selected_compiler = Path(env["AURORAC"]).resolve(strict=True)
        if selected_compiler:
            contract.require(
                selected_compiler.is_file() and os.access(selected_compiler, os.X_OK),
                "AURORAC must select an executable compiler",
            )
            # Legacy image recipes never inherited hosted CXXFLAGS. The native
            # graph likewise uses its exact fixed freestanding options.
            env.pop("CXXFLAGS", None)
    # These settings belonged to the removed Make recipes. Do not silently ignore
    # even an explicitly empty output/path setting on the ordinary graph.
    unsupported = ("OUT", "FORMAT_OUT", "LEXER_EVENTS")
    if scope is not None:
        unsupported += (
            *contract.SELECTORS,
            *contract.PINS,
            "ACCEPTANCE_COMPILER",
            "ACCEPTANCE_COMPILER_SHA256",
            "UTF8_LINES_ARTIFACT_PARENT",
            "UTF8_RANGE_ARTIFACT_PARENT",
            "XFS_ROOT_REPO",
            "XFS_ROOT_FIXTURES",
            "XFS_ROOT_ARTIFACT_PARENT",
            "AURORA_TEST_MODE",
            "AURORA_TEST_COMPILER",
            "AURORA_TEST_IDENTITY_ARGS",
        )
    supplied_unsupported = sorted({name for name in unsupported if name in env})
    contract.require(
        not supplied_unsupported,
        "Unsupported legacy controls: "
        + ", ".join(supplied_unsupported)
        + "; use a configured MESON_BUILD_DIR (compatibility outputs: build/aurorac and build/aurora-fmt)",
    )
    if scope is not None:
        contract.selected_flag_vectors(env)
        for name in (*contract.OPAQUE_ENV, *contract.TEST_FLAGS, "IR_TEST_BUILD_PREFIX"):
            contract.require(not env.get(name), "Unsupported Meson environment override: " + name)
    contract.require(
        not any(env.get(name) for name in contract.CAP_CONTROLS) and (scope is None or not env.get("IR_TEST_CXXFLAGS")),
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
    # BOOTSTRAP_COMPILER selects the pinned checkpoint; HISTORICAL_ORACLE the
    # optional historical C++ emitter. Meson checks both against checkpoint.json.
    requested = {
        name: env.get(variable)
        for name, variable in (("bootstrap_compiler", "BOOTSTRAP_COMPILER"), ("historical_oracle", "HISTORICAL_ORACLE"))
        if env.get(variable) is not None
    }
    for name, value in requested.items():
        contract.require(
            Path(value).is_absolute(),
            name.upper() + " must be an absolute path; see compiler/README.md#source-bootstrap",
        )
    supplied = env.get("MESON_BUILD_DIR")
    default = "meson" if kernel_images else "meson-compiler"
    build = (root / supplied if supplied else root / "build" / default).resolve()
    contract.require(
        (build / "build.ninja").is_file(),
        "Checkpoint-backed Meson setup required at "
        + str(build)
        + "; first follow compiler/README.md#source-bootstrap, then run "
        + shlex.join(
            [
                meson,
                "setup",
                str(build),
                str(root),
                "-Dbootstrap_compiler=" + requested.get("bootstrap_compiler", "/absolute/path/to/checkpoint/aurorac"),
            ]
        )
        + (" -Dkernel_images=false" if not kernel_images else "")
        + "; retry with MESON_BUILD_DIR="
        + shlex.quote(str(build)),
    )
    defaults = {
        "kernel_images": kernel_images,
        "kernel_compiler": str(selected_compiler or ""),
        "uefi_ld": env.get("UEFI_LD", ""),
    }
    build_selection = env.get("AURORA_BUILD_JOBS", "auto")
    test_selection = env.get("AURORA_TEST_JOBS", "auto")
    build_jobs = 64 if build_selection == "auto" else int(build_selection)
    test_jobs = 64 if test_selection == "auto" else int(test_selection)
    contract.require(
        1 <= build_jobs <= 64 and 1 <= test_jobs <= 64,
        "AURORA_BUILD_JOBS and AURORA_TEST_JOBS must be auto or between 1 and 64",
    )
    for name in contract.MAKE_CONTROL:
        env.pop(name, None)
    env["CXX"] = cxx

    def run(*arguments, **kwargs):
        return subprocess.run([meson, *map(str, arguments)], cwd=root, env=env, check=True, **kwargs)

    def introspect(option):
        return json.loads(subprocess.check_output([meson, "introspect", str(build), option], cwd=root, env=env))

    try:
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
        options = {item["name"]: item["value"] for item in introspect("--buildoptions")}
        # Meson rejects an unknown -D on reconfigure, so a directory configured
        # before the single-checkpoint options existed must be wiped.
        contract.require(
            "historical_oracle" in options,
            f"{build} predates the single checkpoint; run "
            + shlex.join(
                [
                    meson,
                    "setup",
                    "--wipe",
                    str(build),
                    str(root),
                    "-Dbootstrap_compiler="
                    + requested.get("bootstrap_compiler", "/absolute/path/to/checkpoint/aurorac"),
                ]
            ),
        )
        missing = {"kernel_compiler", "kernel_images", "uefi_ld", "cpp_args"} - options.keys()
        contract.require(
            not missing,
            "Missing Meson build options: "
            + ", ".join(sorted(missing))
            + "; configure a checkpoint-backed MESON_BUILD_DIR using compiler/README.md#source-bootstrap",
        )
        command = introspect("--compilers")["build"]["cpp"]["exelist"]
        contract.require(
            len(command) == 1 and meson_toolchain.selected_tool(command[0]) == cxx,
            "Configured compiler differs from CXX; select the matching build directory",
        )
        expected_options = {**defaults, "cpp_args": shlex.split(env.get("CXXFLAGS", ""))}
        if scope is not None:
            expected_options.pop("kernel_images")
        # The UEFI linker only matters to image builds; a compiler-only build has none.
        if not kernel_images or not env.get("UEFI_LD"):
            expected_options.pop("uefi_ld")
        for name, expected in expected_options.items():
            contract.require(
                options.get(name, expected) == expected,
                f"Configured {name} differs from request ({options.get(name)!r} != {expected!r}); "
                "select a matching MESON_BUILD_DIR",
            )
        changed = {name: value for name, value in requested.items() if options.get(name) != value}
        if changed:
            setup = ["setup", "--reconfigure", str(build), *(f"-D{name}={value}" for name, value in changed.items())]
            contract.require(
                not supplied,
                "Configured checkpoint/oracle differs from the request; run "
                + shlex.join([meson, *setup])
                + " or select a matching MESON_BUILD_DIR",
            )
            try:
                bootstrap.select(
                    requested.get("bootstrap_compiler", options["bootstrap_compiler"]),
                    requested.get("historical_oracle", options["historical_oracle"]),
                )
            except ValueError as error:
                raise contract.ContractError(str(error)) from error
            run(*setup)
            options = {item["name"]: item["value"] for item in introspect("--buildoptions")}
            contract.require(
                all(options.get(name) == value for name, value in requested.items()),
                "Meson did not apply the requested checkpoint/oracle",
            )
        if tests:
            # Refresh configuration before selecting dependencies, as Meson's
            # own test runner does. This target does not build test fixtures.
            run(
                "compile",
                "-C",
                build,
                "-j",
                admitted_jobs("build", build_jobs),
                "--ninja-args=build.ninja",
                stdout=output,
            )
            registered_tests = introspect("--tests")
            contract.require(
                isinstance(registered_tests, list)
                and all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in registered_tests),
                "Malformed Meson test introspection",
            )
            registered = {item["name"] for item in registered_tests}
            unknown = sorted(set(tests) - registered)
            contract.require(
                not unknown,
                "Unregistered Meson tests: "
                + ", ".join(unknown)
                + "; inspect meson test -C "
                + shlex.quote(str(build))
                + " --list",
            )
            dependencies = set()
            for test in registered_tests:
                if test["name"] in tests:
                    declared = test.get("depends")
                    contract.require(
                        isinstance(declared, list) and all(isinstance(d, str) and d for d in declared),
                        "Malformed Meson dependencies for test: " + test["name"],
                    )
                    dependencies.update(declared)
            # Mirror Meson's selected-test rebuild mapping, preserving every
            # output of custom targets as well as ordinary executable targets.
            target_records = introspect("--targets") if dependencies else []
            contract.require(
                isinstance(target_records, list) and all(isinstance(target, dict) for target in target_records),
                "Malformed Meson target introspection",
            )
            filenames = set()
            for dependency in sorted(dependencies):
                matches = [target for target in target_records if target.get("id") == dependency]
                contract.require(len(matches) == 1, "Unknown or ambiguous Meson test dependency: " + dependency)
                outputs = matches[0].get("filename")
                contract.require(
                    isinstance(outputs, list)
                    and outputs
                    and all(isinstance(name, str) and name and "\0" not in name for name in outputs),
                    "Malformed Meson test dependency outputs: " + dependency,
                )
                for name in outputs:
                    path = Path(name).resolve()
                    contract.require(
                        Path(name).is_absolute() and path != build and path.is_relative_to(build),
                        "Meson test dependency output outside build directory: " + name,
                    )
                    filenames.add(str(path.relative_to(build)))
            # An empty Ninja target list would build 'all', not no prerequisites.
            if filenames:
                run(
                    "compile",
                    "-C",
                    build,
                    "-j",
                    admitted_jobs("build", build_jobs),
                    "--ninja-args=" + json.dumps(["--", *sorted(filenames)]),
                    stdout=output,
                )
        else:
            # Complete suite selections retain their complete prerequisite target.
            build_targets = list(targets) if scope is None or build_only else ["--ninja-args=meson-test-prereq"]
            run("compile", "-C", build, "-j", admitted_jobs("build", build_jobs), *build_targets, stdout=output)
        if scope is None or build_only:
            return build
        run(
            "test",
            "-C",
            build,
            *([] if tests else ["--suite", scope]),
            "--no-rebuild",
            "--num-processes",
            admitted_jobs("test", test_jobs),
            "--print-errorlogs",
            *tests,
        )
        return build


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


def publish_compatibility_output(root, source, name):
    """Atomically preserve the documented path without a second compilation."""
    contract.require(name in ("aurorac", "aurora-fmt"), "Unsupported compatibility output name")
    directory = root.resolve() / "build"
    contract.require(not directory.is_symlink(), "Refusing a symlinked compatibility build directory")
    directory.mkdir(exist_ok=True)
    destination = directory / name
    contract.require(not destination.is_symlink(), "Refusing a symlinked compatibility output: " + name)
    compiler = Path(source).resolve(strict=True)
    contract.require(compiler.is_file() and os.access(compiler, os.X_OK), "Executable compatibility output required")
    if destination.is_file() and destination.read_bytes() == compiler.read_bytes():
        return
    with tempfile.NamedTemporaryFile(prefix="." + name + "-", dir=directory, delete=False) as temporary:
        pending = Path(temporary.name)
    try:
        shutil.copy2(compiler, pending)
        pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)


def publish_compatibility_compiler(root, build):
    publish_compatibility_output(root, selected_kernel_compiler(build), "aurorac")


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
        help="With --kernel or --build-only aurorac, retain build/aurorac",
    )
    parser.add_argument(
        "--print-image-dir",
        action="store_true",
        help="With --kernel, print only its output directory on stdout",
    )
    selection.add_argument(
        "--suite",
        choices=["merge", "release", "full", "compiler", "dev", "slow", "integration", "boot", "exhaustive", "guest"]
        + ["guest-" + family for family in kernel_profiles.GUEST_FAMILIES],
    )
    selection.add_argument("--build-only", nargs="+", choices=["aurorac", "aurora-fmt"])
    selection.add_argument("--tests", nargs="+", help="Run exact registered names in the hosted-only build")
    parser.add_argument("--publish-formatter", action="store_true", help="Retain build/aurora-fmt after its build")
    args = parser.parse_args()
    try:
        contract.require(
            not args.publish_formatter or args.build_only and "aurora-fmt" in args.build_only,
            "--publish-formatter requires --build-only aurora-fmt",
        )
        contract.require(
            not args.publish_compiler or args.kernel or args.build_only and "aurorac" in args.build_only,
            "--publish-compiler requires --kernel or --build-only aurorac",
        )
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
                not args.print_image_dir and args.profile is None,
                "--profile/--print-image-dir require --kernel",
            )
            build = execute(
                args.repo_root,
                "compiler" if args.build_only or args.tests else args.suite or "full",
                args.build_only or (),
                build_only=bool(args.build_only),
                tests=args.tests or (),
            )
            if args.publish_compiler:
                publish_compatibility_output(args.repo_root, build / "aurorac", "aurorac")
            if args.publish_formatter:
                publish_compatibility_output(args.repo_root, build / "aurora-fmt", "aurora-fmt")
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

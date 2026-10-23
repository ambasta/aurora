#!/usr/bin/env python3
"""Separate configure-time historical validation from current invocation checks.

The selection file is ordinary Meson configuration, not a reconstruction receipt,
artifact cache or qualification result. The original receipt and driver remain
unchanged. Historical evidence is tracked by configure dependencies; each use
checks selected bytes and freshly resolves their runtime, before and after use.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import bootstrap

ROLES = ("build_predecessor", "historical_cpp_oracle")
RUNTIME_ENV = ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT")


def runtime_identity(compiler):
    """Inspect trusted selected executables, including newly shadowed libraries."""
    ldd = bootstrap.meson_toolchain.selected_tool("ldd")
    paths = {ldd, sys.executable}
    for executable in (compiler, sys.executable):
        with Path(executable).open("rb") as stream:
            bootstrap.require(stream.read(4) == b"\x7fELF", "bootstrap runtime must be ELF: " + str(executable))
        result = subprocess.run([ldd, str(executable)], capture_output=True, text=True, timeout=10, check=True)
        bootstrap.require("not found" not in result.stdout, "missing bootstrap runtime: " + str(executable))
        libraries = re.findall(r"(?:=>\s+|^\s*)(/[^\s]+)", result.stdout, re.MULTILINE)
        bootstrap.require(libraries, "unresolved bootstrap runtime: " + str(executable))
        paths.update(libraries)
    return [bootstrap.file_identity(path) for path in sorted(paths)]


def historical_dependencies(value):
    records = list(value["tools"]["files"])
    for stage in value["stages"]:
        records += [stage["artifact"], *stage["inputs"], *(command["log"] for command in stage["commands"])]
    return {record[key] for record in records for key in ("path", "resolved")}


def depfile_escape(path):
    value = str(path)
    bootstrap.require(not any(character in value for character in "\n\r\t"), "unsupported dependency path")
    for character, escaped in (("\\", "\\\\"), ("$", "$$"), (" ", "\\ "), ("#", "\\#"), (":", "\\:")):
        value = value.replace(character, escaped)
    return value


def configure(compiler, sha256, receipt, output, depfile):
    identities = {
        "receipt": bootstrap.file_identity(receipt),
        "pin": bootstrap.file_identity(bootstrap.MANIFEST),
        "driver": bootstrap.file_identity(bootstrap.__file__),
        "guard": bootstrap.file_identity(__file__),
        "toolchain": bootstrap.file_identity(bootstrap.meson_toolchain.__file__),
    }
    value = bootstrap.verify(compiler, sha256, receipt)
    roles = {
        role: next(stage["artifact"] for stage in value["stages"] if stage["source"]["name"] == value["route"][role])
        for role in ROLES
    }
    runtimes = {role: runtime_identity(record["path"]) for role, record in roles.items()}
    for record in [*identities.values(), *roles.values()]:
        bootstrap.check_file(record)
    dependencies = historical_dependencies(value)
    for record in [*identities.values(), *(record for records in runtimes.values() for record in records)]:
        dependencies.update((record["path"], record["resolved"]))
    # Meson intentionally omits files under its current build root from build
    # definition dependencies. Reject that unsupported placement, never pretend
    # the historical evidence is watched there.
    build = output.resolve().parent
    bootstrap.require(
        all(not Path(path).absolute().is_relative_to(build) for path in dependencies),
        "historical evidence/runtime must be outside the active Meson build directory",
    )
    selection = {
        "kind": "configured-bootstrap-selection",
        "source_root": str(bootstrap.ROOT),
        "identities": identities,
        "roles": roles,
        "runtimes": runtimes,
        "environment": {name: os.environ.get(name) for name in RUNTIME_ENV},
    }
    depfile.write_text(depfile_escape(output.name) + ": " + " ".join(map(depfile_escape, sorted(dependencies))) + "\n")
    bootstrap.write_json(output, selection)
    return selection


def configured_selection_sha256(build):
    """Read the literal pin from Meson's generated frontend command, not its input."""
    targets = json.loads((Path(build) / "meson-info/intro-targets.json").read_text())
    commands = [
        source["compiler"]
        for target in targets
        if target["name"] == "hosted-frontend-assembly"
        for source in target["target_sources"]
    ]
    bootstrap.require(len(commands) == 1, "configured frontend guard command is missing or ambiguous")
    bootstrap.require("--" in commands[0], "configured frontend guard separator is missing")
    command = commands[0][: commands[0].index("--")]
    bootstrap.require(
        str(Path(__file__).resolve()) in command and "run" in command, "configured frontend guard missing"
    )
    bootstrap.require(command.count("--selection-sha256") == 1, "configured selection SHA256 literal is missing")
    bootstrap.require(command.count("--selection") == 1, "configured selection path is missing")
    bootstrap.require(
        all(command.index(flag) + 1 < len(command) for flag in ("--selection", "--selection-sha256")),
        "configured selection argument is missing",
    )
    bootstrap.require(
        Path(command[command.index("--selection") + 1]) == Path(build) / "bootstrap-selection.json",
        "configured selection path differs from the build directory",
    )
    sha256 = command[command.index("--selection-sha256") + 1]
    bootstrap.require(re.fullmatch(r"[0-9a-f]{64}", sha256), "configured selection SHA256 literal is invalid")
    return sha256


def check(selection, compiler, sha256, receipt, *, selection_sha256, role="build_predecessor"):
    bootstrap.require(
        re.fullmatch(r"[0-9a-f]{64}", selection_sha256 or ""),
        "mandatory configured selection SHA256 is missing or invalid",
    )
    data = Path(selection).read_bytes()
    bootstrap.require(
        hashlib.sha256(data).hexdigest() == selection_sha256, "configured bootstrap selection SHA256 mismatch"
    )
    bootstrap.require(role in ROLES, "unknown configured bootstrap role")
    bootstrap.require(re.fullmatch(r"[0-9a-f]{64}", sha256 or ""), "mandatory SHA256 is missing or invalid")
    bootstrap.require(compiler and Path(compiler).is_absolute(), "absolute predecessor path required")
    bootstrap.require(receipt and Path(receipt).is_absolute(), "absolute reconstruction receipt required")
    value = json.loads(data)
    bootstrap.require(
        value["kind"] == "configured-bootstrap-selection" and value["source_root"] == str(bootstrap.ROOT),
        "bootstrap selection belongs to a different configuration",
    )
    selected = value["roles"][role]
    bootstrap.require(
        selected["path"] == compiler
        and selected["sha256"] == sha256
        and value["identities"]["receipt"]["path"] == receipt,
        "configured bootstrap selection differs; reconfigure Meson",
    )
    expected_paths = {
        "pin": bootstrap.MANIFEST,
        "driver": bootstrap.__file__,
        "guard": __file__,
        "toolchain": bootstrap.meson_toolchain.__file__,
        "receipt": receipt,
    }
    for name, path in expected_paths.items():
        bootstrap.require(
            value["identities"][name] == bootstrap.file_identity(path), "configured bootstrap identity changed: " + name
        )
    bootstrap.check_file(selected)
    bootstrap.require(os.access(compiler, os.X_OK), "selected predecessor is not executable")
    bootstrap.meson_toolchain.explicit_search()
    for name in ("GCC_EXEC_PREFIX", "COMPILER_PATH", "LD_PRELOAD", "LD_AUDIT"):
        bootstrap.require(not os.environ.get(name), "unset bootstrap environment override: " + name)
    bootstrap.require(
        {name: os.environ.get(name) for name in RUNTIME_ENV} == value["environment"],
        "bootstrap runtime environment changed",
    )
    runtime = value["runtimes"][role]
    for record in runtime:
        bootstrap.check_file(record)
    for executable in (bootstrap.meson_toolchain.selected_tool("ldd"), sys.executable):
        bootstrap.require(
            bootstrap.file_identity(executable) in runtime, "bootstrap runtime inspector/interpreter changed"
        )
    bootstrap.require(runtime_identity(compiler) == runtime, "configured bootstrap runtime changed")
    return value


def run(selection, compiler, sha256, receipt, command, *, selection_sha256, role="build_predecessor"):
    bootstrap.require(command, "missing guarded command")
    check(selection, compiler, sha256, receipt, selection_sha256=selection_sha256, role=role)
    try:
        result = subprocess.run(command)
    finally:
        check(selection, compiler, sha256, receipt, selection_sha256=selection_sha256, role=role)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("configure", "check", "run"):
        sub = subparsers.add_parser(action)
        sub.add_argument("--compiler", required=True)
        sub.add_argument("--sha256", required=True)
        sub.add_argument("--receipt", required=True)
        if action == "configure":
            sub.add_argument("--output", required=True, type=Path)
            sub.add_argument("--depfile", required=True, type=Path)
        else:
            sub.add_argument("--selection", required=True, type=Path)
            sub.add_argument("--selection-sha256", required=True)
            sub.add_argument("--role", choices=ROLES, default="build_predecessor")
        if action == "run":
            sub.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.action == "configure":
        configure(args.compiler, args.sha256, args.receipt, args.output, args.depfile)
    elif args.action == "check":
        value = check(
            args.selection,
            args.compiler,
            args.sha256,
            args.receipt,
            selection_sha256=args.selection_sha256,
            role=args.role,
        )
        oracle = value["roles"]["historical_cpp_oracle"]
        print(oracle["path"] + "\n" + oracle["sha256"])
    else:
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        status = run(
            args.selection,
            args.compiler,
            args.sha256,
            args.receipt,
            command,
            selection_sha256=args.selection_sha256,
            role=args.role,
        )
        if status:
            # The guarded command reported its own failure; the predecessor passed both checks.
            sys.exit(bootstrap.child_status(status))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        reason = str(error)
        if "To fix:" not in reason:
            reason += "; reconfigure Meson with the verified predecessor selection"
        sys.exit("bootstrap guard: " + reason)

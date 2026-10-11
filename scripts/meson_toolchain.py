#!/usr/bin/env python3
"""Check selected development tools without build artifacts or byte receipts."""

import argparse
import os
import shlex
import shutil
import subprocess


IMPLICIT_SEARCH_ENV = ("CPATH", "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH", "LIBRARY_PATH")


def explicit_search():
    for name in IMPLICIT_SEARCH_ENV:
        if name in os.environ:
            raise ValueError(
                "BLOCKED: Unset " + name + "; use explicit Meson include/link flags in a fresh build directory"
            )


def selected_tool(name):
    selected = shutil.which(name)
    if selected is None:
        raise ValueError(
            "BLOCKED: Missing development tool: " + name + "; select the pinned image or local tool prefix on PATH"
        )
    return os.path.realpath(selected)


def check(cxx, pe_linker=None):
    explicit_search()
    if not cxx:
        raise ValueError("BLOCKED: Missing configured C++ command")
    commands = [
        (cxx, "-dumpfullversion", "16.2.0"),
        ([selected_tool("gcc")], "-dumpfullversion", "16.2.0"),
    ]
    commands += [
        ([selected_tool(name)], "--version", "2.47") for name in ("as", "ld", "nm", "objcopy", "objdump", "readelf")
    ]
    commands += [
        ([selected_tool("meson")], "--version", "1.12.1"),
        ([selected_tool("ninja")], "--version", "1.13.2"),
    ]
    if pe_linker:
        commands.append(([selected_tool(pe_linker)], "--version", "2.47"))
    for command, flag, expected in commands:
        lines = subprocess.check_output([*command, flag], text=True, stderr=subprocess.STDOUT, timeout=10).splitlines()
        version = lines[0] if lines else ""
        if not version or version.split()[-1] != expected:
            raise ValueError("BLOCKED: " + shlex.join(command) + ": require " + expected + ", got " + version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", required=True)
    parser.add_argument("--pe-linker")
    args = parser.parse_args()
    check(shlex.split(args.cxx), args.pe_linker)


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        raise SystemExit(str(error))
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemExit("BLOCKED: Cannot inspect selected development tools: " + str(error))

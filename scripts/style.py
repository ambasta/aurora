#!/usr/bin/env python3
"""Run pinned host formatters on explicitly selected source files."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {"ruff": "0.16.7", "clang-format": "22.1.8"}
CPP_SUFFIXES = {".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".h"}


def select_files(paths):
    python_files = set()
    cpp_files = set()
    for name in paths:
        path = Path(name).resolve(strict=True)
        relative = path.relative_to(ROOT)
        if not path.is_file() or {"build", "evidence", ".git", ".venv"}.intersection(relative.parts):
            raise ValueError(f"not an editable host source file: {name}")
        if path.suffix == ".py":
            python_files.add(str(path))
        elif path.suffix in CPP_SUFFIXES:
            cpp_files.add(str(path))
        else:
            raise ValueError(f"unsupported host source extension: {name}; .au needs Aurora tooling")
    return sorted(python_files), sorted(cpp_files)


def find_tool(name):
    executable = shutil.which(name)
    if executable is None:
        raise ValueError(f"missing {name} {VERSIONS[name]}; see docs/style.md")
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True, timeout=10, cwd=ROOT)
    words = result.stdout.split()
    if name == "ruff":
        matches = words == ["ruff", VERSIONS[name]]
    else:
        matches = "version" in words and words[words.index("version") + 1 :][:1] == [VERSIONS[name]]
    if not matches:
        raise ValueError(f"expected {name} {VERSIONS[name]}, got {result.stdout.strip()!r}")
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "format"))
    parser.add_argument(
        "files", nargs="+", help="explicit Python or C++ source files, relative to the current directory"
    )
    args = parser.parse_args()
    python_files, cpp_files = select_files(args.files)
    # Resolve every dependency before format mode can modify any selected file.
    ruff = find_tool("ruff") if python_files else None
    clang_format = find_tool("clang-format") if cpp_files else None
    commands = []
    if python_files:
        options = ["--config", str(ROOT / "ruff.toml"), "--no-cache"]
        check = ["--check"] if args.mode == "check" else []
        commands.append([ruff, "format", *options, *check, "--", *python_files])
        commands.append([ruff, "check", *options, "--", *python_files])
    if cpp_files:
        options = ["--dry-run", "--Werror"] if args.mode == "check" else ["-i"]
        commands.append([clang_format, f"--style=file:{ROOT / '.clang-format'}", *options, "--", *cpp_files])
    failed = False
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, timeout=120)
        failed = failed or result.returncode != 0
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"style: {error}", file=sys.stderr)
        sys.exit(2)

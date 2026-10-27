#!/usr/bin/env python3
"""Run pinned host formatters on selected or every tracked host source, or check
every tracked Aurora product source with aurora-fmt."""

import argparse
import concurrent.futures
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {"ruff": "0.16.7", "clang-format": "22.1.8"}
CPP_SUFFIXES = {".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx", ".h"}
SKIPPED = {"build", "evidence", ".git", ".venv"}


def select_files(paths):
    python_files = set()
    cpp_files = set()
    for name in paths:
        path = Path(name).resolve(strict=True)
        relative = path.relative_to(ROOT)
        if not path.is_file() or SKIPPED.intersection(relative.parts):
            raise ValueError(f"not an editable host source file: {name}")
        if path.suffix == ".py":
            python_files.add(str(path))
        elif path.suffix in CPP_SUFFIXES:
            cpp_files.add(str(path))
        else:
            raise ValueError(f"unsupported host source extension: {name}; .au needs Aurora tooling")
    return sorted(python_files), sorted(cpp_files)


def indexed_paths():
    """Tracked paths from the checkout's git index (versions 2 and 3, SHA-1), or
    None without a readable index; the pinned container has no git binary."""
    git = ROOT / ".git"
    if git.is_file():
        git = (ROOT / git.read_text().removeprefix("gitdir:").strip()).resolve()
    try:
        data = (git / "index").read_bytes()
    except OSError:
        return None
    signature, version, count = struct.unpack_from(">4sII", data)
    if signature != b"DIRC" or version not in (2, 3):
        raise ValueError(f"unsupported git index version {version}; run with explicit files")
    paths, at = [], 12
    for _ in range(count):
        # 62 fixed bytes (two more with v3 extended flags), the path, then 1-8
        # NULs padding the entry to a multiple of eight bytes.
        fixed = 64 if struct.unpack_from(">H", data, at + 60)[0] & 0x4000 else 62
        end = data.index(b"\0", at + fixed)
        paths.append(data[at + fixed : end].decode())
        at += (end - at + 8) // 8 * 8
    return paths


def tree_files(suffixes=(".py", *CPP_SUFFIXES), directories=None):
    """Every tracked source with one of SUFFIXES (under DIRECTORIES, when given), or
    every one outside build products and hidden directories when there is no git
    index (an exported tree)."""

    def selected(path):
        inside = directories is None or path.parts[:1] in [(name,) for name in directories]
        return inside and path.suffix in suffixes

    paths = indexed_paths()
    if paths is not None:
        for path in paths:
            # Deleted or sparse entries stay in the index without a file.
            if selected(Path(path)) and (ROOT / path).is_file():
                yield str(ROOT / path)
        return
    for directory, subdirectories, names in os.walk(ROOT):
        subdirectories[:] = sorted(name for name in subdirectories if name not in SKIPPED and name[0] != ".")
        for name in sorted(names):
            path = Path(directory, name)
            if selected(path.relative_to(ROOT)):
                yield str(path)


# Aurora product sources; test drivers and fixtures keep their own layout.
AURORA_DIRECTORIES = ("compiler", "library", "kernel", "examples")


def aurora_check(formatter):
    """aurora-fmt --check over every tracked Aurora product source, in parallel."""
    files = list(tree_files((".au",), AURORA_DIRECTORIES))

    def unformatted(path):
        result = subprocess.run([formatter, "--check", path], capture_output=True, timeout=120)
        return result.returncode != 0 and path

    with concurrent.futures.ThreadPoolExecutor(len(os.sched_getaffinity(0))) as pool:
        failed = [path for path in pool.map(unformatted, files) if path]
    for path in failed:
        print(f"unformatted: {Path(path).relative_to(ROOT)} (run {Path(formatter).name} FILE)", file=sys.stderr)
    print(f"{len(files) - len(failed)} of {len(files)} Aurora files formatted")
    return int(bool(failed))


class MissingTool(ValueError):
    pass


def find_tool(name):
    executable = shutil.which(name)
    if executable is None:
        raise MissingTool(f"missing {name} {VERSIONS[name]}; see docs/style.md")
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True, timeout=10, cwd=ROOT)
    words = result.stdout.split()
    if name == "ruff":
        matches = words == ["ruff", VERSIONS[name]]
    else:
        matches = "version" in words and words[words.index("version") + 1 :][:1] == [VERSIONS[name]]
    if not matches:
        raise MissingTool(f"expected {name} {VERSIONS[name]}, got {result.stdout.strip()!r}")
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "format", "aurora"))
    parser.add_argument("--tree", action="store_true", help="select every host source in the checkout")
    parser.add_argument("--formatter", help="aurora-fmt executable, for the aurora mode")
    parser.add_argument(
        "files", nargs="*", help="explicit Python or C++ source files, relative to the current directory"
    )
    args = parser.parse_args()
    if args.mode == "aurora":
        if not args.formatter or args.files or args.tree:
            parser.error("aurora mode takes only --formatter")
        return aurora_check(args.formatter)
    if args.tree == bool(args.files):
        parser.error("give either --tree or explicit files")
    python_files, cpp_files = select_files(list(tree_files()) if args.tree else args.files)
    # Resolve every dependency before format mode can modify any selected file.
    ruff = find_tool("ruff") if python_files else None
    clang_format = find_tool("clang-format") if cpp_files else None
    ruff_commands, format_commands = [], []
    if python_files:
        options = ["--config", str(ROOT / "ruff.toml"), "--no-cache"]
        check = ["--check"] if args.mode == "check" else []
        ruff_commands.append([ruff, "format", *options, *check, "--", *python_files])
        ruff_commands.append([ruff, "check", *options, "--", *python_files])
    if cpp_files:
        # clang-format is single-threaded; one process per CPU over interleaved slices.
        options = ["--dry-run", "--Werror"] if args.mode == "check" else ["-i"]
        jobs = min(len(os.sched_getaffinity(0)), len(cpp_files))
        for part in range(jobs):
            files = cpp_files[part::jobs]
            format_commands.append([clang_format, f"--style=file:{ROOT / '.clang-format'}", *options, "--", *files])
    # The two ruff steps run in order (format, then check) beside the clang-format slices.
    processes = [subprocess.Popen(command, cwd=ROOT) for command in format_commands]
    failed = False
    for command in ruff_commands:
        failed = subprocess.run(command, cwd=ROOT, timeout=120).returncode != 0 or failed
    for process in processes:
        failed = process.wait(timeout=120) != 0 or failed
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MissingTool as error:
        # Meson reports exit 77 as a skip, so a build without the pinned tools says so.
        print(f"style: {error}", file=sys.stderr)
        sys.exit(77)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"style: {error}", file=sys.stderr)
        sys.exit(2)

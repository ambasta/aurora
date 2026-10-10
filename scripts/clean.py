#!/usr/bin/env python3
"""Clean Meson products or explicitly selected scratch beneath build/. Stop other work first."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess


def checked_path(root, selected, scratch):
    base = root / "build"
    path = Path(os.path.abspath(root / selected))
    if path == base or not path.is_relative_to(base) or not path.resolve().is_relative_to(base):
        raise ValueError("select a path beneath build/, without symlinks outside it: " + str(path))
    parents = [path, *path.parents[: len(path.relative_to(base).parts)]]
    if (
        path.name == ".keep"
        or any((parent / ".keep").exists() or (parent / ".keep").is_symlink() for parent in parents)
        or any(path.rglob(".keep"))
    ):
        raise ValueError("kept output: " + str(path))
    if not path.exists() and not path.is_symlink():
        raise ValueError("missing output: " + str(path))
    if scratch and os.environ.get("MESON_BUILD_DIR"):
        current = (root / os.environ["MESON_BUILD_DIR"]).resolve()
        configuration = [current / name for name in ("meson-private", "meson-info", "build.ninja")]
        if (
            path.resolve() == current
            or path.resolve() in current.parents
            or any(path.resolve() == item or item in path.resolve().parents for item in configuration)
        ):
            raise ValueError("preserve the selected current Meson build/configuration: " + str(path))
    if not scratch:
        info = json.loads((path / "meson-info/meson-info.json").read_text())
        if info.get("directories", {}).get("source") != str(root) or info["directories"].get("build") != str(path):
            raise ValueError("Meson source/build mismatch: " + str(path))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print selections without running cleanup",
    )
    parser.add_argument(
        "--scratch",
        action="store_true",
        help="remove only explicitly selected, reviewed scratch",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="scratch paths beneath build/; may include failed evidence",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.scratch:
        selected = args.paths or shlex.split(os.environ.get("CLEAN_PATHS", ""))
        if not selected:
            parser.error("select reviewed scratch, e.g. CLEAN_PATHS='build/review-old'; preview with --dry-run")
    else:
        if args.paths:
            parser.error("paths require --scratch; use MESON_BUILD_DIR for product cleanup")
        supplied = os.environ.get("MESON_BUILD_DIR")
        selected = (
            [supplied]
            if supplied is not None
            else [
                path
                for name in ("meson", "meson-compiler")
                if (path := root / "build" / name).exists() or path.is_symlink()
            ]
        )
    paths = [checked_path(root, path, args.scratch) for path in selected]
    if not paths:
        print("No default Meson builds; set MESON_BUILD_DIR to select one beneath build/.")
    for path in paths:
        command = ["meson", "compile", "--clean", "-C", str(path)]
        description = ("Would remove " if args.dry_run else "Removing ") + str(path)
        print(description if args.scratch else shlex.join(command), flush=True)
        if not args.dry_run:
            if not args.scratch:
                subprocess.run(command, check=True)
            elif path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))

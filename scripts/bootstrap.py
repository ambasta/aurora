#!/usr/bin/env python3
"""Select the pinned checkpoint compiler, or build the next checkpoint in one hop.

Normal builds use one checkpoint: the checkpoint compiles C1, C1 compiles C2, and
the `hosted-lexer-bootstrap` test requires C1/C2 convergence (GCC's stage compare).
`compiler/checkpoint.json` pins the checkpoint by source commit/tree and executable
SHA256; Meson accepts only that executable. A bump builds a new source with the
current checkpoint (`hop`), runs C1/C2 convergence and the historical-oracle
emitter differential, and prints the new pin. The six-stage route that produced
the first checkpoint is kept as a record in `compiler/bootstrap-history.json`.
Receipts are local build evidence, not signed attestations.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import meson_toolchain
import build_resources

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "compiler/checkpoint.json"
# The fixed configuration every checkpoint is built with; tests stay out of it.
MESON_OPTIONS = (
    "-Dkernel_images=false",
    "-Dlsp=false",
    "-Doptimization=2",
    "-Ddebug=false",
    "-Dcpp_std=c++23",
    "-Dwarning_level=3",
    "-Dwerror=true",
)
# C1/C2 convergence, then the corpus differential against the historical C++ emitter.
HOP_TESTS = ("hosted-lexer-bootstrap", "emitter-differential-default", "emitter-differential-closed")
TOOLS = ("gcc", "g++", "as", "ld", "meson", "ninja", "python3")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def pin():
    value = json.loads(CHECKPOINT.read_text())
    require(value.get("schema") == 1, "unsupported compiler/checkpoint.json schema")
    for role in ("checkpoint", "historical_oracle"):
        require(len(value[role]["sha256"]) == 64, "checkpoint.json: missing " + role + " sha256")
    return value


def checked(path, sha256, role):
    """Absolute executable whose bytes are the pinned ones."""
    require(path and Path(path).is_absolute(), f"absolute {role} path required")
    require(os.access(path, os.X_OK), f"{role} is not executable: {path}")
    actual = digest(path)
    require(actual == sha256, f"{role} {path} has SHA256 {actual}, but compiler/checkpoint.json pins {sha256}")
    return [str(path), sha256]


def select(compiler, oracle=""):
    """Meson's configure-time check: the checkpoint, and the oracle when given."""
    value = pin()
    try:
        lines = checked(compiler, value["checkpoint"]["sha256"], "bootstrap_compiler")
        lines += checked(oracle, value["historical_oracle"]["sha256"], "historical_oracle") if oracle else ["", ""]
        return lines
    except (OSError, ValueError) as error:
        raise ValueError(
            f"Checkpoint compiler rejected: {error}. To fix: select the retained checkpoint "
            "(compiler/README.md#source-bootstrap) or reconstruct it from the recorded route"
        ) from error


def git_tree(directory):
    """Git's tree object id for a checkout, computed from its files without Git.

    The pinned image has no Git; this identifies the exact checkout bytes, modes
    and membership. Untracked or build output inside the checkout changes it."""

    def tree(path):
        entries = []
        for child in path.iterdir():
            if child.name == ".git" and path == directory:
                continue
            if child.is_symlink():
                data, mode = os.readlink(child).encode(), b"120000"
                oid = hashlib.sha1(b"blob %d\0" % len(data) + data).digest()
            elif child.is_dir():
                oid, mode = tree(child), b"40000"
                if oid is None:
                    continue  # Git does not record empty directories.
            else:
                data = child.read_bytes()
                mode = b"100755" if child.stat().st_mode & 0o100 else b"100644"
                oid = hashlib.sha1(b"blob %d\0" % len(data) + data).digest()
            name = os.fsencode(child.name)
            entries.append((name + b"/" if mode == b"40000" else name, mode + b" " + name + b"\0" + oid))
        if not entries:
            return None
        body = b"".join(entry for _, entry in sorted(entries))
        return hashlib.sha1(b"tree %d\0" % len(body) + body).digest()

    directory = Path(directory)
    return tree(directory).hex()


def tools():
    meson_toolchain.explicit_search()
    meson_toolchain.check([meson_toolchain.selected_tool(os.environ.get("CXX", "g++"))])
    selected = {name: meson_toolchain.selected_tool(name) for name in TOOLS}
    return {
        "selected": selected,
        "versions": {
            name: subprocess.check_output([path, "--version"], text=True).splitlines()[0]
            for name, path in selected.items()
        },
        "host": [platform.system(), platform.machine(), list(platform.libc_ver())],
    }


def run_logged(argv, log):
    started = time.monotonic()
    with log.open("w") as stream:
        try:
            result = build_resources.run(argv, stdout=stream, stderr=subprocess.STDOUT)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ValueError(f"{error}; retained log: {log}") from error
    record = {"argv": argv, "returncode": result.returncode, "seconds": round(time.monotonic() - started, 1)}
    require(result.returncode == 0, f"command failed ({result.returncode}); retained log: {log}")
    return record


def hop(args):
    """Build SOURCE with COMPILER, check C1/C2 and the oracle differential, record."""
    jobs = str(build_resources.jobs(args.jobs, "--jobs"))
    source, output = args.source.resolve(), args.output.resolve()
    compiler = str(args.compiler.resolve())
    require(not output.is_relative_to(source), "build outside the source checkout; it must stay clean")
    tree = git_tree(source)
    require(tree == args.tree, f"source tree is {tree}, expected {args.tree}; use a clean `git worktree add`")
    output.mkdir(parents=True, exist_ok=False)
    build = output / "build"
    # The first checkpoint's source still selects its predecessor through the
    # six-stage receipt; later sources take the previous checkpoint and oracle.
    setup = ["meson", "setup", str(build), str(source), *MESON_OPTIONS, "-Dbootstrap_compiler=" + compiler]
    if args.receipt:
        setup.append("-Dbootstrap_receipt=" + str(args.receipt.resolve()))
    else:
        require(args.oracle, "--oracle is required to run the historical emitter differential")
        setup.append("-Dhistorical_oracle=" + str(args.oracle.resolve()))
    commands = [
        setup,
        ["meson", "compile", "-C", str(build), "-j", jobs, "aurorac", "aurorac-stage2"],
        ["meson", "test", "-C", str(build), "--no-rebuild", "--num-processes", jobs, "--print-errorlogs", *HOP_TESTS],
    ]
    identity = tools()
    records = [run_logged(argv, output / f"{index}.log") for index, argv in enumerate(commands)]
    require(git_tree(source) == tree, "source checkout changed during the hop")
    shutil.copy2(build / "aurorac-stage2", output / "aurorac")
    receipt = {
        "schema": 1,
        "source": {"commit": args.commit, "tree": tree},
        "predecessor": {"path": compiler, "sha256": digest(compiler)},
        "historical_oracle": {"path": str(args.oracle.resolve()), "sha256": digest(args.oracle)}
        if args.oracle
        else {"from_receipt": str(args.receipt.resolve())},
        "tools": identity,
        "commands": records,
        "checkpoint": {
            "path": str(output / "aurorac"),
            "sha256": digest(output / "aurorac"),
            "c1_sha256": digest(build / "aurorac"),
        },
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"commit": args.commit, "tree": tree, "sha256": receipt["checkpoint"]["sha256"]}, indent=2))
    if args.expect:
        require(receipt["checkpoint"]["sha256"] == args.expect, "rebuilt checkpoint differs from the expected pin")
        print("Reproduced the pinned checkpoint.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="action", required=True)
    selector = subparsers.add_parser("select", help="verify the pinned checkpoint (and oracle) for Meson")
    selector.add_argument("--compiler", required=True)
    selector.add_argument("--oracle", default="")
    hopper = subparsers.add_parser("hop", help="build the next checkpoint with the current one")
    hopper.add_argument("--compiler", type=Path, required=True, help="the current checkpoint compiler")
    hopper.add_argument("--oracle", type=Path, help="the historical C++ emitter oracle")
    hopper.add_argument("--receipt", type=Path, help="six-stage receipt, for the first checkpoint's source only")
    hopper.add_argument("--source", type=Path, required=True, help="clean checkout of the new checkpoint commit")
    hopper.add_argument("--commit", required=True)
    hopper.add_argument("--tree", required=True, help="`git rev-parse COMMIT^{tree}`")
    hopper.add_argument("--output", type=Path, required=True, help="new directory for the build and receipt")
    hopper.add_argument("--expect", help="require this checkpoint SHA256 (reproducing a pin)")
    hopper.add_argument("--jobs", default="auto", help="auto (nproc) or a positive job ceiling")
    args = parser.parse_args()
    if args.action == "select":
        print("\n".join(select(args.compiler, args.oracle)))
    else:
        hop(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        sys.exit("bootstrap: " + str(error))

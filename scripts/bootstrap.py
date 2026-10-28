#!/usr/bin/env python3
"""Select the checkpoint compiler, bump it by one hop, or rebuild it from source.

Normal builds use one checkpoint (C0): C0 compiles C1, C1 compiles C2, and the
`hosted-lexer-bootstrap` test requires C1 and C2 to agree (GCC's stage compare).
`compiler/checkpoint.json` names C0 by source commit and tree; any C0 built from
that source with the supported tools is accepted, and the stage compare checks it.
`hop` builds a new checkpoint source with the current C0. `rebuild` reconstructs
C0 without any binary: the historical C++ seed and Aurora stages in
`compiler/bootstrap-history.json`, then every recorded hop, each built by the
previous one and each passing its stage compare.
"""

import argparse
import hashlib
import tarfile
import tempfile
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

import meson_toolchain

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "compiler/checkpoint.json"
HISTORY = ROOT / "compiler/bootstrap-history.json"
CHECKPOINT_TARGETS = ("aurorac", "aurorac-stage2")
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
# C1/C2 convergence.
HOP_TESTS = ("hosted-lexer-bootstrap",)
TOOLS = ("gcc", "g++", "as", "ld", "meson", "ninja", "python3")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin():
    value = json.loads(CHECKPOINT.read_text())
    require(value.get("schema") == 2, "unsupported compiler/checkpoint.json schema")
    require(value["checkpoint"]["commit"] and value["checkpoint"]["tree"], "checkpoint.json: missing source pin")
    return value


def select(compiler):
    """Meson's configure-time check of the checkpoint executable."""
    if not compiler or not Path(compiler).is_absolute() or not os.access(compiler, os.X_OK):
        raise ValueError(
            f"Checkpoint compiler rejected: bootstrap_compiler must be an absolute executable path, got "
            f"{compiler!r}. Build it with `scripts/bootstrap.py rebuild` (compiler/README.md#source-bootstrap)"
        )
    pin()
    return str(compiler)


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
            result = subprocess.run([ROOT / "scripts/watchdog.sh", *argv], stdout=stream, stderr=subprocess.STDOUT)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ValueError(f"{error}; retained log: {log}") from error
    record = {"argv": argv, "returncode": result.returncode, "seconds": round(time.monotonic() - started, 1)}
    require(result.returncode == 0, f"command failed ({result.returncode}); retained log: {log}")
    return record


def stage(source, build, compiler, targets, logs, jobs, extra=()):
    """Configure SOURCE with COMPILER, build TARGETS and run the stage compare."""
    setup = ["meson", "setup", str(build), str(source), *MESON_OPTIONS, *extra]
    if compiler:
        setup.append("-Dbootstrap_compiler=" + str(compiler))
    commands = [
        setup,
        ["meson", "compile", "-C", str(build), "-j", jobs, *targets],
        ["meson", "test", "-C", str(build), "--num-processes", jobs, "--print-errorlogs", *HOP_TESTS],
    ]
    logs.mkdir(parents=True, exist_ok=True)
    return [run_logged(argv, logs / f"{index}.log") for index, argv in enumerate(commands)]


def keep_runtime(source, output):
    """Keep the checkpoint's runtime root (aurora.host, aurora.memory) beside it.

    The compiler bakes its source tree's runtime root in; a relocated
    checkpoint names this copy with --runtime-root to compile hosted programs."""
    runtime = Path(source) / "runtime/linux"
    if runtime.is_dir():
        shutil.copytree(runtime, Path(output) / "runtime/linux")


def hop(args):
    """Build SOURCE with COMPILER, check C1/C2 convergence, record."""
    jobs = str(args.jobs or os.cpu_count())
    source, output = args.source.resolve(), args.output.resolve()
    require(not output.is_relative_to(source), "build outside the source checkout; it must stay clean")
    tree = git_tree(source)
    require(tree == args.tree, f"source tree is {tree}, expected {args.tree}; use a clean `git worktree add`")
    output.mkdir(parents=True, exist_ok=False)
    identity = tools()
    records = stage(source, output / "build", args.compiler.resolve(), CHECKPOINT_TARGETS, output, jobs)
    require(git_tree(source) == tree, "source checkout changed during the hop")
    shutil.copy2(output / "build/aurorac-stage2", output / "aurorac")
    keep_runtime(source, output)
    receipt = {
        "schema": 2,
        "source": {"commit": args.commit, "tree": tree},
        "predecessor": str(args.compiler.resolve()),
        "tools": identity,
        "commands": records,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"commit": args.commit, "tree": tree}, indent=2))


# The recorded sources select their predecessor with an exact-version gate and,
# from 2fd30b2 on, a digest pin of the binary they were first built with. After
# their tree is verified, a rebuild exports them with this checkout's minimum
# version gate and this select, which accepts the compiler actually given. It
# prints each era's lines: compiler and its digest, then the historical oracle and
# its digest, which is the receipt's borrow stage (2fd30b2) or --oracle (d4cbabb).
# Sources from schema 2 of checkpoint.json on select by stage compare alone and
# keep their own script.
RECORDED_SELECT = """import hashlib, sys
def digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if path else ""
arguments = dict(zip(sys.argv[2::2], sys.argv[3::2]))
compiler = arguments["--compiler"]
lines = [compiler, digest(compiler)]
if "--receipt" in arguments:
    lines += [compiler, digest(compiler)]
elif "--oracle" in arguments:
    lines += [arguments["--oracle"], digest(arguments["--oracle"])]
print("\\n".join(lines))
"""


def export(commit, tree, directory):
    """The recorded source at COMMIT, verified against TREE, with this checkout's gates."""
    directory.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", commit], check=True, capture_output=True).stdout
    with tempfile.TemporaryFile() as stream:
        stream.write(archive)
        stream.seek(0)
        with tarfile.open(fileobj=stream) as bundle:
            bundle.extractall(directory, filter="tar")
    require(git_tree(directory) == tree, f"{commit}: exported tree differs from {tree}")
    shutil.copy2(ROOT / "scripts/meson_toolchain.py", directory / "scripts/meson_toolchain.py")
    pinned = directory / "compiler/checkpoint.json"
    digest_era = pinned.exists() and json.loads(pinned.read_text()).get("schema", 0) < 2
    if digest_era or (directory / "compiler/bootstrap-route.json").exists():
        (directory / "scripts/bootstrap.py").write_text(RECORDED_SELECT)
    return directory


def rebuild(args):
    """C0 from source: the historical stages, then every recorded hop, natively."""
    jobs = str(args.jobs or os.cpu_count())
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    history = json.loads(HISTORY.read_text())
    value = pin()
    identity = tools()
    compiler, records = None, []
    for recorded in history["stages"]:
        name = recorded["name"]
        source = export(recorded["commit"], recorded["tree"], output / name / "source")
        # The first Aurora stage takes its predecessor's digest as an option.
        extra = ["-Dbootstrap_compiler_sha256=" + sha256(compiler)] if name == "facts" else []
        build = output / name / "build"
        records.append([name, stage(source, build, compiler, recorded["targets"], output / name, jobs, extra)])
        compiler = build / "aurorac"
        print(f"Built stage {name}", flush=True)
    # The first hop's source still reads the six-stage receipt and its oracle.
    receipt = output / "stages.json"
    receipt.write_text("{}\n")
    for index, recorded in enumerate([*reversed(value["history"]), value["checkpoint"]]):
        name = recorded["commit"][:12]
        source = export(recorded["commit"], recorded["tree"], output / name / "source")
        extra = []
        if index == 0:
            extra = ["-Dbootstrap_receipt=" + str(receipt), "-Dbootstrap_compiler_sha256=" + sha256(compiler)]
        build = output / name / "build"
        records.append([name, stage(source, build, compiler, CHECKPOINT_TARGETS, output / name, jobs, extra)])
        compiler = build / "aurorac-stage2"
        print(f"Built checkpoint {name}", flush=True)
    shutil.copy2(compiler, output / "aurorac")
    keep_runtime(output / value["checkpoint"]["commit"][:12] / "source", output)
    # Keep the checkpoint, its runtime, receipt and logs; every source and build is reproducible.
    for directory in output.glob("*/"):
        if directory.name != "runtime":
            shutil.rmtree(directory / "source")
            shutil.rmtree(directory / "build")
    (output / "stages.json").unlink()
    result = {"schema": 2, "source": value["checkpoint"], "tools": identity, "commands": records}
    (output / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    print(f"Checkpoint {value['checkpoint']['commit'][:12]}: {output / 'aurorac'}")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="action", required=True)
    selector = subparsers.add_parser("select", help="check the checkpoint executable for Meson")
    selector.add_argument("--compiler", required=True)
    hopper = subparsers.add_parser("hop", help="build the next checkpoint with the current one")
    hopper.add_argument("--compiler", type=Path, required=True, help="the current checkpoint compiler")
    hopper.add_argument("--source", type=Path, required=True, help="clean checkout of the new checkpoint commit")
    hopper.add_argument("--commit", required=True)
    hopper.add_argument("--tree", required=True, help="`git rev-parse COMMIT^{tree}`")
    hopper.add_argument("--output", type=Path, required=True, help="new directory for the build and receipt")
    hopper.add_argument("--jobs", type=int, help="job count; default nproc")
    rebuilder = subparsers.add_parser("rebuild", help="build the checkpoint from source, without any binary")
    rebuilder.add_argument("--output", type=Path, required=True, help="new directory; OUTPUT/aurorac is C0")
    rebuilder.add_argument("--jobs", type=int, help="job count; default nproc")
    args = parser.parse_args()
    if args.action == "select":
        print(select(args.compiler))
    elif args.action == "hop":
        hop(args)
    else:
        rebuild(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        sys.exit("bootstrap: " + str(error))

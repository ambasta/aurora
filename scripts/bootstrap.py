#!/usr/bin/env python3
"""Reconstruct the pinned source route, or verify a locally retained predecessor.

Receipts are local build evidence, not signed attestations or independent review.
Historical convergence never qualifies changed current source or shortens the route.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import tempfile

import meson_toolchain

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "compiler/bootstrap-route.json"
ENVIRONMENT = (
    "PATH",
    "CC",
    "CXX",
    "LD_LIBRARY_PATH",
    "PYTHONPATH",
    "SOURCE_DATE_EPOCH",
    "LANG",
    "LC_ALL",
    "TZ",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def file_identity(path):
    path = Path(os.path.abspath(path))
    resolved = path.resolve(strict=True)
    return {"path": str(path), "resolved": str(resolved), "sha256": digest(resolved)}


def check_file(record):
    require(file_identity(record["path"]) == record, "file digest changed: " + record["path"])


def output(command, **kwargs):
    return subprocess.check_output(list(map(str, command)), text=True, stderr=subprocess.STDOUT, **kwargs).strip()


def route():
    value = json.loads(MANIFEST.read_text())
    require(value["schema"] == 1 and len(value["stages"]) == 6, "unsupported bootstrap route")
    names = [stage["name"] for stage in value["stages"]]
    require(len(set(names)) == len(names), "duplicate source stage")
    require(value["build_predecessor"] == names[-1], "predecessor must be the final pinned stage")
    require(value["historical_cpp_oracle"] in names, "missing independently named C++ oracle")
    for stage in value["stages"]:
        require(re.fullmatch(r"[a-z][a-z0-9-]*", stage["name"]), "invalid stage name")
        for key in ("commit", "tree"):
            require(re.fullmatch(r"[0-9a-f]{40}", stage[key]), "full source commit/tree required")
    return value


def rebuild_command():
    # The supported route reuses a verified cache and prints the Meson options.
    return (
        "run `python3 scripts/bootstrap.py build --container` from the host checkout, "
        "then reconfigure Meson with the printed -Dbootstrap_receipt option"
    )


def child_status(returncode):
    """Exit status for a failed child; signals keep the shell's 128+N convention."""
    return 128 - returncode if returncode < 0 else returncode


def source_identity(source, stage):
    require(output(["git", "-C", source, "rev-parse", "HEAD"]) == stage["commit"], "source commit mismatch")
    require(output(["git", "-C", source, "rev-parse", "HEAD^{tree}"]) == stage["tree"], "source tree mismatch")
    require(
        not output(["git", "-C", source, "status", "--porcelain", "--untracked-files=all", "--ignored=matching"]),
        "source worktree dirty",
    )
    detached = subprocess.run(["git", "-C", str(source), "symbolic-ref", "-q", "HEAD"], capture_output=True)
    require(detached.returncode == 1, "source worktree must be detached")
    # Git status alone can hide checkout filters or assume-unchanged/skip-worktree bytes.
    entries = subprocess.check_output(["git", "-C", str(source), "ls-tree", "-rz", "HEAD"]).split(b"\0")
    snapshot = {}
    for entry in filter(None, entries):
        identity, name = entry.split(b"\t", 1)
        mode, kind, oid = identity.split()
        path = source / os.fsdecode(name)
        require(
            kind == b"blob" and mode in (b"100644", b"100755") and not path.is_symlink(),
            "unsupported pinned source entry: " + str(path),
        )
        data = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest().encode()
        permissions = path.stat().st_mode & 0o777
        require(
            actual == oid and bool(permissions & 0o111) == (mode == b"100755"),
            "checkout differs from pinned Git blob/mode: " + str(path),
        )
        snapshot[os.fsdecode(name)] = [hashlib.sha256(data).hexdigest(), permissions]
    require(source_files(source) == snapshot, "checkout bytes/membership changed from pinned Git tree")
    return snapshot


def source_files(source):
    """Portable byte/mode identity for host-prepared worktrees; .git is host-only."""
    result = {}
    for path in sorted(source.rglob("*")):
        if path.name == ".git":
            continue
        require(not path.is_symlink(), "unexpected source symlink: " + str(path))
        if path.is_file():
            result[str(path.relative_to(source))] = [digest(path), path.stat().st_mode & 0o777]
    require(result, "empty prepared source")
    return result


def prepare_sources(cache, pin, fresh=False):
    key = hashlib.sha256(json.dumps(pin, sort_keys=True).encode()).hexdigest()
    prepared = Path(tempfile.mkdtemp(prefix="prepared-", dir=cache)) if fresh else cache / ("prepared-" + key)
    require(not prepared.is_symlink() and prepared.resolve().is_relative_to(ROOT), "prepared path escapes checkout")
    prepared.mkdir(parents=True, exist_ok=True)
    stages = []
    for stage in pin["stages"]:
        directory = prepared / stage["name"]
        require(not directory.is_symlink() and directory.resolve().is_relative_to(ROOT), "stage path escapes checkout")
        directory.mkdir(exist_ok=True)
        source = directory / "source"
        require(not source.is_symlink() and source.resolve().is_relative_to(ROOT), "source path escapes checkout")
        if not source.exists():
            present = subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "-e", stage["commit"] + "^{commit}"], capture_output=True
            )
            require(
                present.returncode == 0,
                f"pinned {stage['name']} commit is missing; run: git fetch origin {stage['commit']}",
            )
            # -f re-adds a worktree whose directory was deleted but is still registered.
            record_command(
                ["git", "-C", str(ROOT), "worktree", "add", "-f", "--detach", str(source), stage["commit"]],
                directory,
                "worktree",
            )
        snapshot = source_identity(source, stage)
        stages.append({"source": stage, "source_dir": str(source.relative_to(ROOT)), "source_files": snapshot})
    manifest = prepared / "sources.json"
    write_json(manifest, {"route": pin, "stages": stages})
    return manifest


def prepared_sources(manifest, pin):
    value = json.loads(Path(manifest).read_text())
    require(value["route"] == pin and len(value["stages"]) == len(pin["stages"]), "prepared source pin mismatch")
    for stage, expected in zip(value["stages"], pin["stages"]):
        source = (ROOT / stage["source_dir"]).resolve()
        require(source.is_relative_to(ROOT) and stage["source"] == expected, "prepared source location/pin mismatch")
        require(source_files(source) == stage["source_files"], "prepared source bytes/modes changed: " + str(source))
    return value["stages"]


def tool_identity(*, current_flags=False):
    """Pinned tool paths, versions and executable digests. This identifies the
    toolchain the receipt was built with; it is not a runtime-closure proof."""
    meson_toolchain.explicit_search()
    for name in (
        "CFLAGS",
        "CXXFLAGS",
        "CPPFLAGS",
        "LDFLAGS",
        "GCC_EXEC_PREFIX",
        "COMPILER_PATH",
        "LD_PRELOAD",
        "LD_AUDIT",
    ):
        if not current_flags or name in ("GCC_EXEC_PREFIX", "COMPILER_PATH", "LD_PRELOAD", "LD_AUDIT"):
            require(not os.environ.get(name), "unset bootstrap environment override: " + name)
    cxx = meson_toolchain.selected_tool(os.environ.get("CXX", "g++"))
    meson_toolchain.check([cxx])
    selected = {
        name: meson_toolchain.selected_tool(name) for name in ("gcc", "g++", "as", "ld", "meson", "ninja", "python3")
    }
    selected["cxx"] = cxx
    files = set(selected.values()) | {str(Path(sys.executable).resolve())}
    for name in ("cc1plus", "collect2"):
        files.add(meson_toolchain.selected_tool(output([cxx, "-print-prog-name=" + name])))
    return {
        "selected": selected,
        "files": [file_identity(path) for path in sorted(files)],
        "versions": {name: output([path, "--version"]).splitlines()[0] for name, path in selected.items()},
        "environment": {name: os.environ.get(name) for name in ENVIRONMENT},
        "host": [platform.system(), platform.machine(), list(platform.libc_ver())],
    }


def commands(source, build, stage, pin, previous):
    setup = ["meson", "setup", str(build), str(source), *pin["meson_options"]]
    if previous:
        setup += ["-Dbootstrap_compiler=" + previous["path"]]
        if stage["name"] == "facts":
            setup += ["-Dbootstrap_compiler_sha256=" + previous["sha256"]]
    return [
        setup,
        ["meson", "compile", "-C", str(build), "-j", "2", *stage["targets"]],
        [
            "meson",
            "test",
            "-C",
            str(build),
            "--no-rebuild",
            "--num-processes",
            "2",
            pin["convergence_test"],
            "--print-errorlogs",
        ],
    ]


def verify_receipt(receipt, pin, *, tools=None, check_sources=False):
    value = json.loads(Path(receipt).read_text())
    require(value["schema"] == 1 and value["route"] == pin, "receipt source pin/configuration mismatch")
    require(value["origin"] == "six-source-reconstruction", "not a source reconstruction receipt")
    if tools is not None:
        require(value["tools"] == tools, "cache tool/environment identity mismatch")
    for record in value["tools"]["files"]:
        check_file(record)
    require(value["tools"]["files"], "missing tool identities")
    stages = value["stages"]
    require(len(stages) == len(pin["stages"]), "incomplete six-source receipt")
    previous = None
    for stage, expected in zip(stages, pin["stages"]):
        require(stage["source"] == expected and stage["predecessor"] == previous, "source/predecessor chain mismatch")
        require(stage["source_clean"] is True, "unverified source worktree")
        if check_sources:
            require(
                source_files(Path(stage["source_dir"])) == stage["source_files"], "source worktree bytes/modes changed"
            )
        check_file(stage["artifact"])
        require(os.access(stage["artifact"]["path"], os.X_OK), "predecessor is not executable")
        expected_commands = commands(stage["source_dir"], stage["build_dir"], expected, pin, previous)
        require(len(stage["commands"]) == 3, "missing reconstruction/convergence commands")
        for record, command in zip(stage["commands"], expected_commands):
            require(
                record["argv"] == command and record["returncode"] == 0,
                "unsuccessful or altered reconstruction command",
            )
            check_file(record["log"])
        previous = stage["artifact"]
    return value


def select(receipt, compiler="", sha256=""):
    """Derive the predecessor and the historical C++ oracle from one receipt.

    compiler and sha256 are optional cross-checks for build directories that
    still pass them; when given they must name the receipt's predecessor."""
    try:
        require(
            receipt and Path(receipt).is_absolute(), "absolute reconstruction receipt required (-Dbootstrap_receipt)"
        )
        pin = route()
        value = verify_receipt(receipt, pin)
        active_tools = tool_identity(current_flags=True)
        for field in ("selected", "files", "versions", "host"):
            require(
                active_tools[field] == value["tools"][field], "current tool identity differs from the receipt: " + field
            )
        for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
            require(
                os.environ.get(name) == value["tools"]["environment"].get(name),
                "predecessor runtime environment mismatch: " + name,
            )
        roles = {
            role: next(stage["artifact"] for stage in value["stages"] if stage["source"]["name"] == pin[role])
            for role in ("build_predecessor", "historical_cpp_oracle")
        }
        predecessor = roles["build_predecessor"]
        require(
            not compiler or os.path.abspath(compiler) == predecessor["path"],
            "bootstrap_compiler is not the receipt's predecessor",
        )
        require(not sha256 or sha256 == predecessor["sha256"], "bootstrap_compiler_sha256 differs from the receipt")
        return value, roles
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise ValueError(f"Bootstrap predecessor rejected: {error}. To fix: {rebuild_command()}") from error


def verify(compiler, sha256, receipt, *, role="build_predecessor"):
    value, roles = select(receipt, compiler, sha256 if role == "build_predecessor" else "")
    if role != "build_predecessor":
        require(roles[role] == file_identity(compiler) and roles[role]["sha256"] == sha256, "not the pinned " + role)
    return value


def require_digest(path, sha256):
    """The single check before running a selected predecessor or oracle."""
    require(digest(path) == sha256, f"{path} changed since Meson verified it; reconfigure Meson")


def record_command(argv, directory, ordinal):
    log = directory / f"{ordinal}.log"
    with log.open("w") as stream:
        result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT)
    record = {"argv": argv, "returncode": result.returncode, "log": file_identity(log)}
    write_json(directory / f"{ordinal}.json", record)
    require(result.returncode == 0, f"command failed ({result.returncode}); retained log: {log}")
    return record


def build(cache, fresh=False, prepared=None):
    pin, tools = route(), tool_identity()
    key = hashlib.sha256(json.dumps({"route": pin, "tools": tools}, sort_keys=True).encode()).hexdigest()
    cache = Path(cache).resolve()
    require(cache.is_relative_to(ROOT), "bootstrap cache must remain under the checkout for the container mount")
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        index = cache / (key + ".json")
        if index.exists() and not fresh:
            receipt = Path(json.loads(index.read_text())["receipt"])
            value = verify_receipt(receipt, pin, tools=tools, check_sources=True)
            print("Reusing verified predecessor; not a fresh source bootstrap.")
            return receipt, value
        prepared = prepared or prepare_sources(cache, pin, fresh)
        sources = prepared_sources(prepared, pin)
        run = Path(tempfile.mkdtemp(prefix="source-", dir=cache))
        print("Reconstructing six pinned source stages in " + str(run), flush=True)
        value = {
            "schema": 1,
            "origin": "six-source-reconstruction",
            "route": pin,
            "tools": tools,
            "stages": [],
            "scope": "Historical-stage convergence only; current C1/C2, emitter, full and guest gates remain required.",
        }
        previous = None
        for stage, prepared_stage in zip(pin["stages"], sources):
            directory = run / stage["name"]
            directory.mkdir()
            source, build_dir = ROOT / prepared_stage["source_dir"], directory / "build"
            records = []
            for ordinal, argv in enumerate(commands(source, build_dir, stage, pin, previous)):
                require(
                    source_files(source) == prepared_stage["source_files"], "prepared source changed before execution"
                )
                if previous:
                    check_file(previous)  # Historical graphs after ABI facts ignore the digest option.
                records.append(record_command(argv, directory, ordinal))
            require(source_files(source) == prepared_stage["source_files"], "source changed during reconstruction")
            artifact = file_identity(build_dir / "aurorac")
            value["stages"].append(
                {
                    "source": stage,
                    "source_dir": str(source),
                    "source_clean": True,
                    "source_files": prepared_stage["source_files"],
                    "build_dir": str(build_dir),
                    "predecessor": previous,
                    "artifact": artifact,
                    "commands": records,
                }
            )
            write_json(run / "progress.json", value)
            previous = artifact
            print("Completed " + stage["name"] + ": " + artifact["sha256"], flush=True)
        require(tool_identity() == tools, "bootstrap tools/environment changed during reconstruction")
        receipt = run / "receipt.json"
        write_json(receipt, value)
        verify_receipt(receipt, pin, tools=tools, check_sources=True)
        write_json(index, {"receipt": str(receipt)})
        return receipt, value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    builder = subparsers.add_parser("build")
    builder.add_argument("--cache", type=Path, default=ROOT / "build/bootstrap")
    builder.add_argument("--container", action="store_true", help="prepare with host Git, execute via container.sh")
    builder.add_argument("--prepared", type=Path, help=argparse.SUPPRESS)
    builder.add_argument(
        "--fresh", action="store_true", help="rebuild all six stages; retain old runs and failed evidence"
    )
    selector = subparsers.add_parser("select", help="print the receipt's predecessor and oracle for Meson")
    selector.add_argument("--receipt", required=True)
    selector.add_argument("--compiler", default="", help="optional cross-check against the receipt")
    selector.add_argument("--sha256", default="", help="optional cross-check against the receipt")
    args = parser.parse_args()
    if args.action == "build":
        if args.container:
            require(args.prepared is None, "choose host preparation or prepared container execution")
            cache = args.cache.resolve()
            require(cache.is_relative_to(ROOT), "container cache must remain under the checkout mount")
            cache.mkdir(parents=True, exist_ok=True)
            with (cache / ".prepare.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                prepared = prepare_sources(cache, route(), args.fresh)
            command = [
                str(ROOT / "scripts/container.sh"),
                "python3",
                "scripts/bootstrap.py",
                "build",
                "--cache",
                str(Path("/workspace") / cache.relative_to(ROOT)),
                "--prepared",
                str(Path("/workspace") / prepared.relative_to(ROOT)),
            ]
            if args.fresh:
                command.append("--fresh")
            result = subprocess.run(command)
            if result.returncode:
                sys.exit(child_status(result.returncode))
            return
        receipt, _ = build(args.cache, args.fresh, args.prepared)
        print("Configure Meson with: " + shlex.join(["-Dbootstrap_receipt=" + str(receipt)]))
        return
    _, roles = select(args.receipt, args.compiler, args.sha256)
    for role in ("build_predecessor", "historical_cpp_oracle"):
        print(roles[role]["path"] + "\n" + roles[role]["sha256"])


if __name__ == "__main__":
    try:
        main()
    except BlockingIOError:
        sys.exit("bootstrap: another bootstrap build holds the cache lock; wait for it to finish")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Only predecessor verification adds selection advice; build failures name their log.
        sys.exit("bootstrap: " + str(error))

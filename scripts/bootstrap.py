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
import resource
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

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
    if shutil.which("git") is None:
        return "python3 scripts/bootstrap.py build --container --fresh (from the host checkout)"
    return shlex.join([sys.executable, str(ROOT / "scripts/bootstrap.py"), "build", "--fresh"])


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
            record_command(
                ["git", "-C", str(ROOT), "worktree", "add", "--detach", str(source), stage["commit"]],
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


def link_inputs(cxx):
    """Pinned native GCC's PIE/non-PIE startup and implicit link input superset."""
    files = set()
    for name in (
        "crt1.o",
        "Scrt1.o",
        "crti.o",
        "crtn.o",
        "crtbegin.o",
        "crtend.o",
        "crtbeginS.o",
        "crtendS.o",
        "libstdc++.so",
        "libgcc_s.so",
        "libgcc_s.so.1",
        "libgcc.a",
        "libgcc_eh.a",
        "libc.so",
        "libc.so.6",
        "libc_nonshared.a",
        "libm.so",
        "libm.so.6",
        "libmvec.so.1",
        "libatomic_asneeded.so",
        "libatomic.so",
        "liblto_plugin.so",
    ):
        path = Path(output([cxx, "-print-file-name=" + name]))
        require(path.is_absolute() and path.is_file(), "unresolved implicit linker input: " + name)
        files.add(str(path.resolve()))
        data = path.read_bytes()
        if data.startswith(b"\x7fELF") or data.startswith(b"!<arch>\n"):
            continue
        # The pinned glibc scripts use absolute GROUP/INPUT members, which can
        # differ from GCC's search result. Relative/-l members are listed above.
        script = re.sub(r"/\*.*?\*/", "", data.decode(), flags=re.DOTALL)
        for member in re.findall(r"/[^\s()]+", script):
            require(Path(member).is_file(), "missing linker script input: " + member)
            files.add(str(Path(member).resolve()))
    # Built-in specs are covered by the driver digest. Custom specs can introduce
    # additional inputs outside this supported pinned-route closure.
    require(output([cxx, "-print-file-name=specs"]) == "specs", "unsupported external GCC specs")
    return files


def tool_identity(*, current_flags=False):
    """Hash selected drivers, subprograms, shared runtimes and Meson's Python code."""
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
        name: meson_toolchain.selected_tool(name)
        for name in (
            "gcc",
            "g++",
            "as",
            "ld",
            "ar",
            "nm",
            "objcopy",
            "objdump",
            "readelf",
            "meson",
            "ninja",
            "python3",
        )
    }
    selected["cxx"] = cxx
    files = set(selected.values()) | {str(Path(sys.executable).resolve())}
    meson_script = Path(selected["meson"]).read_text().splitlines()[0]
    require(meson_script.startswith("#!"), "expected pinned Meson Python entrypoint")
    meson_interpreter = shlex.split(meson_script[2:])
    files.add(meson_toolchain.selected_tool(meson_interpreter[0]))
    for name in ("cc1plus", "collect2", "as", "ld", "lto-wrapper"):
        files.add(meson_toolchain.selected_tool(output([cxx, "-print-prog-name=" + name])))
    files.update(link_inputs(cxx))
    # ldd inspects only the selected trusted development tools, never user artifacts.
    for path in sorted(files):
        header = Path(path).read_bytes()[:18]
        if header[:4] == b"\x7fELF" and header[16:18] in (b"\x02\x00", b"\x03\x00"):
            result = subprocess.run(["ldd", path], capture_output=True, text=True)
            require(result.returncode == 0, "cannot inspect tool runtime: " + path)
            require("not found" not in result.stdout, "missing tool runtime: " + path)
            files.update(re.findall(r"(?:=>\s+|^\s*)(/[^\s]+)", result.stdout, re.MULTILINE))
    # The pinned image puts its style venv first on PATH, but Debian Meson uses
    # system Python. Inspect that interpreter, not this driver's import path.
    meson_module = Path(output([*meson_interpreter, "-c", "import mesonbuild; print(mesonbuild.__file__)"]))
    files.update(str(path) for path in meson_module.parent.rglob("*.py"))
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
    require(value["driver_sha256"] == digest(__file__), "reconstruction driver identity changed")
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
        for record in stage["inputs"]:
            check_file(record)
        require(stage["inputs"], "missing compiler header/build input identities")
        previous = stage["artifact"]
    return value


def verify(compiler, sha256, receipt, *, role="build_predecessor"):
    """Mandatory external digest plus a source/config/tool-bound local receipt."""
    try:
        require(
            isinstance(sha256, str) and re.fullmatch(r"[0-9a-f]{64}", sha256), "mandatory SHA256 is missing or invalid"
        )
        require(compiler and Path(compiler).is_absolute(), "absolute predecessor path required")
        require(receipt and Path(receipt).is_absolute(), "absolute reconstruction receipt required")
        require(digest(compiler) == sha256, "selected predecessor SHA256 mismatch")
        pin = route()
        value = verify_receipt(receipt, pin)
        active_tools = tool_identity(current_flags=True)
        for field in ("selected", "files", "versions", "host"):
            require(active_tools[field] == value["tools"][field], "current tool/runtime identity mismatch: " + field)
        for name in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
            require(
                os.environ.get(name) == value["tools"]["environment"].get(name),
                "predecessor runtime environment mismatch: " + name,
            )
        selected = next(stage["artifact"] for stage in value["stages"] if stage["source"]["name"] == pin[role])
        require(selected == file_identity(compiler), "selected artifact does not match pinned " + role)
        return value
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise ValueError(
            f"Bootstrap predecessor rejected: {error}. Rebuild predecessor: {rebuild_command()}"
        ) from error


def record_command(argv, directory, ordinal):
    log = directory / f"{ordinal}.log"
    started = time.monotonic()
    with log.open("w") as stream:
        result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT)
    record = {
        "argv": argv,
        "cwd": str(Path.cwd()),
        "returncode": result.returncode,
        "log": file_identity(log),
        "seconds": time.monotonic() - started,
        "max_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
    }
    write_json(directory / f"{ordinal}.json", record)
    require(result.returncode == 0, f"command failed ({result.returncode}); retained log: {log}")
    return record


def build_inputs(build):
    """Keep the actual Ninja header dependency closure, not just driver hashes."""
    paths = {build / "build.ninja", build / "meson-info/intro-buildoptions.json", build / "compile_commands.json"}
    for line in output(["ninja", "-C", build, "-t", "deps"]).splitlines():
        if line.startswith("    "):
            paths.add(build / line.strip())
    return [file_identity(path) for path in sorted(paths)]


def build(cache, fresh=False, prepared=None):
    pin, tools = route(), tool_identity()
    key = hashlib.sha256(
        json.dumps({"route": pin, "tools": tools, "driver": digest(__file__)}, sort_keys=True).encode()
    ).hexdigest()
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
            "driver_sha256": digest(__file__),
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
                    "inputs": build_inputs(build_dir),
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
    for action in ("verify", "run"):
        sub = subparsers.add_parser(action)
        sub.add_argument("--compiler", required=True)
        sub.add_argument("--sha256", required=True)
        sub.add_argument("--receipt", required=True)
        sub.add_argument("--role", choices=("build_predecessor", "historical_cpp_oracle"), default="build_predecessor")
        if action == "run":
            sub.add_argument("command", nargs=argparse.REMAINDER)
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
            subprocess.run(command, check=True)
            return
        receipt, value = build(args.cache, args.fresh, args.prepared)
        artifact = value["stages"][-1]["artifact"]
        print(
            "Use these mandatory Meson setup options:\n"
            + shlex.join(
                [
                    "-Dbootstrap_compiler=" + artifact["path"],
                    "-Dbootstrap_compiler_sha256=" + artifact["sha256"],
                    "-Dbootstrap_receipt=" + str(receipt),
                ]
            )
        )
        return
    value = verify(args.compiler, args.sha256, args.receipt, role=args.role)
    if args.action == "verify":
        oracle = next(
            stage["artifact"]
            for stage in value["stages"]
            if stage["source"]["name"] == value["route"]["historical_cpp_oracle"]
        )
        print(oracle["path"] + "\n" + oracle["sha256"])
    if args.action == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        require(command, "missing guarded command")
        subprocess.run(command, check=True)
        verify(args.compiler, args.sha256, args.receipt, role=args.role)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        reason = str(error)
        if "Rebuild predecessor:" not in reason:
            reason += "\nRebuild predecessor: " + rebuild_command()
        sys.exit("bootstrap: " + reason)

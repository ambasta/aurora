#!/usr/bin/env python3
"""Compare an external old emitter with a candidate over the complete source corpus.

The explicitly supplied compilers receive identical paths/options, including all
three outputs. Compare bytes, never parsed/normalized JSON or assembly. Against the
historical predecessor, exit status, diagnostics and ABI facts must match exactly;
its assembly and stack facts are recorded but may differ, because code generation
is allowed to improve. C1/C2 convergence stays byte-exact for every output. One run
covers one selected flag profile; default, local symbols and referenced reflection
are not interchangeable receipts. All evidence is retained in a new directory.

This covers the same five *.au source roots as hosted_lexer_bootstrap.py, including
rejected standalone modules. It does not generate the Python runners' embedded
fixtures, execute machine code, inject I/O failures, or establish build provenance.
Text diagnostics are compared verbatim; JSON diagnostics require --check and do
not exercise emission. Equal rejection is not an emitter-coverage observation.
Success must replace each output inode; rejection must preserve bytes and file
metadata. These observations do not prove fault-time or three-file atomicity.
The default profile compares current C1/C2 for every input and historical
predecessor/C2 from the same observations, compiling each role once per input.
Other profiles compare predecessor/C2 for historical inputs; later consumers
always require successful C1/C2 emission and rejection by the old compiler.
An accepted unlisted input fails until explicitly added to historical coverage.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_frontend import stage_modules
from frontend_bridge import render
from qemu_transport import run_logged

SOURCE_ROOTS = ("compiler", "examples", "kernel", "library", "tests")


def non_emitter_path(name):
    """Only known documentation and native-kernel edits may omit the second profile.

    Everything else is conservative: compiler/ABI sources, generators, options,
    runtime/library inputs, AU corpus inputs, tools and the selector's own tests.
    """
    path = Path(name)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        raise ValueError("unsupported Git path")
    return (
        path.suffix == ".md"
        or name == "LICENSE"
        or (path.parts[0] == "kernel" and path.suffix in (".cpp", ".hpp", ".h", ".inc", ".s", ".S", ".ld"))
    )


def closed_profile_required(root, comparison_base):
    """Inspect the live worktree, never infer a comparison base or cache a decision."""
    if not comparison_base:
        return True, "no explicit comparison base"
    try:
        root = Path(root).resolve(strict=True)

        def git(*arguments):
            result = subprocess.run(
                ["git", "-C", str(root), "-c", "core.fsmonitor=false", *arguments],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
            if result.stderr:
                raise ValueError("ambiguous Git result")
            return result.stdout

        def paths(*arguments):
            output = git(*arguments)
            if output and not output.endswith("\0"):
                raise ValueError("incomplete Git path list")
            return output.split("\0")[:-1]

        if Path(git("rev-parse", "--show-toplevel").strip()).resolve() != root:
            raise ValueError("unsupported source root")
        for name in (*SOURCE_ROOTS, "runtime", "scripts"):
            if not (root / name).is_dir() or (root / name).is_symlink():
                raise ValueError("unsupported source layout")
        for name in ("meson.build", "meson_options.txt", "compiler/x86_module.au", "scripts/frontend_bridge.py"):
            if not (root / name).is_file():
                raise ValueError("unsupported source layout")
        base = git("rev-parse", "--verify", "--end-of-options", comparison_base + "^{commit}").strip()
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
            raise ValueError("unresolved comparison commit")
        tracked = paths("ls-files", "-v", "-z")
        if not tracked or any(not row.startswith("H ") for row in tracked):
            raise ValueError("unsupported index state")
        if any((root / row[2:]).is_symlink() for row in tracked if not non_emitter_path(row[2:])):
            raise ValueError("unsupported source symlink")
        # This compares base directly with the current working tree, including
        # staged and unstaged changes. New relevant files must not disappear.
        names = paths("diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", base, "--")
        names += paths("ls-files", "--others", "--exclude-standard", "-z")
        # Local ignore rules must not hide an AU module that can shadow imports.
        # Limit this check to source roots, not retained/generated build outputs.
        names += [
            name
            for name in paths(
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "-z",
                "--",
                *SOURCE_ROOTS,
                "runtime",
                "scripts",
            )
            if Path(name).suffix == ".au"
        ]
        relevant = sorted(name for name in names if not non_emitter_path(name))
        if relevant:
            return True, f"base {base}: emitter-relevant or unknown input {relevant[0]}"
        return False, f"base {base}: only known non-emitter changes ({len(names)} paths)"
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return True, "comparison unavailable: " + str(error)


def selected_closed_profile(arguments):
    parser = argparse.ArgumentParser(description="Run the closed emitter profile unless an explicit base excludes it")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--comparison-base", default="")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(arguments)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("missing closed-profile command")
    required, reason = closed_profile_required(args.source_root, args.comparison_base)
    print(("RUN" if required else "SKIP") + " closed emitter profile: " + reason, flush=True)
    if not required:
        return 77
    # Replace the selector so Meson's existing timeout/signal owner supervises
    # the real guarded command, without another waiting process layer.
    os.execvp(command[0], command)


OUTPUTS = ("assembly.s", "stack.json", "abi.json")
HISTORICAL_EXACT = ("abi.json",)
SENTINELS = {name: ("preserve previous " + name + " on rejection\n").encode() for name in OUTPUTS}
# These exported vocabulary-only modules have no concrete free function when
# compiled alone. Their declarations are exercised through the complete frontend.
# Every other corpus input must emit. Equal rejection is not emitter coverage, so
# a file that stops compiling under both compilers must fail here, not pass.
EXPECTED_REJECTED = {
    # Vocabulary and storage modules declare no function to emit on their own.
    "compiler/lowering_errors.au",
    "compiler/lowering_kinds.au",
    "compiler/resolution_kinds.au",
    "kernel/policies/kernel/note_read.au",
    "kernel/policies/kernel/snapshot.au",
    "library/console/line.au",
    "library/std/array.au",
    "library/std/utility.au",
}
# Preserve the initial gate's members and extend this list for every source the
# historical oracle accepts. Unlisted inputs must prove unsupported, not bypass it.
HISTORICAL_CORPUS = Path(__file__).with_name("emitter-historical-corpus.txt")
# Retired production modules remain byte-exact historical emitter inputs. Stage
# their imports for this gate only; never reintroduce them into the frontend.
HISTORICAL_MODULES = {
    "tests/fixtures/emitter-history/ir_initialization.au": (
        "fa1da348a72dd84453639baa0b1dd80e1e93bd6828c0aa7dee95db8ea67f281f"
    ),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def sources(root):
    # Match hosted_lexer_bootstrap.py: source roots, never generated build trees.
    return sorted(path for name in SOURCE_ROOTS for path in (root / name).rglob("*.au"))


def source_identities(root):
    return {str(path.relative_to(root)): identity(path) for path in sources(root)}


def file_state(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {"kind": "missing"}
    if not stat.S_ISREG(info.st_mode):
        return {"kind": "nonregular", "mode": info.st_mode}
    return {
        "kind": "regular",
        **identity(path),
        "device": info.st_dev,
        "inode": info.st_ino,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def bytes_equal(left, right):
    # Read real bytes even when the evidence hashes agree. Do not normalize JSON,
    # trailing whitespace, symbol order, newlines, diagnostic paths or numbers.
    with left.open("rb") as first, right.open("rb") as second:
        while True:
            a, b = first.read(1024 * 1024), second.read(1024 * 1024)
            if a != b:
                return False
            if not a:
                return True


def observe(compiler, arguments, invocation, destination, root, timeout):
    destination.mkdir(parents=True)
    invocation.mkdir()
    for name, content in SENTINELS.items():
        (invocation / name).write_bytes(content)
    before = {name: file_state(invocation / name) for name in OUTPUTS}
    record = {"command": [str(compiler), *arguments], "cwd": str(root), "timeout_seconds": timeout}
    write_json(destination / "run.json", {**record, "state": "running", "before": before})
    started = time.monotonic()
    try:
        with (destination / "stdout.bin").open("wb") as stdout, (destination / "stderr.bin").open("wb") as stderr:
            # The existing shared runner bounds diagnostic output and cleans up
            # the owned process group, including interruption and wall timeout.
            record["returncode"] = run_logged(
                record["command"], stdout, stderr=stderr, cwd=root, timeout=timeout, timeout_status=False
            )
    except BaseException as error:
        record["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        record["wall_seconds"] = time.monotonic() - started
        record["before"] = before
        record["after"] = {name: file_state(invocation / name) for name in OUTPUTS}
        record["unexpected_outputs"] = sorted(path.name for path in invocation.iterdir() if path.name not in OUTPUTS)
        record["diagnostics"] = {name: file_state(destination / name) for name in ("stdout.bin", "stderr.bin")}
        record["state"] = "failed" if "error" in record else "finished"
        invocation.rename(destination / "outputs")
        write_json(destination / "run.json", record)
    return record


def observation_problems(case, label, run, must_accept):
    problems = []
    status = run["returncode"]
    if status not in (0, 1):
        problems.append(f"{label}: crash or invocation failure ({status})")
    if must_accept and status != 0:
        problems.append(f"{label}: required compiler/library module rejected")
    if b"AU9001" in (case / label / "stderr.bin").read_bytes():
        problems.append(f"{label}: internal compiler diagnostic")
    if run["unexpected_outputs"]:
        problems.append(f"{label}: unexpected output files {run['unexpected_outputs']}")
    for name in OUTPUTS:
        before, after = run["before"][name], run["after"][name]
        if after["kind"] != "regular":
            problems.append(f"{label}: missing/nonregular {name}")
            continue
        path = case / label / "outputs" / name
        if status == 1:
            if before != after or path.read_bytes() != SENTINELS[name]:
                problems.append(f"{label}: rejected compilation changed {name}")
        elif status == 0:
            if after["bytes"] == 0 or path.read_bytes() == SENTINELS[name]:
                problems.append(f"{label}: successful compilation did not produce {name}")
            if (before["device"], before["inode"]) == (after["device"], after["inode"]):
                problems.append(f"{label}: successful compilation did not replace {name}")
    return problems


def compare(case, runs, must_accept, labels=("old", "new")):
    problems = [
        problem
        for label, run in zip(labels, runs, strict=True)
        for problem in observation_problems(case, label, run, must_accept)
    ]
    if runs[0]["returncode"] != runs[1]["returncode"]:
        problems.append("exit status differs")
    for name in ("stdout.bin", "stderr.bin"):
        if not bytes_equal(case / labels[0] / name, case / labels[1] / name):
            problems.append(f"{name} differs byte-for-byte")
    # The predecessor fixes language behavior and the ABI contract, not code
    # quality; current C1/C2 must still agree on every byte of every output.
    exact = HISTORICAL_EXACT if labels == ("old", "new") else OUTPUTS
    for name in OUTPUTS:
        if all(run["after"][name]["kind"] == "regular" for run in runs):
            if not bytes_equal(case / labels[0] / "outputs" / name, case / labels[1] / "outputs" / name):
                if name in exact:
                    problems.append(f"{name} differs byte-for-byte")
                else:
                    write_json(case / f"historical-{name}-differs.json", {"compilers": list(labels)})
    return problems


def oracle_membership_problems(case, run):
    problems = observation_problems(case, "old", run, False)
    if run["returncode"] == 0:
        problems.append("oracle accepted unlisted input; extend the historical corpus")
    # Only located source syntax/type diagnostics establish unsupported input.
    # Missing modules, invocation failures and internal errors cannot remove
    # independent emitter coverage.
    if run["returncode"] != 1 or not re.fullmatch(
        rb"(?:[^\n]+:[0-9]+:[0-9]+: error AU(?:100[1-3]|200[1-3]|3001): [^\n]+\n)+",
        (case / "old/stderr.bin").read_bytes(),
    ):
        problems.append("unlisted input did not produce a source-language rejection")
    if (case / "old/stdout.bin").read_bytes():
        problems.append("unlisted input oracle produced unexpected stdout")
    return problems


def observe_case(
    case, compilers, arguments, root, timeout, *, historical, must_accept, current_convergence, source=None
):
    """Share actual same-run observations across comparison edges, never receipts."""
    invocation = case / "invocation"
    selected = ("old", "c1", "new") if current_convergence or not historical else ("old", "new")
    runs = {}
    for label in selected:
        runs[label] = observe(compilers[label], arguments, invocation, case / label, root, timeout)
        if label == "old" and not historical:
            problems = oracle_membership_problems(case, runs[label])
            write_json(case / "oracle-membership.json", {"source": source or case.name, "problems": problems})
            require(not problems, str(case) + ": " + "; ".join(problems))
    edges = [("old", "new")] if historical else []
    if current_convergence or not historical:
        edges.append(("c1", "new"))
    comparisons = [
        {"compilers": list(edge), "problems": compare(case, [runs[label] for label in edge], must_accept, edge)}
        for edge in edges
    ]
    problems = ["/".join(row["compilers"]) + ": " + problem for row in comparisons for problem in row["problems"]]
    return runs, comparisons, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-compiler", type=Path, required=True, help="explicit external old-backend executable")
    parser.add_argument("--old-compiler-sha256", help="digest Meson verified for the old compiler")
    parser.add_argument("--new-compiler", type=Path, required=True, help="explicit candidate executable")
    parser.add_argument(
        "--stage1-compiler", type=Path, required=True, help="current C1 for corpus convergence and later consumers"
    )
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--artifacts", type=Path, required=True, help="new directory; never removed, even on success")
    parser.add_argument("--local-symbols", action="store_true", help="apply to both compilers for every input")
    parser.add_argument(
        "--referenced-reflection-only", action="store_true", help="apply to both compilers for every input"
    )
    args = parser.parse_args()
    root, artifacts = args.source_root.resolve(strict=True), args.artifacts.resolve()
    labels = ("old", "new", "c1")
    compilers = [path.resolve(strict=True) for path in (args.old_compiler, args.new_compiler, args.stage1_compiler)]
    for path in compilers:
        require(path.is_file() and os.access(path, os.X_OK), f"compiler is not executable: {path}")
    compiler_ids = {label: {"path": str(path), **identity(path)} for label, path in zip(labels, compilers, strict=True)}
    require(compiler_ids["old"]["sha256"] != compiler_ids["new"]["sha256"], "old and new compiler bytes are identical")
    require(
        args.old_compiler_sha256 in (None, compiler_ids["old"]["sha256"]),
        "old compiler changed since Meson verified it; reconfigure Meson",
    )
    for name in SOURCE_ROOTS:
        require((root / name).is_dir(), f"source root missing: {name}")
        require(not artifacts.is_relative_to(root / name), "artifacts must be outside the enumerated source roots")
    corpus = sources(root)
    historical = {line for line in HISTORICAL_CORPUS.read_text().splitlines() if line and not line.startswith("#")}
    require(historical and {root / name for name in historical}.issubset(corpus), "historical corpus inputs missing")
    require(EXPECTED_REJECTED.issubset(historical), "historical standalone rejection coverage missing")
    new_consumers = {str(path.relative_to(root)) for path in corpus} - historical
    modules = sorted((root / "compiler").glob("*.au"))
    historical_modules = [root / name for name in HISTORICAL_MODULES]
    for name, expected_digest in HISTORICAL_MODULES.items():
        require(name in historical, "retired module missing from historical emitter corpus: " + name)
        require(identity(root / name)["sha256"] == expected_digest, "retired historical module changed: " + name)
    decimal = root / "library/std/decimal_digits.au"
    required = {root / "compiler/frontend.au", root / "compiler/lexer.au", decimal, *modules, *historical_modules}
    require(len(corpus) > 1 and required.issubset(corpus), "required compiler/library corpus inputs are missing")
    flags = [
        flag
        for flag, enabled in (
            ("--local-symbols", args.local_symbols),
            ("--referenced-reflection-only", args.referenced_reflection_only),
        )
        if enabled
    ]
    current_convergence = not flags
    artifacts.mkdir(parents=True, exist_ok=False)
    print(f"Retaining emitter differential evidence: {artifacts}", flush=True)
    report = {
        "state": "running",
        "total_inputs": len(corpus),
        "completed_inputs": 0,
        "accepted": 0,
        "rejected": 0,
        "new_consumers_converged": [],
        "current_convergence_inputs": [],
    }
    rejected = []
    try:
        original_sources = source_identities(root)
        bridge_identity = identity(ROOT / "scripts/frontend_bridge.py")
        module_root = artifacts / "compiler-modules"
        staged_inputs = [*modules, *historical_modules, decimal]
        stage_modules(module_root, staged_inputs)
        staged = {str(path.relative_to(module_root)): identity(path) for path in sorted(module_root.rglob("*.au"))}
        expected = sorted(
            (
                hashlib.sha256(render(path.read_bytes().decode()).encode()).hexdigest(),
                len(render(path.read_bytes().decode()).encode()),
            )
            for path in staged_inputs
        )
        require(sorted((row["sha256"], row["bytes"]) for row in staged.values()) == expected, "module staging differs")
        write_json(
            artifacts / "inputs.json",
            {
                "source_root": str(root),
                "source_roots": SOURCE_ROOTS,
                "sources": original_sources,
                "compilers": compiler_ids,
                "flags": flags,
                "current_convergence": current_convergence,
                "historical_corpus": sorted(historical),
                "historical_corpus_manifest": identity(HISTORICAL_CORPUS),
                "new_consumers": sorted(new_consumers),
                "staged_modules": staged,
                "harness": identity(Path(__file__)),
                "staging_helper": identity(ROOT / "scripts/bootstrap_frontend.py"),
                "bridge_table": bridge_identity,
                "process_helper": identity(ROOT / "scripts/qemu_transport.py"),
                "scope": "All source-root *.au inputs; one flag profile; assembly plus both sidecars; text diagnostics",
                "limits": "Artifact identity is not compiler build provenance; no machine execution or I/O injection",
            },
        )
        for source in corpus:
            relative = source.relative_to(root)
            case = artifacts / "cases" / relative
            case.mkdir(parents=True)
            invocation = case / "invocation"
            # Kernel programs import kernel/policies; without it they only "reject".
            roots = (
                [module_root]
                if source in modules
                or source in historical_modules
                or source == root / "tests/compiler/initialization_probe.au"
                else [root / "library", root / "kernel/policies"]
            )
            arguments = [
                *flags,
                *(argument for path in roots for argument in ("--module-root", str(path))),
                str(module_root / "aurora/compiler/frontend.au" if source == root / "compiler/frontend.au" else source),
                "-o",
                str(invocation / "assembly.s"),
                "--stack-facts",
                str(invocation / "stack.json"),
                "--abi-facts",
                str(invocation / "abi.json"),
            ]
            # Match the existing corpus watchdog and whole-frontend exception.
            timeout = 90 if source == root / "compiler/frontend.au" else 30
            compiler_by_label = dict(zip(labels, compilers, strict=True))
            must_accept = str(relative) not in EXPECTED_REJECTED
            runs, comparisons, problems = observe_case(
                case,
                compiler_by_label,
                arguments,
                root,
                timeout,
                historical=str(relative) in historical,
                must_accept=must_accept,
                current_convergence=current_convergence,
                source=str(relative),
            )
            write_json(
                case / "comparison.json", {"source": str(relative), "comparisons": comparisons, "problems": problems}
            )
            report["completed_inputs"] += 1
            if not problems:
                if "c1" in runs:
                    report["current_convergence_inputs"].append(str(relative))
                if str(relative) in new_consumers:
                    report["new_consumers_converged"].append(str(relative))
                elif runs["old"]["returncode"] == 0:
                    report["accepted"] += 1
                else:
                    report["rejected"] += 1
                    rejected.append(str(relative))
            write_json(artifacts / "summary.json", report)
            require(not problems, str(relative) + ": " + "; ".join(problems))
        report["rejected_sources"] = rejected
        require(set(report["new_consumers_converged"]) == new_consumers, "New consumer convergence coverage changed")
        require(
            set(report["current_convergence_inputs"])
            == ({str(path.relative_to(root)) for path in corpus} if current_convergence else new_consumers),
            "Current C1/C2 corpus convergence coverage changed",
        )
        require(
            set(rejected) == EXPECTED_REJECTED,
            f"rejected inputs changed: new {sorted(set(rejected) - EXPECTED_REJECTED)}, "
            f"now accepted {sorted(EXPECTED_REJECTED - set(rejected))}",
        )
        require(source_identities(root) == original_sources, "source corpus changed during comparison")
        require(
            identity(ROOT / "scripts/frontend_bridge.py") == bridge_identity, "bridge table changed during comparison"
        )
        require(
            {str(path.relative_to(module_root)): identity(path) for path in sorted(module_root.rglob("*.au"))}
            == staged,
            "staged modules changed during comparison",
        )
        for label, compiler in zip(labels, compilers, strict=True):
            require({"path": str(compiler), **identity(compiler)} == compiler_ids[label], f"{label} compiler changed")
        report["state"] = "passed"
    except BaseException as error:
        report["state"] = "failed"
        report["error"] = type(error).__name__ + ": " + str(error)
        raise
    finally:
        write_json(artifacts / "summary.json", report)
    print(
        "PASS historical predecessor/C2 and current C1/C2: "
        "assembly, stack, ABI, diagnostics, preservation: " + json.dumps(report),
        flush=True,
    )


if __name__ == "__main__":

    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        if sys.argv[1:2] == ["--select-closed-profile"]:
            sys.exit(selected_closed_profile(sys.argv[2:]))
        main()
    except (OSError, ValueError) as error:
        sys.exit("emitter differential: " + str(error))

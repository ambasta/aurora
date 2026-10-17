#!/usr/bin/env python3
"""Compare an external old emitter with a candidate over the complete source corpus.

The explicitly supplied compilers receive identical paths/options, including all
three outputs. Compare bytes, never parsed/normalized JSON or assembly. One run
covers one selected flag profile; default, local symbols and referenced reflection
are not interchangeable receipts. All evidence is retained in a new directory.

This covers the same five *.au source roots as hosted_lexer_bootstrap.py, including
rejected standalone modules. It does not generate the Python runners' embedded
fixtures, execute machine code, inject I/O failures, or establish build provenance.
Text diagnostics are compared verbatim; JSON diagnostics require --check and do
not exercise emission. Equal rejection is not an emitter-coverage observation.
Success must replace each output inode; rejection must preserve bytes and file
metadata. These observations do not prove fault-time or three-file atomicity.
Historical inputs compare predecessor/C2; exactly two named Call consumers instead
require exact predecessor rejection and successful byte-identical C1/C2 emission.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_frontend import stage_modules
from frontend_bridge import render
from qemu_transport import run_logged

SOURCE_ROOTS = ("compiler", "examples", "kernel", "library", "tests")
OUTPUTS = ("assembly.s", "stack.json", "abi.json")
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
# These two new API consumers are outside the immutable predecessor's language.
# They still run through it, with exact rejection checks, and must emit identically
# through C1/C2. This is a path-specific applicability rule, never rejection discovery.
CALL_CONSUMERS = {"tests/compiler/call_service.au": (3, 22), "tests/kernel-programs/call-client.au": (2, 22)}


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


def compare(case, runs, must_accept, labels=("old", "new")):
    problems = []
    for label, run in zip(labels, runs, strict=True):
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
    if runs[0]["returncode"] != runs[1]["returncode"]:
        problems.append("exit status differs")
    for name in ("stdout.bin", "stderr.bin"):
        if not bytes_equal(case / labels[0] / name, case / labels[1] / name):
            problems.append(f"{name} differs byte-for-byte")
    for name in OUTPUTS:
        if all(run["after"][name]["kind"] == "regular" for run in runs):
            if not bytes_equal(case / labels[0] / "outputs" / name, case / labels[1] / "outputs" / name):
                problems.append(f"{name} differs byte-for-byte")
    return problems


def call_predecessor_problems(case, run, source, root):
    relative = str(source.relative_to(root))
    if relative not in CALL_CONSUMERS:
        return ["not an explicitly named Call consumer"]
    line, column = CALL_CONSUMERS[relative]
    expected = f"{source}:{line}:{column}: error AU2001: expected 'array' (found 'CallSession')\n".encode()
    problems = []
    if run["returncode"] != 1 or run["unexpected_outputs"]:
        problems.append("predecessor did not reject normally with only expected outputs")
    if (case / "old/stdout.bin").read_bytes() or (case / "old/stderr.bin").read_bytes() != expected:
        problems.append("predecessor Call diagnostic differs from exact expected rejection")
    for name in OUTPUTS:
        if (
            run["before"][name] != run["after"][name]
            or run["after"][name]["kind"] != "regular"
            or (case / "old/outputs" / name).read_bytes() != SENTINELS[name]
        ):
            problems.append(f"predecessor Call rejection changed {name}")
    return problems


def oracle_controls(directory, root):
    # Synthetic observations test the oracle itself, never compiler execution.
    case = directory / "synthetic-oracle-controls"
    runs = {}
    for label in ("old", "c1", "new"):
        output = case / label / "outputs"
        output.mkdir(parents=True)
        before = {}
        for name in OUTPUTS:
            path = output / name
            path.write_bytes(SENTINELS[name])
            before[name] = file_state(path)
            if label != "old":
                replacement = output / (name + ".replacement")
                replacement.write_bytes(b"synthetic emitted output\n")
                replacement.replace(path)
        (case / label / "stdout.bin").write_bytes(b"")
        (case / label / "stderr.bin").write_bytes(b"")
        runs[label] = {
            "returncode": 1 if label == "old" else 0,
            "unexpected_outputs": [],
            "before": before,
            "after": {name: file_state(output / name) for name in OUTPUTS},
        }
    source = root / "tests/compiler/call_service.au"
    diagnostic = f"{source}:3:22: error AU2001: expected 'array' (found 'CallSession')\n".encode()
    stderr = case / "old/stderr.bin"
    stderr.write_bytes(diagnostic)
    old = runs["old"]
    require(not call_predecessor_problems(case, old, source, root), "valid synthetic rejection failed")
    require(call_predecessor_problems(case, old, root / "tests/compiler/other.au", root), "broad path exception")
    for status in (0, -9, 2):
        require(call_predecessor_problems(case, {**old, "returncode": status}, source, root), "wrong status accepted")
    for wrong in (b"", diagnostic.replace(b"AU2001", b"AU9001"), diagnostic.replace(b":3:22:", b":2:22:")):
        stderr.write_bytes(wrong)
        require(call_predecessor_problems(case, old, source, root), "wrong diagnostic accepted")
    stderr.write_bytes(diagnostic)
    stdout = case / "old/stdout.bin"
    stdout.write_bytes(b"unexpected")
    require(call_predecessor_problems(case, old, source, root), "unexpected stdout accepted")
    stdout.write_bytes(b"")
    require(
        call_predecessor_problems(case, {**old, "unexpected_outputs": ["extra"]}, source, root),
        "unexpected output accepted",
    )
    for name in OUTPUTS:
        path = case / "old/outputs" / name
        path.write_bytes(b"changed")
        require(call_predecessor_problems(case, old, source, root), "mutated rejection output accepted")
        path.write_bytes(SENTINELS[name])
        changed = {**old, "after": {**old["after"], name: {**old["after"][name], "inode": -1}}}
        require(call_predecessor_problems(case, changed, source, root), "replaced rejection output accepted")
    pair = [runs["c1"], runs["new"]]
    require(not compare(case, pair, True, ("c1", "new")), "valid synthetic convergence failed")
    for name in OUTPUTS:
        path = case / "c1/outputs" / name
        original = path.read_bytes()
        path.write_bytes(b"mismatch")
        require(compare(case, pair, True, ("c1", "new")), "C1/C2 output mismatch accepted")
        path.write_bytes(original)
    require(compare(case, [{**pair[0], "returncode": 1}, pair[1]], True, ("c1", "new")), "C1 rejection accepted")
    write_json(case / "scope.json", {"scope": "synthetic oracle controls only", "state": "passed"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-compiler", type=Path, required=True, help="explicit external old-backend executable")
    parser.add_argument("--new-compiler", type=Path, required=True, help="explicit candidate executable")
    parser.add_argument("--stage1-compiler", type=Path, required=True, help="current C1 for the two Call consumers")
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
    for name in SOURCE_ROOTS:
        require((root / name).is_dir(), f"source root missing: {name}")
        require(not artifacts.is_relative_to(root / name), "artifacts must be outside the enumerated source roots")
    corpus = sources(root)
    require({root / name for name in CALL_CONSUMERS}.issubset(corpus), "named Call consumers missing from corpus")
    modules = sorted((root / "compiler").glob("*.au"))
    decimal = root / "library/std/decimal_digits.au"
    required = {root / "compiler/frontend.au", root / "compiler/lexer.au", decimal, *modules}
    require(len(corpus) > 1 and required.issubset(corpus), "required compiler/library corpus inputs are missing")
    flags = [
        flag
        for flag, enabled in (
            ("--local-symbols", args.local_symbols),
            ("--referenced-reflection-only", args.referenced_reflection_only),
        )
        if enabled
    ]
    artifacts.mkdir(parents=True, exist_ok=False)
    print(f"Retaining emitter differential evidence: {artifacts}", flush=True)
    report = {
        "state": "running",
        "total_inputs": len(corpus),
        "completed_inputs": 0,
        "accepted": 0,
        "rejected": 0,
        "call_converged": [],
    }
    rejected = []
    try:
        oracle_controls(artifacts, root)
        original_sources = source_identities(root)
        bridge_identity = identity(ROOT / "scripts/frontend_bridge.py")
        module_root = artifacts / "compiler-modules"
        stage_modules(module_root, [*modules, decimal])
        staged = {str(path.relative_to(module_root)): identity(path) for path in sorted(module_root.rglob("*.au"))}
        expected = sorted(
            (
                hashlib.sha256(render(path.read_bytes().decode()).encode()).hexdigest(),
                len(render(path.read_bytes().decode()).encode()),
            )
            for path in [*modules, decimal]
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
                "call_consumers": CALL_CONSUMERS,
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
            # Private compiler fixtures import the same staged modules as the
            # frontend. Keep them in the must-emit corpus with all comparisons.
            roots = (
                [module_root]
                if source in modules or source == root / "tests/compiler/ir_projection.au"
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
            runs = [
                observe(compiler, arguments, invocation, case / label, root, timeout)
                for label, compiler in zip(labels[:2], compilers[:2], strict=True)
            ]
            must_accept = str(relative) not in EXPECTED_REJECTED
            if str(relative) in CALL_CONSUMERS:
                c1 = observe(compilers[2], arguments, invocation, case / "c1", root, timeout)
                problems = call_predecessor_problems(case, runs[0], source, root)
                problems += compare(case, [c1, runs[1]], True, ("c1", "new"))
            else:
                problems = compare(case, runs, must_accept)
            write_json(case / "comparison.json", {"source": str(relative), "problems": problems})
            report["completed_inputs"] += 1
            if not problems:
                if str(relative) in CALL_CONSUMERS:
                    report["call_converged"].append(str(relative))
                elif runs[0]["returncode"] == 0:
                    report["accepted"] += 1
                else:
                    report["rejected"] += 1
                    rejected.append(str(relative))
            write_json(artifacts / "summary.json", report)
            require(not problems, str(relative) + ": " + "; ".join(problems))
        report["rejected_sources"] = rejected
        require(set(report["call_converged"]) == set(CALL_CONSUMERS), "Call convergence coverage changed")
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
        "PASS historical predecessor/C2 and named Call rejection+C1/C2: "
        "assembly, stack, ABI, diagnostics, preservation: " + json.dumps(report),
        flush=True,
    )


if __name__ == "__main__":

    def terminate(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit("emitter differential: " + str(error))

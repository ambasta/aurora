#!/usr/bin/env python3
"""Require stage 1 to rebuild its Aurora lexer and preserve compiler outputs."""

from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile


def require(value, message):
    if not value:
        raise AssertionError(message)


def sources(root):
    # Only checked-in source roots, never generated build or retained evidence.
    return sorted(
        path for name in ("compiler", "examples", "kernel", "library", "tests") for path in (root / name).rglob("*.au")
    )


def main():
    stage0, stage1, root = (Path(value).resolve() for value in sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="hosted-lexer-bootstrap-") as temporary:
        work = Path(temporary)
        outputs = [work / "stage0.s", work / "stage1.s"]
        records = []
        corpus = sources(root)
        require(root / "compiler/lexer.au" in corpus, "lexer self-rebuild input is missing")
        for source in corpus:
            runs = []
            for compiler, output in zip((stage0, stage1), outputs, strict=True):
                output.write_bytes(b"preserve on rejection\n")
                runs.append(
                    subprocess.run(
                        [str(compiler), "--module-root", str(root / "library"), str(source), "-o", str(output)],
                        capture_output=True,
                        timeout=30,
                        check=False,
                    )
                )
            for run, output in zip(runs, outputs, strict=True):
                require(run.returncode in (0, 1), f"compiler crash or invocation failure: {source}: {run.returncode}")
                require(b"AU9001" not in run.stderr, f"internal compiler failure: {source}")
                if run.returncode == 1:
                    require(output.read_bytes() == b"preserve on rejection\n", f"rejected output changed: {source}")
            require(
                (runs[0].returncode, runs[0].stdout, runs[0].stderr)
                == (runs[1].returncode, runs[1].stdout, runs[1].stderr),
                f"compiler diagnostics differ: {source}",
            )
            require(
                outputs[0].read_bytes() == outputs[1].read_bytes(), f"assembly/output preservation differs: {source}"
            )
            if source == root / "compiler/lexer.au":
                require(runs[0].returncode == 0, "lexer self-rebuild failed")
                print("PASS stage 1 lexer self-rebuild SHA256 " + hashlib.sha256(outputs[1].read_bytes()).hexdigest())
            records.append({"source": str(source.relative_to(root)), "status": runs[0].returncode})
        require(len(records) > 1, "source corpus is empty")
        print(
            "PASS stage0/stage1 diagnostics, assembly and output preservation: "
            + json.dumps({"sources": len(records), "accepted": sum(row["status"] == 0 for row in records)})
        )


if __name__ == "__main__":
    main()

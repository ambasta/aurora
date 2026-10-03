#!/usr/bin/env python3
"""Bounded source-depth regressions: clean diagnostics, never signals or cleanup overflow."""
from pathlib import Path
import resource
import subprocess
import sys
import tempfile

compiler = Path(sys.argv[1]).resolve()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


cases = [
    ("reported body stack overflow", "{" * 32768 + "return 42;" + "}" * 32768, "block nesting exceeds"),
    ("reported parenthesis stack overflow", "return " + "(" * 16384 + "42" + ")" * 16384 + ";", "expression parser nesting exceeds"),
    ("unary recursion", "return " + "-" * 16384 + "42;", "expression parser nesting exceeds"),
    ("type recursion", "const " + "array<" * 4096 + "i64" + ",1>" * 4096 + " value={42}; return 42;", "type nesting exceeds"),
    ("left-skew AST", "return " + "+".join("1" for _ in range(32768)) + ";", "expression AST depth exceeds"),
    ("member-skew AST", "return value" + ".field" * 16384 + ";", "expression AST depth exceeds"),
    ("index-skew AST", "return value" + "[0]" * 16384 + ";", "expression AST depth exceeds"),
    ("right nested expression", "return " + "1+(" * 8192 + "1" + ")" * 8192 + ";", "expression parser nesting exceeds"),
    ("call recursion", "return " + "call(" * 8192 + "42" + ")" * 8192 + ";", "expression parser nesting exceeds"),
    ("nested conditional bodies", "if(true){" * 8192 + "return 42;" + "}" * 8192 + "return 42;", "block nesting exceeds"),
    ("nested loop bodies", "while(false){" * 8192 + "return 42;" + "}" * 8192 + "return 42;", "block nesting exceeds"),
]
with tempfile.TemporaryDirectory(prefix="aurora-source-depth-") as directory:
    root = Path(directory)
    for name, body, diagnostic in cases:
        source = "module app; auto test()->i64{" + body + "}"
        require(len(source.encode()) < 1024 * 1024, "fixture accidentally exceeds file-byte cap")
        path, output = root / "input.au", root / "output.s"
        path.write_text(source)
        output.unlink(missing_ok=True)
        result = subprocess.run([str(compiler), str(path), "-o", str(output)], capture_output=True,
                                timeout=5, preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
        require(result.returncode == 1, name + f": expected normal rejection, got {result.returncode}")
        require(diagnostic.encode() in result.stderr, name + ": " + repr(result.stderr))
        require(not output.exists(), name + ": emitted artifact on rejection")
        require(path.read_text() == source, name + ": modified source during failure cleanup")
        print("PASS depth", name)
print(f"{len(cases)} bounded-depth rejection cases passed")

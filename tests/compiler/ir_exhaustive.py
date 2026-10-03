#!/usr/bin/env python3
"""Prove new, unhandled IR variants fail both trusted consumers at compile time.

Only temporary header copies are modified. Positive controls first compile the
unchanged headers, then an injected variant must trigger the specific exhaustive
visitor assertion, rather than an unrelated C++ error.
"""
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPILER = shlex.split(os.environ.get("CXX", "g++"))
HEADERS = ("types.hpp", "ir.hpp", "ir_verify.hpp", "x86.hpp")
CONSUMERS = (("ir_verify.hpp", "unhandled typed IR verifier operation"),
             ("x86.hpp", "unhandled typed IR backend operation"))


def compile_probe(directory, header):
    probe = directory / "probe.cpp"
    probe.write_text(f'#include "{header}"\nint main() {{ return 0; }}\n')
    return subprocess.run(COMPILER + ["-std=c++23", "-Werror=switch", "-fsyntax-only", "-I", str(directory), str(probe)],
                          capture_output=True, text=True, timeout=45)


with tempfile.TemporaryDirectory(prefix="aurora-ir-exhaustive-") as temporary:
    directory = Path(temporary)
    for name in HEADERS:
        (directory / name).write_text((ROOT / "compiler" / name).read_text())
    for header, _ in CONSUMERS:
        result = compile_probe(directory, header)
        if result.returncode:
            raise AssertionError(f"{header}: unchanged positive control did not compile:\n{result.stderr}")
        print(f"PASS IR exhaustive unchanged {header} control")
    original = (directory / "ir.hpp").read_text()
    pattern = re.compile(r"(using\s+Instruction\s*=\s*std::variant<)(.*?)(>;)", re.DOTALL)
    if len(pattern.findall(original)) != 1:
        raise AssertionError("could not uniquely locate the Instruction variant for injection")
    injected = pattern.sub(lambda match: "class ExhaustivenessProbe {};\n" + match[1] +
                           match[2] + ", ExhaustivenessProbe" + match[3], original)
    (directory / "ir.hpp").write_text(injected)
    for header, diagnostic in CONSUMERS:
        result = compile_probe(directory, header)
        expected = re.compile(r"static assertion failed[^\n]*" + re.escape(diagnostic))
        if result.returncode == 0 or not expected.search(result.stderr):
            raise AssertionError(f"{header}: missing specific exhaustive-dispatch rejection:\n{result.stderr}")
        print(f"PASS IR exhaustive unknown variant rejected by {header}")
    enum_pattern = re.compile(r"(enum class Binary\s*\{)(.*?)(\};)", re.DOTALL)
    if len(enum_pattern.findall(original)) != 1:
        raise AssertionError("could not uniquely locate Binary operation enumeration")
    enum_injected = enum_pattern.sub(lambda match: match[1] + match[2].rstrip() +
                                    ", ExhaustivenessProbe " + match[3], original)
    (directory / "ir.hpp").write_text(enum_injected)
    for header, _ in CONSUMERS:
        result = compile_probe(directory, header)
        if result.returncode == 0 or "ExhaustivenessProbe" not in result.stderr or "not handled in switch" not in result.stderr:
            raise AssertionError(f"{header}: missing binary-enum exhaustive rejection:\n{result.stderr}")
        print(f"PASS IR exhaustive unknown binary enum rejected by {header}")
print("6 exhaustive IR dispatch checks passed")

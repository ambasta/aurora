#!/usr/bin/env python3
"""Emit the private hosted frontend, standalone lexer, or lexer Event header.

The compiler-module root contains exact exported source copies. Generated Aurora
bindings remain local; only the two trusted assembly bridges expose host entries.
"""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def verify_compiler(compiler, expected_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("compiler SHA-256 must be exactly 64 lowercase hex characters")
    compiler = Path(compiler)
    if not compiler.is_absolute():
        raise ValueError("pinned compiler path must be absolute")
    selected = compiler.resolve()
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise ValueError("pinned compiler must be an executable file")
    digest = hashlib.sha256()
    with selected.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("pinned compiler SHA-256 mismatch")
    return selected


def event_entries(source):
    # This bootstrap input is deliberately a plain, implicit-value enum. Reject
    # other syntax instead of attempting to interpret Aurora constant expressions.
    bodies = re.findall(r"^\s*enum\s+class\s+Event\s*\{([^{}]*)\}\s*;", source.read_text(), re.MULTILINE)
    if len(bodies) != 1:
        raise ValueError("expected one simple enum class Event declaration")
    names = [part.strip() for part in bodies[0].strip().removesuffix(",").split(",")]
    if not all(re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", name) for name in names):
        raise ValueError("Event cases must be plain lowercase names without explicit values")
    host_names = ["".join(part.capitalize() for part in name.split("_")) for name in names]
    if len(set(host_names)) != len(host_names):
        raise ValueError("Event cases must map to distinct host names")
    return "// Generated from compiler/lexer.au; do not edit.\n" + "".join(
        f"    {name} = {value},\n" for value, name in enumerate(host_names)
    )


def stage_modules(module_root, lexer, arena):
    destination = module_root / "aurora" / "compiler"
    destination.mkdir(parents=True, exist_ok=True)
    for source, name in ((lexer, "lexer.au"), (arena, "expression_arena.au")):
        shutil.copyfile(source, destination / name)


def emit(compiler, source, bridges, output, module_root=None, compiler_sha256=None):
    raw = output.with_suffix(".generated.s")
    command = ["--local-symbols"]
    if module_root is not None:
        command += ["--module-root", str(module_root.resolve())]
    command += [str(source.resolve()), "-o", str(raw.resolve())]
    selected = compiler.resolve() if compiler_sha256 is None else verify_compiler(compiler, compiler_sha256)
    subprocess.run([str(selected), *command], check=True)
    # Do not rewrite generated declarations or duplicate the lexer graph.
    output.write_bytes(b"\n".join([raw.read_bytes(), *(bridge.read_bytes() for bridge in bridges)]))


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ["--verify-compiler"]:
        if len(arguments) != 3:
            raise ValueError("--verify-compiler requires a compiler path and SHA-256 digest")
        verify_compiler(arguments[1], arguments[2])
        return

    compiler_sha256 = None
    if arguments[:1] == ["--compiler-sha256"]:
        if len(arguments) < 2:
            raise ValueError("--compiler-sha256 requires a SHA-256 digest")
        compiler_sha256 = arguments[1]
        if not re.fullmatch(r"[0-9a-f]{64}", compiler_sha256):
            raise ValueError("compiler SHA-256 must be exactly 64 lowercase hex characters")
        arguments = arguments[2:]
        if not arguments:
            raise ValueError("--compiler-sha256 requires a compiler invocation")
        if arguments[:1] == ["--events"]:
            raise ValueError("--compiler-sha256 cannot be used with --events")

    if arguments[:1] == ["--events"]:
        source, output = map(Path, arguments[1:])
        entries = event_entries(source)
        if not output.exists() or output.read_bytes() != entries.encode():
            output.write_text(entries)
    elif arguments[:1] == ["--lexer"]:
        compiler, source, bridge, output = map(Path, arguments[1:])
        if compiler_sha256 is not None:
            verify_compiler(compiler, compiler_sha256)
        emit(compiler, source, [bridge], output, compiler_sha256=compiler_sha256)
    else:
        compiler, lexer, arena, parser, lexer_bridge, parser_bridge, output = map(Path, arguments)
        if compiler_sha256 is not None:
            verify_compiler(compiler, compiler_sha256)
        module_root = output.parent / "compiler-modules"
        stage_modules(module_root, lexer, arena)
        emit(compiler, parser, [lexer_bridge, parser_bridge], output, module_root, compiler_sha256)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"bootstrap frontend: {error}")

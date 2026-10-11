#!/usr/bin/env python3
"""Emit the private hosted frontend, standalone lexer, or lexer Event header.

The compiler-module root contains exact exported source copies. Generated Aurora
bindings remain local; only the two trusted assembly bridges expose host entries.
"""

from pathlib import Path
import re
import shutil
import subprocess
import sys


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


def emit(compiler, source, bridges, output, module_root=None):
    raw = output.with_suffix(".generated.s")
    command = [str(compiler.resolve()), "--local-symbols"]
    if module_root is not None:
        command += ["--module-root", str(module_root.resolve())]
    subprocess.run([*command, str(source.resolve()), "-o", str(raw.resolve())], check=True)
    # Do not rewrite generated declarations or duplicate the lexer graph.
    output.write_bytes(b"\n".join([raw.read_bytes(), *(bridge.read_bytes() for bridge in bridges)]))


def main():
    if sys.argv[1:2] == ["--events"]:
        source, output = map(Path, sys.argv[2:])
        entries = event_entries(source)
        if not output.exists() or output.read_bytes() != entries.encode():
            output.write_text(entries)
    elif sys.argv[1:2] == ["--lexer"]:
        compiler, source, bridge, output = map(Path, sys.argv[2:])
        emit(compiler, source, [bridge], output)
    else:
        compiler, lexer, arena, parser, lexer_bridge, parser_bridge, output = map(Path, sys.argv[1:])
        module_root = output.parent / "compiler-modules"
        stage_modules(module_root, lexer, arena)
        emit(compiler, parser, [lexer_bridge, parser_bridge], output, module_root)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"bootstrap frontend: {error}")

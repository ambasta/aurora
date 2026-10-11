#!/usr/bin/env python3
"""Emit one private hosted parser/arena/lexer graph from an explicit seed.

The compiler-module root contains exact exported source copies. Generated Aurora
bindings remain local; only the two trusted assembly bridges expose host entries.
"""

from pathlib import Path
import shutil
import subprocess
import sys


def stage_modules(module_root, lexer, arena):
    destination = module_root / "aurora" / "compiler"
    destination.mkdir(parents=True, exist_ok=True)
    for source, name in ((lexer, "lexer.au"), (arena, "expression_arena.au")):
        shutil.copyfile(source, destination / name)


def main():
    compiler, lexer, arena, parser, lexer_bridge, parser_bridge, output = map(Path, sys.argv[1:])
    module_root = output.parent / "compiler-modules"
    stage_modules(module_root, lexer, arena)
    raw = output.with_suffix(".generated.s")
    subprocess.run(
        [
            str(compiler.resolve()),
            "--local-symbols",
            "--module-root",
            str(module_root.resolve()),
            str(parser.resolve()),
            "-o",
            str(raw.resolve()),
        ],
        check=True,
    )
    # Do not rewrite generated declarations or duplicate the lexer graph.
    output.write_bytes(raw.read_bytes() + b"\n" + lexer_bridge.read_bytes() + b"\n" + parser_bridge.read_bytes())


if __name__ == "__main__":
    main()

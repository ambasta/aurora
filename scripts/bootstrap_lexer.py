#!/usr/bin/env python3
"""Emit the private hosted lexer unit using an explicitly selected seed compiler.

Only compiler/hosted_lexer.S exposes a host-callable symbol. All generated Aurora
symbols remain local in this object. This is bootstrap machinery, not source FFI.
"""

from pathlib import Path
import re
import subprocess
import sys


def main():
    compiler, source, bridge, output = map(Path, sys.argv[1:])
    raw = output.with_suffix(".generated.s")
    subprocess.run([str(compiler.resolve()), str(source.resolve()), "-o", str(raw.resolve())], check=True)
    assembly = raw.read_text()
    entry = "__au_v_m3_6aurora8compiler5lexer_n1_14compiler_lexer_d11next_lexeme"
    if assembly.count(f"\n.local {entry}\n") != 1 or assembly.count(f"\n{entry}:\n") != 1:
        raise RuntimeError("expected exactly one private next_lexeme entry")
    globals_ = re.findall(r"^\.globl ([A-Za-z_][A-Za-z_0-9]*)$", assembly, re.M)
    if not globals_ or any(
        not (
            name.startswith("__au_f_m3_6aurora8compiler5lexer_")
            or name in ("aurora_reflect_size", "aurora_reflect_field_count")
        )
        for name in globals_
    ):
        raise RuntimeError("unexpected generated global symbol in hosted lexer")
    # Changing symbol binding does not modify the generated executable code.
    local = "".join(f".local {name}\n" for name in globals_)
    output.write_text(assembly + "\n" + local + bridge.read_text())


if __name__ == "__main__":
    main()

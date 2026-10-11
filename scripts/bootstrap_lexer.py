#!/usr/bin/env python3
"""Emit the private hosted lexer unit using an explicitly selected seed compiler.

Only compiler/hosted_lexer.S exposes a host-callable symbol. All generated Aurora
symbols remain local in this object. This is bootstrap machinery, not source FFI.
"""

from pathlib import Path
import subprocess
import sys


def main():
    compiler, source, bridge, output = map(Path, sys.argv[1:])
    raw = output.with_suffix(".generated.s")
    subprocess.run(
        [
            str(compiler.resolve()),
            "--local-symbols",
            str(source.resolve()),
            "-o",
            str(raw.resolve()),
        ],
        check=True,
    )
    # The backend owns binding. Appending the trusted shim does not rewrite any
    # generated declaration or instruction; the bootstrap test checks ELF exports.
    output.write_text(raw.read_text() + "\n" + bridge.read_text())


if __name__ == "__main__":
    main()

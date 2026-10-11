#!/usr/bin/env python3
"""Emit the private hosted lexer unit using an explicitly selected seed compiler.

Only compiler/hosted_lexer.S exposes a host-callable symbol. All generated Aurora
symbols remain local in this object. This is bootstrap machinery, not source FFI.
The --events mode generates host enum entries from the same Aurora source.
"""

from pathlib import Path
import re
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


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--events":
        entries = event_entries(Path(sys.argv[2]))
        output = Path(sys.argv[3])
        if not output.exists() or output.read_bytes() != entries.encode():
            output.write_text(entries)
        return
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
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"bootstrap lexer: {error}")

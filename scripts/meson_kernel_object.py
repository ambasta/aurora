#!/usr/bin/env python3
"""Export an actual native object and its same-compilation GCC sidecars."""

import argparse
import json
from pathlib import Path


def export_object(source, native_object, output, compile_directory, callgraph=False):
    source = source.resolve(strict=True)
    native_object = native_object.resolve(strict=True)
    compile_directory = compile_directory.resolve(strict=True)
    suffixes = [".o", ".su"] + ([".ci"] if callgraph else [])
    # Meson's native rule owns the compile. Never silently recompile a missing
    # sidecar or associate one by basename with a different translation unit.
    inputs = {suffix: native_object if suffix == ".o" else native_object.with_suffix(suffix) for suffix in suffixes}
    contents = {suffix: path.read_bytes() for suffix, path in inputs.items()}
    association = dict(
        source=str(source),
        compile_directory=str(compile_directory),
        native_object=str(native_object),
        sidecars={suffix[1:]: str(path) for suffix, path in inputs.items() if suffix != ".o"},
    )
    for suffix, data in contents.items():
        destination = output.with_suffix(suffix)
        temporary = destination.with_name(destination.name + ".pending")
        temporary.write_bytes(data)
        temporary.replace(destination)
    output.with_suffix(".source.json").write_text(json.dumps(association, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--native-object", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compile-directory", type=Path, required=True)
    parser.add_argument("--callgraph", action="store_true")
    args = parser.parse_args()
    export_object(args.source, args.native_object, args.output, args.compile_directory, args.callgraph)


if __name__ == "__main__":
    main()

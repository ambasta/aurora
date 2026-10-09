#!/usr/bin/env python3
"""Bind an incremental build directory to its configured host-toolchain bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess


IMPLICIT_SEARCH_ENV = ('CPATH', 'CPLUS_INCLUDE_PATH', 'C_INCLUDE_PATH', 'LIBRARY_PATH')


def snapshot(cxx):
    for name in IMPLICIT_SEARCH_ENV:
        if name in os.environ:
            raise ValueError('Unset ' + name + '; use explicit Meson include/link flags in a fresh build directory')
    def query(*args):
        return subprocess.check_output([*cxx, *args], text=True).strip()
    if not cxx:
        raise ValueError('Missing configured C++ command')
    gcc = shutil.which('gcc')
    if not gcc or subprocess.check_output([gcc, '-dumpfullversion'], text=True).strip() != query('-dumpfullversion'):
        raise ValueError('Select matching bare gcc on PATH and configured CXX')
    tools = [*cxx, gcc, 'as', 'ld', 'nm', 'objdump', 'objcopy', 'readelf']
    tools += [query('-print-prog-name=' + name) for name in ('cc1plus', 'collect2', 'as', 'ld')]
    tools += [query('-print-file-name=' + name) for name in ('libstdc++.so', 'libgcc_s.so', 'libgcc_s.so.1', 'libgcc.a')]
    files = {}
    for tool in tools:
        found = shutil.which(tool) if not Path(tool).is_absolute() else tool
        if not found or not Path(found).is_file():
            raise ValueError('Cannot identify configured host input: ' + tool)
        path = Path(found).resolve(strict=True)
        files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(search_policy='explicit-meson-flags-v1', cxx=cxx,
                version=query('-dumpfullversion'), target=query('-dumpmachine'), files=files)


def verify(expected, observed):
    if expected != observed:
        raise ValueError('Host toolchain changed; configure a fresh build directory, do not reuse old objects')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--cxx', required=True)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--stamp', type=Path)
    args = parser.parse_args()
    observed = snapshot(shlex.split(args.cxx))
    if args.record.exists():
        verify(json.loads(args.record.read_text()), observed)
    elif args.configure:
        if (args.record.parent / 'build.ninja').exists():
            raise ValueError('Unbound existing build; configure a fresh directory to avoid stale toolchain objects')
        args.record.write_text(json.dumps(observed, indent=2, sort_keys=True) + '\n')
    else:
        raise ValueError('Missing setup-time toolchain identity; configure a fresh build directory')
    if args.stamp:
        args.stamp.write_text('Host toolchain matches setup identity\n')
    print('PASS configured host-toolchain identity')


if __name__ == '__main__':
    main()

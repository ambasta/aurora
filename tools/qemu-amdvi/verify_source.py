#!/usr/bin/env python3
"""Reconstruct the reviewed patches in memory from an external exact QEMU base."""

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
BASE = {
    "hw/i386/amd_iommu.c": "7dbe81fc13a533c265683ee70cd616ccc00e46e890b17dd0113e79d5f9fa52d3",
    "hw/i386/amd_iommu.h": "f19a9e828d3fce319099cf3e4800818a824c4b9ae8d7913eb33778b92d87aff5",
}
STAGES = [
    (
        "0001-event-record-transport.patch",
        {
            "hw/i386/amd_iommu.c": "c6846f7f2c99e8df8a2357f55cc0ae29e96ff5c17fa18d54a6e9a4fc8d8c706d",
            "hw/i386/amd_iommu.h": "9866ac5d8ebffd39a568df5241e550c115cc84f7080c9b58c2498c104144097e",
        },
    ),
    (
        "0002-mode1-requester-permissions-v2.patch",
        {
            "hw/i386/amd_iommu.c": "4222633b8d1dcadd0d9f43f9fd6a56998e2348034d4b39ff40c4c0ea65e08da4",
            "hw/i386/amd_iommu.h": "94d50d0dd0548c533252b4fdff7ec3cf800aed8655ce38db24de837adf1785e4",
        },
    ),
    (
        "0003-command-stop-v1.patch",
        {
            "hw/i386/amd_iommu.c": "a506dccf0c112cc791208724651b3aaca300f8b713362dfd07af2308e6f5a2d9",
            "hw/i386/amd_iommu.h": "94d50d0dd0548c533252b4fdff7ec3cf800aed8655ce38db24de837adf1785e4",
        },
    ),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apply_patch(inputs, patch):
    """Strict unified diff: exact paths, hunk coordinates and old bytes; no fuzz."""
    values = dict(inputs)
    lines = patch.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- a/"):
            raise ValueError("Expected old-file header")
        name = lines[index][6:].rstrip("\n")
        index += 1
        if index == len(lines) or lines[index] != "+++ b/" + name + "\n" or name not in values:
            raise ValueError("Unsupported patch path")
        index += 1
        old = values[name].decode().splitlines(keepends=True)
        new, cursor = [], 0
        while index < len(lines) and lines[index].startswith("@@ "):
            match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n", lines[index])
            if match is None:
                raise ValueError("Invalid hunk header")
            before, old_count, after, new_count = (int(value) if value is not None else 1 for value in match.groups())
            start = before - 1
            if start < cursor or start > len(old):
                raise ValueError("Invalid old hunk position")
            new.extend(old[cursor:start])
            if len(new) != after - 1:
                raise ValueError("Invalid new hunk position")
            cursor, removed, added = start, 0, 0
            index += 1
            while index < len(lines) and lines[index][:1] in (" ", "+", "-"):
                if lines[index].startswith("--- a/"):
                    break
                tag, value = lines[index][0], lines[index][1:]
                if tag in " -":
                    if cursor >= len(old) or old[cursor] != value:
                        raise ValueError("Old hunk bytes differ")
                    cursor += 1
                    removed += 1
                if tag in " +":
                    new.append(value)
                    added += 1
                index += 1
            if (removed, added) != (old_count, new_count):
                raise ValueError("Hunk size mismatch")
        new.extend(old[cursor:])
        values[name] = "".join(new).encode()
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu-source", type=Path, required=True)
    args = parser.parse_args()
    files = {name: (args.qemu_source / name).read_bytes() for name in BASE}
    if {name: sha(data) for name, data in files.items()} != BASE:
        raise SystemExit("QEMU base source identity mismatch; no patch was applied")
    manifest = json.loads((ROOT / "artifacts.json").read_text())["sha256"]
    stages = []
    for name, expected in STAGES:
        path = ROOT / "patches" / name
        data = path.read_bytes()
        if sha(data) != manifest["tools/qemu-amdvi/patches/" + name]:
            raise SystemExit("Patch identity mismatch: " + name)
        files = apply_patch(files, data.decode())
        observed = {name: sha(data) for name, data in files.items()}
        if expected is not None and observed != expected:
            raise SystemExit("Reconstructed source identity mismatch: " + name)
        stages.append({"patch": name, "source_sha256": observed})
    print(json.dumps({"pass": True, "scope": "in-memory source reconstruction only", "stages": stages}, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Prepare byte-preserving UTF-8 Git tree requests locally; never publish them.

Reads tar member bytes directly, never Path.read_text()/universal-newline I/O.
Fails closed on non-UTF-8 members, special files, unsupported permission
bits, duplicate/unsafe paths, and file/directory collisions. Output is exclusive
create so an earlier artifact is never silently replaced. Git does not record
empty directories, timestamps, owners, or permission bits other than executable.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile


def validate_path(path):
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ValueError(f"Invalid path: {path!r}")
    if any(part in ("", ".", "..", ".git") for part in path.split("/")):
        raise ValueError(f"Unsafe or non-canonical path: {path!r}")
    path.encode("utf-8", errors="strict")
    return path


def decode_exact(data):
    text = data.decode("utf-8", errors="strict")
    if text.encode("utf-8", errors="strict") != data:
        raise ValueError("UTF-8 round-trip mismatch")
    return text


def index_entries(entries):
    if not isinstance(entries, list):
        raise ValueError("Snapshot must be a list")
    indexed = {}
    for entry in entries:
        if set(entry) != {"path", "mode", "type", "content"}:
            raise ValueError("Snapshot entries require path/mode/type/content only")
        path = validate_path(entry["path"])
        if path in indexed:
            raise ValueError(f"Duplicate path: {path}")
        if entry["type"] != "blob" or entry["mode"] not in ("100644", "100755", "120000"):
            raise ValueError(f"Unsupported Git entry: {path}")
        if not isinstance(entry["content"], str):
            raise ValueError(f"Content must be a UTF-8 string: {path}")
        entry["content"].encode("utf-8", errors="strict")
        indexed[path] = entry
    for path in indexed:
        parts = path.split("/")
        for stop in range(1, len(parts)):
            if "/".join(parts[:stop]) in indexed:
                raise ValueError(f"File/directory collision: {path}")
    return indexed


def read_snapshot(path):
    entries = json.loads(Path(path).read_bytes())
    index_entries(entries)
    return entries


def snapshot_archive(archive, prefix="aurora/"):
    if prefix and not prefix.endswith("/"):
        raise ValueError("Archive prefix must be empty or end in /")
    entries = []
    seen = set()
    directories = set()
    raw_members = {}
    with tarfile.open(archive, "r:*") as stream:
        for member in stream:
            name = member.name
            if prefix:
                if name.rstrip("/") == prefix.rstrip("/") and member.isdir():
                    continue
                if not name.startswith(prefix):
                    raise ValueError(f"Member outside explicit archive prefix: {name}")
                name = name[len(prefix):]
            elif name.startswith("./"):
                name = name[2:]
            if member.isdir() and name in ("", "."):
                continue
            if member.isdir():
                name = name.rstrip("/")
            validate_path(name)
            if name in seen:
                raise ValueError(f"Duplicate tar member: {name}")
            seen.add(name)
            if member.isdir():
                directories.add(name)
                continue
            if member.isfile():
                if member.mode not in (0o644, 0o755):
                    raise ValueError(f"Unrepresentable/nonstandard file permissions: {name}: {oct(member.mode)}")
                extracted = stream.extractfile(member)
                if extracted is None:
                    raise ValueError(f"Cannot read tar member: {name}")
                data = extracted.read()
                if len(data) != member.size:
                    raise ValueError(f"Truncated tar member: {name}")
                mode = "100755" if member.mode == 0o755 else "100644"
            elif member.issym():
                if member.mode != 0o777:
                    raise ValueError(f"Unrepresentable symlink permissions: {name}: {oct(member.mode)}")
                data = member.linkname.encode("utf-8", errors="strict")
                mode = "120000"
            else:
                raise ValueError(f"Unsupported tar member type: {name}: {member.type!r}")
            raw_members[name] = data
            entries.append({"path": name, "mode": mode, "type": "blob", "content": decode_exact(data)})
    entries.sort(key=lambda entry: entry["path"].encode("utf-8"))
    indexed = index_entries(entries)
    for directory in directories:
        for stop in range(1, len(directory.split("/")) + 1):
            ancestor = "/".join(directory.split("/")[:stop])
            if ancestor in indexed:
                raise ValueError(f"File/directory collision: {directory}")
    # Assert the serialized transport, not only the in-memory strings, is exact.
    roundtrip = json.loads(serialize_json(entries))
    if index_entries(roundtrip) != indexed:
        raise ValueError("JSON round-trip changed snapshot entries")
    if {entry["path"]: entry["content"].encode("utf-8") for entry in roundtrip} != raw_members:
        raise ValueError("JSON round-trip changed member bytes")
    return entries


def serialize_json(value):
    return (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode("utf-8")


def write_json_new(path, value):
    data = serialize_json(value)
    with Path(path).open("xb") as stream:
        stream.write(data)
    if Path(path).read_bytes() != data:
        raise ValueError(f"Output read-back mismatch: {path}")
    return hashlib.sha256(data).hexdigest()


def git_object_id(kind, data):
    header = kind.encode("ascii") + b" " + str(len(data)).encode("ascii") + b"\0"
    return hashlib.sha1(header + data).hexdigest()


def git_tree_id(entries):
    root = {}
    for path, entry in index_entries(entries).items():
        parent = root
        components = path.split("/")
        for component in components[:-1]:
            parent = parent.setdefault(component, {})
        parent[components[-1]] = (entry["mode"], git_object_id("blob", entry["content"].encode("utf-8")))

    def visit(directory):
        output = bytearray()
        # Git sorts subdirectory names as if they ended with a slash.
        for name, value in sorted(directory.items(), key=lambda pair: (pair[0] + ("/" if isinstance(pair[1], dict) else "")).encode("utf-8")):
            mode, digest = ("40000", visit(value)) if isinstance(value, dict) else value
            output.extend(mode.encode("ascii") + b" " + name.encode("utf-8") + b"\0" + bytes.fromhex(digest))
        return git_object_id("tree", bytes(output))

    return visit(root)


def make_delta(base, target, expected_base_tree=None):
    if expected_base_tree is not None and git_tree_id(base) != expected_base_tree:
        raise ValueError("Base snapshot does not match the expected published Git tree")
    before = index_entries(base)
    after = index_entries(target)
    delta = []
    for path in sorted(before.keys() | after.keys(), key=lambda value: value.encode("utf-8")):
        if path not in after:
            delta.append({"path": path, "mode": before[path]["mode"], "type": "blob", "sha": None})
        elif before.get(path) != after[path]:
            delta.append(after[path])
    if index_entries(apply_delta(base, delta)) != after:
        raise ValueError("Delta does not recreate the target")
    return delta


def apply_delta(base, delta):
    result = dict(index_entries(base))
    seen = set()
    for entry in delta:
        path = validate_path(entry["path"])
        if path in seen:
            raise ValueError(f"Duplicate delta path: {path}")
        seen.add(path)
        if "sha" in entry:
            if set(entry) != {"path", "mode", "type", "sha"} or entry["sha"] is not None:
                raise ValueError(f"Invalid deletion: {path}")
            if path not in result:
                raise ValueError(f"Deletion target missing: {path}")
            if entry["mode"] != result[path]["mode"] or entry["type"] != "blob":
                raise ValueError(f"Deletion metadata mismatch: {path}")
            del result[path]
        else:
            index_entries([entry])
            result[path] = entry
    entries = [result[path] for path in sorted(result, key=lambda value: value.encode("utf-8"))]
    index_entries(entries)
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--archive", type=Path, required=True)
    snapshot.add_argument("--prefix", default="aurora/")
    snapshot.add_argument("--output", type=Path, required=True)
    delta = sub.add_parser("delta")
    delta.add_argument("--base", type=Path, required=True)
    delta.add_argument("--target", type=Path, required=True)
    delta.add_argument("--expected-base-tree", required=True)
    delta.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "snapshot":
        entries = snapshot_archive(args.archive, args.prefix)
        digest = write_json_new(args.output, entries)
        print(json.dumps({"entries": len(entries), "git_tree": git_tree_id(entries), "output_sha256": digest}))
    else:
        base = read_snapshot(args.base)
        target = read_snapshot(args.target)
        entries = make_delta(base, target, args.expected_base_tree)
        digest = write_json_new(args.output, entries)
        print(json.dumps({"delta_entries": len(entries), "base_tree": git_tree_id(base), "target_tree": git_tree_id(target), "output_sha256": digest}))


if __name__ == "__main__":
    main()

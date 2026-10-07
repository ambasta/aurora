#!/usr/bin/env python3
"""Native indexed-root checks with preserved fixtures and a Python byte model."""
from pathlib import Path
import hashlib
import os
import tempfile

import xfs_root as root_model
from unsigned_oracle import Case, NativeRunner, Rejection, require


IMPORTS = ("fs.xfs_root",)
FACTS = ("root_inode", "inode_offset_bytes", "parent_inode", "entry_count", "payload_bytes")
ENTRY = ("inode_number", "file_type", "name_offset_bytes", "name_length_bytes")


def array(name, data):
    values = ", ".join(f"{byte}u8" for byte in data)
    return f"builtin::array<u8, {len(data)}> {name} = {{{values}}};\n"


def expected(sb, inode, index):
    # The existing independent parser supplies complete metadata validation.
    # A negative index occupies the same query-validation precedence position.
    validated = root_model.oracle(sb, inode, b"." if index < 0 else b"?")
    if validated.status == "invalid_query":
        return "invalid_index", "entry_index", (0,) * 5, (0,) * 4, b""
    if validated.status not in ("found", "not_found"):
        return validated.status, validated.issue, (0,) * 5, (0,) * 4, b""
    facts = validated.values[:5]
    count = facts[3]
    if index > count:
        return "invalid_index", "entry_index", (0,) * 5, (0,) * 4, b""
    if index == count:
        return "end", "none", facts, (0,) * 4, b""
    cursor = 182
    for _ in range(index):
        cursor += inode[cursor] + 8
    length = inode[cursor]
    name = inode[cursor + 3:cursor + 3 + length]
    number = int.from_bytes(inode[cursor + 4 + length:cursor + 8 + length], "big")
    entry = (number, inode[cursor + 3 + length], cursor + 3, length)
    return "found", "none", facts, entry, name


def getters(variable, names, values):
    text = ""
    for getter, value in zip(names, values):
        text += f"""
            if ({variable}.{getter}() != {value}u64) {{
                return 0u64;
            }}
        """
    return text


def native_case(label, sb, inode, index):
    status, issue, facts, entry, name = expected(sb, inode, index)
    text = array("superblock", sb) + array("inode", inode)
    text += f"""
        const builtin::array<u8, {len(sb)}> saved_superblock = superblock;
        const builtin::array<u8, {len(inode)}> saved_inode = inode;
        const fs::XfsRootEntryReport report = fs::entry_at_xfs_v5_512_root(
            borrow_bytes(superblock), borrow_bytes(inode), {index});
        if (report.status() != fs::XfsRootEntryStatus::{status}) {{
            return 0u64;
        }}
        if (report.issue() != fs::XfsRootIssue::{issue}) {{
            return 0u64;
        }}
        const fs::XfsRootFacts facts = report.facts();
        const fs::XfsRootEntry entry = report.entry();
    """
    text += getters("facts", FACTS, facts) + getters("entry", ENTRY, entry)
    if name:
        text += array("expected_name", name)
        text += f"""
            i64 name_index = 0;
            while (name_index < {len(name)}) {{
                if (inode[i64(entry.name_offset_bytes()) + name_index] != expected_name[name_index]) {{
                    return 0u64;
                }}
                name_index = name_index + 1;
            }}
        """
    for variable, length in (("superblock", len(sb)), ("inode", len(inode))):
        text += f"""
            i64 {variable}_index = 0;
            while ({variable}_index < {length}) {{
                if ({variable}[{variable}_index] != saved_{variable}[{variable}_index]) {{
                    return 0u64;
                }}
                {variable}_index = {variable}_index + 1;
            }}
        """
    text += """
        const fs::XfsRootEntryReport copy = report;
        superblock[0] = 0u8;
        inode[0] = 0u8;
        const fs::XfsRootFacts copied_facts = copy.facts();
        const fs::XfsRootEntry copied_entry = copy.entry();
    """
    text += getters("copied_facts", FACTS, facts) + getters("copied_entry", ENTRY, entry)
    text += "return 42u64;"
    return Case(f"{label} index {index}: {status}/{issue}", text, 42, imports=IMPORTS)


def cases():
    corpus = root_model.cases()
    require(len(corpus) == 203, "complete root reference corpus expected")
    for case in corpus:
        outcome = root_model.oracle(case.sb, case.inode, b"?")
        count = outcome.values[3] if outcome.status in ("found", "not_found") else 2
        for index in (-1, 0, count, count + 1):
            yield native_case(case.label, case.sb, case.inode, index)
        if outcome.status in ("found", "not_found"):
            for index in range(1, count):
                yield native_case(case.label, case.sb, case.inode, index)
    sb = root_model.fixture("named-superblock.hex")
    inode = root_model.fixture("named-root.hex")
    for index in (-(1 << 63), (1 << 63) - 1):
        yield native_case("signed endpoint", sb, inode, index)
    # Reject a late malformed record and trailing data even for an early entry,
    # end marker, or too-large index: none can bypass complete validation.
    late = root_model.sf(inode, [(b"alpha", 131, 1, 96), (b"a/b", 132, 2, 120)])
    trailing = root_model.setv(inode, 56, 8, 32)
    duplicate = root_model.sf(inode, [(b"alpha", 131, 1, 96), (b"alpha", 132, 2, 120)])
    for label, damaged in (("late malformed entry", late), ("trailing payload", trailing),
                           ("duplicate second name", duplicate)):
        for index in (0, 2, 3, (1 << 63) - 1):
            yield native_case(label, sb, damaged, index)


def report_cases():
    statuses = ("found", "end", "invalid_index", "geometry_rejected", "unsupported_profile",
                "invalid_inode", "invalid_directory")
    for status in statuses:
        facts = (1, 2, 3, 4, 5) if status in ("found", "end") else (0,) * 5
        entry = (6, 7, 8, 9) if status == "found" else (0,) * 4
        body = f"""
            const fs::XfsRootFacts supplied_facts = fs::XfsRootFacts(1u64, 2u64, 3u64, 4u64, 5u64);
            const fs::XfsRootEntry supplied_entry = fs::XfsRootEntry(6u64, 7u64, 8u64, 9u64);
            const fs::XfsRootEntryReport report = fs::XfsRootEntryReport(
                fs::XfsRootEntryStatus::{status}, fs::XfsRootIssue::none, supplied_facts, supplied_entry);
            const fs::XfsRootEntryReport copy = report;
            const fs::XfsRootFacts facts = copy.facts();
            const fs::XfsRootEntry entry = copy.entry();
            if (size_of(fs::XfsRootEntry) != 32) {{
                return 0u64;
            }}
            if (size_of(fs::XfsRootEntryReport) != 88) {{
                return 0u64;
            }}
            if (field_count(fs::XfsRootEntryReport) != 0) {{
                return 0u64;
            }}
        """
        body += getters("facts", FACTS, facts) + getters("entry", ENTRY, entry) + "return 42u64;"
        yield Case(f"copied report layout/masking {status}", body, 42, imports=IMPORTS)


def rejections():
    prefix = "module test; import fs.xfs_root; auto test() -> u64 {"
    prefix += "const fs::XfsRootEntry entry = fs::XfsRootEntry(1u64, 2u64, 3u64, 4u64);"
    for label, body in (
        ("private name coordinates", "return entry._name_offset;"),
        ("private result field mutation", "entry._name_length = 0u64; return 0u64;"),
        ("closed enum", "return u64(fs::XfsRootEntryStatus::found);"),
        ("private common validator", "const array<u8, 1> data = {0u8};"
         "const fs::XfsRootReport result = fs::xr_validate_root(borrow_bytes(data), borrow_bytes(data), true);"
         "return 0u64;"),
        ("index exact signed type", "const array<u8, 1> data = {0u8};"
         "const fs::XfsRootEntryReport result = fs::entry_at_xfs_v5_512_root("
         "borrow_bytes(data), borrow_bytes(data), 0u64); return 0u64;"),
    ):
        yield Rejection(label, prefix + body + "}")


def main():
    args = root_model.parser(api=True).parse_args()
    identity = root_model.configure(args)
    compiler = args.compiler.resolve()
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    corpus = list(cases()) + list(report_cases())
    rejected = list(rejections())
    observer = root_model.ROOT / "tests/compiler/integer_signal.cpp"
    paths = [compiler, observer, *root_model.input_paths(__file__)]
    pins = {str(path): root_model.sha(path) for path in paths}
    directory = root_model.ARTIFACTS
    report = dict(status="running", compiler_identity=identity.record(), pins=pins,
                  native_cases=len(corpus), rejections=len(rejected), scope="indexed root entry library")
    environment = root_model.temporary_environment(directory)
    saved_environment = {name: os.environ.get(name) for name in ("TMPDIR", "TMP", "TEMP")}
    try:
        for name in saved_environment:
            os.environ[name] = environment[name]
        with tempfile.TemporaryDirectory(prefix="native-", dir=directory) as temporary:
            runner = NativeRunner(Path(temporary), compiler, 15)
            for start in range(0, len(corpus), 6):
                root_model.budget(24 << 20)
                runner.cases(corpus[start:start + 6])
                root_model.budget()
            for case in rejected:
                root_model.budget(24 << 20)
                runner.rejection(case)
                root_model.budget()
        require(pins == {str(path): root_model.sha(path) for path in paths}, "stable inputs required")
        identity.verify()
        report["status"] = "passed"
    except BaseException as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        for name, value in saved_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        report["allocated_bytes"] = root_model.allocated()
        root_model.write_checked_receipt(directory / "manifest.json", report, root_model.budget)
    print(f"PASS XFS root entry: {len(corpus)} native cases, {len(rejected)} rejections; "
          "full reference corpus, entry bytes, precedence, copies and masking", flush=True)


if __name__ == "__main__":
    main()

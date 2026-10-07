#!/usr/bin/env python3
"""Checked XFS header I/O/capacity consumer; no mount or complete image fixture."""

import argparse
import hashlib
from pathlib import Path
import tempfile

import xfs_geometry as geometry
from block_io import check_sector, make_sector
from unsigned_oracle import Case, NativeRunner, Rejection, require


IMPORTS = (
    "storage.block", "storage.sector", "storage.block_io", "storage.ram_sector",
    "fs.xfs_probe", "fs.xfs_geometry", "fs.xfs_sector",
)
MAXIMUM = (1 << 64) - 1


def check_report(data, count, io="success", status_override=None):
    expected = geometry.oracle(data if io == "success" else b"")
    if io != "success":
        status = "read_failed"
    elif expected.status != "header_geometry_consistent":
        status = "geometry_rejected"
    elif expected.facts[geometry.FACTS.index("claimed_data_sectors")] > count:
        status = "source_too_small"
    else:
        status = "header_fits_source"
    status = status_override or status
    text = f"""
        if (report.status() != fs::XfsSectorHeaderStatus::{status} ||
            report.io_status() != storage::SectorIoStatus::{io}) {{
            return 0u64;
        }}
        const fs::XfsGeometryReport parsed = report.geometry_or_empty();
        if (parsed.status() != fs::XfsGeometryStatus::{expected.status} ||
            parsed.issue() != fs::XfsGeometryIssue::{expected.issue}) {{
            return 0u64;
        }}
    """
    text += geometry.projections("parsed")
    text += f"if (p.status() != fs::XfsProbeStatus::{expected.probe_status}) {{ return 0u64; }}"
    for expression, value in zip(geometry.scalar_expressions(), expected.scalars()[3:]):
        text += f"if ({expression} != {value}u64) {{ return 0u64; }}\n"
    text += "const fs::XfsGeometryFacts safe_facts = report.facts();\n"
    safe_values = expected.facts if status == "header_fits_source" and io == "success" else (0,) * 24
    index = 0
    for group, (typename, fields) in geometry.GROUPS.items():
        text += f"const fs::{typename} safe_{group} = safe_facts.{group}();\n"
        for field in fields:
            text += f"if (safe_{group}.{field}() != {safe_values[index]}u64) {{ return 0u64; }}\n"
            index += 1
    return text


def native_case(label, data, count, io="success", writable=False, actual_geometry=False):
    body = make_sector("initial", data)
    body += """
        storage::RamSectorDevice device = storage::RamSectorDevice();
        if (device.write_sector(0, initial) != storage::SectorIoStatus::success) {
            return 0u64;
        }
    """
    if not writable:
        body += """
            if (device.make_read_only() != storage::SectorIoStatus::success) { return 0u64; }
        """
    if io == "success":
        body += "const storage::SectorReadResult read = device.read_sector(0);\n"
    else:
        # A failed report with a valid nonzero payload must never be parsed.
        body += f"const storage::SectorReadResult read = storage::SectorReadResult("
        body += f"storage::SectorIoStatus::{io}, initial);\n"
    source = "device.geometry()" if actual_geometry else f"storage::SectorGeometry({count}u64, {str(writable).lower()})"
    body += f"""
        const storage::SectorGeometry source = {source};
        const fs::XfsSectorHeaderReport original = fs::inspect_xfs_v5_512_sector(source, read);
        const fs::XfsSectorHeaderReport report = original;
    """
    body += check_sector("initial", data)
    body += "initial.write_byte(0, 0u8); initial.write_byte(511, 0u8);\n"
    if writable:
        body += """
            const storage::Sector512 zero = storage::Sector512();
            if (device.write_sector(0, zero) != storage::SectorIoStatus::success) { return 0u64; }
        """
    body += check_report(data, count, io) + "return 42u64;"
    return Case(label, body, 42, imports=IMPORTS)


def cases(real):
    required = int.from_bytes(real[8:16], "big") * int.from_bytes(real[4:8], "big") // 512
    require(required == 1048576, "preserved image capacity anchor")
    for writable in (False, True):
        yield native_case(f"actual one-sector backend, writable={writable}", real, 1,
                          writable=writable, actual_geometry=True)
        for count in (0, 1, required - 1, required, required + 1, 1 << 63, MAXIMUM):
            yield native_case(f"constructed source capacity {count}, writable={writable}", real, count,
                              writable=writable)
    for io in ("out_of_range", "read_only"):
        for count in (0, required, MAXIMUM):
            yield native_case(f"read failure before parsing/capacity {io}/{count}", real, count, io)
    # Cover each validator status/issue through the copied-sector boundary.
    # Non-512 lengths cannot be carried by a SectorReadResult; the existing span
    # geometry runner owns those cases. These variants are explicitly synthetic.
    selected = {}
    headers = geometry.header_cases(real, geometry.SEED, 0)
    for header in headers:
        if len(header.data) == 512:
            key = (header.expected.status, header.expected.issue, header.expected.probe_status)
            selected.setdefault(key, header)
    for header in selected.values():
        yield native_case("metadata gate: " + header.name, header.data, 0)
        if header.expected.status != "header_geometry_consistent":
            yield native_case("metadata before large capacity: " + header.name, header.data, MAXIMUM)
    large = [header for header in headers
             if header.name == "data representability edge 4503599627370495"]
    require(len(large) == 1 and large[0].expected.status == "header_geometry_consistent", "large header anchor")
    large_required = large[0].expected.facts[geometry.FACTS.index("claimed_data_sectors")]
    require(large_required == 36028797018963960, "large capacity anchor")
    for count in (large_required - 1, large_required, large_required + 1):
        yield native_case(f"large synthetic header capacity {count}", large[0].data, count)
    for offset in (0, 224, 227, 511):
        changed = bytearray(real)
        changed[offset] ^= 1
        yield native_case(f"unrepaired full-sector byte {offset}", bytes(changed), required)
    for index in (-(1 << 63), -1, 1, (1 << 63) - 1):
        body = "const storage::RamSectorDevice device = storage::RamSectorDevice();\n"
        body += f"const storage::SectorReadResult read = device.read_sector({index});\n"
        body += "const storage::SectorGeometry source = device.geometry();\n"
        body += "const fs::XfsSectorHeaderReport report = fs::inspect_xfs_v5_512_sector(source, read);\n"
        body += check_report(real, 1, "out_of_range") + "return 42u64;"
        yield Case(f"actual backend read error {index}", body, 42, imports=IMPORTS)


def report_cases(real, label):
    for status in ("read_failed", "geometry_rejected", "source_too_small", "header_fits_source"):
        for io in ("success", "out_of_range", "read_only"):
            body = geometry.array("bytes", real)
            body += """
                const fs::XfsGeometryReport header = fs::inspect_xfs_v5_512_geometry(borrow_bytes(bytes));
            """
            body += f"""
                const fs::XfsSectorHeaderReport report = fs::XfsSectorHeaderReport(
                    fs::XfsSectorHeaderStatus::{status}, storage::SectorIoStatus::{io}, header);
                if (size_of(fs::XfsSectorHeaderReport) != 352 ||
                    size_of(fs::XfsSectorHeaderStatus) != 8 || field_count(fs::XfsSectorHeaderReport) != 0) {{
                    return 0u64;
                }}
            """
            expected = b"" if status == "read_failed" else real
            body += check_report(expected, MAXIMUM, io, status_override=status) + "return 42u64;"
            yield Case(f"public report masking/layout {label}/{status}/{io}", body, 42, imports=IMPORTS)


def rejections():
    prefix = "module test; " + " ".join(f"import {module};" for module in IMPORTS)
    prefix += " auto test() -> u64 { const storage::SectorGeometry source = storage::SectorGeometry(1u64, false);"
    prefix += "const storage::Sector512 sector = storage::Sector512();"
    prefix += "const storage::SectorReadResult read = storage::SectorReadResult("
    prefix += "storage::SectorIoStatus::success, sector);"
    for body in (
        "const fs::XfsSectorHeaderReport report = fs::inspect_xfs_v5_512_sector(source, sector); return 0u64;",
        "const fs::XfsSectorHeaderReport report = fs::inspect_xfs_v5_512_sector(1u64, read); return 0u64;",
        "const fs::XfsSectorHeaderReport report = fs::inspect_xfs_v5_512_sector(source, read);"
        "const fs::XfsSectorHeaderStatus leaked = report._status; return 0u64;",
        "return u64(fs::XfsSectorHeaderStatus::header_fits_source);",
        "const fs::XfsGeometryReport leaked = fs::xs_empty_geometry(); return 0u64;",
    ):
        yield Rejection("XFS sector exact-type/privacy rejection", prefix + body + "}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    real = geometry.real_fixture()
    corpus = list(cases(real)) + list(report_cases(real, "valid header"))
    corpus += list(report_cases(geometry.change(real, compat=1), "nonzero diagnostic masks"))
    rejected = list(rejections())
    with tempfile.TemporaryDirectory(prefix="aurora-xfs-sector-") as temporary:
        runner = NativeRunner(Path(temporary), compiler, 15)
        for start in range(0, len(corpus), 2):
            runner.cases(corpus[start:start + 2])
        for case in rejected:
            runner.rejection(case)
    print(f"PASS XFS sector: {len(corpus)} native cases, {len(rejected)} rejections", flush=True)


if __name__ == "__main__":
    main()

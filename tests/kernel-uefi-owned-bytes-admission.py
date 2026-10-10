#!/usr/bin/env python3
"""Closed object-import boundary for the dedicated kernel owned-byte profile."""

from pathlib import Path
import subprocess
import sys

RUNTIME = frozenset(
    "__au_runtime_bytes_" + name for name in ("allocate", "at", "set", "drop", "borrow_length", "resize")
)
ENTRY = "__au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry"
CONSUMER = "__au_v_m1_18kernel_owned_bytes_n0__d13consume_bytes"
TRANSFER = "__au_v_m1_18kernel_owned_bytes_n0__d10pass_bytes"
DEFINITIONS = {
    ENTRY: "t",
    TRANSFER: "t",
    CONSUMER: "t",
    "__au_runtime_bytes_kernel_entry": "T",
    "aurora_reflect_size": "T",
    "aurora_reflect_field_count": "T",
}


def mangle(kind, module, scope, name):
    modules, scopes = module.split("."), scope.split("::") if scope else []
    return (
        "__au_"
        + kind
        + "_m"
        + str(len(modules))
        + "_"
        + "".join(str(len(part)) + part for part in modules)
        + "_n"
        + str(len(scopes))
        + "_"
        + "".join(str(len(part)) + part for part in scopes)
        + "_d"
        + str(len(name))
        + name
    )


# Exact declaration closure of the real RAM device and existing serializer.
# Short labels below are finite aliases, never accepted symbol-name patterns.
GENERATED = {"entry": ENTRY, "transfer": TRANSFER, "consumer": CONSUMER}
for name in (
    "sector_pattern_matches",
    "write_ram_pattern",
    "read_ram_pattern",
    "invalid_ram_read",
    "ram_snapshot_survives",
    "check_ram_sectors",
):
    GENERATED[name] = mangle("v", "kernel_owned_bytes", "", name)
for label, name in (("record", "ram_sector_record"), ("example_main", "main")):
    GENERATED[label] = mangle("v", "examples.ram_sector_record", "", name)
CLASSES = {
    ("std.binary", "std", "ByteReadResult"): ("status", "value_or"),
    ("std.binary_buffer", "std", "BinaryBuffer64"): (
        "size",
        "at",
        "read_u8",
        "write_u8",
        "write_le16",
        "write_be16",
        "write_le32",
        "write_be32",
        "write_le64",
        "write_be64",
    ),
    ("storage.sector", "storage", "RecordReadResult"): ("status", "record_or_zero"),
    ("storage.sector", "storage", "Sector512"): (
        "size",
        "read_byte",
        "write_byte",
        "read_record",
        "write_record",
    ),
    ("storage.block_io", "storage", "SectorGeometry"): ("sector_size_bytes", "sector_count", "can_write"),
    ("storage.block_io", "storage", "SectorReadResult"): ("status", "sector_or_zero"),
    ("storage.ram_sector", "storage", "RamSectorDevice"): (
        "status",
        "geometry",
        "read_sector",
        "write_sector",
        "make_read_only",
        "flush",
    ),
}
CLASSES.update({("std.bytes", "std", "Bytes" + str(n)): ("at", "set") for n in (2, 4, 8)})
CLASSES.update({("std.bytes", "std", "Encode" + str(n) + "Result"): ("status", "bytes_or_zero") for n in (16, 32)})
for (module, namespace, name), methods in CLASSES.items():
    GENERATED[name + ".new"] = mangle("k", module, namespace + "::" + name, name)
    for method in methods:
        GENERATED[name + "." + method] = mangle("m", module, namespace + "::" + name, method)
for bits in (16, 32, 64):
    for order in ("le", "be"):
        for prefix, module in (("read_", "std.binary"), ("encode_", "std.bytes"), ("decode_", "std.bytes")):
            name = prefix + order + str(bits)
            GENERATED[name] = mangle("v", module, "std", name)
REFLECTION = {"aurora_reflect_size", "aurora_reflect_field_count"} | {
    f"__au_reflect_s{index}_{name}" for index in range(1, 8) for name in ("size", "field_count")
}
DEFINITIONS.update({name: "t" for name in GENERATED.values()})
DEFINITIONS.update({name: "T" for name in REFLECTION})


# Exact permitted caller/callee sets, including emitted but dormant library
# methods. Changes require reviewing this finite graph, not widening a prefix.
CALLS = {
    "entry": (
        "transfer consumer record check_ram_sectors runtime.allocate runtime.at runtime.set runtime.drop "
        "runtime.borrow_length runtime.resize"
    ),
    "transfer": "runtime.set",
    "consumer": "runtime.at",
    "example_main": "record",
    "record": (
        "BinaryBuffer64.new RamSectorDevice.new Sector512.new BinaryBuffer64.write_be16 "
        "BinaryBuffer64.write_be32 BinaryBuffer64.write_le16 BinaryBuffer64.write_le64 BinaryBuffer64.at "
        "ByteReadResult.value_or RamSectorDevice.read_sector RamSectorDevice.write_sector RamSectorDevice.flush "
        "RamSectorDevice.status RamSectorDevice.geometry RecordReadResult.record_or_zero RecordReadResult.status "
        "Sector512.read_record Sector512.write_record SectorGeometry.sector_count "
        "SectorGeometry.sector_size_bytes SectorGeometry.can_write SectorReadResult.sector_or_zero "
        "SectorReadResult.status runtime.allocate runtime.drop read_be16 read_be32 read_le16 read_le64"
    ),
    "sector_pattern_matches": "ByteReadResult.status ByteReadResult.value_or Sector512.read_byte",
    "write_ram_pattern": "Sector512.new RamSectorDevice.write_sector Sector512.write_byte",
    "read_ram_pattern": (
        "RamSectorDevice.read_sector SectorReadResult.sector_or_zero SectorReadResult.status sector_pattern_matches"
    ),
    "invalid_ram_read": (
        "RamSectorDevice.read_sector SectorReadResult.sector_or_zero SectorReadResult.status sector_pattern_matches"
    ),
    "ram_snapshot_survives": (
        "RamSectorDevice.read_sector SectorReadResult.sector_or_zero SectorReadResult.status read_ram_pattern "
        "write_ram_pattern sector_pattern_matches"
    ),
    "check_ram_sectors": (
        "RamSectorDevice.new RamSectorDevice.make_read_only RamSectorDevice.flush RamSectorDevice.status "
        "RamSectorDevice.geometry SectorGeometry.sector_count SectorGeometry.sector_size_bytes "
        "SectorGeometry.can_write runtime.allocate runtime.drop runtime.set invalid_ram_read read_ram_pattern "
        "write_ram_pattern ram_snapshot_survives"
    ),
    "BinaryBuffer64.read_u8": "ByteReadResult.new",
    "RecordReadResult.record_or_zero": "BinaryBuffer64.new",
    "Sector512.read_byte": "ByteReadResult.new",
    "Sector512.read_record": "BinaryBuffer64.new RecordReadResult.new BinaryBuffer64.write_u8",
    "Sector512.write_record": "BinaryBuffer64.at",
    "SectorReadResult.sector_or_zero": "Sector512.new",
    "RamSectorDevice.new": "runtime.drop",
    "RamSectorDevice.geometry": "SectorGeometry.new RamSectorDevice.status",
    "RamSectorDevice.read_sector": (
        "Sector512.new SectorReadResult.new RamSectorDevice.status Sector512.write_byte runtime.at"
    ),
    "RamSectorDevice.write_sector": "ByteReadResult.value_or RamSectorDevice.status Sector512.read_byte runtime.set",
    "RamSectorDevice.make_read_only": "RamSectorDevice.status",
    "RamSectorDevice.flush": "RamSectorDevice.status",
}
# Packed outgoing records from the existing private value/owner ABI. All other
# methods use scalar registers and hidden synchronous receiver/result addresses.
ARGUMENT_BYTES = {
    "entry": 32,
    "transfer": 48,
    "consumer": 64,
    "record": 32,
    "example_main": 32,
    "check_ram_sectors": 32,
    "RamSectorDevice.new": 48,
    "RecordReadResult.new": 80,
    "SectorReadResult.new": 528,
    "Sector512.write_record": 80,
    "RamSectorDevice.write_sector": 528,
    "sector_pattern_matches": 528,
}
for bits in (16, 32, 64):
    byte_class = "Bytes" + str(bits // 8)
    result_class = "Encode" + str(bits) + "Result"
    if bits != 64:
        CALLS[result_class + ".bytes_or_zero"] = byte_class + ".new"
        ARGUMENT_BYTES[result_class + ".new"] = 16
    for order in ("le", "be"):
        suffix = order + str(bits)
        CALLS["read_" + suffix] = "ByteReadResult.new runtime.at"
        CALLS["encode_" + suffix] = byte_class + ".new " + byte_class + ".set"
        CALLS["decode_" + suffix] = byte_class + ".at"
        CALLS["BinaryBuffer64.write_" + suffix] = "encode_" + suffix + " " + byte_class + ".at"
        if bits != 64:
            CALLS["encode_" + suffix] += " " + result_class + ".new"
            CALLS["BinaryBuffer64.write_" + suffix] += " " + result_class + ".status " + result_class + ".bytes_or_zero"
        ARGUMENT_BYTES["read_" + suffix] = 64
        ARGUMENT_BYTES["encode_" + suffix] = ARGUMENT_BYTES["decode_" + suffix] = 16
CALLS = {
    symbol: frozenset(
        "__au_runtime_bytes_" + callee.removeprefix("runtime.") if callee.startswith("runtime.") else GENERATED[callee]
        for callee in CALLS.get(label, "").split()
    )
    for label, symbol in GENERATED.items()
}
ARGUMENT_BYTES = {GENERATED[name]: size for name, size in ARGUMENT_BYTES.items()}


def validate_symbols(text):
    imports = set()
    definitions = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] == "U":
            if fields[1] in imports:
                raise ValueError("Duplicate undefined symbol")
            imports.add(fields[1])
        elif len(fields) == 3 and len(fields[1]) == 1:
            int(fields[0], 16)
            if fields[2] in definitions:
                raise ValueError("Duplicate defined symbol")
            definitions[fields[2]] = fields[1]
        else:
            raise ValueError("Unrecognized object symbol row")
    unsupported = imports - RUNTIME
    if unsupported:
        raise ValueError("Unsupported kernel owned-byte runtime import: " + ", ".join(sorted(unsupported)))
    if imports != RUNTIME:
        raise ValueError("Dedicated owned-byte profile must exercise all six admitted runtime operations")
    if definitions != DEFINITIONS:
        raise ValueError("Unexpected dedicated owned-byte graph definitions or visibility")
    return dict(imports=sorted(imports), definitions=definitions)


def self_test():
    rows = ["U " + name for name in sorted(RUNTIME)]
    rows += ["0 " + kind + " " + name for name, kind in DEFINITIONS.items()]
    text = "\n".join(rows)
    validate_symbols(text)
    rejected = 0
    mutants = ["\n".join(rows[:i] + rows[i + 1 :]) for i in range(len(rows))]
    mutants += [text + "\nU " + name for name in ("__au_runtime_bytes_unknown", "malloc", "unknown_helper")]
    mutants += [
        text + "\n0 T " + name
        for name in (*sorted(RUNTIME), "__au_runtime_bytes_resize", "aurora_kernel_value", "malloc")
    ]
    mutants += [text.replace("0 t " + name, "0 T " + name) for name in GENERATED.values()]
    mutants += [text + "\n0 t " + mangle("m", "storage.ram_sector", "storage::RamSectorDevice", "unknown")]
    mutants += [text + "\n0 T __au_reflect_s8_size"]
    mutants += [text + "\n" + rows[0], text + "\n" + rows[-1], text + "\nmalformed"]
    for candidate in mutants:
        try:
            validate_symbols(candidate)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Unsupported graph/import mutation accepted")
    print(f"PASS: owned-byte object admission, 1 positive and {rejected} negative controls")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 2:
        symbols = subprocess.check_output(["nm", "-a", str(Path(sys.argv[1]))], text=True)
        validate_symbols(symbols)
        print("PASS: dedicated owned-byte object has only six admitted runtime imports")
    else:
        raise SystemExit("Expected language.o or --self-test")

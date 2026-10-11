#!/usr/bin/env python3
"""Closed object-import boundary for the dedicated kernel owned-byte profile."""

from pathlib import Path
import importlib.util
import sys

RUNTIME = frozenset(
    "__au_runtime_bytes_" + name for name in ("allocate", "at", "set", "drop", "borrow_length", "resize")
)
ENTRY = "__au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry"
CONSUMER = "__au_v_m1_18kernel_owned_bytes_n0__d13consume_bytes"
TRANSFER = "__au_v_m1_18kernel_owned_bytes_n0__d10pass_bytes"
PRODUCER = "__au_v_m1_18kernel_owned_bytes_n0__d14produce_record"
DEFINITIONS = {
    ENTRY: "t",
    TRANSFER: "t",
    CONSUMER: "t",
    "__au_runtime_bytes_kernel_entry": "T",
    "__au_runtime_bytes_kernel_produce": "T",
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


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("owned_object_stack", ROOT / "scripts/kernel_stack.py")
stack = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stack
spec.loader.exec_module(stack)
MODULES = frozenset(
    (
        "kernel_owned_bytes",
        "examples.ram_sector_record",
        "std.binary",
        "std.binary_buffer",
        "std.bytes",
        "storage.sector",
        "storage.block_io",
        "storage.ram_sector",
    )
)
# Only actual entry/workload boundaries are mandatory. Imported dormant methods
# may be pruned; emitted membership is bound to compiler facts by stack admission.
GENERATED = {"entry": ENTRY, "transfer": TRANSFER, "consumer": CONSUMER, "producer": PRODUCER}
GENERATED["ProducedRecord.new"] = mangle("k", "kernel_owned_bytes", "ProducedRecord", "ProducedRecord")
GENERATED["record"] = mangle("v", "examples.ram_sector_record", "", "ram_sector_record")
GENERATED["check_ram_sectors"] = mangle("v", "kernel_owned_bytes", "", "check_ram_sectors")
GENERATED["RamSectorDevice.new"] = mangle("k", "storage.ram_sector", "storage::RamSectorDevice", "RamSectorDevice")
GENERATED["RamSectorDevice.read_sector"] = mangle("m", "storage.ram_sector", "storage::RamSectorDevice", "read_sector")
GENERATED["RamSectorDevice.write_sector"] = mangle(
    "m", "storage.ram_sector", "storage::RamSectorDevice", "write_sector"
)
GENERATED["RamSectorDevice.make_read_only"] = mangle(
    "m", "storage.ram_sector", "storage::RamSectorDevice", "make_read_only"
)
GENERATED["RamSectorDevice.flush"] = mangle("m", "storage.ram_sector", "storage::RamSectorDevice", "flush")
GENERATED["Sector512.read_record"] = mangle("m", "storage.sector", "storage::Sector512", "read_record")
GENERATED["Sector512.write_record"] = mangle("m", "storage.sector", "storage::Sector512", "write_record")
GENERATED["SectorReadResult.sector_or_zero"] = mangle(
    "m", "storage.block_io", "storage::SectorReadResult", "sector_or_zero"
)
GENERATED["read_be32"] = mangle("v", "std.binary", "std", "read_be32")
GENERATED["read_le64"] = mangle("v", "std.binary", "std", "read_le64")
GENERATED["encode_be32"] = mangle("v", "std.bytes", "std", "encode_be32")
GENERATED["encode_le64"] = mangle("v", "std.bytes", "std", "encode_le64")
DEFINITIONS.update({name: "t" for name in GENERATED.values()})


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
    reflection = stack.reflection_inventory(definitions)
    if (
        not DEFINITIONS.items() <= definitions.items()
        or any(
            kind != ("T" if name in reflection or name in DEFINITIONS and DEFINITIONS[name] == "T" else "t")
            for name, kind in definitions.items()
        )
        or any(
            name not in DEFINITIONS and name not in reflection and stack.aurora_module(name) not in MODULES
            for name in definitions
        )
    ):
        raise ValueError("Unexpected dedicated owned-byte module, entry or visibility")
    return dict(imports=sorted(imports), definitions=definitions)

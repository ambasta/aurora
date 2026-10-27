#!/usr/bin/env python3
"""Emit UEFI payload declarations and guest-oracle metadata from the linked payload."""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel_elf import Elf  # noqa: E402
from kernel_layout import LAYOUT  # noqa: E402


def assembly_path(path: Path) -> str:
    """Quote a resolved filename for GNU assembler without directive injection."""
    return (
        '"'
        + "".join(
            chr(byte) if 32 <= byte < 127 and byte not in (34, 92) else f"\\{byte:03o}"
            for byte in os.fsencode(path.resolve())
        )
        + '"'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True, help="profile artifact directory")
    build = parser.parse_args().build_dir.resolve()
    symbols = {symbol.name: symbol.address for symbol in Elf(build / "payload.elf").symbols if symbol.name}
    payload = build / "payload.bin"
    (build / "uefi-payload.hpp").write_text(
        "namespace aurora::uefi {\n"
        + f"inline constexpr unsigned long long payload_size={payload.stat().st_size};\n"
        + "".join(
            f"inline constexpr unsigned long long {name}={symbols['__' + name]};\n"
            for name in ["payload_text_end", "payload_read_end", "payload_memory_end"]
        )
        + "}\n"
    )
    # Guest oracles locate the payload text copy and the selected fault probes.
    for kind, probes in (
        ("bar", (("bar-write", "uefi_bar_write_probe"), ("bar-revoked", "uefi_bar_revoked_probe"))),
        ("ivrs", (("ivrs-write", "uefi_ivrs_write_probe"), ("ivrs-revoked", "uefi_ivrs_revoked_probe"))),
    ):
        faults = {mode: symbols[name] for mode, name in probes if name in symbols}
        (build / f"{kind}-metadata.json").write_text(
            json.dumps(
                dict(offset=LAYOUT.kernel_payload_offset, bytes=symbols["__payload_text_end"], fault_offsets=faults),
                indent=2,
            )
            + "\n"
        )
    if "uefi_service_drain_begin" in symbols:
        (build / "service-timer-metadata.json").write_text(
            json.dumps(
                dict(
                    drain_begin=symbols["uefi_service_drain_begin"],
                    drain_end=symbols["uefi_service_drain_end"],
                    text_end=symbols["__payload_text_end"],
                    forged_pc=symbols.get("uefi_service_forged_pc", 0),
                )
            )
        )
    (build / "embed.S").write_text(
        '.section .rodata.payload,"a"\n.global uefi_embedded_payload\nuefi_embedded_payload:\n.incbin '
        + assembly_path(payload)
        + '\n.global uefi_embedded_payload_end\nuefi_embedded_payload_end:\n.section .note.GNU-stack,"",@progbits\n'
    )


if __name__ == "__main__":
    main()

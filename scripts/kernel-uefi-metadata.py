#!/usr/bin/env python3
"""Emit UEFI payload declarations and metadata from the independently linked image.

Every profile emits uefi-payload.hpp, embed.S, bar-metadata.json and
ivrs-metadata.json. Existing specialized profile sidecars retain their contracts.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument(
        "--build-dir", type=Path, default=ROOT / "build/uefi", help="artifact directory (default: build/uefi)"
    )
    build = parser.parse_args().build_dir.resolve()
    symbols = {}
    for line in subprocess.check_output(["nm", "-a", str(build / "payload.elf")], text=True).splitlines():
        words = line.split()
        if len(words) == 3:
            symbols[words[2]] = int(words[0], 16)
    if symbols["uefi_payload_entry"] != 0:
        raise SystemExit("Entry must start payload")
    if subprocess.check_output(["nm", "-u", str(build / "payload.elf")], text=True).strip():
        raise SystemExit("Unresolved payload reference")
    p = build / "payload.bin"
    console_metadata = build / "console-poll-metadata.json"
    if "uefi_console_poll_begin" in symbols:
        begin, end = symbols["uefi_console_poll_begin"], symbols["uefi_console_poll_end"]
        if not 0 < begin < end < symbols["__payload_text_end"] or p.read_bytes()[begin:end] != bytes.fromhex("fbf4fa"):
            raise SystemExit("Invalid exact console wait site")
        if "uefi_runtime_enter" in symbols or "aurora_kernel_budget_tick" in symbols:
            raise SystemExit("Console must not contain user runtime or service budget fixtures")
        console_metadata.write_text(
            json.dumps(
                dict(
                    wait_begin=begin,
                    wait_end=end,
                    text_end=symbols["__payload_text_end"],
                    frame_bytes=176,
                    interrupt=symbols["uefi_console_interrupt"],
                    dispatch=symbols["uefi_console_interrupt_dispatch"],
                    polling_count=1250000,
                    uart_irq=0,
                ),
                indent=2,
            )
            + "\n"
        )
    else:
        console_metadata.unlink(missing_ok=True)
    program_metadata = build / "program-poll-metadata.json"
    if "uefi_program_poll_begin" in symbols:
        begin, end = symbols["uefi_program_poll_begin"], symbols["uefi_program_poll_end"]
        if not 0 < begin < end < symbols["__payload_text_end"] or p.read_bytes()[begin:end] != bytes.fromhex("fbf4fa"):
            raise SystemExit("Invalid exact program console wait site")
        if "uefi_runtime_enter" not in symbols or "aurora_kernel_budget_tick" not in symbols:
            raise SystemExit("Program console requires protected runtime and bounded timer policy")
        program_metadata.write_text(
            json.dumps(
                dict(
                    wait_begin=begin,
                    wait_end=end,
                    text_end=symbols["__payload_text_end"],
                    frame_bytes=176,
                    polling_count=1250000,
                    uart_irq=0,
                    domains=2,
                ),
                indent=2,
            )
            + "\n"
        )
    else:
        program_metadata.unlink(missing_ok=True)
    (build / "uefi-payload.hpp").write_text(
        "namespace aurora::uefi {\n"
        + f"inline constexpr unsigned long long payload_size={p.stat().st_size};\n"
        + "".join(
            f"inline constexpr unsigned long long {name}={symbols['__' + name]};\n"
            for name in ["payload_text_end", "payload_read_end", "payload_memory_end"]
        )
        + "}\n"
    )
    bar_faults = {}
    for mode, name, opcode in [
        ("bar-write", "uefi_bar_write_probe", bytes.fromhex("c70000000000")),
        ("bar-revoked", "uefi_bar_revoked_probe", bytes.fromhex("8b00")),
    ]:
        if name in symbols:
            at = symbols[name]
            if not 0 < at < symbols["__payload_text_end"] or p.read_bytes()[at : at + len(opcode)] != opcode:
                raise SystemExit("Invalid exact BAR fault site")
            bar_faults[mode] = at
    (build / "bar-metadata.json").write_text(
        json.dumps(dict(offset=0x22000, bytes=symbols["__payload_text_end"], fault_offsets=bar_faults), indent=2) + "\n"
    )
    ivrs_faults = {}
    for mode, name, opcode in [
        ("ivrs-write", "uefi_ivrs_write_probe", bytes.fromhex("48c70000000000")),
        ("ivrs-revoked", "uefi_ivrs_revoked_probe", bytes.fromhex("488b00")),
    ]:
        if name in symbols:
            address = symbols[name]
            if (
                not 0 < address < symbols["__payload_text_end"]
                or p.read_bytes()[address : address + len(opcode)] != opcode
            ):
                raise ValueError("Wrong IVRS probe opcode")
            ivrs_faults[mode] = address
    (build / "ivrs-metadata.json").write_text(
        json.dumps(dict(offset=0x22000, bytes=symbols["__payload_text_end"], fault_offsets=ivrs_faults), indent=2)
        + "\n"
    )
    if "uefi_service_drain_begin" in symbols:
        drain_begin = symbols["uefi_service_drain_begin"]
        drain_end = symbols["uefi_service_drain_end"]
        if not 0 <= drain_begin < drain_end < symbols["__payload_text_end"] or p.read_bytes()[
            drain_begin:drain_end
        ] != bytes.fromhex("fb9090fa"):
            raise SystemExit("Invalid exact drain interval")
        forged = symbols.get("uefi_service_forged_pc", 0)
        if forged and (
            not 2 <= forged < symbols["__payload_text_end"]
            or p.read_bytes()[forged - 2 : forged] != bytes.fromhex("cd40")
        ):
            raise SystemExit("Invalid forged interrupt probe")
        (build / "service-timer-metadata.json").write_text(
            json.dumps(
                dict(
                    drain_begin=drain_begin,
                    drain_end=drain_end,
                    text_end=symbols["__payload_text_end"],
                    forged_pc=symbols.get("uefi_service_forged_pc", 0),
                )
            )
        )
    (build / "embed.S").write_text(
        '.section .rodata.payload,"a"\n.global uefi_embedded_payload\nuefi_embedded_payload:\n.incbin '
        + assembly_path(p)
        + '\n.global uefi_embedded_payload_end\nuefi_embedded_payload_end:\n.section .note.GNU-stack,"",@progbits\n'
    )


if __name__ == "__main__":
    main()

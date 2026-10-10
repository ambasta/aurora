#!/usr/bin/env python3
"""Build the two pointer-free staged IPC user programs."""

from pathlib import Path
import argparse, json, struct, subprocess

ROOT = Path(__file__).resolve().parent.parent
BASE = 0x10000000000


def need(value, message):
    if not value:
        raise ValueError(message)


import importlib.util

_spec = importlib.util.spec_from_file_location("uefi_image_builder", ROOT / "scripts/kernel-uefi-user-images.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


def verify(
    data, blob, base, symbols, probe_opcode=b"\x0f\x0b", *, dispatcher=False, copied_snapshot=False, copied_note=False
):
    result = _base.verify(
        data,
        blob,
        base,
        symbols,
        image_count=3 if dispatcher else 2,
        copied_snapshot=copied_snapshot,
        copied_note=copied_note,
    )
    need(result["probe_offset"] == 0, "IPC has no address literal authority")
    probe = result["probe_pc"]
    if probe:
        need(
            base <= probe <= base + len(blob) - 2
            and blob[probe - base : probe - base + len(probe_opcode)] == probe_opcode,
            "IPC exact hostile probe",
        )
        need(
            probe
            not in [result[k] for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")],
            "IPC probe aliases accepted site",
        )
    return result


def service_metadata(meta, blob, symbols, function_size, compiled="aurora_user_main"):
    base = meta["entry"]
    begin = symbols.get(compiled, 0)
    need(type(function_size) is int and function_size > 0, "Nonempty compiled function")
    end = begin + function_size
    need(
        base <= meta["return_pc"] < begin < end <= base + len(blob) and end <= meta["bounds_pc"],
        "Bounded compiled function",
    )
    probe_begin = symbols.get("aurora_budget_context_begin", 0)
    probe_end = symbols.get("aurora_budget_context_end", 0)
    need(
        (probe_begin == probe_end == 0) or base <= probe_begin < probe_end <= meta["return_pc"],
        "Bounded register probe",
    )
    if probe_begin:
        need(
            blob[probe_begin - base : probe_end - base] == b"\x48\xff\x0c\x24\x75\xfa",
            "Exact register-preservation loop",
        )
    return dict(meta, compiled_begin=begin, compiled_end=end, context_begin=probe_begin, context_end=probe_end)


def build(
    compiler,
    out,
    mode,
    service_budget=False,
    dispatcher=False,
    user_budget=False,
    program_console=False,
    snapshot=False,
):
    need(
        not snapshot or not any((service_budget, dispatcher, user_budget, program_console)),
        "Snapshot requires its exclusive IPC composition",
    )
    need(not snapshot or mode in ("normal", "owner", "reply-reserved", "reply-byte"), "Unsupported snapshot mode")
    need(mode not in ("reply-reserved", "reply-byte") or snapshot, "Snapshot reply probe requires snapshot")
    need(
        not program_console or service_budget and user_budget and not dispatcher,
        "Protected console requires its exact two-domain timer composition",
    )
    need(
        not program_console or mode in ("normal", "owner", "ordinal", "unknown", "transaction"),
        "Unsupported protected console mode",
    )
    need(not user_budget or dispatcher or program_console, "User budgets require dispatcher profile")
    need(not dispatcher or service_budget, "Dispatcher requires service timer profile")
    (out / "objects").mkdir(parents=True, exist_ok=True)
    run = lambda args: subprocess.run([str(x) for x in args], cwd=ROOT, check=True)
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    for index, name in enumerate(("clean", "bounds", "peer") if dispatcher else ("clean", "bounds")):
        prefix = out / f"user-{name}"
        obj = out / "objects" / f"user-{name}.o"
        fixture = "budget-service" if service_budget and index == 1 else "ipc-client" if index == 0 else "ipc-service"
        if program_console:
            fixture = "program-upper-client" if index == 0 else "program-stream-service"
        if dispatcher:
            fixture = "dispatch-service" if index == 1 else "dispatch-client-a" if index == 0 else "dispatch-client-b"
        if user_budget and not program_console and index != 1:
            fixture = "user-budget-client-a" if index == 0 else "user-budget-client-b"
        if snapshot:
            fixture = "snapshot-client" if index == 0 else "snapshot-service"
        run(
            [
                compiler,
                ROOT / f"tests/kernel-programs/{fixture}.au",
                "--module-root",
                ROOT / "library",
                *(["--module-root", ROOT / "kernel/policies"] if snapshot or program_console else []),
                "-o",
                prefix.with_suffix(".s"),
            ]
        )
        adapter = out / "objects" / f"user-{name}-entry.o"
        hostile = (index == 0 and mode in ("owner", "stale", "version", "phase", "site", "unknown", "ordinal")) or (
            index == 1 and mode in ("transaction", "mmio", "softint", "fpu", "context")
        )
        if dispatcher and index == 2 and mode == "peer-code":
            hostile = True
        if user_budget and mode == "context":
            hostile = index == 0
        flags = ["--defsym", f"IPC_{mode.upper().replace(chr(45), chr(95))}=1"] if hostile else []
        if user_budget and mode == "context" and index == 0:
            flags += ["--defsym", "IPC_CLIENT_CONTEXT=1"]
        if (snapshot or program_console) and index == 1:
            flags += ["--defsym", "SNAPSHOT_SERVICE=1" if snapshot else "PROGRAM_NOTE_SERVICE=1"]
            if mode in ("reply-reserved", "reply-byte"):
                flags += ["--defsym", f"SNAPSHOT_{mode.upper().replace(chr(45), chr(95))}=1"]
            run(
                [
                    "as",
                    "--64",
                    "-L",
                    *flags,
                    prefix.with_suffix(".s"),
                    ROOT / "kernel/uefi/ipc-user-entry.S",
                    "-o",
                    obj,
                ]
            )
            inputs = [obj]
        else:
            run(["as", "--64", "-L", prefix.with_suffix(".s"), "-o", obj])
            run(["as", "--64", *flags, ROOT / "kernel/uefi/ipc-user-entry.S", "-o", adapter])
            inputs = [adapter, obj]
        elf = prefix.with_suffix(".elf")
        binary = prefix.with_suffix(".bin")
        base = BASE + index * 4096
        run(
            [
                "ld",
                "-nostdlib",
                "--discard-none",
                "-T",
                ROOT / "kernel/program.ld",
                "--defsym",
                f"USER_BASE={base}",
                "-z",
                "max-page-size=0x1000",
                *inputs,
                "-o",
                elf,
            ]
        )
        run(["objcopy", "-O", "binary", elf, binary])
        need(
            "There are no relocations" in subprocess.check_output(["readelf", "-rW", elf], text=True),
            "Unresolved image relocations",
        )
        symbols = {
            line.split()[2]: int(line.split()[0], 16)
            for line in subprocess.check_output(["nm", "-a", elf], text=True).splitlines()
            if len(line.split()) == 3
        }
        blob = binary.read_bytes()
        opcode = {"mmio": b"\x8b\x00", "softint": b"\xcd\x40", "fpu": b"\xd9\xd0", "peer-code": b"\x49\x8b\x02"}.get(
            mode, b"\x0f\x0b"
        )
        meta = verify(
            elf.read_bytes(),
            blob,
            base,
            symbols,
            opcode,
            dispatcher=dispatcher,
            copied_snapshot=snapshot and index == 1,
            copied_note=program_console and index == 1,
        )
        if service_budget:
            compiled = (
                "__au_v_m1_22program_stream_service_n0__d16aurora_user_main"
                if program_console and index == 1
                else "aurora_user_main"
            )
            functions = [
                line.split()
                for line in subprocess.check_output(["readelf", "-sW", elf], text=True).splitlines()
                if line.split() and line.split()[-1] == compiled
            ]
            need(len(functions) == 1 and functions[0][3] == "FUNC", "Exact compiled function symbol")
            need(int(functions[0][1], 16) == symbols[compiled], "Consistent function entry")
            meta = service_metadata(meta, blob, symbols, int(functions[0][2]), compiled)
        records[name] = meta
        header.append(
            f"inline constexpr std::array<std::byte,{len(blob)}> {name}_bytes = {{"
            + ",".join(f"std::byte{{{value}}}" for value in blob)
            + "};"
        )
        for key, value in meta.items():
            header.append(f"inline constexpr unsigned long long {name}_{key}={value}ULL;")
    header.append("}")
    (out / "uefi-user-images.hpp").write_text("\n".join(header) + "\n")
    (out / "user-images.json").write_text(json.dumps(records, indent=2) + "\n")
    print("PASS: " + str(len(records)) + " independently compiled staged IPC RX images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--output", default="build/uefi")
    parser.add_argument(
        "--mode",
        default="normal",
        choices=[
            "normal",
            "owner",
            "stale",
            "version",
            "phase",
            "transaction",
            "site",
            "unknown",
            "mmio",
            "softint",
            "fpu",
            "context",
            "peer-code",
            "ordinal",
            "reply-reserved",
            "reply-byte",
        ],
    )
    parser.add_argument("--service-budget", action="store_true")
    parser.add_argument("--dispatcher", action="store_true")
    parser.add_argument("--user-budget", action="store_true")
    parser.add_argument("--program-console", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()
    build(
        Path(args.compiler).resolve(),
        Path(args.output).resolve(),
        args.mode,
        args.service_budget,
        args.dispatcher,
        args.user_budget,
        args.program_console,
        args.snapshot,
    )

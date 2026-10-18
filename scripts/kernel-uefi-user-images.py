#!/usr/bin/env python3
"""Validate linked high-VA user images and emit their bounded metadata/header."""

from pathlib import Path
import argparse, json, struct, subprocess, sys

ROOT = Path(__file__).resolve().parent.parent
BASE = 0x10000000000


def need(value, message):
    if not value:
        raise ValueError(message)


def verify(
    data,
    blob,
    base,
    symbols,
    *,
    image_count=2,
    max_pages=1,
    copied_snapshot=False,
    copied_note=False,
    note_entry=None,
    call_entry=None,
):
    need(len(data) >= 64, "Truncated ELF header")
    need(type(image_count) is int and image_count in (2, 3), "Unknown bounded image profile")
    need(type(max_pages) is int and 1 <= max_pages <= 3, "Unknown bounded page allowance")
    need(base in tuple(BASE + index * 16384 for index in range(image_count)), "Foreign virtual image layout")
    need(data[:7] == b"\x7fELF\x02\x01\x01", "ELF64 little-endian required")
    kind, machine = struct.unpack_from("<HH", data, 16)
    entry, phoff = struct.unpack_from("<QQ", data, 24)
    phsize, phcount = struct.unpack_from("<HH", data, 54)
    need(
        kind == 2 and machine == 62 and entry == base and phsize == 56 and phcount == 1,
        "Exact static image entry/segments",
    )
    need(phoff + 56 <= len(data), "Truncated segment")
    kind, flags, offset, virtual, physical, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", data, phoff)
    need(
        kind == 1
        and flags == 5
        and virtual == physical == base
        and filesz == memsz == len(blob)
        and 4 <= memsz <= max_pages * 4096,
        "Bounded RX image",
    )
    need(offset + filesz <= len(data) and data[offset : offset + filesz] == blob, "Exact installed image bytes")
    need(not (copied_snapshot and copied_note), "Distinct copied service records")
    compiled = "__au_v_m1_16snapshot_service_n0__d16aurora_user_main" if copied_snapshot else "aurora_user_main"
    if copied_note:
        need(type(note_entry) is str and bool(note_entry), "Missing compiler-produced note entry")
        compiled = note_entry
    need(
        not (copied_snapshot or copied_note) or base == BASE + 16384 and image_count == 2,
        "Exact copied snapshot service slot",
    )
    if call_entry is not None:
        need(
            not copied_snapshot and not copied_note and base == BASE and image_count == 2,
            "Exact singleton call client slot",
        )
        need(type(call_entry) is str and bool(call_entry), "Missing compiler-produced call entry")
        compiled = call_entry
    need(
        symbols.get("aurora_program_entry") == base and base <= symbols.get(compiled, 0) < base + len(blob),
        "Compiled entry",
    )
    names = [
        "aurora_program_return_pc",
        ".Laurora_bounds_trap",
        ".Laurora_overflow_trap",
        ".Laurora_division_zero_trap",
        ".Laurora_shift_count_trap",
    ]
    sites = [symbols.get(name, 0) for name in names]
    need(all(sites[:3]), "Required return/bounds/overflow metadata")
    present = [pc for pc in sites if pc]
    need(len(set(present)) == len(present), "Distinct exact sites")
    for pc in present:
        need(
            base <= pc <= base + len(blob) - 2 and blob[pc - base : pc - base + 2] == b"\x0f\x0b",
            "Exact UD2 within image",
        )
    ret = sites[0] - base
    need(ret >= 2 and blob[ret - 2 : ret] == b"\xcd\x81", "Typed return instruction")
    patch = symbols.get("aurora_kernel_probe_target", 0)
    if patch:
        need(
            base + 2 <= patch <= base + len(blob) - 8 and blob[patch - base : patch - base + 8] == bytes(8),
            "Trusted test literal",
        )
        need(
            all(not (patch < pc + 2 and pc < patch + 8) for pc in present), "Test literal aliases instruction authority"
        )
    return dict(
        entry=base,
        size=len(blob),
        return_pc=sites[0],
        bounds_pc=sites[1],
        overflow_pc=sites[2],
        division_zero_pc=sites[3],
        shift_count_pc=sites[4],
        probe_offset=patch - base if patch else 0,
        probe_pc=symbols.get("aurora_probe_pc", 0),
    )


def multipage_wrapper(code, symbols, base, fault):
    import kernel_stack as stack

    end = base + (68 if fault else 63)
    need(symbols["aurora_program_entry"] == base and symbols["bad_entry"] == end - 2, "Exact multipage entry extent")
    targets = {symbols["bad_entry"]: "bad_entry", symbols["aurora_user_main"]: "aurora_user_main"}
    actual = [
        (row.op, targets.get(stack.target_of(row)) if row.op in ("call", "jne") else row.args)
        for address, row in sorted(code.items())
        if base <= address < end
    ]
    expected = [
        ("or", f"%{reg},%rax")
        for reg in ("rbx", "rcx", "rdx", "rbp", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15")
    ]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry")]
    if fault:
        expected += [("mov", "$0x1,%edi")]
    expected += [("call", "aurora_user_main"), ("int", "$0x81"), ("ud2", ""), ("ud2", "")]
    need(actual == expected, "Exact multipage entry wrapper")
    need(symbols["aurora_program_return_pc"] == end - 4, "Exact multipage return site")
    return end


def multipage_evidence(functions, symbols, base):
    import kernel_stack as stack

    result = stack.calculate(functions, "aurora_user_main")
    # Conservative extra return-address reserve for the fixed, frameless wrapper.
    result["peak_with_wrapper"] = result["peak"] + 8
    need(result["peak_with_wrapper"] <= stack.STACK_CAP, "Multipage user stack reserve")
    late = "__au_m_m2_3std4utf8_n2_3std16Utf8EncodeResult_d7byte_or"
    need(
        late in result["closure"] and symbols.get(late, 0) > base + 8192,
        "Real multipage byte comparison must call third-page code",
    )
    need(symbols.get(".Laurora_bounds_trap", 0) > base + 8192, "Multipage bounds trap must execute on third page")
    return result


def multipage_stack(prefix, base, fault):
    sys.path.insert(0, str(ROOT / "scripts"))
    import kernel_stack as stack

    user = stack.Elf(prefix.with_suffix(".elf"))
    need(
        not any(symbol.name and not symbol.section for symbol in user.symbols), "Multipage image has undefined imports"
    )
    symbols = {symbol.name: symbol.address for symbol in user.symbols}
    code, _ = stack.disassemble(user.path)
    facts = json.loads(prefix.with_suffix(".stack.json").read_text())["functions"]
    need(set(user.functions) == set(facts), "Closed multipage function inventory")
    starts = {symbol.address: name for name, symbol in user.functions.items()}
    functions = stack.aurora_stack_functions(prefix.with_suffix(".stack.json"), user.functions, code, starts, facts)
    end = multipage_wrapper(code, symbols, base, fault)
    need(min(starts) == end, "Multipage wrapper directly precedes generated functions")
    # Also reject cycles in generated functions outside the executed root closure.
    for name in functions:
        stack.calculate(functions, name)
    return multipage_evidence(functions, symbols, base)


def emit_metadata(out, mode):
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    for index, name in enumerate(("clean", "bounds")):
        prefix = out / f"user-{name}"
        elf = prefix.with_suffix(".elf")
        binary = prefix.with_suffix(".bin")
        base = BASE + index * 16384
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
        meta = verify(elf.read_bytes(), blob, base, symbols, max_pages=3 if mode == "multipage" else 1)
        if mode == "multipage":
            need(8192 < len(blob) <= 12288, "Real three-page multipage consumer")
            evidence = multipage_stack(prefix, base, name == "bounds")
            print(
                f"PASS: multipage {name} user stack {evidence['peak_with_wrapper']}/15360 bytes; "
                "third-page call and trap"
            )
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
    print("PASS: two independently linked high-VA RX user images")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/uefi")
    parser.add_argument(
        "--mode",
        default="normal",
        choices=[
            "normal",
            "span",
            "multipage",
            "code",
            "stack",
            "window",
            "kernel",
            "write",
            "nx",
            "return",
            "unknown",
            "syscall",
            "sysenter",
        ],
    )
    args = parser.parse_args()
    emit_metadata(Path(args.output).resolve(), args.mode)

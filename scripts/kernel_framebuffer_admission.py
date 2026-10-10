#!/usr/bin/env python3
"""Automatic graphics image/stack checks, separate from independent qualification."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
MODES = ("framebuffer", "framebuffer-record", "framebuffer-permissions", "framebuffer-stale")
ENTRY = "__au_v_m1_22kernel_display_service_n0__d15display_service"
BRIDGE = "__au_runtime_display_entry"


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("framebuffer_common", ROOT / "scripts/kernel_program_console_admission.py")
console = load("framebuffer_decoder_controls", ROOT / "scripts/kernel_console_service_admission.py")
console.ENTRY, console.BRIDGE = ENTRY, BRIDGE


def configure_paths(build_dir, source_root=None):
    global ROOT, BUILD
    common.configure_paths(build_dir, source_root or ROOT)
    ROOT, BUILD = common.ROOT, common.BUILD
    console.configure_paths(BUILD, ROOT)


def normalize_instruction(decoder, row, payload):
    need(row.op != "sti", "Output-only profile must not enable interrupts")
    if row.op in ("mfence", "pause"):
        need(not row.args, "Unexpected fence/pause operands")
    if row.op == "push" and row.args.startswith("$"):
        expected = {"$0x0": bytes.fromhex("6a00"), "$0x28": bytes.fromhex("6a28")}.get(row.args)
        actual = payload[row.address : row.address + row.size]
        need(
            expected is not None and row.size == 2 and actual == expected,
            "Unreviewed immediate push width, bytes or value",
        )
        return decoder.Instruction(row.address, row.size, "push", "%rax"), dict(
            address=row.address,
            original=row.args,
            bytes=actual.hex(),
            equivalent="validated imm8 sign-extended qword push, +8 stack bytes",
        )
    # Memory pushes and signed-wide immediate stack arithmetic are deliberately
    # not normalized in this profile. Unsupported forms fail in the core decoder.
    return row, None


def verify_stack_budget(normal, fault):
    need(all(type(value) is int and value >= 0 for value in (normal, fault)), "Invalid stack measurement")
    need(normal + fault <= 15360, "Existing 16 KiB mixed-stack/fault reserve exhausted")


def stack_evidence(directory):
    decoder = load("framebuffer_stack_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    decoder.CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "framebuffer")
    decoder.configure_console("framebuffer")
    original_rows = decoder.stack_rows
    original_bounded_rows = []

    def bounded_rows(text):
        original_bounded_rows.extend(line for line in text.splitlines() if line.endswith("\tdynamic,bounded"))
        return original_rows(text, allow_bounded=lambda signature: "FramebufferPayload::restore_fixture(" in signature)

    decoder.stack_rows = bounded_rows
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked payload")
    need(not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(), "Unresolved payload")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    normalized = []
    payload = (directory / "payload.bin").read_bytes()
    for address, row in list(code.items()):
        code[address], receipt = normalize_instruction(decoder, row, payload)
        if receipt is not None:
            normalized.append(receipt)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous function starts")
    frames, associations = decoder.cpp_frames(directory, linked, source_root=ROOT)
    language, memory = (
        decoder.Elf(directory / "objects" / "language.o"),
        decoder.Elf(directory / "objects" / "memory.o"),
    )
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = common.linked_assembly(decoder, linked, directory, "payload-entry")
    accounted = (
        set(frames)
        | set(language.functions)
        | set(memory.functions)
        | {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common"}
    )
    need(set(linked.functions) == accounted, "Unaccounted linked function/frame inventory")
    need(
        not any(
            name in linked.functions
            for name in (
                "uefi_console_interrupt",
                "uefi_runtime_enter",
                "__au_runtime_console_put",
                "__au_runtime_console_next",
            )
        ),
        "Unexpected input/runtime capability",
    )
    need(not any(name.startswith("__au_runtime_bytes_") for name in linked.functions), "Unexpected allocator runtime")
    decoder.NORETURN = frozenset(
        name
        for name in linked.functions
        if name == "uefi_payload_fail" or "4failE" in name or name == "_ZN6aurora4uefi15run_framebufferEm"
    )
    functions = {}
    for name, symbol in linked.functions.items():
        try:
            functions[name] = decoder.analyze_function(symbol, code, starts, fault=name == "fault_common")
        except ValueError as error:
            raise ValueError(name + ": " + str(error)) from error
    console.verify_noreturn(functions, decoder.NORETURN)
    bridge = linked.functions[BRIDGE]
    body = [row for address, row in sorted(code.items()) if bridge.address <= address < bridge.address + bridge.size]
    console.verify_bridge_body(decoder, body, starts)
    for name in functions:
        common.graph_peak(functions, frames, name)
    normal = common.graph_peak(functions, frames, "uefi_payload_entry")
    session = common.graph_peak(functions, frames, ENTRY)
    fault = 48 + max(
        common.graph_peak(functions, frames, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    verify_stack_budget(normal["peak"], fault)
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        session=session,
        boot_fault=fault,
        bridge=dict(symbol=BRIDGE, entry=ENTRY),
        compiler_frames=associations,
        original_dynamic_bounded_rows=original_bounded_rows,
        bounded_row_explanation="Annotation retained; exact linked CFG independently proves every finite stack effect",
        linked_functions=functions,
        assembly_objects=assembly,
        normalized_stack_immediates=normalized,
        page_verifier=dict(traversal_slots=4, recursion="rejected"),
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
    )


def build_files():
    names = ["payload.ld", "payload.elf", "payload.bin", "esp/EFI/BOOT/BOOTX64.EFI", "uefi-payload.hpp", "language.s"]
    names += [
        name + ".o"
        for name in (
            "payload",
            "acpi",
            "pci",
            "runtime",
            "framebuffer",
            "language",
            "payload-entry",
            "loader",
            "memory",
            "embed",
            "transition",
        )
    ]
    names += [
        name + suffix
        for name in ("payload", "acpi", "pci", "runtime", "framebuffer", "loader")
        for suffix in (".su", ".ci")
    ]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return common.build_artifacts(names)


def begin(mode, compiler, cxx, flags):
    need(mode in MODES and compiler and cxx and flags, "Missing exact graphics build controls")
    record = dict(
        schema="aurora-framebuffer-build-v1",
        mode=mode,
        flags=flags,
        source_sha256=common.hashes(common.source_files()),
        compiler=common.executable(compiler),
        cxx=common.executable(cxx),
    )
    (BUILD / "framebuffer-build-start.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    (BUILD / "framebuffer-build.json").unlink(missing_ok=True)
    (BUILD / "framebuffer-admission.json").unlink(missing_ok=True)


def inputs(record, mode):
    need(record["schema"] == "aurora-framebuffer-build-v1" and record["mode"] == mode, "Build profile mismatch")
    need(record["source_sha256"] == common.hashes(common.source_files()), "Source changed since build")
    for name in ("compiler", "cxx"):
        need(common.digest(Path(record[name]["path"])) == record[name]["sha256"], "Build executable changed")
    flags = set(record["flags"])
    need(
        {"-DAURORA_UEFI_FRAMEBUFFER", "-DAURORA_UEFI_FRAMEBUFFER_FIXTURE", "-DAURORA_UEFI_FRAMEBUFFER_CAPTURE"}
        <= flags,
        "Missing graphics profile flags",
    )
    need(
        not any(
            flag.startswith("-DAURORA_UEFI_")
            and flag
            not in {
                "-DAURORA_UEFI_FRAMEBUFFER",
                "-DAURORA_UEFI_FRAMEBUFFER_FIXTURE",
                "-DAURORA_UEFI_FRAMEBUFFER_CAPTURE",
            }
            for flag in flags
        ),
        "Mixed profile flags",
    )
    expected = set() if mode == "framebuffer" else {"-DAURORA_FRAMEBUFFER_" + mode.split("-")[1].upper()}
    need({flag for flag in flags if flag.startswith("-DAURORA_FRAMEBUFFER_")} == expected, "Negative profile mismatch")


def end(mode):
    record = json.loads((BUILD / "framebuffer-build-start.json").read_text())
    inputs(record, mode)
    common.verify_object_exports(build_files())
    record["output_sha256"] = common.hashes(build_files())
    (BUILD / "framebuffer-build.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def emit(mode):
    record = json.loads((BUILD / "framebuffer-build.json").read_text())
    inputs(record, mode)
    common.verify_object_exports(build_files())
    need(record["output_sha256"] == common.hashes(build_files()), "Build output changed")
    subprocess.run(
        [sys.executable, "-B", ROOT / "tests/kernel-uefi-image.py", "--build-dir", BUILD], cwd=ROOT, check=True
    )
    result = dict(
        schema="aurora-framebuffer-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        build=record,
        stack=stack_evidence(BUILD),
    )
    result["sha256"] = common.hashes(common.source_files() + build_files() + [BUILD / "framebuffer-build.json"])
    (BUILD / "framebuffer-admission.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("PASS: automated graphics image/mixed-stack checks; independent qualification still requires review")


def checked(mode):
    """Bind automatic checks to current bytes; this does not establish review."""
    need(mode in MODES, "Unsupported framebuffer profile")
    receipt = json.loads((BUILD / "framebuffer-admission.json").read_text())
    need(
        receipt["schema"] == "aurora-framebuffer-admission-v1" and receipt["mode"] == mode,
        "Admission covers another profile",
    )
    need(
        receipt["status"] == "requires-independent-review" and receipt["clock"] == "tcg-original-clock",
        "Unexpected admission status or clock",
    )
    record = json.loads((BUILD / "framebuffer-build.json").read_text())
    inputs(record, mode)
    common.verify_object_exports(build_files())
    need(record["output_sha256"] == common.hashes(build_files()), "Build output changed")
    need(receipt["build"] == record, "Admitted build provenance changed")
    expected = common.hashes(common.source_files() + build_files() + [BUILD / "framebuffer-build.json"])
    need(receipt["sha256"] == expected, "Admission source/output inventory or bytes changed")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    common.path_arguments(parser)
    parser.add_argument("action", choices=("begin", "end", "emit", "checked"))
    parser.add_argument("--mode", required=True, choices=MODES)
    parser.add_argument("--compiler")
    parser.add_argument("--cxx")
    parser.add_argument("--flag", action="append", default=[])
    args = parser.parse_args()
    common.check_depfile_options(args)
    configure_paths(args.build_dir or args.source_root / "build/uefi", args.source_root)
    if args.action == "begin":
        begin(args.mode, args.compiler, args.cxx, args.flag)
        common.write_build_depfile(args, "framebuffer-build-start.json")
    elif args.action == "end":
        end(args.mode)
    elif args.action == "emit":
        emit(args.mode)
    else:
        checked(args.mode)
        print("PASS: current-source framebuffer admission; independent qualification not claimed")


if __name__ == "__main__":
    main()

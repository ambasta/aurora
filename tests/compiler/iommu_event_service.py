#!/usr/bin/env python3
"""Executed Event source/IR ABI, bounded Aurora intake and authority rejections."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
POSITIVE = (
    "fault",
    "finite",
    "empty",
    "partial",
    "zero-poll",
    "zero-record",
    "invalid-poll-budget",
    "invalid-record-budget",
    "poll-budget",
    "record-budget",
    "maximum-budget",
    "code5",
    "code6",
    "unsupported",
    "malformed-code2",
    "poll-overflow",
    "poll-transport",
    "ack-overflow",
    "ack-transport",
    "output",
)
TRAPS = (
    "poll-enum-4",
    "poll-enum-wide",
    "status-32",
    "status-wide",
    "status-all-ones",
    "payload-0-word0",
    "payload-0-word1",
    "payload-2-word0",
    "payload-2-word1",
    "payload-3-word0",
    "payload-3-word1",
    "ack-enum-3",
    "ack-enum-wide",
)


def need(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("ir", type=Path)
    args = parser.parse_args()
    compiler, ir = args.compiler.resolve(strict=True), args.ir.resolve(strict=True)
    work = Path(tempfile.mkdtemp(prefix="iommu-event-service-"))
    cxx = shlex.split(os.environ.get("CXX", "c++"))
    records = []

    def run(argv):
        result = subprocess.run(list(map(str, argv)), cwd=ROOT, capture_output=True, timeout=120)
        records.append(
            dict(
                argv=list(map(str, argv)),
                exit=result.returncode,
                stdout=result.stdout.decode(errors="replace"),
                stderr=result.stderr.decode(errors="replace"),
            )
        )
        (work / "commands.json").write_text(json.dumps(records, indent=2) + "\n")
        return result

    def link(assembly, entry, name, host=ROOT / "tests/compiler/iommu_event_service_host.cpp"):
        text = assembly.read_text()
        candidates = re.findall(r"^\.local\s+(\S+)", text, re.MULTILINE)
        symbol = (
            entry
            if entry in candidates
            else next((s for s in candidates if s.endswith(f"_d{len(entry)}{entry}")), None)
        )
        need(symbol is not None, f"private entry missing: {entry}")
        bridge = f"""\n.text
.global __au_runtime_iommu_event_entry
.hidden __au_runtime_iommu_event_entry
.type __au_runtime_iommu_event_entry,@function
__au_runtime_iommu_event_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call {symbol}
    leave
    ret
.size __au_runtime_iommu_event_entry,.-__au_runtime_iommu_event_entry
"""
        combined = work / (name + "-linked.s")
        combined.write_text(text + bridge)
        binary = work / name
        result = run(
            cxx
            + [
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-no-pie",
                combined,
                host,
                ROOT / "tests/compiler/iommu_event_service_abi.S",
                "-o",
                binary,
            ]
        )
        need(result.returncode == 0, result.stderr.decode())
        return binary

    def emit(source, name):
        assembly = work / (name + ".s")
        result = run([compiler, source, "-o", assembly])
        need(result.returncode == 0, result.stderr.decode())
        return assembly

    consumer = link(emit(ROOT / "examples/kernel-iommu-event-service.au", "consumer"), "iommu_event_intake", "consumer")
    for mode in POSITIVE:
        result = run([consumer, mode])
        need(result.returncode == 0 and result.stdout.startswith(b"PASS IOMMU event"), f"{mode}: {result.stderr!r}")
    for mode in TRAPS:
        result = run([consumer, mode])
        need(result.returncode == -signal.SIGILL, f"{mode}: expected generated-code trap, got {result.returncode}")
    composition = link(
        work / "consumer.s", "iommu_event_intake", "composition", ROOT / "tests/kernel-iommu-event-composition.cpp"
    )
    composition_modes = (
        "fault",
        "wrap",
        "empty",
        "code5",
        "code6",
        "unsupported",
        "malformed-code2",
        "output",
        "poll-overflow",
        "ack-overflow",
        "ack-transport",
        "zero-poll",
        "zero-record",
        "poll-budget",
        "record-budget",
        "maximum-budget",
    )
    for mode in composition_modes:
        result = run([composition, mode])
        need(result.returncode == 0 and result.stdout.startswith(b"PASS"), f"composition {mode}: {result.stderr!r}")
    fixture = link(emit(ROOT / "tests/compiler/iommu_event_service.au", "abi"), "event_service", "abi")
    result = run([fixture, "abi"])
    need(result.returncode == 0 and result.stdout.startswith(b"PASS IOMMU event"), result.stderr.decode())
    modules = work / "modules"
    (modules / "events").mkdir(parents=True)
    (modules / "events/probe.au").write_text("""export module events.probe;
export namespace event_probe {
    auto event_only(builtin::IommuEventSession& events) -> builtin::IommuEventSample {
        const builtin::IommuEventSample result = events.poll();
        return result;
    }
}
""")
    original = (ROOT / "tests/compiler/iommu_event_service.au").read_text()
    helper = (
        "auto event_only(builtin::IommuEventSession& events) -> builtin::IommuEventSample"
        " {\n    const builtin::IommuEventSample result = events.poll();\n    return result"
        ";\n}\n"
    )
    need(helper in original, "cross-module fixture helper changed")
    cross_source = work / "cross-module.au"
    cross_source.write_text(
        original.replace("module event_service_abi;", "module event_service_abi;\nimport events.probe;")
        .replace(helper, "")
        .replace("event_only(events)", "event_probe::event_only(events)")
    )
    cross_assembly = work / "cross-module.s"
    result = run([compiler, "--module-root", modules, cross_source, "-o", cross_assembly])
    need(result.returncode == 0, result.stderr.decode())
    cross_binary = link(cross_assembly, "event_service", "cross-module")
    result = run([cross_binary, "abi"])
    need(result.returncode == 0 and result.stdout.startswith(b"PASS IOMMU event"), result.stderr.decode())
    ir_assembly = work / "independent-ir.s"
    result = run([ir, ir_assembly])
    need(result.returncode == 0 and b"PASS IOMMU event" in result.stdout, result.stderr.decode())
    ir_binary = link(ir_assembly, "event_ir_entry", "independent-ir")
    result = run([ir_binary, "ir"])
    need(result.returncode == 0 and result.stdout.startswith(b"PASS IOMMU event"), result.stderr.decode())

    invalid = [
        "auto f(builtin::IommuEventSession e)->u64{return 0u64;}",
        "auto f(const builtin::IommuEventSession& e)->u64{return 0u64;}",
        "auto f(u64 x,builtin::IommuEventSession& e)->u64{return x;}",
        "auto f(builtin::IommuEventSession& e,builtin::IommuEventSession& f)->u64{return 0u64;}",
        "auto f(builtin::IommuEventSession& e,builtin::DisplaySession& d)->u64{return 0u64;}",
        "auto f(builtin::DisplaySession& d,builtin::IommuEventSession& e)->u64{return 0u64;}",
        (
            "auto f(builtin::IommuEventSession& e,builtin::ConsoleSession& c,builtin::Display"
            "Session& d)->u64{return 0u64;}"
        ),
        "class Holder{builtin::IommuEventSession authority;};auto f()->u64{return 0u64;}",
        "auto f()->u64{builtin::IommuEventSession e;return 0u64;}",
        "auto f(builtin::IommuEventSession& e)->u64{e.put(0u8);return 0u64;}",
        "auto f(builtin::IommuEventSession& e)->u64{e.acknowledge(16u64);return 0u64;}",
        "auto f(builtin::ConsoleSession& c)->u64{c.poll();return 0u64;}",
        "auto f(builtin::IommuEventSession& e)->u64{return f(e);}",
        "auto h(builtin::ConsoleSession& c)->u64{return 0u64;}auto f(builtin::IommuEventSession& e)->u64{return h(e);}",
        (
            "auto h(builtin::IommuEventSession& e,builtin::EventAckResult r)->u64{return 0u64"
            ";}auto f(builtin::IommuEventSession& e)->u64{return h(e,e.acknowledge());}"
        ),
    ]
    invalid += [
        "auto f(builtin::IommuEventSession& e)->u64{builtin::IommuEventSession copy=e;return 0u64;}",
        "auto f(builtin::IommuEventSession& e)->builtin::IommuEventSession{return e;}",
        "auto f()->u64{return reflect_size(type_id(builtin::IommuEventSession));}",
        "auto f(builtin::IommuEventSession& e)->u64{return u64(e);}",
        "auto f()->u64{builtin::IommuEventSession e=builtin::IommuEventSession();return 0u64;}",
        "auto f(builtin::IommuEventSession& e)->u64{e.next();return 0u64;}",
        "auto f(builtin::IommuEventSession& e)->u64{e.pixel(0u64,0u64,0u8,0u8,0u8);return 0u64;}",
        "auto f(builtin::DisplaySession& d)->u64{d.poll();return 0u64;}",
        "auto f()->builtin::EventPollResult{return builtin::EventPollResult::invented;}",
        "auto f()->builtin::EventAckResult{return builtin::EventAckResult::invented;}",
        "auto f()->builtin::EventIntakeCompletion{return builtin::EventIntakeCompletion::invented;}",
        "auto f(builtin::IommuEventSession& e)->builtin::ConsoleSample{return e.poll();}",
        "auto f(builtin::ConsoleSession& c)->builtin::IommuEventSample{return c.next();}",
        "template<typename T> auto f(builtin::IommuEventSession& e,T value)->T{return value;}",
    ]
    for index, body in enumerate(invalid):
        source = work / f"reject-{index}.au"
        source.write_text("module event_rejection;\n" + body + "\n")
        result = run([compiler, "--check", source])
        need(result.returncode == 1 and b"error AU" in result.stderr, f"rejection {index}: {result.stderr!r}")
    receipt = dict(
        status="passed",
        compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
        consumer_cases=len(POSITIVE),
        composition_cases=len(composition_modes),
        malformed_host_traps=len(TRAPS),
        source_rejections=len(invalid),
        independent_ir_and_source_abi=True,
        artifact_directory=str(work),
        guest_executed=False,
    )
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    main()

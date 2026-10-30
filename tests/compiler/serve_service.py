#!/usr/bin/env python3
"""Sealed Serve source/IR ABI, exact catalogues and hostile copied results."""

import argparse
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "serve-service-ir" / "abi.air"

ROOT = Path(__file__).resolve().parents[2]
SOURCE = """module serve_probe;
auto exchange_reply(builtin::ServeSession& session,u64 reply)->builtin::ServeRequest {
    const builtin::ServeRequest request=session.exchange(reply);
    return request;
}
auto serve_entry(builtin::ServeSession& session)->u64 {
    const array<u64,3> live={17u64,23u64,2u64};
    const builtin::ServeRequest request=exchange_reply(session,live[0]+live[1]+live[2]);
    if(size_of(builtin::ServeRequest)!=16 || field_count(builtin::ServeRequest)!=2
        || live[0]!=17u64 || live[1]!=23u64 || live[2]!=2u64) {return 1u64;}
    if(request.status==builtin::ServeStatus::request) {
        if(request.value!=18446744073709551615u64) {return 2u64;}
    } else {
        if(request.status!=builtin::ServeStatus::cancelled || request.value!=0u64) {return 3u64;}
    }
    return live[0]+live[1]+live[2];
}
"""
HOST = r"""
#include <cstdint>
#include <cstdlib>
struct Grant {std::uint64_t grant,generation;};
struct Request {std::uint64_t status,value;};
static unsigned mode,calls;
extern "C" std::uint64_t checked_group_entry(const Grant*);
extern "C" Request __au_runtime_serve_exchange(std::uint64_t grant,std::uint64_t generation,std::uint64_t reply) {
    if(grant!=0x5345525645ULL || generation!=91 || reply!=42 || calls++) std::abort();
    switch(mode) {
    case 0:return {0,UINT64_MAX};
    case 1:return {1,0};
    case 2:return {2,0};
    case 3:return {0x100000000ULL,0};
    case 4:return {0x8000000000000000ULL,0};
    case 5:return {UINT64_MAX,0};
    case 6:return {1,1};
    case 7:return {1,0x100000000ULL};
    default:std::abort();
    }
}
int main(int argc,char**argv) {
    mode=argc==2?std::atoi(argv[1]):0;
    const Grant grant{0x5345525645ULL,91};
    return checked_group_entry(&grant)==42 && calls==1?0:1;
}
"""


def need(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("ir", type=Path)
    args = parser.parse_args()
    compiler, ir = args.compiler.resolve(strict=True), args.ir.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="serve-service-") as scratch:
        work = Path(scratch)
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

        source, host = work / "serve.au", work / "serve-host.cpp"
        source.write_text(SOURCE)
        host.write_text(HOST)
        for name, entry in (("source", "serve_entry"), ("ir", "serve_ir_entry")):
            assembly = work / (name + ".s")
            abi_path, stack_path = work / "serve-abi.json", work / "serve-stack.json"
            result = run(
                [compiler, source, "-o", assembly, "--abi-facts", abi_path, "--stack-facts", stack_path]
                if name == "source"
                else [ir, "--output", AIR, "forwarded", assembly]
            )
            need(result.returncode == 0, result.stderr.decode())
            if name == "source":
                abi = json.loads(abi_path.read_text())
                record = abi["records"]["__au_serve_request"]
                need(
                    record["size"] == 16 and record["alignment"] == 8 and record["reserved"] == 16,
                    "ServeRequest physical layout",
                )
                need(record["source_name"] == "__au_serve_request", "ServeRequest sealed nominal identity")
                need(
                    abi["enums"]["__au_serve_status"]
                    == {"source_name": "__au_serve_status", "cases": {"request": 0, "cancelled": 1}},
                    "ServeStatus exact closed cases",
                )
                need([field["offset"] for field in record["fields"]] == [0, 8], "ServeRequest field offsets")
                need([field["name"] for field in record["fields"]] == ["status", "value"], "ServeRequest field names")
                functions = abi["functions"]
                entry_rows = [row for row in functions.values() if row.get("source_name") == "serve_entry"]
                need(len(entry_rows) == 1, "missing Serve entry ABI")
                need(
                    entry_rows[0]["parameters"]
                    == [{"offset": 0, "bytes": 16, "kind": "service", "type_name": "builtin::ServeSession"}],
                    "Serve entry must name its exact singleton capability",
                )
                stack = json.loads(stack_path.read_text())["functions"]
                calls = [row.get("service_abi", {}).get("calls", {}) for row in stack.values()]
                need(
                    any(
                        row.get("__au_runtime_serve_exchange") == {"sysv_arguments": 3, "result_max": 1}
                        for row in calls
                    ),
                    "Serve runtime facts",
                )
                need(
                    any(
                        row.get("service_abi", {}).get("record")
                        == {"parameters": [["builtin::ServeSession", 16]], "result_bytes": 8}
                        for row in stack.values()
                    ),
                    "Serve exact singleton stack record",
                )
            text = assembly.read_text()
            locals_ = re.findall(r"^\.local\s+(\S+)", text, re.MULTILINE)
            symbol = next((s for s in locals_ if s == entry or s.endswith(f"_d{len(entry)}{entry}")), None)
            need(symbol is not None, "Serve entry must remain private")
            assembly.write_text(
                text
                + f"""\n.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call {symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
            )
            binary = work / name
            result = run(
                shlex.split(os.environ.get("CXX", "c++"))
                + [
                    "-std=c++23",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-no-pie",
                    host,
                    assembly,
                    ROOT / "tests/compiler/service_group_abi.S",
                    "-o",
                    binary,
                ]
            )
            need(result.returncode == 0, result.stderr.decode())
            for mode in range(8):
                result = run([binary, mode])
                need(
                    result.returncode == (0 if mode < 2 else -signal.SIGILL),
                    f"{name} mode {mode}: expected canonical result gate, got {result.returncode}",
                )

        # One compiled execution-effects consumer retains an ordinary private
        # ledger across all five synchronous methods. Hostile reports are data.
        assembly, execution_abi = work / "execution.s", work / "execution-abi.json"
        result = run(
            [compiler, "--abi-facts", execution_abi, ROOT / "tests/compiler/execution_effects.au", "-o", assembly]
        )
        need(result.returncode == 0, result.stderr.decode())
        execution_facts = json.loads(execution_abi.read_text())
        entry = next(
            row for row in execution_facts["functions"].values() if row.get("source_name") == "execution_entry"
        )
        need(
            entry["parameters"]
            == [{"offset": 0, "bytes": 16, "kind": "service", "type_name": "builtin::ExecutionEffects"}],
            "ExecutionEffects nominal entry ABI",
        )
        emitted = assembly.read_text()
        symbol = next(
            name
            for name in re.findall(r"^\.local\s+(\S+)", emitted, re.MULTILINE)
            if name.endswith("_d15execution_entry")
        )
        assembly.write_text(
            emitted
            + f"""\n.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call {symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
        )
        binary = work / "execution"
        result = run(
            shlex.split(os.environ.get("CXX", "c++"))
            + [
                "-std=c++23",
                "-O1",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-no-pie",
                ROOT / "tests/compiler/execution_effects_host.cpp",
                assembly,
                ROOT / "tests/compiler/service_group_abi.S",
                "-o",
                binary,
            ]
        )
        need(result.returncode == 0, result.stderr.decode())
        for mode in range(17):
            result = run([binary, mode])
            need(
                result.returncode == (0 if mode == 0 else -signal.SIGILL), f"execution mode {mode}: {result.returncode}"
            )

        # One actual endpoint consumer and one native trap adapter, with hostile
        # raw channels and bounds as runtime data (not a compilation per case).
        assembly = work / "endpoint.s"
        result = run([compiler, "--target", "aurora", ROOT / "tests/compiler/endpoint.au", "-o", assembly])
        need(result.returncode == 0, result.stderr.decode())
        emitted = assembly.read_text()
        endpoint_symbol = next(
            name
            for name in re.findall(r"^\.local\s+(\S+)", emitted, re.MULTILINE)
            if name.endswith("_d14endpoint_entry")
        )
        assembly.write_text(
            emitted
            + f"""\n.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call {endpoint_symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
        )
        binary = work / "endpoint"
        result = run(
            shlex.split(os.environ.get("CXX", "c++"))
            + [
                "-std=c++23",
                "-O1",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-no-pie",
                ROOT / "tests/compiler/endpoint_host.cpp",
                assembly,
                ROOT / "tests/compiler/service_group_abi.S",
                "-o",
                binary,
            ]
        )
        need(result.returncode == 0, result.stderr.decode())
        for mode in range(17):
            result = run([binary, mode])
            need(
                result.returncode == (0 if mode < 2 else -signal.SIGILL),
                f"endpoint mode {mode}: expected canonical result/bounds gate, got {result.returncode}",
            )

        # Read the explicit block grant through one copied-result consumer. The
        # independent private IR functions test load/descriptor bounds without
        # introducing a public escape hatch into the trusted runtime module.
        assembly, private = work / "block.s", work / "block-private.s"
        result = run(
            [
                compiler,
                "--target",
                "aurora",
                "--module-root",
                ROOT / "library",
                ROOT / "tests/compiler/block.au",
                "-o",
                assembly,
            ]
        )
        need(result.returncode == 0, result.stderr.decode())
        result = run([ir, "--output", AIR.with_name("block.air"), "accepted private block primitives", private])
        need(result.returncode == 0, result.stderr.decode())
        emitted = assembly.read_text()
        symbol = next(
            name for name in re.findall(r"^\.local\s+(\S+)", emitted, re.MULTILINE) if name.endswith("_d11block_entry")
        )
        bridges = [
            ("__au_runtime_group_entry", symbol),
            ("block_byte_entry", "__au_v_m2_6aurora5block_n1_5block_d4byte"),
            ("block_descriptor_entry", "__au_v_m2_6aurora5block_n1_5block_d10descriptor"),
        ]
        private_text = private.read_text().replace("aurora_reflect_", "block_ir_reflect_")
        # Independent translation units keep their generated local labels private.
        private_text += "\n.text\n"
        for name, target in bridges:
            bridge = f"\n.text\n.globl {name}\n.hidden {name}\n.type {name},@function\n{name}:\n"
            bridge += f"    pushq %rbp\n    movq %rsp,%rbp\n    movq %rdi,%r11\n    call {target}\n    leave\n    ret\n"
            bridge += f".size {name},.-{name}\n"
            if name == "__au_runtime_group_entry":
                emitted += bridge
            else:
                private_text += bridge
        assembly.write_text(emitted)
        private.write_text(private_text)
        writer_assembly = work / "writer-private.s"
        result = run(
            [ir, "--output", AIR.with_name("block.air"), "accepted private writer primitives", writer_assembly]
        )
        need(result.returncode == 0, result.stderr.decode())
        writer_text = writer_assembly.read_text().replace("aurora_reflect_", "writer_ir_reflect_")
        for name in ("read", "byte", "descriptor", "stage", "write", "flush", "budget"):
            target = f"__au_v_m2_6aurora11block_write_n1_11block_write_d{len(name)}{name}"
            bridge = f"writer_{name}_entry"
            writer_text += (
                f"\n.text\n.globl {bridge}\n.hidden {bridge}\n.type {bridge},@function\n{bridge}:\n"
                f"    pushq %rbp\n    movq %rsp,%rbp\n    movq %rdi,%r11\n    call {target}\n    leave\n    ret\n"
                f".size {bridge},.-{bridge}\n"
            )
        writer_assembly.write_text(writer_text)
        binary = work / "block"
        result = run(
            shlex.split(os.environ.get("CXX", "c++"))
            + [
                "-std=c++23",
                "-O1",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-no-pie",
                ROOT / "tests/compiler/block_host.cpp",
                assembly,
                private,
                writer_assembly,
                ROOT / "tests/compiler/service_group_abi.S",
                "-o",
                binary,
            ]
        )
        need(result.returncode == 0, result.stderr.decode())
        good = {0, 1, 2, 3, 11, 12, 20, 21, 26, 27}
        for mode in [*range(13), *range(20, 28)]:
            result = run([binary, mode])
            need(
                result.returncode == (0 if mode in good else -signal.SIGILL),
                f"block mode {mode}: expected canonical result/bounds gate, got {result.returncode}",
            )

        for mode in [*range(100, 104), *range(110, 127), *range(130, 133)]:
            result = run([binary, mode])
            need(result.returncode == (0 if mode < 104 else -signal.SIGILL), f"writer mode {mode}: {result.returncode}")

        # Inspect the real process entry's published ABI and startup call graph.
        # The private memory bootstrap must not acquire hosted file authority.
        entry_object = work / "endpoint-main.o"
        entry_abi, entry_stack = work / "endpoint-main-abi.json", work / "endpoint-main-stack.json"
        result = run(
            [
                compiler,
                "--target",
                "aurora",
                "--emit-object",
                ROOT / "tests/host-files/endpoint.au",
                "-o",
                entry_object,
                "--abi-facts",
                entry_abi,
                "--stack-facts",
                entry_stack,
            ]
        )
        need(result.returncode == 0, result.stderr.decode())
        functions = json.loads(entry_abi.read_text())["functions"]
        entry = next(row for row in functions.values() if row.get("source_name") == "main")
        need(
            entry["parameters"]
            == [
                {"offset": 0, "bytes": 16, "kind": "service", "type_name": "builtin::ServeSession"},
                {"offset": 16, "bytes": 8, "kind": "region", "type_name": "builtin::ByteRegion"},
                {"offset": 24, "bytes": 56, "kind": "span"},
            ],
            "retained process main capability/span record",
        )
        calls = json.loads(entry_stack.read_text())["functions"]["_start"]["calls"]
        need(
            "__au_v_m2_6aurora6memory_n1_6memory_d5start" in calls
            and "__au_v_m2_6aurora6memory_n1_6memory_d6finish" in calls,
            "retained process memory startup and cleanup",
        )
        need(not any("_m2_6aurora4host_" in name for name in calls), "endpoint must not call hosted file hooks")

        readonly_start_bytes = None
        for capability, fixture in (("ReadOnlyBlock", "endpoint-block.au"), ("WritableBlock", "endpoint-writer.au")):
            result = run(
                [
                    compiler,
                    "--target",
                    "aurora",
                    "--module-root",
                    ROOT / "library",
                    "--emit-object",
                    ROOT / "tests/host-files" / fixture,
                    "-o",
                    entry_object,
                    "--abi-facts",
                    entry_abi,
                    "--stack-facts",
                    entry_stack,
                ]
            )
            need(result.returncode == 0, result.stderr.decode())
            functions = json.loads(entry_abi.read_text())["functions"]
            entry = next(row for row in functions.values() if row.get("source_name") == "main")
            need(
                entry["parameters"]
                == [
                    {"offset": 0, "bytes": 16, "kind": "service", "type_name": "builtin::ServeSession"},
                    {"offset": 16, "bytes": 16, "kind": "service", "type_name": "builtin::" + capability},
                    {"offset": 32, "bytes": 8, "kind": "region", "type_name": "builtin::ByteRegion"},
                    {"offset": 40, "bytes": 56, "kind": "span"},
                ],
                "separate process block grant record",
            )
            start_facts = json.loads(entry_stack.read_text())["functions"]["_start"]
            if capability == "ReadOnlyBlock":
                readonly_start_bytes = start_facts["local_bytes"]
            else:
                need(start_facts["local_bytes"] == readonly_start_bytes + 16, "independent writer staging window")
            calls = start_facts["calls"]
            need(
                "__au_v_m2_6aurora6memory_n1_6memory_d5start" in calls
                and "__au_v_m2_6aurora6memory_n1_6memory_d6finish" in calls
                and not any("_m2_6aurora4host_" in name for name in calls),
                "block bootstrap memory-only authority",
            )

        # All optional catalogues are independent, including sparse operation IDs.
        for call, port, serve in itertools.product((False, True), repeat=3):
            terms = ["true"]
            for active, type_, case in (
                (call, "CallStatus", "replied"),
                (port, "PortWriteResult", "issued"),
                (serve, "ServeStatus", "request"),
            ):
                if active:
                    terms.append(f"builtin::{type_}::{case}==builtin::{type_}::{case}")
            declarations = []
            if call:
                declarations.append(
                    "auto call(builtin::CallSession& c)->builtin::CallResult{"
                    "const builtin::CallResult r=c.call(42u64);return r;}"
                )
            if port:
                declarations.append("auto port(builtin::Com1UartGrant& p)->u8{return p.read8(0u64);}")
            if serve:
                declarations.append(
                    "auto serve(builtin::ServeSession& s)->builtin::ServeRequest{"
                    "const builtin::ServeRequest r=s.exchange(42u64);return r;}"
                )
            source.write_text(
                "module catalogue;auto f()->bool{return " + " && ".join(terms) + ";}" + "".join(declarations)
            )
            result = run([compiler, source, "-o", work / "catalogue.s", "--abi-facts", work / "catalogue.json"])
            need(result.returncode == 0, result.stderr.decode())
            abi = json.loads((work / "catalogue.json").read_text())
            need(("__au_call_result" in abi["records"]) == call, "Call catalogue changed")
            need(("__au_port_write_result" in abi["enums"]) == port, "Port catalogue changed")
            need(("__au_serve_request" in abi["records"]) == serve, "Serve request catalogue activation")
            need(("__au_serve_status" in abi["enums"]) == serve, "Serve status catalogue activation")

        plain = "module catalogue;auto f()->i64{return 7;}"
        baseline = None
        for label, code, active in (
            ("plain", plain, False),
            ("comment", plain + " // builtin::ServeSession builtin::ServeRequest builtin::ServeStatus\n", False),
            (
                "string",
                'module catalogue;auto f()->i64{const array<u8,20> s="builtin::ServeStatus";return i64(s[0]);}',
                False,
            ),
            (
                "user",
                "module catalogue;class ServeRequest{public:i64 n;};auto f()->i64{return size_of(ServeRequest);}",
                False,
            ),
            (
                "unused-type",
                "module catalogue;template<Scalar T> auto unused(T v)->i64{return "
                "size_of(builtin::ServeRequest);}auto f()->i64{return 7;}",
                True,
            ),
            (
                "unused-case",
                "module catalogue;template<Scalar T> auto unused(T v)->bool{return "
                "builtin::ServeStatus::request==builtin::ServeStatus::request;}auto f()->i64{return 7;}",
                True,
            ),
        ):
            source.write_text(code)
            assembly, abi_path, stack_path = [
                work / ("catalogue" + extension) for extension in (".s", ".json", "-stack.json")
            ]
            result = run([compiler, source, "-o", assembly, "--abi-facts", abi_path, "--stack-facts", stack_path])
            need(result.returncode == 0, f"{label}: {result.stderr.decode()}")
            abi = json.loads(abi_path.read_text())
            need(("__au_serve_request" in abi["records"]) == active, label + ": syntax-only activation")
            output = tuple(path.read_bytes() for path in (assembly, abi_path, stack_path))
            if label == "plain":
                baseline = output
            if label == "comment":
                need(output == baseline, "Serve-free graph assembly/ABI/stack output changed")

        p = "builtin::ServeSession& s"
        invalid = {
            "value": "auto f(builtin::ServeSession s)->u64{return 0u64;}",
            "const": "auto f(const builtin::ServeSession& s)->u64{return 0u64;}",
            "late": f"auto f(u64 n,{p})->u64{{return n;}}",
            "mint": "auto f()->u64{builtin::ServeSession s;return 0u64;}",
            "construct": "auto f()->u64{builtin::ServeSession s=builtin::ServeSession();return 0u64;}",
            "store": "class Holder{builtin::ServeSession s;};auto f()->u64{return 0u64;}",
            "copy": f"auto f({p})->u64{{builtin::ServeSession copy=s;return 0u64;}}",
            "move": f"auto f({p})->u64{{builtin::ServeSession copy=move(s);return 0u64;}}",
            "return": f"auto f({p})->builtin::ServeSession{{return s;}}",
            "reflect": "auto f()->i64{return size_of(builtin::ServeSession);}",
            "reflect-id": "auto f()->u64{return reflect_size(type_id(builtin::ServeSession));}",
            "cast": f"auto f({p})->u64{{return u64(s);}}",
            "recursive": f"auto f({p})->u64{{return f(s);}}",
            "missing": f"auto f({p})->builtin::ServeRequest{{const builtin::ServeRequest r=s.exchange();return r;}}",
            "extra": f"auto f({p})->u64{{s.exchange(0u64,1u64);return 0u64;}}",
            "signed": f"auto f({p})->u64{{s.exchange(0);return 0u64;}}",
            "byte": f"auto f({p})->u64{{s.exchange(0u8);return 0u64;}}",
            "invented-case": "auto f()->builtin::ServeStatus{return builtin::ServeStatus::closed;}",
            "suspended": f"auto h({p},builtin::ServeRequest r)->u64{{return r.value;}}"
            f"auto f({p})->u64{{return h(s,s.exchange(0u64));}}",
            "raw": "auto __au_runtime_serve_exchange()->u64{return 0u64;}",
        }
        for kind in (
            "ConsoleSession",
            "DisplaySession",
            "IommuEventSession",
            "CallSession",
            "Com1UartGrant",
            "ServeSession",
        ):
            for reverse in (False, True):
                pair = [p, f"builtin::{kind}& other"]
                if reverse:
                    pair.reverse()
                invalid[f"mixed-{kind}-{reverse}"] = f"auto f({','.join(pair)})->u64{{return 0u64;}}"
        invalid["main-no-region"] = (
            f"auto main({p},builtin::span<const u8> a)->builtin::HostExit{{return builtin::HostExit::success;}}"
        )
        invalid["main-wrong-result"] = (
            f"auto main({p},builtin::ByteRegion r,builtin::span<const u8> a)->u64{{return 0u64;}}"
        )
        invalid["region-misplaced"] = f"auto f({p},u64 n,builtin::ByteRegion r)->u64{{return n;}}"
        invalid["region-repeated"] = f"auto f({p},builtin::ByteRegion r,builtin::ByteRegion t)->u64{{return 0u64;}}"
        invalid["private-exchange"] = (
            f"auto f({p})->builtin::ServeRequest{{const builtin::ServeRequest r=s.message_exchange(0u64);return r;}}"
        )
        invalid["private-load"] = f"auto f({p})->u8{{return s.message_load(0u64);}}"
        invalid["private-store"] = f"auto f({p})->u8{{return s.message_store(0u64,0u8);}}"
        invalid["private-identity"] = f"auto f({p})->u64{{return s.message_identity(0u64);}}"
        b = "builtin::ReadOnlyBlock& b"
        for label in (
            "value",
            "const",
            "late",
            "mint",
            "construct",
            "store",
            "copy",
            "move",
            "return",
            "reflect",
            "reflect-id",
            "cast",
            "recursive",
        ):
            invalid["block-" + label] = invalid[label].replace("ServeSession", "ReadOnlyBlock")
        for method, result_type in (("read_sector", "u64"), ("sector_byte", "u8"), ("descriptor", "u64")):
            invalid["block-private-" + method] = f"auto f({b})->{result_type}{{return b.{method}(0u64);}}"
        for kind in (
            "ConsoleSession",
            "DisplaySession",
            "IommuEventSession",
            "CallSession",
            "Com1UartGrant",
            "HostFiles",
            "ReadOnlyBlock",
        ):
            for reverse in (False, True):
                pair = [b, f"builtin::{kind}& other"]
                if reverse:
                    pair.reverse()
                invalid[f"block-mixed-{kind}-{reverse}"] = f"auto f({','.join(pair)})->u64{{return 0u64;}}"
        activation = f"auto block_active({b})->u64{{return 0u64;}}"
        invalid["block-tag64-alias"] = (
            activation + "auto f(builtin::DisplaySession& d,builtin::IommuEventSession& e)->u64{return 0u64;}"
        )
        invalid["block-tag128-alias"] = (
            activation + "auto f(builtin::ConsoleSession& c,builtin::DisplaySession& d,"
            "builtin::IommuEventSession& e)->u64{return 0u64;}"
        )
        for label, params in (
            ("reordered", f"{b},{p},builtin::ByteRegion r"),
            ("region-middle", f"{p},builtin::ByteRegion r,{b}"),
            ("only-block", f"{b},builtin::ByteRegion r"),
        ):
            invalid["block-main-" + label] = (
                f"auto main({params},builtin::span<const u8> a)->builtin::HostExit{{"
                "return builtin::HostExit::success;}"
            )
        writer = "builtin::WritableBlock& w"
        writer_main = (
            f"auto main({writer},builtin::ByteRegion r,builtin::span<const u8> a)"
            "->builtin::HostExit{return builtin::HostExit::success;}"
        )
        source.write_text("module writer_entry;import aurora.memory;" + writer_main)
        result = run([compiler, "--target", "aurora", "--emit-object", source, "-o", entry_object])
        need(result.returncode == 0, result.stderr.decode())
        result = run([compiler, "--emit-object", source, "-o", entry_object])
        need(result.returncode == 1 and b"error AU" in result.stderr, "writer entry rejects Linux")
        source.write_text(
            "module mounted_entry;import aurora.memory;"
            + writer_main.replace("auto main(", "auto main(builtin::ServeSession& s,")
        )
        result = run([compiler, "--emit-object", source, "-o", entry_object])
        need(result.returncode == 1 and b"error AU" in result.stderr, "mounted writer entry rejects Linux")
        for label in (
            "value",
            "const",
            "late",
            "mint",
            "construct",
            "store",
            "copy",
            "move",
            "return",
            "reflect",
            "reflect-id",
            "cast",
            "recursive",
        ):
            invalid["writer-" + label] = invalid[label].replace("ServeSession", "WritableBlock")
        for kind in ("ReadOnlyBlock", "HostFiles", "WritableBlock", "ConsoleSession", "DisplaySession", "CallSession"):
            for reverse in (False, True):
                pair = [writer, f"builtin::{kind}& other"]
                if reverse:
                    pair.reverse()
                invalid[f"writer-mixed-{kind}-{reverse}"] = f"auto f({','.join(pair)})->u64{{return 0u64;}}"
        invalid["writer-main-reverse"] = (
            f"auto main({writer},builtin::ServeSession& s,builtin::ByteRegion r,builtin::span<const u8> a)"
            "->builtin::HostExit{return builtin::HostExit::success;}"
        )
        invalid["writer-triple"] = (
            f"auto f(builtin::ServeSession& s,{writer},builtin::ReadOnlyBlock& b)->u64{{return 0u64;}}"
        )
        invalid["writer-tag1024-alias"] = (
            f"auto writer_active(builtin::ServeSession& s,{writer})->u64{{return 0u64;}}"
            "auto f(builtin::DisplaySession& d,builtin::CallSession& c)->u64{return 0u64;}"
        )
        for method, arguments, result_type in (
            ("read_sector", "0u64", "u64"),
            ("sector_byte", "0u64", "u8"),
            ("descriptor", "0u64", "u64"),
            ("stage_byte", "0u64,0u8", "u64"),
            ("write_sector", "0u64", "u64"),
            ("flush", "", "u64"),
            ("budget", "", "u64"),
        ):
            invalid["writer-private-" + method] = f"auto f({writer})->{result_type}{{return w.{method}({arguments});}}"
        invalid["writer-tag512-alias"] = (
            f"auto writer_active({writer})->u64{{return 0u64;}}"
            "auto f(builtin::ConsoleSession& c,builtin::CallSession& s)->u64{return 0u64;}"
        )
        invalid["readonly-write"] = f"auto f({b})->u64{{return b.write_sector(0u64);}}"
        invalid["readonly-flush"] = f"auto f({b})->u64{{return b.flush();}}"
        for label in (
            "value",
            "const",
            "late",
            "mint",
            "construct",
            "store",
            "copy",
            "move",
            "return",
            "reflect",
            "reflect-id",
            "cast",
            "recursive",
        ):
            invalid["execution-" + label] = invalid[label].replace("ServeSession", "ExecutionEffects")
        execution = "builtin::ExecutionEffects& e"
        for kind in (
            "ConsoleSession",
            "DisplaySession",
            "ServeSession",
            "HostFiles",
            "ReadOnlyBlock",
            "WritableBlock",
            "ExecutionEffects",
        ):
            for reverse in (False, True):
                pair = [execution, f"builtin::{kind}& other"]
                if reverse:
                    pair.reverse()
                invalid[f"execution-mixed-{kind}-{reverse}"] = f"auto f({','.join(pair)})->u64{{return 0u64;}}"
        invalid["execution-finish-integer"] = f"auto f({execution})->builtin::ExecEffect{{return e.finish(0u64);}}"
        invalid["execution-finish-wrong-enum"] = (
            f"auto f({execution})->builtin::ExecEffect{{return e.finish(builtin::ExecEffect::success);}}"
        )
        invalid["execution-suspended"] = (
            f"auto h({execution},builtin::ExecEffect r)->u64{{return 0u64;}}"
            f"auto f({execution})->u64{{return h(e,e.output());}}"
        )
        invalid["execution-wrong-forward"] = (
            f"auto h({execution})->u64{{return 0u64;}}auto f(builtin::ConsoleSession& c)->u64{{return h(c);}}"
        )
        invalid["execution-main"] = f"auto main({execution})->u64{{return 0u64;}}"
        invalid["execution-region"] = f"auto f({execution},builtin::ByteRegion r)->u64{{return 0u64;}}"
        for label, code in invalid.items():
            source.write_text("module rejected;" + code)
            target = ["--target", "aurora"] if label.startswith(("writer-", "readonly-")) else []
            result = run([compiler, *target, "--check", source])
            need(result.returncode == 1 and b"error AU" in result.stderr, f"{label}: {result.stderr!r}")
            if label in ("missing", "extra"):
                need(
                    result.stderr.count(b"error AU") == 1
                    and result.stderr.endswith(b"error AU3001: wrong argument count for method\n"),
                    f"{label}: expected method arity diagnostic, got {result.stderr!r}",
                )
        print(
            "PASS Serve: source/IR, endpoint, block, writer and execution effects, 74 hostile runtime traps, "
            f"eight catalogues, {len(invalid)} rejections"
        )


if __name__ == "__main__":
    main()

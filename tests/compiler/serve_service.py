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
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    compiler, ir = args.compiler.resolve(strict=True), args.ir.resolve(strict=True)
    work = args.artifacts.resolve() if args.artifacts else Path(tempfile.mkdtemp(prefix="serve-service-"))
    work.mkdir(parents=True, exist_ok=True)
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
            else [ir, assembly]
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
                any(row.get("__au_runtime_serve_exchange") == {"sysv_arguments": 3, "result_max": 1} for row in calls),
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
            declarations.append("auto port(builtin::PortRange& p)->u8{return p.read8(0u64);}")
        if serve:
            declarations.append(
                "auto serve(builtin::ServeSession& s)->builtin::ServeRequest{"
                "const builtin::ServeRequest r=s.exchange(42u64);return r;}"
            )
        source.write_text("module catalogue;auto f()->bool{return " + " && ".join(terms) + ";}" + "".join(declarations))
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
    for kind in ("ConsoleSession", "DisplaySession", "IommuEventSession", "CallSession", "PortRange", "ServeSession"):
        for reverse in (False, True):
            pair = [p, f"builtin::{kind}& other"]
            if reverse:
                pair.reverse()
            invalid[f"mixed-{kind}-{reverse}"] = f"auto f({','.join(pair)})->u64{{return 0u64;}}"
    invalid["region"] = f"auto f({p},builtin::ByteRegion r)->u64{{return 0u64;}}"
    for label, code in invalid.items():
        source.write_text("module rejected;" + code)
        result = run([compiler, "--check", source])
        need(result.returncode == 1 and b"error AU" in result.stderr, f"{label}: {result.stderr!r}")
    print(f"PASS Serve: source/IR execution, 12 hostile runtime traps, eight catalogues, {len(invalid)} rejections")


if __name__ == "__main__":
    main()

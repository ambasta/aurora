#!/usr/bin/env python3
"""Sealed Port source/independent IR execution; fixed mocks, never actual I/O."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "port-service-ir" / "abi.air"

ROOT = Path(__file__).resolve().parents[2]


def need(value, message):
    if not value:
        raise RuntimeError(message)


SOURCE = """module port_probe;
class State {public:u8 value;u64 offset;};
auto read_port_byte(builtin::Com1UartGrant& p)->u8{return p.read8(5u64);}
auto write_port_state(builtin::Com1UartGrant& p, State state)->State{
    State result=state;
    if(p.write8(state.offset,state.value)!=builtin::PortWriteResult::issued){result.value=0u8;}
    result.offset=result.offset+1u64;
    return result;
}
auto port_entry(builtin::Com1UartGrant& p)->i64{
    State s=State{.value=read_port_byte(p),.offset=0u64};
    State r=write_port_state(p,s);
    if(r.value!=255u8 || r.offset!=1u64 || s.value!=255u8 || s.offset!=0u64){return 1;}
    return 42;
}
"""
HOST = r"""
#include <cstdint>
#include <cstdlib>
struct Grant {std::uint64_t grant, generation;};
static unsigned mode, reads, writes;
extern "C" std::uint64_t checked_group_entry(const Grant*);
extern "C" std::uint64_t __au_runtime_port_read8(std::uint64_t grant,std::uint64_t generation,std::uint64_t offset){
    if(grant!=0x504f5254 || generation!=91 || offset!=5 || reads++ || writes) std::abort();
    if(mode==1) return 256;
    if(mode==2) return 0x100000000ULL;
    if(mode==3) return UINT64_MAX;
    return 255;
}
extern "C" std::uint64_t __au_runtime_port_write8(
    std::uint64_t grant,std::uint64_t generation,std::uint64_t offset,std::uint64_t value){
    if(grant!=0x504f5254 || generation!=91 || offset!=0 || value!=255 || reads!=1 || writes++) std::abort();
    if(mode==4) return 1;
    if(mode==5) return 256;
    if(mode==6) return 0x100000000ULL;
    if(mode==7) return UINT64_MAX;
    return 0;
}
int main(int argc,char**argv){
    mode=argc==2 ? std::atoi(argv[1]) : 0;
    const Grant grant{0x504f5254,91};
    return checked_group_entry(&grant)==42 && reads==1 && writes==1 ? 0 : 1;
}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("ir", type=Path)
    args = parser.parse_args()
    compiler, ir = args.compiler.resolve(strict=True), args.ir.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="port-service-") as scratch:
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

        host = work / "port-host.cpp"
        host.write_text(HOST)
        source = work / "port.au"
        source.write_text(SOURCE)
        for name, entry in (("source", "port_entry"), ("ir", "port_ir_entry")):
            assembly = work / (name + ".s")
            stack_path, abi_path = work / "port-stack.json", work / "port-abi.json"
            result = run(
                [compiler, source, "-o", assembly, "--stack-facts", stack_path, "--abi-facts", abi_path]
                if name == "source"
                else [ir, "--output", AIR, "forwarded", assembly]
            )
            need(result.returncode == 0, result.stderr.decode())
            if name == "source":
                stack = json.loads(stack_path.read_text())["functions"]
                copied = [
                    row
                    for row in stack.values()
                    if (row.get("service_abi", {}).get("record") or {}).get("result_kind") == "copied_class"
                ]
                need(len(copied) == 1, "copied State helper must have a distinct Port service record")
                need(
                    copied[0]["copied_record"] is None
                    and copied[0]["service_abi"]["record"]
                    == {
                        "parameters": [["builtin::Com1UartGrant", 16], ["copied_class", 16]],
                        "result_bytes": 16,
                        "result_kind": "copied_class",
                    },
                    "Port copied State stack ABI must retain exact copied widths and kind",
                )
                scalar = [
                    row["service_abi"]["record"]
                    for row in stack.values()
                    if row.get("service_abi", {}).get("record")
                    and row["service_abi"]["record"].get("result_kind") != "copied_class"
                ]
                need(
                    any(row == {"parameters": [["builtin::Com1UartGrant", 16]], "result_bytes": 1} for row in scalar),
                    "read helper must retain scalar u8 result width",
                )
                abi = json.loads(abi_path.read_text())
                copied_abi = [
                    row
                    for row in abi["functions"].values()
                    if len(row["parameters"]) == 2 and row["parameters"][1]["kind"] == "class"
                ]
                need(len(copied_abi) == 1, "missing copied State helper generic ABI")
                row = copied_abi[0]
                need(
                    row["parameter_bytes"] == 32
                    and row["parameters"][0]
                    == {
                        "offset": 0,
                        "bytes": 16,
                        "kind": "service",
                        "type_name": "builtin::Com1UartGrant",
                    },
                    "Port authority identity/width lost from generic ABI",
                )
                state_type = row["parameters"][1]["type_name"]
                need(
                    row["parameters"][1]
                    == {
                        "offset": 16,
                        "bytes": 16,
                        "kind": "class",
                        "type_name": state_type,
                    }
                    and row["result"] == {"bytes": 16, "kind": "class", "type_name": state_type}
                    and state_type in abi["records"],
                    "copied State nominal identity/width lost from generic ABI",
                )
            text = assembly.read_text()
            locals_ = re.findall(r"^\.local\s+(\S+)", text, re.MULTILINE)
            symbol = next((s for s in locals_ if s == entry or s.endswith(f"_d{len(entry)}{entry}")), None)
            need(symbol is not None, "Port entry must remain private")
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
                    result.returncode == (0 if mode == 0 else -signal.SIGILL),
                    f"{name} mode {mode}: expected canonicality gate, got {result.returncode}: {result.stderr!r}",
                )

        p = "builtin::Com1UartGrant& p"
        invalid = {
            "old-spelling": (
                "auto f(builtin::PortRange& p)->u8{return p.read8(0u64);}",
                "AU2001: expected 'array' (found 'PortRange')",
            ),
            "value": (
                "auto f(builtin::Com1UartGrant p)->i64{return 0;}",
                "AU3001: service functions require one leading exclusive sealed service reference and copied result",
            ),
            "const": (
                "auto f(const builtin::Com1UartGrant& p)->i64{return 0;}",
                "AU3001: service functions require one leading exclusive sealed service reference and copied result",
            ),
            "late": (
                f"auto f(u64 n,{p})->i64{{return 0;}}",
                "AU2001: borrowed parameters require a supported leading ownership reference signature "
                "on an ordinary function (found 'p')",
            ),
            "mint": ("auto f()->i64{builtin::Com1UartGrant p;return 0;}", "AU2001: expected '=' (found ';')"),
            "construct": (
                "auto f()->i64{builtin::Com1UartGrant p=builtin::Com1UartGrant();return 0;}",
                "AU4001: reserved builtin namespace or identifier: builtin",
            ),
            "store": (
                "class Holder{builtin::Com1UartGrant p;};auto f()->i64{return 0;}",
                "AU2003: unsupported class field type 'builtin::Com1UartGrant': class fields require scalar, class, "
                "private fixed-array or private owned-byte storage",
            ),
            "copy": (
                f"auto f({p})->i64{{builtin::Com1UartGrant copy=p;return 0;}}",
                "AU3001: service capability cannot be stored in a local",
            ),
            "move": (
                f"auto f({p})->i64{{builtin::Com1UartGrant copy=move(p);return 0;}}",
                "AU3001: service capability cannot be stored in a local",
            ),
            "return": (
                f"auto f({p})->builtin::Com1UartGrant{{return p;}}",
                "AU2001: only scalar function results or scalar-field class values are supported (found '{')",
            ),
            "reflect": (
                "auto f()->i64{return size_of(builtin::Com1UartGrant);}",
                "AU3001: resource capabilities are unavailable to reflection",
            ),
            "reflect-id": (
                "auto f()->u64{return reflect_size(type_id(builtin::Com1UartGrant));}",
                "AU3001: resource capabilities are unavailable to reflection",
            ),
            "cast": (f"auto f({p})->u64{{return u64(p);}}", "AU3001: service capability is not a value"),
            "revoke": (
                f"auto f({p})->i64{{p.revoke();return 0;}}",
                "AU3001: unknown operation for sealed service kind",
            ),
            "recursive": (
                f"auto f({p})->i64{{return f(p);}}",
                "AU3001: invalid typed IR: recursive receiver call cycle",
            ),
            "read-missing": (f"auto f({p})->u8{{return p.read8();}}", "AU3001: wrong argument count for method"),
            "read-extra": (f"auto f({p})->u8{{return p.read8(0u64,1u64);}}", "AU3001: wrong argument count for method"),
            "read-signed": (f"auto f({p})->u8{{return p.read8(0);}}", "AU3001: expected u64, got i64"),
            "read-byte": (f"auto f({p})->u8{{return p.read8(0u8);}}", "AU3001: expected u64, got u8"),
            "read-return": (
                f"auto f({p})->builtin::PortWriteResult{{return p.read8(0u64);}}",
                "AU3001: expected builtin::PortWriteResult, got u8",
            ),
            "write-missing": (
                f"auto f({p})->i64{{p.write8(0u64);return 0;}}",
                "AU3001: wrong argument count for method",
            ),
            "write-extra": (
                f"auto f({p})->i64{{p.write8(0u64,0u8,0u8);return 0;}}",
                "AU3001: wrong argument count for method",
            ),
            "write-wide": (f"auto f({p})->i64{{p.write8(0u64,0u64);return 0;}}", "AU3001: expected u8, got u64"),
            "write-signed": (f"auto f({p})->i64{{p.write8(0u64,0);return 0;}}", "AU3001: expected u8, got i64"),
            "write-offset": (f"auto f({p})->i64{{p.write8(0u8,0u8);return 0;}}", "AU3001: expected u64, got u8"),
            "write-return": (
                f"auto f({p})->u8{{return p.write8(0u64,0u8);}}",
                "AU3001: expected u8, got builtin::PortWriteResult",
            ),
            "invented-case": (
                "auto f()->builtin::PortWriteResult{return builtin::PortWriteResult::timeout;}",
                "AU4001: unknown sealed service enum case: builtin::PortWriteResult::timeout",
            ),
            "suspended": (
                f"auto h({p},u8 b)->u8{{return b;}}auto f({p})->u8{{return h(p,p.read8(0u64));}}",
                "AU3001: service operation requires an active named exclusive service parameter",
            ),
            "raw-read": (
                "auto __au_runtime_port_read8()->i64{return 0;}",
                "AU2001: reserved compiler identifier prefix: __au_ (found '__au_runtime_port_read8')",
            ),
            "raw-write": (
                "auto __au_runtime_port_write8()->i64{return 0;}",
                "AU2001: reserved compiler identifier prefix: __au_ (found '__au_runtime_port_write8')",
            ),
        }
        for width in (16, 32):
            for op in ("read", "write"):
                invalid[f"{op}{width}"] = (
                    f"auto f({p})->i64{{p.{op}{width}(0u64);return 0;}}",
                    "AU3001: unknown operation for sealed service kind",
                )
        for kind in ("ConsoleSession", "DisplaySession", "IommuEventSession", "CallSession", "Com1UartGrant"):
            for reverse in (False, True):
                pair = [p, f"builtin::{kind}& other"]
                if reverse:
                    pair.reverse()
                invalid[f"mixed-{kind}-{reverse}"] = (
                    f"auto f({','.join(pair)})->i64{{return 0;}}",
                    "AU2001: borrowed parameters require a supported leading ownership reference signature "
                    f"on an ordinary function (found '{'p' if reverse else 'other'}')",
                )
        for name, (body, expected) in invalid.items():
            source = work / (name + ".au")
            source.write_text("module rejected;" + body)
            result = run([compiler, "--check", source])
            diagnostics = re.findall(rb"error (AU[0-9]{4}: [^\n]+)", result.stderr)
            need(
                result.returncode == 1 and not result.stdout and diagnostics == [expected.encode()],
                f"{name}: expected {expected!r}, got {result.returncode}: {result.stderr!r}",
            )
        print(
            f"PASS Port: source and independent IR execution, 14 malformed host traps, {len(invalid)} source rejections"
        )


if __name__ == "__main__":
    main()

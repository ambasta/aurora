#!/usr/bin/env python3
"""Distinct sealed service group source/ABI probe; no native or guest claim."""

import argparse
import json
import os
import re
import signal
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def require(okay, message):
    if not okay:
        raise RuntimeError(message)


def run(command):
    return subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, timeout=120)


def catalogue_checks(compiler, work):
    source = work / "catalogue.au"
    facts = work / "catalogue.json"
    assembly = work / "catalogue.s"
    stack = work / "catalogue-stack.json"
    plain = "module catalogue; auto f()->i64{return 7;}"
    cases = {
        "plain": (plain, False),
        "comment": (plain + " // builtin::CallSession builtin::CallResult builtin::CallStatus\n", False),
        "string": (
            'module catalogue; auto f()->i64{const array<u8,19> s="builtin::CallStatus";return i64(s[0]);}',
            False,
        ),
        "user-name": (
            "module catalogue; class CallResult {public:i64 n;}; auto f()->i64{return size_of(CallResult);}",
            False,
        ),
        "status-type": (
            "module catalogue; auto f(builtin::CallStatus s)->bool{return s==builtin::CallStatus::replied;}",
            True,
        ),
        "status-only": (
            "module catalogue; auto f()->bool{return builtin::CallStatus::replied==builtin::CallStatus::replied;}",
            True,
        ),
        "copied-result": ("module catalogue; auto f(builtin::CallResult r)->u64{return r.value;}", True),
        "reflection": (
            "module catalogue; auto f()->i64{return size_of(builtin::CallResult)"
            "+field_count(builtin::CallResult)+size_of(builtin::CallStatus);}",
            True,
        ),
        "unused-template-type": (
            "module catalogue; template<Scalar T> auto unused(T v)->i64{return size_of(builtin::CallResult);}"
            " auto f()->i64{return 7;}",
            True,
        ),
        "unused-template-case": (
            "module catalogue; template<Scalar T> auto unused(T v)->bool{return builtin::CallStatus::replied"
            "==builtin::CallStatus::replied;} auto f()->i64{return 7;}",
            True,
        ),
        "instantiated-template": (
            "module catalogue; template<Scalar T> auto identity(T v)->T{return v;}"
            " auto f()->bool{return identity<i64>(7)==7 && builtin::CallStatus::replied"
            "==builtin::CallStatus::replied;}",
            True,
        ),
    }
    # Preserve all Call cases and their legacy expectations; Port is independent.
    cases = {label: (text, active, False) for label, (text, active) in cases.items()}
    cases.update(
        {
            "port-comment": (plain + " // builtin::PortRange builtin::PortWriteResult\n", False, False),
            "port-string": (
                'module catalogue; auto f()->i64{const array<u8,24> s="builtin::PortWriteResult";return i64(s[0]);}',
                False,
                False,
            ),
            "port-user-name": (
                "module catalogue; class PortRange {public:i64 n;}; class PortWriteResult {public:i64 n;}; "
                "auto f()->i64{return size_of(PortRange);}",
                False,
                False,
            ),
            "port-type": ("module catalogue; auto f(builtin::PortRange& p)->u8{return p.read8(7u64);}", False, True),
            "port-status-type": (
                "module catalogue; auto f(builtin::PortWriteResult r)->bool{return "
                "r==builtin::PortWriteResult::issued;}",
                False,
                True,
            ),
            "port-status-only": (
                "module catalogue; auto f()->bool{return "
                "builtin::PortWriteResult::issued==builtin::PortWriteResult::issued;}",
                False,
                True,
            ),
            "port-unused-template-type": (
                "module catalogue; template<Scalar T> auto unused(T v)->i64{return "
                "size_of(builtin::PortWriteResult);} auto f()->i64{return 7;}",
                False,
                True,
            ),
            "port-unused-template-case": (
                "module catalogue; template<Scalar T> auto unused(T v)->bool{return "
                "builtin::PortWriteResult::issued==builtin::PortWriteResult::issued;} auto f()->i64{return "
                "7;}",
                False,
                True,
            ),
            "port-sparse-operations": (
                "module catalogue; auto f(builtin::PortRange& p)->builtin::PortWriteResult{const u8 "
                "b=p.read8(7u64);return p.write8(7u64,b);}",
                False,
                True,
            ),
            "both-port-first": (
                "module catalogue; auto p(builtin::PortRange& p)->u8{return p.read8(7u64);} auto "
                "c(builtin::CallSession& c)->builtin::CallResult{const builtin::CallResult "
                "result=c.call(42u64);return result;}",
                True,
                True,
            ),
            "both-call-first": (
                "module catalogue; auto c(builtin::CallSession& c)->builtin::CallResult{const "
                "builtin::CallResult result=c.call(42u64);return result;} auto p(builtin::PortRange& "
                "p)->u8{return p.read8(7u64);}",
                True,
                True,
            ),
        }
    )

    def check_families(abi, call, port, label):
        require(("__au_call_result" in abi["records"]) == call, label + ": result catalogue activation")
        require(("__au_call_status" in abi["enums"]) == call, label + ": status catalogue activation")
        require(("__au_port_write_result" in abi["enums"]) == port, label + ": independent Port catalogue activation")

    baseline = None
    for label, (text, active, port_active) in cases.items():
        source.write_text(text)
        result = run([compiler, source, "--abi-facts", facts, "--stack-facts", stack, "-o", assembly])
        require(result.returncode == 0, label + ": " + result.stderr.decode())
        abi = json.loads(facts.read_text())
        check_families(abi, active, port_active, label)
        output = (assembly.read_bytes(), facts.read_bytes(), stack.read_bytes())
        if label == "plain":
            baseline = output
        if label in ("comment", "port-comment"):
            require(output == baseline, "Service spellings in comments changed assembly/ABI/stack/reflection output")
    # Root arrives before two dependencies; the Call reference is in an unused
    # template in the transitive leaf. Import visibility must remain unchanged.
    (work / "middle.au").write_text("export module middle; import leaf; export auto middle()->i64{return leaf();}")
    (work / "leaf.au").write_text(
        "export module leaf; export template<Scalar T> auto unused(T v)->i64{return size_of(builtin::CallResult);}"
        " template<Scalar T> auto identity(T v)->T{return v;} export auto leaf()->i64{return identity<i64>(7);}"
    )
    source.write_text("module catalogue; import middle; auto f()->i64{return middle();}")
    result = run([compiler, "--module-root", work, source, "--abi-facts", facts, "-o", assembly])
    require(result.returncode == 0, "transitive activation: " + result.stderr.decode())
    abi = json.loads(facts.read_text())
    require("__au_call_result" in abi["records"] and "__au_call_status" in abi["enums"], "transitive catalogue missing")
    check_families(abi, True, False, "transitive Call-only")
    # Activate at transitive leaves, including an uninstantiated enum expression.
    # Port-only skips wire operation 5 and kind 3; successful operation lowering
    # proves active row indices are dense without renumbering permanent identities.
    (work / "port_leaf.au").write_text(
        "export module port_leaf; export template<Scalar T> auto unused_port(T v)->bool{"
        "return builtin::PortWriteResult::issued==builtin::PortWriteResult::issued;}"
        " export auto port_leaf(builtin::PortRange& p)->builtin::PortWriteResult{"
        "const u8 b=p.read8(7u64);return p.write8(7u64,b);}"
    )
    (work / "port_middle.au").write_text(
        "export module port_middle; import port_leaf; export auto port_middle()->i64{return 7;}"
    )
    for label, imports, call, port in (
        ("neither", "", False, False),
        ("call-only", "import middle;", True, False),
        ("port-only", "import port_middle;", False, True),
        ("call-port", "import middle; import port_middle;", True, True),
        ("port-call", "import port_middle; import middle;", True, True),
    ):
        source.write_text("module catalogue;" + imports + " auto f()->i64{return 7;}")
        result = run(
            [compiler, "--module-root", work, source, "--abi-facts", facts, "--stack-facts", stack, "-o", assembly]
        )
        require(result.returncode == 0, label + ": " + result.stderr.decode())
        check_families(json.loads(facts.read_text()), call, port, label)
    # A transitive unused enum expression alone must activate Port, independently
    # of an operation receiver type or any instantiated body.
    (work / "port_leaf.au").write_text(
        "export module port_leaf; export template<Scalar T> auto unused_port(T v)->bool{"
        "return builtin::PortWriteResult::issued==builtin::PortWriteResult::issued;}"
        " export auto port_leaf()->i64{return 7;}"
    )
    source.write_text("module catalogue; import port_middle; auto f()->i64{return 7;}")
    result = run([compiler, "--module-root", work, source, "--abi-facts", facts, "-o", assembly])
    require(result.returncode == 0, "transitive Port enum expression: " + result.stderr.decode())
    check_families(json.loads(facts.read_text()), False, True, "transitive Port enum expression")
    print(f"PASS: independent Call/Port catalogue: {len(cases)} source cases and transitive import orders")


def file_count_checks(compiler, work):
    samples = [
        b"",
        b"word",
        b"a b",
        b" a  b ",
        b"a\n",
        b"a\nb",
        bytes(range(9, 14)),
        b"\0\xff x",
        b"x" * 49,
        b"\n" * 49,
        b"x " * 24 + b"x",
    ]
    statements = []
    for index, data in enumerate(samples):
        words = len(re.findall(rb"[^\x09-\x0d ]+", data))
        expected = 1 | (data.count(b"\n") << 8) | (words << 16) | (len(data) << 24)
        statements.append(f"console::FileReader r{index}=console::FileReader();")
        statements.append(f"console::FileStream c{index}=console::FileStream(r{index},false);")
        for byte in data:
            statements.append(f"if (!c{index}.accept(true,{1 | (byte << 8)}u64)) {{ return 1u64; }}")
        statements.append(f"if(!c{index}.accept(true,2u64)) {{ return 2u64; }}")
        statements.append(f"if(c{index}.result()!={expected}u64) {{ return 2u64; }}")
        statements.append(f"if(c{index}.accept(true,65537u64)||c{index}.result()!={expected}u64) {{ return 3u64; }}")
        if len(data) == 49:
            statements.append(f"if(c{index}.accept(true,1u64)||c{index}.result()!={expected}u64) {{ return 4u64; }}")
    statements += [
        "console::FileReader cr=console::FileReader();",
        "console::FileStream crc=console::FileStream(cr,true);",
    ]
    for byte in b"123456789":
        statements.append(f"if(!crc.accept(true,{1 | (byte << 8)}u64)) {{return 15u64;}}")
    statements += [
        "if(!crc.accept(true,2u64)||crc.result()!=975067841281u64) {return 16u64;}",
        "console::FileStream interrupted=console::FileStream(cr,false);",
        "if(!interrupted.accept(true,24833u64)||interrupted.accept(false,2u64)",
        "||interrupted.active()||interrupted.result()!=0u64) {return 17u64;}",
    ]
    # Exercise the actual Call-free reader independently of either consumer.
    statements.extend(
        [
            "console::FileReader reader=console::FileReader();",
            "if(reader.offset()!=0u64||!reader.active()) {return 5u64;}",
            "u64 index=0u64; while(index<49u64) {",
            "if(!reader.accept(true,65281u64)||reader.value()!=255u64) {return 6u64;}",
            "index=index+1u64; if(reader.offset()!=index) {return 7u64;} }",
            "if(!reader.accept(true,2u64)||reader.active()||reader.offset()!=49u64",
            "||reader.status()!=console::FileReadStatus::eof||reader.value()!=0u64) {return 8u64;}",
            "if(reader.accept(true,1u64)||reader.accept(true,3u64)) {return 9u64;}",
            "console::FileReader overflow=console::FileReader(); index=0u64;",
            "while(index<49u64) {if(!overflow.accept(true,1u64)) {return 10u64;} index=index+1u64;}",
            "if(overflow.accept(true,1u64)||overflow.offset()!=49u64||overflow.active()) {return 11u64;}",
            "console::FileReader missing=console::FileReader();",
            "if(!missing.accept(true,3u64)||missing.status()!=console::FileReadStatus::missing",
            "||missing.active()||missing.accept(true,2u64)) {return 12u64;}",
        ]
    )
    for index, value in enumerate((0, 4, 257 + (256 << 8), 65537, 258, 259, 0xFFFFFFFFFFFFFFFF)):
        statements.extend(
            [
                f"console::FileReader bad{index}=console::FileReader();",
                f"if(bad{index}.accept(true,{value}u64)||bad{index}.active()",
                f"||bad{index}.offset()!=0u64||bad{index}.value()!=0u64",
                f"||bad{index}.status()!=console::FileReadStatus::rejected) {{return 13u64;}}",
            ]
        )
    statements.extend(
        [
            "console::FileReader cancelled=console::FileReader();",
            "if(!cancelled.accept(true,257u64)||cancelled.accept(false,2u64)",
            "||cancelled.offset()!=1u64||cancelled.value()!=0u64||cancelled.active()) {return 14u64;}",
        ]
    )
    source = work / "file-counts.au"
    source.write_text(
        "module counts; import console.file_reader; import console.file_stream;\n"
        + "auto count_test()->u64 {"
        + "".join(statements)
        + "return 0u64;}"
    )
    assembly = work / "file-counts.s"
    result = run([compiler, "--module-root", ROOT / "library", source, "-o", assembly])
    require(result.returncode == 0, result.stderr)
    bridge = work / "file-counts-entry.s"
    bridge.write_text(
        ".text\n.globl _start\n_start:\n call count_test\n mov %rax,%rdi\n"
        ' mov $60,%rax\n syscall\n.section .note.GNU-stack,"",@progbits\n'
    )
    for name in ("file-counts", "file-counts-entry"):
        result = run(["as", "--64", work / (name + ".s"), "-o", work / (name + ".o")])
        require(result.returncode == 0, result.stderr)
    executable = work / "file-counts"
    result = run(["ld", "-o", executable, work / "file-counts.o", work / "file-counts-entry.o"])
    require(result.returncode == 0, result.stderr)
    result = run([executable])
    require(result.returncode == 0, "actual streaming counter mismatch")
    print("PASS actual pure file counter: LF/words/bytes, binary bytes, limit and refusal preservation")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if args.artifacts:
        work = args.artifacts.resolve()
        work.mkdir(parents=True)
    else:
        (ROOT / "build").mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="service-group-", dir=ROOT / "build"))
    assembly = work / "group.s"
    file_count_checks(compiler, work)
    catalogue_checks(compiler, work)
    result = run([compiler, ROOT / "tests/compiler/service_group.au", "-o", assembly])
    require(result.returncode == 0, result.stderr.decode())
    text = assembly.read_text()
    symbol = "__au_v_m1_13service_group_n0__d13group_service"
    require(".local " + symbol in text, "group entry must remain private")
    require("__au_runtime_bytes_" not in text, "service group acquired owner runtime")
    assembly.write_text(
        text
        + f"""
.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call {symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
    )
    binary = work / "group"
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/service_group_host.cpp",
            ROOT / "tests/compiler/service_group_abi.S",
            assembly,
            "-o",
            binary,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    for mode in range(4):
        result = run([binary, mode])
        require(result.returncode == 0, f"service group ABI/stop-prefix failed ({mode}): " + result.stderr.decode())
    call_assembly = work / "call.s"
    result = run([compiler, ROOT / "tests/compiler/call_service.au", "-o", call_assembly])
    require(result.returncode == 0, result.stderr.decode())
    call_text = call_assembly.read_text()
    call_symbol = "__au_v_m1_12call_service_n0__d12call_service"
    require(".local " + call_symbol in call_text, "call entry must remain private")
    call_assembly.write_text(
        call_text
        + f"""
.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call {call_symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
    )
    call_binary = work / "call"
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/call_service_host.cpp",
            ROOT / "tests/compiler/service_group_abi.S",
            call_assembly,
            "-o",
            call_binary,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    for mode in range(7):
        result = run([call_binary, mode])
        require(
            result.returncode == (0 if mode < 3 else -signal.SIGILL),
            f"call result ABI/canonicality failed ({mode}): " + result.stderr.decode(),
        )
    pair = "builtin::ConsoleSession& c, builtin::DisplaySession& d"
    helper = f"auto g({pair}, bool flag) -> i64 {{ return 0; }} "
    negative = {
        "duplicate-console": "auto f(builtin::ConsoleSession& c, builtin::ConsoleSession& d) -> i64 { return 0; }",
        "duplicate-display": "auto f(builtin::DisplaySession& c, builtin::DisplaySession& d) -> i64 { return 0; }",
        "late": "auto f(builtin::ConsoleSession& c, i64 n, builtin::DisplaySession& d) -> i64 { return 0; }",
        "third": f"auto f({pair}, builtin::ConsoleSession& again) -> i64 {{ return 0; }}",
        "crossed": helper + f"auto f({pair}) -> i64 {{ return g(d, c, true); }}",
        "duplicate-argument": helper + f"auto f({pair}) -> i64 {{ return g(c, c, true); }}",
        "suspended-first": helper
        + f"auto f({pair}) -> i64 {{ return g(c, d, c.put('Q') == builtin::ConsolePutResult::success); }}",
        "suspended-second": helper + f"auto f({pair}) -> i64 {{ return g(c, d, d.pixel(0u64,0u64,0u8,"
        f"0u8,0u8) == builtin::DisplayPutResult::success); }}",
        "fake": helper + "auto f(i64 c, i64 d) -> i64 { return g(c, d, true); }",
        "second-by-value": "auto f(builtin::ConsoleSession& c, builtin::DisplaySession d) -> i64 { return 0; }",
        "second-const": "auto f(builtin::ConsoleSession& c, const builtin::DisplaySession& d) -> i64 { return 0; }",
        "region": f"auto f({pair}, builtin::ByteRegion r) -> i64 {{ return 0; }}",
        "owner": f"auto f({pair}, builtin::OwnedBytes b) -> i64 {{ return 0; }}",
        "mutable-span": f"auto f({pair}, builtin::span<u8> b) -> i64 {{ return 0; }}",
        "store": f"auto f({pair}) -> i64 {{ builtin::DisplaySession x = d; return 0; }}",
        "return": f"auto f({pair}) -> builtin::DisplaySession {{ return d; }}",
        "reflect": f"auto f({pair}) -> i64 {{ return size_of(builtin::DisplaySession); }}",
        "recursive": f"auto f({pair}) -> i64 {{ return f(c, d); }}",
        "seven": f"auto f({pair}, i64 a, i64 b, i64 e, i64 f, i64 g) -> i64 {{ return 0; }}",
    }
    call = "builtin::CallSession& c"
    negative.update(
        {
            "call-mixed-console": f"auto f({call}, builtin::ConsoleSession& s) -> i64 {{ return 0; }}",
            "call-mixed-event": f"auto f({call}, builtin::IommuEventSession& s) -> i64 {{ return 0; }}",
            "call-mixed-display": f"auto f({call}, builtin::DisplaySession& s) -> i64 {{ return 0; }}",
            "call-duplicate": f"auto f({call}, builtin::CallSession& s) -> i64 {{ return 0; }}",
            "call-owned-values": f"auto f({call}, builtin::OwnedValues<u64> v) -> i64 {{ return 0; }}",
            "call-wrong-signed": f"auto f({call}) -> builtin::CallResult {{ return c.call(1); }}",
            "call-wrong-byte": f"auto f({call}) -> builtin::CallResult {{ return c.call(1u8); }}",
            "call-extra": f"auto f({call}) -> builtin::CallResult {{ "
            "const builtin::CallResult r = c.call(1u64, 2u64); return r; }",
            "call-absent": f"auto f({call}) -> builtin::CallResult {{ "
            "const builtin::CallResult r = c.call(); return r; }",
            "call-value": "auto f(builtin::CallSession c) -> i64 { return 0; }",
            "call-const": "auto f(const builtin::CallSession& c) -> i64 { return 0; }",
            "call-return-capability": f"auto f({call}) -> builtin::CallSession {{ return c; }}",
            "call-forge": "auto f() -> i64 { builtin::CallSession c; return 0; }",
            "call-raw": "auto __au_runtime_call() -> i64 { return 0; }",
        }
    )
    for name, body in negative.items():
        source = work / (name + ".au")
        source.write_text("module rejected; " + body)
        result = run([compiler, source, "-o", work / "rejected.s"])
        require(result.returncode == 1 and result.stderr, "invalid group source was not cleanly rejected: " + name)
        if name in ("call-extra", "call-absent"):
            require(
                result.stderr.count(b"error AU") == 1
                and result.stderr.endswith(b"error AU3001: wrong argument count for method\n"),
                f"{name}: expected method arity diagnostic, got {result.stderr!r}",
            )
    print(f"PASS distinct service group source/ABI: {len(negative)} negative cases; {work}")


if __name__ == "__main__":
    main()

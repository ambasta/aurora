#!/usr/bin/env python3
"""Actual generated scratchpad records, editor, Call codec and presentation.

The host supplies scripted scalar replies and observes bytes. It neither stores
files nor models settlement; these checks do not qualify protected guest use.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import tempfile

from unsigned_oracle import Case, NativeRunner, Rejection

ROOT = Path(__file__).resolve().parents[2]
PROMPT = b"aurora> "
INVALID = b"\r\nInvalid command. Type help; put accepts at most 49 printable ASCII bytes.\r\n" + PROMPT
REJECTED = b"\r\nLine rejected: too long, non-ASCII/control byte, or UART error.\r\n" + PROMPT
MAXIMUM = bytes(32 + (index * 37) % 95 for index in range(49))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(command, **kwargs):
    return subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, timeout=120, **kwargs)


def source_cases():
    imports = ("console.scratchpad", "console.scratchpad_parse", "console.line")
    sizes = """
        static_assert(size_of(console::ScratchpadCommand) == 80);
        static_assert(size_of(console::ScratchpadResult) == 80);
        static_assert(size_of(console::ScratchpadSubmission) == 96);
        static_assert(size_of(console::ScratchpadResponse) == 80);
    """
    for raw, payload in [
        (b"get", None),
        (b"put", b""),
        (b"put ", b""),
        (b"put x", b"x"),
        (b"put  a  ", b" a  "),
        (b"put " + MAXIMUM, MAXIMUM),
        (b"put " + b"x" * 50, False),
        (b" get", False),
        (b"get ", False),
        (b"GET", False),
        (b"putx", False),
        (b"put\tvalue", False),
        (b"help", False),
        (b"status", False),
        (b"exit", False),
        (b"", False),
        (b"x" * 64, False),
        (b"x" * 65 + b"\b" * 65 + b"get", False),
    ]:
        body = sizes + "console::Line64 line = console::Line64(false);\n"
        body += "".join(f"line.consume({byte}u8);\n" for byte in raw + b"\n")
        body += "const console::ScratchpadCommand command = console::parse_scratchpad_command(line);\n"
        if payload is False:
            body += "if (command.valid()) { return 0u64; }\n"
        else:
            op = "get" if payload is None else "put"
            expected = payload or b""
            body += f"if (!command.valid() || command.size() != {len(expected)}u64"
            body += f" || command.selection() != console::ScratchpadOperation::{op}) {{ return 0u64; }}\n"
            for index, byte in enumerate(expected):
                body += f"if (command.at({index}u64) != {byte}u8) {{ return 0u64; }}\n"
            body += "if (command.at(63u64) != 0u8) { return 0u64; }\n"
        yield Case(f"exact grammar {raw!r}", body + "return 42u64;", 42, imports=imports)
    body = (
        sizes
        + """
        console::ScratchpadCommand put = console::ScratchpadCommand(console::ScratchpadOperation::put, 1u64);
        if (put.valid() || put.set(1u64, 'x') || put.set(0u64, 31u8) || !put.set(0u64, 'x') || !put.valid()) {
            return 0u64;
        }
        const console::ScratchpadCommand get = console::ScratchpadCommand(console::ScratchpadOperation::get, 0u64);
        const console::ScratchpadSubmission exit = console::ScratchpadSubmission(
            get, console::ScratchpadInputAction::requested_exit, 1u64);
        const console::ScratchpadSubmission bad_exit = console::ScratchpadSubmission(
            put, console::ScratchpadInputAction::requested_exit, 1u64);
        const console::ScratchpadSubmission bad_carry = console::ScratchpadSubmission(
            get, console::ScratchpadInputAction::command, 2u64);
        if (!exit.valid() || bad_exit.valid() || bad_carry.valid()) { return 0u64; }
    """
    )
    for kind in ("incomplete", "content", "missing", "saved", "refused"):
        body += f"const console::ScratchpadResult result_{kind} = "
        body += f"console::ScratchpadResult(console::ScratchpadResultKind::{kind});\n"
        body += f"if (!result_{kind}.valid() || result_{kind}.size() != 0u64) {{ return 0u64; }}\n"
    for kind in (
        "ready",
        "content",
        "missing",
        "saved",
        "rejected",
        "aborted",
        "read_failed",
        "committed_caller_failed",
        "indeterminate_reset",
        "reset",
        "unavailable",
        "limit",
    ):
        body += f"const console::ScratchpadResponse response_{kind} = "
        body += f"console::ScratchpadResponse(console::ScratchpadResponseKind::{kind});\n"
        body += f"if (!response_{kind}.valid() || response_{kind}.size() != 0u64) {{ return 0u64; }}\n"
    body += """
        console::ScratchpadResult result = console::ScratchpadResult(console::ScratchpadResultKind::content);
        console::ScratchpadResponse response = console::ScratchpadResponse(console::ScratchpadResponseKind::content);
        u64 index = 0u64;
        while (index < 49u64) {
            if (!result.append(' ') || !response.append('~')) { return 0u64; }
            index = index + 1u64;
        }
        if (!result.valid() || !response.valid() || result.append('x') || response.append('x')) { return 0u64; }
        return 42u64;
    """
    yield Case("all canonical copied shapes and bounded constructors", body, 42, imports=imports)


HOSTS = {}


def compile_bridge(compiler, work, mode, source, entry, result_offset):
    assembly, facts = work / f"{mode}.s", work / f"{mode}.json"
    result = run(
        [
            compiler,
            "--module-root",
            ROOT / "library",
            "--module-root",
            ROOT / "kernel/policies",
            source,
            "-o",
            assembly,
            "--abi-facts",
            facts,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    functions = json.loads(facts.read_text())["functions"]
    matches = [(name, row) for name, row in functions.items() if row.get("source_name") == entry]
    require(len(matches) == 1, f"ambiguous source entry {entry}: {matches}")
    name, row = matches[0]
    require(row["parameter_bytes"] == (24 if mode == "input" else 96), "copied argument width drift")
    if result_offset is not None:
        require(row["result"]["kind"] == "class", "copied result kind drift")
    bridge = "\n.text\n.globl __au_runtime_group_entry\n__au_runtime_group_entry:\n"
    bridge += "    pushq %rbp\n    movq %rsp, %rbp\n    movq %rdi, %r11\n"
    if result_offset is not None:
        bridge += f"    leaq {result_offset}(%rdi), %r10\n"
    bridge += f"    call {name}\n"
    if result_offset is not None:
        bridge += "    movq $42, %rax\n"
    bridge += "    leave\n    ret\n"
    combined = work / f"{mode}-bridge.s"
    combined.write_text(assembly.read_text() + bridge)
    binary = work / mode
    result = run([*shlex.split(os.environ.get("CXX", "g++")), combined, HOSTS[mode], "-o", binary])
    require(result.returncode == 0, result.stderr.decode())
    return binary


def record(result, expected, count, kind):
    require(result.returncode == 0, f"generated adapter failed: {result.returncode}: {result.stderr!r}")
    match = re.search(rb"record=(\d+),(\d+),([0-9a-f]{128})\n", result.stderr)
    require(match is not None, f"missing complete copied record: {result.stderr!r}")
    require((int(match[1]), int(match[2])) == (count, kind), f"wrong record shape: {result.stderr!r}")
    require(bytes.fromhex(match[3].decode()) == expected + bytes(64 - len(expected)), "noncanonical bytes or suffix")


def client_cases(binary):
    def execute(operation, payload, steps, expected=b"", kind=0, mutation=0):
        data = "".join(f"{request} {status} {value}\n" for request, status, value in steps).encode()
        result = run([binary, operation, payload.decode(), mutation], input=data)
        record(result, expected, len(expected), kind)
        require(f"calls={len(steps)}\n".encode() in result.stderr, "unexpected retry/request count")
        require(not result.stdout, "Call client emitted Console bytes")

    for payload in (b"", b"x", b" first ", b" other ", MAXIMUM):
        writes = [(3 | (len(payload) << 8), 0, 1)]
        writes += [(4 | (index << 8) | (byte << 16), 0, 1) for index, byte in enumerate(payload)]
        writes += [(5, 0, 5)]
        execute(1, payload, writes, kind=3)
        reads = [(1, 0, 1)] + [(2 | (index << 8), 0, 2 | (byte << 8)) for index, byte in enumerate(payload)]
        reads += [(2 | (len(payload) << 8), 0, 3)]
        execute(0, b"", reads, payload, 1)
        for index in range(len(writes)):
            request = writes[index][0]
            for status, value, kind in ((1, 0, 0), (2, 0, 0), (0, 6, 4), (0, 7, 0)):
                execute(1, payload, writes[:index] + [(request, status, value)], kind=kind)
        for index in range(len(reads)):
            request = reads[index][0]
            for status, value, kind in ((1, 0, 0), (2, 0, 0), (0, 6, 4), (0, 7, 0)):
                execute(0, b"", reads[:index] + [(request, status, value)], kind=kind)
    execute(0, b"", [(1, 0, 1), (2, 0, 4)], kind=2)
    for malformed in (0, 1, 5, 7, 2, 2 | (31 << 8), 2 | (127 << 8), 2 | (255 << 8), 2 | (1 << 16), 3 | (1 << 32)):
        execute(0, b"", [(1, 0, 1), (2, 0, malformed)])
    execute(0, b"", [(1, 0, 1), (2, 0, 2 | (65 << 8)), (258, 0, 4)])
    execute(0, b"", [(1, 0, 1)] + [(2 | (i << 8), 0, 2 | (65 << 8)) for i in range(50)])
    for operation, payload, mutation in ((0, b"x", 0), (1, b"x" * 50, 0), (1, b"x", 1), (1, b"x", 2), (1, b"", 3)):
        execute(operation, payload, [], mutation=mutation)
    # Noncanonical host Call status/value combinations must trap, not turn into
    # an outcome enum. The original native service adapter covers exact trap PCs.
    for status, value in ((3, 0), (1 << 32, 0), (1, 1), (2, 1)):
        result = run([binary, 0, ""], input=f"1 {status} {value}\n".encode())
        require(result.returncode == -signal.SIGILL and b"record=" not in result.stderr, "malformed transport accepted")


def input_cases(binary):
    def execute(raw, *, carry=0, limit=(1 << 64) - 1, samples=None):
        samples = samples if samples is not None else [(1, byte, 0) for byte in raw]
        data = "".join(f"{present} {byte} {damage}\n" for present, byte, damage in samples).encode()
        return run([binary, carry, limit], input=data)

    for raw, payload, kind in (
        (b"get\n", b"", 0),
        (b"put\n", b"", 1),
        (b"put \n", b"", 1),
        (b"put  x \r", b" x ", 1),
        (b"put " + MAXIMUM + b"\n", MAXIMUM, 1),
        (b"put ab\bc\x7fd\n", b"ad", 1),
    ):
        result = execute(raw)
        record(result, payload, len(payload), kind)
        require(b"action=0" in result.stderr and result.stdout.endswith(b"\r\n"), "command before delimiter")
        expected_carry = 1 if raw.endswith(b"\r") else 0
        require(f"carry={expected_carry}".encode() in result.stderr, "lost submitted CR carry")
    result = execute(b"\nget\n", carry=1)
    record(result, b"", 0, 0)
    require(result.stdout == b"get\r\n", "copied CRLF carry submitted an extra line")
    for invalid in (
        b" get",
        b"get x",
        b"get ",
        b"putx",
        b"Put x",
        b"exit ",
        b"help x",
        b"status x",
        b"put " + b"x" * 50,
        b"x" * 64,
    ):
        result = execute(invalid + b"\nget\n")
        record(result, b"", 0, 0)
        require(INVALID in result.stdout, f"rejected grammar dispatched: {invalid!r}")
    for invalid in (b"x" * 65 + b"\b" * 65 + b"put x", b"put x\x00", b"put x\xff", b"put x\x1b"):
        result = execute(invalid + b"\nget\n")
        record(result, b"", 0, 0)
        require(REJECTED in result.stdout, "damaged/overflow line was rehabilitated")
    for damage in ((0, 0, 1), (1, 10, 1), (1, 13, 1), (1, ord("x"), 1)):
        samples = [(1, byte, 0) for byte in b"put new"] + [damage]
        samples += [(1, byte, 0) for byte in b"\nget\n"]
        result = execute(b"", samples=samples)
        record(result, b"", 0, 0)
        require(REJECTED in result.stdout, "UART damage admitted a command")
    result = execute(b"help\r\nstatus\n\nget\n")
    record(result, b"", 0, 0)
    require(result.stdout.count(b"put [text]") == 1 and b"command ceiling=64" in result.stdout, "local help/status")
    require(b"upper" not in result.stdout and b"note" not in result.stdout, "legacy grammar leaked")
    result = execute(b"exit\r")
    record(result, b"", 0, 0)
    require(b"action=1 carry=1" in result.stderr, "exit/carry not canonical")
    for raw in (b"put actual\n", b"get\n", b"help\nget\n", b"status\nget\n", b"exit\n", b"x\bget\n"):
        complete = execute(raw)
        for limit in range(len(complete.stdout)):
            result = execute(raw, limit=limit)
            record(result, b"", 0, 0)
            require(b"action=2" in result.stderr, "output failure dispatched or resumed input")
            require(result.stdout == complete.stdout[:limit], "output bytes replayed after failure")
            require(f"puts={limit + 1}".encode() in result.stderr, "put attempted after first failure")


def output_cases(binary):
    outputs = {
        0: b"AURORA_RAM_SCRATCHPAD_READY: 49-byte session scratchpad; "
        b"all data is lost on service reset or session exit.\r\n" + PROMPT,
        2: b"missing\r\n" + PROMPT,
        3: b"saved\r\n" + PROMPT,
        4: b"rejected\r\n" + PROMPT,
        5: b"aborted: previous data retained\r\n" + PROMPT,
        6: b"read failed: output discarded\r\n" + PROMPT,
        7: b"committed; caller failed: do not retry automatically\r\n" + PROMPT,
        8: b"commit indeterminate; service reset: all data lost; do not retry automatically\r\n" + PROMPT,
        9: b"service reset: all data lost\r\n" + PROMPT,
        10: b"scratchpad unavailable; session closed\r\n",
        11: b"command limit reached; session closed\r\n",
    }
    cases = [(kind, b"", expected) for kind, expected in outputs.items()]
    cases += [(1, payload, b"data: " + payload + b"\r\n" + PROMPT) for payload in (b"", b"x", b" a  ", MAXIMUM)]
    for kind, payload, expected in cases:
        result = run([binary, kind, payload.decode()])
        require(
            result.returncode == 0 and result.stdout == expected and b"success=1" in result.stderr, "output transcript"
        )
        for limit in range(len(expected)):
            result = run([binary, kind, payload.decode(), limit])
            require(
                result.returncode == 0 and result.stdout == expected[:limit], "output byte replay or prefix mismatch"
            )
            require(f"success=0 puts={limit + 1} nexts=0".encode() in result.stderr, "output continued after failure")
    for kind, payload, mutation in (
        (1, b"x" * 50, 0),
        (1, b"x", 1),
        (1, b"x", 2),
        (1, b"", 3),
        (0, b"x", 0),
        (2, b"x", 0),
        (3, b"x", 0),
    ):
        result = run([binary, kind, payload.decode(), (1 << 64) - 1, mutation])
        require(
            result.returncode == 0 and not result.stdout and b"success=0 puts=0" in result.stderr,
            "malformed copied response produced partial output",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    for mode in ("client", "input", "output"):
        parser.add_argument(f"--{mode}-host", type=Path, required=True, help="Meson-built host library")
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    for mode in ("client", "input", "output"):
        HOSTS[mode] = getattr(args, f"{mode}_host").resolve(strict=True)
    work = Path(tempfile.mkdtemp(prefix="scratchpad-source-"))
    print(f"artifacts={work}", flush=True)
    runner = NativeRunner(work, compiler, 30)
    cases = list(source_cases())
    runner.cases(cases)
    for kind, field in (
        ("Command", "bytes[0]"),
        ("Command", "count"),
        ("Result", "kind"),
        ("Submission", "action"),
        ("Response", "bytes[0]"),
    ):
        runner.rejection(
            Rejection(
                f"private {kind}.{field}",
                "module private_record; import console.scratchpad; "
                f"auto invalid(console::Scratchpad{kind} value) -> u64 {{ return u64(value.{field}); }}",
            )
        )
    client = compile_bridge(
        compiler, work, "client", ROOT / "examples/kernel-ram-scratchpad-client.au", "aurora_user_main", 96
    )
    client_cases(client)
    supervisor = ROOT / "examples/kernel-ram-scratchpad-console.au"
    input_cases(compile_bridge(compiler, work, "input", supervisor, "read_scratchpad_input", 24))
    output_cases(compile_bridge(compiler, work, "output", supervisor, "present_scratchpad_response", None))
    print(
        f"PASS scratchpad: {len(cases)} generated record/parser cases; client, editor and output transcripts",
        flush=True,
    )
    shutil.rmtree(work)


if __name__ == "__main__":
    main()

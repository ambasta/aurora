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
INVALID = b"\r\nInvalid command. Type help; put/append accept at most 49 printable ASCII bytes.\r\n" + PROMPT
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
        (b"crc", None),
        (b"crc ", False),
        (b"crc x", False),
        (b"CRC", False),
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
        (b"append", b""),
        (b"append ", b""),
        (b"append  x ", b" x "),
        (b"append " + MAXIMUM, MAXIMUM),
        (b"append " + b"x" * 50, False),
        (b"appendx", False),
        (b"append\tvalue", False),
        (b"Append x", False),
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
            op = (
                ("crc" if raw == b"crc" else "get")
                if payload is None
                else "append"
                if raw.startswith(b"append")
                else "put"
            )
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
        console::ScratchpadResult digest = console::ScratchpadResult(console::ScratchpadResultKind::checksum);
        console::ScratchpadResponse shown = console::ScratchpadResponse(console::ScratchpadResponseKind::checksum);
        if (digest.valid() || shown.valid() || digest.append('g') || shown.append('A')) { return 0u64; }
        index = 0u64;
        while (index < 8u64) {
            if (!digest.append('a') || !shown.append('0')) { return 0u64; }
            index = index + 1u64;
        }
        if (!digest.valid() || !shown.valid() || digest.append('0') || shown.append('f')) { return 0u64; }
        return 42u64;
    """
    yield Case("all canonical copied shapes and bounded constructors", body, 42, imports=imports)


def compile_bridges(compiler, work, host):
    """Compile each source once; the host selects its six entries at runtime."""
    sources = (
        ("scratchpad-client", "kernel-ram-scratchpad-client.au", ((0, "aurora_user_main", 96, 96),)),
        ("namespace-client", "kernel-namespace-client.au", ((3, "aurora_user_main", 176, 176),)),
        (
            "supervisor",
            "kernel-ram-scratchpad-console.au",
            (
                (1, "read_scratchpad_input", 24, 24),
                (2, "present_scratchpad_response", 96, None),
                (4, "read_namespace_input", 24, 24),
                (5, "present_namespace_response", 192, None),
            ),
        ),
    )
    objects = []
    for label, source, entries in sources:
        assembly, facts = work / f"{label}.s", work / f"{label}.json"
        result = run(
            [
                compiler,
                "--local-symbols",
                "--module-root",
                ROOT / "library",
                "--module-root",
                ROOT / "kernel/policies",
                ROOT / "examples" / source,
                "-o",
                assembly,
                "--abi-facts",
                facts,
            ]
        )
        require(result.returncode == 0, result.stderr.decode())
        functions = json.loads(facts.read_text())["functions"]
        bridges = []
        for selector, entry, argument_bytes, result_offset in entries:
            matches = [(name, row) for name, row in functions.items() if row.get("source_name") == entry]
            require(len(matches) == 1, f"ambiguous source entry {entry}: {matches}")
            name, row = matches[0]
            require(row["parameter_bytes"] == argument_bytes, "copied argument width drift")
            if result_offset is not None:
                require(row["result"]["kind"] == "class", "copied result kind drift")
            symbol = f"scratchpad_entry_{selector}"
            bridge = f"\n.text\n.globl {symbol}\n.hidden {symbol}\n{symbol}:\n"
            bridge += "    pushq %rbp\n    movq %rsp, %rbp\n    movq %rdi, %r11\n"
            if result_offset is not None:
                bridge += f"    leaq {result_offset}(%rdi), %r10\n"
            bridge += f"    call {name}\n"
            if result_offset is not None:
                bridge += "    movq $42, %rax\n"
            bridges.append(bridge + "    leave\n    ret\n")
        with assembly.open("a") as output:
            output.write("".join(bridges))
            if label == "supervisor":
                # The existing ABI envelope forwards the runtime selector in RSI.
                output.write(
                    ".text\n.globl __au_runtime_group_entry\n__au_runtime_group_entry:\n"
                    + "".join(f"    cmpq ${i}, %rsi\n    je scratchpad_entry_{i}\n" for i in range(6))
                    + "    ud2\n"
                )
        objects.append(work / f"{label}.o")
        result = run(["as", "--64", assembly, "-o", objects[-1]])
        require(result.returncode == 0, result.stderr.decode())
    binary = work / "scratchpad"
    result = run([*shlex.split(os.environ.get("CXX", "g++")), *objects, host, "-o", binary])
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
        result = run([*binary, operation, payload.decode(), mutation], input=data)
        record(result, expected, len(expected), kind)
        require(f"calls={len(steps)}\n".encode() in result.stderr, "unexpected retry/request count")
        require(not result.stdout, "Call client emitted Console bytes")

    for payload in (b"", b"x", b" first ", b" other ", MAXIMUM):
        writes = [(3 | (len(payload) << 8), 0, 1)]
        writes += [(4 | (index << 8) | (byte << 16), 0, 1) for index, byte in enumerate(payload)]
        writes += [(5, 0, 5)]
        execute(1, payload, writes, kind=3)
        appends = [(8 | (len(payload) << 8), 0, 1)] + writes[1:]
        execute(2, payload, appends, kind=3)
        for index in range(len(appends)):
            request = appends[index][0]
            for status, value, kind in ((1, 0, 0), (2, 0, 0), (0, 6, 4), (0, 7, 0)):
                execute(2, payload, appends[:index] + [(request, status, value)], kind=kind)
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
                execute(3, b"", reads[:index] + [(request, status, value)], kind=kind)
    # CRC32C Castagnoli known vectors, independently checked with x86 CRC32.
    for payload, digest in (
        (b"", b"00000000"),
        (b"1234", b"f63af4ee"),
        (b"123456789", b"e3069283"),
        (b"x" * 49, b"e0de1ddc"),
    ):
        reads = [(1, 0, 1)] + [(2 | (i << 8), 0, 2 | (byte << 8)) for i, byte in enumerate(payload)]
        execute(3, b"", reads + [(2 | (len(payload) << 8), 0, 3)], digest, 5)
    execute(3, b"", [(1, 0, 1), (2, 0, 4)], kind=2)
    execute(3, b"x", [])
    execute(0, b"", [(1, 0, 1), (2, 0, 4)], kind=2)
    for malformed in (0, 1, 5, 7, 2, 2 | (31 << 8), 2 | (127 << 8), 2 | (255 << 8), 2 | (1 << 16), 3 | (1 << 32)):
        execute(0, b"", [(1, 0, 1), (2, 0, malformed)])
        execute(3, b"", [(1, 0, 1), (2, 0, malformed)])
    execute(0, b"", [(1, 0, 1), (2, 0, 2 | (65 << 8)), (258, 0, 4)])
    execute(0, b"", [(1, 0, 1)] + [(2 | (i << 8), 0, 2 | (65 << 8)) for i in range(50)])
    execute(3, b"", [(1, 0, 1), (2, 0, 2 | (65 << 8)), (258, 0, 4)])
    execute(3, b"", [(1, 0, 1)] + [(2 | (i << 8), 0, 2 | (65 << 8)) for i in range(50)])
    for operation, payload, mutation in ((0, b"x", 0), (1, b"x" * 50, 0), (1, b"x", 1), (1, b"x", 2), (1, b"", 3)):
        execute(operation, payload, [], mutation=mutation)
    for payload, mutation in ((b"x" * 50, 0), (b"x", 1), (b"x", 2), (b"", 3)):
        execute(2, payload, [], mutation=mutation)
    # Noncanonical host Call status/value combinations must trap, not turn into
    # an outcome enum. The original native service adapter covers exact trap PCs.
    for status, value in ((3, 0), (1 << 32, 0), (1, 1), (2, 1)):
        result = run([*binary, 0, ""], input=f"1 {status} {value}\n".encode())
        require(result.returncode == -signal.SIGILL and b"record=" not in result.stderr, "malformed transport accepted")


def input_cases(binary):
    def execute(raw, *, carry=0, limit=(1 << 64) - 1, samples=None):
        samples = samples if samples is not None else [(1, byte, 0) for byte in raw]
        data = "".join(f"{present} {byte} {damage}\n" for present, byte, damage in samples).encode()
        return run([*binary, carry, limit], input=data)

    for raw, payload, kind in (
        (b"get\n", b"", 0),
        (b"crc\n", b"", 3),
        (b"put\n", b"", 1),
        (b"put \n", b"", 1),
        (b"put  x \r", b" x ", 1),
        (b"put " + MAXIMUM + b"\n", MAXIMUM, 1),
        (b"put ab\bc\x7fd\n", b"ad", 1),
        (b"append\n", b"", 2),
        (b"append \n", b"", 2),
        (b"append  x \r", b" x ", 2),
        (b"append " + MAXIMUM + b"\n", MAXIMUM, 2),
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
        b"crc x",
        b"CRC",
        b"get ",
        b"putx",
        b"appendx",
        b"append " + b"x" * 50,
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
    require(
        result.stdout.count(b"put [text]") == 1
        and result.stdout.count(b"append [text]") == 1
        and b"command ceiling=64" in result.stdout,
        "local help/status",
    )
    require(b"upper" not in result.stdout and b"note" not in result.stdout, "legacy grammar leaked")
    result = execute(b"exit\r")
    record(result, b"", 0, 0)
    require(b"action=1 carry=1" in result.stderr, "exit/carry not canonical")
    for raw in (
        b"append actual\n",
        b"put actual\n",
        b"get\n",
        b"crc\n",
        b"help\nget\n",
        b"status\nget\n",
        b"exit\n",
        b"x\bget\n",
    ):
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
    cases += [(12, b"e3069283", b"crc32c: e3069283\r\n" + PROMPT)]
    for kind, payload, expected in cases:
        result = run([*binary, kind, payload.decode()])
        require(
            result.returncode == 0 and result.stdout == expected and b"success=1" in result.stderr, "output transcript"
        )
        for limit in range(len(expected)):
            result = run([*binary, kind, payload.decode(), limit])
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
        (12, b"", 0),
        (12, b"0000000", 0),
        (12, b"000000000", 0),
        (12, b"E3069283", 0),
        (12, b"g3069283", 0),
        (12, b"e3069283", 1),
    ):
        result = run([*binary, kind, payload.decode(), (1 << 64) - 1, mutation])
        require(
            result.returncode == 0 and not result.stdout and b"success=0 puts=0" in result.stderr,
            "malformed copied response produced partial output",
        )


# Scripted scalar transcripts exercise the actual compiled codec, not a host
# namespace implementation. The owner semantics remain in namespace_protocol.cases.
def namespace_client_cases(binary):
    def word(tag, cursor=0, count=0, payload=0):
        return tag | (cursor << 8) | (count << 16) | (payload << 24)

    def execute(operation, name, value, steps, expected=b"", event=0, revision=0, mutation=0):
        data = "".join(f"{request} {status} {reply}\n" for request, status, reply in steps).encode()
        result = run([*binary, "namespace", operation, name, value, mutation], input=data)
        record(result, expected, len(expected), event)
        require(f"revision={revision} calls={len(steps)}\n".encode() in result.stderr, "namespace revision/retry drift")
        require(not result.stdout, "namespace Call client emitted Console bytes")

    # One-byte name/value, then full-width two-word revision and terminal receipt.
    revision = 0x80000000FFFFFFFF
    revision_steps = [(6, 0, word(8, 0, 4, 0xFFFFFFFF)), (1030, 0, word(8, 4, 4, 0x80000000))]
    write = [(65794, 0, 1), (1627455491, 0, 1), (2013331460, 0, 1), (5, 0, 1)] + revision_steps
    write += [(word(7, 0, 4, 0xFFFFFFFF), 0, 1), (word(7, 4, 4, 0x80000000), 0, 1), (8, 0, 5)]
    execute(1, "a", "x", write, event=1, revision=revision + 1)
    empty_write = [(258, 0, 1), (1627455491, 0, 1), (5, 0, 1)] + write[4:]
    execute(1, "a", "", empty_write, event=1, revision=revision + 1)
    read = [(257, 0, 1), (1627455491, 0, 1), (5, 0, 1)] + revision_steps
    execute(0, "a", "", read + [(9, 0, 3)], event=2, revision=revision)
    execute(0, "a", "", read + [(9, 0, 4)], event=5, revision=revision)
    execute(0, "a", "", read + [(9, 0, word(2, 0, 1, ord("x"))), (265, 0, 3)], b"x", 2, revision)
    chunks = [
        (word(9, i), 0, word(2, i, len(MAXIMUM[i : i + 4]), int.from_bytes(MAXIMUM[i : i + 4], "little")))
        for i in range(0, 49, 4)
    ]
    execute(0, "a", "", read + chunks + [(word(9, 49), 0, 3)], MAXIMUM, 2, revision)
    for operation, value, script in ((1, "x", write), (0, "", read + chunks + [(word(9, 49), 0, 3)])):
        for index, (request, _, _) in enumerate(script):
            for status, reply, event in ((1, 0, 0), (2, 0, 0), (0, 1542, 6), (0, 1798, 7), (0, 2054, 8)):
                execute(operation, "a", value, script[:index] + [(request, status, reply)], event=event)
    for malformed in (
        0,
        1,
        5,
        word(2, 1, 1, 65),
        word(2, 0, 0),
        word(2, 0, 5),
        word(2, 0, 1, 31),
        word(2, 0, 1, 127),
        word(2, 0, 1, 0x4141),
        word(2, 0, 1, 65) | (1 << 56),
        3 | (1 << 32),
    ):
        execute(0, "a", "", read + [(9, 0, malformed)])
    # No prefix survives a late malformed reply, including DATA after a short
    # chunk or MISSING after any data. No successful result may carry revision 0.
    for reply in (word(2, 1, 1, 66), 4):
        execute(0, "a", "", read + [(9, 0, word(2, 0, 1, 65)), (265, 0, reply)])
    for reply in (word(8, 0, 3, 1), word(8, 4, 4, 1), word(8, 0, 4, 1) | (1 << 56)):
        execute(0, "a", "", read[:3] + [(6, 0, reply)])
    execute(0, "a", "", read[:3] + [(6, 0, word(8, 0, 4)), (1030, 0, word(8, 4, 4))])
    execute(1, "a", "x", write[:4] + [(6, 0, word(8, 0, 4, 0xFFFFFFFF)), (1030, 0, word(8, 4, 4, 0xFFFFFFFF))])
    for operation, name, value, mutation in (
        (0, "a", "x", 0),
        (1, "", "x", 0),
        (1, ".", "x", 0),
        (1, "a/b", "x", 0),
        (1, "abcdefghi", "x", 0),
        (1, "a", "x" * 50, 0),
        (1, "a", "\x1f", 0),
        (1, "a", "", 3),
        (1, "a", "", 4),
    ):
        execute(operation, name, value, [], mutation=mutation)
    for status, reply in ((3, 0), (1 << 32, 0), (1, 1), (2, 1)):
        result = run([*binary, "namespace", 0, "a", ""], input=f"257 {status} {reply}\n".encode())
        require(
            result.returncode == -signal.SIGILL and b"record=" not in result.stderr,
            "namespace malformed transport accepted",
        )


def namespace_input_cases(binary):
    invalid = b"\r\nInvalid command, name or content. Type help; note is reserved.\r\n" + PROMPT

    def execute(raw, *, carry=0, limit=(1 << 64) - 1, samples=None):
        samples = samples if samples is not None else [(1, byte, 0) for byte in raw]
        data = "".join(f"{present} {byte} {damage}\n" for present, byte, damage in samples).encode()
        return run([*binary, "namespace", carry, limit], input=data)

    def copied(result, name=b"", value=b"", operation=0, action=0, carry=0):
        require(result.returncode == 0, f"namespace editor failed: {result.stderr!r}")
        for label, expected in (("name", name), ("value", value)):
            match = re.search(label.encode() + rb"=(\d+),([0-9a-f]{128})\n", result.stderr)
            require(match is not None and int(match[1]) == len(expected), "namespace copied input width")
            require(
                bytes.fromhex(match[2].decode()) == expected + bytes(64 - len(expected)),
                "namespace copied input zero suffix",
            )
        require(
            f"operation={operation} action={action} carry={carry}".encode() in result.stderr,
            "namespace copied input discriminants",
        )

    for raw, name, value, operation in (
        (b"cat a\n", b"a", b"", 0),
        (b"write a \n", b"a", b"", 1),
        (b"write a  x \r", b"a", b" x ", 1),
        (b"write abcdefgh " + MAXIMUM + b"\n", b"abcdefgh", MAXIMUM, 1),
        (b"write a ab\bc\x7fd\n", b"a", b"ad", 1),
    ):
        result = execute(raw)
        copied(result, name, value, operation, carry=int(raw.endswith(b"\r")))
        require(result.stdout.endswith(b"\r\n"), "namespace command dispatched before delimiter")
    result = execute(b"\ncat a\n", carry=1)
    copied(result, b"a")
    require(result.stdout == b"cat a\r\n", "namespace copied CRLF submitted extra line")
    for raw in (
        b"write a",
        b"write a " + b"x" * 50,
        b"cat",
        b"cat a ",
        b"cat note",
        b"write note x",
        b"cat .",
        b"cat ..",
        b"cat a/b",
        b"cat abcdefghi",
        b"list",
        b"append a x",
        b"remove a",
    ):
        result = execute(raw + b"\ncat a\n")
        copied(result, b"a")
        require(invalid in result.stdout, "namespace invalid grammar dispatched")
    for raw in (b"x" * 65 + b"\b" * 65, b"write a x\x00", b"write a x\xff", b"write a x\x1b"):
        result = execute(raw + b"\ncat a\n")
        copied(result, b"a")
        require(REJECTED in result.stdout, "namespace overflow/control line rehabilitated")
    result = execute(
        b"", samples=[(1, byte, 0) for byte in b"write a x"] + [(0, 0, 1)] + [(1, byte, 0) for byte in b"\ncat a\n"]
    )
    copied(result, b"a")
    require(REJECTED in result.stdout, "namespace UART damage dispatched")
    result = execute(b"help\r\nstatus\ncat a\n")
    copied(result, b"a")
    require(
        result.stdout.count(b"write NAME TEXT") == 1
        and b"capacity=4 files" in result.stdout
        and b"put [text]" not in result.stdout,
        "namespace closed help/status",
    )
    copied(execute(b"exit\r"), action=1, carry=1)
    for raw in (b"write a x\n", b"cat a\n", b"exit\n", b"help\ncat a\n"):
        complete = execute(raw)
        for limit in range(len(complete.stdout)):
            result = execute(raw, limit=limit)
            copied(result, action=2)
            require(result.stdout == complete.stdout[:limit], "namespace editor output replay")
            require(f"puts={limit + 1}".encode() in result.stderr, "namespace input resumed after output failure")


def namespace_output_cases(binary):
    maximum = (1 << 64) - 1

    def execute(kind, name="", submitted=0, event=0, revision=0, value=b"", limit=maximum, mutation=0):
        return run([*binary, "namespace", kind, name, submitted, event, revision, value.decode(), limit, mutation])

    outcomes = {
        0: b"AURORA_NAMESPACE_READY: four named RAM files; all data is lost on owner reset or session exit.\r\n"
        + PROMPT,
        2: b"aborted: previous data retained\r\n" + PROMPT,
        3: b"read failed: output discarded\r\n" + PROMPT,
        4: b"committed; caller failed: do not retry automatically\r\n" + PROMPT,
        5: b"commit indeterminate; owner reset: all data lost; do not retry automatically\r\n" + PROMPT,
        6: b"owner reset: all data lost\r\n" + PROMPT,
        7: b"namespace unavailable; session closed\r\n",
        8: b"command limit reached; session closed\r\n",
    }
    cases = [((kind, "", 0, 0, 0, b""), expected) for kind, expected in outcomes.items()]
    cases += [
        (
            (1, "a", length, 1, 0x8000000100000000, b""),
            f"wrote a: {length} byte{'s' if length != 1 else ''}\r\n".encode() + PROMPT,
        )
        for length in (0, 1, 49)
    ]
    cases += [((1, "a", 0, 2, maximum, value), value + b"\r\n" + PROMPT) for value in (b"", b" x ", MAXIMUM)]
    cases += [
        ((1, "a", 0, event, revision, b""), reply + b"\r\n" + PROMPT)
        for event, revision, reply in (
            (5, maximum, b"files: not found (RAM-only)."),
            (6, 0, b"files: invalid name or content."),
            (7, 0, b"files: full (4 files)."),
            (8, 0, b"files: note is reserved."),
        )
    ]
    for arguments, expected in cases:
        result = execute(*arguments)
        require(
            result.returncode == 0 and result.stdout == expected and b"success=1" in result.stderr,
            "namespace exact response transcript",
        )
        for limit in range(len(expected)):
            result = execute(*arguments, limit=limit)
            require(result.returncode == 0 and result.stdout == expected[:limit], "namespace output replay")
            require(
                f"success=0 puts={limit + 1} nexts=0".encode() in result.stderr,
                "namespace output continued after failed put",
            )
    for arguments, mutation in (
        ((1, "a", 0, 2, 1, b"x"), 1),
        ((1, "a", 0, 2, 1, b"x"), 2),
        ((1, "a", 0, 2, 1, b""), 3),
        ((1, "a", 0, 2, 0, b""), 0),
        ((1, "a", 0, 2, 1, b"x" * 50), 0),
        ((1, "a", 0, 3, 0, b""), 0),
        ((1, "note", 0, 5, 1, b""), 0),
        ((1, "a", 50, 1, 1, b""), 0),
        ((0, "a", 0, 0, 0, b""), 0),
        ((9, "", 0, 0, 0, b""), 0),
    ):
        result = execute(*arguments, mutation=mutation)
        require(
            result.returncode == 0 and not result.stdout and b"success=0 puts=0" in result.stderr,
            "namespace invalid response produced partial output",
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--host", type=Path, required=True, help="Meson-built runtime-mode host library")
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    host = args.host.resolve(strict=True)
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
    binary = compile_bridges(compiler, work, host)
    client_cases((binary, "client"))
    input_cases((binary, "input"))
    output_cases((binary, "output"))
    namespace_client_cases((binary, "client"))
    namespace_input_cases((binary, "input"))
    namespace_output_cases((binary, "output"))
    print(
        f"PASS scratchpad/namespace: {len(cases)} generated record/parser cases; client, editor and output transcripts",
        flush=True,
    )
    shutil.rmtree(work)


if __name__ == "__main__":
    main()

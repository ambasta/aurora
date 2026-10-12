#!/usr/bin/env python3
"""Only authored byte/register mocks. Never launch a harness, supervisor or emulator."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
BLOCKED = []


def block_processes(event, args):
    if event in ("subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.exec", "pty.spawn"):
        BLOCKED.append(event)
        raise RuntimeError("Process execution blocked in static/mock tests: " + event)


sys.addaudithook(block_processes)
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("command_stop_under_test", ROOT / "fixtures/command-stop-diagnostic.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


class MemoryGuest:
    """Synthetic contract examples only; no C interpretation or emulator linkage."""

    def __init__(self, mutation=None):
        self.mem, self.regs, self.operations, self.mutation, self.writes = {}, {}, [], mutation, []
        self.regs.update({h.HEAD: 0, h.TAIL: 0, h.EH: 0, h.ET: 0, h.CTRL: h.CONTROL, h.STATUS: h.RUN | h.LOG_RUN})
        self.write_bytes(h.EV, h.t.RING_POISON)
        self.write_bytes(h.EV - 16, h.t.PATTERNS["ring_before"])
        self.write_bytes(h.EV + 4096, h.t.PATTERNS["ring_after"])
        self.buffer = bytes(4)
        self.after_stop = False

    def read_bytes(self, addr, n):
        return bytes(self.mem.get(addr + i, 0) for i in range(n))

    def write_bytes(self, addr, data):
        self.mem.update({addr + i: value for i, value in enumerate(data)})

    def q(self, command):
        words = command.split()
        if words[0] == "read":
            return "0x" + self.read_bytes(int(words[1], 0), int(words[2], 0)).hex()
        raise AssertionError("Mock only supports bulk-read q commands: " + command)

    def read(self, addr, width="q"):
        return (
            self.regs[addr]
            if addr in self.regs
            else int.from_bytes(self.read_bytes(addr, 8 if width == "q" else 4), "little")
        )

    def write(self, addr, value):
        self.writes.append((addr, value))
        if addr == h.STATUS:
            if self.mutation == "status_restart" and value & h.RUN:
                self.regs[h.STATUS] |= h.RUN
                self.execute()
            return
        if addr == h.CTRL:
            previous = self.regs[addr]
            self.regs[addr] = value
            self.regs[h.STATUS] = (self.regs[h.STATUS] & ~(h.RUN | h.LOG_RUN)) | (h.LOG_RUN if value & 5 == 5 else 0)
            if value & (1 | h.CMD_EN) == 1 | h.CMD_EN:
                if not (self.mutation == "requires_enable_edge" and previous == value):
                    self.regs[h.STATUS] |= h.RUN
                self.execute()
            return
        if addr in (h.HEAD, h.TAIL, h.EH, h.ET):
            self.regs[addr] = value
            if addr in (h.HEAD, h.TAIL):
                if self.after_stop and self.mutation == "notification_restarts":
                    self.regs[h.STATUS] |= h.RUN
                self.execute()
            return
        self.write_bytes(addr, value.to_bytes(8, "little"))

    def append(self, data):
        if not self.regs[h.CTRL] & 4 or self.regs[h.STATUS] & h.OVERFLOW:
            if self.mutation != "logs_when_suppressed":
                return
        tail = self.regs[h.ET]
        following = (tail + 16) % 4096
        if following == self.regs[h.EH]:
            self.regs[h.STATUS] |= h.OVERFLOW
            if self.mutation != "writes_full_slot":
                return
        self.write_bytes(h.EV + tail, data)
        self.regs[h.ET] = following
        self.regs[h.STATUS] |= h.LOG_INT

    def execute(self):
        if self.regs[h.CTRL] & h.CMD_EN == 0 or not self.regs[h.STATUS] & h.RUN:
            return
        for _ in range(256):
            head = self.regs[h.HEAD]
            if head == self.regs[h.TAIL]:
                return
            a, b = struct.unpack("<QQ", self.read_bytes(h.CMD + head, 16))
            opcode = a >> 60
            if opcode in h.OPCODES:
                info = (b >> 60) << 48 if self.mutation == "leaks_second_nibble" else 0
                self.append(struct.pack("<QQ", (5 << 60) | info, h.CMD + head))
                if self.mutation == "wrong_command_address":
                    self.write_bytes(h.EV + (self.regs[h.ET] - 16) % 4096 + 8, struct.pack("<Q", h.CMD))
                if self.mutation != "continues_after_illegal":
                    self.regs[h.STATUS] &= ~h.RUN
                    self.after_stop = True
                    if self.mutation == "advances_bad_head":
                        self.regs[h.HEAD] = (head + 16) % 4096
                    if self.mutation == "clears_stale_interrupt":
                        self.regs[h.STATUS] &= ~h.COM_INT
                    return
            elif opcode == 1:
                if a & 1 and self.mutation != "drops_completions":
                    address = a & ((1 << 52) - 8)
                    self.write_bytes(address, struct.pack("<Q", b))
                if a & 2:
                    self.regs[h.STATUS] |= h.COM_INT
                if self.mutation == "stores_no_store" and not a & 1:
                    self.write_bytes(a & ((1 << 52) - 8), struct.pack("<Q", b))
            else:
                raise AssertionError("Unexpected recognized command in new-case mock")
            self.regs[h.HEAD] = (head + 16) % 4096
        raise AssertionError("Mock command bound reached")

    def leaf(self, index, value):
        self.write(h.PT + index * 8, value)

    def dma(self, addr, count, write, role, result):
        if count != 4:
            raise AssertionError("Mock DMA supports only four-byte transfers")
        if self.mutation == "kills_other_dma" and self.after_stop:
            self.operations.append({"role": role, "completed": True})
            return
        mapping = {h.t.IOVA: h.t.PA, h.t.OUT: h.t.SINK, h.t.HELPER_IOVA: h.t.HELPER}
        target = mapping[addr]
        if addr == h.t.IOVA and write:
            self.append(h.t.expected_event(addr, True))
            if self.mutation == "denied_dma_writes":
                self.write_bytes(target, self.buffer)
        elif write:
            self.write_bytes(target, self.buffer)
        else:
            self.buffer = self.read_bytes(target, count)
        self.operations.append(
            {
                "role": role,
                "completed": True,
                "direction": "write" if write else "read",
                "declared_bytes": count,
                "write_count_at_submit": len(self.writes),
            }
        )


results = []


def record(name, condition, **detail):
    results.append({"name": name, "pass": bool(condition), **detail})


for path in ROOT.glob("*.py"):
    ast.parse(path.read_text(), filename=str(path))
record("all_python_sources_parse", True)
record("exact_30_cases_unique", len(h.CASES) == len(set(h.CASES)) == 30)
record(
    "full_eight_by_three_matrix",
    h.CASES[:24]
    == [f"opcode_{op:x}_{mode}" for op in (0, 9, 10, 11, 12, 13, 14, 15) for mode in ("live", "disabled", "full")],
)
for name, digest in h.IMPORT_PINS.items():
    record("pin_" + name, h.sha(ROOT / "fixtures" / name) == digest)
record("frozen_import_identity", h.sha(ROOT / "fixtures/frozen-import.py") == h.IMPORT_PINS["frozen-import.py"])
record(
    "transport_import_identity",
    h.sha(ROOT / "fixtures/transport-import-v1.py") == h.IMPORT_PINS["transport-import-v1.py"],
)

for name in h.CASES[:28]:
    guest = MemoryGuest()
    value = h.run_case(guest, name)
    failures = [key for key, okay in value["checks"].items() if not okay]
    record(
        "mock_" + name,
        value["pass"],
        failed_checks=failures,
        check_count=len(value["checks"]),
        dma_operations=len(guest.operations),
        snapshots=len(value["snapshots"]),
    )
    if name == "preexisting_overflow":
        record(
            "preoverflow_without_status_fabrication",
            all(addr != h.STATUS for addr, _ in guest.writes[: guest.operations[1]["write_count_at_submit"]]),
        )
        first_status = next(i for i, item in enumerate(guest.writes) if item[0] == h.STATUS)
        record(
            "overflow_precedes_all_status_probes",
            guest.operations[1]["role"] == "establish_overflow"
            and guest.operations[1]["write_count_at_submit"] < first_status
            and value["snapshots"]["preoverflow_full_after"]["status"] & 1 == 1
            and value["snapshots"]["before_batch"]["status"] & 1 == 1,
        )

mutants = [
    ("continues_after_illegal", "opcode_0_live"),
    ("advances_bad_head", "opcode_f_live"),
    ("leaks_second_nibble", "opcode_0_live"),
    ("wrong_command_address", "opcode_f_live"),
    ("notification_restarts", "opcode_9_live"),
    ("status_restart", "opcode_0_live"),
    ("clears_stale_interrupt", "opcode_0_live"),
    ("logs_when_suppressed", "opcode_9_disabled"),
    ("logs_when_suppressed", "preexisting_overflow"),
    ("writes_full_slot", "opcode_9_full"),
    ("drops_completions", "positive_healthy_commands"),
    ("stores_no_store", "positive_healthy_commands"),
    ("requires_enable_edge", "recovery_same_value_control"),
    ("kills_other_dma", "opcode_0_live"),
    ("denied_dma_writes", "opcode_0_live"),
]
for mutation, name in mutants:
    value = h.run_case(MemoryGuest(mutation), name)
    failed = [key for key, okay in value["checks"].items() if not okay]
    record("reject_" + mutation + "_" + name, bool(failed), detected_failed_checks=failed)

# Record actual denial of a process-creation API. No command reaches Popen.
try:
    import subprocess

    subprocess.Popen(["/__must_never_execute_static_mock__"])
except RuntimeError as exc:
    record("process_execution_block_is_live", bool(BLOCKED), error=str(exc))
else:
    record("process_execution_block_is_live", False)

# A synthetic target exercises the unchanged path guard without installing a
# runtime target, touching a model binary or importing any external preparation.
target = {
    "profile": h.PROFILE,
    "source_c_sha256": h.SOURCE_SHA256,
    "binary_path": "/__expected_static_model__",
    "binary_sha256": "unused",
}
with patch.object(Path, "read_text", return_value=json.dumps(target)):
    try:
        h.validate_target("/__unallocated_binary__")
    except RuntimeError:
        record("wrong_target_path_fails_closed", True)
    else:
        record("wrong_target_path_fails_closed", False)

# No TARGET-BINARY is installed in the repository. Runtime admission is separate.
record("no_runtime_target_in_repository", not (ROOT / "fixtures/TARGET-BINARY.json").exists())
values = [h.nonce(name, i) for name in h.CASES[:28] for i in range(8)]
poisons = [h.poison(name, i) for name in h.CASES[:28] for i in range(8)]
record(
    "fresh_nonces_and_poisons_distinct",
    len(values) == len(set(values)) and len(poisons) == len(set(poisons)) and not set(values) & set(poisons),
)
report = {
    "schema": 1,
    "kind": "static_and_authored_mock_only",
    "pass": all(r["pass"] for r in results),
    "checks": results,
    "check_count": len(results),
    "process_audit_events_blocked": BLOCKED,
    "harness_sha256": h.sha(ROOT / "fixtures/command-stop-diagnostic.py"),
    "test_sha256": h.sha(__file__),
    "not_executed": [
        "QEMU",
        "supervisor",
        "wrapper",
        "harness main",
        "frozen Guest/run_case",
        "source C",
        "compiler/build",
    ],
    "limits": (
        "28 new cases use synthetic transport; frozen two cases have static byte-identity/import checks only. "
        "Authored mocks are not independent emulator/runtime validation."
    ),
}
print(
    json.dumps(
        {
            "suite": "command-stop-mocks",
            "pass": report["pass"],
            "checks": len(results),
            "failures": [r for r in results if not r["pass"]],
        }
    )
)
raise SystemExit(0 if report["pass"] else 1)

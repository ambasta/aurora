#!/usr/bin/env python3
"""Offline only: synthetic RAM/register transport, no emulator/frozen harness execution."""

import ast
import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def deny_processes(event, args):
    if event in ("subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp", "os.fork"):
        raise RuntimeError("This static/mock test must never start a process")


sys.addaudithook(deny_processes)
source = ROOT / "fixtures/transport-import-v1.py"
ast.parse(source.read_text())
spec = importlib.util.spec_from_file_location("granularity_fixture", source)
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


class MockGuest(f.Guest):
    """Independent toy byte-memory transport. Its assumptions are not QEMU evidence."""

    def __init__(self, directory, mutation=None):
        self.output = Path(directory)
        self.operations, self.command_tail, self.mutation = [], 0, mutation
        self.ram, self.registers, self.buffer, self.commands = {}, {}, bytes(16), []
        self.write(f.MMIO + 0x18, f.CONTROL)
        self.write(f.MMIO + 0x2010, 0)
        self.write(f.MMIO + 0x2018, 0)
        self.write(f.MMIO + 0x2000, 0)
        for index, address in [(3, f.PA), (4, f.SINK), (5, f.HELPER)]:
            self.leaf(index, (address & ~4095) | 1 | f.RW)
        self.write_bytes(f.EV, f.RING_POISON)
        self.write_bytes(f.EV - 16, f.PATTERNS["ring_before"])
        self.write_bytes(f.EV + 4096, f.PATTERNS["ring_after"])

    def mem_get(self, address, count):
        return bytes(self.ram.get(address + i, 0) for i in range(count))

    def mem_put(self, address, value):
        for i, byte in enumerate(value):
            self.ram[address + i] = byte

    def append(self, address, write):
        ctrl, status = self.registers[f.MMIO + 0x18], self.registers[f.MMIO + 0x2020]
        if not ctrl & 4 and self.mutation != "disabled_logging":
            return
        if status & 1:
            return
        head, tail = self.registers[f.MMIO + 0x2010], self.registers[f.MMIO + 0x2018]
        next_tail = (tail + 16) % 4096
        if next_tail == head:
            if self.mutation == "full_record_write":
                self.mem_put(f.EV + tail, b"corrupted slot!!")
            self.registers[f.MMIO + 0x2020] |= 1
            return
        first = (2 << 60) + (1 << 54) + (int(write) << 53) + (1 << 52) + (0x1234 << 32) + 0x20
        if self.mutation == "wrong_domain":
            first ^= 1 << 32
        if self.mutation == "raw_rz_only":
            first |= 1 << 55
        self.mem_put(f.EV + tail, struct.pack("<QQ", first, address))
        if self.mutation != "missing_tail":
            self.registers[f.MMIO + 0x2018] = next_tail
        self.registers[f.MMIO + 0x2020] |= 2
        if self.mutation == "ring_canary":
            self.mem_put(f.EV + 4096, b"!")

    def transfer(self, command):
        write = command == 3
        n = self.registers[f.EDU + 0x90]
        address = self.registers[f.EDU + (0x88 if write else 0x80)]
        leaf = int.from_bytes(self.mem_get(f.PT + (address // 4096) * 8, 8), "little")
        physical = (leaf & ((1 << 40) - 4096)) + address % 4096
        allowed = bool(leaf & (1 << (62 if write else 61)))
        if allowed:
            if write:
                if self.mutation != "dead_output" or address != f.OUT:
                    self.mem_put(physical, self.buffer[:n])
                    if self.mutation == "output_guard":
                        self.mem_put(physical + n, b"!")
            else:
                self.buffer = self.mem_get(physical, n)
        else:
            for displacement in range(0, 4 if self.mutation == "one_event_only" else n, 4):
                self.append(address if self.mutation == "duplicate_address" else address + displacement, write)
            if self.mutation == "unexpected_record":
                self.append(address + n, write)
            if write:
                if self.mutation == "write_leak":
                    self.mem_put(physical, self.buffer[:1])
            else:
                self.buffer = bytes(n)
                if self.mutation == "partial_read_leak":
                    leaked = bytearray(self.buffer)
                    leaked[min(5, n - 1)] = self.mem_get(physical, n)[min(5, n - 1)]
                    self.buffer = bytes(leaked)
        self.registers[f.EDU + 0x98] = command & ~1

    def q(self, command):
        self.commands.append(command)
        words = command.split()
        verb, address = words[0], int(words[1], 0)
        if verb == "write":
            n = int(words[2], 0)
            if len(words[3]) != 2 + n * 2 or not words[3].startswith("0x"):
                raise AssertionError("Malformed mock write payload")
            self.mem_put(address, bytes.fromhex(words[3][2:]))
            return ""
        if verb == "read":
            n = int(words[2], 0)
            return "0x" + self.mem_get(address, n).hex()
        if verb == "writeq":
            value = int(words[2], 0)
            if address >= 0xF0000000:
                self.registers[address] = value
                if address == f.MMIO + 0x18:
                    self.registers[f.MMIO + 0x2020] = (
                        (self.registers.get(f.MMIO + 0x2020, 0) & 7) | 16 | (8 if value & 4 else 0)
                    )
                elif address == f.MMIO + 0x2008:
                    self.mem_put(f.DONE, f.NONCE.to_bytes(8, "little"))
                    self.registers[f.MMIO + 0x2000] = value
                elif address == f.MMIO + 0x2010 and self.mutation == "overflow_suppression":
                    self.registers[f.MMIO + 0x2020] &= ~1
                elif address == f.EDU + 0x98:
                    self.transfer(value)
            else:
                self.mem_put(address, value.to_bytes(8, "little"))
            return ""
        if verb in ("readq", "readl"):
            n = 8 if verb == "readq" else 4
            value = (
                self.registers.get(address, 0)
                if address >= 0xF0000000
                else int.from_bytes(self.mem_get(address, n), "little")
            )
            if self.mutation == "count_readback" and address == f.EDU + 0x90:
                value += 4
            return hex(value)
        raise ValueError("Mock lacks command: " + command)


results = []


def record(name, passed, detail=None):
    results.append({"test": name, "pass": bool(passed), "detail": detail})


record("exact_13_case_matrix", len(f.CASES) == 13 and len(set(f.CASES)) == 13)
record("all_pattern_lengths_16", all(len(x) == 16 for x in f.PATTERNS.values()))
record(
    "fresh_secret_distinct_per_byte",
    all(
        f.PATTERNS["secret"][i] != f.PATTERNS[key][i]
        for i in range(16)
        for key in ["prime", "poison", "helper", "decoy"]
    ),
)
rom = bytearray(65536)
rom[-16:-12] = bytes.fromhex("faf4ebfd")
record("reset_rom_identity", hashlib.sha256(rom).hexdigest() == f.ROM_SHA256)
record(
    "all_256_poison_records_invalid",
    all(f.decode_event(f.RING_POISON[i : i + 16])["code"] == 15 for i in range(0, 4096, 16)),
)
with tempfile.TemporaryDirectory(prefix="aurora-granularity-mock-") as temporary:
    for i, case in enumerate(f.CASES):
        directory = Path(temporary) / str(i)
        directory.mkdir()
        guest = MockGuest(directory)
        report = f.run_case(guest, case)
        failed = [key for key, passed in report["checks"].items() if not passed]
        record(
            "synthetic_" + case,
            report["pass"],
            {
                "failed_checks": failed,
                "dma_operations": len(report["dma_operations"]),
                "snapshots": len(report["snapshots"]),
            },
        )
    mutations = [
        ("one_event_only", "denied_write_16", "model_granularity"),
        ("partial_read_leak", "denied_read_16", "memory_denial"),
        ("write_leak", "denied_write_8", "memory_denial"),
        ("duplicate_address", "denied_write_8", "model_granularity"),
        ("unexpected_record", "denied_write_16", "model_granularity"),
        ("wrong_domain", "denied_read_4", "defined_event_fields"),
        ("raw_rz_only", "denied_read_4", "model_encoding_hypothesis"),
        ("missing_tail", "denied_write_8", "model_granularity"),
        ("dead_output", "denied_read_8", "observation_control"),
        ("output_guard", "positive_16", "memory_bounds"),
        ("ring_canary", "transport_append_4", "event_transport"),
        ("disabled_logging", "transport_disabled_then_live_4", "event_transport"),
        ("full_record_write", "transport_full_then_suppressed_4", "event_transport"),
        ("overflow_suppression", "transport_full_then_suppressed_4", "event_transport"),
    ]
    for i, (mutation, case, component) in enumerate(mutations):
        directory = Path(temporary) / ("mutation-" + str(i))
        directory.mkdir()
        report = f.run_case(MockGuest(directory, mutation), case)
        failed = [key for key, passed in report["checks"].items() if not passed]
        record(
            "reject_" + mutation,
            not report["pass"] and report["components"].get(component) is False,
            {"expected_component": component, "failed_checks": failed},
        )
        if mutation == "one_event_only":
            record("missing_predicted_records_do_not_invent_bad_flags", report["components"]["defined_event_fields"])
        if mutation == "raw_rz_only":
            record("undefined_rz_does_not_fail_defined_fields", report["components"]["defined_event_fields"])
        if mutation == "unexpected_record":
            record("unexpected_records_retained", len(report["event_effects"]["denial"]["records"]) == 5)
        if mutation == "duplicate_address":
            record("granularity_failure_does_not_reclassify_denial", report["components"]["memory_denial"])
    directory = Path(temporary) / "wrong-count"
    directory.mkdir()
    guest = MockGuest(directory, "count_readback")
    try:
        f.run_case(guest, "positive_4")
        rejected = False
    except RuntimeError as exc:
        rejected = "count mismatch" in str(exc)
    record("count_mismatch_rejected_before_submit", rejected and not guest.operations)
    # Production bulk decoder rejects truncation rather than zero-padding a record.
    stub = object.__new__(f.Guest)
    stub.q = lambda command: "0x1234"
    try:
        stub.read_bytes(0, 4)
        rejected = False
    except RuntimeError:
        rejected = True
    record("truncated_bulk_read_rejected", rejected)

report = {
    "schema": 1,
    "scope": (
        "Static parsing and synthetic byte-memory/register mock only. "
        "No QEMU, frozen harness, guest, build or supervisor execution."
    ),
    "fixture_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "test_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "tests": results,
    "pass": all(x["pass"] for x in results),
}
print(
    json.dumps(
        {
            "suite": "access-granularity-mocks",
            "pass": report["pass"],
            "tests": len(results),
            "failures": [x for x in results if not x["pass"]],
        }
    )
)
raise SystemExit(0 if report["pass"] else 1)

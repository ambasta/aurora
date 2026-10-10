#!/usr/bin/env python3
"""Test-only PCI EDU DMA architecture gate. Never boots Aurora or opens a disk."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import tempfile
import time

MMIO, EDU, DT, PT, EV, CMD, DONE = 0xFED80000, 0xF0000000, 0x100000, 0x102000, 0x104000, 0x106000, 0x108000
PA, SINK, IOVA, OUT = 0x200000, 0x201000, 0x3000, 0x4000
SECRET, GUARD, NONCE = 0xA18FC2476395B0DE, 0x3759BED12468ACF0, 0xDB1937456280ACEF
HELPER_IOVA, HELPER_PA = 0x5000, 0x202000
HELPER_SENTINEL, OUTPUT_POISON = 0x7291AD84C53BE60F, 0xBADDCAFE71938462
RW = 3 << 61


class Guest:
    def __init__(self, binary, output, rid=0x20):
        self.rid, self.output, self.tail = rid, output, 0
        output.mkdir(parents=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="aurora-dma-")
        rom = bytearray(65536)
        rom[-16:-12] = bytes.fromhex("faf4ebfd")  # CLI; HLT; JMP back to HLT
        bios = Path(self.tmp.name) / "reset.bin"
        bios.write_bytes(rom)
        self.log = (output / "qtest.jsonl").open("w")
        self.err = (output / "qemu.stderr").open("w")
        self.argv = [
            binary,
            "-machine",
            "q35",
            "-accel",
            "tcg",
            "-m",
            "64M",
            "-nodefaults",
            "-display",
            "none",
            "-bios",
            str(bios),
            "-device",
            "amd-iommu",
            "-device",
            f"edu,addr={rid >> 3:02x}.{rid & 7},dma_mask=0xffffffffffffffff",
            "-qtest",
            "stdio",
        ]
        self.p = None
        try:
            self.p = subprocess.Popen(
                self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, bufsize=0
            )
            self.pci(0x10, EDU)
            self.pci(4, 6)  # Test-only device MEM/BME; no production authority.
            assert self.read(EDU, "l") == 0x010000ED
            self.write(DT + rid * 32, PT | 3 | (1 << 9) | RW)
            self.write(DT + rid * 32 + 8, 0x1234)
            self.leaf(3, PA | 1 | RW)
            self.leaf(4, SINK | 1 | RW)
            self.leaf(5, HELPER_PA | 1 | RW)
            self.write(MMIO, DT | 1)
            self.write(MMIO + 0x10, EV | (8 << 56))
            self.write(MMIO + 8, CMD | (8 << 56))
            self.write(MMIO + 0x18, 5 | (1 << 12))
            self.write(PA, SECRET)
            self.write(SINK, GUARD)
            self.write(IOVA, GUARD)
            self.write(OUT, GUARD)
            self.write(DONE, GUARD)
        except BaseException as exc:
            try:
                self.close()
            except Exception as cleanup:
                exc.add_note("Guest construction cleanup failed: " + repr(cleanup))
            raise

    def q(self, command):
        self.p.stdin.write((command + "\n").encode())
        if not select.select([self.p.stdout], [], [], 5)[0]:
            raise RuntimeError("qtest response timeout: " + command)
        reply = self.p.stdout.readline().decode().strip()
        self.log.write(json.dumps({"request": command, "response": reply}) + "\n")
        self.log.flush()
        if not reply.startswith("OK"):
            raise RuntimeError(reply)
        return reply[2:].strip()

    def write(self, addr, value):
        self.q(f"writeq {addr:#x} {value:#x}")

    def read(self, addr, width="q"):
        return int(self.q(f"read{width} {addr:#x}"), 16)

    def pci(self, offset, value):
        self.q(f"outl 0xcf8 {0x80000000 + (self.rid << 8) + offset:#x}")
        self.q(f"outl 0xcfc {value:#x}")

    def leaf(self, index, value):
        self.write(PT + 8 * index, value)

    def dma(self, addr, write=False):
        self.write(EDU + 0x80, 0x40000 if write else addr)
        self.write(EDU + 0x88, addr if write else 0x40000)
        self.write(EDU + 0x90, 8)
        self.write(EDU + 0x98, 3 if write else 1)
        deadline = time.monotonic() + 3
        while self.read(EDU + 0x98) & 1:
            if time.monotonic() > deadline:
                raise RuntimeError("EDU DMA timer did not finish")
            time.sleep(0.02)

    def prime(self):
        self.dma(IOVA)

    def dump(self):
        self.dma(OUT, True)
        return self.read(SINK)

    def invalidate(self, nonce=NONCE, bad=False):
        commands = [
            (0 if bad else (2 << 60) | self.rid, 0),
            ((3 << 60) | (0x1234 << 32), 0x7FFFFFFFFFFFF001),
            ((1 << 60) | DONE | 5, nonce),
        ]  # s=1, f=1; i=0
        for a, b in commands:
            self.write(CMD + self.tail, a)
            self.write(CMD + self.tail + 8, b)
            self.tail += 16
        self.write(MMIO + 0x2008, self.tail)

    def event(self, offset=0):
        a, b = self.read(EV + offset), self.read(EV + offset + 8)
        return {
            "raw": [a, b],
            "code": a >> 60,
            "rid": a & 0xFFFF,
            "domain": (a >> 32) & 0xFFFF,
            "address": b,
            "pr": (a >> 52) & 1,
            "rw": (a >> 53) & 1,
            "pe": (a >> 54) & 1,
            "rz": (a >> 55) & 1,
            "i": (a >> 51) & 1,
            "tr": (a >> 56) & 1,
            "gn": (a >> 48) & 1,
        }

    def close(self):
        try:
            if self.p is not None:
                if self.p.poll() is None:
                    self.p.terminate()
                    try:
                        self.p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.p.kill()
                        self.p.wait(timeout=5)
                self.p.stdin.close()
                self.p.stdout.close()
        finally:
            self.err.close()
            self.log.close()
            self.tmp.cleanup()


def run_case(g, name):
    checks, facts = {}, {}

    def check(key, actual, expected, kind="architectural"):
        facts[key] = {"actual": actual, "expected": expected, "kind": kind}
        checks[key] = actual == expected

    def event(addr=IOVA, domain=0x1234, **flags):
        e = g.event()
        facts["event"] = e
        for key, value in dict(code=2, rid=g.rid, domain=domain, address=addr, i=0, tr=0, gn=0, **flags).items():
            check("event_" + key, e[key], value)
        check("event_tail", g.read(MMIO + 0x2018), 16)
        check("event_status", g.read(MMIO + 0x2020) & 7, 2)

    def output_liveness():
        # Distinct, independently permitted mapping of the SAME requester.
        # This verifies the observation route only, never the denied source.
        g.write(HELPER_PA, HELPER_SENTINEL)
        g.write(SINK, OUTPUT_POISON)
        g.dma(HELPER_IOVA)
        check("permitted_output_liveness", g.dump(), HELPER_SENTINEL, kind="observation_control")

    if name == "permitted_read_write":
        g.prime()
        check("read_write_sentinel", g.dump(), SECRET)
        check("physical_iova_decoy", g.read(IOVA), GUARD)
        check("physical_output_decoy", g.read(OUT), GUARD)
        check("no_fault", g.read(MMIO + 0x2018), 0)
    elif name == "bme_off_control":
        g.prime()
        g.pci(4, 2)
        g.dma(OUT, True)
        check("BME_off_blocks_write", g.read(SINK), GUARD)
        check("physical_decoy", g.read(OUT), GUARD)
    elif name in (
        "high_iova",
        "nonpresent_payload",
        "nonpresent_zero",
        "denied_dte",
        "tv_zero",
        "out_of_table_rid",
        "leaf_write_denied",
    ):
        g.prime()
        # Clear primed translation by actual invalidation and unique completion.
        if name == "nonpresent_payload":
            g.leaf(3, PA | RW)
        if name == "nonpresent_zero":
            g.leaf(3, 0)
        if name == "denied_dte":
            g.write(DT + g.rid * 32, PT | 3 | (1 << 9))
        if name == "tv_zero":
            g.write(DT + g.rid * 32, PT | 1 | (1 << 9) | RW)
        if name == "leaf_write_denied":
            g.leaf(3, PA | 1 | (1 << 61))
        if name == "out_of_table_rid":
            g.write(MMIO, DT)  # 128 entries; RID128 backing exists.
        g.invalidate()
        check("fresh_completion", g.read(DONE), NONCE)
        g.write(PA, GUARD)
        address = 0x203000 if name == "high_iova" else IOVA
        g.write(address, GUARD)
        g.dma(address, True)
        check("mapped_target_unchanged", g.read(PA), GUARD)
        check("physical_iova_unchanged", g.read(address), GUARD)
        flags = {"pr": 0} if name.startswith("nonpresent") else {"pr": 1, "rw": 1}
        if name in ("denied_dte", "leaf_write_denied"):
            flags["pe"] = 1
        if name == "high_iova":
            flags["pe"] = 0
        if name == "out_of_table_rid":
            flags = {}
        event(address, domain=0 if name == "out_of_table_rid" else 0x1234, **flags)
    elif name in ("parent_cache_permissions", "leaf_cache_permissions"):
        if name == "parent_cache_permissions":
            g.write(DT + g.rid * 32, PT | 3 | (1 << 9) | (1 << 61))
        else:
            g.leaf(3, PA | 1 | (1 << 61))
        g.prime()
        if name == "leaf_cache_permissions":
            check("permitted_read", g.dump(), SECRET)
        else:
            # An IR-only DTE also denies output DMA. EDU's private buffer has no
            # MMIO readback, so do not claim that this priming read succeeded.
            # This case observes only the later denied write. The separate
            # permitted_read_write case is its positive write control.
            facts["read_priming"] = {"observed": False, "reason": "EDU buffer has no independent readback"}
        g.write(PA, GUARD)
        g.dma(IOVA, True)
        check("parent_or_leaf_permission_blocks_write", g.read(PA), GUARD)
        check("physical_iova_decoy", g.read(IOVA), GUARD)
        event(pr=1, rw=1, pe=1)
    elif name == "denied_read":
        g.prime()
        g.leaf(3, PA | 1 | (1 << 62))
        g.invalidate()
        check("fresh_completion", g.read(DONE), NONCE)
        g.write(PA, SECRET ^ 0xFFFFFFFFFFFFFFFF)
        g.dma(IOVA)
        g.write(SINK, OUTPUT_POISON)
        observed = g.dump()
        check("denied_read_dump_performed", observed != OUTPUT_POISON, True, kind="observation_control")
        check("read_cannot_leak_secret", observed == (SECRET ^ 0xFFFFFFFFFFFFFFFF), False)
        check("source_unchanged", g.read(PA), SECRET ^ 0xFFFFFFFFFFFFFFFF)
        event(pr=1, rw=0, pe=1)
        output_liveness()
    elif name == "revoke_invalidate_completion":
        g.prime()
        g.leaf(3, 0)
        check("prior_EDU_buffer_observed", g.dump(), SECRET, kind="observation_control")
        g.write(PA, SECRET ^ 0x1111)
        g.dma(IOVA)
        check("actual_stale_dma_before_invalidation", g.dump(), SECRET ^ 0x1111, kind="coverage_prerequisite")
        # Stale completion bit cannot satisfy the fresh store requirement.
        g.write(CMD, (1 << 60) | 2)
        g.write(CMD + 8, 0)
        g.write(MMIO + 0x2008, 16)
        g.tail = 16
        check("stale_completion_bit", g.read(MMIO + 0x2020) & 4, 4)
        check("no_fresh_store_yet", g.read(DONE), GUARD)
        g.invalidate()
        check("matching_nonce", g.read(DONE), NONCE)
        check("executed_command_head", g.read(MMIO + 0x2000), 64)
        g.write(PA, GUARD)
        g.dma(IOVA, True)
        check("revoked_old_write_denied", g.read(PA), GUARD)
        check("revoked_physical_iova_decoy", g.read(IOVA), GUARD)
        g.dma(IOVA)
        g.write(SINK, OUTPUT_POISON)
        observed = g.dump()
        check("revoked_read_dump_performed", observed != OUTPUT_POISON, True, kind="observation_control")
        check("revoked_old_read_no_leak", observed == GUARD, False)
        output_liveness()
    elif name in ("event_wrap", "event_full", "event_capacity"):
        g.write(DT + g.rid * 32, PT | 3 | (1 << 9))
        if name == "event_capacity":
            for _ in range(17):
                g.dma(IOVA)
            check("17_records_fit", g.read(MMIO + 0x2018), 272)
            check("not_overflowed", g.read(MMIO + 0x2020) & 1, 0)
        else:
            g.write(MMIO + 0x18, 1 | (1 << 12))
            g.write(MMIO + 0x2010, 16 if name == "event_wrap" else 0)
            g.write(MMIO + 0x2018, 4080)
            g.write(MMIO + 0x18, 5 | (1 << 12))
            g.write(EV + 4080, GUARD)
            g.dma(IOVA)
            check("tail", g.read(MMIO + 0x2018), 0 if name == "event_wrap" else 4080)
            check("overflow", g.read(MMIO + 0x2020) & 1, 0 if name == "event_wrap" else 1)
            if name == "event_full":
                check("full_discards_record", g.read(EV + 4080), GUARD)
                g.write(MMIO + 0x2010, 16)
                g.dma(IOVA)
                check("overflow_suppresses_later_record", g.read(EV + 4080), GUARD)
            else:
                check("wrapped_record_code", g.event(4080)["code"], 2)
    elif name == "illegal_command_stops":
        g.invalidate(bad=True)
        check("no_completion_store", g.read(DONE), GUARD)
        check("command_engine_stopped", g.read(MMIO + 0x2020) & 16, 0)
        e = g.event()
        facts["event"] = e
        check("illegal_command_event", e["code"], 5)
        check("command_address", e["address"], CMD)
    else:
        raise ValueError(name)
    return {"checks": checks, "observations": facts, "pass": all(checks.values())}


CASES = [
    "permitted_read_write",
    "bme_off_control",
    "high_iova",
    "nonpresent_payload",
    "nonpresent_zero",
    "denied_dte",
    "tv_zero",
    "out_of_table_rid",
    "leaf_write_denied",
    "parent_cache_permissions",
    "leaf_cache_permissions",
    "denied_read",
    "revoke_invalidate_completion",
    "event_wrap",
    "event_full",
    "event_capacity",
    "illegal_command_stops",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--case", choices=CASES, action="append")
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name in args.case or CASES:
        g = None
        try:
            g = Guest(args.qemu, args.output / name, 128 if name == "out_of_table_rid" else 32)
            results[name] = run_case(g, name)
        except Exception as exc:
            results[name] = {
                "pass": False,
                "infrastructure_error": repr(exc),
                "exception_notes": list(getattr(exc, "__notes__", [])),
            }
        finally:
            if g:
                try:
                    g.close()
                except Exception as exc:
                    results[name]["pass"] = False
                    results[name]["cleanup_error"] = repr(exc)
        print(name, "PASS" if results[name]["pass"] else "FAIL", flush=True)
    report = {
        "schema": 1,
        "scope": "test-only emulated ordinary PCI DMA; no physical drain claim",
        "qemu_sha256": hashlib.sha256(Path(args.qemu).read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "results": results,
        "pass": all(r["pass"] for r in results.values()),
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

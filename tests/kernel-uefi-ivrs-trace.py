#!/usr/bin/env python3
"""Strict cold-fixture traces for three read-only AMD-Vi discovery registers.

No DMA isolation is established: disabled IommuEn permits identity translation,
and QEMU maps this aperture despite the PCI base Enable bit remaining zero.
"""

from pathlib import Path
from decimal import Decimal
import importlib.util
import hashlib
import json
import re
import sys


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


prior = module("ivrs_bar_trace", "kernel-uefi-bar-trace.py")
ivrs = module("ivrs_serial_trace", "kernel-uefi-ivrs-smoke.py")
need = ivrs.need
AMD_EVENT_TEXT = (
    "amdvi_evntlog_fail\namdvi_cache_update\namdvi_completion_wait_fail\namdvi_mmio_write\namdvi_mmio_read\n"
    "amdvi_mmio_read_invalid\namdvi_command_error\namdvi_command_read_fail\namdvi_command_exec\n"
    "amdvi_unhandled_command\namdvi_intr_inval\namdvi_iotlb_inval\namdvi_prefetch_pages\namdvi_pages_inval\n"
    "amdvi_all_inval\namdvi_ppr_exec\namdvi_devtab_inval\namdvi_completion_wait\namdvi_control_status\n"
    "amdvi_iotlb_reset\namdvi_dte_get_fail\namdvi_invalid_dte\namdvi_get_pte_hwerror\namdvi_mode_invalid\n"
    "amdvi_page_fault\namdvi_iotlb_hit\namdvi_translation_result\namdvi_mem_ir_write_req\namdvi_mem_ir_write\n"
    "amdvi_ir_remap_msi_req\namdvi_ir_remap_msi\namdvi_err\namdvi_ir_irte\namdvi_ir_irte_val\namdvi_ir_err\n"
    "amdvi_ir_intctl\namdvi_ir_target_abort\namdvi_ir_delivery_mode\namdvi_ir_irte_ga_val\n"
)
EVENT_TEXT = prior.EVENT_TEXT + AMD_EVENT_TEXT
EVENTS = frozenset(EVENT_TEXT.splitlines())
AMD_EVENTS = frozenset(AMD_EVENT_TEXT.splitlines())
AMD_READ = re.compile(
    r"amdvi_mmio_read (AMDVI_MMIO_[A-Z_]+) read addr 0x([0-9a-f]+), size ([0-9]+) offset 0x([0-9a-f]+)"
)
AMD_BOOT = [
    "amdvi_iotlb_reset IOTLB exceed size limit - reset ",
    "amdvi_iotlb_reset IOTLB exceed size limit - reset ",
    "amdvi_mem_ir_write_req addr 0x0 data 0x0 size 0x4",
    "amdvi_ir_remap_msi_req addr 0xfee00000 data 0x0 devid 0xa0",
    "amdvi_ir_remap_msi (addr 0xfee00000, data 0x0) -> (addr 0xfee00000, data 0x0)",
    "amdvi_mem_ir_write addr 0xfee00000 data 0x0",
]
LABELS = ("AMDVI_MMIO_CONTROL", "AMDVI_MMIO_EXT_FEATURES", "AMDVI_MMIO_STATUS")
CONTROL_FILES = {
    "invocation.json",
    "protocol.jsonl",
    "qtest-native.log",
    "trace.log",
    "registers-before.json",
    "registers-after.json",
    "query-pci-before.json",
    "query-pci-after.json",
    "qtree.txt",
    "mtree.txt",
    "process-result.json",
    "stderr.log",
    "trace-enable-events.txt",
    "trace-help-stdout.txt",
    "trace-help-stderr.txt",
}
CONTROL_REGS = (
    ("control", 0x18, "CONTROL"),
    ("device_table", 0, "DEVTAB_BASE"),
    ("command_base", 8, "CMDBUF_BASE"),
    ("event_base", 16, "EVTLOG_BASE"),
    ("exclusion_base", 32, "EXCL_BASE"),
    ("exclusion_limit", 40, "EXCL_LIMIT"),
    ("ppr_base", 56, "PPR_BASE"),
    ("extended_features", 48, "EXT_FEATURES"),
    ("status", 0x2020, "STATUS"),
)


def load_coverage(path):
    result = prior.load_coverage(path)
    need(isinstance(result.get("amdvi_control"), str), "Missing AMD-Vi real coverage control path")
    result["amdvi_control"] = str(Path(path).parent / result["amdvi_control"])
    return result


def read_amdvi_control(directory):
    path = Path(directory)
    manifest = (path / "SHA256SUMS").read_text()
    names = []
    for line in manifest.splitlines():
        match = re.fullmatch(r"[0-9a-f]{64}  ([A-Za-z0-9_.-]+)", line)
        need(
            match is not None and match[1] not in names and match[1] not in (".", "..", "SHA256SUMS"),
            "Malformed AMD-Vi control manifest",
        )
        names.append(match[1])
    need(CONTROL_FILES <= set(names), "Incomplete AMD-Vi control manifest")
    return dict({name: (path / name).read_bytes().decode("utf-8") for name in names}, SHA256SUMS=manifest)


def verify_amdvi_control(artifacts):
    need(
        isinstance(artifacts, dict) and CONTROL_FILES | {"SHA256SUMS"} <= set(artifacts),
        "Missing real AMD-Vi coverage artifacts",
    )
    manifest = {}
    for line in artifacts["SHA256SUMS"].splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        need(
            match is not None and match[2] not in manifest and match[2] not in (".", "..", "SHA256SUMS"),
            "Malformed/duplicate AMD-Vi control digest",
        )
        manifest[match[2]] = match[1]
    need(set(manifest) == set(artifacts) - {"SHA256SUMS"}, "Unbound AMD-Vi control artifact")
    for name, digest in manifest.items():
        need(hashlib.sha256(artifacts[name].encode()).hexdigest() == digest, "AMD-Vi control digest mismatch: " + name)
    read_json = lambda name: json.loads(artifacts[name])
    invocation = read_json("invocation.json")
    argv = invocation.get("argv")
    need(
        isinstance(argv, list)
        and len(argv) > 1
        and all(isinstance(v, str) and v and "\x00" not in v for v in argv)
        and Path(argv[0]).is_absolute(),
        "Missing control invocation",
    )
    need(
        invocation.get("qemu_sha256") == "d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067",
        "Unpinned control binary",
    )
    required = {
        "-machine": "q35",
        "-accel": "tcg",
        "-cpu": "qemu64",
        "-smp": "1",
        "-m": "128M",
        "-nic": "none",
        "-display": "none",
        "-serial": "none",
        "-monitor": "none",
        "-qmp": "stdio",
        "-device": "amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off",
    }
    values, flags = {}, set()
    at = 1
    while at < len(argv):
        option = argv[at]
        if option in ("-nodefaults", "-S", "-no-reboot", "-no-shutdown"):
            need(option not in flags, "Repeated control flag")
            flags.add(option)
            at += 1
        else:
            need(
                option in set(required) | {"-L", "-qtest", "-qtest-log", "-trace"}
                and option not in values
                and at + 1 < len(argv),
                "Unreviewed/repeated control option",
            )
            values[option] = argv[at + 1]
            at += 2
    need(
        flags == {"-nodefaults", "-S", "-no-reboot", "-no-shutdown"}
        and all(values.get(k) == v for k, v in required.items()),
        "Control was not stopped, namespace-free, pinned TCG",
    )
    need(
        set(values) == set(required) | {"-L", "-qtest", "-qtest-log", "-trace"}
        and values["-qtest"].startswith("pipe:/"),
        "Unbound control transport",
    )
    directory = str(Path(values["-qtest"][5:]).parent)
    need(
        values["-qtest"] == "pipe:" + directory + "/qtest"
        and values["-qtest-log"] == directory + "/qtest-native.log"
        and values["-trace"] == "events=" + directory + "/trace-enable-events.txt,file=" + directory + "/trace.log",
        "Control trace/qtest paths disagree",
    )
    need(
        invocation.get("environment_override") and set(invocation["environment_override"]) == {"LD_LIBRARY_PATH"},
        "Unsafe control environment",
    )
    need(
        artifacts["stderr.log"] == "" and read_json("process-result.json").get("returncode") == 0,
        "Control process failed",
    )
    need(
        artifacts["trace-enable-events.txt"] == AMD_EVENT_TEXT + "pci_cfg_write\nmemory_region_ops_write\n",
        "Control trace coverage incomplete",
    )
    available = set((artifacts["trace-help-stdout.txt"] + artifacts["trace-help-stderr.txt"]).splitlines())
    need(
        {event for event in available if event.startswith("amdvi_")} == AMD_EVENTS,
        "Control binary AMD-Vi inventory differs",
    )
    protocol = [json.loads(line) for line in artifacts["protocol.jsonl"].splitlines()]
    previous_time = 0
    for item in protocol:
        need(
            isinstance(item, dict)
            and set(item) == {"monotonic_ns", "kind", "data"}
            and type(item["monotonic_ns"]) is int
            and item["monotonic_ns"] > previous_time,
            "Malformed/backwards control protocol timestamp",
        )
        previous_time = item["monotonic_ns"]
    need(
        protocol
        and protocol[0].get("kind") == "qmp-greeting"
        and protocol[0].get("data", {}).get("QMP", {}).get("version", {}).get("qemu")
        == {"major": 10, "minor": 0, "micro": 13},
        "Control greeting mismatch",
    )
    qmp, qtest, statuses, blocks, pci, monitors = [], [], [], [], [], []
    at = 1
    while at < len(protocol):
        item = protocol[at]
        kind = item.get("kind")
        data = item.get("data")
        at += 1
        need(kind in ("qmp-request", "qtest-request") and at < len(protocol), "Malformed control request/pair")
        reply = protocol[at]
        at += 1
        if kind == "qmp-request" and data == {"execute": "quit"} and reply.get("data", {}).get("event") == "SHUTDOWN":
            need(
                reply["data"].get("data") == {"guest": False, "reason": "host-qmp-quit"} and at < len(protocol),
                "Unexpected QMP lifecycle",
            )
            reply = protocol[at]
            at += 1
        need(reply.get("kind") == kind.replace("request", "response"), "Unpaired AMD-Vi control protocol")
        if kind == "qtest-request":
            need(len(statuses) == 1 and len(monitors) == 2, "qtest executed outside stopped observation interval")
            qtest.append((data, reply.get("data")))
            continue
        need(
            isinstance(data, dict) and set(data) <= {"execute", "arguments"} and "return" in reply.get("data", {}),
            "Failed/unreviewed QMP command",
        )
        operation, value = data.get("execute"), reply["data"]["return"]
        qmp.append(operation)
        need(operation == "human-monitor-command" or set(data) == {"execute"}, "Unexpected QMP arguments")
        if operation == "query-status":
            statuses.append(value)
        elif operation == "query-block":
            blocks.append(value)
        elif operation == "query-pci":
            pci.append(value)
        elif operation == "human-monitor-command":
            need(
                data.get("arguments") == {"command-line": "info " + ("qtree" if not monitors else "mtree")},
                "Unexpected HMP operation",
            )
            monitors.append(value)
        else:
            need(operation in ("qmp_capabilities", "quit") and value == {}, "Unreviewed QMP operation")
    need(
        qmp
        == [
            "qmp_capabilities",
            "query-status",
            "query-block",
            "query-pci",
            "human-monitor-command",
            "human-monitor-command",
            "query-status",
            "query-block",
            "query-pci",
            "quit",
        ]
        and statuses == [{"status": "prelaunch", "running": False}] * 2
        and blocks == [[], []],
        "Control CPU ran, storage existed or lifecycle differed",
    )
    need(
        pci == [read_json("query-pci-before.json"), read_json("query-pci-after.json")] and pci[0] == pci[1],
        "PCI topology changed/unbound",
    )
    targets = [
        (bus.get("bus"), device)
        for bus in pci[0]
        for device in bus.get("devices", [])
        if device.get("id", {}).get("vendor") == 0x1022
    ]
    need(
        len(targets) == 1
        and targets[0][0] == 0
        and targets[0][1].get("slot") == 1
        and targets[0][1].get("function") == 0
        and targets[0][1].get("id", {}).get("device") == 0x1419,
        "Wrong standalone control IOMMU identity",
    )
    need(
        monitors == [artifacts["qtree.txt"], artifacts["mtree.txt"]]
        and "00000000fed80000-00000000fed83fff (prio 0, i/o): amdvi-mmio" in monitors[1],
        "IOMMU memory-region identity unbound",
    )
    reads = [
        (f"readq {ivrs.BASE + offset:#x}", f"OK 0x{0x29D3 if offset == 48 else 0:016x}")
        for _, offset, _ in CONTROL_REGS
    ]
    need(qtest == reads + [("writeq 0xfed80018 0x0", "OK"), reads[0]] + reads, "Unexpected control accesses/readbacks")
    native = []
    lifecycle = []
    previous_time = Decimal(0)
    for index, line in enumerate(artifacts["qtest-native.log"].splitlines()):
        match = re.fullmatch(r"\[([RSI]) (\+?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?)\] (.*)", line)
        need(match is not None, "Malformed native qtest timestamp/record")
        stamp = Decimal(match[2].lstrip("+"))
        need(
            stamp >= previous_time
            and (index == 0 and not match[2].startswith("+") or index > 0 and match[2].startswith("+")),
            "Backwards/non-relative native qtest timestamp",
        )
        previous_time = stamp
        if match[1] == "I":
            lifecycle.append(match[3])
        else:
            native.append((match[1], match[3]))
    need(
        lifecycle == ["OPENED", "CLOSED"]
        and native
        == [(kind, value) for request, response in qtest for kind, value in (("R", request), ("S", response))],
        "Native qtest/protocol mismatch",
    )
    registers = {
        name: {"offset": hex(offset), "address": hex(ivrs.BASE + offset), "value": 0x29D3 if offset == 48 else 0}
        for name, offset, _ in CONTROL_REGS
    }
    need(
        read_json("registers-before.json") == read_json("registers-after.json") == registers,
        "Control register state changed/unbound",
    )
    records, serial, _, debug, _ = parse_trace(artifacts["trace.log"])
    need(not serial and not debug and len(records) == 30, "Control ran firmware or omitted/added trace records")
    need([r["line"] for r in records[:2] + records[3:7]] == AMD_BOOT, "Control startup sequence differs")
    for index, address, region, size in ((2, 0xFEE00000, "amdvi-ir", 4), (16, ivrs.BASE + 24, "amdvi-mmio", 8)):
        record = records[index]
        need(
            record["name"] == "memory_region_ops_write"
            and (record["cpu"], record["address"], record["value"], record["region"], record["size"])
            == (-1, address, 0, region, size),
            "Wrong generic control write witness",
        )
    read_lines = [
        f"amdvi_mmio_read AMDVI_MMIO_{label} read addr 0x{offset:x}, size 8 offset 0x{offset:x}"
        for _, offset, label in CONTROL_REGS
    ]
    need(
        [r["line"] for r in records[7:16]] == read_lines
        and [r["line"] for r in records[17:]]
        == [
            read_lines[0],
            "amdvi_control_status MMIO_STATUS state 0x0",
            "amdvi_command_error error: Executing commands with command buffer disabled 0x0",
            read_lines[0],
        ]
        + read_lines,
        "Control trace/handler sequence differs",
    )
    # The exact raw startup sequence above contains interrupt-remapping writes;
    # this write witness cannot establish whole-run zero interrupt activity.
    return {
        "write": [ivrs.BASE + 24, 0, 8],
        "cpu_stopped": True,
        "startup_ir_records": 5,
        "whole_run_zero_interrupt_activity": False,
        "valid_write_named_event": False,
    }


def parse_trace(text):
    need(isinstance(text, str) and text.endswith("\n"), "Missing/truncated IVRS hardware trace")
    base_lines, base_positions, amd = [], [], []
    for index, line in enumerate(text.splitlines()):
        name = line.split(" ", 1)[0]
        need(name in EVENTS, "Unknown/uncovered trace event: " + name)
        if name in AMD_EVENTS:
            record = {"name": name, "line": line, "index": index}
            if name == "amdvi_mmio_read":
                match = AMD_READ.fullmatch(line)
                need(match is not None, "Malformed AMD-Vi MMIO read")
                label, address, size, aligned = match.groups()
                address, size, aligned = int(address, 16), int(size), int(aligned, 16)
                need(
                    address < ivrs.LENGTH and size in (2, 4, 8) and aligned == address & ~7,
                    "Invalid AMD-Vi MMIO read width/address",
                )
                record.update(label=label, address=address, size=size, aligned=aligned)
            else:
                need(" " in line and line.split(" ", 1)[1], "Truncated AMD-Vi event")
            amd.append(record)
        else:
            base_positions.append(index)
            base_lines.append(line)
    records, serial, serial_at, debug, debug_at = prior.parse_trace("\n".join(base_lines) + "\n")
    for record in records:
        record["index"] = base_positions[record["index"]]
    records += amd
    records.sort(key=lambda record: record["index"])
    return records, serial, [base_positions[i] for i in serial_at], debug, [base_positions[i] for i in debug_at]


def validate_coverage(coverage):
    need(isinstance(coverage, dict) and coverage.get("qemu_version") == "10.0.13", "Unpinned trace binary")
    need(coverage.get("events") == EVENT_TEXT and len(EVENTS) == 257, "Incomplete/unreviewed IVRS event inventory")
    available = set(coverage.get("available_events", "").splitlines())
    need(
        {name for name in available if name.startswith("amdvi_")} == AMD_EVENTS and EVENTS <= available,
        "Binary AMD-Vi trace inventory differs from coverage contract",
    )
    candidate = dict(coverage, events=prior.EVENT_TEXT)
    result = prior.validate_coverage(candidate)
    control = coverage.get("amdvi_control")
    result["amdvi_control"] = verify_amdvi_control(read_amdvi_control(control) if isinstance(control, str) else control)
    return result


def clean_firmware(records, debug, debug_at, firmware, entry, target, measured):
    markers = [line for line in prior.normalized(firmware).splitlines() if "AURORA_FIXTURE" in line]
    need(
        markers == prior.FIRMWARE_MARKERS and "PhysBits: 40" in firmware, "Wrong clean-firmware handoff/physical width"
    )
    spans = []
    cursor = 0
    for marker in prior.FIRMWARE_MARKERS:
        at = debug.find(marker, cursor)
        need(at >= 0, "Firmware handoff marker missing from trace")
        spans.append((debug_at[at], debug_at[at + len(marker) - 1]))
        cursor = at + len(marker)
    need(spans[-1][1] < entry, "Firmware handoff ran after Aurora entry")
    command_writes = [r for r in target if r["operation"] == "write" and r["offset"] == 4]
    need(
        [r["value"] for r in command_writes] == [0, 0, 0, 0x27, 0, 0, 3, 3, 0, 2, 2],
        "Unbounded NVMe firmware command probe",
    )
    need(
        spans[0][1] < command_writes[-2]["index"] < spans[1][0]
        and spans[2][1] < command_writes[-1]["index"] < spans[3][0],
        "Firmware command/marker order disagrees",
    )
    begin, end = command_writes[3]["index"], command_writes[4]["index"]
    need(
        [(r["operation"], r["offset"], r["value"]) for r in target if begin < r["index"] < end] == [("read", 4, 7)],
        "BME capability probe not immediately restored",
    )
    need(end < entry and command_writes[-1]["index"] < entry, "Firmware command restoration too late")
    need(
        [(r["offset"], r["value"]) for r in target if r["operation"] == "write"]
        == prior.expected_config_writes(measured["base"]),
        "NVMe enumeration writes differ from pinned sequence",
    )
    bar_reads = [
        (r["offset"], r["value"])
        for r in target
        if r["operation"] == "read" and r["index"] >= entry and r["offset"] in (0x10, 0x14)
    ]
    need(
        bar_reads
        and all(
            value == ((measured["base"] & 0xFFFFFFF0) | 4 if offset == 0x10 else measured["base"] >> 32)
            for offset, value in bar_reads
        ),
        "Trace BAR base disagrees with descriptor",
    )


def validate_trace(trace, firmware, serial, mode, coverage, payload=None):
    measured = ivrs.validate(33 if mode == "ivrs-read" else 35, serial, mode, payload)
    controls = validate_coverage(coverage)
    records, tx, tx_at, debug, debug_at = parse_trace(trace)
    need(prior.normalized(tx) == prior.normalized(serial), "Trace/serial byte stream mismatch (DLAB-aware)")
    need(prior.normalized(debug) == prior.normalized(firmware), "Trace/firmware byte stream mismatch")
    entry, _ = prior.marker_index(tx, tx_at, "AURORA_UEFI_ENTRY")
    exit_at, exited = prior.marker_index(tx, tx_at, "AURORA_UEFI_EXIT_OK: attempts=1")
    need(entry < exited, "Trace serial phase order")
    if mode not in ivrs.EARLY:
        _, pci_closed = prior.marker_index(tx, tx_at, "AURORA_PCI_WINDOW_CLOSED: reads=39")
        need(exited < pci_closed, "PCI window closure order")
    resets = [r for r in records if r["name"] == "pci_nvme_pci_reset"]
    need(
        len(resets) == 1 and resets[0]["index"] == (1 if mode == "ivrs-missing" else 7),
        "Missing/late/repeated NVMe cold reset",
    )
    if mode == "ivrs-missing":
        initial = records[0]
        need(
            initial["name"] == "memory_region_ops_write"
            and (initial["cpu"], initial["address"], initial["value"], initial["size"], initial["region"])
            == (-1, 0xFEE00000, 0, 4, "apic-msi"),
            "Missing-device APIC realization sequence differs",
        )
    need(
        not any(r["name"] == "pci_cfg_write" and r["index"] >= entry for r in records),
        "Aurora performed PCI configuration write",
    )
    target = [r for r in records if r["name"].startswith("pci_cfg_") and r["device"] == "nvme"]
    need(
        target and any(r["operation"] == "read" and r["offset"] == 0 and r["value"] == 0x101B36 for r in target),
        "NVMe trace identity absent",
    )
    commands = [
        r["value"] & 0xFFFF for r in target if r["operation"] == "read" and r["offset"] == 4 and r["index"] >= entry
    ]
    need(commands and set(commands) == {2}, "NVMe command differs from inactive serial receipt")
    nvme_reads = [r for r in records if r["name"] == "pci_nvme_mmio_read"]
    expected = list(ivrs.bar.READS) if measured["reads"] else []
    need(
        [(r["address"], r["size"]) for r in nvme_reads] == expected,
        "Extra/missing/reordered NVMe reads or firmware register access",
    )
    if nvme_reads:
        _, reconciled = prior.marker_index(tx, tx_at, "AURORA_BAR_RESERVATIONS: count=3 matched=1")
        state, _ = prior.marker_index(tx, tx_at, "AURORA_BAR_STATE:")
        need(all(reconciled < r["index"] < state for r in nvme_reads), "NVMe read outside bounded diagnostic phase")
    need(
        all(
            r["name"] in ("pci_nvme_pci_reset", "pci_nvme_mmio_read")
            for r in records
            if r["name"].startswith("pci_nvme_")
        ),
        "Clean trace contains NVMe initialization/queue/doorbell/DMA/interrupt activity",
    )
    need(not any(r["name"] == "msix_write_config" for r in records), "MSI-X enable/mask changed")
    clean_firmware(records, debug, debug_at, firmware, entry, target, measured)
    amd = [r for r in records if r["name"] in AMD_EVENTS]
    bootstrap = [r for r in amd if r["index"] < entry]
    need(
        [r["line"] for r in bootstrap] == ([] if mode == "ivrs-missing" else AMD_BOOT),
        "Foreign AMD-Vi bootstrap event or firmware MMIO access",
    )
    if bootstrap:
        need(
            [r["index"] for r in bootstrap] == [0, 1, 3, 4, 5, 6], "AMD-Vi bootstrap moved outside initial realization"
        )
    runtime = [r for r in amd if r["index"] >= entry]
    need(all(r["name"] == "amdvi_mmio_read" for r in runtime), "Aurora activated/wrote/signalled AMD-Vi")
    expected_iommu = list(zip(LABELS, ivrs.READS)) if measured["iommu_reads"] else []
    need(
        [(r["label"], (r["address"], r["size"])) for r in runtime] == expected_iommu,
        "Extra/missing/reordered/incorrect-width IOMMU transaction",
    )
    if runtime:
        _, policy = prior.marker_index(tx, tx_at, ivrs.POLICY)
        state, _ = prior.marker_index(tx, tx_at, ivrs.REGISTERS)
        need(
            all(policy < r["index"] < state for r in runtime), "IOMMU read outside explicit read policy/snapshot phase"
        )
    iommu_pci = [
        r for r in records if r["name"].startswith("pci_cfg_") and (r["device"] == "AMDVI-PCI" or r["bdf"] == (0, 3, 0))
    ]
    if mode == "ivrs-missing":
        need(not iommu_pci, "Missing-IOMMU gate still contains its PCI endpoint")
    else:
        need(
            iommu_pci and all(r["device"] == "AMDVI-PCI" and r["bdf"] == (0, 3, 0) for r in iommu_pci),
            "Foreign IOMMU PCI identity",
        )
        observed = [r for r in iommu_pci if r["operation"] == "read" and r["index"] >= entry]
        for record in observed:
            offset = record["offset"]
            if offset < 0x70 and offset % 4 == 0:
                snapshot = ivrs.HEADER + ivrs.CAPABILITY
                need(
                    record["value"] == int.from_bytes(snapshot[offset : offset + 4], "little"),
                    "IOMMU trace readback differs from actual cold snapshot",
                )
        if mode not in ivrs.EARLY + ("ivrs-scope",):
            _, bar_done = prior.marker_index(tx, tx_at, "AURORA_BAR_READ_ONLY_OK")
            raw_at, _ = prior.marker_index(tx, tx_at, "AURORA_IVRS_PCI_RAW:")
            captured = [r for r in observed if bar_done < r["index"] < raw_at]
            need(
                [(r["offset"], r["value"]) for r in captured]
                == [
                    (offset, int.from_bytes((ivrs.HEADER + ivrs.CAPABILITY)[offset : offset + 4], "little"))
                    for offset in list(range(0, 0x40, 4)) * 2 + list(range(0x40, 0x70, 4)) * 2
                ],
                "IOMMU serial snapshot lacks complete ordered trace readbacks",
            )
    for record in records:
        if record["name"] != "memory_region_ops_write":
            continue
        address, size, region = record["address"], record["size"], record["region"]
        need(
            region not in ("nvme", "msix-table", "msix-pba", "amdvi-mmio") and not region.startswith("nvme-"),
            "NVMe/MSI-X/IOMMU MMIO write occurred",
        )
        need(
            not (address < measured["base"] + measured["length"] and measured["base"] < address + size),
            "Write overlaps NVMe BAR",
        )
        need(not (address < ivrs.BASE + ivrs.LENGTH and ivrs.BASE < address + size), "Write overlaps IOMMU aperture")
        # ExitBootServices already succeeded when its first marker byte is
        # emitted. Do not allow a write interleaved into the marker itself.
        if record["index"] > exit_at:
            need(
                region not in ("apic-msi", "ioapic", "hpet")
                and not region.startswith("lapic")
                and not any(
                    address < end and start < address + size
                    for start, end in ((0xFEE00000, 0xFEF00000), (0xFEC00000, 0xFEC01000), (0xFED00000, 0xFED00400))
                ),
                "Aurora wrote APIC/IOAPIC/HPET interrupt registers after firmware exit",
            )
        if region.startswith("amdvi"):
            need(
                mode != "ivrs-missing"
                and record["index"] == 2
                and region == "amdvi-ir"
                and (record["cpu"], address, record["value"], size) == (-1, 0xFEE00000, 0, 4),
                "Unreviewed AMD-Vi memory write",
            )
    return dict(
        controls,
        reads=expected,
        iommu_reads=measured["iommu_reads"],
        command=2,
        architectural_mmio_enable=0,
        profile=ivrs.PROFILE if mode != "ivrs-default" else "architectural",
        dma_evidence="reset plus no initialization/queue/doorbell activity; no DMA isolation established",
    )


def fixture_trace(mode):
    """Synthetic parser input only; real emulator/control runs remain mandatory."""
    _, serial, payload = ivrs.fixture(mode)

    def write(address, value, region="serial", cpu=0, size=1):
        return (
            f"memory_region_ops_write cpu {cpu} mr 0x1 addr 0x{address:x} va"
            f"lue 0x{value:x} size {size} name '{region}'\n"
        )

    def emit(value, region="serial"):
        return "".join(
            write(0x402 if region == "isa-debugcon" else 0x3F8, ord(character), region) for character in value
        )

    trace = write(0xFEE00000, 0, "apic-msi", -1, 4) if mode == "ivrs-missing" else ""
    if mode != "ivrs-missing":
        trace = (
            "\n".join(AMD_BOOT[:2]) + "\n" + write(0xFEE00000, 0, "amdvi-ir", -1, 4) + "\n".join(AMD_BOOT[2:]) + "\n"
        )
    trace += prior.RESET + "\n" + emit("PhysBits: 40\n", "isa-debugcon")
    marker = 0
    for offset, value in prior.expected_config_writes(0xC000000000):
        if offset == 4 and value == 2:
            trace += emit(prior.FIRMWARE_MARKERS[marker] + "\n", "isa-debugcon")
        trace += f"pci_cfg_write nvme 00:02.0 @0x{offset:x} <- 0x{value:x}\n"
        if offset == 4 and value == 0x27:
            trace += "pci_cfg_read nvme 00:02.0 @0x4 -> 0x7\n"
        if offset == 4 and value == 2:
            trace += emit(prior.FIRMWARE_MARKERS[marker + 1] + "\n", "isa-debugcon")
            marker += 2
    trace += "pci_cfg_read nvme 00:02.0 @0x0 -> 0x101b36\n"
    if mode != "ivrs-missing":
        trace += "pci_cfg_read AMDVI-PCI 00:03.0 @0x0 -> 0x14191022\n"
    trace += write(0x3FB, 0x80) + write(0x3F8, 0xFF) + write(0x3FB, 3)
    for line in serial.splitlines(True):
        trace += emit(line)
        if line == "AURORA_UEFI_ENTRY\n":
            trace += (
                "pci_cfg_read nvme 00:02.0 @0x4 -> 0x100002\npci_cfg_read nvme 00:02.0 @0x10 -> 0x4\npci_cfg_re"
                "ad nvme 00:02.0 @0x14 -> 0xc0\n"
            )
        if line.startswith("AURORA_BAR_RESERVATIONS:"):
            trace += "".join(f"pci_nvme_mmio_read addr 0x{offset:x} size {size}\n" for offset, size in ivrs.bar.READS)
        if line == "AURORA_BAR_READ_ONLY_OK\n":
            trace += "".join(
                f"pci_cfg_read AMDVI-PCI 00:03.0 @0x{offset:x} -> 0x"
                f"{int.from_bytes((ivrs.HEADER + ivrs.CAPABILITY)[offset : offset + 4], 'little'):x}\n"
                for offset in list(range(0, 0x40, 4)) * 2 + list(range(0x40, 0x70, 4)) * 2
            )
        if line == ivrs.POLICY + "\n":
            trace += "".join(
                f"amdvi_mmio_read {label} read addr 0x{offset:x}, size {size} offset 0x{offset:x}\n"
                for label, (offset, size) in zip(LABELS, ivrs.READS)
            )
    firmware = "PhysBits: 40\n" + "\n".join(prior.FIRMWARE_MARKERS) + "\n"
    return trace, firmware, serial, payload


def fixture_amdvi_control():
    """Synthetic control artifacts; these never replace a real coverage run."""
    directory = "/tmp/synthetic-amdvi-control"
    protocol = [
        {"kind": "qmp-greeting", "data": {"QMP": {"version": {"qemu": {"major": 10, "minor": 0, "micro": 13}}}}}
    ]
    native = ["[I 0] OPENED"]

    def qmp(operation, value, arguments=None):
        request = {"execute": operation}
        if arguments is not None:
            request["arguments"] = arguments
        protocol.extend(({"kind": "qmp-request", "data": request}, {"kind": "qmp-response", "data": {"return": value}}))

    def qt(request, response):
        protocol.extend(({"kind": "qtest-request", "data": request}, {"kind": "qtest-response", "data": response}))
        native.extend(("[R +0] " + request, "[S +0] " + response))

    pci = [{"bus": 0, "devices": [{"slot": 1, "function": 0, "id": {"vendor": 0x1022, "device": 0x1419}}]}]
    status = {"status": "prelaunch", "running": False}
    qtree = "synthetic qtree"
    mtree = "00000000fed80000-00000000fed83fff (prio 0, i/o): amdvi-mmio"
    qmp("qmp_capabilities", {})
    qmp("query-status", status)
    qmp("query-block", [])
    qmp("query-pci", pci)
    qmp("human-monitor-command", qtree, {"command-line": "info qtree"})
    qmp("human-monitor-command", mtree, {"command-line": "info mtree"})
    reads = [
        (f"readq {ivrs.BASE + offset:#x}", f"OK 0x{0x29D3 if offset == 48 else 0:016x}")
        for _, offset, _ in CONTROL_REGS
    ]
    for request, response in reads + [("writeq 0xfed80018 0x0", "OK"), reads[0]] + reads:
        qt(request, response)
    qmp("query-status", status)
    qmp("query-block", [])
    qmp("query-pci", pci)
    qmp("quit", {})
    native.append("[I +0] CLOSED")
    for index, item in enumerate(protocol):
        item["monotonic_ns"] = index + 1
    registers = {
        name: {"offset": hex(offset), "address": hex(ivrs.BASE + offset), "value": 0x29D3 if offset == 48 else 0}
        for name, offset, _ in CONTROL_REGS
    }
    read_lines = [
        f"amdvi_mmio_read AMDVI_MMIO_{label} read addr 0x{offset:x}, size 8 offset 0x{offset:x}"
        for _, offset, label in CONTROL_REGS
    ]
    trace = (
        AMD_BOOT[:2]
        + ["memory_region_ops_write cpu -1 mr 0x1 addr 0xfee00000 value 0x0 size 4 name 'amdvi-ir'"]
        + AMD_BOOT[2:]
        + read_lines
    )
    trace += [
        "memory_region_ops_write cpu -1 mr 0x2 addr 0xfed80018 value 0x0 size 8 name 'amdvi-mmio'",
        read_lines[0],
        "amdvi_control_status MMIO_STATUS state 0x0",
        "amdvi_command_error error: Executing commands with command buffer disabled 0x0",
        read_lines[0],
    ] + read_lines
    argv = [
        "/tmp/synthetic-qemu",
        "-L",
        "/tmp/firmware",
        "-machine",
        "q35",
        "-accel",
        "tcg",
        "-cpu",
        "qemu64",
        "-smp",
        "1",
        "-m",
        "128M",
        "-nodefaults",
        "-S",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "none",
        "-monitor",
        "none",
        "-no-reboot",
        "-no-shutdown",
        "-device",
        "amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off",
        "-qmp",
        "stdio",
        "-qtest",
        "pipe:" + directory + "/qtest",
        "-qtest-log",
        directory + "/qtest-native.log",
        "-trace",
        "events=" + directory + "/trace-enable-events.txt,file=" + directory + "/trace.log",
    ]
    data = {
        "invocation.json": json.dumps(
            {
                "argv": argv,
                "qemu_sha256": "d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067",
                "environment_override": {"LD_LIBRARY_PATH": "/tmp/libraries"},
            }
        ),
        "protocol.jsonl": "\n".join(map(json.dumps, protocol)) + "\n",
        "qtest-native.log": "\n".join(native) + "\n",
        "trace.log": "\n".join(trace) + "\n",
        "registers-before.json": json.dumps(registers),
        "registers-after.json": json.dumps(registers),
        "query-pci-before.json": json.dumps(pci),
        "query-pci-after.json": json.dumps(pci),
        "qtree.txt": qtree,
        "mtree.txt": mtree,
        "process-result.json": json.dumps({"returncode": 0}),
        "stderr.log": "",
        "trace-enable-events.txt": AMD_EVENT_TEXT + "pci_cfg_write\nmemory_region_ops_write\n",
        "trace-help-stdout.txt": EVENT_TEXT,
        "trace-help-stderr.txt": "",
    }
    return prior.resign_control(data)


def self_test():
    # Only synthetic tests substitute the independent, separately-tested real
    # coverage checker. The production API always requires actual controls.
    global validate_coverage
    actual = validate_coverage
    validate_coverage = lambda value: {} if value == {"self_test": True} else actual(value)
    failures = 0
    try:
        for mode in ivrs.HISTORICAL_MODES:
            trace, firmware, serial, payload = fixture_trace(mode)
            validate_trace(trace, firmware, serial, mode, {"self_test": True}, payload)
            cases = [
                trace.rstrip("\n"),
                trace + prior.RESET + "\n",
                trace + "pci_cfg_write AMDVI-PCI 00:03.0 @0x44 <- 0xfed80001\n",
                trace + "pci_nvme_mmio_read addr 0x8 size 4\n",
                trace + "unknown_event surprise\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfed80018 value 0x0 size 8 name 'foreign'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0x0 value 0x0 size 8 name 'amdvi-mmio'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfed7ffff value 0x0 size 2 name 'foreign'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfed83fff value 0x0 size 2 name 'foreign'\n",
                trace
                + "memory_region_ops_write cpu 0 mr 0x1 addr 0xffffffffffffffff value 0x0 size 2 name 'foreign'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfed80018 value 0x0 size 3 name 'foreign'\n",
                trace + "memory_region_ops_write cpu 1 mr 0x1 addr 0xfed80018 value 0x0 size 8 name 'foreign'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfee00300 value 0x0 size 4 name 'apic-msi'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfec00010 value 0x0 size 4 name 'ioapic'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfed00010 value 0x0 size 4 name 'hpet'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfebfffff value 0x0 size 2 name 'foreign'\n",
                trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0x0 value 0x0 size 4 name 'ioapic'\n",
                trace.replace("pci_cfg_read nvme 00:02.0", "pci_cfg_read nvme 00:03.0", 1),
            ]
            _, emitted, positions, _, _ = parse_trace(trace)
            exit_start, _ = prior.marker_index(emitted, positions, "AURORA_UEFI_EXIT_OK: attempts=1")
            split_trace = trace.splitlines(True)
            cases.append(
                "".join(split_trace[: exit_start + 1])
                + "memory_region_ops_write cpu 0 mr 0x1 addr 0xfee00300 value 0x0 size 4 name 'apic-msi'\n"
                + "".join(split_trace[exit_start + 1 :])
            )
            if mode == "ivrs-missing":
                first = trace.splitlines(True)[0]
                cases += [
                    trace.replace(first, "", 1),
                    trace.replace(first, first * 2, 1),
                    trace.replace(first, first.replace("value 0x0", "value 0x1"), 1),
                    trace.replace(first, first.replace("name 'apic-msi'", "name 'foreign'"), 1),
                ]
            for event in sorted(AMD_EVENTS):
                cases.append(trace + event + " injected\n")
            for line in trace.splitlines(True):
                if line.startswith("amdvi_mmio_read "):
                    cases += [
                        trace.replace(line, "", 1),
                        trace.replace(line, line * 2, 1),
                        trace.replace(line, line.replace("size 8", "size 4"), 1),
                    ]
            for candidate in cases:
                try:
                    validate_trace(candidate, firmware, serial, mode, {"self_test": True}, payload)
                except (ValueError, KeyError):
                    failures += 1
                else:
                    raise RuntimeError("Invalid synthetic IVRS trace accepted: " + mode)
    finally:
        validate_coverage = actual
    for candidate in (
        {},
        {"qemu_version": "10.0.13", "events": prior.EVENT_TEXT},
        {"qemu_version": "10.0.13", "events": EVENT_TEXT, "available_events": prior.EVENT_TEXT},
    ):
        try:
            validate_coverage(candidate)
        except (ValueError, KeyError):
            failures += 1
        else:
            raise RuntimeError("Incomplete IVRS coverage accepted")
    control = fixture_amdvi_control()
    need(
        verify_amdvi_control(control)["whole_run_zero_interrupt_activity"] is False,
        "Raw startup interrupt activity lost its limitation",
    )
    delayed = dict(control)
    delayed["qtest-native.log"] = (
        delayed["qtest-native.log"].replace("[I 0]", "[I 0.000001]", 1).replace("+0]", "+0.000001]")
    )
    verify_amdvi_control(prior.resign_control(delayed))
    archived = prior.resign_control(
        dict(
            control,
            **{
                name: "archived auxiliary artifact\n"
                for name in ("control.py", "result.json", "preflight-provenance.json", "trace-verification.json")
            },
        )
    )
    verify_amdvi_control(archived)
    mutations = [dict(control, **{"unbound.txt": "unlisted control evidence"})]
    for extra in ("changed archival evidence", None):
        changed = dict(archived)
        if extra is None:
            changed.pop("control.py")
        else:
            changed["control.py"] = extra
        mutations.append(changed)
    for name in CONTROL_FILES:
        changed = dict(control)
        changed.pop(name)
        mutations.append(prior.resign_control(changed))
    for name in ("../outside.txt", ".", "..", "SHA256SUMS"):
        changed = dict(control)
        changed["SHA256SUMS"] += "0" * 64 + "  " + name + "\n"
        mutations.append(changed)
    changed = dict(control)
    changed["SHA256SUMS"] += control["SHA256SUMS"].splitlines(True)[0]
    mutations.append(changed)
    for name in control:
        changed = dict(control)
        changed.pop(name)
        mutations.append(changed)
        if name != "SHA256SUMS":
            changed = dict(control)
            changed[name] += "corruption"
            mutations.append(changed)
    for name, old, new in (
        ("trace.log", "value 0x0 size 8", "value 0x1 size 8"),
        ("trace.log", "name 'amdvi-mmio'", "name 'foreign'"),
        ("trace.log", "size 8 offset 0x18", "size 4 offset 0x18"),
        ("protocol.jsonl", '"running": false', '"running": true'),
        ("protocol.jsonl", '"monotonic_ns": 1', '"monotonic_ns": "corrupted"'),
        ("protocol.jsonl", '"monotonic_ns": 2', '"monotonic_ns": 0'),
        ("qtest-native.log", "[R +0]", "[R corrupted]"),
        ("qtest-native.log", "[I 0]", "[I +0]"),
        ("qtest-native.log", "[I 0]", "[I 1]"),
        ("protocol.jsonl", "writeq 0xfed80018 0x0", "writeq 0xfed80018 0x1"),
        ("qtest-native.log", "writeq 0xfed80018 0x0", "writeq 0xfed80018 0x1"),
        ("invocation.json", '"-S"', '"-unsafe"'),
        ("registers-after.json", '"value": 0', '"value": 1'),
        ("trace.log", "amdvi_ir_remap_msi_req addr 0xfee00000", "amdvi_ir_remap_msi_req addr 0xfee00001"),
        ("trace.log", "name 'amdvi-ir'", "name 'foreign'"),
        ("invocation.json", "d3c1a558", "00000000"),
    ):
        changed = dict(control)
        changed[name] = changed[name].replace(old, new, 1)
        mutations.append(prior.resign_control(changed))
    for candidate in mutations:
        try:
            verify_amdvi_control(candidate)
        except (ValueError, KeyError):
            failures += 1
        else:
            raise RuntimeError("Malformed AMD-Vi coverage control accepted")
    print(
        f"PASS: IVRS trace {len(ivrs.HISTORICAL_MODES)} synthetic positive and "
        f"{failures} adversarial cases; real controls required separately"
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        try:
            result = validate_trace(
                Path(sys.argv[1]).read_text(),
                Path(sys.argv[2]).read_text(),
                Path(sys.argv[3]).read_text(),
                sys.argv[4],
                load_coverage(sys.argv[5]),
                json.loads(Path(sys.argv[6]).read_text()) if len(sys.argv) > 6 else None,
            )
        except (ValueError, IndexError, KeyError, OSError) as error:
            sys.exit("FAIL: " + str(error))
        print("PASS: strict IVRS hardware trace " + json.dumps(result, sort_keys=True))

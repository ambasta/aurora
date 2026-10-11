"""Fresh local BAR/IVRS trace controls, using the shared QEMU transport.

These deliberate stopped-CPU writes only establish trace coverage. They never
qualify DMA isolation or replace the independently checked cold guest traces.
"""

from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time

import qemu_transport as transport

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREFIX = "/opt/aurora-fixtures"
FIRMWARE_VERSION = "edk2-fbe0805b2091393406952e84724188f8c1941837-clean-nvme-v1"
QEMU_SHA256 = "d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067"
PATCH_SHA256 = "2a6e8f018d16fc1b4c0304bf7d1f3b56ca4962ca8ec204a19ff94b0e4790ad1f"
need = transport.need


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / f"kernel-uefi-{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(root, name, value):
    (root / name).write_text(json.dumps(value, indent=2) + "\n")


def supported_firmware(env=None):
    env = os.environ if env is None else env
    root = transport.input_path(
        Path(env.get("AURORA_BOOT_FIXTURE_PREFIX") or DEFAULT_PREFIX) / "firmware",
        "supported clean firmware directory",
        True,
    )
    paths = [
        transport.input_path(root / name, "supported clean firmware")
        for name in ("OVMF_CODE.fd", "OVMF_VARS.fd", "policy-three-file.patch", "VERSION")
    ]
    code, variables, patch, version = paths
    need(version.read_text() == FIRMWARE_VERSION + "\n", "Unsupported clean firmware VERSION")
    need(code.stat().st_size == 3653632 and variables.stat().st_size == 540672, "Malformed clean firmware images")
    need(digest(patch) == PATCH_SHA256, "Clean firmware policy patch mismatch")
    return code, variables, patch


def stock_firmware(env):
    code = transport.input_path(env.get("OVMF") or "/usr/share/ovmf/OVMF.fd", "stock OVMF")
    need(digest(code) == module("bar-provenance").PINS["stock_code"], "Unreviewed stock firmware CODE")
    return code


def native_image(profile, root, env):
    with (root / "build.log").open("xb") as log:
        transport.run_logged(
            [
                sys.executable,
                "-B",
                ROOT / "scripts/meson_test.py",
                "--kernel",
                "uefi",
                "--profile",
                profile,
                "--print-image-dir",
            ],
            root / "image-directory.log",
            stderr=log,
            cwd=ROOT,
            env=env,
            timeout=1800,
            expected=0,
            timeout_status=False,
        )
    selected = (root / "image-directory.log").read_text()
    build = Path(selected.rstrip("\n"))
    need(
        selected == str(build) + "\n"
        and selected.count("\n") == 1
        and build.is_absolute()
        and build.parts[-3:] == ("kernel-images", "uefi", profile),
        "Invalid native control image handoff",
    )
    return build


class ControlQmp(transport.Qmp):
    """Record semantic pairs after the shared parser enforces wire IDs/deadlines."""

    def __init__(self, process, deadline, log, record):
        self.record_control, self.greeting = record, True
        super().__init__(process, deadline, log)

    def receive(self):
        result = super().receive()
        kind = "qmp-greeting" if self.greeting else "qmp-response"
        self.greeting = False
        self.record_control(kind, {key: value for key, value in result.items() if key != "id"})
        return result

    def command(self, name, arguments=None):
        request = {"execute": name}
        if arguments is not None:
            request["arguments"] = arguments
        self.record_control("qmp-request", request)
        return super().command(name, arguments)


class Qtest:
    def __init__(self, reader, writer, deadline, record):
        self.reader, self.writer, self.deadline, self.record = reader, writer, deadline, record
        self.buffer, self.total = b"", 0

    def __call__(self, request):
        self.record("qtest-request", request)
        pending = memoryview((request + "\n").encode())
        while pending:
            need(select.select([], [self.writer], [], transport.remaining(self.deadline, 2))[1], "qtest write timeout")
            count = os.write(self.writer, pending)
            need(count > 0, "qtest pipe closed")
            pending = pending[count:]
        while b"\n" not in self.buffer:
            need(select.select([self.reader], [], [], transport.remaining(self.deadline, 2))[0], "qtest read timeout")
            chunk = os.read(self.reader, 4096)
            need(chunk, "qtest pipe closed")
            self.total += len(chunk)
            need(self.total <= 65536, "qtest response limit")
            self.buffer += chunk
        response, self.buffer = self.buffer.split(b"\n", 1)
        response = response.decode().strip()
        self.record("qtest-response", response)
        fields = response.split()
        need(fields and fields[0] == "OK" and len(fields) <= 2, "Failed qtest access: " + response)
        return int(fields[1], 0) if len(fields) == 2 else None


@contextmanager
def stopped(root, qemu, data, device, events, env, include_quit):
    root.mkdir()
    (root / "trace-enable-events.txt").write_text(events)
    argv = transport.command(
        qemu,
        data,
        prefix=["-nodefaults", "-S"],
        serial="none",
        debug_exit=False,
        peripherals=["-device", device],
        diagnostics=[
            "-qmp",
            "stdio",
            "-qtest",
            f"pipe:{root}/qtest",
            "-qtest-log",
            str(root / "qtest-native.log"),
            "-trace",
            f"events={root}/trace-enable-events.txt,file={root}/trace.log",
        ],
        extra=["-no-shutdown"],
    )
    save(
        root,
        "invocation.json",
        {
            "argv": argv,
            "qemu_sha256": digest(qemu),
            "environment_override": {"LD_LIBRARY_PATH": env.get("LD_LIBRARY_PATH", "")},
        },
    )
    process, descriptors = None, []
    with (
        (root / "protocol.jsonl").open("x") as protocol,
        (root / "qmp.log").open("xb") as qmp_log,
        (root / "stderr.log").open("xb") as stderr,
    ):

        def record(kind, value):
            protocol.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(), kind=kind, data=value)) + "\n")
            protocol.flush()

        try:
            for suffix in ("in", "out"):
                path = root / ("qtest." + suffix)
                os.mkfifo(path)
                descriptors.append(os.open(path, os.O_RDWR | os.O_NONBLOCK))
            process = transport.start(
                argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, bufsize=0
            )
            deadline = time.monotonic() + 20
            qmp = ControlQmp(process, deadline, qmp_log, record)
            yield qmp, Qtest(descriptors[1], descriptors[0], deadline, record)
            if not include_quit:
                qmp.record_control = lambda *_: None
            qmp.command("quit")
            transport.wait_exit(process, 5, expected=0)
        finally:
            primary = sys.exception()
            errors, _, unsettled = transport.finish(
                process,
                streams=(() if process is None else (process.stdin, process.stdout)),
                fds=descriptors,
                require_natural=primary is None,
            )
            if process is not None:
                save(root, "process-result.json", {"returncode": process.returncode})
            if unsettled:
                raise transport.ChildNotReaped("Control child has not settled: " + "; ".join(errors)) from primary
            if errors:
                diagnostic = "Control cleanup failed: " + "; ".join(errors)
                if primary is not None:
                    primary.add_note(diagnostic)
                else:
                    raise ValueError(diagnostic)


def msix_control(root, qemu, data, env, trace):
    with stopped(
        root,
        qemu,
        data,
        "nvme,id=control_nvme,serial=AURORA-MSIX-TRACE-CONTROL,bus=pcie.0,addr=02.0,romfile=",
        trace.EVENT_TEXT,
        env,
        False,
    ) as (qmp, qt):
        need(qmp.command("query-status") == {"running": False, "status": "prelaunch"}, "Control CPU ran")
        need(qmp.command("query-block") == [], "Control has block backends")
        save(root, "query-pci.json", qmp.command("query-pci"))
        (root / "qtree.txt").write_text(qmp.command("human-monitor-command", {"command-line": "info qtree"}))

        def select_config(offset):
            qt(f"outl 0xcf8 {0x80001000 | (offset & 0xFC):#x}")

        def read(offset, width=4):
            select_config(offset)
            return qt(f"in{ {1: 'b', 2: 'w', 4: 'l'}[width] } {0xCFC + (offset & 3):#x}")

        def write(offset, value, width=4):
            select_config(offset)
            qt(f"out{ {2: 'w', 4: 'l'}[width] } {0xCFC + (offset & 3):#x} {value:#x}")

        need(read(0) == 0x00101B36 and read(8) >> 8 == 0x010802 and read(0x0E, 1) == 0, "Wrong MSI-X endpoint")
        need(read(4, 2) == 0 and read(0x10) == 4 and read(0x14) == 0, "Control was not cold")
        capability = read(0x34, 1)
        need(capability == 0x40 and read(capability, 1) == 0x11, "Wrong MSI-X capability")
        control, table = read(capability + 2, 2), read(capability + 4)
        need(control == 0x40 and table == 0x2000, "Unexpected MSI-X layout/state")
        write(0x10, 0xC0000004)
        write(0x14, 0)
        need(read(0x10) == 0xC0000004 and read(0x14) == 0, "BAR mapping failed")
        write(4, 2, 2)
        need(read(4, 2) == 2, "Memory decode differs; BME must stay clear")

        def registers():
            result = {
                hex(offset): qt(f"readl {0xC0000000 + offset:#x}")
                for offset in (0x14, 0x1C, 0x24, 0x28, 0x2C, 0x30, 0x34)
            }
            need(all(value == 0 for value in result.values()), "NVMe initialized during control")
            return result

        before = registers()
        need(read(capability + 2, 2) == control, "MSI-X state changed")
        target = 0xC0000000 + table + 12
        need(qt(f"readl {target:#x}") == 1, "Vector not masked")
        qt(f"writel {target:#x} 0x1")
        need(qt(f"readl {target:#x}") == 1 and registers() == before, "Control changed device state")
        need(read(4, 2) == 2 and read(capability + 2, 2) == control, "Control enabled device")
        need(qmp.command("query-status") == {"running": False, "status": "prelaunch"}, "Control CPU ran")


def amdvi_control(root, qemu, data, env, trace, available):
    events = trace.AMD_EVENT_TEXT + "pci_cfg_write\nmemory_region_ops_write\n"
    with stopped(root, qemu, data, "amd-iommu,pt=off,intremap=off,device-iotlb=off,xtsup=off", events, env, True) as (
        qmp,
        qt,
    ):
        (root / "trace-help-stdout.txt").write_text(available)
        (root / "trace-help-stderr.txt").write_text("")
        before_status = qmp.command("query-status")
        need(before_status == {"running": False, "status": "prelaunch"}, "Control CPU ran")
        need(qmp.command("query-block") == [], "Control has block backends")
        pci = qmp.command("query-pci")
        save(root, "query-pci-before.json", pci)
        for name in ("qtree", "mtree"):
            (root / (name + ".txt")).write_text(qmp.command("human-monitor-command", {"command-line": "info " + name}))

        def snapshot():
            result = {}
            for name, offset, _ in trace.CONTROL_REGS:
                value = qt(f"readq {0xFED80000 + offset:#x}")
                need(value == (0x29D3 if offset == 48 else 0), "Unexpected AMD-Vi register")
                result[name] = {"offset": hex(offset), "address": hex(0xFED80000 + offset), "value": value}
            return result

        before = snapshot()
        save(root, "registers-before.json", before)
        qt("writeq 0xfed80018 0x0")
        need(qt("readq 0xfed80018") == 0, "AMD-Vi control enabled")
        after = snapshot()
        save(root, "registers-after.json", after)
        after_status = qmp.command("query-status")
        need(after == before and after_status == before_status, "Control changed AMD-Vi state")
        need(qmp.command("query-block") == [], "Control has block backends")
        pci_after = qmp.command("query-pci")
        save(root, "query-pci-after.json", pci_after)
        need(pci_after == pci, "Control changed topology")


def seal_control(root):
    names = sorted(path.name for path in root.iterdir() if path.is_file())
    (root / "SHA256SUMS").write_text("".join(f"{digest(root / name)}  {name}\n" for name in names))


def generate(family, root, qemu, data, stock, env):
    """Generate once in this run; return paths accepted by existing overrides."""
    need(family in ("bar", "ivrs"), "Unknown trace control family")
    need(digest(qemu) == QEMU_SHA256, "Unreviewed control QEMU")
    root.mkdir()
    bar = module("bar-trace")
    events = root / "bar-events.txt"
    events.write_text(bar.EVENT_TEXT)
    with (root / "trace-help-stderr.txt").open("xb") as stderr:
        transport.run_logged(
            [qemu, "-trace", "help"], root / "available-events.txt", stderr=stderr, env=env, timeout=10, expected=0
        )
    available = (root / "available-events.txt").read_text() + (root / "trace-help-stderr.txt").read_text()
    (root / "available-events.txt").write_text(available)
    stock_run = root / "stock"
    stock_run.mkdir()
    # bar-state refuses BME before MMIO; the inherited profile measures seven
    # read-only registers, then rejects the active controller. Its native image
    # is shared with bar-read, while the semantic oracle remains bar-inherited.
    build = native_image("bar-read", stock_run, env)
    shutil.copytree(build / "esp", stock_run / "esp")
    argv = transport.command(
        qemu,
        data,
        firmware=["-bios", str(stock)],
        boot=transport.fat_boot(stock_run / "esp"),
        peripherals=["-device", "nvme,serial=AURORA_READ_ONLY,bus=pcie.0,addr=02.0"],
        diagnostics=["-trace", f"events={events},file={root}/stock.trace"],
    )
    transport.run_logged(argv, stock_run / "serial.log", cwd=ROOT, env=env, timeout=60, expected=35)
    metadata = json.loads((build / "bar-metadata.json").read_text())
    module("bar-smoke").validate(35, (stock_run / "serial.log").read_text(), "bar-inherited", metadata)
    bar.validate_stock_control((root / "stock.trace").read_text())
    msix_control(root / "msix-control", qemu, data, env, bar)
    seal_control(root / "msix-control")
    coverage = dict(
        qemu_version="10.0.13",
        events="bar-events.txt",
        available_events="available-events.txt",
        stock_trace="stock.trace",
        msix_control="msix-control",
    )
    save(root, "bar-coverage.json", coverage)
    bar.validate_coverage(bar.load_coverage(root / "bar-coverage.json"))
    if family == "ivrs":
        ivrs = module("ivrs-trace")
        (root / "ivrs-events.txt").write_text(ivrs.EVENT_TEXT)
        amdvi_control(root / "amdvi-control", qemu, data, env, ivrs, available)
        seal_control(root / "amdvi-control")
        save(root, "ivrs-coverage.json", dict(coverage, events="ivrs-events.txt", amdvi_control="amdvi-control"))
        ivrs.validate_coverage(ivrs.load_coverage(root / "ivrs-coverage.json"))
    return root / (family + "-coverage.json")

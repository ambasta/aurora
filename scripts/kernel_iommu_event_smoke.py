#!/usr/bin/env python3
"""Boot the IOMMU Event image once per case under the packaged AMD-Vi QEMU model.

The case travels in the fw_cfg fixture file. When the guest prints its terminal
record (or a failure), QEMU is paused over QMP, the retained Event allocations
are saved with pmemsave, and kernel_iommu_event_oracle checks the serial output
and the captures. Local emulator evidence only, not hardware qualification.
"""

import argparse
import os
from pathlib import Path
import re
import selectors
import shutil
import struct
import subprocess
import sys
import tempfile
import time

import kernel_iommu_event_oracle as oracle
from kernel_elf import Elf
from kernel_layout import LAYOUT
from kernel_profiles import fw_cfg_fixture
import qemu_transport as transport
from qemu_transport import MissingPrerequisite, Qmp, exited, reap_completed

ROOT = Path(__file__).resolve().parents[1]
STREAM_LIMIT = 1024 * 1024
# Linked symbol, exact bytes and alignment of each allocation the guest retains for capture.
RETAINED = {
    "terminal": ("uefi_event_terminal", 672, 8),
    "backing": ("uefi_event_backing", 32768, 4096),
    "ring": ("_ZN6aurora11iommu_event16BootLifetimeRing6bytes_E", 4096, 4096),
    "before_ring": ("uefi_event_before_ring", 4096, 4096),
    "after_ring": ("uefi_event_after_ring", 4096, 4096),
}
SHT_NOBITS, SHF_WRITE_ALLOC = 8, 3
need = oracle.need


def section_alignment(elf, index):
    """sh_addralign of one section header; kernel_elf.Section omits it."""
    shoff, shentsize = struct.unpack_from("<Q", elf.data, 40)[0], struct.unpack_from("<H", elf.data, 58)[0]
    return struct.unpack_from("<Q", elf.data, shoff + index * shentsize + 48)[0]


def image_receipt(mode, image):
    """Locate every retained Event allocation in the linked payload, for capture and the oracle."""
    linked = Elf(image / "payload.elf")
    bounds = ("__payload_text_end", "__payload_read_end", "__payload_memory_end")
    symbols = {}
    for symbol in linked.symbols:
        if symbol.name in {name for name, _, _ in RETAINED.values()} | set(bounds):
            need(symbol.name not in symbols, "Ambiguous retained Event symbol: " + symbol.name)
            symbols[symbol.name] = symbol
    begin, end = symbols["__payload_read_end"].address, symbols["__payload_memory_end"].address
    need(0 < begin < end <= LAYOUT.kernel_payload_limit and begin % 4096 == end % 4096 == 0, "Retained RW bounds")
    objects = {}
    for role, (name, size, alignment) in RETAINED.items():
        symbol = symbols[name]
        section = linked.sections[symbol.section]
        need(
            symbol.kind == 1
            and symbol.size == size
            and symbol.address % alignment == 0
            and section.kind == SHT_NOBITS
            and section.flags == SHF_WRITE_ALLOC
            and section_alignment(linked, symbol.section) >= alignment,
            "Retained Event object must be aligned zero-initialized writable BSS: " + role,
        )
        objects[role] = dict(
            symbol=name,
            offset=symbol.address,
            bytes=size,
            alignment=alignment,
            arena_offset=LAYOUT.kernel_payload_offset + symbol.address,
        )
    backing = dict(objects=objects, payload_rw_begin=begin, payload_memory_end=end)
    layout = {name[2:]: symbols[name].address for name in bounds} | {
        "payload_size": (image / "payload.bin").stat().st_size
    }
    return dict(mode=mode, image=dict(mode=mode, backing=backing, payload_layout=layout))


def raw_esp(loader, path):
    """A 64 MiB FAT32 disk holding only EFI/BOOT/BOOTX64.EFI; the Event QEMU has no vvfat driver."""
    with path.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024)
    for argv in (
        ["mformat", "-i", path, "-F", "-T", "131072", "-h", "64", "-s", "32", "-c", "1", "-v", "AURORAESP", "::"],
        ["mmd", "-i", path, "::/EFI", "::/EFI/BOOT"],
        ["mcopy", "-i", path, loader, "::/EFI/BOOT/BOOTX64.EFI"],
    ):
        result = subprocess.run([str(value) for value in argv], capture_output=True, text=True, timeout=60)
        need(result.returncode == 0, " ".join(map(str, argv)) + ": " + result.stderr)


def command(runtime, mode, esp, vars_copy, serial_fd):
    return transport.command(
        runtime / "bin/qemu-system-x86_64",
        runtime / "share/qemu",
        firmware=[
            "-drive",
            f"if=pflash,format=raw,unit=0,readonly=on,file={runtime / 'firmware/OVMF_CODE_4M.fd'}",
            "-drive",
            f"if=pflash,format=raw,unit=1,file={vars_copy}",
        ],
        boot=["-drive", f"if=none,id=boot,format=raw,file={esp}"],
        peripherals=["-nodefaults", "-no-user-config", "-device", "ide-hd,drive=boot,bus=ide.0"]
        + ["-device", "amd-iommu", "-device", "edu,addr=04.0"],
        serial="chardev:guestserial",
        extra=[
            "-boot",
            "order=c",
            "-qmp",
            "stdio",
            "-add-fd",
            f"fd={serial_fd},set=1,opaque=serial-pipe",
            "-chardev",
            "file,id=guestserial,path=/dev/fdset/1,append=on",
            *fw_cfg_fixture(mode),
        ],
    )


def run_case(mode, runtime, image, work):
    """Boot one case, capture the retained allocations when it finishes, and validate."""
    receipt = image_receipt(mode, image)
    layout = oracle.capture_layout(receipt)
    vars_copy = work / "vars.fd"
    shutil.copyfile(runtime / "firmware/OVMF_VARS_4M.fd", vars_copy)
    serial_read, serial_write = os.pipe()
    raw_esp(image / "esp/EFI/BOOT/BOOTX64.EFI", work / "esp.raw")
    argv = command(runtime, mode, work / "esp.raw", vars_copy, serial_write)
    environment = dict(PATH="/usr/bin:/bin", HOME=str(work), LANG="C", LC_ALL="C", TZ="UTC")
    process = transport.start(
        argv,
        cwd=work,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(serial_write,),
    )
    os.close(serial_write)
    serial_stream = os.fdopen(serial_read, "rb", buffering=0)
    serial, stderr = bytearray(), bytearray()
    deadline = time.monotonic() + (90 if mode == "iommu-event-overflow" else 30)
    captures = {}
    watched = selectors.DefaultSelector()
    qmp_log = (work / "qmp.log").open("wb")
    try:
        for stream, name in ((serial_stream, "serial"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            watched.register(stream, selectors.EVENT_READ, name)
        while True:
            transport.remaining(deadline)
            for key, _ in watched.select(min(0.05, deadline - time.monotonic())):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    watched.unregister(key.fileobj)
                    continue
                target = serial if key.data == "serial" else stderr
                need(len(target) + len(chunk) <= STREAM_LIMIT, key.data + " size limit")
                target.extend(chunk)
            terminal = re.search(rb"AURORA_IOMMU_EVENT_TERMINAL: [^\r\n]*\r\n", serial)
            failure = re.search(rb"AURORA_[^\r\n]*(?:FAIL|EXCEPTION|REJECTED)[^\r\n]*\r\n", serial)
            if terminal or failure:
                break
            need(
                not exited(process),
                "Guest exited before its terminal record: " + (stderr or serial[-2000:]).decode(errors="replace"),
            )
        need(not failure, "Guest failure: " + (failure.group(0).decode(errors="replace").strip() if failure else ""))
        qmp = Qmp(process, deadline, qmp_log)
        need(qmp.command("stop") == {}, "QMP stop response")
        status = qmp.command("query-status")
        need(type(status) is dict and status.get("status") == "paused", "QEMU did not pause")
        arena, _ = oracle.ownership(bytes(serial))
        for name, offset, size in layout:
            result = qmp.command(
                "human-monitor-command", {"command-line": f'pmemsave {arena + offset} {size} "{name}"'}
            )
            need(result == "" and (work / name).stat().st_size == size, "Incomplete RAM capture: " + name)
            captures[name] = (work / name).read_bytes()
        need(qmp.command("quit") == {}, "QMP quit response")
        need(reap_completed(process, deadline) == 0, "QEMU exit status")
        need(not stderr, "Unexpected QEMU stderr: " + stderr.decode(errors="replace"))
    finally:
        _, _, unsettled = transport.finish(
            process,
            drains=[watched.close],
            require_natural=False,
            streams=[serial_stream, qmp_log, process.stdin, process.stdout, process.stderr],
        )
        (work / "serial.log").write_bytes(bytes(serial))
    need(not unsettled, "QEMU was not reaped")
    return oracle.validate(mode, receipt, bytes(serial), captures, (work / "qmp.log").read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--tool-prefix", default=os.environ.get("EVENT_TOOL_PREFIX") or "/opt/aurora-event")
    args = parser.parse_args()
    built = subprocess.run(
        [ROOT / "scripts/kernel-image.sh", "uefi", "iommu-event"], cwd=ROOT, capture_output=True, text=True
    )
    need(built.returncode == 0, "Event image build failed:\n" + built.stderr[-4000:])
    image = Path(built.stdout.strip())
    if args.build_only:
        print("Built " + str(image))
        return
    runtime = Path(args.tool_prefix)
    if not (runtime / "bin/qemu-system-x86_64").is_file():
        raise MissingPrerequisite("Event QEMU with the AMD-Vi model not found under " + str(runtime))
    if not shutil.which("mformat"):
        raise MissingPrerequisite("GNU mtools is required to build the raw ESP")
    scratch = Path(tempfile.mkdtemp(prefix="aurora-event-", dir=ROOT / "build"))
    for mode in oracle.MODES:
        work = scratch / mode
        work.mkdir()
        run_case(mode, runtime, image, work)
        print("PASS: " + mode, flush=True)
    shutil.rmtree(scratch)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(transport.failure_label(error) + ": Event smoke: " + str(error), file=sys.stderr)
        raise SystemExit(2 if isinstance(error, MissingPrerequisite) else 1)

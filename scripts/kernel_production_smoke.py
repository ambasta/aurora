#!/usr/bin/env python3
"""Production UEFI guest smoke: both consoles of the one production image.

1. The protected program console's complete PTY oracle
   (tests/kernel-program-console-pty.py) on the production image.
2. One original-clock q35/OVMF/std-VGA guest with QMP: program-console commands
   over serial, whose Console output must equal the reviewed transcript in
   tests/kernel-production-console.json (only whole native diagnostic lines may
   interleave), and the graphical terminal's framebuffer viewport, which must
   equal the real host painter's rendering of that transcript
   (tests/graphical-terminal-host --viewport), in physical memory and in the QMP
   screendump. QEMU's std-VGA identity is pinned by this harness, not by the
   kernel's admission.
3. Fail-closed firmware cases: no display (no GOP) and QEMU's ramfb, whose
   framebuffer lies in firmware-described RAM, must stop in the loader before
   ExitBootServices.
With --nvme-prefix, instead boot the explicit read-only NVMe/XFS production
composition of that same image, checking its storage transcript, screen and
unchanged private disk. --xfs-dual uses two namespaces on that same controller,
with independent malformed-volume cases and unchanged readonly backings.
--xfs-recovery selects the explicit recovery composition
on a private writable copy; this does not establish physical power-loss safety
or physical-hardware support.
--xfs-mounted uses the same production binaries with only a tiny source file
added to a private ESP. Supply --mounted-object compiled independently with:
  C0 --emit-object --target aurora a -o expected.o
where a contains these two lines joined by one space (no trailing newline):
  module mounted; import aurora.host;
  auto main(builtin::HostFiles& f,builtin::span<const u8> a)->builtin::HostExit{return builtin::HostExit::usage;}
The reference must measure 1..4096 bytes. --xfs-db names the pinned xfsprogs
read-only decoder. The result is checked against those bytes and metadata,
then linked/run after a cold readonly boot; Linux mount acceptance is separate.
With --storage-readonly CASE, instead exercise same-boot retirement/remount or
one isolated RAM conflict. Supply --continuity-probe (the existing immutable
host-files-probe-aurora fixture), not --mounted-object. The source preservation
case enters its source over the serial input stream. --continuity-bytes selects
1..4096 binary bytes (default 4096); the original 150-second guest deadline applies.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import struct
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tty

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qemu_transport as transport  # noqa: E402
from kernel_profiles import PROCESS_MEMORY  # noqa: E402
import importlib.util  # noqa: E402
from framebuffer_capture_oracle import BASE, HEIGHT, PITCH, SIZE, WIDTH, need, parse_ppm, ppm_rgb  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/kernel-production-console.json"
_spec = importlib.util.spec_from_file_location("production_capture", ROOT / "scripts/kernel-framebuffer-capture.py")
capture = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = capture
_spec.loader.exec_module(capture)
# The painter's 80x24 cells of 6x9 pixels at (32,32).
VIEW_X, VIEW_Y, VIEW_WIDTH, VIEW_HEIGHT = 32, 32, 480, 216
READY = f"AURORA_GRAPHICAL_TERMINAL_READY: base={BASE} width={WIDTH} height={HEIGHT} pitch={PITCH} format=1"
PROMPT = b"aurora> "


# Firmware framebuffers the loader must refuse, with the exact refusal.
DEVICE_CASES = (
    ("no-display", ["-vga", "none"], "AURORA_UEFI_FAIL: bounded GOP capture"),
    ("ram-framebuffer", ["-vga", "none", "-device", "ramfb"], "AURORA_UEFI_FAIL: framebuffer final map authority"),
)


class Blocked(Exception):
    pass


def golden(storage=False, clean=True, history=False, restart=False, exchange=False, nested=False):
    path = GOLDEN
    if nested:
        path = ROOT / "tests/kernel-production-storage-nested.json"
    elif restart:
        path = ROOT / "tests/kernel-production-recovery-restart.json"
    elif storage:
        name = (
            "kernel-production-storage-unavailable"
            if not clean
            else "kernel-production-storage-clean"
            if history
            else "kernel-production-storage"
        )
        path = ROOT / f"tests/{name}.json"
    data = json.loads(path.read_text())
    need(set(data) == {"input", "console"}, "transcript golden keys")
    need(all(type(item) is str for item in data["input"] + data["console"]), "transcript golden values")
    if exchange and clean:
        # The existing-name permutation changes source names, not expected
        # contents or sizes. Keep RAM output paths such as hello.txt unchanged.
        names = {"hello": "pattern", "pattern": "hello"}
        for key in ("input", "console"):
            data[key] = [
                re.sub(r"(?<!\S)(hello|pattern)(?!\S)", lambda match: names[match[0]], line) for line in data[key]
            ]
    return [item.encode("latin-1") for item in data["input"]], "\r\n".join(data["console"]).encode("latin-1")


DUAL_HELLO = (b"Namespace 1 has distinct readonly bytes.", b"Namespace 2 has distinct readonly bytes.")


def dual_golden(malformed):
    """Reviewed client responses and fixture bytes, independent of the storage implementation."""
    commands = []
    expected = b"AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper/note, ASCII, 64-byte lines\r\naurora> "

    def row(command, response):
        nonlocal expected
        need(len(command) <= 64, "Dual command exceeds production line limit")
        commands.append(command.encode() + b"\r")
        expected += command.encode() + b"\r\n" + response + b"aurora> "

    row("write memo retained", b"wrote memo: 8 bytes\r\n")
    for index in (0, 1, 0, 1):
        path = "/disk" if index == 0 else "/disk2"
        valid = malformed != index + 1
        row(
            f"run bin/list-files {path}",
            b"f hello\nf pattern\n\r\nrun: exited status=0\r\n"
            if valid
            else b"list-files: cannot open directory\n\r\nrun: exited status=1\r\n",
        )
        row(
            f"run bin/cat {path} copy{index} hello",
            b"hello 40\n\r\nrun: exited status=0\r\n"
            if valid
            else b"cannot open directory\n\r\nrun: exited status=1\r\n",
        )
        if valid:
            # The existing compiled reader prints at most 32 bytes per read.
            # Two offsets expose every byte of the independently created input.
            row(
                f"run probe file copy{index} read @1 0 read @1 32 read @1 40",
                b"1 file success 40 #1 \n2 read success 40 "
                + DUAL_HELLO[index][:32]
                + b"\n3 read success 8 "
                + DUAL_HELLO[index][32:]
                + b"\n4 read success 0 \n\r\nrun: exited status=0\r\n",
            )
        row(
            f"run bin/cat {path} {path}/denied hello",
            b"cannot create output\n\r\nrun: exited status=1\r\n"
            if valid
            else b"cannot open directory\n\r\nrun: exited status=1\r\n",
        )
    row("run bin/list-files /disk3", b"list-files: cannot open directory\n\r\nrun: exited status=1\r\n")
    row("run bin/cat / ram-copy input.txt", b"input.txt 17\n\r\nrun: exited status=0\r\n")
    row("run bin/sort / sorted ram-copy", b"3 lines: 5 3 6\n\r\nrun: exited status=0\r\n")
    row("cat memo", b"output> retained\r\n")
    return commands, expected


# This source also defines the independently compiled --mounted-object oracle.
MOUNTED_SOURCE = (
    "module mounted; import aurora.host; "
    "auto main(builtin::HostFiles& f,builtin::span<const u8> a)->builtin::HostExit{return builtin::HostExit::usage;}"
)
MOUNTED_CLEAN_SHA256 = "a764493bba9ea4501ed0b8c73bf5af50c191bd22b4ef4578fc36c259f53a4406"


def mounted_golden(size, cold):
    commands = []
    lines = ["AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper/note, ASCII, 64-byte lines"]

    def command(text, output):
        need(len(text) <= 64, "Mounted command exceeds the production line limit")
        commands.append((text + "\r").encode())
        lines.append("aurora> " + text)
        lines.extend(output)

    if not cold:
        command("run bin/cat /disk old hello", ["hello 64\n", "run: exited status=0"])
        command("run bin/aurorac --emit-executable --target aurora a -o test", ["", "run: exited status=0"])
        command(
            "run-pair test -- bin/cat /disk /disk/hello hello",
            ["[2] cannot create output\n", "[1] run: exited status=2", "[2] run: exited status=1"],
        )
        command("run bin/aurorac --emit-object --target aurora a -o /disk/hello", ["", "run: exited status=0"])
    command("run bin/cat /disk saved hello", [f"hello {size}\n", "run: exited status=0"])
    command("run bin/aurorac --link-object /disk/hello -o test", ["", "run: exited status=0"])
    command("run test", ["", "run: exited status=2"])
    command("run bin/cat /disk hidden .aurora-stage", ["cannot open .aurora-stage\n", "run: exited status=1"])
    command("run bin/cat /disk /disk/hello hello", ["cannot create output\n", "run: exited status=1"])
    command("run bin/file-service-mounted", ["", "run: fault vector=6"])
    command("run bin/cat / copied input.txt", ["input.txt 17\n", "run: exited status=0"])
    command("run bin/sort / sorted copied", ["3 lines: 5 3 6\n", "run: exited status=0"])
    lines.append("aurora> ")
    return commands, "\r\n".join(lines).encode()


READONLY_REFUSED = "storage: readonly refused; RAM retained or disk not ready"
READONLY_READY = "storage: readonly remount ready"
READONLY_UNAVAILABLE = "storage: readonly switch unavailable"
CONTINUITY_SOURCE = (
    b"module retained; import aurora.host;\n"
    b"auto main(builtin::HostFiles&f,builtin::span<const u8>a)->builtin::HostExit{\n"
    b'const builtin::HostFileResult s=f.open_file("main.au");\n'
    b"const builtin::HostChunk c=f.read(s.id,0u64);\n"
    b"const array<u8,504>b=c.bytes;\n"
    b"const builtin::span<const u8>v=borrow_bytes(b);\n"
    b"f.print(builtin::HostStream::stdout,v.subspan(0,i64(c.count)));\n"
    b"f.close(s.id);return builtin::HostExit::success;}\n"
)


def continuity_golden(case, size, probe_size):
    """Cases are input data for the same production image and mounted profile."""
    commands = []
    lines = ["AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper/note, ASCII, 64-byte lines"]

    def command(text, output, input_bytes=None):
        need(len(text) <= 64, "Continuity command exceeds the production line limit")
        commands.append(((text + "\r").encode(), input_bytes))
        lines.append("aurora> " + text)
        lines.extend(output)

    def run(text, output="", status=0):
        command("run " + text, [output, f"run: exited status={status}"])

    def author(path, contents):
        command(
            "run bin/write-source " + path,
            [
                "write-source ready: no echo; Ctrl-D saves, Ctrl-C cancels\nwrite-source: saved\n",
                "run: exited status=0",
                "aurora> ",
                "Input closed; press Enter to return to the console.",
                "",
            ],
            contents + b"\x04",
        )

    command("storage readonly", [READONLY_UNAVAILABLE])
    run(f"probe binary /disk/hello {size}", "1 binary success \n")
    run(f"probe verify /disk/hello {size}", "1 verify success \n")
    if case == "clean":
        # Cancellation leaves no committed RAM record, including an empty one.
        run("probe create cancelled discard @1", "1 create success #0 #1 \n2 discard success \n")
        command("storage readonly", [READONLY_READY])
        run(f"probe verify /disk/hello {size}", "1 verify success \n")
        run(f"probe binary /disk/hello {size}", "1 binary denied \n")
        command("storage readonly", [READONLY_UNAVAILABLE])
    else:
        if case == "ram-source":
            author("main.au", CONTINUITY_SOURCE)
        elif case == "ram-executable":
            run("bin/cat / app probe", f"probe {probe_size}\n")
        elif case == "ram-zero":
            author("empty", b"")
        elif case == "note":
            command("write note retained", ["Note saved."])
        elif case == "named":
            command("write kept retained", ["wrote kept: 8 bytes"])
        command("storage readonly", [READONLY_REFUSED])
        if case == "ram-source":
            run("bin/aurorac --emit-executable --target aurora main.au -o app")
            run("app", CONTINUITY_SOURCE.decode())
        elif case == "ram-executable":
            run(f"app verify /disk/hello {size}", "1 verify success \n")
        elif case == "ram-zero":
            run("probe file empty close @1", "1 file success 0 #1 \n2 close success \n")
        elif case == "note":
            command("cat note", ["output> retained"])
        elif case == "named":
            command("cat kept", ["output> retained"])
        run(f"probe verify /disk/hello {size}", "1 verify success \n")
    lines.append("aurora> ")
    return commands, "\r\n".join(lines).encode()


def mounted_delta(args, directory, before):
    """Bound all changes; let xfsprogs, not a second XFS implementation, decode the result."""
    changed = set()
    old_hash, new_hash = hashlib.sha256(), hashlib.sha256()
    with (directory / "before.raw").open("rb") as old, (directory / "storage.raw").open("rb") as new:
        lba = 0
        while first := old.read(1024 * 1024):
            second = new.read(len(first))
            need(len(second) == len(first), "Mounted disk shortened")
            old_hash.update(first)
            new_hash.update(second)
            for offset in range(0, len(first), 512):
                if first[offset : offset + 512] != second[offset : offset + 512]:
                    changed.add(lba + offset // 512)
            lba += len(first) // 512
        need(not new.read(1), "Mounted disk grew")
    (directory / "image-delta.json").write_text(
        json.dumps(
            dict(
                before_sha256=old_hash.hexdigest(),
                after_sha256=new_hash.hexdigest(),
                object_sha256=hashlib.sha256(args.mounted_bytes).hexdigest(),
                object_size=len(args.mounted_bytes),
                changed_sectors=sorted(changed),
            ),
            indent=2,
        )
        + "\n"
    )
    need(old_hash.digest() == before, "Private mounted baseline changed")
    # Fixed Linux witness geometry: two home sectors, one data block and six log sectors.
    need(changed <= {96, 100, *range(160, 168), *range(524361, 524367)}, "Unexpected mounted disk changes")
    need({96, 100} <= changed and bool(changed & set(range(160, 168))), "Mounted replacement not published")
    with (directory / "storage.raw").open("rb") as image:
        image.seek(20 * 4096)
        need(image.read(4096) == args.mounted_bytes.ljust(4096, b"\0"), "Committed object differs from reference")
    argv = [str(args.xfs_db), "-r", "-f", "-c", "inode 96", "-c", "p core.size u3.sfdir3"]
    for inode in (99, 100):
        argv += ["-c", f"inode {inode}", "-c", "p core.size core.nblocks core.nextents u3.bmx"]
    argv.append(str(directory / "storage.raw"))
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    (directory / "xfs-db.txt").write_text(result.stdout + result.stderr)
    need(result.returncode == 0 and not result.stderr, "xfs_db rejected committed metadata")
    expected = [
        "core.size = 40",
        "u3.sfdir3.hdr.count = 2",
        "u3.sfdir3.hdr.i8count = 0",
        "u3.sfdir3.hdr.parent.i4 = 96",
        "u3.sfdir3.list[0].namelen = 5",
        "u3.sfdir3.list[0].offset = 0x60",
        'u3.sfdir3.list[0].name = "hello"',
        "u3.sfdir3.list[0].inumber.i4 = 100",
        "u3.sfdir3.list[0].filetype = 1",
        "u3.sfdir3.list[1].namelen = 13",
        "u3.sfdir3.list[1].offset = 0x90",
        'u3.sfdir3.list[1].name = ".aurora-stage"',
        "u3.sfdir3.list[1].inumber.i4 = 99",
        "u3.sfdir3.list[1].filetype = 1",
    ]
    for size, block in ((64, 9), (len(args.mounted_bytes), 20)):
        expected += [
            f"core.size = {size}",
            "core.nblocks = 1",
            "core.nextents = 1",
            "u3.bmx[0] = [startoff,startblock,blockcount,extentflag]",
            f"0:[0,{block},1,0]",
        ]
    need([line.rstrip() for line in result.stdout.splitlines()] == expected, "Committed XFS mapping/size differs")


def console_stream(serial, expected):
    """The Console bytes in serial: expected, with only whole AURORA_ diagnostic lines interleaved."""
    start = serial.find(b"AURORA_PROGRAM_CONSOLE_READY:")
    need(start >= 0 and serial[:start].endswith(b"\n"), "Console ready response")
    actual, wanted = serial[start:].split(b"\r\n"), expected.split(b"\r\n")
    index, skipped = 0, 0
    for line in actual[:-1]:
        if index < len(wanted) - 1 and line == wanted[index]:
            index += 1
        else:
            need(
                line.startswith(b"AURORA_") and line != b"AURORA_CONSOLE_EXIT", "Console output differs: " + repr(line)
            )
            skipped += 1
    need(index == len(wanted) - 1 and actual[-1] == wanted[-1], "Console transcript incomplete or differs")
    return skipped


def viewport(raw):
    return b"".join(
        raw[((VIEW_Y + y) * PITCH + VIEW_X) * 4 : ((VIEW_Y + y) * PITCH + VIEW_X + VIEW_WIDTH) * 4]
        for y in range(VIEW_HEIGHT)
    )


def probe(channel, stem):
    """Pause-time read of only the viewport rows from physical memory."""
    path = channel.directory / (stem + ".bin")
    need(not path.exists(), "stale viewport probe")
    first = BASE + (VIEW_Y * PITCH + VIEW_X) * 4
    size = ((VIEW_HEIGHT - 1) * PITCH + VIEW_WIDTH) * 4
    response = channel.command("human-monitor-command", {"command-line": f'pmemsave {first} {size} "{path}"'})
    need(response == "" and path.is_file() and path.stat().st_size == size, "viewport probe failed")
    raw = path.read_bytes()
    path.unlink()
    return b"".join(raw[y * PITCH * 4 : (y * PITCH + VIEW_WIDTH) * 4] for y in range(VIEW_HEIGHT))


def live_view(channel, renderer, expected, stem, begin):
    """Observe a real foreground child's framebuffer before supplying more input."""
    stream = channel.directory / (stem + "-expected.bin")
    model = channel.directory / (stem + "-viewport.bin")
    stream.write_bytes(expected)
    subprocess.run([str(renderer), "--viewport", str(stream), str(model)], check=True, timeout=60)
    wanted = model.read_bytes()
    need(len(wanted) == VIEW_WIDTH * VIEW_HEIGHT * 4, "live viewport extent")
    for attempt in range(100):
        channel.stop()
        channel.drain_serial()
        need(
            b"run: " not in channel.serial_bytes[begin:] and PROMPT not in channel.serial_bytes[begin:],
            "foreground child returned before live capture",
        )
        if probe(channel, f"{stem}-probe-{attempt:03}") == wanted:
            break
        channel.command("cont")
        time.sleep(0.1)
    else:
        raise ValueError("foreground framebuffer did not update before input/exit")
    raw, ppm = channel.capture(stem)
    need(len(raw) == SIZE and viewport(raw) == wanted, "live physical viewport differs")
    need(parse_ppm(ppm) == ppm_rgb(WIDTH, HEIGHT, PITCH, 1, raw), "live physical/screenshot mismatch")
    channel.command("cont")


def wait_for(channel, marker, begin):
    while marker not in channel.serial_bytes[begin:]:
        channel.drain_serial()
        need(
            not any(marker in channel.serial_bytes for marker in (b"_FAIL", b"EXCEPTION", b"QUARANTINED:")),
            "guest failure",
        )
        need(not transport.exited(channel.proc), "premature QEMU exit")
        select.select([channel.serial], [], [], min(0.05, channel.remaining()))


def send(channel, data):
    for byte in data:
        need(select.select([], [channel.serial], [], channel.remaining())[1], "PTY write timeout")
        need(os.write(channel.serial, bytes([byte])) == 1, "short PTY input write")
        time.sleep(0.003)


def firmware():
    selected = subprocess.check_output(
        [
            "bash",
            "-c",
            "set -e; source scripts/uefi-firmware.sh; uefi_firmware_select; "
            'printf "%s\\0" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" "$UEFI_FIRMWARE_VARS"',
        ],
        cwd=ROOT,
    )
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    if not qemu:
        raise Blocked("QEMU unavailable")
    return qemu, transport.firmware_args(*selected.decode().split("\0")[:3])


def device_guests(args, directory):
    qemu, firmware_args = firmware()
    for name, devices, refusal in DEVICE_CASES:
        log = directory / (name + ".log")
        argv = transport.command(
            qemu,
            os.environ.get("QEMU_DATA", ""),
            firmware=firmware_args,
            boot=transport.fat_boot(args.build_dir / "esp"),
            peripherals=devices,
            memory=PROCESS_MEMORY["production"],
        )
        status = transport.run_logged(argv, log, timeout=30)
        lines = log.read_bytes().decode("ascii", "replace").replace("\r\n", "\n").split("\n")
        need(status == 35 and lines.count(refusal) == 1 and lines.count("AURORA_UEFI_ENTRY") == 1, name + " refusal")
        need(not any(line.startswith(("AURORA_UEFI_EXIT_OK", "AURORA_UEFI_PAYLOAD")) for line in lines), name + " exit")
        print("PASS: " + name + " fails closed in the loader: " + refusal)


def recovery_delta(directory, state, before, exchange=False):
    """Record complete private-disk changes after QEMU has been reaped."""
    changed, homes = set(), {}
    old_hash, new_hash = hashlib.sha256(), hashlib.sha256()
    with (directory / "before.raw").open("rb") as old, (directory / "storage.raw").open("rb") as new:
        lba = 0
        while first := old.read(1024 * 1024):
            second = new.read(len(first))
            need(len(second) == len(first), "Recovery disk shortened")
            old_hash.update(first)
            new_hash.update(second)
            for offset in range(0, len(first), 512):
                sector = lba + offset // 512
                data = second[offset : offset + 512]
                if first[offset : offset + 512] != data:
                    changed.add(sector)
                if sector in ((96,) if exchange else (99, 100)):
                    homes[sector] = data
            lba += len(first) // 512
        need(not new.read(1), "Recovery disk grew")
    (directory / "image-delta.json").write_text(
        json.dumps(
            dict(
                state=state,
                exchange=exchange,
                before_sha256=old_hash.hexdigest(),
                after_sha256=new_hash.hexdigest(),
                changed_sectors=sorted(changed),
            ),
            indent=2,
        )
        + "\n"
    )
    need(old_hash.digest() == before, "Private recovery baseline changed")
    dirty_changes = {96, 524343, 524344} if exchange else {99, 100, 524335, 524336}
    need(
        changed == (dirty_changes if state == "dirty" else set()),
        "Unexpected recovery changed sectors: " + str(sorted(changed)),
    )
    if state != "refused":
        for inode in (96,) if exchange else (99, 100):
            path = (
                "fixtures/xfs-root-exchange/root-after.hex"
                if exchange
                else f"fixtures/xfs-core-redo/inode-{inode}-after.hex"
            )
            expected = bytes.fromhex((ROOT / path).read_text())
            need(homes[inode] == expected, "Production recovery home differs from Linux output")


def recovery_lifecycle(serial, state, restarted=False, exchange=False):
    text = serial.decode("ascii", "replace").replace("\r\n", "\n")
    need(
        text.count("AURORA_NVME_ADMISSION_OK:") == 1 and text.count("AURORA_NVME_READY:") == 1,
        "Recovery reattachment must not reinitialize the backend",
    )
    granted = re.findall(r"AURORA_RECOVERY_GRANTED: owner=(\d+) root=(\d+) generation=(\d+) sectors=(\d+)", text)
    need(
        len(granted) == 1
        and int(granted[0][0]) > 0
        and int(granted[0][1]) > 0
        and int(granted[0][1]) % 4096 == 0
        and granted[0][2:] == ("1", "1048576"),
        "Production recovery authority",
    )
    writes, flushes = (0, 0) if state == "refused" else (0, 1) if state == "clean" else (3 if exchange else 4, 3)
    sealed = 0 if state == "refused" else 1
    retired = (
        f"AURORA_RECOVERY_RETIRED: generation=1 sealed={sealed} readonly={sealed} "
        f"admitted_writes={writes} admitted_flushes={flushes}"
    )
    need(
        text.count(retired) == 1 and text.count("AURORA_RECOVERY_CLEANUP:") == 1,
        "Production recovery retirement/cleanup",
    )
    readers = re.findall(r"^AURORA_FILE_SERVICE_READY: generation=(\d+) disk=(ready|unavailable)$", text, re.MULTILINE)
    loaded = re.findall(r"^AURORA_PROCESS_LOADED: run=2 .* owner=(\d+) root=(\d+)$", text, re.MULTILINE)
    need(
        readers == [(str(n), "unavailable" if state == "refused" else "ready") for n in range(1, 3 if restarted else 2)]
        and len(loaded) == 1
        and loaded[0][0] != granted[0][0]
        and int(loaded[0][1]) > 0
        and int(loaded[0][1]) % 4096 == 0,
        "Production independent file-service authority",
    )
    if restarted:
        losses = re.findall(
            r"^AURORA_FILE_SERVICE_LOST: generation=(\d+) transaction=[1-9]\d* cause=(.*?) volatile_data=lost$",
            text,
            re.MULTILINE,
        )
        owners = re.findall(r"^AURORA_PROCESS_LOADED: run=\d+ .* owner=(\d+) root=(\d+)$", text, re.MULTILINE)
        need(
            losses == [("1", "exit status=0")]
            and len(owners) == 3
            and len({owner for owner, _ in owners}) == 3
            and text.index("AURORA_FILE_SERVICE_READY: generation=1")
            < text.index("AURORA_FILE_SERVICE_LOST:")
            < text.index("AURORA_FILE_SERVICE_READY: generation=2"),
            "Recovery owner loss must remount through one fresh owner without replay",
        )
    exit_status = 1 if state == "refused" else 0
    need(
        text.count(f"AURORA_PROCESS_END: run=1 reason=exit status={exit_status}") == 1,
        "Production recovery program exit",
    )
    baseline = re.findall(r"^AURORA_PROCESS_FRAMES: .* free=(\d+)$", text, re.MULTILINE)
    restored = re.findall(r"^AURORA_RECOVERY_CLEANUP: free=(\d+)$", text, re.MULTILINE)
    need(len(baseline) == 1 and restored == baseline, "Production recovery frame cleanup")
    outcome = (
        "AURORA_PROCESS_RECOVERY: refused disk=unavailable"
        if state == "refused"
        else "AURORA_PROCESS_RECOVERY: complete readonly"
    )
    opposite = (
        "AURORA_PROCESS_RECOVERY: complete readonly"
        if state == "refused"
        else "AURORA_PROCESS_RECOVERY: refused disk=unavailable"
    )
    need(
        text.count(outcome) == 1
        and opposite not in text
        and text.index(outcome) < text.index("AURORA_FILE_SERVICE_READY:"),
        "Production recovery outcome",
    )
    need(
        text.index("AURORA_PROCESS_RELEASED: run=1 ")
        < text.index(retired)
        < text.index("AURORA_RECOVERY_CLEANUP:")
        < text.index("AURORA_FILE_SERVICE_READY:")
        < text.index("aurora> "),
        "Production writer release precedes reader and prompt",
    )


def screen_guest(args, directory, *, clean_storage=True, mounted_cold=False, malformed=0):
    mounted = args.xfs_mounted and not mounted_cold
    recover = args.xfs_recovery is not None
    restart = args.recovery_owner_restart
    commands, expected = golden(
        bool(args.nvme_prefix),
        clean_storage,
        args.xfs_history is not None or recover,
        restart,
        args.xfs_exchange,
        args.xfs_nested,
    )
    if args.dual_probe:
        commands = [b"run bin/sort\r"]
        expected = (
            b"AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper/note, ASCII, 64-byte lines\r\n"
            b"aurora> run bin/sort\r\n\r\nrun: file service unavailable\r\naurora> "
        )
    elif args.xfs_dual:
        commands, expected = dual_golden(malformed)
    elif args.storage_readonly:
        commands, expected = continuity_golden(
            args.storage_readonly, len(args.mounted_bytes), args.continuity_probe.stat().st_size
        )
    elif args.xfs_mounted:
        commands, expected = mounted_golden(len(args.mounted_bytes), mounted_cold)
    if recover and not restart:
        commands.append(b"run bin/xfs-recover\r")
        expected += b"run bin/xfs-recover\r\n\r\nrun: fault vector=6\r\naurora> "
    stream = directory / "console-expected.bin"
    stream.write_bytes(expected)
    model = directory / "viewport-expected.bin"
    subprocess.run([str(args.renderer), "--viewport", str(stream), str(model)], check=True, timeout=60)
    expected_view = model.read_bytes()
    need(len(expected_view) == VIEW_WIDTH * VIEW_HEIGHT * 4, "host viewport extent")
    disk = before = second_disk = second_before = None
    if args.nvme_prefix:
        from kernel_iommu_event_smoke import raw_esp
        from kernel_nvme_smoke import command, copy_xfs_history, file_hash
        from xfs_image import create_image

        runtime = transport.input_path(args.nvme_prefix, "NVMe graphics model prefix", directory=True)
        transport.input_path(runtime / "bin/qemu-system-x86_64", "NVMe graphics model")
        need(
            json.loads((runtime / "runtime.json").read_text()).get("model")
            == "aurora-amdvi-command-stop-nvme-graphics-v1",
            "Wrong bounded graphics model",
        )
        fixture = transport.required(os.environ, "AURORA_BOOT_FIXTURE_PREFIX", "clean NVMe firmware prefix")
        clean = transport.input_path(Path(fixture) / "firmware", "clean firmware", directory=True)
        disk = (
            copy_xfs_history(args.xfs_image, directory / "storage.raw")
            if args.xfs_image
            else create_image(directory / "storage.raw", **({"hello": DUAL_HELLO[0]} if args.xfs_dual else {}))
        )
        if args.xfs_dual and not args.dual_singleton:
            second_disk = create_image(directory / "storage2.raw", image_bytes=768 * 1024 * 1024, hello=DUAL_HELLO[1])
            # The independent mkfs producer places both distinct payloads at the
            # same LBA. Check a bounded prefix, not an XFS decoder in Python.
            offsets = []
            for backing, payload in zip((disk, second_disk), DUAL_HELLO):
                with backing.open("rb") as image:
                    prefix = image.read(1024 * 1024)
                need(prefix.count(payload) == 1, "Unique dual-volume fixture payload")
                offsets.append(prefix.index(payload))
            need(offsets[0] == offsets[1] and offsets[0] % 512 == 0, "Dual fixture payloads must share an LBA")
            if malformed:
                # A corrupt magic rejects only this mount, without granting writes.
                with (disk if malformed == 1 else second_disk).open("r+b") as image:
                    need(image.write(b"BAD!") == 4, "Malformed volume fixture")
            second_before = file_hash(second_disk)
        if not clean_storage and not args.xfs_image:
            # Synthetic missing-clean-marker negative for this exact producer,
            # not a genuine dirty transaction or a log-replay test.
            with disk.open("r+b") as image:
                sb = image.read(512)
                need(
                    sb[:4] == b"XFSB"
                    and int.from_bytes(sb[4:8], "big") == 4096
                    and int.from_bytes(sb[48:56], "big") == 65541,
                    "Fresh XFS log location",
                )
                image.seek(65541 * 4096)
                log = image.read(1024)
                need(
                    log[:4] == bytes.fromhex("feedbabe")
                    and log[512:516] == bytes.fromhex("00000001")
                    and log[520:522] == bytes.fromhex("aa20")
                    and log[524:526] == bytes.fromhex("6e55"),
                    "Fresh XFS UNMOUNT record",
                )
                image.seek(65541 * 4096 + 512 + 9)
                need(image.write(b"\x00") == 1, "Remove clean marker")
        before = file_hash(disk)
        if recover or mounted:
            need(before == args.recovery_source_hash, "Writable copy differs from held original")
            copy_xfs_history(disk, directory / "before.raw")
        esp, variables = directory / "esp.raw", directory / "vars.fd"
        esp_source = args.build_dir / "esp"
        if mounted or (args.xfs_dual and not args.dual_probe):
            # Add source input or the existing immutable reader fixture, never
            # replace a shipped executable or kernel.
            import kernel_volume

            esp_source = directory / "source-esp"
            shutil.copytree(args.build_dir / "esp", esp_source)
            path = esp_source / "aurora/system"
            data = path.read_bytes()
            _, _, _, count, stride, names, _, payload, _, _, _ = struct.unpack_from("<8sIIIIQQQQII", data)
            entries = []
            for index in range(count):
                name, length, _, offset, size = struct.unpack_from("<QIIQQ", data, 64 + index * stride)
                entries.append(
                    (data[names + name : names + name + length], data[payload + offset : payload + offset + size])
                )
            if args.storage_readonly or args.xfs_dual:
                need(not any(name == b"probe" for name, _ in entries), "Probe name already present")
                reader = (
                    args.continuity_probe
                    if args.storage_readonly
                    else args.build_dir.parents[2] / "host-files-probe-aurora"
                )
                entries.append((b"probe", reader.read_bytes()))
            else:
                need(not any(name == b"a" for name, _ in entries), "Tiny source name already present")
                entries.append((b"a", MOUNTED_SOURCE.encode()))
            path.write_bytes(kernel_volume.volume(entries))
            if not args.storage_readonly and not args.xfs_dual:
                (directory / "source.au").write_text(MOUNTED_SOURCE)
        if restart or args.dual_probe:
            # Reuse the existing private designated-owner fixture; the production
            # kernel and recovery executable remain unchanged.
            spec = importlib.util.spec_from_file_location(
                "production_pty", ROOT / "tests/kernel-program-console-pty.py"
            )
            pty_oracle = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(pty_oracle)
            owner_directory = directory / "owner-fixture"
            owner_directory.mkdir()
            esp_source = pty_oracle.production_case_volume(
                esp_source,
                args.build_dir.parents[2],
                owner_directory,
                f"dual-{args.dual_probe}" if args.dual_probe else "console-commit",
            )
        raw_esp(esp_source, esp)
        shutil.copyfile(clean / "OVMF_VARS.fd", variables)
    else:
        qemu, firmware_args = firmware()
    master, slave = os.openpty()
    tty.setraw(slave)
    if disk:
        selection = "nvme-linux-6.12-recover" if recover else "nvme-linux-6.12-clean" if args.xfs_image else "nvme"
        if args.xfs_dual:
            selection = "nvme-dual-readonly"
        if mounted:
            selection = "nvme-linux-6.12-write"
        argv = command(
            runtime,
            clean,
            esp,
            disk,
            variables,
            serial=os.ttyname(slave),
            extra=["-qmp", "stdio", "-S", "-boot", "order=c", "-fw_cfg", f"name=opt/aurora/storage,string={selection}"],
            readonly=not (recover or mounted),
            debug_exit=True,
            memory=PROCESS_MEMORY["production"],
            graphics=True,
            second_disk=second_disk,
        )
    else:
        argv = transport.command(
            qemu,
            os.environ.get("QEMU_DATA", ""),
            firmware=firmware_args,
            boot=transport.fat_boot(args.build_dir / "esp"),
            peripherals=["-vga", "std"],
            serial=os.ttyname(slave),
            extra=["-qmp", "stdio", "-S"],
            memory=PROCESS_MEMORY["production"],
        )
    proc = channel = None
    continuity_hash = None
    record = dict(argv=argv, status="failed")
    try:
        with open(directory / "qemu.stderr", "xb") as stderr:
            proc = transport.start(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, bufsize=0)
        channel = capture.Channel(proc, master, directory, time.monotonic() + 150)
        channel.command("cont")
        wait_for(channel, PROMPT, 0)
        need(channel.serial_bytes.count(READY.encode() + b" columns=80 rows=24\r\n") == 1, "terminal readiness")
        if disk:
            marker = (
                b"AURORA_PROCESS_DISK: "
                + (b"ready" if clean_storage and not args.dual_probe else b"unavailable")
                + (b" mounted\r\n" if mounted else b" readonly\r\n")
            )
            need(
                channel.serial_bytes.count(marker) == 1
                and channel.serial_bytes.find(marker) < channel.serial_bytes.find(PROMPT),
                "Production XFS startup result must precede the first prompt",
            )
            need(
                channel.serial_bytes.count(b"AURORA_NVME_ADMISSION_OK: default-ivrs=1 cold=1 handoff-complete=1\r\n")
                == 1,
                "Production NVMe admission",
            )
            ready = f"AURORA_NVME_READY: nsid=1 blocks={disk.stat().st_size // 512} lba-bytes=512 queue-entries=2\r\n"
            need(
                channel.serial_bytes.count(ready.encode()) == 1
                and b"AURORA_NVME_QUARANTINED:" not in channel.serial_bytes,
                "Production read-only namespace",
            )
            if args.xfs_dual:
                if not args.dual_probe:
                    mask = 3 if malformed == 0 else 2 if malformed == 1 else 1
                    marker2 = f"AURORA_DUAL_STORAGE_READY: mask={mask}\r\n".encode()
                    need(
                        channel.serial_bytes.count(marker2) == 1
                        and channel.serial_bytes.find(marker2) < channel.serial_bytes.find(PROMPT),
                        "Independent mount readiness must precede first prompt",
                    )
                count = 1 if args.dual_singleton else 2
                need(
                    channel.serial_bytes.count(f"AURORA_NVME_VOLUMES: count={count} readonly=1\r\n".encode()) == 1,
                    "Exact independently identified readonly namespace count",
                )
                if second_disk:
                    ready2 = (
                        f"AURORA_NVME_READY: nsid=3 blocks={second_disk.stat().st_size // 512} "
                        "lba-bytes=512 queue-entries=2\r\n"
                    )
                    need(channel.serial_bytes.count(ready2.encode()) == 1, "Second readonly namespace identity")
                else:
                    need(
                        channel.serial_bytes.count(b"AURORA_NVME_READY:") == 1,
                        "Singleton cannot invent another namespace",
                    )
            if recover:
                recovery_lifecycle(channel.serial_bytes, args.xfs_recovery, exchange=args.xfs_exchange)
        for item in commands:
            command, input_bytes = item if args.storage_readonly else (item, None)
            begin = len(channel.serial_bytes)
            prompt_begin = begin
            send(channel, command)
            if input_bytes is not None:
                wait_for(channel, b"write-source ready:", begin)
                send(channel, input_bytes)
                wait_for(channel, b"Input closed; press Enter to return to the console.", begin)
                # The run result already printed a prompt before quarantine.
                # Only a fresh prompt after Enter returns input ownership.
                prompt_begin = len(channel.serial_bytes)
                send(channel, b"\r")
            wait_for(channel, PROMPT, prompt_begin)
            if args.storage_readonly and command == b"storage readonly\r":
                part = channel.serial_bytes[begin:]
                if READONLY_READY.encode() in part:
                    need(args.storage_readonly == "clean", "RAM conflict discarded the old service")
                    markers = (
                        rb"AURORA_MOUNTED_RETIRED: generation=\d+ writes=16 flushes=5 disk=readonly\r\n",
                        rb"AURORA_RESIDENT_STOPPED: clean=1 reclaimed=1 retained=1\r\n",
                        rb"AURORA_FILE_SERVICE_READY: generation=\d+ disk=ready\r\n",
                        rb"AURORA_STORAGE_READONLY: ready\r\n",
                    )
                    positions = []
                    for pattern in markers:
                        matches = list(re.finditer(pattern, part))
                        need(len(matches) == 1, "Missing unique readonly lifecycle receipt: " + repr(pattern))
                        positions.append(matches[0].start())
                    need(positions == sorted(positions), "Readonly remount preceded actual old-owner retirement")
                else:
                    need(
                        b"AURORA_MOUNTED_RETIRED:" not in part
                        and b"AURORA_FILE_SERVICE_READY:" not in part
                        and b"AURORA_RESIDENT_STOPPED:" not in part,
                        "Refusal changed the live service incarnation",
                    )
            if args.storage_readonly and command.startswith(b"run probe binary ") and continuity_hash is None:
                # The first command has returned only after all Flush replies and
                # checked commit confirmation. Later reads/refusals may not write.
                channel.stop()
                continuity_hash = file_hash(disk)
                channel.command("cont")
        if continuity_hash is not None:
            channel.stop()
            need(file_hash(disk) == continuity_hash, "Readonly switch or subsequent commands changed disk")
            channel.command("cont")
        channel.drain_serial()
        if disk:
            forbidden = (b"AURORA_NVME_QUARANTINED:",)
            if not restart and not args.dual_probe:
                forbidden += (b"AURORA_PROCESS_DISK: lost", b"AURORA_FILE_SERVICE_LOST:")
            forbidden += (
                ()
                if args.xfs_dual
                else (
                    (b"AURORA_PROCESS_DISK: unavailable", b" disk=unavailable")
                    if clean_storage
                    else (b"AURORA_PROCESS_DISK: ready", b" disk=ready")
                )
            )
            need(not any(marker in channel.serial_bytes for marker in forbidden), "Production storage state changed")
        if args.dual_probe:
            # Both owners are actually admitted and retired. Returning to the
            # console and creating generation 2 crosses the native all-frame
            # cleanup audit, not a synthetic reclamation acknowledgement.
            losses = re.findall(
                rb"AURORA_FILE_SERVICE_LOST: generation=(\d+) transaction=0 "
                rb"cause=(call operation=\d+|exit status=\d+) volatile_data=lost\r\n",
                channel.serial_bytes,
            )
            operation = 24 if args.dual_probe in (41, 43, 44) else 23
            first = b"exit status=0" if args.dual_probe == 42 else f"call operation={operation}".encode()
            need(
                losses == [(b"1", first), (b"2", f"call operation={operation}".encode())],
                "Actual grant probe terminals and fresh-generation retry",
            )
            need(
                channel.serial_bytes.count(b"AURORA_FILE_SERVICE_LOST:") == 2
                and re.findall(rb"AURORA_PROCESS_LOADED: run=(\d+) regions=", channel.serial_bytes) == [b"1", b"2"],
                "Only the two designated owners may execute",
            )
            need(
                not any(
                    marker in channel.serial_bytes
                    for marker in (
                        b"AURORA_FILE_SERVICE_READY:",
                        b"AURORA_DUAL_STORAGE_READY:",
                        b"AURORA_PROCESS_FAIL",
                        b"AURORA_PROCESS_KERNEL_FAULT",
                        b"AURORA_PROCESS_REJECTED:",
                        b"AURORA_UEFI_RUNTIME_FAIL:",
                        b"AURORA_NVME_QUARANTINED:",
                    )
                ),
                "Grant refusal must remain unpublished, local and recoverable",
            )
        if recover:
            # Ordinary execution and repeated runtime attachment never mint another writer.
            recovery_lifecycle(channel.serial_bytes, args.xfs_recovery, restart, args.xfs_exchange)
        if args.xfs_mounted:
            need(
                channel.serial_bytes.count(b"AURORA_MOUNTED_ARMED:") == int(mounted),
                "Mounted authority armed more than once or on readonly boot",
            )
            need(
                channel.serial_bytes.count(b"AURORA_FILE_SERVICE_READY:")
                == (2 if args.storage_readonly == "clean" else 1),
                "Mounted commands replaced the file owner unexpectedly",
            )
        if not disk:
            # These screenshots precede every subsequent input byte and EOF.
            # A final-only repaint cannot satisfy them. The existing host
            # painter consumes reviewed bytes, not a second Python renderer.
            begin = len(channel.serial_bytes)
            send(channel, b"run bin/line-echo\r")
            wait_for(channel, b"line-echo ready\n", begin)
            expected += b"run bin/line-echo\r\nline-echo ready\n"
            live_view(channel, args.renderer, expected, "live-ready", begin)
            for index, line in enumerate((b"first live line", b"second live line")):
                send(channel, line + b"\r")
                wait_for(channel, line + b"\n", begin)
                expected += line + b"\n"
                live_view(channel, args.renderer, expected, f"live-line-{index}", begin)
            # More dirty output turns than the source-owned 32-pass allowance:
            # computation and serial delivery must continue, while optional
            # live rendering defers to the ordinary command-return paint.
            for index in range(35):
                line = f"deferred line {index:02}".encode()
                send(channel, line + b"\r")
                wait_for(channel, line + b"\n", begin)
                expected += line + b"\n"
            # Exact admission exhaustion belongs to the compiled lifecycle
            # case. A framebuffer sampled immediately after serial delivery
            # could simply precede painting, so it is not an exhaustion oracle.
            send(channel, b"\x04")
            wait_for(channel, b"Input closed; press Enter to return to the console.", begin)
            handoff = len(channel.serial_bytes)
            send(channel, b"\r")
            wait_for(channel, PROMPT, handoff)
            expected += (
                b"\r\nrun: exited status=0\r\naurora> "
                b"\r\nInput closed; press Enter to return to the console.\r\n\r\naurora> "
            )
            stream.write_bytes(expected)
            subprocess.run([str(args.renderer), "--viewport", str(stream), str(model)], check=True, timeout=60)
            expected_view = model.read_bytes()
            record["live_foreground_captures"] = ["live-ready", "live-line-0", "live-line-1"]
        skipped = console_stream(channel.serial_bytes, expected)
        # Painting follows the serial prompt; sample paused states until the viewport settles.
        for attempt in range(100):
            channel.stop()
            if probe(channel, f"probe-{attempt:03}") == expected_view:
                break
            channel.command("cont")
            time.sleep(0.1)
        else:
            raise ValueError("framebuffer viewport never matched the host painter")
        raw, ppm = channel.capture("terminal")
        need(len(raw) == SIZE and viewport(raw) == expected_view, "physical viewport differs")
        need(parse_ppm(ppm) == ppm_rgb(WIDTH, HEIGHT, PITCH, 1, raw), "physical/screenshot mismatch")
        channel.command("cont")
        begin = len(channel.serial_bytes)
        send(channel, b"exit\r")
        wait_for(channel, b"AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0\r\n", begin)
        need(transport.wait_exit(proc, 10) == 33, "QEMU did not exit cleanly")
        channel.drain_serial()
        need(b"\r\nAURORA_CONSOLE_EXIT\r\n" in channel.serial_bytes[begin:], "Console exit response")
        if args.storage_readonly or args.dual_probe:
            need(
                channel.serial_bytes.count(b"AURORA_RESIDENT_OWNER_FINISHED: clean=1 reclaimed=1\r\n") == 1,
                "Final retained owner was not consumed exactly once",
            )
            if args.storage_readonly == "clean":
                generations = re.findall(
                    rb"AURORA_FILE_SERVICE_READY: generation=(\d+) disk=ready", channel.serial_bytes
                )
                need(len(generations) == 2 and generations[0] != generations[1], "Readonly remount reused generation")
        for path in (directory / "terminal.bin", directory / "terminal.ppm"):
            path.unlink()
        record.update(status="passed", diagnostics=skipped, probes=attempt + 1, exit_status=33)
    finally:
        primary_error = sys.exception()
        if primary_error is not None:
            record["failure"] = str(primary_error)
        errors, _, unsettled = transport.finish(
            proc,
            drains=[channel.drain_serial] if channel else [],
            fds=(master, slave),
            streams=([channel.qlog, channel.slog] if channel else []) + ([proc.stdin, proc.stdout] if proc else []),
        )
        record["cleanup_errors"] = errors
        (directory / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
        if unsettled:
            raise transport.ChildNotReaped("; ".join(errors))
        if disk:
            if continuity_hash is not None:
                need(file_hash(disk) == continuity_hash, "Final owner cleanup changed the confirmed disk")
            if mounted:
                try:
                    mounted_delta(args, directory, before)
                except Exception as error:
                    record.update(status="failed", disk_verification_error=str(error))
                    (directory / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
                    raise
            elif recover:
                recovery_delta(directory, args.xfs_recovery, before, args.xfs_exchange)
            else:
                need(file_hash(disk) == before, "Readonly production XFS image changed")
                if second_disk:
                    need(file_hash(second_disk) == second_before, "Second readonly XFS image changed")
            # Failure cleanup may terminate QEMU and produce its SIGTERM notice.
            # Preserve the original failed oracle; successful runs still require
            # completely empty diagnostics.
            if primary_error is None:
                need(not (directory / "qemu.stderr").stat().st_size, "Production storage QEMU diagnostics")
        need(not errors, "guest cleanup: " + "; ".join(errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True, help="kernel-images/uefi/production")
    parser.add_argument("--renderer", type=Path, required=True, help="Meson-built tests/graphical-terminal-host")
    parser.add_argument(
        "--nvme-prefix", type=Path, help="instead qualify explicit storage with the separate graphics model"
    )
    parser.add_argument(
        "--xfs-image", type=Path, help="copy an explicit 512MiB Linux-history image, never attach the input"
    )
    parser.add_argument(
        "--xfs-history", choices=("used", "wrapped", "dirty"), help="expected history outcome, not producer attestation"
    )
    parser.add_argument(
        "--xfs-recovery",
        choices=("dirty", "clean", "refused"),
        help="explicit bounded recovery on a private copy; expected outcome, not crash provenance",
    )
    parser.add_argument(
        "--xfs-exchange", action="store_true", help="expect the root-only existing-name exchange recovery witness"
    )
    parser.add_argument(
        "--recovery-owner-restart",
        action="store_true",
        help="private real-mount owner loss/restart fixture after clean recovery, not a HostFiles restart test",
    )
    parser.add_argument(
        "--xfs-dual",
        action="store_true",
        help="two readonly namespaces, independent malformed mounts and cache alternation",
    )
    parser.add_argument(
        "--dual-singleton",
        action="store_true",
        help="new readonly volume grant with only one namespace; /disk2 stays reserved",
    )
    parser.add_argument(
        "--dual-probe",
        type=int,
        choices=range(40, 46),
        help="existing immutable service probe on two readonly namespaces",
    )
    parser.add_argument("--xfs-nested", action="store_true", help="read-only shortform directories and shipped clients")
    parser.add_argument("--xfs-mounted", action="store_true", help="one tiny compiler commit, then readonly cold boot")
    parser.add_argument(
        "--storage-readonly",
        choices=("clean", "ram-source", "ram-executable", "ram-zero", "note", "named"),
        help="same-boot mounted continuity case; no cold boot or RAM source injection",
    )
    parser.add_argument("--continuity-probe", type=Path, help="existing host-files-probe-aurora fixture")
    parser.add_argument("--continuity-bytes", type=int, default=4096, help="binary fixture size, 1..4096")
    parser.add_argument("--mounted-object", type=Path, help="independent Aurora-target object of MOUNTED_SOURCE")
    parser.add_argument("--xfs-db", type=Path, help="pinned read-only xfs_db metadata oracle for mounted mode")
    args = parser.parse_args()
    need(not args.dual_probe or args.xfs_dual, "Dual grant probe requires --xfs-dual")
    need(
        not args.dual_singleton or (args.xfs_dual and not args.dual_probe),
        "Singleton requires dual readonly mode without a two-volume probe",
    )
    need(
        not args.xfs_dual
        or (
            args.nvme_prefix
            and not (args.xfs_image or args.xfs_nested or args.xfs_mounted or args.xfs_recovery or args.xfs_history)
        ),
        "Dual readonly requires NVMe and cannot combine with other storage modes",
    )
    need(
        not args.xfs_nested or not (args.xfs_mounted or args.xfs_history or args.xfs_recovery),
        "Choose nested, mounted, history or recovery",
    )
    need(not args.xfs_mounted or not (args.xfs_history or args.xfs_recovery), "Choose mounted, history or recovery")
    need(
        bool(args.mounted_object) == (args.xfs_mounted and not args.storage_readonly)
        and bool(args.xfs_db) == args.xfs_mounted,
        "Mounted mode requires xfs_db and, outside continuity cases, an independent object",
    )
    need(not args.storage_readonly or args.xfs_mounted, "Continuity requires mounted profile")
    need(bool(args.continuity_probe) == bool(args.storage_readonly), "Continuity requires the immutable probe")
    need(1 <= args.continuity_bytes <= 4096, "Continuity binary must fit one block")
    need(not args.recovery_owner_restart or args.xfs_recovery == "clean", "Owner restart requires clean recovery")
    need(not args.xfs_exchange or args.xfs_recovery, "Exchange requires explicit recovery")
    need(not (args.xfs_exchange and args.recovery_owner_restart), "Exchange owner restart is not qualified")
    need(not (args.xfs_history and args.xfs_recovery), "Choose history or recovery, not both")
    need(
        bool(args.xfs_image) == bool(args.xfs_history or args.xfs_recovery or args.xfs_mounted or args.xfs_nested),
        "Image requires explicit history, recovery or nested-directory outcome",
    )
    need(not args.xfs_image or args.nvme_prefix, "Linux clean profile requires the NVMe graphics model")
    args.build_dir = args.build_dir.resolve(strict=True)
    need(args.build_dir.name == "production" and args.renderer.is_file(), "production image and host painter")
    if args.nvme_prefix:
        evidence = ROOT / "build/program-console-evidence"
        evidence.mkdir(parents=True, exist_ok=True)
        if args.xfs_dual:
            for malformed in (2,) if args.dual_singleton else (0,) if args.dual_probe else (0, 1, 2):
                label = (
                    "singleton"
                    if args.dual_singleton
                    else f"probe-{args.dual_probe}"
                    if args.dual_probe
                    else str(malformed)
                )
                directory = Path(tempfile.mkdtemp(prefix=f"production-dual-{label}-", dir=evidence))
                print("Production dual-volume guest: " + str(directory), flush=True)
                screen_guest(args, directory, malformed=malformed)
            if args.dual_singleton:
                print(
                    "PASS: singleton readonly volume grant, reserved /disk2, exact client bytes and unchanged backing"
                )
            elif args.dual_probe:
                print(f"PASS: dual grant probe {args.dual_probe}, owner loss/retry, reclamation and unchanged backings")
            else:
                print("PASS: dual readonly namespaces, isolated malformed mounts, exact client bytes and framebuffer")
            return
        if args.xfs_mounted:
            if args.storage_readonly:
                need(args.continuity_probe.is_file(), "Continuity probe unavailable")
                args.mounted_bytes = bytes(range(256)) * (args.continuity_bytes // 256) + bytes(
                    range(args.continuity_bytes % 256)
                )
            else:
                fd = os.open(args.mounted_object, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as artifact:
                    facts = os.fstat(artifact.fileno())
                    need(stat.S_ISREG(facts.st_mode) and 0 < facts.st_size <= 4096, "Mounted object must fit one block")
                    args.mounted_bytes = artifact.read(4097)
                    need(
                        len(args.mounted_bytes) == facts.st_size
                        and args.mounted_bytes[:6] == b"\x7fELF\x02\x01"
                        and args.mounted_bytes[16:20] == b"\x01\x00\x3e\x00",
                        "Mounted reference must be x86-64 ET_REL",
                    )
            # Keep argv[0]'s name: pinned tool wrappers can dispatch by basename.
            args.xfs_db = args.xfs_db.absolute()
            need(args.xfs_db.is_file() and os.access(args.xfs_db, os.X_OK), "xfs_db metadata oracle unavailable")
            directory = Path(tempfile.mkdtemp(prefix="production-mounted-", dir=evidence))
            print("Production mounted guest: " + str(directory), flush=True)
            fd = os.open(args.xfs_image, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as original:
                facts = os.fstat(original.fileno())
                need(stat.S_ISREG(facts.st_mode) and facts.st_size == 512 * 1024 * 1024, "Mounted source extent/type")
                args.recovery_source_hash = hashlib.file_digest(original, "sha256").digest()
                need(
                    args.recovery_source_hash.hex() == MOUNTED_CLEAN_SHA256,
                    "Mounted smoke requires reviewed private pair",
                )
                try:
                    screen_guest(args, directory)
                    if not args.storage_readonly:
                        args.xfs_image = directory / "storage.raw"
                        cold = directory / "cold-readonly"
                        cold.mkdir()
                        screen_guest(args, cold, mounted_cold=True)
                finally:
                    original.seek(0)
                    need(
                        hashlib.file_digest(original, "sha256").digest() == args.recovery_source_hash,
                        "Held original mounted image changed",
                    )
            if args.storage_readonly:
                print(f"PASS: mounted readonly continuity {args.storage_readonly}, exact binary data and framebuffer")
            else:
                print("PASS: production compiler commit, xfsprogs metadata, readonly cold link/run and framebuffer")
            return
        if args.xfs_recovery:
            profile = "exchange-" if args.xfs_exchange else ""
            directory = Path(
                tempfile.mkdtemp(prefix=f"production-recovery-{profile}{args.xfs_recovery}-", dir=evidence)
            )
            print("Production recovery guest: " + str(directory), flush=True)
            fd = os.open(args.xfs_image, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as original:
                facts = os.fstat(original.fileno())
                need(stat.S_ISREG(facts.st_mode) and facts.st_size == 512 * 1024 * 1024, "Recovery source extent/type")
                args.recovery_source_hash = hashlib.file_digest(original, "sha256").digest()
                original.seek(0)
                sb = original.read(512)
                fixture = "xfs-root-exchange" if args.xfs_exchange else "xfs-core-redo"
                reference_sb = bytes.fromhex((ROOT / f"fixtures/{fixture}/superblock.hex").read_text())
                need(sb == reference_sb, "Recovery smoke requires the reviewed witness superblock/geometry")
                if args.xfs_recovery == "dirty":
                    expected_dirty = (
                        "a9f2c9d9e96a80d87b21730d14fc9e479db7ed18e3e4425b4d201e9669f8c49c"
                        if args.xfs_exchange
                        else "14786e316d191c2a399460a116952a773d197e52efec5c0c74ccc4f153c6c7c6"
                    )
                    need(
                        args.recovery_source_hash.hex() == expected_dirty,
                        "Dirty recovery smoke requires the reviewed Linux dirty witness",
                    )
                try:
                    screen_guest(args, directory, clean_storage=args.xfs_recovery != "refused")
                finally:
                    original.seek(0)
                    need(
                        hashlib.file_digest(original, "sha256").digest() == args.recovery_source_hash,
                        "Held original recovery image changed",
                    )
            print(
                f"PASS: production recovery {profile}{args.xfs_recovery}, "
                "private disk delta and command/framebuffer oracle"
            )
            return
        if args.xfs_image:
            profile = "nested" if args.xfs_nested else args.xfs_history
            directory = Path(tempfile.mkdtemp(prefix=f"production-storage-{profile}-", dir=evidence))
            print("Production Linux-history storage guest: " + str(directory), flush=True)
            screen_guest(args, directory, clean_storage=args.xfs_history != "dirty")
            print(f"PASS: production {profile} profile, command/framebuffer oracle and unchanged readonly disk")
            return
        directory = Path(tempfile.mkdtemp(prefix="production-storage-", dir=evidence))
        print("Production storage screen guest: " + str(directory), flush=True)
        screen_guest(args, directory)
        print("PASS: production NVMe/XFS commands, graphical terminal and unchanged readonly disk")
        rejected = Path(tempfile.mkdtemp(prefix="production-storage-unavailable-", dir=evidence))
        print("Production missing-clean-marker guest: " + str(rejected), flush=True)
        screen_guest(args, rejected, clean_storage=False)
        print("PASS: missing XFS clean marker refuses /disk, preserves RAM service and leaves disk unchanged")
        return
    pty_oracle = [sys.executable, "-B", str(ROOT / "tests/kernel-program-console-pty.py")]
    status = subprocess.run(pty_oracle + ["--mode", "program-console", "--build-dir", str(args.build_dir)]).returncode
    if status:
        raise SystemExit(status)
    # All hostile rows use the identical production kernel; only private ESP
    # payloads differ. Service rows exercise designated-owner failure, not a
    # rogue ordinary client or a production fault hook.
    for service_case in (
        None,
        "pair",
        "snapshot-read",
        "snapshot-close",
        "console-commit",
        "source-writer",
        "bootstrap-serve",
        "shutdown-fault",
    ):
        command = pty_oracle + [
            "--mode",
            "program-console",
            "--build-dir",
            str(args.build_dir),
            "--program-cases",
            str(args.build_dir.parents[2]),
        ]
        if service_case == "pair":
            command += ["--pair-cases"]
        elif service_case:
            command += ["--service-case", service_case]
        status = subprocess.run(command).returncode
        if status:
            raise SystemExit(status)
    evidence = ROOT / "build/program-console-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="production-screen-", dir=evidence))
    print("Production screen guest evidence: " + str(directory))
    screen_guest(args, directory)
    print("PASS: production program console commands over serial and its graphical terminal framebuffer")
    device_guests(args, directory)


if __name__ == "__main__":
    try:
        main()
    except Blocked as error:
        print("BLOCKED: production smoke: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (Exception, KeyboardInterrupt) as error:
        raise SystemExit(transport.failure_label(error) + ": production smoke: " + str(error)) from error

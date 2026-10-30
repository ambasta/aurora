#!/usr/bin/env python3
"""Disposable NVMe: protected raw I/O or the retained process service reading XFS.

Requires the patched AMD-Vi model built with CONFIG_NVME_PCI and the clean
no-NvmExpressDxe firmware. The clean-XFS row copies an explicit regular-file
history into its private workspace; no caller file or block device is attached.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
import time

from kernel_iommu_event_smoke import raw_esp
import qemu_transport as transport

ROOT = Path(__file__).resolve().parents[1]
need = transport.need


def command(
    runtime,
    firmware,
    esp,
    disk,
    variables,
    *,
    serial,
    extra,
    readonly=False,
    debug_exit=False,
    memory=None,
    graphics=False,
):
    """Closed six-function storage profile, or its explicit seven-function standard-VGA composition."""
    return transport.command(
        runtime / "bin/qemu-system-x86_64",
        runtime / "share/qemu",
        firmware=transport.firmware_args(code=str(firmware / "OVMF_CODE.fd"), variables=str(variables)),
        boot=["-drive", f"if=none,id=boot,format=raw,file={esp}"],
        peripherals=[
            "-nodefaults",
            "-no-user-config",
            "-device",
            "ide-hd,drive=boot,bus=ide.0",
            "-device",
            "amd-iommu",
            "-drive",
            "if=none,id=storage,format=raw,cache=writeback,aio=threads,"
            f"readonly={'on' if readonly else 'off'},file={disk}",
            "-device",
            "nvme,addr=02.0,drive=storage,serial=AURORA-DISPOSABLE,max_ioqpairs=1,msix_qsize=1,mqes=1",
            *(["-device", "VGA,addr=03.0,vgamem_mb=16,romfile=,rombar=0"] if graphics else []),
        ],
        serial=serial,
        debug_exit=debug_exit,
        memory=memory,
        extra=extra,
    )


def run_case(case, runtime, firmware, esp, disk, work):
    work.mkdir()
    variables = work / "vars.fd"
    shutil.copyfile(firmware / "OVMF_VARS.fd", variables)
    serial_read, serial_write = os.pipe()
    argv = command(
        runtime,
        firmware,
        esp,
        disk,
        variables,
        serial="chardev:guestserial",
        extra=[
            "-boot",
            "order=c",
            "-add-fd",
            f"fd={serial_write},set=1,opaque=serial-pipe",
            "-chardev",
            "file,id=guestserial,path=/dev/fdset/1,append=on",
            "-qmp",
            "stdio",
        ]
        + (["-fw_cfg", f"name=opt/aurora/case,string={case}"] if case else []),
    )
    process = transport.start(
        argv,
        cwd=work,
        env=os.environ.copy(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        pass_fds=(serial_write,),
    )
    os.close(serial_write)
    serial_stream = os.fdopen(serial_read, "rb", buffering=0)
    serial, stderr = bytearray(), bytearray()
    watched = selectors.DefaultSelector()
    deadline = time.monotonic() + 45
    qmp_log = (work / "qmp.log").open("wb")
    try:
        for stream, label in ((serial_stream, "serial"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            watched.register(stream, selectors.EVENT_READ, label)
        while True:
            transport.remaining(deadline)
            for key, _ in watched.select(min(0.05, deadline - time.monotonic())):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    watched.unregister(key.fileobj)
                    continue
                target = serial if key.data == "serial" else stderr
                need(len(target) + len(data) <= transport.MAX_IO, "Guest output limit")
                target.extend(data)
            terminal = re.search(rb"AURORA_NVME_TERMINAL: [^\r\n]*\r\n", serial)
            failure = re.search(rb"AURORA_[^\r\n]*(?:FAIL|EXCEPTION|REJECTED|QUARANTINED)[^\r\n]*\r\n", serial)
            # Range rejection is the intended successful pre-submit negative row.
            if failure and failure.group(0).startswith(b"AURORA_NVME_RANGE_REJECTED:"):
                failure = re.search(rb"AURORA_[^\r\n]*(?:FAIL|EXCEPTION|QUARANTINED)[^\r\n]*\r\n", serial)
            if terminal or failure:
                break
            need(not transport.exited(process), "Guest exited before terminal: " + stderr.decode(errors="replace"))
        qmp = transport.Qmp(process, deadline, qmp_log)
        need(qmp.command("stop") == {}, "QMP stop")
        need(qmp.command("query-status").get("status") == "paused", "QEMU pause")
        need(qmp.command("quit") == {}, "QMP quit")
        need(transport.reap_completed(process, deadline) == 0, "QEMU exit status")
        need(not stderr, "QEMU diagnostics: " + stderr.decode(errors="replace"))
        text = serial.decode("utf-8", errors="replace")
        need("AURORA_NVME_ADMISSION_OK: default-ivrs=1 cold=1 handoff-complete=1" in text, "NVMe admission")
        need("AURORA_NVME_READY: nsid=1 blocks=16384 lba-bytes=512 queue-entries=2" in text, "Identify/queues")
        if case == 3:
            need(
                not terminal
                and "AURORA_NVME_COMPLETION_ERROR: status=16385" in text
                and "AURORA_NVME_QUARANTINED: reason=completion exposed=1 completed=5 retained=boot" in text,
                "Invalid opcode must quarantine with exact Invalid Command Opcode+DNR status",
            )
        else:
            need(not failure, "Guest failure: " + (failure.group(0).decode() if failure else ""))
            count = {0: 6, 1: 9, 2: 6, 4: 5}[case]
            need(
                f"AURORA_NVME_TERMINAL: case={case} completed={count} flushed={int(case == 1)}" in text,
                "Exact terminal counts",
            )
            need(
                "AURORA_NVME_REVOKED: controller-ready=0 bme=0 invalidation=1 retained=boot" in text,
                "NVMe shutdown/revocation",
            )
            if case in (0, 1, 2):
                need(f"AURORA_NVME_READ: lba=7 bytes=512 pattern={int(case == 2)}" in text, "Read data")
            if case == 1:
                need(
                    "AURORA_NVME_FLUSH: completed=1" in text and "AURORA_NVME_READ: lba=7 bytes=512 pattern=1" in text,
                    "Write/Flush/read",
                )
            if case == 4:
                need("AURORA_NVME_RANGE_REJECTED: submitted=0" in text, "Out-of-range pre-submit rejection")
    finally:
        errors, _, unsettled = transport.finish(
            process,
            drains=[watched.close],
            streams=[serial_stream, qmp_log, process.stdin, process.stdout, process.stderr],
        )
        (work / "serial.log").write_bytes(serial)
        (work / "stderr.log").write_bytes(stderr)
        need(not errors and not unsettled, "QEMU cleanup: " + "; ".join(errors))


def file_hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").digest()


def copy_xfs_history(source, destination):
    """Hold the caller's regular file read-only while making a new private test copy."""
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as original:
        before = os.fstat(original.fileno())
        need(
            stat.S_ISREG(before.st_mode) and before.st_size == 512 * 1024 * 1024,
            "XFS history must be a 512MiB regular file",
        )
        with destination.open("xb") as copied:
            remaining = before.st_size
            while remaining:
                block = original.read(min(remaining, 1024 * 1024))
                need(block, "XFS history shortened during copy")
                if block.strip(b"\0"):
                    copied.write(block)
                else:
                    copied.seek(len(block), os.SEEK_CUR)
                remaining -= len(block)
            copied.truncate(before.st_size)
            need(not original.read(1), "XFS history grew during copy")
        after = os.fstat(original.fileno())
        need(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "XFS history changed during copy",
        )
    return destination


def mounted_write_plan(path):
    """Read the source builder's 16 fixed LBA/Flush/sector records, never replay XFS in Python."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size == 16 * 528, "Mounted plan extent")
        raw = stream.read(16 * 528 + 1)
        after = os.fstat(stream.fileno())
        need(len(raw) == 16 * 528, "Mounted plan length")
        need(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "Mounted plan changed while reading",
        )
    plan = []
    for offset in range(0, len(raw), 528):
        lba = int.from_bytes(raw[offset : offset + 8], "little")
        flush = int.from_bytes(raw[offset + 8 : offset + 16], "little")
        need(lba < 1048576 and flush in (0, 1), "Mounted plan command bounds")
        plan.append((lba, flush, raw[offset + 16 : offset + 528]))
    need(
        [i + 1 for i, (_, flush, _) in enumerate(plan) if flush] == [10, 12, 14, 15, 16], "Mounted plan fence schedule"
    )
    return raw, plan


def mounted_pair_reference(path, prefix):
    """Bind the actual cut to reviewed command bytes, not a Python XFS replay."""
    import lzma

    raw, plan = mounted_write_plan(path)
    fixture = ROOT / "fixtures/xfs-staged-replace"
    hashes = json.loads((fixture / "append-hashes.json").read_text())
    need(
        hashlib.sha256(raw).hexdigest() == hashes["append-writes.hex"],
        "Pair plan differs from reviewed 777-byte payload",
    )
    need(0 <= prefix <= 16, "Pair completed-command prefix")
    archive = fixture / "append-clean.img.xz"
    need(hashlib.sha256(archive.read_bytes()).hexdigest() == hashes[archive.name], "Pair archive identity")
    replacement = {lba: data for lba, _, data in plan[:prefix]}
    original_hash, expected_hash = hashlib.sha256(), hashlib.sha256()
    position = 0
    with lzma.open(archive, "rb") as source:
        while chunk := source.read(1024 * 1024):
            original_hash.update(chunk)
            result = bytearray(chunk)
            for lba, sector in replacement.items():
                offset = lba * 512 - position
                if 0 <= offset < len(result):
                    result[offset : offset + 512] = sector
            expected_hash.update(result)
            position += len(chunk)
    need(position == 536870912 and original_hash.hexdigest() == hashes["append-clean.img"], "Pair clean image identity")
    # This inode is independently Linux-replayed at the identical authored LSN.
    linux_home = bytes.fromhex((fixture / "append-stage-linux.hex").read_text())
    need(hashlib.sha256(linux_home).hexdigest() == hashes["append-stage-linux.hex"], "Pair Linux home identity")
    need(plan[12][0] == 100 and plan[12][2] == linux_home and plan[13][0] == 96, "Pair authored home plan")
    return raw, plan, expected_hash.digest()


def run_process_xfs(
    runtime,
    firmware,
    image,
    work,
    *,
    history=None,
    expected_history=None,
    recover=False,
    recovery_state="dirty",
    recovery_cut=None,
    recovery_reference=None,
    recovery_exchange=False,
    recovery_pair_prefix=None,
    mounted=False,
    mounted_small=False,
    mounted_loss=False,
    mounted_cut=None,
    mounted_reference=None,
):
    from kernel_profiles import GUEST_TIMEOUTS, PROCESS_MEMORY, fw_cfg_fixture
    from xfs_image import create_image

    pair = recovery_pair_prefix is not None
    mode = (
        "process-xfs-recover-pair"
        if pair
        else "process-xfs-mounted-loss"
        if mounted_loss
        else "process-xfs-mounted-small"
        if mounted_small
        else "process-xfs-mounted"
        if mounted
        else "process-xfs-recover"
        if recover
        else "process-xfs-clean"
        if history is not None
        else "process-xfs"
    )
    writable = recover or mounted
    disk = (
        copy_xfs_history(history, work / "storage.raw") if history is not None else create_image(work / "storage.raw")
    )
    before = file_hash(disk)
    exchange_completed = "f13d816ddf9fa68eb6eccdf95136d993a0ac032fe471366f4a49ad60cc33d4c5"
    home_lbas = (96,) if recovery_exchange else (99, 100)
    completion_lbas = (524349, 524350) if recovery_exchange else (524335, 524336)
    if pair:
        home_lbas = (96, 99, 100)
    if recovery_exchange:
        fixture = ROOT / "fixtures/xfs-root-exchange/reverse"
        with disk.open("rb") as source:
            need(
                source.read(512) == bytes.fromhex((fixture / "superblock.hex").read_text()),
                "Reverse exchange witness superblock",
            )
        if recovery_state == "dirty":
            need(
                before.hex() == "a8d27f6c54fa4cabd1346ba0b7724888783c88fadd2e9174a6b154973e7196b1",
                "Dirty reverse exchange requires the genuine Linux witness",
            )
    baseline = work / "before.raw"
    if writable:
        # Preserve exact private before bytes; only storage.raw is attached.
        # The caller's original is never opened writable or given to QEMU.
        copy_xfs_history(disk, baseline)
    # Admit and snapshot the expected changed sectors before any guest can
    # write. Later reference-path failures cannot hide captured disk facts.
    reference_hash = hashlib.sha256()
    reference_sectors = {}
    mounted_plan = []
    if pair:
        raw, mounted_plan, expected_input = mounted_pair_reference(mounted_reference, recovery_pair_prefix)
        need(before == expected_input, "Pair input differs from exact acknowledged command prefix")
        reference_hash.update(raw)
        (work / "mounted-plan.bin").write_bytes(raw)
    if mounted:
        raw, mounted_plan = mounted_write_plan(mounted_reference)
        reference_hash.update(raw)
        (work / "mounted-plan.bin").write_bytes(raw)
        prefix = len(mounted_plan)
        if mounted_cut:
            operation, ordinal = mounted_cut.split("-")
            ordinal = int(ordinal)
            prefix = (
                ordinal
                if operation == "write"
                else [i + 1 for i, (_, flush, _) in enumerate(mounted_plan) if flush][ordinal - 1]
            )
        reference_sectors = {lba: data for lba, _, data in mounted_plan[:prefix]}
    if recovery_cut:
        fd = os.open(recovery_reference, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as reference:
            facts = os.fstat(reference.fileno())
            need(stat.S_ISREG(facts.st_mode) and facts.st_size == 512 * 1024 * 1024, "Recovery reference extent")
            position = 0
            while chunk := reference.read(1024 * 1024):
                reference_hash.update(chunk)
                for lba in (*home_lbas, *completion_lbas):
                    offset = lba * 512 - position
                    if 0 <= offset < len(chunk):
                        reference_sectors[lba] = chunk[offset : offset + 512]
                position += len(chunk)
            after = os.fstat(reference.fileno())
            need(
                position == facts.st_size and len(reference_sectors) == len(home_lbas) + 2,
                "Recovery reference length",
            )
            need(
                (facts.st_dev, facts.st_ino, facts.st_size, facts.st_mtime_ns, facts.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "Recovery reference changed",
            )
        need(
            not recovery_exchange or reference_hash.hexdigest() == exchange_completed,
            "Reverse cut reference differs from the independently accepted completion",
        )
    esp, variables = work / "esp.raw", work / "vars.fd"
    raw_esp(image / "esp", esp)
    shutil.copyfile(firmware / "OVMF_VARS.fd", variables)
    argv = command(
        runtime,
        firmware,
        esp,
        disk,
        variables,
        serial="stdio",
        extra=["-boot", "order=c", *fw_cfg_fixture(mode, recovery_cut=recovery_cut, mounted_cut=mounted_cut)],
        readonly=not writable,
        debug_exit=True,
        memory=PROCESS_MEMORY[mode],
    )
    log, errors = work / (mode + ".log"), work / "stderr.log"
    unsettled = False
    try:
        with errors.open("xb") as diagnostics:
            status = transport.run_logged(
                argv,
                log,
                cwd=work,
                env=os.environ.copy(),
                timeout=GUEST_TIMEOUTS.get(mode, 60),
                stderr=diagnostics,
            )
    except transport.ChildNotReaped:
        unsettled = True
        raise
    finally:
        # The private file has no other writer; O_RDONLY additionally prevents
        # the emulator from modifying it, even after a guest/controller fault.
        if not unsettled and not writable:
            need(file_hash(disk) == before, "Readonly XFS image changed")
    text = log.read_text()
    print(text, end="")
    if writable:
        changed = set()
        before_hash, after_hash = hashlib.sha256(), hashlib.sha256()
        homes = {}
        mismatched_reference = []
        with baseline.open("rb") as old, disk.open("rb") as new:
            lba = 0
            while first := old.read(1024 * 1024):
                second = new.read(len(first))
                need(len(second) == len(first), "Recovery disk extent changed")
                before_hash.update(first)
                after_hash.update(second)
                for offset in range(0, len(first), 512):
                    sector = lba + offset // 512
                    data = second[offset : offset + 512]
                    if first[offset : offset + 512] != data:
                        changed.add(sector)
                        if recovery_cut and data != reference_sectors.get(sector):
                            mismatched_reference.append(sector)
                    if mounted and data != reference_sectors.get(sector, first[offset : offset + 512]):
                        mismatched_reference.append(sector)
                    if sector in home_lbas:
                        homes[sector] = data
                lba += len(first) // 512
            need(not new.read(1), "Recovery disk grew")
        # Preserve facts even if subsequent semantic validation refuses the run.
        (work / "image-delta.json").write_text(
            json.dumps(
                {
                    "state": mode if mounted or pair else recovery_state,
                    "mounted_recovery_prefix": recovery_pair_prefix,
                    "exchange": recovery_exchange,
                    "completed_boundary_cut": mounted_cut if mounted else recovery_cut,
                    "reference_sha256": reference_hash.hexdigest() if recovery_cut or mounted or pair else None,
                    "mismatched_reference_sectors": mismatched_reference,
                    "before_sha256": before_hash.hexdigest(),
                    "after_sha256": after_hash.hexdigest(),
                    "changed_sectors": sorted(changed),
                },
                indent=2,
            )
            + "\n"
        )
    need(not errors.stat().st_size, "QEMU diagnostics: " + errors.read_text())
    need(text.count("AURORA_NVME_ADMISSION_OK: default-ivrs=1 cold=1 handoff-complete=1") == 1, "NVMe admission")
    ready = f"AURORA_NVME_READY: nsid=1 blocks={disk.stat().st_size // 512} lba-bytes=512 queue-entries=2"
    need(text.count(ready) == 1 and "AURORA_NVME_QUARANTINED:" not in text, "Readonly namespace/queues")
    spec = importlib.util.spec_from_file_location("kernel_process_smoke", ROOT / "tests/kernel-process-smoke.py")
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    if pair:
        from kernel_profiles import mounted_recovery_outcome

        _, _, target, expected_changes = mounted_recovery_outcome(recovery_pair_prefix)
        need(before_hash.digest() == before and file_hash(history) == before, "Pair original or baseline changed")
        need(changed == expected_changes, "Pair recovery changed sectors: " + str(sorted(changed)))
        if recovery_pair_prefix >= 10:
            # Same-LSN independent Linux replay golden, checked when reading the plan.
            need(homes[100] == mounted_plan[12][2], "Pair stage home differs from Linux")
        if recovery_pair_prefix >= 12:
            # Authored-plan root oracle, not an independent Linux replay claim.
            need(homes[96] == mounted_plan[13][2], "Pair root differs from authored plan")
        oracle.validate(status, text, mode, image, recovery_pair_prefix=recovery_pair_prefix)
        print(
            f"PASS: {mode} prefix={recovery_pair_prefix} target={target}; exact bounded delta; retained {disk}",
            flush=True,
        )
    elif recover:
        need(not mismatched_reference, "Cut sectors differ from qualified completed output")
        need(before_hash.digest() == before, "Private recovery baseline changed")
        expected_changes = {
            "dirty": {99, 100, 524335, 524336},
            "clean": set(),
            "orphan": {524335},
            "partial-99": {100, 524335, 524336},
            "partial-100": {99, 524335, 524336},
            "partial-both": {524335, 524336},
            "refused": set(),
        }
        if recovery_exchange:
            expected_changes = {
                "dirty": {96, 524349, 524350},
                "clean": set(),
                "orphan": {524349},
                "partial-root": {524349, 524350},
                "refused": set(),
            }
        if recovery_cut:
            expected_changes[recovery_state] = {
                "write-1": {home_lbas[0]},
                "flush-1": set(home_lbas),
                "flush-2": {*home_lbas, completion_lbas[1]},
                "flush-3": {*home_lbas, *completion_lbas},
            }[recovery_cut]
        need(changed == expected_changes[recovery_state], "Recovery changed sectors: " + str(sorted(changed)))
        if recovery_state != "refused":
            for inode in home_lbas[:1] if recovery_cut == "write-1" else home_lbas:
                # Reviewed Linux output, never a Python replay implementation.
                path = (
                    "fixtures/xfs-root-exchange/reverse/root-after.hex"
                    if recovery_exchange
                    else f"fixtures/xfs-core-redo/inode-{inode}-after.hex"
                )
                expected = bytes.fromhex((ROOT / path).read_text())
                need(homes[inode] == expected, "Recovery home differs from Linux golden")
        if recovery_exchange and recovery_state != "refused" and not recovery_cut:
            need(
                after_hash.hexdigest() == exchange_completed,
                "Reverse recovery differs from the independently accepted complete image",
            )
        oracle.validate(
            status,
            text,
            mode,
            image,
            recovery_state=recovery_state,
            recovery_cut=recovery_cut,
            recovery_exchange=recovery_exchange,
        )
        print(f"PASS: {mode} {recovery_state}; changed sectors {sorted(changed)}; retained {disk}", flush=True)
    elif mounted:
        need(before_hash.digest() == before, "Private mounted baseline changed")
        need(
            not mismatched_reference,
            "Mounted image differs from exact source-plan prefix: " + str(mismatched_reference),
        )
        oracle.validate(status, text, mode, image, mounted_cut=mounted_cut, mounted_plan=mounted_plan)
        print(f"PASS: {mode}; exact source-plan prefix; changed sectors {sorted(changed)}; retained {disk}", flush=True)
    else:
        oracle.validate(status, text, mode, image, xfs_history=expected_history)
        print(f"PASS: {mode}; entire readonly XFS image unchanged", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-prefix", default=os.environ.get("NVME_TOOL_PREFIX", ""))
    parser.add_argument("--build-only", action="store_true")
    process_mode = parser.add_mutually_exclusive_group()
    process_mode.add_argument(
        "--process-xfs", action="store_true", help="boot the process image's fresh XFS service row"
    )
    process_mode.add_argument(
        "--process-xfs-clean", type=Path, metavar="IMAGE", help="copy a 512MiB XFS history and boot case11 read-only"
    )
    process_mode.add_argument(
        "--process-xfs-recover",
        type=Path,
        metavar="IMAGE",
        help="copy the dirty Linux CORE witness and boot private case12 with writes only to the copy",
    )
    process_mode.add_argument(
        "--process-xfs-mounted",
        type=Path,
        metavar="IMAGE",
        help="copy a clean XFS pair and exercise one mounted source-owned replacement",
    )
    mounted_mode = parser.add_mutually_exclusive_group()
    mounted_mode.add_argument(
        "--mounted-loss",
        action="store_true",
        help="inject source-owner termination after final Flush and verify RAM-only restart",
    )
    mounted_mode.add_argument(
        "--mounted-small", action="store_true", help="replace the prior 777-byte result with 113 bytes"
    )
    mounted_mode.add_argument(
        "--mounted-cut",
        choices=tuple(f"write-{n}" for n in range(1, 17)) + tuple(f"flush-{n}" for n in range(1, 6)),
        help="stop after one acknowledged mounted command boundary",
    )
    parser.add_argument("--mounted-reference", type=Path, help="exact source-emitted ordered write plan")
    parser.add_argument(
        "--recovery-pair-prefix",
        type=int,
        choices=range(17),
        help="recover a reviewed mounted777 command prefix through case41 and ordinary HostFiles",
    )
    parser.add_argument(
        "--recovery-state",
        choices=("dirty", "clean", "orphan", "partial-99", "partial-100", "partial-both", "partial-root", "refused"),
        help="expected private recovery fixture state; partial/orphan inputs are modeled, not observed crashes",
    )
    parser.add_argument(
        "--recovery-exchange", action="store_true", help="expect the root-only reverse name-exchange witness"
    )
    parser.add_argument(
        "--recovery-cut",
        choices=("write-1", "flush-1", "flush-2", "flush-3"),
        help="private completed-command boundary interruption; never physical power-loss evidence",
    )
    parser.add_argument(
        "--recovery-reference", type=Path, help="read-only qualified completed image for exact cut-prefix comparison"
    )
    parser.add_argument(
        "--xfs-history",
        choices=("used", "wrapped", "dirty"),
        help="expected clean-XFS test outcome, not image provenance",
    )
    parser.add_argument("--run-only", type=Path, help="already-built exact image directory; never invokes Ninja")
    parser.add_argument("--output-dir", type=Path, help="fresh output directory, retained even after success")
    args = parser.parse_args()
    need(
        bool(args.process_xfs_clean) == bool(args.xfs_history),
        "Clean XFS requires both an explicit image and expected --xfs-history",
    )
    need(
        args.process_xfs_recover is not None or args.recovery_state is None,
        "Recovery state requires --process-xfs-recover",
    )
    need(not args.recovery_exchange or args.process_xfs_recover is not None, "Exchange requires recovery")
    pair = args.recovery_pair_prefix is not None
    need(
        not pair
        or (
            args.process_xfs_recover is not None
            and args.recovery_state is None
            and not args.recovery_exchange
            and args.recovery_cut is None
        ),
        "Pair prefix requires recovery without legacy witness/cut options",
    )
    need(
        args.recovery_state in (None, "dirty", "clean", "orphan", "partial-root", "refused")
        if args.recovery_exchange
        else args.recovery_state != "partial-root",
        "Recovery state does not apply to the selected witness",
    )
    need(
        args.recovery_cut is None or (args.process_xfs_recover is not None and args.recovery_state in (None, "dirty")),
        "Recovery cut requires a dirty private recovery fixture",
    )
    need(bool(args.recovery_cut) == bool(args.recovery_reference), "Cut requires exact completed reference")
    need(not args.mounted_loss or args.process_xfs_mounted is not None, "Owner loss requires mounted image")
    need(not args.mounted_small or args.process_xfs_mounted is not None, "Small replacement requires mounted image")
    need(
        not args.mounted_cut or (args.process_xfs_mounted is not None and not args.mounted_small),
        "Cuts require first mounted replacement",
    )
    need(
        bool(args.mounted_reference) == bool(args.process_xfs_mounted or pair),
        "Mounted/pair image requires exact source write plan",
    )
    process_xfs = (
        args.process_xfs
        or args.process_xfs_clean is not None
        or args.process_xfs_recover is not None
        or args.process_xfs_mounted is not None
    )
    mode = (
        "process-xfs-recover-pair"
        if pair
        else "process-xfs-mounted-loss"
        if args.mounted_loss
        else "process-xfs-mounted-small"
        if args.mounted_small
        else "process-xfs-mounted"
        if args.process_xfs_mounted
        else "process-xfs-recover"
        if args.process_xfs_recover
        else "process-xfs-clean"
        if args.process_xfs_clean
        else "process-xfs"
        if args.process_xfs
        else "nvme"
    )
    profile = "process-fixture" if process_xfs else "nvme"
    if args.run_only:
        image = args.run_only.resolve(strict=True)
        need(image.is_dir() and image.parts[-3:] == ("kernel-images", "uefi", profile), "Wrong image profile")
    else:
        built = subprocess.run(
            [ROOT / "scripts/kernel-image.sh", "uefi", mode], cwd=ROOT, capture_output=True, text=True
        )
        need(built.returncode == 0, "NVMe image build:\n" + built.stderr[-6000:])
        image = Path(built.stdout.strip())
    if args.build_only:
        print("Built " + str(image))
        return
    runtime = transport.input_path(args.tool_prefix, "NVMe model prefix", directory=True)
    transport.input_path(runtime / "bin/qemu-system-x86_64", "NVMe model")
    fixture = transport.required(os.environ, "AURORA_BOOT_FIXTURE_PREFIX", "clean NVMe firmware prefix")
    firmware = transport.input_path(Path(fixture) / "firmware", "clean firmware", directory=True)
    if args.output_dir:
        scratch = args.output_dir.resolve()
        need(
            not scratch.exists() and image != scratch and image not in scratch.parents,
            "Output must be fresh and outside image",
        )
        scratch.mkdir()
    else:
        scratch = Path(tempfile.mkdtemp(prefix="aurora-nvme-", dir=ROOT / "build"))
    print("Disposable NVMe workspace: " + str(scratch), flush=True)
    need(not any(char in str(scratch) for char in ",\r\n"), "Unsupported QEMU workspace path")
    if process_xfs:
        run_process_xfs(
            runtime,
            firmware,
            image,
            scratch,
            history=args.process_xfs_mounted or args.process_xfs_recover or args.process_xfs_clean,
            expected_history=args.xfs_history,
            recover=args.process_xfs_recover is not None,
            recovery_state=args.recovery_state or "dirty",
            recovery_cut=args.recovery_cut,
            recovery_reference=args.recovery_reference,
            recovery_exchange=args.recovery_exchange,
            recovery_pair_prefix=args.recovery_pair_prefix,
            mounted=args.process_xfs_mounted is not None,
            mounted_small=args.mounted_small,
            mounted_loss=args.mounted_loss,
            mounted_cut=args.mounted_cut,
            mounted_reference=args.mounted_reference,
        )
        if not args.output_dir and not args.process_xfs_recover and not args.process_xfs_mounted:
            shutil.rmtree(scratch)
        return
    esp, disk = scratch / "esp.raw", scratch / "storage.raw"
    raw_esp(image / "esp/EFI/BOOT/BOOTX64.EFI", esp)
    expected = bytearray(8 * 1024 * 1024)
    expected[7 * 512 : 8 * 512] = bytes((i * 29 + 0x3D) & 255 for i in range(512))
    # Only newly created files beneath this driver's private workspace are writable disks.
    with disk.open("xb") as stream:
        stream.write(expected)
    for case in (0, 1, 2, 4, 3):
        run_case(case, runtime, firmware, esp, disk, scratch / f"case-{case}")
        if case == 1:
            expected[7 * 512 : 8 * 512] = bytes((i * 29 + 0xB7) & 255 for i in range(512))
        need(disk.read_bytes() == expected, "Exact raw contents and unchanged neighbouring LBAs")
        print(f"PASS: NVMe case {case}", flush=True)
    if not args.output_dir:
        shutil.rmtree(scratch)


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(transport.failure_label(error) + ": NVMe smoke: " + str(error), file=sys.stderr)
        raise SystemExit(2 if isinstance(error, transport.MissingPrerequisite) else 1)

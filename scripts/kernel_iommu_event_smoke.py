#!/usr/bin/env python3
"""Opt-in current-source Event developer smoke; never independent qualification."""

import argparse
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time

import kernel_iommu_event_esp as esp
import kernel_iommu_event_oracle as oracle
import kernel_uefi_oracle as normal
from kernel_elf import Elf
import qemu_transport as transport
import smoke_outputs
from qemu_transport import ChildNotReaped, Qmp, exited, reap_completed
from qemu_transport import MissingPrerequisite as PrerequisiteBlocked
from owned_outputs import allocated_bytes
from kernel_layout import LAYOUT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUILD = None
# iommu-event-observe is a read-only build profile without a guest capture fixture.
MODES = ("iommu-event-denial", "iommu-event-success", "iommu-event-overflow", "iommu-event-command-error")
STREAM_LIMIT = 1024 * 1024
EVIDENCE_LIMIT = 1024**3
FREE_FLOOR = 1024**3
RUN_MARKER = ".event-smoke-run.json"
# Linked symbol, exact bytes and alignment of each allocation the guest retains for capture.
RETAINED = {
    "terminal": ("uefi_event_terminal", 672, 8),
    "backing": ("uefi_event_backing", 32768, 4096),
    "ring": ("_ZN6aurora11iommu_event16BootLifetimeRing6bytes_E", 4096, 4096),
    "before_ring": ("uefi_event_before_ring", 4096, 4096),
    "after_ring": ("uefi_event_after_ring", 4096, 4096),
}
SHT_NOBITS = 8
SHF_WRITE_ALLOC = 3
need = esp.need
json_object = oracle.json_object


def safe_path(value, *, directory=False):
    path = Path(value).absolute()
    need(not any(c in str(path) for c in (",", "\n", "\r", "\0", '"')), "Unsafe QEMU path")
    need(path.resolve(strict=True) == path, "Symlink path: " + str(path))
    need(path.is_dir() if directory else stat.S_ISREG(path.lstat().st_mode), "Not a regular input: " + str(path))
    return path


def identity(path):
    path = esp.regular(path)
    return dict(bytes=path.stat().st_size, sha256=esp.sha256(path))


def write_json(path, record):
    path.write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n")


def read_json(path):
    path = esp.regular(path)
    need(path.stat().st_size <= 4 * 1024**2, "Manifest size limit")
    return json_object(path.read_bytes())


# The packaged runtime must provide the command-stop AMD-Vi model the oracle expects.
PACKAGE_MARKER = dict(schema="aurora-event-runtime-v1", model="aurora-amdvi-command-stop-v1")


def packaged_runtime(prefix):
    """The selected package is the tool trust boundary; this is not attestation."""
    prefix = safe_path(prefix, directory=True)
    marker = read_json(prefix / "runtime.json")
    need({key: marker.get(key) for key in PACKAGE_MARKER} == PACKAGE_MARKER, "Unsupported packaged Event model")
    qemu = safe_path(prefix / "bin/qemu-system-x86_64")
    need(os.access(qemu, os.X_OK), "Packaged Event QEMU is not executable")
    firmware = {
        role: str(safe_path(prefix / "firmware" / filename))
        for role, filename in (("code", "OVMF_CODE_4M.fd"), ("vars", "OVMF_VARS_4M.fd"))
    }
    libraries = [safe_path(prefix / name, directory=True) for name in ("lib", "lib64") if (prefix / name).exists()]
    return dict(
        qemu=str(qemu),
        data=str(safe_path((prefix / "share/qemu").resolve(strict=True), directory=True)),
        library_path=":".join(str(path) for path in libraries),
        **firmware,
    )


def runtime_inputs(args):
    """Select a trusted user-supplied Event QEMU build, like the compiler toolchain."""
    if getattr(args, "tool_prefix", None):
        return packaged_runtime(args.tool_prefix)
    build = read_json(safe_path(args.build_receipt))
    binary = safe_path(build["binary_path"])
    need(os.access(binary, os.X_OK), "Custom Event QEMU is not executable")
    library_dirs = read_json(safe_path(build["runtime_library_manifest"]["path"]))["LD_LIBRARY_PATH"]
    need(type(library_dirs) is str, "Invalid library path")
    for path in library_dirs.split(":") if library_dirs else []:
        safe_path(path, directory=True)
    return dict(
        qemu=str(binary),
        code=str(safe_path(args.code)),
        vars=str(safe_path(args.vars)),
        data=str(safe_path(args.data, directory=True)),
        library_path=library_dirs,
    )


def environment(directory, runtime):
    return dict(
        PATH="/usr/bin:/bin",
        HOME=str(directory / "home"),
        LANG="C",
        LC_ALL="C",
        TZ="UTC",
        LD_LIBRARY_PATH=runtime["library_path"],
        QEMU_MODULE_DIR=str(directory / "no-modules"),
    )


def command(runtime, directory, serial_fd):
    need(type(serial_fd) is int and serial_fd >= 3, "Invalid owned serial FD")
    for key in ("qemu", "data", "code"):
        safe_path(runtime[key], directory=key == "data")
    for name in ("vars.fd", "esp.raw"):
        safe_path(directory / name)
    return transport.command(
        runtime["qemu"],
        runtime["data"],
        firmware=[
            "-drive",
            "if=pflash,format=raw,unit=0,readonly=on,file=" + runtime["code"],
            "-drive",
            "if=pflash,format=raw,unit=1,file=" + str(directory / "vars.fd"),
        ],
        boot=["-drive", "if=none,id=boot,format=raw,file=" + str(directory / "esp.raw")],
        peripherals=[
            "-nodefaults",
            "-no-user-config",
            "-device",
            "ide-hd,drive=boot,bus=ide.0",
            "-device",
            "amd-iommu",
            "-device",
            "edu,addr=04.0",
        ],
        serial="chardev:guestserial",
        extra=[
            "-boot",
            "order=c",
            "-qmp",
            "stdio",
            "-add-fd",
            f"fd={serial_fd},set=1,opaque=owned-serial-pipe",
            "-chardev",
            "file,id=guestserial,path=/dev/fdset/1,append=on",
        ],
    )


def child_limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def copy_private(source, destination, digest=None):
    source = esp.regular(source)
    need(not os.path.lexists(destination), "Private destination exists")
    with source.open("rb") as left, destination.open("xb") as right:
        shutil.copyfileobj(left, right)
    destination.chmod(0o600)
    need(digest is None or esp.sha256(destination) == digest, "Private copy identity mismatch")


def capture_guest(mode, receipt, runtime, master, directory, *, master_sha256):
    need(mode in MODES, "Unknown Event profile")
    captures = oracle.capture_layout(receipt)
    safe_path(directory.parent, directory=True)
    need(
        shutil.disk_usage(directory.parent).free >= FREE_FLOOR + esp.IMAGE_BYTES + 8 * STREAM_LIMIT,
        "Event guest disk reservation failed",
    )
    directory.mkdir(mode=0o700)
    for name in ("home", "no-modules"):
        (directory / name).mkdir(mode=0o700)
    # Only writable guest VARS is copied; tools and read-only CODE stay in place.
    copy_private(runtime["vars"], directory / "vars.fd")
    copy_private(master, directory / "esp.raw", master_sha256)
    process = serial_stream = serial_read = serial_write = None
    outputs, captured, errors = {}, {}, []
    selector = selectors.DefaultSelector()
    serial, counts = bytearray(), dict(serial=0, stderr=0)
    started = time.monotonic()
    deadline = started + (90 if mode == "iommu-event-overflow" else 30)
    reason, forced, unsettled = "pending", False, False
    try:
        for name in ("serial", "stderr", "qmp"):
            outputs[name] = (directory / (name + ".log")).open("xb")
        serial_read, serial_write = os.pipe()
        serial_stream = os.fdopen(serial_read, "rb", buffering=0)
        serial_read = None
        argv = command(runtime, directory, serial_write)
        write_json(
            directory / "launch.json", dict(argv=argv, environment=environment(directory, runtime), captures=captures)
        )
        process = transport.start(
            argv,
            cwd=directory,
            env=environment(directory, runtime),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(serial_write,),
            preexec_fn=child_limits,
        )
        os.close(serial_write)
        serial_write = None
        for stream, name in ((serial_stream, "serial"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            transport.remaining(deadline)
            for key, _ in selector.select(min(0.05, deadline - time.monotonic())):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                left = STREAM_LIMIT - counts[name]
                retained = chunk[:left]
                counts[name] += min(len(chunk), left)
                if name == "serial":
                    serial.extend(retained)
                transport.capture_bytes(
                    outputs[name], chunk, counts[name] - len(retained), STREAM_LIMIT, name + " size limit"
                )
            terminal = re.search(rb"AURORA_IOMMU_EVENT_TERMINAL: [^\r\n]*\r\n", serial)
            failure = re.search(rb"AURORA_[^\r\n]*(?:FAIL|EXCEPTION|REJECTED)[^\r\n]*\r\n", serial)
            if reason == "pending" and (terminal or failure):
                need(not exited(process), "Guest exited before capture")
                qmp = Qmp(process, deadline, outputs["qmp"])
                need(qmp.command("stop") == {}, "QMP stop response")
                status = qmp.command("query-status")
                need(
                    type(status) is dict and status.get("status") == "paused" and status.get("running") is False,
                    "QEMU did not prove paused",
                )
                try:
                    arena, _ = oracle.ownership(bytes(serial))
                except ValueError:
                    need(failure, "Missing unique ownership for capture")
                else:
                    for name, offset, size in captures:
                        target = directory / name
                        need(not os.path.lexists(target), "Capture destination exists")
                        result = qmp.command(
                            "human-monitor-command", {"command-line": f'pmemsave {arena + offset} {size} "{name}"'}
                        )
                        need(result == "" and esp.regular(target).stat().st_size == size, "Incomplete RAM capture")
                        captured[name] = dict(physical=arena + offset, **identity(target))
                need(qmp.command("quit") == {}, "QMP quit response")
                reason = "failure-captured" if failure else "terminal-captured"
            if reason == "pending" and exited(process):
                raise ValueError("Guest exited before captured terminal")
        need(reason == "terminal-captured", "No successful captured terminal: " + reason)
        need(reap_completed(process, deadline) == 0, "QMP quit exit status")
        need(not counts["stderr"], "Unexpected QEMU stderr")
    except BaseException as error:
        errors.append(type(error).__name__ + ": " + str(error))
    finally:
        cleanup_errors, forced, unsettled = transport.finish(
            process,
            drains=[selector.close],
            fds=(serial_read, serial_write),
            require_natural=True,
            streams=[
                serial_stream,
                *outputs.values(),
                *([process.stdin, process.stdout, process.stderr] if process else []),
            ],
        )
        errors.extend(cleanup_errors)
        write_json(
            directory / "result.json",
            dict(
                reason=reason,
                returncode=process.returncode if process else None,
                owned_process_reaped=bool(process and process.returncode is not None),
                forced_cleanup=forced,
                elapsed_seconds=time.monotonic() - started,
                stream_bytes=counts,
                captures=captured,
                errors=errors,
            ),
        )
    if unsettled or (process and process.returncode is None):
        raise ChildNotReaped("; ".join(errors))
    need(not errors, "; ".join(errors))
    result = oracle.validate(
        mode,
        receipt,
        bytes(serial),
        {name: (directory / name).read_bytes() for name in captured},
        (directory / "qmp.log").read_bytes(),
    )
    write_json(directory / "oracle.json", result)
    return result


def budget(directory):
    need(allocated_bytes(directory) <= EVIDENCE_LIMIT, "Event run evidence exceeds 1 GiB")
    need(shutil.disk_usage(directory).free >= FREE_FLOOR, "Less than 1 GiB free")


def bounded_child(argv, log, *, env=None, timeout=1800, expected=0, limit=32 * STREAM_LIMIT):
    return transport.run_logged(
        argv,
        log,
        env=env,
        cwd=ROOT,
        timeout=timeout,
        expected=expected,
        limit=limit,
        preexec_fn=child_limits,
        timeout_status=False,
    )


def build(mode, directory, label=None):
    global BUILD
    label = label or mode
    selection = directory / ("image-directory-" + label + ".log")
    with (directory / ("build-" + label + ".log")).open("xb") as log:
        transport.run_logged(
            [
                sys.executable,
                "-B",
                ROOT / "scripts/meson_test.py",
                "--kernel",
                "uefi",
                "--profile",
                mode,
                "--print-image-dir",
            ],
            selection,
            cwd=ROOT,
            env=os.environ.copy(),
            stderr=log,
            timeout=1800,
            expected=0,
            timeout_status=False,
            preexec_fn=child_limits,
        )
    selected = selection.read_text()
    BUILD = Path(selected.rstrip("\n"))
    need(
        selected == str(BUILD) + "\n" and selected.count("\n") == 1 and BUILD.is_absolute(),
        "Invalid native image directory handoff",
    )
    need(BUILD.parts[-3:] == ("kernel-images", "uefi", mode), "Wrong native image profile")
    budget(directory)


def section_alignment(elf, index):
    """sh_addralign of one section header; kernel_elf.Section omits it."""
    shoff, shentsize = struct.unpack_from("<Q", elf.data, 40)[0], struct.unpack_from("<H", elf.data, 58)[0]
    return struct.unpack_from("<Q", elf.data, shoff + index * shentsize + 48)[0]


def backing_evidence(linked, directory):
    """Locate every retained Event allocation in the linked payload for RAM capture."""
    names = {item[0] for item in RETAINED.values()} | {"__payload_read_end", "__payload_memory_end"}
    symbols = {}
    for symbol in linked.symbols:
        if symbol.name in names:
            need(symbol.name not in symbols, "Ambiguous retained Event symbol: " + symbol.name)
            symbols[symbol.name] = symbol
    begin, end = symbols["__payload_read_end"].address, symbols["__payload_memory_end"].address
    need(
        0 < begin < end <= LAYOUT.kernel_payload_limit and begin % 4096 == end % 4096 == 0,
        "Invalid retained payload RW bound",
    )
    owner = Elf(directory / "objects" / "event-intake.o")
    result = {}
    for role, (name, size, alignment) in RETAINED.items():
        symbol = symbols[name]
        section = linked.sections[symbol.section]
        need(
            symbol.kind == 1
            and symbol.size == size
            and symbol.address % alignment == 0
            and begin <= symbol.address
            and symbol.address + size <= end,
            "Changed retained Event object extent/alignment: " + role,
        )
        need(
            section.kind == SHT_NOBITS
            and section.flags == SHF_WRITE_ALLOC
            and section_alignment(linked, symbol.section) >= alignment
            and section.address <= symbol.address
            and symbol.address + size <= section.address + section.size,
            "Retained Event object must occupy allocated writable non-executable zero-initialized BSS: " + role,
        )
        originals = [row for row in owner.symbols if row.name == name and row.section]
        need(
            len(originals) == 1
            and originals[0].kind == 1
            and originals[0].size == size
            and owner.sections[originals[0].section].kind == SHT_NOBITS,
            "Retained Event object lacks exact native owner: " + role,
        )
        for other in result.values():
            need(
                symbol.address + size <= other["offset"] or other["offset"] + other["bytes"] <= symbol.address,
                "Overlapping retained Event allocations",
            )
        result[role] = dict(
            symbol=name, offset=symbol.address, bytes=size, alignment=alignment, arena_offset=0x22000 + symbol.address
        )
    return dict(
        objects=result,
        retained_bytes=sum(row["bytes"] for row in result.values()),
        payload_rw_begin=begin,
        payload_memory_end=end,
    )


def image_receipt(mode, directory):
    """The current image facts the Event oracle consumes: linked layout and retained allocations."""
    linked = Elf(directory / "payload.elf")
    layout = {
        name: [s.address for s in linked.symbols if s.name == "__" + name]
        for name in ("payload_text_end", "payload_read_end", "payload_memory_end")
    }
    need(all(len(values) == 1 for values in layout.values()), "Ambiguous current image layout")
    layout = {name: values[0] for name, values in layout.items()} | {
        "payload_size": (directory / "payload.bin").stat().st_size
    }
    image = dict(mode=mode, payload_layout=layout, backing=backing_evidence(linked, directory))
    return dict(mode=mode, image=image)


def stage(mode, directory):
    """Copy the loader, sidecars and the inputs of the Event image receipt from BUILD."""
    names = ["esp/EFI/BOOT/BOOTX64.EFI", "bar-metadata.json", "ivrs-metadata.json"]
    if mode != "normal":
        names += ["payload.elf", "payload.bin", "uefi-payload.hpp", "objects/event-intake.o"]
    directory.mkdir(mode=0o700)
    for name in names:
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_private(BUILD / name, target)
    record = dict(mode=mode)
    if mode != "normal":
        record["receipt"] = image_receipt(mode, directory)
        oracle.capture_layout(record["receipt"])
    write_json(directory / "image.json", record)
    return record


def normal_boot(args, directory, image):
    qemu = safe_path(Path(shutil.which(args.normal_qemu) or args.normal_qemu).resolve())
    argv = transport.command(
        qemu,
        args.normal_data,
        firmware=transport.firmware_args(args.normal_firmware, args.normal_code, args.normal_vars),
        boot=transport.fat_boot(image / "esp"),
    )
    argv.append("-no-user-config")
    write_json(directory / "normal-launch.json", dict(argv=argv))
    log = directory / "normal-restoration.log"
    status = bounded_child(argv, log, timeout=30, expected=33)
    normal.validate(status, log.read_text(), "normal")


def capture_staged(mode, build, image, record, runtime, master, directory, *, master_sha256):
    """Run one staged image, without builds, with signals turned into interrupts."""
    need(mode in MODES and build.parts[-3:] == ("kernel-images", "uefi", mode), "Wrong staged Event profile")
    need(build.is_absolute() and build.is_dir() and build.resolve(strict=True) == build, "Invalid prebuilt Event image")
    need(
        not directory.resolve().is_relative_to(build) and not directory.resolve().is_relative_to(image.resolve()),
        "Guest output cannot modify the staged Event image",
    )
    need(record["mode"] == mode, "Staged Event mode differs")

    def interrupted(signum, _frame):
        raise KeyboardInterrupt("Event worker interrupted by signal " + str(signum))

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        capture_guest(mode, record["receipt"], runtime, master, directory, master_sha256=master_sha256)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def window(args, directory, runtime):
    results, normal_image, normal_record, errors = [], directory / "normal-image", None, []
    unreaped = False
    try:
        build("normal", directory)
        normal_record = stage("normal", normal_image)
        for mode in MODES:
            record = dict(mode=mode, status="failed")
            results.append(record)
            build(mode, directory)
            image = directory / (mode + "-image")
            staged = stage(mode, image)
            loader = image / "esp/EFI/BOOT/BOOTX64.EFI"
            esp_dir = directory / (mode + "-esp")
            if args.esp_dir:
                master = safe_path(Path(args.esp_dir) / (mode + ".raw"))
                fat = esp.validate_image(master, esp.sha256(loader), loader.stat().st_size)
                esp_dir.mkdir(mode=0o700)
                copy_private(master, esp_dir / "esp-master.raw", fat["image_sha256"])
                master = esp_dir / "esp-master.raw"
                master.chmod(0o400)
                write_json(esp_dir / "fat.json", fat)
            else:
                built = esp.build(
                    loader,
                    esp.sha256(loader),
                    args.mtools_dir,
                    esp_dir,
                    run_command=lambda command, log, env: bounded_child(
                        command, log, env=env, timeout=60, limit=STREAM_LIMIT
                    ),
                )
                master, fat = Path(built["master"]), built["fat32"]
            budget(directory)
            if not args.build_only:
                capture_staged(
                    mode,
                    BUILD,
                    image,
                    staged,
                    runtime,
                    master,
                    directory / (mode + "-guest"),
                    master_sha256=fat["image_sha256"],
                )
            record["status"] = "build-checked" if args.build_only else "local-developer-evidence-passed"
            write_json(directory / "summary.json", dict(profiles=results, errors=errors))
            print(record["status"] + ": " + mode, flush=True)
    except BaseException as error:
        errors.append("primary: " + type(error).__name__ + ": " + str(error))
        unreaped = isinstance(error, ChildNotReaped)
    finally:
        if unreaped:
            errors.append("restoration blocked: owned child has not been reaped")
        elif normal_record:
            try:
                if not args.build_only:
                    normal_boot(args, directory, normal_image)
                results.append(dict(mode="normal-restoration", status="passed"))
            except BaseException as error:
                errors.append("restoration: " + type(error).__name__ + ": " + str(error))
                results.append(dict(mode="normal-restoration", status="failed"))
        write_json(
            directory / "summary.json",
            dict(
                scope="local developer emulator evidence; no independent qualification",
                build_only=args.build_only,
                profiles=results,
                errors=errors,
            ),
        )
    need(not errors, "; ".join(errors))
    budget(directory)


def prerequisites(args):
    for name, value in os.environ.items():
        need(
            not value
            or not (
                name.startswith("KERNEL_TEST_")
                or name
                in (
                    "AURORA_TEST_CONTEXT",
                    "KERNEL_USER_PROBE_MODE",
                    "KERNEL_CONSOLE",
                    "UEFI_MODE",
                    "UEFI_CONSOLE_HANDOFF",
                )
            ),
            "Unset conflicting control: " + name,
        )
    prefix = getattr(args, "tool_prefix", None)
    need(
        not prefix or not any((args.build_receipt, args.code, args.vars, args.data)),
        "Choose EVENT_TOOL_PREFIX or external Event runtime inputs, not both",
    )
    if not args.build_only and not prefix and not all((args.build_receipt, args.code, args.vars, args.data)):
        raise PrerequisiteBlocked(
            "Set EVENT_BUILD_RECEIPT, EVENT_CODE, EVENT_VARS and EVENT_DATA, "
            "or EVENT_TOOL_PREFIX for packaged Event tools"
        )
    if not args.esp_dir:
        tool = shutil.which("mformat")
        if not (args.mtools_dir or tool):
            raise PrerequisiteBlocked("Install GNU mtools or supply EVENT_ESP_DIR")
        args.mtools_dir = args.mtools_dir or str(Path(tool).parent)
        esp.mtools(args.mtools_dir)
    else:
        directory = safe_path(args.esp_dir, directory=True)
        for mode in MODES:
            safe_path(directory / (mode + ".raw"))
    for tool in (
        os.environ.get("CXX") or "g++",
        "bash",
        "meson",
        "ninja",
        "as",
        "ld",
        "objcopy",
        "objdump",
        "nm",
        "readelf",
    ):
        if not shutil.which(tool):
            raise PrerequisiteBlocked("Missing dependency: " + tool)
    linker = subprocess.run(
        ["bash", "-c", 'source "$1"; uefi_linker_select', "event-linker-check", str(ROOT / "scripts/uefi-linker.sh")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if linker.returncode == 2:
        raise PrerequisiteBlocked(linker.stderr.strip() or "Missing UEFI PE linker")
    need(linker.returncode == 0, linker.stderr.strip() or "UEFI PE linker check failed")
    if not args.build_only:
        qemu = safe_path(Path(shutil.which(args.normal_qemu) or args.normal_qemu).resolve())
        need(os.access(qemu, os.X_OK), "Normal QEMU is not executable")
        if not args.normal_firmware and not (args.normal_code and args.normal_vars):
            raise PrerequisiteBlocked("Supply ordinary OVMF or both CODE/VARS paths for normal restoration")
        for value in (args.normal_firmware, args.normal_code, args.normal_vars):
            if value:
                safe_path(value)
        transport.firmware_args(args.normal_firmware, args.normal_code, args.normal_vars)
        if args.normal_data:
            safe_path(args.normal_data, directory=True)
    parent = Path(args.output_parent).absolute()
    if parent == ROOT / "build":
        parent.mkdir(exist_ok=True)
    parent = safe_path(parent, directory=True)
    need(
        not parent.is_relative_to(ROOT) or parent.is_relative_to(ROOT / "build"),
        "Event output must be in build/ or outside the source tree",
    )
    if shutil.disk_usage(parent).free < FREE_FLOOR + EVIDENCE_LIMIT:
        raise PrerequisiteBlocked("Event run requires 1 GiB reservation plus 1 GiB free floor")
    try:
        runtime = None if args.build_only else runtime_inputs(args)
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid custom runtime receipt: " + str(error)) from error
    return parent, runtime


def discard_captures(directory):
    files = []
    for mode in MODES:
        files.extend(directory / (mode + "-esp") / name for name in ("esp-master.raw", "esp-rebuild.raw"))
        files.extend(
            directory / (mode + "-guest") / name
            for name in ("esp.raw", "vars.fd", *(capture[0] for capture in oracle.CAPTURES))
        )
    smoke_outputs.discard_files(directory, files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--tool-prefix", default=os.environ.get("EVENT_TOOL_PREFIX") or None)
    parser.add_argument("--build-receipt", default=os.environ.get("EVENT_BUILD_RECEIPT"))
    parser.add_argument("--code", default=os.environ.get("EVENT_CODE"))
    parser.add_argument("--vars", default=os.environ.get("EVENT_VARS"))
    parser.add_argument("--data", default=os.environ.get("EVENT_DATA"))
    parser.add_argument("--esp-dir", default=os.environ.get("EVENT_ESP_DIR"))
    parser.add_argument("--mtools-dir", default=os.environ.get("MTOOLS_DIR"))
    parser.add_argument("--output-parent", default=os.environ.get("EVENT_OUTPUT_PARENT") or str(ROOT / "build"))
    parser.add_argument("--normal-qemu", default=os.environ.get("QEMU") or "qemu-system-x86_64")
    parser.add_argument("--normal-firmware", default="")
    parser.add_argument("--normal-code", default="")
    parser.add_argument("--normal-vars", default="")
    parser.add_argument("--normal-data", default=os.environ.get("QEMU_DATA", ""))
    args = parser.parse_args()
    keep = smoke_outputs.retained_runs("AURORA_EVENT_KEEP_RUNS")
    try:
        parent, runtime = prerequisites(args)
    except FileNotFoundError as error:
        raise PrerequisiteBlocked(str(error)) from error

    def interrupted(signum, _frame):
        raise KeyboardInterrupt("Event smoke interrupted by signal " + str(signum))

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    directory = Path(tempfile.mkdtemp(prefix="aurora-event-smoke-", dir=parent))
    print("Event smoke evidence: " + str(directory), flush=True)
    outputs = smoke_outputs.SmokeOutputs(parent, "aurora-event-smoke-", RUN_MARKER, keep)
    outputs.start(directory)
    status = 1
    try:
        if runtime:
            write_json(directory / "runtime.json", runtime)
        window(args, directory, runtime)
        status = 0
    finally:
        outputs.finish(directory, status, discard_captures)


def cli():
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(transport.failure_label(error) + ": Event developer smoke: " + str(error), file=sys.stderr)
        return 2 if isinstance(error, PrerequisiteBlocked) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())

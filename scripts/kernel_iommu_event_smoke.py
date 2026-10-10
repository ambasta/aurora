#!/usr/bin/env python3
"""Opt-in current-source Event developer smoke; never independent qualification."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

import kernel_iommu_event_admission as admission
import kernel_iommu_event_esp as esp
import kernel_iommu_event_oracle as oracle
import kernel_uefi_oracle as normal
from kernel_emulator_clock import expected_uefi_argv
import qemu_transport as transport
from qemu_transport import ChildNotReaped, Qmp, cleanup, exited, reap_completed
from qemu_transport import MissingPrerequisite as PrerequisiteBlocked
from owned_outputs import allocated_bytes

ROOT = Path(__file__).resolve().parents[1]
BUILD = None
MODES = admission.MODES[:4]
STREAM_LIMIT = 1024 * 1024
EVIDENCE_LIMIT = 1024**3
FREE_FLOOR = 1024**3
FIRMWARE = {
    "code": (3653632, "624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0"),
    "vars": (540672, "5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e"),
}
MODEL = {
    "hw/i386/amd_iommu.c": "a506dccf0c112cc791208724651b3aaca300f8b713362dfd07af2308e6f5a2d9",
    "hw/i386/amd_iommu.h": "94d50d0dd0548c533252b4fdff7ec3cf800aed8655ce38db24de837adf1785e4",
}
DEVICE_CONFIG = "CONFIG_Q35=y\nCONFIG_AMD_IOMMU=y\nCONFIG_EDU=y\nCONFIG_ISA_DEBUG=y\n"
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


def data_files(directory):
    directory = safe_path(directory, directory=True)
    result, visited, pending, total = {}, set(), [(directory, 0)], 0
    while pending:
        current, depth = pending.pop()
        resolved = safe_path(current.resolve(strict=True), directory=True)
        need(depth <= 8 and len(visited) < 64, "QEMU data directory limit")
        need(resolved not in visited, "QEMU data directory cycle or repeated alias")
        visited.add(resolved)
        for path in current.iterdir():
            target = path.resolve(strict=True)
            if target.is_dir():
                pending.append((path, depth + 1))
                need(len(pending) + len(visited) <= 64, "QEMU data directory limit")
                continue
            need(stat.S_ISREG(target.stat().st_mode), "Nonregular QEMU data")
            need(len(result) < 256, "QEMU data inventory limit")
            total += target.stat().st_size
            need(total <= 32 * 1024**2, "QEMU data size limit")
            result[str(path.relative_to(directory))] = dict(path=str(target), **identity(target))
    need(result, "Empty QEMU data")
    return result


def runtime_inputs(args):
    """Verify a supplied build record, never its historical acceptance status.

    Like the compiler toolchain, this is a trusted user-supplied executable and
    build record. Hashes bind the actual inputs; they are not build attestation.
    """
    record_path = safe_path(args.build_receipt)
    build = read_json(record_path)
    source = safe_path(build["source_path"], directory=True)
    files = {str(record_path): identity(record_path)}
    for name, digest in MODEL.items():
        path = safe_path(source / name)
        observed = identity(path)
        need(observed["sha256"] == digest, "Custom model source changed")
        files[str(path)] = observed
    config = safe_path(source / "configs/devices/x86_64-softmmu/aurora-dma.mak")
    observed = identity(config)
    need(
        observed["sha256"] == hashlib.sha256(DEVICE_CONFIG.encode()).hexdigest(),
        "Custom model device configuration changed",
    )
    files[str(config)] = observed
    binary = safe_path(build["binary_path"])
    observed = identity(binary)
    need(
        os.access(binary, os.X_OK) and observed == dict(bytes=build["binary_bytes"], sha256=build["binary_sha256"]),
        "Custom QEMU binary/build record mismatch",
    )
    files[str(binary)] = observed
    libraries_path = safe_path(build["runtime_library_manifest"]["path"])
    observed = identity(libraries_path)
    need(observed["sha256"] == build["runtime_library_manifest"]["sha256"], "Dependency manifest changed")
    libraries = read_json(libraries_path)
    files[str(libraries_path)] = observed
    library_dirs = libraries["LD_LIBRARY_PATH"]
    need(type(library_dirs) is str, "Invalid library path")
    for path in library_dirs.split(":") if library_dirs else []:
        safe_path(path, directory=True)
    bindings = libraries["libraries"]
    need(type(bindings) is dict and 1 <= len(bindings) <= 64, "Dependency inventory limit")
    for alias, row in bindings.items():
        target = safe_path(row["resolved_path"])
        need(Path(alias).is_absolute() and Path(alias).resolve(strict=True) == target, "Dependency resolution changed")
        observed = identity(target)
        need(observed == {k: row[k] for k in ("bytes", "sha256")}, "Dependency bytes changed")
        files[str(target)] = observed
    for role in FIRMWARE:
        path = safe_path(getattr(args, role))
        observed = identity(path)
        need(observed == dict(zip(("bytes", "sha256"), FIRMWARE[role])), "Unsupported default split OVMF " + role)
        files[str(path)] = observed
    return dict(
        qemu=str(binary),
        code=str(safe_path(args.code)),
        vars=str(safe_path(args.vars)),
        data=str(safe_path(args.data, directory=True)),
        data_files=data_files(args.data),
        files=files,
        library_path=library_dirs,
        library_bindings=bindings,
    )


def verify_runtime(runtime):
    for path, recorded in runtime["files"].items():
        need(identity(path) == recorded, "Runtime input changed: " + path)
    for alias, row in runtime["library_bindings"].items():
        need(Path(alias).resolve(strict=True) == Path(row["resolved_path"]), "Dependency link changed")
    need(data_files(runtime["data"]) == runtime["data_files"], "QEMU data changed")


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
    before = identity(source)
    with source.open("rb") as left, destination.open("xb") as right:
        shutil.copyfileobj(left, right)
    destination.chmod(0o600)
    need(identity(destination) == before == identity(source), "Input changed during private copy")
    need(digest is None or before["sha256"] == digest, "Private copy identity mismatch")


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
    copy_private(runtime["vars"], directory / "vars.fd", runtime["files"][runtime["vars"]]["sha256"])
    copy_private(master, directory / "esp.raw", master_sha256)
    verify_dependencies(runtime, directory)
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
    verify_runtime(runtime)
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


def verify_dependencies(runtime, directory):
    bindings = runtime["library_bindings"]
    loaders = {row["resolved_path"] for alias, row in bindings.items() if Path(alias).name == "ld-linux-x86-64.so.2"}
    need(len(loaders) == 1, "Expected recorded x86-64 ELF interpreter")
    log = directory / "dependency-resolution.log"
    bounded_child(
        [loaders.pop(), "--list", runtime["qemu"]], log, env=environment(directory, runtime), timeout=5, limit=65536
    )
    rows = log.read_text().splitlines()
    selected = set()
    for row in rows:
        if re.fullmatch(r"\s*linux-vdso.so.1 \(0x[0-9a-f]+\)", row):
            continue
        match = re.fullmatch(r"\s*(?:\S+ => )?(/\S+) \(0x[0-9a-f]+\)", row)
        need(match is not None, "Unresolved/unexpected dynamic dependency")
        selected.add(str(Path(match[1]).resolve(strict=True)))
    need(
        selected == {row["resolved_path"] for row in bindings.values()}, "Selected dynamic dependency inventory differs"
    )
    verify_runtime(runtime)


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
    admission.configure_paths(BUILD, ROOT)
    budget(directory)


def source_identity():
    return admission.common.hashes(admission.source_files())


def stage(mode, directory):
    source = source_identity()
    checked = admission.checked(mode) if mode != "normal" else None
    # Reuse the complete ordinary build inventory, including PE inputs/sidecars.
    if mode == "normal":
        graphical = admission.load("event_normal_inventory", ROOT / "scripts/kernel_graphical_console_admission.py")
        graphical.configure_paths(BUILD, ROOT)
        files = graphical.build_files("normal")
        graphical.common.verify_object_exports(files)
    else:
        files = admission.build_files(mode)
    admitted = list(files)
    files += [BUILD / name for name in ("bar-metadata.json", "ivrs-metadata.json")]
    if checked:
        files += [admission.RECEIPT, BUILD / "iommu-event-build.json", BUILD / "iommu-event-build-start.json"]
    expected = admission.common.hashes(files)
    if checked:
        for path in admitted:
            key = "build:" + path.relative_to(BUILD).as_posix()
            need(expected[key] == checked["sha256"][key], "Admitted Event image changed before staging")
    directory.mkdir(mode=0o700)
    for path in files:
        esp.regular(path)
        target = directory / path.relative_to(BUILD)
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_private(path, target, expected["build:" + path.relative_to(BUILD).as_posix()])
    result = dict(
        mode=mode,
        source=source,
        files={str(p.relative_to(directory)): identity(p) for p in directory.rglob("*") if p.is_file()},
    )
    if checked:
        decoder = admission.load("event_smoke_layout", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
        linked = decoder.Elf(directory / "payload.elf")
        layout = {
            name: [s.address for s in linked.symbols if s.name == "__" + name]
            for name in ("payload_text_end", "payload_read_end", "payload_memory_end")
        }
        need(all(len(values) == 1 for values in layout.values()), "Ambiguous current image layout")
        layout = {name: values[0] for name, values in layout.items()} | {
            "payload_size": (directory / "payload.bin").stat().st_size
        }
        expected_header = (
            "namespace aurora::uefi {\n"
            + "".join(
                f"inline constexpr unsigned long long {name}={layout[name]};\n"
                for name in ("payload_size", "payload_text_end", "payload_read_end", "payload_memory_end")
            )
            + "}\n"
        )
        need((directory / "uefi-payload.hpp").read_text() == expected_header, "Current header/linked layout mismatch")
        result["checked"] = copy.deepcopy(checked)
        result["checked"]["image"]["payload_layout"] = layout
        oracle.capture_layout(result["checked"])
    need(source == source_identity(), "Source changed during image staging")
    write_json(directory / "image.json", result)
    return result


def verify_stage(directory, record, *, source=True):
    safe_path(directory, directory=True)
    need(not any(p.is_symlink() for p in directory.rglob("*")), "Symlink in staged image")
    need(read_json(directory / "image.json") == record, "Staged image record changed")
    need(
        record["files"]
        == {
            str(p.relative_to(directory)): identity(p)
            for p in directory.rglob("*")
            if p.is_file() and p.name != "image.json"
        },
        "Staged image changed",
    )
    need(not source or record["source"] == source_identity(), "Source changed since admission")


def normal_boot(args, directory, image):
    qemu = safe_path(Path(shutil.which(args.normal_qemu) or args.normal_qemu).resolve())
    paths = [qemu]
    for value in (args.normal_firmware, args.normal_code, args.normal_vars):
        if value:
            paths.append(safe_path(value))
    before = {str(p): identity(p) for p in paths}
    if args.normal_data:
        data_before = data_files(args.normal_data)
    argv = transport.command(
        qemu,
        args.normal_data,
        firmware=transport.firmware_args(args.normal_firmware, args.normal_code, args.normal_vars),
        boot=transport.fat_boot(image / "esp"),
    )
    need(
        argv
        == expected_uefi_argv(
            "normal",
            str(qemu),
            args.normal_firmware,
            args.normal_data,
            args.normal_code,
            args.normal_vars,
            esp=str(image / "esp"),
        ),
        "Normal restoration command differs from independent clock contract",
    )
    argv.append("-no-user-config")
    write_json(directory / "normal-launch.json", dict(argv=argv, inputs=before))
    log = directory / "normal-restoration.log"
    status = bounded_child(argv, log, timeout=30, expected=33)
    normal.validate(status, log.read_text(), "normal")
    need(before == {str(p): identity(p) for p in paths}, "Normal runtime input changed")
    if args.normal_data:
        need(data_files(args.normal_data) == data_before, "Normal data changed")


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
                    developer=True,
                    run_command=lambda command, log, env: bounded_child(
                        command, log, env=env, timeout=60, limit=STREAM_LIMIT
                    ),
                )
                master, fat = Path(built["master"]), built["fat32"]
            verify_stage(image, staged)
            budget(directory)
            if not args.build_only:
                checked = copy.deepcopy(staged["checked"])
                del checked["image"]["payload_layout"]
                need(admission.checked(mode) == checked, "Current Event admission changed before launch")
                capture_guest(
                    mode,
                    staged["checked"],
                    runtime,
                    master,
                    directory / (mode + "-guest"),
                    master_sha256=fat["image_sha256"],
                )
                need(admission.checked(mode) == checked, "Current Event admission changed after launch")
            verify_stage(image, staged)
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
                verify_stage(normal_image, normal_record, source=False)
                if not args.build_only:
                    normal_boot(args, directory, normal_image)
                verify_stage(normal_image, normal_record, source=False)
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
    if not args.build_only and not all((args.build_receipt, args.code, args.vars, args.data)):
        raise PrerequisiteBlocked(
            "Set EVENT_BUILD_RECEIPT, EVENT_CODE, EVENT_VARS and EVENT_DATA for the supported custom QEMU tuple"
        )
    if not args.esp_dir:
        tool = shutil.which("mformat")
        if not (args.mtools_dir or tool):
            raise PrerequisiteBlocked("Install supported GNU mtools 4.0.48 or supply EVENT_ESP_DIR")
        args.mtools_dir = args.mtools_dir or str(Path(tool).parent)
        Path(args.mtools_dir).resolve(strict=True)
        esp.developer_tool_identity(args.mtools_dir)
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
        expected_uefi_argv(
            "normal", str(qemu), args.normal_firmware, args.normal_data, args.normal_code, args.normal_vars
        )
        if args.normal_data:
            data_files(args.normal_data)
    parent = safe_path(args.output_parent, directory=True)
    need(parent != ROOT and ROOT not in parent.parents, "Event output must be outside the source tree")
    if shutil.disk_usage(parent).free < FREE_FLOOR + EVIDENCE_LIMIT:
        raise PrerequisiteBlocked("Event run requires 1 GiB reservation plus 1 GiB free floor")
    try:
        runtime = None if args.build_only else runtime_inputs(args)
    except (KeyError, TypeError) as error:
        raise ValueError("Invalid custom runtime receipt: " + str(error)) from error
    return parent, runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--build-receipt", default=os.environ.get("EVENT_BUILD_RECEIPT"))
    parser.add_argument("--code", default=os.environ.get("EVENT_CODE"))
    parser.add_argument("--vars", default=os.environ.get("EVENT_VARS"))
    parser.add_argument("--data", default=os.environ.get("EVENT_DATA"))
    parser.add_argument("--esp-dir", default=os.environ.get("EVENT_ESP_DIR"))
    parser.add_argument("--mtools-dir", default=os.environ.get("MTOOLS_DIR"))
    parser.add_argument("--output-parent", default=os.environ.get("EVENT_OUTPUT_PARENT") or tempfile.gettempdir())
    parser.add_argument("--normal-qemu", default=os.environ.get("QEMU") or "qemu-system-x86_64")
    parser.add_argument("--normal-firmware", default="")
    parser.add_argument("--normal-code", default="")
    parser.add_argument("--normal-vars", default="")
    parser.add_argument("--normal-data", default=os.environ.get("QEMU_DATA", ""))
    args = parser.parse_args()
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
    if runtime:
        write_json(directory / "runtime.json", runtime)
    window(args, directory, runtime)


def cli():
    try:
        main()
    except (Exception, KeyboardInterrupt) as error:
        print(transport.failure_label(error) + ": Event developer smoke: " + str(error), file=sys.stderr)
        return 2 if isinstance(error, PrerequisiteBlocked) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())

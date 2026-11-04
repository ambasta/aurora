#!/usr/bin/env python3
"""Cold-boot the one standalone UEFI AP-worker image through its closed cases.

Uses the original QEMU clock, stock pinned QEMU and the clean CODE/VARS fixture.
The reviewed results are sums of squares over the eight intervals [3+i, 515+i).
Serial completion also requires the ordinary BSP memory/readback/release checks.
Retained backing and a closed owner are not AP-stop or reclamation evidence.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import qemu_transport as transport
from kernel_layout import LAYOUT
from kernel_uefi_oracle import validate as validate_uefi

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/kernel-ap-worker-cases.json"
FIRMWARE_HASHES = {
    "OVMF_CODE.fd": "b82aecfaa2bcfd72b9cd60bc745e3558edcc79ab8fc99aa1dd214f0c7ec7f787",
    "OVMF_VARS.fd": "5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e",
}
need = transport.need


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context(text):
    owned = re.findall(r"^AURORA_UEFI_OWNERSHIP_OK: arena=(\d+) bytes=(\d+) descriptors=(\d+)$", text, re.M)
    protected = re.findall(r"^AURORA_UEFI_PROTECTION_OK: root=(\d+) stack=(\d+)$", text, re.M)
    need(len(owned) == len(protected) == 1, "Missing unique BSP ownership/protection evidence")
    arena, size, descriptors = map(int, owned[0])
    root, stack = map(int, protected[0])
    need(
        arena >= 0x100000
        and arena % 4096 == 0
        and size == LAYOUT.arena_bytes
        and arena + size <= 0x100000000
        and 1 <= descriptors <= 512
        and root == arena + 0x11000
        and arena + LAYOUT.kernel_stack_bottom <= stack < arena + LAYOUT.kernel_stack_top,
        "Invalid BSP ownership/protection context",
    )
    return arena, size, root


def topology(text):
    rows = re.findall(r"^AURORA_ACPI_CPU: id=(\d+) uid=(\d+) enabled=(\d+) capable=(\d+) x2=(\d+)$", text, re.M)
    need(
        len(rows) == 2
        and {tuple(map(int, row)) for row in rows} == {(0, 0, 1, 0, 0), (1, 1, 1, 0, 0)}
        and text.count("AURORA_ACPI_TOPOLOGY: records=2 enabled=2 capable=0 lapic=4276092928\n") == 1,
        "Wrong actual two-CPU QEMU topology",
    )
    closed = re.findall(r"^AURORA_ACPI_WINDOW_CLOSED: copies=(\d+)$", text, re.M)
    need(len(closed) == 1 and int(closed[0]) >= 5, "ACPI observation window not closed")


def validate(status, text, case, results):
    text = text.replace("\r", "")
    selector = f"AURORA_AP_CASE: value={case['selector']}"
    ap_lines = [line for line in text.splitlines() if line.startswith("AURORA_AP_")]
    need(ap_lines[:1] == [selector] and ap_lines.count(selector) == 1, "Wrong AP case selector")
    need("AURORA_FIXTURE_" not in text and "AURORA_UEFI_EXCEPTION:" not in text, "Unexpected selector or BSP fault")
    if "failure" in case:
        failure = "AURORA_UEFI_PAYLOAD_FAIL: " + case["failure"]
        need(
            status == 35
            and [line for line in text.splitlines() if "_FAIL:" in line] == [failure]
            and "AURORA_UEFI_LANGUAGE_OK:" not in text
            and "AURORA_UEFI_OK" not in text
            and ap_lines == [selector],
            "Early refusal did not stop before AP startup",
        )
        markers = ["AURORA_UEFI_ENTRY", selector, "AURORA_UEFI_EXIT_OK: attempts=1", "AURORA_UEFI_PAYLOAD_ENTRY"]
        if case["protected"]:
            context(text)
            markers += ["AURORA_UEFI_OWNERSHIP_OK:", "AURORA_UEFI_PROTECTION_OK:"]
        else:
            need(
                "AURORA_UEFI_OWNERSHIP_OK:" not in text and "AURORA_UEFI_PROTECTION_OK:" not in text,
                "Invalid backing reached protected payload",
            )
        markers.append(failure)
        need(all(text.count(marker) == 1 for marker in markers), "Missing/duplicate early-refusal phase")
        need(all(text.index(a) < text.index(b) for a, b in zip(markers, markers[1:])), "Early-refusal phase order")
        if case["failure"] == "AP worker":
            topology(text)
        else:
            need(
                "AURORA_ACPI_CPU:" not in text and "AURORA_ACPI_TOPOLOGY:" not in text,
                "Rejected map or parser issued topology",
            )
        return

    validate_uefi(status, text, "normal")
    arena, size, bsp_root = context(text)
    topology(text)
    expected = [selector, f"AURORA_AP_START_ATTEMPT: value={case['attempted']}"]
    if case["ready"]:
        ready = re.findall(r"^AURORA_AP_READY: bsp=(\d+) ap=(\d+) root=(\d+)$", text, re.M)
        need(len(ready) == 1, "Missing unique AP readiness")
        bsp, ap, root = map(int, ready[0])
        need(
            bsp != ap
            and {bsp, ap} == {0, 1}
            and root >= 0x100000
            and root % 4096 == 0
            and root < 0x100000000
            and root != bsp_root
            and not arena <= root < arena + size,
            "AP identity/private permanent root differs from admitted actual observations",
        )
        expected.append(f"AURORA_AP_READY: bsp={bsp} ap={ap} root={root}")
    if "status" in case:
        if case.get("late"):
            expected.append("AURORA_AP_LATE_IGNORED")
        expected.append(f"AURORA_AP_QUARANTINED: status={case['status']} retained=1 retry=0")
    else:
        expected += [
            f"AURORA_AP_RESULT: sequence={sequence} value={value}" for sequence, value in enumerate(results, 1)
        ]
        expected.append("AURORA_AP_EXHAUSTED: jobs=8 work=4096 retained=1")
    need(ap_lines == expected, "AP transcript differs from reviewed results/quarantine sequence")
    need(
        text.index("AURORA_ACPI_WINDOW_CLOSED:") < text.index(expected[1])
        and text.index(expected[-1]) < text.index("AURORA_UEFI_LANGUAGE_OK:"),
        "AP activity or subsequent BSP memory-work phase order",
    )


def run_case(case, results, image, qemu, data, firmware, output):
    output.mkdir()
    argv = transport.command(
        qemu,
        data,
        cpu=case.get("cpu", "qemu64,vendor=GenuineIntel"),
        cpus=case.get("cpus", 2),
        firmware=transport.firmware_args(code=str(firmware / "OVMF_CODE.fd"), variables=str(firmware / "OVMF_VARS.fd")),
        boot=transport.fat_boot(image / "esp"),
        extra=["-fw_cfg", f"name=opt/aurora/case,string={case['selector']}"] if case["selector"] else [],
    )
    (output / "command.json").write_text(json.dumps(argv, indent=2) + "\n")
    started = time.monotonic()
    with (output / "stderr.log").open("xb") as diagnostics:
        status = transport.run_logged(argv, output / "serial.log", cwd=ROOT, timeout=30, stderr=diagnostics)
    (output / "exit.json").write_text(json.dumps({"status": status, "seconds": time.monotonic() - started}) + "\n")
    need(not (output / "stderr.log").read_bytes(), "QEMU diagnostics: " + (output / "stderr.log").read_text())
    validate(status, (output / "serial.log").read_text(), case, results)
    print(f"PASS: AP-worker {case['name']}; output {output}", flush=True)


def interrupted(signum, frame):
    raise SystemExit(128 + signum)


def main():
    golden = json.loads(GOLDEN.read_text())
    cases = {case["name"]: case for case in golden["cases"]}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-only", type=Path, required=True, help="already-built standalone AP-worker image directory"
    )
    parser.add_argument(
        "--output-dir", type=Path, help="fresh retained output directory (default: private temporary directory)"
    )
    parser.add_argument("--case", action="append", choices=cases, help="run only this case; repeat for several cases")
    args = parser.parse_args()
    output = None
    try:
        image = transport.input_path(args.run_only, "AP-worker image", directory=True)
        need(image.parts[-3:] == ("kernel-images", "uefi", "ap-worker"), "Wrong standalone image profile")
        boot = transport.input_path(image / "esp/EFI/BOOT/BOOTX64.EFI", "AP-worker EFI executable")
        image_hash = digest(boot)
        qemu = shutil.which(os.environ.get("QEMU") or "qemu-system-x86_64")
        if not qemu:
            raise transport.MissingPrerequisite("QEMU unavailable")
        version = subprocess.run([qemu, "--version"], capture_output=True, text=True, timeout=10, check=True).stdout
        need(
            re.fullmatch(r"QEMU emulator version 10\.0\.13(?: \([^()]+\))?", version.splitlines()[0]),
            "Expected pinned QEMU 10.0.13",
        )
        data = transport.input_path(os.environ.get("QEMU_DATA") or "/usr/share/qemu", "QEMU data", directory=True)
        firmware = Path(os.environ.get("AURORA_BOOT_FIXTURE_PREFIX") or "/opt/aurora-fixtures") / "firmware"
        for name, expected in FIRMWARE_HASHES.items():
            path = transport.input_path(firmware / name, name)
            need(digest(path) == expected, "Wrong pinned firmware: " + name)
        output = args.output_dir.resolve() if args.output_dir else Path(tempfile.mkdtemp(prefix="aurora-ap-worker-"))
        if args.output_dir:
            need(image != output and image not in output.parents, "Output must be outside the image directory")
            output.mkdir(parents=True)
        print(f"Retained output: {output}", flush=True)
        selected = args.case or list(cases)
        need(len(selected) == len(set(selected)), "Repeated case selection")
        (output / "inputs.json").write_text(
            json.dumps(
                {
                    "image": str(image),
                    "efi_sha256": image_hash,
                    "qemu": qemu,
                    "qemu_version": version.splitlines()[0],
                    "qemu_data": str(data),
                    "firmware": str(firmware),
                    "firmware_sha256": FIRMWARE_HASHES,
                    "clock": "tcg-original-clock",
                    "cases": selected,
                },
                indent=2,
            )
            + "\n"
        )
        for name in selected:
            need(digest(boot) == image_hash, "AP-worker image changed between cold boots")
            run_case(cases[name], golden["results"], image, qemu, data, firmware, output / name)
        need(digest(boot) == image_hash, "AP-worker image changed during guest acceptance")
        print(f"PASS: {len(selected)} actual AP-worker guest cases; retained backing is not reclamation", flush=True)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            f"{transport.failure_label(error)}: AP-worker: {error}" + (f"; output {output}" if output else ""),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)

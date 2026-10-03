#!/usr/bin/env python3
"""Validate actual exception codes, origin privilege, stacks and denied addresses."""
from pathlib import Path
import sys
import re
import json

FOUNDATIONS = (
    "AURORA_E820_OK",
    "AURORA_EXCEPTION_OK: breakpoint, 15 GPRs, direction flag",
    "AURORA_PAGES_OK: 128 frames, exhaustion, reuse, ownership, double-free",
    "AURORA_WX_OK: RX text, R-NX constants, RW-NX data, NXE, WP, guards",
)
USER_OK = "AURORA_USER_OK: ring3, own stack, TSS entry, controlled return"
# vector, error code, CPL, denied linear address, controlled user selector
FAULTS = {
    "--fault": (0, 0, 0, None, None),
    "--page-fault": (14, 0, 0, 0x400000, None),
    "--wp": (14, 3, 0, 0x10000, None),
    "--nx": (14, 17, 0, "target", None),
    "--stack": (8, 0, 0, "guard", None),
    "--user-read": (14, 5, 3, 0x10000, 1),
    "--user-write": (14, 7, 3, 0x10000, 2),
    "--user-cli": (13, 0, 3, None, 3),
    "--user-code-write": (14, 7, 3, 0x1D0000, 4),
    "--user-nx": (14, 21, 3, 0x1E0000, 5),
    "--user-io": (13, 0, 3, None, 6),
    "--program-bad-return": (129, 0, 3, None, None),
    "--program-unknown-trap": (6, 0, 3, None, None),
    "--program-kernel-trap": (6, 0, 0, None, None),
    "--domain-code": (14, 20, 3, 0x1B1000, None),
    "--domain-stack": (14, 5, 3, 0x104000, None),
    "--domain-root-mismatch": (129, 0, 3, None, None),
}

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


COMPILED_OK = "AURORA_COMPILED_USER_OK: arrays, loop, bounds, overflow, clean restart"


def program_flow(bounds: int, overflow: int) -> str:
    return ("AURORA_PROGRAM_ENTER: image=0\nAURORA_PROGRAM_RETURN: image=0 value=42\n"
            "AURORA_PROGRAM_ENTER: image=1\n"
            f"AURORA_PROGRAM_FAULT: image=1 kind=bounds vector=6 rip={bounds} cpl=3 frame=548688\n"
            "AURORA_PROGRAM_CONTAINED: image=1 kind=bounds\n"
            "AURORA_PROGRAM_ENTER: image=0\nAURORA_PROGRAM_RETURN: image=0 value=42\n"
            "AURORA_PROGRAM_ENTER: image=2\n"
            f"AURORA_PROGRAM_FAULT: image=2 kind=overflow vector=6 rip={overflow} cpl=3 frame=548688\n"
            "AURORA_PROGRAM_CONTAINED: image=2 kind=overflow\n"
            "AURORA_PROGRAM_ENTER: image=0\nAURORA_PROGRAM_RETURN: image=0 value=42\n"
            "AURORA_PROGRAM_ENTER: image=0\nAURORA_PROGRAM_RETURN: image=0 value=42\n" + COMPILED_OK + "\n")


def validate_program_sequence(transcript: str, metadata: dict | None) -> None:
    faults = re.findall(r"^AURORA_PROGRAM_FAULT: image=([0-9]+) kind=(bounds|overflow) vector=6 rip=([0-9]+) cpl=3 frame=([0-9]+)\r?$", transcript, re.MULTILINE)
    require(len(faults) == 2, "Missing compiled bounds/overflow faults")
    pcs = []
    for (image, kind, pc, frame), expected in zip(faults, (("1", "bounds"), ("2", "overflow"))):
        require((image, kind) == expected and 0x82000 <= int(frame) <= 0x86000 - 176, "Wrong contained fault kind/origin")
        base = 0x1B0000 + int(image) * 4096
        require(base <= int(pc) < base + 4096, "Contained fault outside active image")
        if metadata is not None:
            require(int(pc) == metadata[image][kind], "Contained fault does not match linked UD2 metadata")
        pcs.append(int(pc))
    actual = [line for line in transcript.splitlines() if line.startswith(("AURORA_PROGRAM_", "AURORA_COMPILED_USER_"))]
    expected = program_flow(*pcs).splitlines()
    # Frame address can vary with compiler stack layout; the bounds above are authoritative.
    normalize = lambda lines: [re.sub(r"frame=[0-9]+", "frame=checked", line) for line in lines]
    require(normalize(actual) == normalize(expected), "Program outcomes/restarts missing or out of order")


DOMAIN_REUSE = "AURORA_DOMAIN_REUSE_OK: stale denied, released bytes zero, partial rollback, same frames"
DOMAIN_OK = "AURORA_DOMAINS_OK: private CR3, private stacks, zero reuse, clean teardown"

def domain_fixture() -> str:
    return "AURORA_DOMAINS_READY: kernel=196608 root0=65536 frame0=1048576 root1=86016 frame1=1064960 root2=106496 frame2=1081344\n"

def domain_flow() -> str:
    roots = (65536, 86016, 106496)
    result = domain_fixture()
    for run, image in enumerate((0, 1, 0, 2, 0, 0)):
        if run == 5: result += DOMAIN_REUSE + "\n"
        result += f"AURORA_DOMAIN_ENTER: image={image} root={roots[image]}\n"
        result += f"AURORA_DOMAIN_EVENT: image={image} root={roots[image]}\n"
        result += "AURORA_DOMAIN_RESTORED: root=196608\n"
    return result + DOMAIN_OK + "\n"

def validate_domains(transcript: str, mode: str) -> None:
    ready = re.findall(r"^AURORA_DOMAINS_READY: kernel=([0-9]+) root0=([0-9]+) frame0=([0-9]+) root1=([0-9]+) frame1=([0-9]+) root2=([0-9]+) frame2=([0-9]+)\r?$", transcript, re.MULTILINE)
    require(len(ready) == 1, "Missing domain ownership setup")
    values = list(map(int, ready[0]))
    kernel = values[0]; roots = values[1::2]; frames = values[2::2]
    require(len(set([kernel] + roots)) == 4 and all(0x10000 <= root < 0x70000 and root % 4096 == 0 for root in [kernel] + roots), "CR3 roots are not distinct/aligned/bounded")
    require(all(0x100000 <= frame <= 0x180000 - 16384 and frame % 4096 == 0 for frame in frames), "Private stacks outside leased pool")
    require(all(abs(a - b) >= 16384 for index, a in enumerate(frames) for b in frames[index + 1:]), "Private stack leases overlap")
    actual = [line for line in transcript.splitlines() if line.startswith(("AURORA_DOMAIN_", "AURORA_DOMAINS_"))]
    expected = [next(line for line in transcript.splitlines() if line.startswith("AURORA_DOMAINS_READY:"))]
    if mode == "normal":
        for run, image in enumerate((0, 1, 0, 2, 0, 0)):
            if run == 5: expected.append(DOMAIN_REUSE)
            expected += [f"AURORA_DOMAIN_ENTER: image={image} root={roots[image]}",
                         f"AURORA_DOMAIN_EVENT: image={image} root={roots[image]}",
                         f"AURORA_DOMAIN_RESTORED: root={kernel}"]
        expected.append(DOMAIN_OK)
    else:
        expected.append(f"AURORA_DOMAIN_ENTER: image=0 root={roots[0]}")
        if mode == "--domain-root-mismatch": expected.append("AURORA_DOMAIN_ROOT_MISMATCH_INJECTED")
        observed = kernel if mode == "--domain-root-mismatch" else roots[0]
        expected.append(f"AURORA_DOMAIN_FAULT_ROOT: root={observed}")
    require(actual == expected, "Domain CR3 event/restore/teardown authority mismatch")

def validate(status: int, transcript: str, metadata: dict | None = None) -> None:
    lines = transcript.splitlines()
    require(status == 33, f"QEMU exit status {status}, expected 33")
    for marker in (*FOUNDATIONS, USER_OK, "AURORA_USER_ENTER: 0", "Aurora language result: 42", "AURORA_BOOT_OK"):
        require(lines.count(marker) == 1, f"Missing or duplicated marker: {marker}")
    require("AURORA_BOOT_FAIL" not in transcript and "AURORA_EXCEPTION_FATAL" not in transcript,
            "Normal run emitted failure")
    validate_program_sequence(transcript, metadata)
    validate_domains(transcript, "normal")


def validate_mode(status: int, transcript: str, mode: str, metadata: dict | None = None) -> None:
    if mode == "normal":
        validate(status, transcript, metadata)
        return
    lines = transcript.splitlines()
    require(status == 35, f"Fault QEMU exit status {status}, expected 35")
    require(lines.count("AURORA_BOOT_FAIL") == 1 and "AURORA_BOOT_OK" not in transcript, "Fault did not fail-stop")
    program_mode = mode.startswith(("--program-", "--domain-"))
    if program_mode:
        require(lines.count(USER_OK) == 1 and "AURORA_PROGRAM_ENTER: image=0" in lines, "Missing program entry")
        require("AURORA_PROGRAM_RETURN" not in transcript and "AURORA_PROGRAM_CONTAINED" not in transcript
                and COMPILED_OK not in transcript, "Rejected transition was incorrectly contained")
    else:
        require(USER_OK not in transcript, "Denied operation returned to success path")
    if mode == "--no-nx":
        require("Required NX capability or protected mapping validation failed" in lines, "Missing NX rejection")
        require("AURORA_WX_OK" not in transcript and "AURORA_EXCEPTION_FATAL" not in transcript, "NX absence was not rejected cleanly")
        return
    require(mode in FAULTS, "Unknown smoke mode")
    for marker in FOUNDATIONS:
        require(lines.count(marker) == 1, f"Fault happened before required foundation: {marker}")
    vector, error, cpl, denied, user_mode = FAULTS[mode]
    fatal = re.findall(r"^AURORA_EXCEPTION_FATAL: ([0-9]+) error=([0-9]+) rip=([0-9]+)\r?$", transcript, re.MULTILINE)
    require(len(fatal) == 1, "Missing or multiple fatal diagnostics")
    actual_vector, actual_error, rip = map(int, fatal[0])
    require((actual_vector, actual_error) == (vector, error), "Wrong CPU exception or error bits")
    contexts = re.findall(r"^AURORA_EXCEPTION_CONTEXT: cpl=([0-9]+) frame=([0-9]+) cr2=([0-9]+)\r?$", transcript, re.MULTILINE)
    require(len(contexts) == 1, "Missing or multiple privilege/stack contexts")
    actual_cpl, frame, cr2 = map(int, contexts[0])
    require(actual_cpl == cpl, "Wrong exception origin privilege")
    if mode == "--stack":
        require(0x7C000 <= frame < 0x80000 and "AURORA_IST_OK" in lines, "Double fault did not use emergency IST")
        require(0x87000 <= cr2 < 0x88000, "Stack fault outside guard")
    elif cpl == 3:
        require(0x82000 <= frame < 0x86000 and "AURORA_TSS_ENTRY_OK" in lines, "User exception did not use RSP0")
        if program_mode:
            if mode == "--domain-code": require(rip == 0x1B1000, "Foreign-code fault did not reject fetch")
            else: require(0x1B0000 <= rip < 0x1B1000, "Program fault did not originate in active image")
        else:
            require(f"AURORA_USER_ENTER: {user_mode}" in lines, "Wrong controlled user probe")
        if mode != "--user-nx" and not program_mode:
            require(0x1D0000 <= rip < 0x1D1000, "Fault did not originate in user code")
    else:
        require(0x88000 <= frame < 0x90000, "Kernel exception used unexpected stack")
    if program_mode: validate_domains(transcript, mode)
    if program_mode and metadata is not None:
        image = metadata["0"]
        if mode == "--program-kernel-trap":
            require(rip == image["bounds"], "Kernel-origin fault is not the exact known compiler trap")
        elif mode == "--program-unknown-trap":
            require(rip not in (image["bounds"], image["overflow"], image["return"]), "Unknown trap was actually authorized")
        elif mode == "--domain-root-mismatch":
            require(rip == image["return"], "CR3 mismatch must reject an otherwise authorized return PC")
        elif mode == "--program-bad-return":
            require(rip != image["return"], "Bad return matched authorized continuation")
    if isinstance(denied, int):
        require(cr2 == denied, "Page fault denied the wrong address")
    elif denied == "target":
        target = re.findall(r"^AURORA_FAULT_TARGET: ([0-9]+)\r?$", transcript, re.MULTILINE)
        require(len(target) == 1 and cr2 == int(target[0]) and rip == cr2, "NX fault did not deny the requested instruction fetch")
    if mode == "--user-nx":
        require(rip == cr2, "User NX fault did not deny instruction fetch")


def validate_fault(status: int, transcript: str, vector: int = 0) -> None:
    validate_mode(status, transcript, "--fault" if vector == 0 else "--page-fault")


def self_test() -> None:
    foundation = "\n".join(FOUNDATIONS) + "\n"
    good = foundation + USER_OK + "\nAURORA_USER_ENTER: 0\nAurora language result: 42\nAURORA_BOOT_OK\n"
    good += program_flow(0x1B1040, 0x1B2042) + domain_flow()
    validate(33, good)
    rejected = 0
    def must_reject(status: int, text: str, mode: str) -> None:
        nonlocal rejected
        try:
            validate_mode(status, text, mode)
        except ValueError:
            rejected += 1
            return
        raise RuntimeError(f"Bad transcript accepted for {mode}: {text!r}")
    for marker in (*FOUNDATIONS, USER_OK, "AURORA_USER_ENTER: 0", "Aurora language result: 42", "AURORA_BOOT_OK"):
        must_reject(33, good.replace(marker, "missing"), "normal")
    for status, text in ((0, good), (124, good), (33, good + "AURORA_BOOT_FAIL\n"),
                         (33, good + "AURORA_EXCEPTION_FATAL\n"), (33, good.replace("result: 42", "result: 420")),
                         (33, good + "AURORA_BOOT_OK\n")):
        must_reject(status, text, "normal")
    for mode, (vector, error, cpl, denied, user_mode) in FAULTS.items():
        frame = 0x7FF00 if mode == "--stack" else 0x85F00 if cpl == 3 else 0x8FF00
        cr2 = denied if isinstance(denied, int) else 0x87FF8 if denied == "guard" else 0x20000 if denied == "target" else 0
        rip = cr2 if mode in ("--nx", "--user-nx") else 0x1D0200 if cpl == 3 else 0x10500
        text = foundation
        if mode.startswith(("--program-", "--domain-")):
            text += USER_OK + "\nAURORA_PROGRAM_ENTER: image=0\n"
            rip = 0x1B1000 if mode == "--domain-code" else 0x1B0040
            text += domain_fixture() + "AURORA_DOMAIN_ENTER: image=0 root=65536\n"
            if mode == "--domain-root-mismatch": text += "AURORA_DOMAIN_ROOT_MISMATCH_INJECTED\n"
            text += "AURORA_DOMAIN_FAULT_ROOT: root=" + ("196608" if mode == "--domain-root-mismatch" else "65536") + "\n"
            if cpl == 3: text += "AURORA_TSS_ENTRY_OK\n"
        if user_mode is not None: text += f"AURORA_USER_ENTER: {user_mode}\nAURORA_TSS_ENTRY_OK\n"
        if mode == "--stack": text += "AURORA_IST_OK\n"
        if mode == "--nx": text += f"AURORA_FAULT_TARGET: {cr2}\n"
        text += f"AURORA_EXCEPTION_FATAL: {vector} error={error} rip={rip}\n"
        text += f"AURORA_EXCEPTION_CONTEXT: cpl={cpl} frame={frame} cr2={cr2}\nAURORA_BOOT_FAIL\n"
        validate_mode(35, text, mode)
        for status, corrupted in ((33, text), (35, text + "AURORA_BOOT_OK\n"),
                                  (35, text.replace(f"error={error} ", "error=99 ")),
                                  (35, text.replace(f"cpl={cpl} ", "cpl=2 ")),
                                  (35, text.replace(f"frame={frame} ", "frame=0 ")),
                                  (35, text.replace("AURORA_BOOT_FAIL", "missing"))):
            must_reject(status, corrupted, mode)
        if denied is not None:
            must_reject(35, text.replace(f"cr2={cr2}", "cr2=9"), mode)
    absent = "Required NX capability or protected mapping validation failed\nAURORA_BOOT_FAIL\n"
    validate_mode(35, absent, "--no-nx")
    must_reject(35, absent + "AURORA_WX_OK\n", "--no-nx")
    must_reject(33, good.replace("AURORA_PROGRAM_CONTAINED: image=1 kind=bounds\n", ""), "normal")
    must_reject(33, good.replace("AURORA_PROGRAM_RETURN: image=0 value=42", "AURORA_PROGRAM_RETURN: image=0 value=41", 1), "normal")
    expected_metadata = {"1": {"bounds": 0x1B1040}, "2": {"overflow": 0x1B2042}}
    validate(33, good, expected_metadata)
    try:
        validate(33, good.replace(f"rip={0x1B1040}", f"rip={0x1B1041}"), expected_metadata)
    except ValueError:
        rejected += 1
    else:
        raise RuntimeError("Wrong linked UD2 address accepted")
    must_reject(33, good.replace("root1=86016", "root1=65536"), "normal")
    must_reject(33, good.replace("frame1=1064960", "frame1=1048576"), "normal")
    must_reject(33, good.replace("AURORA_DOMAIN_RESTORED: root=196608", "AURORA_DOMAIN_RESTORED: root=65536", 1), "normal")
    must_reject(33, good.replace(DOMAIN_REUSE, "missing reuse"), "normal")
    print(f"PASS: smoke validators, 19 success cases and {rejected} failure regressions (no QEMU required)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) in (4, 5):
        try:
            metadata_path = Path(sys.argv[4]) if len(sys.argv) == 5 else Path(__file__).resolve().parents[1] / "build" / "user-metadata.json"
            metadata = json.loads(metadata_path.read_text())
            validate_mode(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], metadata)
        except ValueError as error:
            sys.exit(f"FAIL: {error}")
    else:
        sys.exit("usage: kernel-smoke.py --self-test | EXIT_STATUS SERIAL_LOG MODE [IMAGE_METADATA]")

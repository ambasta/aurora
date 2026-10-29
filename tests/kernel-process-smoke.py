#!/usr/bin/env python3
"""Serial oracle for the process-fixture rows (kernel/uefi/process.md#guest-rows).

    kernel-process-smoke.py STATUS LOG MODE IMAGE_DIR

The baseline exports one boot-volume entry, which must equal the repository
file of the same path; the volume size is the image's own ESP volume. A row
with a run list reduces each run to one `ORDINAL PATH ARGUMENTS<TAB>OUTCOME`
line compared with tests/kernel-process/MODE.golden; a run of bin/probe must
also equal the hosted probe's line in tests/host-files/cases.golden (without
its file tree), a run of bin/memory with the whole quota its line in
tests/host-files/memory.golden (a trap at the runtime's ud2 is SIGILL there)
and the compiler with no arguments the Linux compiler's line in
tests/host-files/usage.golden. A run's committed files are exported when it
ends; in process-files every run's line, with the volume's tree/ and the
files the run exported under it, must equal its hosted line in
tests/host-files/cases.golden (or limits.golden) but for the tree entries the
volume lacks by design (symlinks and a FIFO). In process-compile the first
run's object must equal the hosted build's host-sort.o (in the build root
above IMAGE_DIR) and each later run's diagnostics its line of
tests/kernel-process/compile.golden; in process-self-host the compiler's
object of itself must equal aurorac-stage2.o.
"""

import base64
import binascii
from pathlib import Path
import re
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from golden import compare, flat  # noqa: E402
from host_files import TREE  # noqa: E402
from kernel_profiles import COMPILE_GOLDEN, PROCESS_CASES  # noqa: E402
from kernel_uefi_oracle import exports, loader_selection, need  # noqa: E402

RECORD = re.compile(r"(AURORA_PROCESS_[A-Z_]+|AURORA_STDOUT|AURORA_STDERR): (.*)")

BASE = (
    "AURORA_UEFI_ENTRY",
    "AURORA_UEFI_EXIT_OK: attempts=1",
    "AURORA_UEFI_PAYLOAD_ENTRY",
    "AURORA_UEFI_OWNERSHIP_OK:",
    "AURORA_UEFI_PROTECTION_OK:",
    "AURORA_UEFI_LANGUAGE_OK: value=42",
    "AURORA_UEFI_OK",
)
FRAMES = re.compile(
    r"AURORA_PROCESS_FRAMES: frames=(\d+) ranges=(\d+) tables=(\d+) metadata=(\d+) free=(\d+)\r?$", re.M
)
EXPORTED = "examples/host-sort.au"
# Hosted tree entries the volume lacks by design.
ABSENT = {"dirlink", "fifo", "link"}


def ordered(text, markers):
    positions = []
    for marker in markers:
        need(text.count(marker) == 1, f"Missing/duplicate {marker}")
        positions.append(text.index(marker))
    need(positions == sorted(positions), "Record order")


def frames(text):
    """The inventory's own consistency; the kernel's walk and the hosted cases check the plan."""
    match = FRAMES.search(text)
    need(match and text.count("AURORA_PROCESS_FRAMES:") == 1, "Missing frame inventory")
    count, ranges, tables, metadata, free = map(int, match.groups())
    need(1 <= ranges <= 512 and tables and metadata and free > 0 and count == tables + metadata + free, "Inventory")
    return free


def fields(rest):
    return dict(word.split("=", 1) for word in rest.split() if "=" in word)


def tree(exported):
    """The hosted cases' `tree:` listing of the volume's tree/ and a run's exports."""
    entries = {path.split("/")[0]: None if "/" in path else len(content) for path, content in TREE.items()}
    for path, content in exported.items():
        parts = path.split("/")
        if parts[0] == "tree" and len(parts) == 2:
            entries[parts[1]] = len(content)
    return "tree: " + " ".join(name if size is None else f"{name}:{size}" for name, size in sorted(entries.items()))


def run_exports(text):
    """Each run's exported files, decoded from the records between its start and the next."""
    pieces = re.split(r"(?m)^(?=AURORA_PROCESS_RUN: )", text.replace("\r", ""))
    return {int(fields(piece.split("\n", 1)[0])["run"]): exports(piece) for piece in pieces[1:]}


def runs(text, mode):
    """One outcome line per run, checking each run's record order and release."""
    case, expected = PROCESS_CASES[mode]
    exported = run_exports(text)
    need(text.count(f"AURORA_PROCESS_CASE_SELECTED: value={case}\n") == 1, "Missing case selector echo")
    initial = int(FRAMES.search(text)[5])
    lines, current, output = [], None, None
    for kind, rest in RECORD.findall(text.replace("\r", "")):
        values = fields(rest)
        if kind in ("AURORA_STDOUT", "AURORA_STDERR"):
            need(current and current["loaded"] and int(values["run"]) == current["run"], "Output outside its run")
            try:
                output[kind].append(base64.b64decode(rest.split()[1], validate=True))
            except (binascii.Error, IndexError) as error:
                raise ValueError("Malformed output record") from error
            continue
        if kind == "AURORA_PROCESS_RUN":
            need(current is None, "Run started before the previous one ended")
            run = int(values["run"])
            need(run == len(lines) + 1 and run <= len(expected), "Run order")
            ticks, _, _, path, arguments = expected[run - 1]
            need(values["path"] == path and int(values["ticks"]) == ticks, "Run record differs from its list")
            current, output = {"run": run, "loaded": None, "key": f"{run} {path} {arguments}"}, {}
            output.update(AURORA_STDOUT=[], AURORA_STDERR=[])
            continue
        if kind in ("AURORA_PROCESS_FRAMES", "AURORA_PROCESS_VOLUME_OK", "AURORA_PROCESS_CASE_SELECTED"):
            continue
        if kind == "AURORA_PROCESS_WALK_OK":
            need(current and not current["loaded"] and expected[current["run"] - 1][1] & 2, "Walk probes")
            need(int(values["run"]) == current["run"] and values["rejected"] == "4", "Walk edit admitted")
            current["walked"] = True
            continue
        if kind not in ("AURORA_PROCESS_KERNEL_FAULT", "AURORA_PROCESS_FAIL", "AURORA_PROCESS_RUNS_OK"):
            need(current and int(values.get("run", 0)) == current["run"], "Record outside its run: " + kind)
        if kind == "AURORA_PROCESS_REJECTED":
            need(not current["loaded"], "Rejected after loading")
            lines.append(f"{current['key']}\trejected {values['reason']}")
            current = None
        elif kind == "AURORA_PROCESS_LOADED":
            need(current.get("walked", False) == bool(expected[current["run"] - 1][1] & 2), "Walk probes missing")
            current["loaded"] = int(values["pages"]) + int(values["tables"])
        elif kind == "AURORA_PROCESS_END":
            need(current["loaded"], "Ended before loading")
            streams = [
                f"{label}: " + flat(b"".join(output[stream]))
                for stream, label in (("AURORA_STDOUT", "stdout"), ("AURORA_STDERR", "stderr"))
                if output[stream]
            ]
            if values["reason"] == "exit":
                outcome = " | ".join([f"exit {values['status']}", *streams])
                if mode == "process-files":
                    outcome += " | " + tree(exported.get(current["run"], {}))
                elif exported.get(current["run"]):
                    outcome += " | exported: " + " ".join(
                        f"{path}:{len(content)}" for path, content in sorted(exported[current["run"]].items())
                    )
            elif values["reason"] == "watchdog":
                outcome = f"watchdog ticks={values['ticks']}"
            elif values["reason"] == "call":
                need(not streams, "Output before a refused call")
                outcome = f"call operation={values['operation']}"
            else:
                # The architectural error code tells which check refused (a page
                # fault's present/write/user/fetch bits, a gate's vector).
                outcome = " | ".join(
                    [f"{values['reason']} vector={values['vector']} error={values['error']}", *streams]
                )
            current["outcome"] = outcome
        elif kind == "AURORA_PROCESS_RELEASED":
            # Every frame of the load and of the memory service comes back.
            need(
                "outcome" in current and int(values["frames"]) == current["loaded"] + int(values["memory"]),
                "Released frames differ",
            )
            lines.append(f"{current['key']}\t{current['outcome']}")
            current = None
        elif kind == "AURORA_PROCESS_KERNEL_FAULT":
            need(current and current["loaded"] and "outcome" not in current, "Kernel fault outside a run")
            lines.append(f"{current['key']}\tkernel fault vector={values['vector']}")
            current = None
        elif kind == "AURORA_PROCESS_RUNS_OK":
            need(current is None and int(values["runs"]) == len(expected), "Runs incomplete")
            need(int(values["free"]) == initial, "Frames leaked across runs")
        elif kind != "AURORA_PROCESS_FAIL":
            raise ValueError("Unexpected process record " + kind)
    hosted, files = {}, {}
    for name in ("cases", "limits", "memory", "usage"):
        for line in (ROOT / f"tests/host-files/{name}.golden").read_text().splitlines():
            key, result = line.split("\t", 1)
            hosted[name, key] = result.split(" | tree:", 1)[0]
            if name in ("cases", "limits") and " | tree: " in result:
                head, listing = result.split(" | tree: ", 1)
                files[key] = head + " | tree: " + " ".join(e for e in listing.split() if e.split(":")[0] not in ABSENT)
    if mode == "process-files":
        for line in lines:
            key, outcome = line.split("\t")
            words = shlex.join(shlex.split(key.split(" ", 2)[2]))
            need(outcome == files.get(words), "Files case differs from its hosted golden: " + key)
        return lines
    for (_, _, quota, _, _), line in zip(expected, lines):
        key, outcome = line.split("\t")
        _, path, arguments = key.split(" ", 2)
        words = shlex.join(shlex.split(arguments))
        if path == "bin/probe" and not outcome.startswith("kernel fault"):
            need(hosted.get(("cases", words)) == outcome, "Probe differs from its hosted golden")
        if path == "bin/memory" and quota == 0:
            # The runtime's fail-stop trap is ud2: SIGILL on Linux.
            linux = outcome.replace("invalid_opcode vector=6 error=0", "signal 4", 1)
            need(hosted.get(("memory", words)) == linux, "Memory case differs from its hosted golden: " + words)
        if mode == "process-memory" and path == "bin/aurorac" and quota == 0:
            need(hosted.get(("usage", "")) == outcome, "Compiler differs from the Linux compiler")
    return lines


def compiled(text, mode, image, name):
    """A compile row: its first run's only export, `name`, is the hosted build's object of that name.

    The meson build root holds it: IMAGE_DIR is kernel-images/uefi/process-fixture beneath it.
    """
    lines, exported = runs(text, mode), run_exports(text)
    reference = (image.parents[2] / name).read_bytes()
    need(lines and "AURORA_PROCESS_RUNS_OK:" in text, "Compile row incomplete")
    need(lines[0].split("\t")[1] == f"exit 0 | exported: {name}:{len(reference)}", "Compile run failed")
    need(exported.get(1) == {name: reference}, f"Guest object differs from the hosted {name}")
    return lines, exported


def rejected(text, mode, image):
    """The compile row: host-sort.o is the hosted build's, its rejections the hosted compiler's."""
    lines, exported = compiled(text, mode, image, "host-sort.o")
    rejections = [line.split("\t", 1)[1] for line in (ROOT / COMPILE_GOLDEN).read_text().splitlines()]
    need(len(lines) == len(PROCESS_CASES[mode][1]) == 1 + len(rejections), "Compile runs")
    for index, (line, diagnostic) in enumerate(zip(lines[1:], rejections)):
        source = f"rejections/case-{index:04d}.au"
        # Like golden.py --reject: exit 1, no stdout, no output, the diagnostic without the source path.
        outcome = line.split("\t")[1].replace(f"{source}:", "")
        need(
            outcome == "exit 1 | stderr: " + diagnostic and not exported.get(index + 2), "Rejection differs: " + source
        )


def validate(status, text, mode, image):
    text = loader_selection(text, mode)
    need("AURORA_UEFI_PAYLOAD_FAIL" not in text and "AURORA_UEFI_EXCEPTION" not in text, "Payload failure")
    if mode == "process-volume-empty":
        need(status == 35 and text.count("AURORA_UEFI_FAIL: boot volume bounds") == 1, "Empty volume accepted")
        need("AURORA_UEFI_EXIT_OK" not in text and "AURORA_PROCESS" not in text, "Empty volume continued")
        return
    need("AURORA_UEFI_FAIL:" not in text, "Loader failure")
    ordered(text, BASE)
    volume = (image / "esp/aurora/volume").read_bytes()
    if mode == "process-volume-map":
        need(
            status == 35
            and text.count("AURORA_PROCESS_GRANT_REJECTED: reason=arena") == 1
            and text.count("AURORA_PROCESS_FAIL: boot volume map ownership") == 1,
            "Unconfirmed volume accepted",
        )
        need("AURORA_PROCESS_FRAMES" not in text and "AURORA_EXPORT" not in text, "Unconfirmed volume continued")
        return
    if mode == "process-volume-corrupt":
        frames(text)
        need(
            status == 35
            and text.count("AURORA_PROCESS_VOLUME_REJECTED: reason=order") == 1
            and text.count("AURORA_PROCESS_FAIL: boot volume admission") == 1,
            "Unsorted volume accepted",
        )
        need("AURORA_PROCESS_VOLUME_OK" not in text and "AURORA_EXPORT" not in text, "Unsorted volume continued")
        return
    if mode == "process-files":
        runs(text, mode)
        need(status == 33 and "AURORA_PROCESS_FAIL" not in text, "Process row failed")
        return
    if mode in ("process-compile", "process-self-host"):
        if mode == "process-compile":
            rejected(text, mode, image)
        else:
            # The compiler's object of itself is the one C1 emits (aurorac-stage2.o).
            need(len(compiled(text, mode, image, "aurorac-stage2.o")[0]) == 1, "Self-host runs")
        need(status == 33 and "AURORA_PROCESS_FAIL" not in text, "Process row failed")
        return
    if mode in PROCESS_CASES:
        compare(ROOT / f"tests/kernel-process/{mode}.golden", runs(text, mode))
        if mode == "process-hostile":
            need(status == 35 and text.count("AURORA_PROCESS_FAIL: kernel fault") == 1, "Kernel fault continued")
        else:
            need(status == 33 and "AURORA_PROCESS_FAIL" not in text, "Process row failed")
        return
    need(mode == "process-volume", "Unknown process mode")
    need(status == 33 and "AURORA_PROCESS_FAIL" not in text, "Process row failed")
    free = frames(text)
    ordered(
        text,
        (
            "AURORA_UEFI_OK",
            "AURORA_PROCESS_FRAMES:",
            f"AURORA_PROCESS_VOLUME_OK: bytes={len(volume)} pages={(len(volume) + 4095) // 4096}",
            f"AURORA_PROCESS_FRAMES_OK: allocated={free} scrubbed={free} released={free} rejected=6 leaks=0",
            "AURORA_PROCESS_SPACE_OK: rejected=4",
            f"AURORA_EXPORT_BEGIN: path={EXPORTED} bytes=",
            "AURORA_PROCESS_OK",
        ),
    )
    need(exports(text) == {EXPORTED: (ROOT / EXPORTED).read_bytes()}, "Exported bytes differ from the source")


if __name__ == "__main__":
    try:
        validate(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], Path(sys.argv[4]))
    except (ValueError, OSError) as error:
        sys.exit(f"FAIL: {error}")

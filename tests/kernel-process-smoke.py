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
above IMAGE_DIR), its second run's static executable the native-linked Aurora
host-sort-aurora-native, and each later run's diagnostics its line of
tests/kernel-process/compile.golden; in process-self-host the compiler's
object of itself must equal aurorac-stage2.o. Cases 1..6 use a fresh source
file-service companion for each existing client run. Its separate lifecycle
records must prove distinct authority and exact release without renumbering
clients, weakening hosted results, or changing the export artifact comparison.
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

RECORD = re.compile(
    r"(AURORA_PROCESS_[A-Z_]+|AURORA_FILE_SERVICE_(?:LOADED|END|RELEASED)|AURORA_STDOUT|AURORA_STDERR): (.*)"
)

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
    paired = mode == "process-lifecycle"
    isolated = 1 <= case <= 6
    retained = mode in (
        "process-service",
        "process-service-hostile",
        "process-xfs",
        "process-xfs-clean",
        "process-xfs-recover",
        "process-xfs-recover-pair",
        "process-xfs-mounted",
        "process-xfs-mounted-small",
        "process-xfs-mounted-loss",
    )
    exported = {} if paired else run_exports(text)
    need(text.count(f"AURORA_PROCESS_CASE_SELECTED: value={case}\n") == 1, "Missing case selector echo")
    initial = int(FRAMES.search(text)[5])
    lines, current, output = [], None, None
    live, completed = {}, {}
    started = 0
    parked = set()
    companion, last_generation, released_companions = None, 0, 0
    seen_owners = set()
    fatal_companion = None
    mounted_bootstrap = mode in ("process-xfs-mounted", "process-xfs-mounted-small", "process-xfs-mounted-loss")
    bootstrap_owners = set()
    normalized = text.replace("\r", "")
    for kind, rest in RECORD.findall(normalized):
        values = fields(rest)
        if kind.startswith("AURORA_FILE_SERVICE_"):
            need(isolated, "Unexpected implicit file-service companion")
            run, generation = int(values["run"]), int(values["generation"])
            if kind == "AURORA_FILE_SERVICE_LOADED":
                need(companion is None and not live, "Companion loaded before prior cleanup")
                need(run == started + 1 and run <= len(expected), "Companion belongs to the next client")
                owner, root = int(values["owner"]), int(values["root"])
                pages, tables = int(values["pages"]), int(values["tables"])
                need(
                    generation > last_generation and owner > 0 and owner not in seen_owners,
                    "Companion incarnation or owner reused",
                )
                need(
                    root > 0 and root % 4096 == 0 and pages > 0 and tables > 0 and int(values["quota"]) >= 0,
                    "Companion load authority or extent",
                )
                companion = dict(
                    run=run, generation=generation, owner=owner, root=root, loaded=pages + tables, ended=False
                )
                seen_owners.add(owner)
                last_generation = generation
            else:
                need(
                    companion is not None and run == companion["run"] and generation == companion["generation"],
                    "Companion record outside its incarnation",
                )
                need(run in completed and not live, "Companion retired before client completion")
                if kind == "AURORA_FILE_SERVICE_END":
                    need(
                        not companion["ended"] and values["reason"] == "exit" and int(values["status"]) == 0,
                        "Fresh file-service companion failed or ended twice",
                    )
                    companion["ended"] = True
                else:
                    need(
                        companion["ended"] and int(values["frames"]) == companion["loaded"] + int(values["memory"]),
                        "Companion released frames differ",
                    )
                    companion = None
                    released_companions += 1
            continue
        if kind == "AURORA_PROCESS_LOADED" and mounted_bootstrap and int(values["run"]) not in live:
            # Production start_file_service is not load_one: its actual LOADED
            # record starts the service lifecycle, without a fixture RUN record.
            # Admit only these closed service slots, never an ordinary client.
            run = int(values["run"])
            need(run == 1 or (mode == "process-xfs-mounted-loss" and run == 3), "Unexpected service bootstrap slot")
            need(not live and run == started + 1 and run <= len(expected), "Service bootstrap before cleanup")
            path = "bin/file-service-mounted" if run == 1 else "bin/file-service"
            need(expected[run - 1] == (64, 0, 32768, path, "file-service"), "Canonical bootstrap entry differs")
            need(
                int(values["quota"]) == 32768 and int(values["pages"]) > 0 and int(values["tables"]) > 0,
                "Service bootstrap load extent",
            )
            owner, root = int(values["owner"]), int(values["root"])
            need(
                owner > 0 and owner not in bootstrap_owners and root > 0 and root % 4096 == 0,
                "Service bootstrap authority",
            )
            marker = "AURORA_PROCESS_LOADED: " + rest
            need(
                len(re.findall(rf"^AURORA_PROCESS_LOADED: run={run} ", normalized, re.M)) == 1,
                "Duplicate service bootstrap load",
            )
            if run == 1:
                grants = re.findall(r"^AURORA_MOUNTED_GRANTED: (.*)$", normalized, re.M)
                need(len(grants) == 1, "Service bootstrap needs its unique mounted grant")
                grant = fields(grants[0])
                need(
                    int(grant["owner"]) == owner
                    and int(grant["root"]) == root
                    and normalized.index(marker) < normalized.index("AURORA_MOUNTED_GRANTED:"),
                    "Service load and mounted grant differ",
                )
            else:
                need(1 in completed and 2 in completed, "RAM restart before original pair release")
                need(
                    normalized.index("AURORA_MOUNTED_RETIRED:") < normalized.index(marker),
                    "RAM restart before writer retirement",
                )
                ready = re.findall(r"^AURORA_FILE_SERVICE_READY: generation=\d+ disk=unavailable$", normalized, re.M)
                need(
                    len(ready) == 1
                    and normalized.index(marker)
                    < normalized.index(ready[0])
                    < normalized.index("AURORA_PROCESS_RUN: run=4 path=bin/lifecycle ticks=16"),
                    "RAM bootstrap readiness order",
                )
            bootstrap_owners.add(owner)
            started = run
            current = {
                "run": run,
                "loaded": None,
                "key": f"{run} {path} file-service",
                "parks": 0,
                "output": {"AURORA_STDOUT": [], "AURORA_STDERR": []},
            }
            live[run] = current
        if "run" in values and kind != "AURORA_PROCESS_RUN":
            current = live.get(int(values["run"]))
            output = current["output"] if current else None
        if (
            paired
            and current
            and kind in ("AURORA_STDOUT", "AURORA_STDERR", "AURORA_PROCESS_PARKED", "AURORA_PROCESS_END")
        ):
            for waiting in parked:
                if waiting != current["run"]:
                    live[waiting]["peer_observed"] = True
        if kind in ("AURORA_STDOUT", "AURORA_STDERR"):
            need(current and current["loaded"] and int(values["run"]) == current["run"], "Output outside its run")
            try:
                output[kind].append(base64.b64decode(rest.split()[1], validate=True))
            except (binascii.Error, IndexError) as error:
                raise ValueError("Malformed output record") from error
            continue
        if kind == "AURORA_PROCESS_RUN":
            need(not live or paired or retained, "Run started before the previous one ended")
            need(len(live) < 2, "Resident limit")
            run = int(values["run"])
            need(run == started + 1 and run <= len(expected), "Run order")
            if isolated:
                need(
                    companion is not None and companion["run"] == run and not companion["ended"],
                    "Client started without its fresh source file service",
                )
            started = run
            ticks, _, _, path, arguments = expected[run - 1]
            need(values["path"] == path and int(values["ticks"]) == ticks, "Run record differs from its list")
            current, output = {"run": run, "loaded": None, "key": f"{run} {path} {arguments}"}, {}
            output.update(AURORA_STDOUT=[], AURORA_STDERR=[])
            current["output"] = output
            current["parks"] = 0
            live[run] = current
            continue
        if kind in ("AURORA_PROCESS_FRAMES", "AURORA_PROCESS_VOLUME_OK", "AURORA_PROCESS_CASE_SELECTED"):
            continue
        if kind in ("AURORA_PROCESS_PARKED", "AURORA_PROCESS_RESUMED"):
            need(paired and current and current["loaded"], "Continuation outside a resident")
            run, ticks = current["run"], int(values["ticks"])
            if kind == "AURORA_PROCESS_PARKED":
                need(run not in parked and ticks == current["parks"] + 1, "Repeated or reset park")
                need(ticks < expected[run - 1][0], "Park exhausted its budget")
                current["parks"] = ticks
                parked.add(run)
            else:
                need(run in parked and ticks == current["parks"], "Resume without its original park")
                parked.remove(run)
                if run in (3, 5) and run + 1 in completed:
                    current["resumed_after_failure"] = True
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
            completed[current["run"]] = f"{current['key']}\trejected {values['reason']}"
            del live[current["run"]]
            current = None
        elif kind == "AURORA_PROCESS_LOADED":
            need(current.get("walked", False) == bool(expected[current["run"] - 1][1] & 2), "Walk probes missing")
            current["loaded"] = int(values["pages"]) + int(values["tables"])
            if paired or retained or isolated:
                current["root"] = int(values["root"])
                current["owner"] = int(values["owner"])
                need(current["root"] > 0 and current["root"] % 4096 == 0, "Process root")
                if isolated:
                    need(
                        current["owner"] > 0 and current["owner"] not in seen_owners, "Client incarnation owner reused"
                    )
                    seen_owners.add(current["owner"])
                    need(
                        companion is not None
                        and current["root"] != companion["root"]
                        and current["owner"] != companion["owner"],
                        "Client/companion authority alias",
                    )
                for other in live.values():
                    if other is not current and other["loaded"]:
                        need(
                            other["root"] != current["root"] and other["owner"] != current["owner"],
                            "Resident authority alias",
                        )
        elif kind == "AURORA_PROCESS_END":
            need(current["loaded"] and current["run"] not in parked, "Ended before loading or while parked")
            if paired and expected[current["run"] - 1][4] in ("lifecycle A", "lifecycle B"):
                need(current["parks"] > 0, "Finite resident never resumed")
                if current["run"] <= 6:
                    need(current.get("peer_observed"), "No peer ran while the survivor was parked")
                if current["run"] in (3, 5):
                    need(current.get("resumed_after_failure"), "Survivor did not resume after peer failure cleanup")
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
            elif values["reason"] == "service_lost":
                outcome = " | ".join(["service_lost", *streams])
            elif values["reason"] == "cancelled":
                need(
                    mode == "process-service"
                    and expected[current["run"] - 1][4] in ("raw-cancel-initial", "raw-cancel-tail")
                    and not streams,
                    "Unexpected explicit cancellation",
                )
                outcome = "cancelled"
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
            completed[current["run"]] = f"{current['key']}\t{current['outcome']}"
            del live[current["run"]]
            current = None
        elif kind == "AURORA_PROCESS_KERNEL_FAULT":
            need(current and current["loaded"] and "outcome" not in current, "Kernel fault outside a run")
            completed[current["run"]] = f"{current['key']}\tkernel fault vector={values['vector']}"
            if isolated:
                fatal_companion = current["run"]
            del live[current["run"]]
            current = None
        elif kind == "AURORA_PROCESS_RUNS_OK":
            need(companion is None and (not isolated or released_companions == len(expected)), "Companions incomplete")
            need(not live and not parked and int(values["runs"]) == len(expected), "Runs incomplete")
            need(int(values["free"]) == initial, "Frames leaked across runs")
        elif kind != "AURORA_PROCESS_FAIL":
            raise ValueError("Unexpected process record " + kind)
    need(not live and not parked and len(completed) == len(expected), "Missing process completion")
    if isolated:
        if fatal_companion is not None:
            need(
                mode == "process-hostile"
                and fatal_companion == len(expected)
                and text.count("AURORA_PROCESS_FAIL: kernel fault") == 1
                and companion is not None
                and companion["run"] == fatal_companion
                and not companion["ended"]
                and released_companions == len(expected) - 1,
                "Only the deliberate final kernel fault may leave its companion live",
            )
        else:
            need(companion is None and released_companions == len(expected), "Missing companion release")
    lines = [completed[run] for run in range(1, len(expected) + 1)]
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
        if path == "bin/probe" and not retained and not outcome.startswith("kernel fault"):
            need(hosted.get(("cases", words)) == outcome, "Probe differs from its hosted golden")
        if path == "bin/memory" and quota == 0:
            # The runtime's fail-stop trap is ud2: SIGILL on Linux.
            linux = outcome.replace("invalid_opcode vector=6 error=0", "signal 4", 1)
            need(hosted.get(("memory", words)) == linux, "Memory case differs from its hosted golden: " + words)
        if mode == "process-memory" and path == "bin/aurorac" and quota == 0:
            need(hosted.get(("usage", "")) == outcome, "Compiler differs from the Linux compiler")
    return lines


def artifact(lines, exported, image, ordinal, name):
    """An exported artifact equals the build-root reference, without relinking it."""
    reference = (image.parents[2] / name).read_bytes()
    need(lines[ordinal - 1].split("\t")[1] == f"exit 0 | exported: {name}:{len(reference)}", "Compile run failed")
    need(exported.get(ordinal) == {name: reference}, f"Guest artifact differs from the hosted {name}")


def compiled(text, mode, image, name):
    """A compile row's first export; IMAGE_DIR is kernel-images/uefi/process-fixture."""
    lines, exported = runs(text, mode), run_exports(text)
    need(lines and "AURORA_PROCESS_RUNS_OK:" in text, "Compile row incomplete")
    artifact(lines, exported, image, 1, name)
    return lines, exported


def rejected(text, mode, image):
    """Guest object/executable bytes match; rejected sources keep the hosted diagnostics."""
    lines, exported = compiled(text, mode, image, "host-sort.o")
    rejections = [line.split("\t", 1)[1] for line in (ROOT / COMPILE_GOLDEN).read_text().splitlines()]
    need(len(lines) == len(PROCESS_CASES[mode][1]) == 2 + len(rejections), "Compile runs")
    artifact(lines, exported, image, 2, "host-sort-aurora-native")
    for index, (line, diagnostic) in enumerate(zip(lines[2:], rejections)):
        source = f"rejections/case-{index:04d}.au"
        # Like golden.py --reject: exit 1, no stdout, no output, the diagnostic without the source path.
        outcome = line.split("\t")[1].replace(f"{source}:", "")
        need(
            outcome == "exit 1 | stderr: " + diagnostic and not exported.get(index + 3), "Rejection differs: " + source
        )


def recovery_authority(text, writes, flushes):
    grant = re.findall(r"AURORA_RECOVERY_GRANTED: owner=(\d+) root=(\d+) generation=(\d+) sectors=(\d+)", text)
    need(
        len(grant) == 1
        and int(grant[0][0]) > 0
        and int(grant[0][1]) > 0
        and int(grant[0][1]) % 4096 == 0
        and grant[0][2:] == ("1", "1048576"),
        "Recovery boot authority",
    )
    retired = (
        f"AURORA_RECOVERY_RETIRED: generation=1 sealed=1 readonly=1 admitted_writes={writes} admitted_flushes={flushes}"
    )
    need(text.count(retired) == 1, "Recovery sealed retirement")
    ready = re.findall(
        r"AURORA_FILE_SERVICE_READY: generation=(\d+) owner=(\d+) block_generation=(\d+) block_sectors=(\d+)", text
    )
    need(
        len(ready) == 1 and ready[0][0] == "1" and ready[0][2:] == ("2", "1048576") and ready[0][1] != grant[0][0],
        "Fresh independent readonly owner",
    )
    need(
        text.index("AURORA_PROCESS_RELEASED: run=1 ") < text.index(retired) < text.index("AURORA_FILE_SERVICE_READY:"),
        "Recovery release and reader admission order",
    )
    need(
        "AURORA_FILE_SERVICE_LOST:" not in text and "AURORA_NVME_QUARANTINED:" not in text,
        "Recovery service/backend loss",
    )


def mounted_authority(status, text, mode, image, cut, plan):
    """Authenticate the real service lifecycle and exact acknowledged write boundary."""
    from kernel_profiles import MOUNTED_CUT_CASES

    need(
        mode in ("process-xfs-mounted", "process-xfs-mounted-small", "process-xfs-mounted-loss") and len(plan) == 16,
        "Mounted profile and plan",
    )
    loss = mode == "process-xfs-mounted-loss"
    frames(text)
    grants = re.findall(
        r"AURORA_MOUNTED_GRANTED: owner=(\d+) root=(\d+) generation=(\d+) service=(\d+) sectors=(\d+)", text
    )
    need(len(grants) == 1, "One mounted writer grant")
    owner, root, generation, service, sectors = map(int, grants[0])
    need(
        owner > 0 and root > 0 and root % 4096 == 0 and generation > 0 and service > 0 and sectors == 1048576,
        "Mounted service authority",
    )
    armed = f"AURORA_MOUNTED_ARMED: generation={generation}"
    ready = f"AURORA_FILE_SERVICE_READY: generation={service} disk=ready"
    client = "AURORA_PROCESS_RUN: run=2 path=bin/lifecycle ticks=16"
    need(text.count(armed) == 1 and text.count(ready) == 1 and text.count(client) == 1, "Clean mounted admission")
    need(
        text.index("AURORA_MOUNTED_GRANTED:") < text.index(armed) < text.index(ready) < text.index(client),
        "Mounted clean admission precedes client",
    )
    fences = [(i + 1, sum(record[1] for record in plan[: i + 1])) for i, record in enumerate(plan) if record[1]]
    if cut:
        need(mode == "process-xfs-mounted" and cut in MOUNTED_CUT_CASES, "Closed mounted cut")
        case = MOUNTED_CUT_CASES[cut]
        operation, value = cut.split("-")
        ordinal = int(value)
        if operation == "write":
            writes, flushes = ordinal, sum(record[1] for record in plan[: ordinal - 1])
            opcode, lba = 18, plan[ordinal - 1][0]
        else:
            writes, flushes = fences[ordinal - 1]
            opcode, lba = 19, 0
        trace = (
            f"AURORA_MOUNTED_CUT: case={case} operation={opcode} ordinal={ordinal} "
            f"lba={lba} generation={generation} writes={writes} flushes={flushes}"
        )
        need(
            status == 37 and text.count(trace) == 1 and text.count("AURORA_MOUNTED_CUT:") == 1,
            "Mounted acknowledged boundary",
        )
        need(text.count(f"AURORA_PROCESS_CASE_SELECTED: value={case}") == 1, "Mounted cut selector")
        fences = [(w, f) for w, f in fences if f < flushes or (operation == "write" and f == flushes)]
        need(
            not any(
                marker in text
                for marker in (
                    "AURORA_PROCESS_END:",
                    "AURORA_PROCESS_RELEASED:",
                    "AURORA_MOUNTED_RETIRED:",
                    "AURORA_PROCESS_RUNS_OK:",
                    "AURORA_PROCESS_FAIL:",
                    "AURORA_FILE_SERVICE_OK:",
                    "AURORA_FILE_SERVICE_LOST:",
                    "AURORA_MOUNTED_OWNER_LOSS:",
                )
            ),
            "Mounted cut continued into publication acknowledgement or cleanup",
        )
    else:
        need(
            status == 33 and "AURORA_PROCESS_FAIL:" not in text and "AURORA_MOUNTED_CUT:" not in text,
            "Mounted replacement failed",
        )
        retired = f"AURORA_MOUNTED_RETIRED: generation={generation} writes=16 flushes=5 disk=unavailable"
        need(text.count(retired) == 1, "Mounted budget consumed and authority retired")
        final_fence = f"AURORA_MOUNTED_FENCE: generation={generation} writes=16 flushes=5"
        if loss:
            injected = f"AURORA_MOUNTED_OWNER_LOSS: generation={generation} writes=16 flushes=5"
            need(text.count(injected) == 1, "Explicit mounted owner termination")
            lost = re.findall(
                r"AURORA_FILE_SERVICE_LOST: generation=(\d+) transaction=(\d+) cause=exit status=1 volatile_data=lost",
                text,
            )
            restarted = re.findall(r"AURORA_FILE_SERVICE_READY: generation=(\d+) disk=unavailable", text)
            need(
                len(lost) == 1
                and int(lost[0][0]) == service
                and int(lost[0][1]) > 0
                and text.count("AURORA_FILE_SERVICE_LOST:") == 1,
                "Actual owner exit lost the unconfirmed reply",
            )
            need(
                len(restarted) == 1 and int(restarted[0]) > service and text.count("AURORA_FILE_SERVICE_READY:") == 2,
                "Fresh RAM-only service incarnation",
            )
            need(text.count("AURORA_MOUNTED_ARMED:") == 1, "Writer was not rearmed")
            need(
                text.index(injected)
                < text.index(final_fence)
                < text.index("AURORA_PROCESS_END: run=1 reason=exit status=1")
                < text.index(retired)
                < text.index("AURORA_PROCESS_END: run=2 reason=service_lost")
                < text.index(f"AURORA_FILE_SERVICE_READY: generation={restarted[0]} disk=unavailable")
                < text.index("AURORA_PROCESS_RUN: run=4 path=bin/lifecycle ticks=16"),
                "Owner retirement, client loss and RAM-only restart order",
            )
        else:
            need(
                text.index(final_fence) < text.index("AURORA_PROCESS_END: run=2") < text.index(retired),
                "Mounted persistence before client completion and retirement",
            )
            need(
                "AURORA_MOUNTED_OWNER_LOSS:" not in text and "AURORA_FILE_SERVICE_LOST:" not in text,
                "Unexpected owner loss",
            )
        need(
            len(re.findall(r"AURORA_FILE_SERVICE_OK: clients=1 transactions=[1-9][0-9]*", text)) == 1,
            "Mounted source service completed",
        )
        compare(ROOT / f"tests/kernel-process/{mode}.golden", runs(text, mode))
    observed = re.findall(r"AURORA_MOUNTED_FENCE: generation=(\d+) writes=(\d+) flushes=(\d+)", text)
    need(observed == [(str(generation), str(w), str(f)) for w, f in fences], "Mounted durable fence sequence")
    need(
        not any(
            marker in text
            for marker in (
                "AURORA_RECOVERY_GRANTED:",
                "AURORA_RECOVERY_RETIRED:",
                "AURORA_NVME_QUARANTINED:",
            )
        ),
        "Mounted authority was reset or lost",
    )


def validate(
    status,
    text,
    mode,
    image,
    *,
    xfs_history=None,
    recovery_state="dirty",
    recovery_cut=None,
    recovery_exchange=False,
    recovery_pair_prefix=None,
    mounted_cut=None,
    mounted_plan=(),
):
    need(
        xfs_history in ("used", "wrapped", "dirty") if mode == "process-xfs-clean" else xfs_history is None,
        "Clean-XFS expected history",
    )
    need(not recovery_exchange or mode == "process-xfs-recover", "Exchange requires the recovery fixture")
    need((mode == "process-xfs-recover-pair") == (recovery_pair_prefix is not None), "Pair prefix requires case41")
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
    if mode in ("process-xfs-mounted", "process-xfs-mounted-small", "process-xfs-mounted-loss"):
        mounted_authority(status, text, mode, image, mounted_cut, mounted_plan)
        return
    if mode == "process-xfs-recover-pair":
        from kernel_profiles import mounted_recovery_outcome

        need(recovery_pair_prefix is not None, "Pair expected command prefix")
        writes, flushes, target, _ = mounted_recovery_outcome(recovery_pair_prefix)
        free = frames(text)
        need(text.count(f"AURORA_RECOVERY_CLEANUP: free={free}") == 1, "Pair recovery frame baseline")
        recovery_authority(text, writes, flushes)
        need(
            status == 33
            and "AURORA_PROCESS_FAIL:" not in text
            and "AURORA_MOUNTED_GRANTED:" not in text
            and "AURORA_MOUNTED_ARMED:" not in text,
            "Pair recovery failed or reminted a mounted writer",
        )
        expected = [
            "1 bin/xfs-recover xfs-recover\texit 0",
            "2 bin/file-service file-service\texit 0",
            "3 bin/isolation-6 writer-stale-write\tcall operation=18",
            "4 bin/isolation-6 writer-stale-flush\tcall operation=19",
            "5 bin/lifecycle lifecycle recovered-pair\texit 0 | stdout: "
            f"xfs recovered pair {target} readonly stage hidden ram intact",
        ]
        need(runs(text, mode) == expected, "Pair real HostFiles lifecycle or stale writer probe")
        need(text.count("AURORA_FILE_SERVICE_OK:") == 1, "Pair retained readonly service lifecycle")
        return
    if recovery_cut:
        from kernel_profiles import RECOVERY_CUT_CASES

        need(mode == "process-xfs-recover" and recovery_cut in RECOVERY_CUT_CASES, "Closed recovery cut")
        case = RECOVERY_CUT_CASES[recovery_cut]
        frames(text)
        need(text.count(f"AURORA_PROCESS_CASE_SELECTED: value={case}") == 1, "Cut fixture selector")
        operation, ordinal, lba, writes, flushes = {
            "write-1": (18, 1, 99, 1, 0),
            "flush-1": (19, 1, 0, 2, 1),
            "flush-2": (19, 2, 0, 3, 2),
            "flush-3": (19, 3, 0, 4, 3),
        }[recovery_cut]
        if recovery_exchange:
            operation, ordinal, lba, writes, flushes = {
                "write-1": (18, 1, 96, 1, 0),
                "flush-1": (19, 1, 0, 1, 1),
                "flush-2": (19, 2, 0, 2, 2),
                "flush-3": (19, 3, 0, 3, 3),
            }[recovery_cut]
        grant = re.findall(
            r"AURORA_RECOVERY_GRANTED: owner=([0-9]+) root=([0-9]+) generation=([0-9]+) sectors=1048576", text
        )
        need(len(grant) == 1 and all(int(value) for value in grant[0]), "Cut authenticated writer grant")
        generation = int(grant[0][2])
        trace = (
            f"AURORA_RECOVERY_CUT: case={case} operation={operation} ordinal={ordinal} "
            f"lba={lba} generation={generation} writes={writes} flushes={flushes}"
        )
        need(
            status == 37 and text.count(trace) == 1 and text.count("AURORA_RECOVERY_CUT:") == 1,
            "Completed boundary cut",
        )
        need(text.count("AURORA_PROCESS_RUN: run=1 path=bin/xfs-recover ticks=16") == 1, "Cut original source")
        need(
            not any(
                marker in text
                for marker in (
                    "AURORA_PROCESS_END:",
                    "AURORA_PROCESS_RELEASED:",
                    "AURORA_RECOVERY_RETIRED:",
                    "AURORA_RECOVERY_CLEANUP:",
                    "AURORA_FILE_SERVICE_READY:",
                    "AURORA_BLOCK_GRANTED:",
                    "AURORA_PROCESS_RUN: run=2",
                    "AURORA_PROCESS_RUNS_OK:",
                    "AURORA_PROCESS_FAIL:",
                )
            ),
            "Cut continued into retirement, failure or read-only service",
        )
        return
    if mode == "process-xfs-recover":
        free = frames(text)
        need(text.count("AURORA_PROCESS_CASE_SELECTED: value=12") == 1, "Recovery fixture selector")
        need(
            text.count(f"AURORA_RECOVERY_CLEANUP: free={free}") == 1,
            "Recovery did not restore its complete frame baseline",
        )
    if mode == "process-xfs-recover" and recovery_state == "refused":
        frames(text)
        need(
            status == 35 and text.count("AURORA_PROCESS_FAIL: recovery not completed") == 1,
            "Refused recovery continued",
        )
        need(
            text.count("AURORA_PROCESS_RUN: run=1 path=bin/xfs-recover ticks=16") == 1
            and text.count("AURORA_PROCESS_END: run=1 reason=exit status=1") == 1
            and text.count("AURORA_PROCESS_RELEASED: run=1 ") == 1,
            "Refused recovery program lifecycle",
        )
        need(
            text.count("AURORA_RECOVERY_RETIRED: generation=1 sealed=0 readonly=0 admitted_writes=0 admitted_flushes=0")
            == 1,
            "Refused recovery performed I/O or promoted reader",
        )
        need(
            "AURORA_FILE_SERVICE_READY:" not in text and "AURORA_PROCESS_RUN: run=2 " not in text,
            "Refused recovery exposed read-only service",
        )
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
    if mode == "process-service-hostile":
        ready = [int(value) for value in re.findall(r"AURORA_FILE_SERVICE_READY: generation=(\d+)", text)]
        lost = [int(value) for value in re.findall(r"AURORA_FILE_SERVICE_LOST: generation=(\d+)", text)]
        need(ready == list(range(1, 12)) and lost == list(range(1, 11)), "Service restart incarnation/loss order")
        causes = re.findall(
            r"AURORA_FILE_SERVICE_LOST: generation=\d+ transaction=\d+ cause=([^\n]+) volatile_data=lost", text
        )
        need(
            causes
            == ["call operation=15"] * 5
            + ["invalid_reply operation=18"] * 2
            + ["fault vector=6", "watchdog ticks=8", "call operation=15"],
            "Service loss must preserve the checked reply refusal or actual terminal outcome",
        )
        need(
            text.count(" volatile_data=lost") == 10 and text.count("AURORA_FILE_SERVICE_OK:") == 1,
            "Service loss visibility or healthy restart",
        )
        delivered = re.findall(
            r"^AURORA_EXECUTION_CANCEL: client=(\d+) tail=(\d+) generation=(\d+) transaction=(\d+) next=(\d+)$",
            text.replace("\r", ""),
            re.MULTILINE,
        )
        need(
            len(delivered) == 1
            and delivered[0][:3] == ("18", "2", "9")
            and int(delivered[0][3]) > 0
            and delivered[0][3] == delivered[0][4]
            and text.count("AURORA_EXECUTION_CANCEL:") == 1,
            "Authenticated delivered-request cancellation boundary",
        )
    if mode == "process-xfs":
        ready = re.findall(
            r"AURORA_FILE_SERVICE_READY: generation=(\d+) owner=\d+ block_generation=(\d+) block_sectors=(\d+)", text
        )
        need(ready == [("1", "1", "1048576"), ("2", "2", "1048576")], "Block lease extent/incarnation")
        need(
            re.findall(
                r"AURORA_FILE_SERVICE_LOST: generation=1 transaction=\d+ cause=([^\n]+) volatile_data=lost", text
            )
            == ["call operation=16"],
            "Block grant refusal loss cause",
        )
        need(
            text.count("AURORA_FILE_SERVICE_LOST: generation=1 ") == 1
            and text.count(" volatile_data=lost") == 1
            and text.count("AURORA_FILE_SERVICE_OK:") == 1,
            "Block forgery cleanup or fresh mount recovery",
        )
    if mode == "process-service":
        need(
            text.count("AURORA_FILE_SERVICE_READY:") == 1 and text.count("AURORA_FILE_SERVICE_OK:") == 1,
            "Retained file service did not run and terminate",
        )
        need("AURORA_FILE_SERVICE_LOST:" not in text, "File service lost its state")
        cancelled = re.findall(
            r"^AURORA_EXECUTION_CANCEL: client=(\d+) tail=([01]) generation=(\d+) transaction=(\d+) next=(\d+)$",
            text.replace("\r", ""),
            re.MULTILINE,
        )
        expected_cancel = [
            (str(index), str(int(row[4] == "raw-cancel-tail")))
            for index, row in enumerate(PROCESS_CASES[mode][1], 1)
            if row[4] in ("raw-cancel-initial", "raw-cancel-tail")
        ]
        need(
            [(client, tail) for client, tail, _, _, _ in cancelled] == expected_cancel
            and all(
                generation == "1" and int(transaction) > 0 and transaction == next_id
                for _, _, generation, transaction, next_id in cancelled
            ),
            "Authenticated initial/tail cancellation boundaries",
        )
        need(text.count("AURORA_EXECUTION_CANCEL:") == len(cancelled), "Malformed cancellation boundary")
    if mode == "process-xfs-clean":
        ready = re.findall(
            r"AURORA_FILE_SERVICE_READY: generation=(\d+) owner=\d+ block_generation=(\d+) block_sectors=(\d+)", text
        )
        need(ready == [("1", "1", "1048576")], "Clean-XFS block lease extent/incarnation")
        need(
            text.count("AURORA_FILE_SERVICE_READY:") == 1 and text.count("AURORA_FILE_SERVICE_OK:") == 1,
            "Clean-XFS retained owner lifecycle",
        )
        need(
            "AURORA_FILE_SERVICE_LOST:" not in text and "AURORA_NVME_QUARANTINED:" not in text,
            "Clean-XFS owner/backend loss",
        )
    if mode == "process-xfs-recover":
        writes, flushes = (0, 1) if recovery_state == "clean" else (3 if recovery_exchange else 4, 3)
        recovery_authority(text, writes, flushes)
    if mode in PROCESS_CASES:
        golden = f"{mode}-{xfs_history}" if mode == "process-xfs-clean" else mode
        compare(ROOT / f"tests/kernel-process/{golden}.golden", runs(text, mode))
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
        validate(
            int(sys.argv[1]),
            Path(sys.argv[2]).read_text(),
            sys.argv[3],
            Path(sys.argv[4]),
            xfs_history=sys.argv[5] if len(sys.argv) == 6 else None,
        )
    except (ValueError, OSError) as error:
        sys.exit(f"FAIL: {error}")

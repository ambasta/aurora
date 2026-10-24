#!/usr/bin/env python3
"""Exact M013 user-run, interrupt, disposal and peer-preservation receipts.

The fixture owns the state machine and physical layout. Receipts cannot choose
their own roots, generations, transactions, run roles or terminal sequence.
Timer arrival counts and PCs remain nondeterministic within their owned image.
"""

from pathlib import Path
import copy
import importlib.util
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT

spec = importlib.util.spec_from_file_location(
    "user_phase_budget", Path(__file__).with_name("kernel-uefi-budget-smoke.py")
)
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)
need = budget.need
BASE = budget.BASE
EVENT = budget.EVENT
NAMES = ("clean", "bounds", "peer")
SUCCESS = (
    "user-phases",
    "user-context",
    "user-retire-pending",
    "user-request-budget",
    "user-completion-budget",
    "user-request-bounds",
    "user-completion-bounds",
    "user-request-overflow",
    "user-completion-overflow",
    "user-pending",
)
DENIED_IRQ = ("user-role", "user-phase", "user-transaction", "user-epoch", "user-root")
DISPOSAL_DENIED = ("user-disposal-input", "user-disposal-output")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_profiles  # noqa: E402

# Modes that boot user-fixture, whose clean client carries the probe set.
FIXTURE_MODES = tuple(mode for mode, (image, _) in kernel_profiles.FIXTURE_MODES.items() if image == "user-fixture")
# Historical synthetic scenarios include copied-policy failures now covered hosted.
# Current boot modes are admitted separately by kernel_profiles and emulator_clock.
MODES = SUCCESS + DENIED_IRQ + ("user-unknown", "user-stale-grant") + DISPOSAL_DENIED


def metadata_valid(meta, mode):
    need(type(meta) is dict and set(meta) == {"images", "kernel"}, "User metadata shape")
    images = meta["images"]
    need(type(images) is dict and set(images) == set(NAMES), "Exactly three user images")
    keys = {
        "entry",
        "size",
        "return_pc",
        "bounds_pc",
        "overflow_pc",
        "division_zero_pc",
        "shift_count_pc",
        "probe_offset",
        "probe_pc",
        "compiled_begin",
        "compiled_end",
        "context_begin",
        "context_end",
    }
    for index, name in enumerate(NAMES):
        image = dict(images[name]) if type(images[name]) is dict else images[name]
        probes = image.pop("probes", None) if type(image) is dict else None
        need(
            type(image) is dict
            and set(image) == keys
            and all(type(v) is int and 0 <= v < 1 << 64 for v in image.values()),
            "Malformed user image scalars",
        )
        base = BASE + index * LAYOUT.code_stride
        need(
            image["entry"] == base and 4 <= image["size"] <= 4096 and image["probe_offset"] == 0,
            "User image layout widened",
        )
        sites = [image[k] for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")]
        need(
            all(base + 2 <= pc <= base + image["size"] - 2 for pc in sites)
            and all(a + 2 <= b for a, b in zip(sites, sites[1:])),
            "Missing, aliased or unordered retained sites",
        )
        need(
            image["return_pc"] < image["compiled_begin"] < image["compiled_end"] <= image["bounds_pc"],
            "Compiled interval outside owned function",
        )
        begin, end = image["context_begin"], image["context_end"]
        hostile = mode in FIXTURE_MODES and index == 0
        if hostile:
            need(base <= begin < end <= image["return_pc"] and end - begin == 6, "Exact clean-client context interval")
        else:
            need(begin == end == 0, "Unexpected context authority")
        need(image["probe_pc"] == 0, "Unexpected single hostile probe")
        if hostile:
            # Wrapper code only: inside the image, distinct, never a retained
            # site, the context loop or compiled code.
            need(type(probes) is dict and set(probes) == budget.PROBE_NAMES, "Exact clean-client probe set")
            pcs = [
                pc
                for pc in probes.values()
                if type(pc) is int
                and base <= pc <= base + image["size"] - 2
                and pc not in sites
                and pc not in (begin, end)
                and not image["compiled_begin"] <= pc < image["compiled_end"]
            ]
            need(len(set(pcs)) == len(budget.PROBE_NAMES), "Clean-client probe outside wrapper or aliased")
        else:
            need(probes is None, "Unexpected hostile probe")
    kernel = meta["kernel"]
    need(
        type(kernel) is dict
        and set(kernel) == {"drain_begin", "drain_end", "text_end", "forged_pc"}
        and all(type(v) is int and 0 <= v < 1 << 64 for v in kernel.values()),
        "Malformed kernel sites",
    )
    need(
        0 < kernel["drain_begin"] < kernel["drain_end"] < kernel["text_end"] <= LAYOUT.kernel_payload_limit
        and kernel["drain_end"] - kernel["drain_begin"] == 4
        and kernel["text_end"] % 4096 == 0
        and kernel["forged_pc"] == 0,
        "Drain outside exact owned RX interval",
    )


def expected(mode, arena):
    """Derive the complete logical plan without using a receipt's state values."""
    rows = []
    roots = [
        arena + n
        for n in (
            LAYOUT.tables_offset,
            (LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size),
            LAYOUT.third_tables_offset,
        )
    ]
    states = ["idle", "idle"]
    tickets = [0, 0]
    grants = [1, 2]
    counter = 2

    def record(op, client, transaction, first, second):
        queued = states.count("pending")
        return (
            f"AURORA_UEFI_DISPATCH_{op}: client={client} transaction={transaction}"
            f" first={first} second={second} queued={queued}"
        )

    def run(client, source, outcome="returned", failure=None, old_grant=False):
        domain = 1 if source == 1 else 0 if client == 0 else 2
        phase = "service" if source == 1 else "request" if source in (0, 6, 8, 9) else "completion"
        transaction = 0 if phase == "request" else tickets[client]
        grant = 1 if old_grant else grants[client]
        value = ((40, 70)[client] if phase == "request" else (42, 73)[client]) if outcome == "returned" else 0
        second = (2, 3)[client] if phase != "completion" else 0
        terminal = []
        if outcome == "returned" and failure != "unknown":
            terminal.append(
                f"AURORA_UEFI_DISPATCH_ENVELOPE: client={client} phase={source}"
                f" version=1 slot={int(domain == 1)} generation={grant}"
                f" transaction={transaction} value={value} second={second}"
            )
            if failure == "stale":
                terminal.append("AURORA_UEFI_RUNTIME_FAIL: dispatch request capability/queue")
            elif phase == "request":
                nonlocal counter
                counter += 1
                tickets[client] = counter
                states[client] = "pending"
                terminal.append(record("SUBMIT", client, counter, value, second))
            else:
                if phase == "service":
                    states[client] = "replied"
                terminal.append(record("REPLY" if phase == "service" else "COMPLETE", client, transaction, value, 0))
        rows.append(
            dict(
                client=client,
                domain=domain,
                source=source,
                phase=phase,
                transaction=transaction,
                grant=grant,
                outcome=outcome,
                value=value,
                terminal=terminal,
                failure=failure,
            )
        )

    def request(client, stale=False):
        run(client, 0, failure="stale" if stale else None, old_grant=stale)

    def service(client):
        states[client] = "delivered"
        rows.append(record("SELECT", client, tickets[client], (40, 70)[client], (2, 3)[client]))
        run(client, 1)

    def complete(client, source=2, outcome="returned"):
        states[client] = "consumed"
        rows.append(record("CONSUME", client, tickets[client], (42, 73)[client], 0))
        run(client, source, outcome)

    ordinary = mode in ("user-phases", "user-context", "user-pending", "user-unknown")
    if ordinary:
        for domain in range(3):
            rows.append(
                f"AURORA_UEFI_DISPATCH_DOMAIN: index={domain} root={roots[domain]}"
                f" entry={BASE + domain * LAYOUT.code_stride}"
                f" stack={LAYOUT.user_stack_top + domain * LAYOUT.user_stack_stride}"
                f" frame={arena + LAYOUT.stack_frames_offset + domain * LAYOUT.stack_pages * LAYOUT.page_size}"
            )
    for client in range(2):
        rows.append(record("BIND", client, 0, grants[client], client * 2))
    if mode == "user-unknown":
        run(0, 0, failure="unknown")
        return rows
    if ordinary:
        request(0)
        request(1)
        service(0)
        complete(0)
        states[0] = "idle"
        tickets[0] = 0
        rows.append(record("RECYCLE", 0, 0, 0, 0))
        request(0)
        service(1)
        complete(1)
        service(0)
        complete(0)
    else:
        request(1)
        if mode in DENIED_IRQ:
            run(0, 6, "budget", "irq")
            return rows
        replied = mode.startswith("user-completion-") or mode == "user-retire-pending"
        if replied:
            request(0)
            service(0)
        outcome = (
            "bounds"
            if mode.endswith("bounds") or mode == "user-retire-pending" or mode in DISPOSAL_DENIED
            else "overflow"
            if mode.endswith("overflow")
            else "budget"
        )
        source = {"budget": 7 if replied else 6, "bounds": 10 if replied else 8, "overflow": 11 if replied else 9}[
            outcome
        ]
        if replied:
            complete(0, source, outcome)
        else:
            run(0, source, outcome)
        if mode in DISPOSAL_DENIED:
            rows.append("AURORA_UEFI_RUNTIME_FAIL: user terminal disposition")
            return rows
        rows.append(
            f"AURORA_UEFI_USER_DISPOSE: client=0 disposition={'replied' if replied else 'idle'}"
            f" transaction={4 if replied else 0} value={42 if replied else 0}"
        )
        rows.append(
            f"AURORA_UEFI_USER_REVOKE: root={roots[0]} kernel={arena + LAYOUT.kernel_tables_offset}"
            f" tables={LAYOUT.table_pages} frames={LAYOUT.stack_pages} used=8"
        )
        counter += 1
        grants[0] = counter
        states[0] = "idle"
        tickets[0] = 0
        rows.append(
            f"AURORA_UEFI_USER_REBIND: client=0 old=1 fresh={counter} peer=2 transaction=3 "
            f"frame={arena + LAYOUT.stack_frames_offset}"
        )
        service(1)
        complete(1)
        request(0, mode == "user-stale-grant")
        if mode == "user-stale-grant":
            return rows
        service(0)
        complete(0)
    rows.extend(
        (
            "AURORA_UEFI_DISPATCH_CLEANUP_OK: used=0 records=0",
            "AURORA_UEFI_DISPATCH_OK",
            "AURORA_UEFI_USER_PHASES_OK",
            "AURORA_UEFI_LANGUAGE_OK: value=42",
            "AURORA_UEFI_OK",
        )
    )
    return rows


def event_line(arena, domain, vector, pc):
    root = (
        arena
        + (
            LAYOUT.tables_offset,
            (LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size),
            LAYOUT.third_tables_offset,
        )[domain]
    )
    return (
        f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3"
        f" root={root} frame={arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size} cr2=0"
    )


def launch_lines(run, epoch, arena):
    c, d, source = run["client"], run["domain"], run["source"]
    root = (
        arena
        + (
            LAYOUT.tables_offset,
            (LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size),
            LAYOUT.third_tables_offset,
        )[d]
    )
    transaction = run["transaction"]
    return [
        f"AURORA_UEFI_DISPATCH_ENTER: client={c} domain={d} phase={source}"
        f" root={root} grant={run['grant']} transaction={transaction}",
        f"AURORA_UEFI_USER_RUN: epoch={epoch} role={'service' if d == 1 else 'client'}"
        f" phase={run['phase']} client={c} transaction={transaction} source={source} root={root}",
        f"AURORA_UEFI_TIMER_ARM: epoch={epoch} budget={3 if source in (6, 7) else 128} root={root}",
    ]


def needs_pending(mode, run):
    return mode == "user-pending" or mode == "user-retire-pending" and run["source"] == 10


def checksum(seed):
    # Independent bitwise Castagnoli oracle, including initial/final complement.
    remainder = 0xFFFFFFFF
    for byte in bytes(range(seed, seed + 64)) * 512:
        remainder ^= byte
        for _ in range(8):
            remainder = (remainder >> 1) ^ (0x82F63B78 if remainder & 1 else 0)
    return remainder ^ 0xFFFFFFFF


def resume_code(text, image):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from kernel_elf import Elf

    elf = Elf(image)
    crc = elf.functions["__au_v_m2_3std8checksum_n1_3std_d13crc32c_extend"]
    for epoch in (1, 5):
        pcs = re.findall(
            r"AURORA_UEFI_TIMER_TICK: epoch=" + str(epoch) + r" used=1 remaining=127 pc=(\d+) flags=", text
        )
        need(
            len(pcs) == 1 and crc.address < int(pcs[0]) < crc.address + crc.size,
            "Suspension inside linked Aurora CRC function with live state",
        )
    print("PASS: both checksum suspensions inside linked Aurora CRC body")


def validate_resume(status, text, metadata):
    metadata_valid(metadata, "user-resume")
    need(status == 33 and "AURORA_UEFI_OK" in text and "FAIL" not in text, "Resume guest exit")
    need(text.count("AURORA_UEFI_USER_RESUME_OK") == 1, "Complete resume workload")
    cases = list(re.finditer(r"AURORA_USER_RESUME_CASE: case=(\d+) used=0", text))
    need([int(m[1]) for m in cases] == [0, 1, 2], "Normal, exhaustion and cancellation cases")
    previous = 0
    for scenario, end in enumerate(cases):
        part = text[previous : end.start()]
        previous = end.end()
        parked = re.findall(r"AURORA_USER_SUSPEND: domain=0 epoch=(\d+) remaining=(\d+)", part)
        need(len(parked) == 1, "Exactly one saved client continuation")
        epoch, remaining = map(int, parked[0])
        need(epoch == 2 * scenario + 1 and remaining == (2 if scenario == 1 else 127), "Saved original budget")
        peer = re.search(
            r"AURORA_UEFI_DISPATCH_RESTORE: client=1 domain=2 .* event=returned value=" + str(checksum(70)), part
        )
        need(peer and part.index("AURORA_USER_SUSPEND:") < peer.start(), "Peer checksum executes while A is parked")
        restored = re.findall(r"AURORA_USER_RESUME: domain=0 epoch=(\d+) remaining=(\d+) ticks=(\d+)", part)
        if scenario == 2:
            need(not restored, "Retired continuation never resumes")
        else:
            need(restored == [(str(epoch), str(remaining), "1")], "Resume preserves epoch and debited budget")
            need(peer.end() < part.index("AURORA_USER_RESUME:"), "Resume follows actual peer execution")
            outcome, value = ("budget", 0) if scenario == 1 else ("returned", checksum(40))
            need(
                re.search(
                    r"AURORA_UEFI_DISPATCH_RESTORE: client=0 domain=0 .* event=" + outcome + " value=" + str(value),
                    part,
                ),
                "Resumed checksum or exhaustion outcome",
            )
        ticks = re.findall(r"AURORA_UEFI_TIMER_TICK: epoch=" + str(epoch) + r" used=(\d+) remaining=(\d+) pc=", part)
        need(ticks and [int(t[0]) for t in ticks] == list(range(1, len(ticks) + 1)), "No timer debit reset")
        need(all(int(used) + int(left) == (3 if scenario == 1 else 128) for used, left in ticks), "No budget recharge")
        if scenario == 1:
            need(ticks[-1] == ("3", "0"), "Exhaustion after exactly original three ticks")


def validate_call(status, text, mode, metadata):
    denied = mode in ("user-call-owner", "user-call-site")
    need(
        mode in ("user-call", "user-call-pending", "user-call-owner", "user-call-site")
        and type(status) is int
        and status == (35 if denied else 33),
        "Call mode/exit",
    )
    cleaned = copy.deepcopy(metadata)
    client = cleaned["images"]["clean"]
    call_pc = client.pop("call_pc")
    need(
        type(call_pc) is int and client["return_pc"] + 4 <= call_pc < client["compiled_begin"], "Exact call site range"
    )
    budget.metadata_valid(cleaned, mode)
    if denied:
        need(
            text.count("AURORA_UEFI_RUNTIME_FAIL: call exact site and endpoint") == 1
            and "AURORA_CALL_PARK" not in text
            and "AURORA_UEFI_CALL_OK" not in text
            and "AURORA_UEFI_OK" not in text,
            "Call rejected before publication",
        )
        return
    need(
        text.count("AURORA_UEFI_CALL_OK") == 1
        and text.count("AURORA_UEFI_OK") == 1
        and "FAIL" not in text
        and "REJECT" not in text,
        "Call success and restoration",
    )
    cases = re.findall(r"AURORA_CALL_CASE: case=(\d+) used=(\d+)", text)
    need(cases == [(str(i), "0") for i in range(4)], "Complete ordered call scenarios")
    parks = re.findall(r"AURORA_CALL_PARK: ticket=(\d+) epoch=(\d+) ticks=(\d+) remaining=(\d+)", text)
    resumes = re.findall(r"AURORA_CALL_RESUME: epoch=(\d+) ticks=(\d+) remaining=(\d+)", text)
    need(len(parks) == 4 and len(resumes) == 3, "Exact park and wake counts")
    need([int(row[1]) for row in parks] == [1, 3, 5, 7], "Monotonic fresh run epochs")
    need([int(row[0]) for row in parks] == [2, 4, 6, 8], "Fresh private transaction stamps")
    for i, (_, epoch, used, left) in enumerate(parks):
        need(0 < int(used) < 128 and int(used) + int(left) == 128, "Original budget before park")
        if i < 3:
            need(resumes[i] == (epoch, used, left), "Resume exact original budget and epoch")
        ticks = re.findall(rf"AURORA_UEFI_TIMER_TICK: epoch={epoch} used=(\d+) remaining=(\d+) pc=(\d+)", text)
        need(
            len(ticks) >= int(used) and [int(t[0]) for t in ticks] == list(range(1, len(ticks) + 1)),
            "Continuous caller tick sequence",
        )
        need(
            all(
                int(t[0]) + int(t[1]) == 128 and client["entry"] <= int(t[2]) < client["entry"] + client["size"]
                for t in ticks
            ),
            "Caller ticks stay in original image/quota",
        )
        if i == 2:
            need(ticks[-1][:2] == ("128", "0"), "Post-call original budget exhaustion")
        elif i == 3:
            need(len(ticks) == int(used), "Retired caller never resumes")
    calls = [row for row in re.findall(EVENT, text) if int(row[0]) == 130]
    need(
        len(calls) == 7 and all(int(row[1]) == 0 and int(row[2]) == call_pc and int(row[3]) == 3 for row in calls),
        "Only exact CPL3 call site traps",
    )
    launches = re.findall(
        r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) phase=(request|service) "
        r"client=(\d+) transaction=(\d+) source=(\d+) root=(\d+)",
        text,
    )
    need(
        [row[:6] for row in launches]
        == [
            ("1", "client", "request", "0", "0", "0"),
            ("2", "service", "service", "0", "2", "1"),
            ("3", "client", "request", "0", "0", "1"),
            ("4", "service", "service", "0", "4", "4"),
            ("5", "client", "request", "0", "0", "8"),
            ("6", "service", "service", "0", "6", "1"),
            ("7", "client", "request", "0", "0", "0"),
        ],
        "Exact caller/peer run authority",
    )
    services = list(re.finditer(r"AURORA_CALL_SERVICE: epoch=(\d+) event=(returned|bounds) value=(\d+)", text))
    completed = re.findall(r"AURORA_CALL_COMPLETE: epoch=(\d+) event=(returned|budget) value=(\d+)", text)
    need(
        [match.groups() for match in services]
        == [("2", "returned", "309914170369"), ("4", "bounds", "0"), ("6", "returned", "309914170369")],
        "Actual peer completion and fault",
    )
    need(
        completed == [("1", "returned", "1210602268"), ("3", "returned", "40"), ("5", "budget", "0")],
        "Live caller results and exhaustion",
    )
    park_positions = list(re.finditer(r"AURORA_CALL_PARK:", text))
    resume_positions = list(re.finditer(r"AURORA_CALL_RESUME:", text))
    case_positions = list(re.finditer(r"AURORA_CALL_CASE:", text))
    complete_positions = list(re.finditer(r"AURORA_CALL_COMPLETE:", text))
    for index, (_, epoch, used, _) in enumerate(parks):
        ticks = list(re.finditer(rf"AURORA_UEFI_TIMER_TICK: epoch={epoch} used=\d+ remaining=\d+ pc=\d+", text))
        lower = 0 if index == 0 else case_positions[index - 1].end()
        need(
            all(lower < tick.start() < park_positions[index].start() for tick in ticks[: int(used)]),
            "Caller ticks precede its park",
        )
        if index < 3:
            need(
                all(
                    resume_positions[index].end() < tick.start() < case_positions[index].start()
                    for tick in ticks[int(used) :]
                ),
                "Caller cannot tick while parked or after retirement",
            )
            need(
                resume_positions[index].end() < complete_positions[index].start() < case_positions[index].start(),
                "Caller completes only after resume",
            )
    service_image = cleaned["images"]["bounds"]
    for index, completion in enumerate(services):
        peer_epoch = 2 * index + 2
        begin, end = park_positions[index].end(), resume_positions[index].start()
        need(begin < completion.start() < end, "Peer completes between park and wake")
        segment = text[begin:end]
        need(f"AURORA_UEFI_USER_RUN: epoch={peer_epoch} role=service" in segment, "Peer launch after park")
        peer_ticks = re.findall(
            rf"AURORA_UEFI_TIMER_TICK: epoch={peer_epoch} used=(\d+) remaining=(\d+) pc=(\d+)", segment
        )
        need(
            # A bounded 64-byte checksum may finish before its first timer tick.
            [int(t[0]) for t in peer_ticks] == list(range(1, len(peer_ticks) + 1))
            and all(
                int(t[0]) + int(t[1]) == 128
                and service_image["entry"] <= int(t[2]) < service_image["entry"] + service_image["size"]
                for t in peer_ticks
            ),
            "Actual bounded peer execution",
        )
        event = (6, service_image["bounds_pc"]) if index == 1 else (129, service_image["return_pc"])
        need(
            any(
                int(row[0]) == event[0] and int(row[1]) == 0 and int(row[2]) == event[1] and int(row[3]) == 3
                for row in re.findall(EVENT, segment)
            ),
            "Exact peer terminal event",
        )
    if mode == "user-call-pending":
        pending = list(re.finditer(r"AURORA_UEFI_TIMER_PENDING: epoch=(\d+)", text))
        drains = list(re.finditer(r"AURORA_UEFI_TIMER_DRAIN: epoch=(\d+) root=(\d+) ss=16", text))
        expected = [1, 2, 1, 3, 4, 3, 5, 6, 7]
        need(
            [int(m[1]) for m in pending] == expected and [int(m[1]) for m in drains] == expected,
            "Pending/drain exact owner epochs",
        )
        for index, (park, drain) in enumerate(zip(pending, drains)):
            quiet = re.search(rf"AURORA_UEFI_TIMER_QUIET: epoch={park[1]} ticks=\d+ drains=1 ", text[drain.end() :])
            need(
                park.end() < drain.start()
                and quiet is not None
                and (index == len(pending) - 1 or drain.end() + quiet.end() < pending[index + 1].start()),
                "Each forced pending interrupt drains before the next boundary",
            )


RAM_MODES = (
    "user-ram-file",
    "user-ram-file-service-fault",
    "user-ram-file-grant",
    "user-ram-file-site",
    "user-ram-file-settlement",
    "user-ram-file-commit-fault",
    "user-ram-file-caller-budget",
    "user-ram-file-service-budget",
    "user-ram-file-abort-budget",
    "user-ram-file-epochs",
    "user-ram-file-pending",
    "user-ram-file-frame",
    "user-ram-file-root",
)
RAM_SCENARIOS = [0, 1, 2, 3, 4, 7, 4, 15, 4, 16, 2, 5, 6, 8, 9, 13, 14, 10, 14, 11, 14, 12, 14, 5, 6]


def ram_scenarios(mode):
    return {
        "user-ram-file": RAM_SCENARIOS,
        "user-ram-file-service-fault": [1, 2, 0, 3, 4, 0],
        "user-ram-file-commit-fault": [5, 1, 0],
        "user-ram-file-settlement": [13, 14],
        "user-ram-file-caller-budget": [13, 1, 14],
        "user-ram-file-service-budget": [1, 0],
        "user-ram-file-abort-budget": [7, 0],
        "user-ram-file-epochs": [13, 1],
        "user-ram-file-pending": [0],
    }.get(mode, [])


def ram_run_parser(take, peek, arena, metadata, call_pc, serve_pc, mode):
    """Shared run/IRQ/debit/drain grammar; consumers own cursors and expected plans."""
    kernel = arena + LAYOUT.kernel_tables_offset
    roots = [arena + LAYOUT.tables_offset, arena + LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size]
    compiled_total = 0

    def run(domain, epoch, source, transaction, remaining):
        role, phase = ("client", "request") if domain == 0 else ("service", "service")
        take(
            f"AURORA_UEFI_USER_RUN: epoch={epoch} role={role} phase={phase} client=0 "
            f"transaction={transaction} source={source} root={roots[domain]}"
        )
        take(f"AURORA_UEFI_TIMER_ARM: epoch={epoch} budget={remaining} root={roots[domain]}")

    def segment(
        domain, epoch, limit, used=0, compiled=0, terminal=130, probe=False, pending=False, refused=False, denied=False
    ):
        nonlocal compiled_total
        image = metadata["images"][NAMES[domain]]

        def interrupts():
            nonlocal used, compiled, compiled_total
            while True:
                event = re.fullmatch(EVENT, peek())
                if event is None or int(event[1]) != 64 or int(event[4]) != 3:
                    break
                pc = int(event[3])
                need(
                    used + 1 < limit and image["entry"] <= pc < image["entry"] + image["size"],
                    "RAM finite hardware interrupt owned image/allowance",
                )
                take(event_line(arena, domain, 64, pc))
                tick = re.fullmatch(
                    r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=(\d+) remaining=(\d+) pc=(\d+) flags=(\d+)", peek()
                )
                need(tick is not None, "RAM hardware IRQ has immediate charge")
                e, n, left, address, flags = map(int, tick.groups())
                need(
                    (e, n, left, address) == (epoch, used + 1, limit - used - 1, pc)
                    and flags & 0x202 == 0x202
                    and flags & ~LAYOUT.allowed_user_flags == 0,
                    "RAM exact IRQ identity, flags and debit",
                )
                take(tick[0])
                used += 1
                hit = image["compiled_begin"] <= pc < image["compiled_end"]
                compiled += hit
                compiled_total += hit

        interrupts()
        pc = (
            (call_pc if domain == 0 else serve_pc)
            if terminal == 130
            else image["bounds_pc" if terminal == 6 else "return_pc"]
        )
        take(event_line(arena, domain, terminal, pc))
        if denied:
            reason = (
                "RAM Serve grant and dormant capacity"
                if mode.endswith("-grant")
                else "RAM active exchange authority"
                if mode.endswith("-root")
                else "RAM exact role selected exchange site"
            )
            take("AURORA_UEFI_RUNTIME_FAIL: " + reason)
            return used, compiled
        if terminal == 130:
            if probe:
                take(f"AURORA_RAM_FILE_BUDGET_PROBE: role={domain} initial={limit}")
                used = limit - 1  # Explicit conservative withholding, never an IRQ claim.
            used += 1
            need(used <= limit, "RAM boundary within original allowance")
            take(f"AURORA_RAM_FILE_DEBIT: epoch={epoch} used={used} remaining={limit - used}")
        if refused:
            interrupts()
            take(event_line(arena, domain, 129, image["return_pc"]))
        if pending:
            take(f"AURORA_UEFI_TIMER_PENDING: epoch={epoch}")
        drains = 0
        while re.fullmatch(EVENT, peek()):
            event = re.fullmatch(EVENT, peek())
            vector, error, pc, cpl, root, frame, cr2 = map(int, event.groups())
            need(
                (vector, error, cpl, root, cr2) == (64, 0, 0, kernel, 0)
                and arena + LAYOUT.kernel_stack_bottom
                <= frame
                <= arena + LAYOUT.kernel_stack_top - LAYOUT.fault_frame_size
                and frame % 8 == 0
                and arena + LAYOUT.kernel_payload_offset + metadata["kernel"]["drain_begin"]
                <= pc
                <= arena + LAYOUT.kernel_payload_offset + metadata["kernel"]["drain_end"],
                "RAM exact kernel drain authority",
            )
            take(event[0])
            take(f"AURORA_UEFI_TIMER_DRAIN: epoch={epoch} root={kernel} ss=16")
            drains += 1
        need(not pending or drains > 0, "RAM forced pending must drain")
        take(
            f"AURORA_UEFI_TIMER_QUIET: epoch={epoch} ticks={used} drains={drains}"
            f" compiled={compiled} context=0 root={kernel}"
        )
        return used, compiled

    return run, segment, lambda: compiled_total


def ram_trace(text, mode, metadata, call_pc, serve_pc):
    """Parse every authority/IRQ/settlement record against the fixture-owned plan."""
    lines = text.splitlines()
    start = next(
        (
            i
            for i, row in enumerate(lines)
            if row.startswith(
                (
                    "AURORA_UEFI_TIMER_",
                    "AURORA_RAM_FILE",
                    "AURORA_UEFI_USER_",
                    "AURORA_UEFI_DOMAIN_",
                    "AURORA_UEFI_RUNTIME_",
                )
            )
        ),
        None,
    )
    need(start is not None, "RAM missing admitted timer")
    prefix = "\n".join(lines[:start]) + "\n"
    budget.firmware_prefix(prefix, "budget")
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    kernel = arena + LAYOUT.kernel_tables_offset
    roots = [arena + LAYOUT.tables_offset, arena + LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size]
    records = [row for row in lines[start:] if "AURORA" in row]
    position = 0

    def peek():
        return records[position] if position < len(records) else ""

    def take(wanted):
        nonlocal position
        need(peek() == wanted, "RAM sequence expected " + wanted + "; got " + peek())
        position += 1

    run, segment, compiled_count = ram_run_parser(take, peek, arena, metadata, call_pc, serve_pc, mode)

    take(f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={budget.APIC} id=0 root={kernel}")
    if mode != "user-ram-file":
        take("AURORA_FIXTURE_READY")
    epoch = 1
    run(1, epoch, 1, 0, 8)
    denied = mode.endswith(("-grant", "-site", "-frame", "-root"))
    segment(1, epoch, 8, pending=mode.endswith("-pending"), denied=denied)
    if denied:
        need(position == len(records), "RAM authority denial cannot reset or continue")
        return
    generation, caller, ticket = 1, 2, 0
    counts = {
        0: 2,
        1: 7,
        2: 7,
        3: 5,
        4: 5,
        5: 2,
        6: 2,
        7: 2,
        8: 51,
        9: 51,
        10: 0,
        11: 0,
        12: 0,
        13: 3,
        14: 3,
        15: 2,
        16: 7,
    }
    for index, phase in enumerate(ram_scenarios(mode)):
        exhausted_caller = index == 1 and mode.endswith(("-caller-budget", "-epochs"))
        resetting = (
            (index in (1, 4) and mode.endswith("-service-fault")) or (index == 1 and mode.endswith("-commit-fault"))
        ) or (index == 0 and mode.endswith(("-service-budget", "-abort-budget")))
        fault = resetting and mode.endswith(("-service-fault", "-commit-fault"))
        if exhausted_caller and mode.endswith("-epochs"):
            epoch = (1 << 64) - 3
        cleanup, client_epoch = epoch + 1, epoch + 2
        epoch = client_epoch
        caller += 1
        ticket += 1  # Binding mints a fresh endpoint generation, not a transaction.
        take(f"AURORA_RAM_FILE_BEGIN: phase={phase} service={generation} caller={caller} root={roots[1]}")
        if exhausted_caller and mode.endswith("-epochs"):
            take("AURORA_RAM_FILE_EPOCH_PROBE: cleanup=18446744073709551614 ceiling=18446744073709551615")
        run(0, client_epoch, phase, 0, 128)
        count = counts[phase]
        if exhausted_caller or (resetting and not mode.endswith("-commit-fault")):
            count = 1 if mode.endswith("-epochs") else 2
        caller_used = caller_compiled = service_used = 0
        for exchange in range(count):
            caller_used, caller_compiled = segment(0, client_epoch, 128, caller_used, caller_compiled)
            ticket += 1
            if exhausted_caller and mode.endswith("-epochs"):
                break  # Real publication occurred, but no new service epoch exists.
            epoch += 1
            run(1, epoch, 2, ticket, 120 - service_used)
            last = exchange == count - 1
            service_used, _ = segment(
                1,
                epoch,
                120,
                service_used,
                terminal=6 if fault and last else 130,
                probe=resetting and mode.endswith("-service-budget") and last,
            )
        disposed = mode.endswith("-settlement") and index == 0
        aborted = phase in (7, 10, 11, 12, 15) or exhausted_caller
        if not (fault or (resetting and mode.endswith("-service-budget")) or disposed):
            if exhausted_caller and mode.endswith("-caller-budget"):
                segment(0, client_epoch, 128, caller_used, caller_compiled, probe=True)
            elif not (exhausted_caller and mode.endswith("-epochs")):
                segment(
                    0,
                    client_epoch,
                    128,
                    caller_used,
                    caller_compiled,
                    terminal=130 if phase in (10, 11, 12) else 6 if phase in (15, 16) else 129,
                    refused=phase in (10, 11, 12),
                )
        if aborted:
            run(1, cleanup, 3, 0, 8)
            segment(1, cleanup, 8, probe=resetting and mode.endswith("-abort-budget"))
        if resetting:
            outcome = "indeterminate" if mode.endswith("-commit-fault") else "reset"
            take(f"AURORA_RAM_FILE_RESET: outcome={outcome} data_lost=1")
            epoch += 1
            generation += 1
            caller += 2  # Fresh reservation and service owner, before a new caller.
            run(1, epoch, 1, 0, 8)
            segment(1, epoch, 8)
            if mode.endswith("-service-fault"):
                take(f"AURORA_RAM_FILE_REUSE: generation={generation} pages=4 old_owner_denied=1")
            continue
        value = 0 if disposed or exhausted_caller or phase in (15, 16) else 42
        outcome = "aborted" if aborted else "completed"
        take(f"AURORA_RAM_FILE_COMMAND: phase={phase} exchanges={count} result={value} outcome={outcome} retained=1")
        if disposed:
            take("AURORA_RAM_FILE_SETTLED: caller_disabled=1 committed=1 consumed_once=1 retained=1")
    take("AURORA_UEFI_RAM_FILE_OK: used=0 volatile=1")
    take("AURORA_UEFI_LANGUAGE_OK: value=42")
    take("AURORA_UEFI_OK")
    need(position == len(records), "RAM duplicate or trailing authority evidence")
    if mode != "user-ram-file":
        need(compiled_count() > 0, "RAM fixture requires an actual compiled-PC hardware IRQ")


def validate_ram_file(status, text, mode, metadata):
    need(mode in RAM_MODES and type(text) is str, "RAM file exact mode")
    text = text.replace("\r", "")
    denied = mode.endswith(("-grant", "-site", "-frame", "-root"))
    need(type(status) is int and status == (35 if denied else 33), "RAM file process exit")
    cleaned = copy.deepcopy(metadata)
    call_pc = cleaned["images"]["clean"].pop("call_pc")
    serve_pc = cleaned["images"]["bounds"].pop("serve_pc")
    for name, pc in (("clean", call_pc), ("bounds", serve_pc)):
        row = cleaned["images"][name]
        need(type(pc) is int and row["return_pc"] + 4 <= pc < row["compiled_begin"], "RAM exact role trap range")
        need(
            pc
            not in [
                row[key] for key in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")
            ],
            "RAM trap nonalias",
        )
    budget.metadata_valid(cleaned, "user-call")
    ram_trace(text, mode, metadata, call_pc, serve_pc)


def validate(status, text, mode, metadata):
    if mode in MODES:
        marker = "AURORA_FIXTURE_READY\n"
        need(text.count(marker) == (1 if mode in FIXTURE_MODES else 0), "Exact user fixture readiness")
        if mode in FIXTURE_MODES:
            need(
                text.index("AURORA_PCI_WINDOW_CLOSED:") < text.index(marker) < text.index("AURORA_UEFI_TIMER_READY:"),
                "User selector admission phase",
            )
            text = text.replace(marker, "", 1)
    if mode.startswith("user-ram-file"):
        return validate_ram_file(status, text, mode, metadata)
    if mode in ("user-call", "user-call-pending", "user-call-owner", "user-call-site"):
        return validate_call(status, text, mode, metadata)
    if mode == "user-resume":
        return validate_resume(status, text, metadata)
    need(mode in MODES, "Unknown user-phase mode")
    metadata_valid(metadata, mode)
    need(type(status) is int and status == (33 if mode in SUCCESS else 35), "Wrong user-phase exit")
    need(type(text) is str, "Malformed serial log")
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith(
                (
                    "AURORA_UEFI_TIMER_",
                    "AURORA_UEFI_DISPATCH_",
                    "AURORA_UEFI_USER_",
                    "AURORA_UEFI_RUNTIME_",
                    "AURORA_UEFI_DOMAIN_",
                )
            )
        ),
        None,
    )
    need(start is not None, "Missing user-phase boundary")
    prefix = "\n".join(lines[:start]) + "\n"
    budget.firmware_prefix(prefix, "budget")
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    kernel = arena + LAYOUT.kernel_tables_offset
    # Firmware/QEMU noise is not evidence, but malformed Aurora-looking lines
    # must reach the exact parser rather than disappear during projection.
    records = [line for line in lines[start:] if "AURORA" in line]
    position = 0

    def peek():
        return records[position] if position < len(records) else ""

    def take(wanted):
        nonlocal position
        need(peek() == wanted, "Wrong user sequence: expected " + wanted + "; got " + peek())
        position += 1

    take(f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={budget.APIC} id=0 root={kernel}")
    epoch = 0
    for run in expected(mode, arena):
        if type(run) is str:
            take(run)
            continue
        epoch += 1
        for line in launch_lines(run, epoch, arena):
            take(line)
        c, d, source = run["client"], run["domain"], run["source"]
        image = metadata["images"][NAMES[d]]
        limit = 3 if source in (6, 7) else 128
        used = compiled = contexts = drains = 0
        while True:
            event = re.fullmatch(EVENT, peek())
            if not event or int(event[1]) != 64 or int(event[4]) != 3:
                break
            pc = int(event[3])
            need(
                used < limit and image["entry"] <= pc < image["entry"] + image["size"],
                "User timer outside live owned image/budget",
            )
            take(event_line(arena, d, 64, pc))
            if run["failure"] == "irq":
                need(c == d == 0 and source == 6 and used == 0, "Wrong rejected IRQ origin")
                if mode == "user-root":
                    take(f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}")
                take("AURORA_UEFI_RUNTIME_FAIL: user timer active authority")
                need(position == len(records), "Execution after denied timer authority")
                return
            tick = re.fullmatch(
                r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=(\d+) remaining=(\d+) pc=(\d+) flags=(\d+)", peek()
            )
            need(tick is not None, "Hardware event lacks its immediate tick")
            e, n, left, tick_pc, flags = map(int, tick.groups())
            need(
                (e, n, left, tick_pc) == (epoch, used + 1, limit - used - 1, pc)
                and flags & 0x202 == 0x202
                and flags & ~LAYOUT.allowed_user_flags == 0,
                "Wrong timer accounting or interrupt-enabled context",
            )
            take(tick[0])
            used += 1
            compiled += image["compiled_begin"] <= pc < image["compiled_end"]
            if image["context_begin"] and image["context_begin"] <= pc <= image["context_end"]:
                need(
                    mode == "user-context" and c == d == source == 0 and flags & 0x400,
                    "Context sample lacks exact clean request/DF authority",
                )
                contexts += 1
                take(f"AURORA_UEFI_TIMER_CONTEXT: epoch={epoch} tick={used} registers=15 df=1")
        need(run["failure"] != "irq", "Missing first offending-client IRQ denial")
        if run["outcome"] == "budget":
            need(used == 3 and compiled > 0, "Client budget lacks three charged hardware interrupts")
        else:
            need(used < limit, "Finite run reached exhausted budget")
            site = run["outcome"] + "_pc"
            if site == "returned_pc":
                site = "return_pc"
            vector = 129 if run["outcome"] == "returned" and run["failure"] != "unknown" else 6
            pc = image["probes"]["unknown"] if run["failure"] == "unknown" else image[site]
            take(event_line(arena, d, vector, pc))
            if needs_pending(mode, run):
                take(f"AURORA_UEFI_TIMER_PENDING: epoch={epoch}")
            if run["failure"] == "unknown":
                take("AURORA_UEFI_RUNTIME_FAIL: exception site authority")
                need(position == len(records), "Unknown UD2 was contained or continued")
                return
            for line in run["terminal"]:
                take(line)
            if run["failure"] == "stale":
                need(position == len(records), "Stale client grant accepted or continued")
                return
        # Drain is possible only after the terminal state transition, with the
        # old owner still ready and before quiet/restore/dispose/rebind/select.
        while re.fullmatch(EVENT, peek()):
            event = re.fullmatch(EVENT, peek())
            v, error, pc, cpl, root, frame, cr2 = map(int, event.groups())
            need(
                (v, error, cpl, root, cr2) == (64, 0, 0, kernel, 0)
                and arena + LAYOUT.kernel_stack_bottom
                <= frame
                <= arena + LAYOUT.kernel_stack_top - LAYOUT.fault_frame_size
                and frame % 8 == 0
                and arena + LAYOUT.kernel_payload_offset + metadata["kernel"]["drain_begin"]
                <= pc
                <= arena + LAYOUT.kernel_payload_offset + metadata["kernel"]["drain_end"],
                "Unauthorized kernel drain frame",
            )
            take(event[0])
            take(f"AURORA_UEFI_TIMER_DRAIN: epoch={epoch} root={kernel} ss=16")
            drains += 1
        if needs_pending(mode, run):
            need(drains > 0, "Forced pending IRQ did not drain before retirement/return")
        if source == 1:
            need(compiled > 0, "Finite service lacks compiled-code interrupt")
        if mode == "user-context" and c == d == source == 0:
            need(contexts > 0, "Clean client lacks exact GPR/DF interrupt evidence")
        take(
            f"AURORA_UEFI_TIMER_QUIET: epoch={epoch} ticks={used} drains={drains}"
            f" compiled={compiled} context={contexts} root={kernel}"
        )
        restore = re.fullmatch(
            r"AURORA_UEFI_DISPATCH_RESTORE: client=(\d+) domain=(\d+) root=(\d+) stack=(\d+)"
            r" event=(returned|bounds|overflow|budget) value=(\d+)",
            peek(),
        )
        need(restore is not None, "Missing post-quiescence kernel restoration")
        sp = int(restore[4])
        need(
            arena + LAYOUT.kernel_stack_bottom <= sp < arena + LAYOUT.kernel_stack_top and sp % 8 == 0,
            "Restored stack outside owned kernel stack",
        )
        take(
            f"AURORA_UEFI_DISPATCH_RESTORE: client={c} domain={d} root={kernel}"
            f" stack={sp} event={run['outcome']} value={run['value']}"
        )
    need(
        (mode in SUCCESS or mode in DISPOSAL_DENIED) and position == len(records),
        "Incomplete/unknown/trailing user receipt",
    )


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--resume-code":
        resume_code(Path(sys.argv[2]).read_text(), Path(sys.argv[3]))
    else:
        try:
            validate(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        except (ValueError, IndexError, KeyError, TypeError) as error:
            raise SystemExit("FAIL: " + str(error))
        print("PASS: exact user-run authority, hardware budgets and client recovery transcript")

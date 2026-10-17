#!/usr/bin/env python3
"""Exact M013 user-run, interrupt, disposal and peer-preservation receipts.

The fixture owns the state machine and physical layout. Receipts cannot choose
their own roots, generations, transactions, run roles or terminal sequence.
Timer arrival counts and PCs remain nondeterministic within their owned image.
"""

from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import re
import sys

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
        image = images[name]
        need(
            type(image) is dict
            and set(image) == keys
            and all(type(v) is int and 0 <= v < 1 << 64 for v in image.values()),
            "Malformed user image scalars",
        )
        base = BASE + index * 4096
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
        if mode == "user-context" and index == 0:
            need(base <= begin < end <= image["return_pc"] and end - begin == 6, "Exact clean-client context interval")
        else:
            need(begin == end == 0, "Unexpected context authority")
        probe = image["probe_pc"]
        if mode == "user-unknown" and index == 0:
            need(base <= probe <= image["return_pc"] - 2 and probe not in sites, "Exact non-retained clean probe")
        else:
            need(probe == 0, "Unexpected hostile probe")
    kernel = meta["kernel"]
    need(
        type(kernel) is dict
        and set(kernel) == {"drain_begin", "drain_end", "text_end", "forged_pc"}
        and all(type(v) is int and 0 <= v < 1 << 64 for v in kernel.values()),
        "Malformed kernel sites",
    )
    need(
        0 < kernel["drain_begin"] < kernel["drain_end"] < kernel["text_end"] <= 0x20000
        and kernel["drain_end"] - kernel["drain_begin"] == 4
        and kernel["text_end"] % 4096 == 0
        and kernel["forged_pc"] == 0,
        "Drain outside exact owned RX interval",
    )


def expected(mode, arena):
    """Derive the complete logical plan without using a receipt's state values."""
    rows = []
    roots = [arena + n for n in (0x90000, 0xA0000, 0xD0000)]
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
                f" entry={BASE + domain * 4096} stack={BASE + 0x204000 + domain * 0x200000}"
                f" frame={arena + 0xC0000 + domain * 0x4000}"
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
        rows.append(f"AURORA_UEFI_USER_REVOKE: root={roots[0]} kernel={arena + 0x11000} tables=16 frames=4 used=8")
        counter += 1
        grants[0] = counter
        states[0] = "idle"
        tickets[0] = 0
        rows.append(
            f"AURORA_UEFI_USER_REBIND: client=0 old=1 fresh={counter} peer=2 transaction=3 frame={arena + 0xC0000}"
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
    root = arena + (0x90000, 0xA0000, 0xD0000)[domain]
    return (
        f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3"
        f" root={root} frame={arena + 0x88000 - 176} cr2=0"
    )


def launch_lines(run, epoch, arena):
    c, d, source = run["client"], run["domain"], run["source"]
    root = arena + (0x90000, 0xA0000, 0xD0000)[d]
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
    from kernel_stack import Elf

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
    budget.metadata_valid(cleaned, "budget")
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
        == [("2", "returned", "42"), ("4", "bounds", "0"), ("6", "returned", "42")],
        "Actual peer completion and fault",
    )
    need(
        completed == [("1", "returned", "82"), ("3", "returned", "40"), ("5", "budget", "0")],
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
            (index == 1 or peer_ticks)
            and [int(t[0]) for t in peer_ticks] == list(range(1, len(peer_ticks) + 1))
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


def validate(status, text, mode, metadata):
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
    kernel = arena + 0x11000
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
                and flags & ~0x10ED7 == 0,
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
            site = "probe_pc" if run["failure"] == "unknown" else run["outcome"] + "_pc"
            if site == "returned_pc":
                site = "return_pc"
            vector = 129 if run["outcome"] == "returned" and run["failure"] != "unknown" else 6
            take(event_line(arena, d, vector, image[site]))
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
                and arena + 0x44000 <= frame <= arena + 0x48000 - 176
                and frame % 8 == 0
                and arena + 0x22000 + metadata["kernel"]["drain_begin"]
                <= pc
                <= arena + 0x22000 + metadata["kernel"]["drain_end"],
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
        need(arena + 0x44000 <= sp < arena + 0x48000 and sp % 8 == 0, "Restored stack outside owned kernel stack")
        take(
            f"AURORA_UEFI_DISPATCH_RESTORE: client={c} domain={d} root={kernel}"
            f" stack={sp} event={run['outcome']} value={run['value']}"
        )
    need(
        (mode in SUCCESS or mode in DISPOSAL_DENIED) and position == len(records),
        "Incomplete/unknown/trailing user receipt",
    )


def fixtures(client_ticks=True):
    """Deterministic inputs, independent of QEMU timing or local build output."""
    arena = 0x1000000
    kernel = arena + 0x11000
    prefix = (
        f"AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\n"
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes=1048576 descriptors=111\n"
        f"AURORA_UEFI_PROTECTION_OK: root={kernel} stack={arena + 0x47E00}\n"
        "AURORA_ACPI_CPU: id=0 uid=0 enabled=1 capable=0 x2=0\n"
        "AURORA_ACPI_TOPOLOGY: records=1 enabled=1 capable=0 lapic=4276092928\n"
        "AURORA_ACPI_WINDOW_CLOSED: copies=14\n"
        "AURORA_PCI_APERTURE: base=3758096384 bytes=268435456 segment=0 first=0 last=255\n"
        "AURORA_PCI_FUNCTION: segment=0 bus=0 device=0 function=0 vendor=32902 product=10688"
        " class=6 subclass=0 interface=0 header=0 command=7 secondary=0 subordinate=0\n"
        "AURORA_PCI_INVENTORY: functions=1 buses=1\nAURORA_PCI_WINDOW_CLOSED: reads=39\n"
    )
    for mode in MODES:
        images = {}
        for d, name in enumerate(NAMES):
            base = BASE + d * 4096
            images[name] = dict(
                entry=base,
                size=512,
                return_pc=base + 60,
                bounds_pc=base + 400,
                overflow_pc=base + 402,
                division_zero_pc=base + 404,
                shift_count_pc=base + 406,
                probe_offset=0,
                probe_pc=base + 50 if d == 0 and mode == "user-unknown" else 0,
                compiled_begin=base + 80,
                compiled_end=base + 300,
                context_begin=base + 20 if d == 0 and mode == "user-context" else 0,
                context_end=base + 26 if d == 0 and mode == "user-context" else 0,
            )
        metadata = dict(images=images, kernel=dict(drain_begin=100, drain_end=104, text_end=4096, forged_pc=0))
        rows = [f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={budget.APIC} id=0 root={kernel}"]
        epoch = 0
        for run in expected(mode, arena):
            if type(run) is str:
                rows.append(run)
                continue
            epoch += 1
            rows.extend(launch_lines(run, epoch, arena))
            d, source = run["domain"], run["source"]
            image = images[NAMES[d]]
            limit = 3 if source in (6, 7) else 128
            used = 3 if run["outcome"] == "budget" else 1 if d == 1 or client_ticks else 0
            context = mode == "user-context" and d == source == 0
            if context:
                used = 1
            if run["failure"] == "irq":
                rows.append(event_line(arena, d, 64, image["compiled_begin"] + 8))
                if mode == "user-root":
                    rows.append(f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}")
                rows.append("AURORA_UEFI_RUNTIME_FAIL: user timer active authority")
                break
            compiled = 0
            for tick in range(1, used + 1):
                pc = (
                    image["context_begin"]
                    if context
                    else image["compiled_begin"] + 8
                    if d == 1 or limit == 3
                    else image["entry"]
                )
                compiled += image["compiled_begin"] <= pc < image["compiled_end"]
                rows.extend(
                    (
                        event_line(arena, d, 64, pc),
                        f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used={tick} remaining={limit - tick}"
                        f" pc={pc} flags={1538 if context else 514}",
                    )
                )
                if context:
                    rows.append(f"AURORA_UEFI_TIMER_CONTEXT: epoch={epoch} tick={tick} registers=15 df=1")
            if run["outcome"] != "budget":
                site = (
                    "probe_pc"
                    if run["failure"] == "unknown"
                    else "return_pc"
                    if run["outcome"] == "returned"
                    else run["outcome"] + "_pc"
                )
                rows.append(event_line(arena, d, 129 if site == "return_pc" else 6, image[site]))
                if needs_pending(mode, run):
                    rows.append(f"AURORA_UEFI_TIMER_PENDING: epoch={epoch}")
                if run["failure"] == "unknown":
                    rows.append("AURORA_UEFI_RUNTIME_FAIL: exception site authority")
                    break
                rows.extend(run["terminal"])
                if run["failure"] == "stale":
                    break
            drains = int(client_ticks or needs_pending(mode, run))
            if drains:
                rows.extend(
                    (
                        f"AURORA_UEFI_DOMAIN_EVENT: vector=64 error=0 pc={arena + 0x22000 + 102}"
                        f" cpl=0 root={kernel} frame={arena + 0x46E00} cr2=0",
                        f"AURORA_UEFI_TIMER_DRAIN: epoch={epoch} root={kernel} ss=16",
                    )
                )
            rows.extend(
                (
                    f"AURORA_UEFI_TIMER_QUIET: epoch={epoch} ticks={used} drains={drains}"
                    f" compiled={compiled} context={int(context)} root={kernel}",
                    f"AURORA_UEFI_DISPATCH_RESTORE: client={run['client']} domain={d} root={kernel}"
                    f" stack={arena + 0x47000} event={run['outcome']} value={run['value']}",
                )
            )
        yield mode, 33 if mode in SUCCESS else 35, prefix + "\n".join(rows) + "\n", metadata


def self_test():
    # Exact accepted PR84 fixture corpus for all 17 original modes, with and
    # without optional client interrupts. New profiles must not redefine it.
    old_rows = [(ticks, item) for ticks in (True, False) for item in fixtures(ticks) if item[0] not in DISPOSAL_DENIED]
    original_digest = hashlib.sha256(json.dumps(old_rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    need(
        original_digest == "5ab59a168c375d606834cd41bb73937329a73963f494f6ec59317b09d4b7420b",
        "Changed accepted user-phase fixture corpus",
    )
    rejected = positives = 0

    def reject(status, text, mode, meta, label):
        nonlocal rejected
        try:
            validate(status, text, mode, meta)
        except (ValueError, TypeError, KeyError):
            rejected += 1
        else:
            raise RuntimeError("Invalid user-phase receipt accepted: " + mode + " " + label)

    for client_ticks in (True, False):
        for mode, status, text, meta in fixtures(client_ticks):
            validate(status, text, mode, meta)
            positives += 1
            reject(35 if status == 33 else 33, text, mode, meta, "exit status")
            reject(status, text, "user-unrecognized", meta, "unknown mode")
            lines = text.splitlines()
            boundary = next(i for i, line in enumerate(lines) if line.startswith("AURORA_UEFI_TIMER_READY:"))
            for i in range(boundary, len(lines)):
                for label, changed in (
                    ("missing", lines[:i] + lines[i + 1 :]),
                    ("duplicate", lines[:i] + [lines[i]] + lines[i:]),
                    ("unknown", lines[:i] + ["AURORA_UEFI_USER_UNRECOGNIZED: value=1"] + lines[i:]),
                ):
                    reject(status, "\n".join(changed) + "\n", mode, meta, f"{label} line {i}")
                if i + 1 < len(lines):
                    changed = lines[:i] + [lines[i + 1], lines[i]] + lines[i + 2 :]
                    reject(status, "\n".join(changed) + "\n", mode, meta, f"reordered line {i}")
                for match in re.finditer(r"(?<==)\d+", lines[i]):
                    value = int(match[0]) + 1
                    field = lines[i][: match.start()].rsplit(" ", 1)[-1]
                    if field == "flags=" or field == "pc=" and "vector=64 " in lines[i]:
                        value = 0
                    changed = lines.copy()
                    changed[i] = lines[i][: match.start()] + str(value) + lines[i][match.end() :]
                    reject(status, "\n".join(changed) + "\n", mode, meta, f"numeric line {i} {field}")
            for name in NAMES:
                for key in meta["images"][name]:
                    changed = copy.deepcopy(meta)
                    changed["images"][name][key] = True
                    reject(status, text, mode, changed, f"metadata type {name} {key}")
                for key, value in (
                    ("entry", BASE + 0x3000),
                    ("size", 8192),
                    ("return_pc", 0),
                    ("compiled_begin", 0),
                    ("compiled_end", BASE),
                    ("bounds_pc", 0),
                    ("overflow_pc", meta["images"][name]["bounds_pc"]),
                    ("probe_offset", 8),
                    ("context_end", 1),
                    ("probe_pc", BASE + 0x3000),
                ):
                    changed = copy.deepcopy(meta)
                    changed["images"][name][key] = value
                    reject(status, text, mode, changed, f"metadata range {name} {key}")
            for key, value in (
                ("drain_begin", 0),
                ("drain_end", 0),
                ("text_end", 0x21000),
                ("forged_pc", 1),
                ("text_end", True),
            ):
                changed = copy.deepcopy(meta)
                changed["kernel"][key] = value
                reject(status, text, mode, changed, f"kernel metadata {key}")
            changed = copy.deepcopy(meta)
            changed["images"]["extra"] = changed["images"]["clean"]
            reject(status, text, mode, changed, "fourth image")
            reject(status, text + "AURORA_UEFI_USER_PHASES_OK\n", mode, meta, "downstream success")
            reject(status, text + " AURORA_UEFI_TIMER_QUIET: epoch=1\n", mode, meta, "malformed Aurora-looking receipt")
            # These rewrite all matching claims, not just one side of a pair.
            # An implementation which trusts two agreeing receipts would fail.
            arena = 0x1000000
            substitutions = (
                (f"root={arena + 0x90000}", f"root={arena + 0xB0000}"),
                ("epoch=1", "epoch=99"),
                ("role=client", "role=service"),
                ("phase=request", "phase=completion"),
                ("transaction=3", "transaction=99"),
                ("grant=1", "grant=99"),
                ("generation=1", "generation=99"),
            )
            for before, after in substitutions:
                if before in text:
                    reject(status, text.replace(before, after), mode, meta, "joint forgery " + before)
    # Bounded new behavior fixture: peer executes between a saved tick and
    # resume, and the original quota is consumed rather than replenished.
    meta = next(fixtures())[3]
    rows = ["AURORA_UEFI_OK"]
    for scenario in range(3):
        epoch = 2 * scenario + 1
        left = 2 if scenario == 1 else 127
        rows += [
            f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used=1 remaining={left} pc=1",
            f"AURORA_USER_SUSPEND: domain=0 epoch={epoch} remaining={left}",
            f"AURORA_UEFI_DISPATCH_RESTORE: client=1 domain=2 root=1 event=returned value={checksum(70)}",
        ]
        if scenario < 2:
            rows += [f"AURORA_USER_RESUME: domain=0 epoch={epoch} remaining={left} ticks=1"]
            if scenario == 1:
                rows += [
                    f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used={used} remaining={3 - used} pc=1" for used in (2, 3)
                ]
            event, value = ("budget", 0) if scenario == 1 else ("returned", checksum(40))
            rows += [f"AURORA_UEFI_DISPATCH_RESTORE: client=0 domain=0 root=1 event={event} value={value}"]
        rows += [f"AURORA_USER_RESUME_CASE: case={scenario} used=0"]
    text = "\n".join(rows + ["AURORA_UEFI_USER_RESUME_OK"])
    validate(33, text, "user-resume", meta)
    positives += 1
    for before, after in (
        ("remaining=127 ticks=1", "remaining=128 ticks=0"),
        (f"value={checksum(40)}", "value=1"),
        (
            "AURORA_USER_RESUME: domain=0 epoch=1 remaining=127 ticks=1",
            "AURORA_USER_RESUME: domain=0 epoch=1 remaining=127 ticks=1\n"
            "AURORA_USER_RESUME: domain=0 epoch=1 remaining=127 ticks=1",
        ),
    ):
        reject(33, text.replace(before, after), "user-resume", meta, "resume behavioral regression")
    call_meta = copy.deepcopy(next(fixtures())[3])
    del call_meta["images"]["peer"]
    call_meta["images"]["clean"]["call_pc"] = BASE + 70
    rows = []
    for case in range(4):
        epoch = 2 * case + 1
        rows += [
            f"AURORA_UEFI_USER_RUN: epoch={epoch} role=client phase=request "
            f"client=0 transaction=0 source={1 if case == 1 else 8 if case == 2 else 0} root=1",
            f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used=1 remaining=127 pc={BASE + 88}",
            f"AURORA_UEFI_DOMAIN_EVENT: vector=130 error=0 pc={BASE + 70} cpl=3 root=1 frame=1 cr2=0",
            f"AURORA_CALL_PARK: ticket={2 * case + 2} epoch={epoch} ticks=1 remaining=127",
        ]
        if case < 3:
            rows += [
                f"AURORA_UEFI_USER_RUN: epoch={epoch + 1} role=service phase=service "
                f"client=0 transaction={epoch + 1} source={4 if case == 1 else 1} root=2"
            ]
            if case != 1:
                rows += [f"AURORA_UEFI_TIMER_TICK: epoch={epoch + 1} used=1 remaining=127 pc={BASE + 4096 + 88}"]
            rows += [
                f"AURORA_UEFI_DOMAIN_EVENT: vector={6 if case == 1 else 129} error=0 "
                f"pc={BASE + 4096 + (400 if case == 1 else 60)} cpl=3 root=2 frame=1 cr2=0",
                f"AURORA_CALL_SERVICE: epoch={epoch + 1} event={'bounds' if case == 1 else 'returned'} "
                f"value={0 if case == 1 else 42}",
                f"AURORA_CALL_RESUME: epoch={epoch} ticks=1 remaining=127",
                f"AURORA_UEFI_DOMAIN_EVENT: vector=130 error=0 pc={BASE + 70} cpl=3 root=1 frame=1 cr2=0",
            ]
        if case == 2:
            rows += [
                f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used={tick} remaining={128 - tick} pc={BASE + 88}"
                for tick in range(2, 129)
            ]
        if case < 3:
            rows += [
                f"AURORA_CALL_COMPLETE: epoch={epoch} event={'budget' if case == 2 else 'returned'} "
                f"value={82 if case == 0 else 40 if case == 1 else 0}"
            ]
        rows += [f"AURORA_CALL_CASE: case={case} used=0"]
    call_text = "\n".join(rows + ["AURORA_UEFI_CALL_OK", "AURORA_UEFI_OK"])
    validate(33, call_text, "user-call", call_meta)
    positives += 1
    for before, after in (
        ("epoch=1 ticks=1 remaining=127", "epoch=1 ticks=0 remaining=128"),
        ("ticket=4", "ticket=2"),
        ("used=128 remaining=0", "used=127 remaining=1"),
        ("case=3 used=0", "case=3 used=4"),
        ("vector=130 error=0", "vector=130 error=1"),
        ("AURORA_UEFI_CALL_OK", ""),
    ):
        reject(33, call_text.replace(before, after), "user-call", call_meta, "call receipt mutation")
    for prefix in ("AURORA_UEFI_TIMER_TICK: epoch=1 ", "AURORA_CALL_COMPLETE: epoch=1 "):
        selected = next(row for row in call_text.splitlines() if row.startswith(prefix))
        changed = call_text.replace(selected + "\n", "")
        changed = changed.replace("AURORA_CALL_RESUME: epoch=1", selected + "\nAURORA_CALL_RESUME: epoch=1")
        reject(33, changed, "user-call", call_meta, "misordered caller evidence")
    reject(33, call_text, "user-call-pending", call_meta, "missing pending drain")
    for prefix in (
        "AURORA_UEFI_TIMER_TICK: epoch=1 ",
        "AURORA_UEFI_USER_RUN: epoch=2 ",
        "AURORA_CALL_SERVICE: epoch=2 ",
        "AURORA_CALL_COMPLETE: epoch=1 ",
    ):
        changed = "\n".join(row for row in call_text.splitlines() if not row.startswith(prefix))
        reject(33, changed, "user-call", call_meta, "missing caller/peer evidence")
    print(f"PASS: user-phase transcripts {positives} positive and {rejected} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 4 and sys.argv[1] == "--resume-code":
        resume_code(Path(sys.argv[2]).read_text(), Path(sys.argv[3]))
    else:
        try:
            validate(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        except (ValueError, IndexError, KeyError, TypeError) as error:
            raise SystemExit("FAIL: " + str(error))
        print("PASS: exact user-run authority, hardware budgets and client recovery transcript")

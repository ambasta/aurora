#!/usr/bin/env python3
"""Exact staged dispatcher sequence plus independently validated timer frames."""

from pathlib import Path
import copy, importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location("budget", Path(__file__).with_name("kernel-uefi-budget-smoke.py"))
budget = importlib.util.module_from_spec(spec)
spec.loader.exec_module(budget)
need = budget.need
BASE = budget.BASE
EVENT = budget.EVENT
# Historical synthetic scenarios include copied-policy failures now covered hosted.
# Current boot modes are admitted separately by kernel_profiles and emulator_clock.
MODES = (
    "dispatch",
    "dispatch-budget",
    "dispatch-fault",
    "dispatch-mixed",
    "dispatch-pending",
    "dispatch-cross-reply",
    "dispatch-client-owner",
    "dispatch-stale",
    "dispatch-duplicate",
    "dispatch-full",
    "dispatch-root",
    "dispatch-peer-code",
    "dispatch-policy-cursor",
    "dispatch-policy-mask",
    "dispatch-policy-output",
)
SUCCESS = MODES[:5]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT  # noqa: E402
import kernel_profiles  # noqa: E402

# Modes of the dispatcher rows of service-fixture, whose peer wrapper carries the probe set.
FIXTURE_MODES = kernel_profiles.family_modes("service-fixture", "dispatch_")


def metadata_valid(meta, mode):
    need(type(meta) is dict and set(meta) == {"images", "kernel"}, "Dispatcher metadata shape")
    images = meta["images"]
    need(type(images) is dict and set(images) == {"clean", "bounds", "peer"}, "Exactly three images")
    base = copy.deepcopy(meta)
    base["images"] = {name: base["images"][name] for name in ("clean", "bounds")}
    budget.metadata_valid(base, "budget")
    image = dict(images["peer"]) if type(images["peer"]) is dict else images["peer"]
    probes = image.pop("probes", None) if type(image) is dict else None
    need(
        type(image) is dict
        and set(image) == set(images["clean"])
        and all(type(v) is int and 0 <= v < 1 << 64 for v in image.values()),
        "Peer metadata types",
    )
    shifted = {
        key: (value - 32768 if key not in ("size", "probe_offset") and value else value) for key, value in image.items()
    }
    if probes is not None:
        shifted["probes"] = (
            {key: value - 32768 if type(value) is int else value for key, value in probes.items()}
            if type(probes) is dict
            else probes
        )
    base["images"]["clean"] = shifted
    budget.metadata_valid(base, "budget", "clean" if mode in FIXTURE_MODES else None)
    need(image["entry"] == BASE + 32768 and image["probe_offset"] == 0, "Peer layout authority")


def expected(mode, images, arena):
    rows = []
    roots = [arena + v for v in (0x90000, 0xA0000, 0xD0000)]
    kernel = arena + 0x11000
    frame = arena + 0x88000 - 176

    def add(s):
        rows.append(re.escape(s))

    def event(index, vector=129, error=0, pc=None, cr2=0):
        image = images[("clean", "bounds", "peer")[index]]
        add(
            f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error={error} pc="
            f"{image['return_pc'] if pc is None else pc} cpl=3 root={roots[index]}"
            f" frame={frame} cr2={cr2}"
        )

    states = ["idle", "idle"]
    tx = [0, 0]
    grants = [0, 0]
    counter = 0
    queued = lambda: sum(state == "pending" for state in states)

    def record(op, c, t, a, b):
        add(f"AURORA_UEFI_DISPATCH_{op}: client={c} transaction={t} first={a} second={b} queued={queued()}")

    def bind():
        nonlocal counter
        states[:] = ["idle", "idle"]
        tx[:] = [0, 0]
        for c in range(2):
            counter += 1
            grants[c] = counter
            record("BIND", c, 0, counter, 0 if c == 0 else 2)

    def enter(c, index, phase, t, grant=None):
        add(
            f"AURORA_UEFI_DISPATCH_ENTER: client={c} domain={index} phase="
            f"{phase} root={roots[index]} grant="
            f"{grants[c] if grant is None else grant} transaction={t}"
        )

    def envelope(c, phase, slot, t, value, second, grant=None):
        add(
            f"AURORA_UEFI_DISPATCH_ENVELOPE: client={c} phase={phase} versio"
            f"n=1 slot={slot} generation={grants[c] if grant is None else grant}"
            f" transaction={t} value={value} second={second}"
        )

    def restore(c, index, outcome, value):
        rows.append(
            re.escape(f"AURORA_UEFI_DISPATCH_RESTORE: client={c} domain={index} root={kernel} stack=")
            + r"(\d+)"
            + re.escape(f" event={outcome} value={value}")
        )

    def request(c, denied=False, owner=False, peer=False):
        nonlocal counter
        index = 0 if c == 0 else 2
        grant = grants[0] if owner else grants[c]
        enter(c, index, 0, 0, grant)
        if peer:
            event(index, 14, 4, images["peer"]["probes"]["peer_code"], BASE)
            add("AURORA_UEFI_RUNTIME_FAIL: exception site authority")
            return
        event(index)
        envelope(c, 0, 0, 0, (40, 70)[c], (2, 3)[c], grant)
        if denied:
            add("AURORA_UEFI_RUNTIME_FAIL: dispatch request capability/queue")
            return
        counter += 1
        tx[c] = counter
        states[c] = "pending"
        record("SUBMIT", c, counter, (40, 70)[c], (2, 3)[c])
        restore(c, index, "returned", (40, 70)[c])

    def service(c, phase=1, denial=None):
        states[c] = "delivered"
        record("SELECT", c, tx[c], (40, 70)[c], (2, 3)[c])
        grant = grants[1 - c] if denial == "cross" else 1 if denial == "stale" else grants[c]
        enter(c, 1, phase, tx[c], grant)
        if denial == "root":
            add(f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}")
            add("AURORA_UEFI_RUNTIME_FAIL: timer active origin")
            return
        if phase == 1:
            event(1)
            envelope(c, 1, 1, tx[c], (42, 73)[c], (2, 3)[c], grant)
            if denial:
                add("AURORA_UEFI_RUNTIME_FAIL: dispatch selected reply authority")
                return
            states[c] = "replied"
            record("REPLY", c, tx[c], (42, 73)[c], 0)
        elif phase == 4:
            event(1, 6, 0, images["bounds"]["bounds_pc"])
        restore(
            c, 1, "returned" if phase == 1 else "bounds" if phase == 4 else "budget", (42, 73)[c] if phase == 1 else 0
        )

    def complete(c, cancelled=False):
        states[c] = "consumed"
        record("CONSUME", c, tx[c], 0 if cancelled else (42, 73)[c], 1 if cancelled else 0)
        index = 0 if c == 0 else 2
        phase = 3 if cancelled else 2
        value = (7, 9)[c] if cancelled else (42, 73)[c]
        enter(c, index, phase, tx[c])
        event(index)
        envelope(c, phase, 0, tx[c], value, 0)
        record("COMPLETE", c, tx[c], value, 0)
        restore(c, index, "returned", value)

    for index in range(3):
        add(
            f"AURORA_UEFI_DISPATCH_DOMAIN: index={index} root={roots[index]}"
            f" entry={BASE + index * 16384} stack={BASE + 0x204000 + index * 0x200000}"
            f" frame={arena + 0xC0000 + index * 0x4000}"
        )
    bind()
    request(0)
    if mode == "dispatch-duplicate":
        request(0, True)
        return rows
    if mode == "dispatch-client-owner":
        request(1, True, True)
        return rows
    if mode == "dispatch-peer-code":
        request(1, peer=True)
        return rows
    request(1)
    if mode == "dispatch-full":
        request(0, True)
        return rows
    if mode.startswith("dispatch-policy-"):
        add("AURORA_UEFI_RUNTIME_FAIL: dispatch fair copied selection")
        return rows
    if mode in ("dispatch-budget", "dispatch-fault", "dispatch-mixed", "dispatch-stale"):
        mixed = mode == "dispatch-mixed"
        if mixed:
            service(0)
            service(1, 5)
        else:
            service(0, 4 if mode == "dispatch-fault" else 5)
        for c in range(2):
            if states[c] in ("pending", "delivered"):
                states[c] = "cancelled"
        record("CANCEL", 2, 0, 1 if mixed else 2, 1 if mixed else 0)
        complete(0, not mixed)
        complete(1, True)
        record("RESTART", 2, 0, arena + 0xC4000, 12)
        bind()
        request(0)
        request(1)
    denial = {"dispatch-cross-reply": "cross", "dispatch-stale": "stale", "dispatch-root": "root"}.get(mode)
    service(0, denial=denial)
    if denial:
        return rows
    complete(0)
    states[0] = "idle"
    tx[0] = 0
    record("RECYCLE", 0, 0, 0, 0)
    request(0)
    service(1)
    complete(1)
    service(0)
    complete(0)
    add("AURORA_UEFI_DISPATCH_CLEANUP_OK: used=0 records=0")
    add("AURORA_UEFI_DISPATCH_OK")
    add("AURORA_UEFI_LANGUAGE_OK: value=42")
    add("AURORA_UEFI_OK")
    return rows


def validate(status, text, mode, meta):
    marker = "AURORA_FIXTURE_READY\n"
    need(text.count(marker) == (1 if mode in FIXTURE_MODES else 0), "Exact dispatcher fixture readiness")
    if mode in FIXTURE_MODES:
        text = budget.ipc.selected_echo(text, mode)
        need(
            text.index("AURORA_PCI_WINDOW_CLOSED:") < text.index(marker) < text.index("AURORA_UEFI_TIMER_READY:"),
            "Dispatcher selector admission phase",
        )
        text = text.replace(marker, "", 1)
    need(mode in MODES, "Unknown dispatcher mode")
    metadata_valid(meta, mode)
    need(status == (33 if mode in SUCCESS else 35), "Wrong dispatcher exit")
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith(
                ("AURORA_UEFI_TIMER_", "AURORA_UEFI_DISPATCH_", "AURORA_UEFI_RUNTIME_", "AURORA_UEFI_DOMAIN_")
            )
        ),
        None,
    )
    need(start is not None, "Missing dispatcher boundary")
    prefix = "\n".join(lines[:start]) + "\n"
    budget.firmware_prefix(prefix, "budget")
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    kernel = arena + 0x11000
    service = arena + 0xA0000
    roots = [arena + x for x in (0x90000, 0xA0000, 0xD0000)]
    records = [line for line in lines[start:] if line.startswith("AURORA_")]
    need(
        records.pop(0) == f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={budget.APIC} id=0 root={kernel}",
        "Exact admitted timer",
    )
    logical = []
    active = False
    domain = None
    phase = None
    epoch = 0
    armed = False
    terminal = False
    quiet = False
    last = None
    used = drains = compiled = 0
    limit = 0
    pending = False
    for pos, line in enumerate(records):
        if last and last[0] == 64:
            need(
                line.startswith(
                    (
                        "AURORA_UEFI_TIMER_TICK:",
                        "AURORA_UEFI_TIMER_DRAIN:",
                        "AURORA_UEFI_RUNTIME_ROOT_PROBE:",
                        "AURORA_UEFI_RUNTIME_FAIL:",
                    )
                ),
                "Unconsumed timer frame",
            )
        entry = re.fullmatch(
            (
                "AURORA_UEFI_DISPATCH_ENTER: client=(\\d+) domain=(\\d+) phase=(\\d+) root=(\\d+) grant=(\\d+) "
                "transaction=(\\d+)"
            ),
            line,
        )
        if entry:
            c, domain, phase, r, g, t = map(int, entry.groups())
            need(
                not active and not armed and c in (0, 1) and domain in (0, 1, 2) and r == roots[domain],
                "Overlapping/wrong domain launch",
            )
            active = True
            terminal = quiet = False
            last = None
            logical.append(line)
            continue
        arm = re.fullmatch(r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=(\d+)", line)
        if arm:
            e, b, r = map(int, arm.groups())
            need(
                active
                and domain == 1
                and phase in (1, 4, 5)
                and not armed
                and e == epoch + 1
                and b == (3 if phase == 5 else 128)
                and r == service
                and pos
                and re.fullmatch(r"AURORA_UEFI_DISPATCH_ENTER:.*", records[pos - 1]),
                "Wrong timer arm",
            )
            epoch = e
            limit = b
            armed = True
            used = drains = compiled = 0
            pending = False
            continue
        event = re.fullmatch(EVENT, line)
        if event:
            v, e, pc, cpl, r, f, cr2 = map(int, event.groups())
            need(active, "Event outside run")
            last = (v, e, pc, cpl, r, f, cr2)
            if v == 64:
                need(armed and domain == 1 and e == 0 and cr2 == 0, "Timer outside selected service")
                if cpl == 3:
                    need(
                        r == service
                        and f == arena + 0x88000 - 176
                        and BASE + 16384 <= pc < BASE + 16384 + meta["images"]["bounds"]["size"],
                        "Wrong service timer frame",
                    )
                else:
                    need(
                        cpl == 0
                        and terminal
                        and r == kernel
                        and arena + LAYOUT.kernel_stack_bottom <= f <= arena + LAYOUT.kernel_stack_top - 176
                        and f % 8 == 0
                        and arena + LAYOUT.kernel_payload_offset + meta["kernel"]["drain_begin"]
                        <= pc
                        <= arena + LAYOUT.kernel_payload_offset + meta["kernel"]["drain_end"],
                        "Wrong kernel drain frame",
                    )
                continue
            need(not terminal, "Duplicate terminal event")
            terminal = True
            logical.append(line)
            continue
        tick = re.fullmatch(
            r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=(\d+) remaining=(\d+) pc=(\d+) flags=(\d+)", line
        )
        if tick:
            e, n, left, pc, flags = map(int, tick.groups())
            need(
                armed
                and not terminal
                and last
                and last[:2] == (64, 0)
                and last[3] == 3
                and pos
                and re.fullmatch(EVENT, records[pos - 1])
                and e == epoch
                and n == used + 1
                and left == limit - n
                and n <= limit
                and pc == last[2]
                and flags & 0x202 == 0x202
                and flags & ~0x10ED7 == 0,
                "Invalid tick/context pairing",
            )
            used = n
            image = meta["images"]["bounds"]
            compiled += image["compiled_begin"] <= pc < image["compiled_end"]
            last = None
            if left == 0:
                need(phase == 5, "Unexpected finite exhaustion")
                terminal = True
            continue
        forced = re.fullmatch(r"AURORA_UEFI_TIMER_PENDING: epoch=(\d+)", line)
        if forced:
            need(
                mode == "dispatch-pending"
                and armed
                and terminal
                and last
                and last[0] == 129
                and pos
                and re.fullmatch(EVENT, records[pos - 1])
                and int(forced[1]) == epoch
                and not pending,
                "Wrong pending injection",
            )
            pending = True
            continue
        drain = re.fullmatch(r"AURORA_UEFI_TIMER_DRAIN: epoch=(\d+) root=(\d+) ss=(\d+)", line)
        if drain:
            need(
                armed
                and terminal
                and last
                and last[0] == 64
                and last[3] == 0
                and pos
                and re.fullmatch(EVENT, records[pos - 1])
                and tuple(map(int, drain.groups())) == (epoch, kernel, 16),
                "Wrong drain authority",
            )
            drains += 1
            last = None
            continue
        finish = re.fullmatch(
            r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ticks=(\d+) drains=(\d+) compiled=(\d+) context=(\d+) root=(\d+)",
            line,
        )
        if finish:
            need(
                armed and terminal and tuple(map(int, finish.groups())) == (epoch, used, drains, compiled, 0, kernel),
                "Wrong timer accounting",
            )
            need((phase == 4 or compiled > 0) and (phase != 5 or used == 3), "Missing compiled preemption")
            if phase == 1:
                need(logical[-1].startswith("AURORA_UEFI_DISPATCH_REPLY:"), "Quiescence before reply")
            if mode == "dispatch-pending":
                need(pending and drains > 0, "Pending delivery unproved")
            armed = False
            quiet = True
            last = None
            continue
        restore = re.fullmatch(
            (
                "AURORA_UEFI_DISPATCH_RESTORE: client=(\\d+) domain=(\\d+) root=(\\d+) stack=(\\d+) event=(retu"
                "rned|bounds|budget) value=(\\d+)"
            ),
            line,
        )
        if restore:
            c, d, r, sp = map(int, restore.groups()[:4])
            need(
                active
                and terminal
                and d == domain
                and r == kernel
                and arena + LAYOUT.kernel_stack_bottom <= sp < arena + LAYOUT.kernel_stack_top
                and sp % 8 == 0
                and (domain != 1 or quiet and not armed),
                "Restore before quiescence/ownership",
            )
            active = False
            last = None
            logical.append(line)
            continue
        if line.startswith("AURORA_UEFI_TIMER_"):
            raise ValueError("Unexpected timer record")
        if line.startswith("AURORA_UEFI_RUNTIME_ROOT_PROBE:"):
            need(
                mode == "dispatch-root" and last and last[0] == 64 and pos and re.fullmatch(EVENT, records[pos - 1]),
                "Root probe outside exact event",
            )
        if line.startswith("AURORA_UEFI_RUNTIME_FAIL:"):
            need(pos == len(records) - 1, "Continued after fail-stop")
        logical.append(line)
    wanted = expected(mode, meta["images"], arena)
    need(len(logical) == len(wanted), "Incomplete/extra dispatcher sequence")
    for actual, pattern in zip(logical, wanted):
        need(re.fullmatch(pattern, actual), "Wrong dispatcher state/order: " + actual)
    if mode in SUCCESS:
        need(not armed and not active, "Active state at cleanup")
    elif mode == "dispatch-root":
        need(armed and active and used == 0 and last and last[0] == 64, "Wrong denied root event")
    elif mode.startswith("dispatch-policy-"):
        need(not armed and not active and epoch == 0, "Policy failure after service activation")


if __name__ == "__main__":
    try:
        validate(
            int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
        )
    except (ValueError, IndexError, KeyError, TypeError) as error:
        raise SystemExit("FAIL: " + str(error))
    print("PASS: exact dispatcher lifecycle and hardware timer transcript")

#!/usr/bin/env python3
"""Validate each hardware timer event before projecting the IPC state trace."""

from pathlib import Path
import copy, importlib.util, json, re, sys

spec = importlib.util.spec_from_file_location("ipc", Path(__file__).with_name("kernel-uefi-ipc-smoke.py"))
ipc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipc)
need = ipc.need
BASE = ipc.BASE
APIC = 0xFFFF900000000000
# Historical synthetic scenarios include copied-policy failures now covered hosted.
# Current boot modes are admitted separately by kernel_profiles and emulator_clock.
MODES = (
    "budget",
    "budget-fault",
    "budget-context",
    "budget-pending",
    "budget-noapic",
    "budget-smp",
    "budget-discovery",
    "budget-cache",
    "budget-alias",
    "budget-forged",
    "budget-root",
    "budget-mmio",
    "budget-softint",
    "budget-fpu",
    "budget-epoch",
)
FIXTURE_MODES = (
    "budget-fault",
    "budget-discovery",
    "budget-cache",
    "budget-alias",
    "budget-pending",
    "budget-forged",
    "budget-root",
    "budget-epoch",
)
POLICY_MODES = ("budget-policy-zero", "budget-policy-counts", "budget-policy-wide", "budget-policy-output")
MODES += POLICY_MODES
SUCCESS = MODES[:4]
EARLY = MODES[4:9]
EVENT = r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)"


def metadata_valid(meta, mode):
    need(type(meta) is dict and set(meta) == {"images", "kernel"}, "Malformed budget metadata")
    images = meta["images"]
    need(type(images) is dict and set(images) == {"clean", "bounds"}, "Budget image set")
    extra = {"compiled_begin", "compiled_end", "context_begin", "context_end"}
    base_images = {}
    for index, name in enumerate(("clean", "bounds")):
        image = images[name]
        need(type(image) is dict and extra <= set(image), "Missing compiled ranges")
        need(all(type(value) is int and 0 <= value < 1 << 64 for value in image.values()), "Invalid range scalar")
        base_images[name] = {key: value for key, value in image.items() if key not in extra}
        base = BASE + index * 16384
        size = image["size"]
        start = image["compiled_begin"]
        end = image["compiled_end"]
        need(base <= image["return_pc"] < start < end <= base + size, "Compiled function range")
        need(end <= image["bounds_pc"], "Compiled function includes trap helpers")
        begin = image["context_begin"]
        finish = image["context_end"]
        if mode == "budget-context" and index == 1:
            need(base <= begin < finish <= image["return_pc"] and finish - begin == 6, "Exact context interval")
        else:
            need(begin == finish == 0, "Unexpected context authority")
        probe = image["probe_pc"]
        want = index == 1 and mode in ("budget-mmio", "budget-softint", "budget-fpu")
        need(bool(probe) == want and (not probe or base <= probe < image["return_pc"]), "Unexpected privileged probe")
        base_images[name]["probe_pc"] = 0
    ipc.metadata_valid(
        base_images,
        mode if mode in ("user-call", "user-call-pending", "user-call-owner", "user-call-site") else "ipc-fault",
    )
    kernel = meta["kernel"]
    if mode == "budget-noapic":
        need(kernel is None, "No-APIC rejection must not claim timer sites")
        return base_images
    need(
        type(kernel) is dict
        and set(kernel) == {"drain_begin", "drain_end", "text_end", "forged_pc"}
        and all(type(v) is int and v >= 0 for v in kernel.values()),
        "Malformed kernel sites",
    )
    need(
        0 < kernel["drain_begin"] < kernel["drain_end"] < kernel["text_end"] <= 0x20000
        and kernel["drain_end"] - kernel["drain_begin"] == 4
        and kernel["text_end"] % 4096 == 0,
        "Drain range outside owned RX",
    )
    need(
        (2 <= kernel["forged_pc"] < kernel["text_end"]) if mode in FIXTURE_MODES else kernel["forged_pc"] == 0,
        "Forged site authority",
    )
    return base_images


def firmware_prefix(prefix, mode):
    if mode == "budget-smp":
        ipc.pci.acpi.validate(33, prefix + ipc.SUFFIX, "acpi-two")
        prefix = prefix.replace("AURORA_ACPI_CPU: id=1 uid=1 enabled=1 capable=0 x2=0\n", "").replace(
            "AURORA_ACPI_TOPOLOGY: records=2 enabled=2", "AURORA_ACPI_TOPOLOGY: records=1 enabled=1"
        )
    ipc.pci.validate(33, prefix + ipc.SUFFIX, "pci")


def validate(status, text, mode, meta):
    marker = "AURORA_FIXTURE_READY\n"
    need(text.count(marker) == (1 if mode in FIXTURE_MODES else 0), "Exact budget fixture readiness")
    if mode in FIXTURE_MODES:
        need(text.index("AURORA_PCI_WINDOW_CLOSED:") < text.index(marker), "Budget selector before firmware completion")
        boundary = [text.index(item) for item in ("AURORA_UEFI_TIMER_", "AURORA_UEFI_RUNTIME_FAIL:") if item in text]
        need(boundary and text.index(marker) < min(boundary), "Budget selector after timer admission")
        text = text.replace(marker, "", 1)
    need(mode in MODES, "Unknown budget mode")
    base_images = metadata_valid(meta, mode)
    need(status == (33 if mode in SUCCESS else 35), "Wrong budget exit")
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.startswith(
                ("AURORA_UEFI_TIMER_", "AURORA_UEFI_IPC_", "AURORA_UEFI_RUNTIME_", "AURORA_UEFI_DOMAIN_")
            )
        ),
        None,
    )
    need(start is not None, "Missing budget boundary")
    prefix = "\n".join(lines[:start]) + "\n"
    firmware_prefix(prefix, mode)
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    kernel = arena + 0x11000
    service = arena + 0xA0000
    records = [line for line in lines[start:] if line.startswith("AURORA_")]
    if mode in EARLY:
        reason = "timer mapping tree" if mode == "budget-alias" else "timer aperture admission"
        need(records == ["AURORA_UEFI_RUNTIME_FAIL: " + reason], "Early rejection continued")
        return
    need(
        records and records.pop(0) == f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={APIC} id=0 root={kernel}",
        "Wrong timer admission",
    )
    projected = []
    phase = None
    slot = None
    epoch = 0
    armed = False
    used = 0
    budget = 0
    drains = 0
    compiled = 0
    contexts = 0
    last_event = None
    pending_context = False
    terminal = False
    quiet = False
    forced_pending = False
    service_runs = 0
    success_marker = False
    for position, line in enumerate(records):
        if pending_context:
            need(
                line == f"AURORA_UEFI_TIMER_CONTEXT: epoch={epoch} tick={used} registers=15 df=1",
                "Missing exact GPR/DF receipt",
            )
            pending_context = False
            continue
        if last_event and last_event[0] == 64:
            need(
                line.startswith(
                    (
                        "AURORA_UEFI_TIMER_TICK:",
                        "AURORA_UEFI_TIMER_DRAIN:",
                        "AURORA_UEFI_RUNTIME_ROOT_PROBE:",
                        "AURORA_UEFI_RUNTIME_FAIL:",
                    )
                ),
                "Unconsumed hardware timer frame",
            )
        entry = re.fullmatch(
            r"AURORA_UEFI_IPC_ENTER: slot=(\d+) phase=(\d+) root=(\d+) grant=(\d+) transaction=(\d+)", line
        )
        if entry:
            need(not armed, "New domain before timer quiescence")
            slot, phase, root, grant, transaction = map(int, entry.groups())
            last_event = None
            quiet = False
            terminal = False
            need(slot in (0, 1) and root == arena + 0x90000 + slot * 0x10000, "Wrong timer run root")
            if slot == 1:
                need(phase in (1, 4, 5), "Wrong service phase")
            projected.append(line.replace("phase=5 ", "phase=4 "))
            continue
        arm = re.fullmatch(r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=(\d+)", line)
        if arm:
            e, b, r = map(int, arm.groups())
            service_runs += 1
            need(
                slot == 1
                and phase in (1, 4, 5)
                and not armed
                and e == service_runs
                and b == (3 if phase == 5 else 128)
                and r == service,
                "Invalid arm/run epoch",
            )
            need(position and records[position - 1].startswith("AURORA_UEFI_IPC_ENTER:"), "Arm outside fresh launch")
            epoch = e
            budget = b
            used = drains = compiled = contexts = 0
            armed = True
            forced_pending = False
            continue
        event = re.fullmatch(EVENT, line)
        if event:
            vector, error, pc, cpl, root, frame, cr2 = map(int, event.groups())
            last_event = (vector, error, pc, cpl, root, frame, cr2)
            if vector == 64:
                need(armed and slot == 1, "Timer outside active service")
                if cpl == 3:
                    need(
                        (error, root, frame, cr2) == (0, service, arena + 0x88000 - 176, 0)
                        and BASE + 16384 <= pc < BASE + 16384 + meta["images"]["bounds"]["size"],
                        "Invalid user timer frame",
                    )
                else:
                    need(
                        cpl == 0
                        and error == 0
                        and cr2 == 0
                        and arena + 0x44000 <= frame <= arena + 0x48000 - 176
                        and frame % 8 == 0,
                        "Invalid kernel timer frame",
                    )
                    if mode == "budget-forged":
                        need(
                            root == service and pc == arena + 0x22000 + meta["kernel"]["forged_pc"],
                            "Forged interrupt site",
                        )
                    else:
                        need(
                            terminal
                            and root == kernel
                            and arena + 0x22000 + meta["kernel"]["drain_begin"]
                            <= pc
                            <= arena + 0x22000 + meta["kernel"]["drain_end"],
                            "Unauthorized kernel drain",
                        )
                continue
            if slot == 1:
                need(armed, "Service terminal without armed run")
            if slot == 1 and vector in (129, 6):
                terminal = True
            projected.append(line)
            continue
        tick = re.fullmatch(
            r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=(\d+) remaining=(\d+) pc=(\d+) flags=(\d+)", line
        )
        if tick:
            e, n, remaining, pc, flags = map(int, tick.groups())
            need(
                armed
                and last_event
                and last_event[:2] == (64, 0)
                and last_event[3] == 3
                and position
                and re.fullmatch(EVENT, records[position - 1]),
                "Tick lacks unique immediately preceding hardware frame",
            )
            need(
                e == epoch
                and n == used + 1
                and n <= budget
                and remaining == budget - n
                and pc == last_event[2]
                and flags & 0x202 == 0x202
                and flags & ~0x10ED7 == 0,
                "Wrong tick accounting/context",
            )
            used = n
            image = meta["images"]["bounds"]
            compiled += image["compiled_begin"] <= pc < image["compiled_end"]
            if image["context_begin"] and image["context_begin"] <= pc <= image["context_end"]:
                need(flags & 0x400, "Context lost DF")
                contexts += 1
                pending_context = True
            if remaining == 0:
                need(phase == 5, "Unexpected finite-service exhaustion")
                terminal = True
                projected.append(
                    f"AURORA_UEFI_DOMAIN_EVENT: vector=6 error=0 pc={image['bounds_pc']}"
                    f" cpl=3 root={service} frame={arena + 0x88000 - 176} cr2=0"
                )
            last_event = None
            continue
        pending = re.fullmatch(r"AURORA_UEFI_TIMER_PENDING: epoch=(\d+)", line)
        if pending:
            need(
                position and re.fullmatch(EVENT, records[position - 1]) and last_event and last_event[0] == 129,
                "Pending injection not at return boundary",
            )
            need(
                mode == "budget-pending" and armed and terminal and int(pending[1]) == epoch and not forced_pending,
                "Invalid pending injection phase",
            )
            forced_pending = True
            continue
        drain = re.fullmatch(r"AURORA_UEFI_TIMER_DRAIN: epoch=(\d+) root=(\d+) ss=(\d+)", line)
        if drain:
            need(
                armed
                and terminal
                and last_event
                and last_event[0] == 64
                and last_event[3] == 0
                and position
                and re.fullmatch(EVENT, records[position - 1])
                and tuple(map(int, drain.groups())) == (epoch, kernel, 16),
                "Drain lacks exact kernel frame",
            )
            drains += 1
            last_event = None
            continue
        finish = re.fullmatch(
            r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ticks=(\d+) drains=(\d+) compiled=(\d+) context=(\d+) root=(\d+)",
            line,
        )
        if finish:
            need(
                projected
                and (
                    projected[-1].startswith("AURORA_UEFI_IPC_REPLY:")
                    if phase == 1
                    else projected[-1].startswith("AURORA_UEFI_DOMAIN_EVENT: vector=6 ")
                ),
                "Quiescence before terminal IPC transition",
            )
            need(
                armed
                and terminal
                and tuple(map(int, finish.groups())) == (epoch, used, drains, compiled, contexts, kernel),
                "Incorrect terminal timer accounting",
            )
            need((phase == 4 or compiled > 0) and (phase != 5 or used == 3), "No actual compiled-code preemption")
            if mode == "budget-context" and phase == 1:
                need(contexts > 0, "No register restoration evidence")
            if mode == "budget-pending" and phase == 1:
                need(forced_pending and drains > 0, "Pending interrupt not drained")
            armed = False
            quiet = True
            continue
        if line.startswith("AURORA_UEFI_IPC_RESTORE:"):
            restored = re.fullmatch(
                (
                    "AURORA_UEFI_IPC_RESTORE: slot=(\\d+) root=(\\d+) stack=(\\d+) event=(returned|bounds|budge"
                    "t) value=(\\d+)"
                ),
                line,
            )
            need(restored is not None, "Malformed restored context")
            rs, rr, rsp = map(int, restored.groups()[:3])
            need(
                rs == slot and rr == kernel and arena + 0x44000 <= rsp < arena + 0x48000 and rsp % 8 == 0,
                "Invalid restored kernel context",
            )
            if slot == 1:
                need(quiet and not armed, "Kernel continuation before timer drain")
            projected.append(line.replace("event=budget ", "event=bounds "))
            continue
        if line == "AURORA_UEFI_SERVICE_BUDGET_OK":
            need(
                mode in SUCCESS
                and not armed
                and service_runs == 2
                and not success_marker
                and position
                and records[position - 1] == "AURORA_UEFI_IPC_OK",
                "Premature budget success",
            )
            success_marker = True
            continue
        if line.startswith("AURORA_UEFI_TIMER_"):
            raise ValueError("Unknown timer record")
        if line.startswith("AURORA_UEFI_RUNTIME_ROOT_PROBE:"):
            need(
                mode == "budget-root"
                and last_event
                and last_event[0] == 64
                and position
                and re.fullmatch(EVENT, records[position - 1]),
                "Root probe outside timer event",
            )
        if line.startswith("AURORA_UEFI_RUNTIME_FAIL:"):
            need(position == len(records) - 1, "Execution after rejection")
        projected.append(line)
    need(not pending_context, "Missing final context receipt")
    if mode in SUCCESS:
        need(success_marker and not armed, "Missing budget completion")
        ipc.validate_protocol_projection(status, prefix + "\n".join(projected) + "\n", "ipc-fault", base_images)
    else:
        need(not success_marker and service_runs == 1 and armed, "Unexpected failure lifecycle")
        wanted = ipc.expected("ipc-fault", base_images, arena)
        # The successful request and delivery must match independently validated IPC phases.
        expected_prefix = wanted[:7]
        need(len(projected) >= 8 and len(projected) <= 10, "Extra negative lifecycle records")
        for line, pattern in zip(projected[:7], expected_prefix):
            need(re.fullmatch(pattern, line), "Wrong request before denied timer operation")
        tail = projected[7:]
        if mode in POLICY_MODES:
            need(
                used == 0 and last_event is not None and last_event[:2] == (64, 0) and last_event[3] == 3,
                "Policy rejection lacks uncharged real user interrupt",
            )
            need(tail == ["AURORA_UEFI_RUNTIME_FAIL: Aurora budget transition"], "Wrong policy rejection")
        elif mode in ("budget-root", "budget-epoch", "budget-forged"):
            need(used == 0 and last_event is not None, "Unexpected charged rejected interrupt")
            if mode == "budget-root":
                need(
                    tail
                    == [
                        f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}",
                        "AURORA_UEFI_RUNTIME_FAIL: timer active origin",
                    ],
                    "Wrong root rejection",
                )
            else:
                need(tail == ["AURORA_UEFI_RUNTIME_FAIL: timer active origin"], "Wrong active interrupt rejection")
        else:
            need(mode in ("budget-mmio", "budget-softint", "budget-fpu") and len(tail) == 2, "Unexpected timer failure")
            fault = re.fullmatch(EVENT, tail[0])
            need(fault is not None, "Missing exact denied user event")
            v, e, pc, cpl, r, f, cr2 = map(int, fault.groups())
            need(
                (v, e) == {"budget-mmio": (14, 5), "budget-softint": (13, 514), "budget-fpu": (7, 0)}[mode]
                and pc == meta["images"]["bounds"]["probe_pc"]
                and cpl == 3
                and r == service
                and f == arena + 0x88000 - 176
                and cr2 == (APIC if mode == "budget-mmio" else 0),
                "Wrong denied user instruction",
            )
            need(tail[1] == "AURORA_UEFI_RUNTIME_FAIL: timer terminal context", "Wrong failure reason")


def self_test():
    arena = 0x1000000
    kernel = arena + 0x11000
    root = arena + 0xA0000
    frame = arena + 0x88000 - 176
    prefix = (
        f"AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEF"
        f"I_PAYLOAD_ENTRY\nAURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes"
        f"=1048576 descriptors=111\nAURORA_UEFI_PROTECTION_OK: root="
        f"{kernel} stack={arena + 0x47E00}\nAURORA_ACPI_CPU: id=0 uid=0 "
        f"enabled=1 capable=0 x2=0\nAURORA_ACPI_TOPOLOGY: records=1 enab"
        f"led=1 capable=0 lapic=4276092928\nAURORA_ACPI_WINDOW_CLOSED: c"
        f"opies=14\nAURORA_PCI_APERTURE: base=3758096384 bytes=268435456"
        f" segment=0 first=0 last=255\nAURORA_PCI_FUNCTION: segment=0 bu"
        f"s=0 device=0 function=0 vendor=32902 product=10688 class=6 sub"
        f"class=0 interface=0 header=0 command=7 secondary=0 subordinate"
        f"=0\nAURORA_PCI_INVENTORY: functions=1 buses=1\nAURORA_PCI_WIND"
        f"OW_CLOSED: reads=39\n"
    )
    rejected = 0
    for mode in MODES:
        images = {}
        for index, name in enumerate(("clean", "bounds")):
            base = BASE + index * 16384
            images[name] = dict(
                entry=base,
                size=512,
                return_pc=base + 60,
                bounds_pc=base + 400,
                overflow_pc=base + 404,
                division_zero_pc=base + 408,
                shift_count_pc=base + 412,
                probe_offset=0,
                probe_pc=base + 50 if index == 1 and mode in ("budget-mmio", "budget-softint", "budget-fpu") else 0,
                compiled_begin=base + 80,
                compiled_end=base + 300,
                context_begin=base + 20 if index == 1 and mode == "budget-context" else 0,
                context_end=base + 26 if index == 1 and mode == "budget-context" else 0,
            )
        meta = dict(
            images=images,
            kernel=None
            if mode == "budget-noapic"
            else dict(drain_begin=100, drain_end=104, text_end=4096, forged_pc=200 if mode in FIXTURE_MODES else 0),
        )
        simple = {
            name: {
                key: value
                for key, value in image.items()
                if key not in ("compiled_begin", "compiled_end", "context_begin", "context_end")
            }
            for name, image in images.items()
        }
        for image in simple.values():
            image["probe_pc"] = 0
        source = [line.replace(r"(\d+)", str(arena + 0x47C00)) for line in ipc.expected("ipc-fault", simple, arena)]
        rows = []
        run = 0
        ticks = 0
        contexts = 0
        phase = 0

        def event(v, pc, cpl=3, error=0, cr2=0):
            return (
                f"AURORA_UEFI_DOMAIN_EVENT: vector={v} error={error} pc={pc} cpl"
                f"={cpl} root={root if cpl == 3 or mode == 'budget-forged' else kernel}"
                f" frame={frame if cpl == 3 else arena + 0x47C00} cr2={cr2}"
            )

        def tick(pc, n, budget, context=False):
            rows.extend(
                [
                    event(64, pc),
                    f"AURORA_UEFI_TIMER_TICK: epoch={run} used={n} remaining={budget - n}"
                    f" pc={pc} flags={0x602 if context else 0x202}",
                ]
            )
            if context:
                rows.append(f"AURORA_UEFI_TIMER_CONTEXT: epoch={run} tick={n} registers=15 df=1")

        if mode in EARLY:
            rows = [
                "AURORA_UEFI_RUNTIME_FAIL: "
                + ("timer mapping tree" if mode == "budget-alias" else "timer aperture admission")
            ]
        else:
            rows = [f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={APIC} id=0 root={kernel}"]
            for line in source:
                if line.startswith("AURORA_UEFI_IPC_ENTER: slot=1 "):
                    run += 1
                    phase = 4 if run == 1 and mode == "budget-fault" else 5 if run == 1 else 1
                    ticks = 0
                    contexts = 0
                    rows.append(line.replace("phase=4 ", f"phase={phase} "))
                    rows.append(f"AURORA_UEFI_TIMER_ARM: epoch={run} budget={3 if phase == 5 else 128} root={root}")
                    if mode not in SUCCESS:
                        if mode in ("budget-root", "budget-epoch", "budget-forged") + POLICY_MODES:
                            rows.append(
                                event(
                                    64,
                                    arena + 0x22000 + 200
                                    if mode == "budget-forged"
                                    else images["bounds"]["compiled_begin"],
                                    0 if mode == "budget-forged" else 3,
                                )
                            )
                            if mode == "budget-root":
                                rows.append(f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}")
                            rows.append(
                                "AURORA_UEFI_RUNTIME_FAIL: "
                                + ("Aurora budget transition" if mode in POLICY_MODES else "timer active origin")
                            )
                        else:
                            tick(images["bounds"]["entry"], 1, 3)
                            v, e = {"budget-mmio": (14, 5), "budget-softint": (13, 514), "budget-fpu": (7, 0)}[mode]
                            rows.append(
                                event(
                                    v, images["bounds"]["probe_pc"], error=e, cr2=APIC if mode == "budget-mmio" else 0
                                )
                            )
                            rows.append("AURORA_UEFI_RUNTIME_FAIL: timer terminal context")
                        break
                    if phase == 5:
                        for n in range(1, 4):
                            tick(images["bounds"]["compiled_begin"], n, 3)
                        ticks = 3
                    elif phase == 1:
                        if mode == "budget-context":
                            tick(images["bounds"]["context_begin"], 1, 128, True)
                            contexts = 1
                            ticks = 1
                        ticks += 1
                        tick(images["bounds"]["compiled_begin"], ticks, 128)
                    continue
                if line.startswith("AURORA_UEFI_DOMAIN_EVENT: vector=6 ") and run == 1 and phase == 5:
                    continue
                if line.startswith("AURORA_UEFI_IPC_RESTORE: slot=1 "):
                    drains = 0
                    if mode == "budget-pending" and run == 2:
                        rows.extend(
                            [
                                event(64, arena + 0x22000 + 102, 0),
                                f"AURORA_UEFI_TIMER_DRAIN: epoch=2 root={kernel} ss=16",
                            ]
                        )
                        drains = 1
                    rows.append(
                        f"AURORA_UEFI_TIMER_QUIET: epoch={run} ticks={ticks} drains="
                        f"{drains} compiled={ticks - contexts} context={contexts} root="
                        f"{kernel}"
                    )
                    rows.append(line.replace("event=bounds ", "event=budget ") if phase == 5 else line)
                    continue
                rows.append(line)
                if (
                    mode == "budget-pending"
                    and run == 2
                    and line.startswith("AURORA_UEFI_DOMAIN_EVENT: vector=129 ")
                    and f"pc={images['bounds']['return_pc']} " in line
                ):
                    rows.append("AURORA_UEFI_TIMER_PENDING: epoch=2")
                if line == "AURORA_UEFI_IPC_OK":
                    rows.append("AURORA_UEFI_SERVICE_BUDGET_OK")
        prefix_case = prefix
        if mode == "budget-smp":
            prefix_case = prefix.replace(
                "AURORA_ACPI_TOPOLOGY: records=1 enabled=1",
                "AURORA_ACPI_CPU: id=1 uid=1 enabled=1 capable=0 x2=0\nAURORA_ACPI_TOPOLOGY: records=2 enabled=2",
            )
        prefix_case += "AURORA_FIXTURE_READY\n" if mode in FIXTURE_MODES else ""
        text = prefix_case + "\n".join(rows) + "\n"
        status = 33 if mode in SUCCESS else 35
        validate(status, text, mode, meta)
        wrong_sites = copy.deepcopy(meta)
        wrong_sites["kernel"] = (
            dict(drain_begin=100, drain_end=104, text_end=4096, forged_pc=0) if mode == "budget-noapic" else None
        )
        try:
            validate(status, text, mode, wrong_sites)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Wrong timer-site presence accepted: " + mode)
        failures = [(0, text), (status, text + ipc.SUFFIX), (status, text + "AURORA_UEFI_SERVICE_BUDGET_OK\n")]
        for line in text.splitlines():
            failures.extend(
                ((status, text.replace(line + "\n", "", 1)), (status, text.replace(line + "\n", (line + "\n") * 2, 1)))
            )
        for i, line in enumerate(rows):
            for field in re.findall(r"([a-z]+)=\d+", line):
                failures.append(
                    (status, text.replace(line, re.sub(rf"{field}=\d+", f"{field}=9999999999999999999", line), 1))
                )
            if i + 1 < len(rows):
                swapped = rows.copy()
                swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
                failures.append((status, prefix_case + "\n".join(swapped) + "\n"))
        for path, key, value in [
            ("bounds", "return_pc", 0),
            ("bounds", "compiled_begin", 0),
            ("bounds", "compiled_end", BASE + 32768),
            ("bounds", "size", 8192),
            ("bounds", "context_begin", BASE),
            ("clean", "entry", True),
        ]:
            altered = copy.deepcopy(meta)
            altered["images"][path][key] = value
            try:
                validate(status, text, mode, altered)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError(f"Bad budget metadata accepted: {mode} {key}")
        if mode == "budget-pending":
            for selector in (0, 8, 24, 35):
                failures.append((status, text.replace(" ss=16", " ss=" + str(selector))))
        for code, bad in failures:
            try:
                validate(code, bad, mode, meta)
            except ValueError:
                rejected += 1
            else:
                import difflib

                raise RuntimeError(
                    f"Bad budget receipt accepted: {mode} "
                    + repr(list(difflib.unified_diff(text.splitlines(), bad.splitlines())))
                )
    print(f"PASS: service budget transcripts {len(MODES)} positive and {rejected} negative cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        try:
            validate(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        except (ValueError, IndexError, KeyError, TypeError) as error:
            raise SystemExit(f"FAIL: {error}")
        print("PASS: service budget exact interrupt/IPC transcript")

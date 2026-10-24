#!/usr/bin/env python3
"""Strict APIC/context authority and scheduler transcript gates; no optimized-away asserts."""

from pathlib import Path
import json
import re
import sys


def need(value, reason):
    if not value:
        raise ValueError(reason)


def validate(status, text, mode, metadata):
    need("AURORA_USER_OK:" in text, "Missing earlier protected-user gate")
    need("AURORA_EXCEPTION_OK:" in text and "AURORA_PAGES_OK:" in text, "Missing foundations")
    if mode != "--schedule":
        need(
            status == 35 and text.count("AURORA_BOOT_FAIL") == 1 and "AURORA_BOOT_OK" not in text,
            "Adversarial mode did not fail closed",
        )
        need("AURORA_SCHEDULE_OK:" not in text, "Failed scheduler claimed success")
        if mode in ("--schedule-no-apic", "--schedule-smp"):
            need("AURORA_APIC_UNSUPPORTED" in text and "AURORA_APIC_OK:" not in text, "Absent APIC accepted")
            need("AURORA_SCHEDULE_ENTER:" not in text, "Task started without APIC")
            return
        need(
            "AURORA_APIC_OK:" in text and "AURORA_TIMER_DRAIN_OK:" in text and "AURORA_SCHEDULE_ENTER: task=0" in text,
            "Missing authorized timer setup",
        )
        expected = {
            "--schedule-forged": (64, 0, 0),
            "--schedule-context": (64, 0, 3),
            "--schedule-root": (64, 0, 3),
            "--schedule-softint": (13, 514, 3),
            "--schedule-fpu": (7, 0, 3),
            "--schedule-mmio": (14, 5, 3),
        }[mode]
        fault = re.search(r"AURORA_EXCEPTION_FATAL: (\d+) error=(\d+) rip=(\d+)", text)
        context = re.search(r"AURORA_EXCEPTION_CONTEXT: cpl=(\d+) frame=(\d+) cr2=(\d+)", text)
        need(fault and context, "Missing fatal context")
        need((int(fault[1]), int(fault[2]), int(context[1])) == expected, "Wrong injected fault")
        need(
            "AURORA_SCHEDULE_RETIRED:" not in text and "AURORA_SCHEDULE_TICK:" not in text[fault.end() :],
            "Rejected authority changed scheduler lifecycle",
        )
        if mode in ("--schedule-forged", "--schedule-context", "--schedule-root"):
            need("AURORA_SCHEDULE_TICK:" not in text, "Rejected timer was charged")
        if mode == "--schedule-mmio":
            need(int(context[3]) == 0xFEE00000, "Wrong MMIO denied address")
        if expected[2] == 3:
            need(0x82000 <= int(context[2]) <= 0x86000 - 176, "Wrong TSS stack")
        return
    need(
        status == 33 and text.count("AURORA_BOOT_OK") == 1 and "AURORA_BOOT_FAIL" not in text,
        "Normal scheduling boot failed",
    )
    for marker in (
        "AURORA_APIC_OK:",
        "AURORA_TIMER_DRAIN_OK:",
        "AURORA_TIMER_RETIRE_OK:",
        "AURORA_CONTEXT_OK:",
        "AURORA_SCHEDULE_REUSE_OK:",
        "AURORA_SCHEDULE_OK:",
        "Aurora language result: 42",
    ):
        need(text.count(marker) == 1, f"Missing/duplicate {marker}")
    roots = {}
    kernel = None
    active = None
    event = None
    restored = None
    ticks = [0, 0, 0, 0]
    retired = set()
    terminals = {}
    frames = 0
    enters = []
    expected_completion = {0: "RESULT42", 1: "CANCEL", 2: "BOUNDS", 3: "RESULT42"}
    finished = set()
    slice_frame = False
    slice_terminal = False
    for line in text.splitlines():
        timer = re.fullmatch(r"AURORA_TIMER_FRAME: task=(\d+) pc=(\d+) flags=(\d+) frame=(\d+) isr=1 eoi=1", line)
        if timer:
            task, pc, flags, frame = map(int, timer.groups())
            need(
                active == task and event is None and not slice_frame and not slice_terminal,
                "Duplicate/misordered timer frame",
            )
            slice_frame = True
            image = metadata[str(task % 3)]
            need(image["base"] <= pc < image["base"] + image["size"], "Timer RIP outside own image")
            need(flags & 0x202 == 0x202 and flags & ~0x10ED7 == 0, "Invalid saved flags")
            need(0x82000 <= frame <= 0x86000 - 176 and frame % 8 == 0, "Invalid timer TSS frame")
            frames += 1
        terminal = re.fullmatch(r"AURORA_SCHEDULE_TERMINAL: task=(\d+) vector=(\d+) pc=(\d+) value=(\d+)", line)
        if terminal:
            task, vector, pc, value = map(int, terminal.groups())
            need(
                active == task and task in (0, 2, 3) and not slice_terminal and not slice_frame,
                "Unauthorized terminal task",
            )
            slice_terminal = True
            need(task not in terminals, "Replayed terminal authority")
            image = metadata[str(task % 3)]
            need(
                (vector, pc) == ((129, image["return"]) if task in (0, 3) else (6, image["bounds"])),
                "Wrong linked terminal site",
            )
            if task in (0, 3):
                need(value == 42, "Wrong compiled result")
            terminals[task] = True
        match = re.fullmatch(
            r"AURORA_SCHEDULE_(ENTER|TICK|EVENT|RESTORE|CANCEL|RESULT42|BOUNDS|RETIRED): task=(\d+) root=(\d+)", line
        )
        if not match:
            continue
        kind, task, root = match[1], int(match[2]), int(match[3])
        need(task in (0, 1, 2, 3) and root % 4096 == 0 and 0 < root < 0x70000, "Invalid domain/root")
        if kind == "ENTER":
            need(active is None and task not in retired, "Nested/stale task resume")
            need(task not in roots or roots[task] == root, "Domain root changed")
            need(task != 3 or retired == {0, 1, 2}, "Restart preceded old-domain cleanup")
            roots[task] = root
            active = task
            event = None
            restored = None
            slice_frame = False
            slice_terminal = False
            enters.append(task)
        elif kind in ("TICK", "EVENT"):
            need(active == task and roots[task] == root and event is None, "Event lacks active CR3 authority")
            event = kind
            if kind == "TICK":
                need(slice_frame and not slice_terminal, "Tick missing its unique captured frame")
                ticks[task] += 1
            else:
                need(slice_terminal and not slice_frame and task in terminals, "Terminal metadata missing/mixed")
        elif kind == "RESTORE":
            need(active == task and event is not None and root not in roots.values(), "Bad root restore/order")
            need(kernel is None or kernel == root, "Kernel root changed")
            kernel = root
            active = None
            restored = task
        elif kind == "RETIRED":
            need(
                active is None and task in finished and root == kernel and task not in retired, "Bad teardown authority"
            )
            retired.add(task)
        else:
            need(
                active is None and restored == task and root == kernel and kind == expected_completion[task],
                "Invalid task completion",
            )
            need(event == ("TICK" if kind == "CANCEL" else "EVENT"), "Completion has wrong interruption kind")
            need(kind != "CANCEL" or ticks[task] == 24, "Premature budget cancellation")
            need(task not in finished, "Duplicate completion")
            finished.add(task)
    need(
        active is None and retired == {0, 1, 2, 3} and len(set(roots.values())) == 3 and roots[3] == roots[0],
        "Incomplete lifecycle/root isolation",
    )
    need(
        ticks[0] >= 2 and ticks[3] >= 2 and ticks[1] == 24 and frames == sum(ticks),
        "Missing preemption/budget evidence",
    )
    need(enters[:3] == [0, 1, 2], "Initial round-robin sequence missing")
    probe = re.search(r"AURORA_CONTEXT_OK: all15 GPRs and DF resumed; probe_ticks=(\d+)", text)
    need(probe and int(probe[1]) >= 2, "No resumed integer/DF proof")


if __name__ == "__main__":
    try:
        validate(
            int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
        )
    except ValueError as error:
        sys.exit(f"FAIL: {error}")

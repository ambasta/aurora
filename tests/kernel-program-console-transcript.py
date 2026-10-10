#!/usr/bin/env python3
"""Guest-free positive and refusal controls for the protected console PTY oracle."""

from pathlib import Path
import importlib.util

path = Path(__file__).with_name("kernel-program-console-pty.py")
spec = importlib.util.spec_from_file_location("console_pty", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
images = dict(
    clean=dict(entry=1000, size=100, return_pc=1010, bounds_pc=1090, probe_pc=1080),
    bounds=dict(entry=2000, size=100, return_pc=2010, bounds_pc=2090, probe_pc=0),
)
arena = 0x2000000
kernel_root = arena + 0x11000
timer = dict(drain_begin=100, drain_end=104)


def fixture(mode, note=False, value="A", missing=False):
    lines = [
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena}",
        f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual=18446620928407240704 id=0 root={kernel_root}",
        "AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper",
    ]
    epoch = 0
    expected = []
    failure = mode not in ("program-console", "program-pending")
    phases = ["request", "service", "completion"]
    for command in range(2 if failure else 1):
        failing = failure and command == 0
        length = 8 if note else 2 if failing else len(value)
        rounds = (len(value) + 1 if not missing else 1) if note else len(value)
        kind = "note" if note else "upper"
        lines.append(f"AURORA_PROGRAM_COMMAND_BEGIN: grant={1 + command * 8} length={length} domains=2 kind={kind}")
        stop = phases.index(mode.split("-")[1]) if failing else 2
        sequence = phases + phases[: stop + 1] if failing else phases * rounds
        for offset, phase in enumerate(sequence):
            epoch += 1
            role = "service" if phase == "service" else "client"
            transaction = 0 if phase == "request" else 3 + command * 8 + offset // 3
            source = {"request": 12, "service": 11, "completion": 13}[phase] if note else phases.index(phase)
            terminal = failing and offset + 1 == len(sequence)
            if terminal:
                source = (
                    {"request": 6, "service": 5, "completion": 7}
                    if mode.endswith("budget")
                    else {"request": 8, "service": 4, "completion": 10}
                )[phase]
            root = arena + (0xA0000 if phase == "service" else 0x90000)
            lines.append(
                f"AURORA_UEFI_USER_RUN: epoch={epoch} role={role} phase={phase} "
                f"client=0 transaction={transaction} source={source} root={root}"
            )
            image = images["bounds" if phase == "service" else "clean"]
            if terminal and mode.endswith("fault"):
                lines.append(
                    f"AURORA_UEFI_DOMAIN_EVENT: vector=6 error=0 pc={image['bounds_pc']} cpl=3 root={root} "
                    f"frame={arena + 0x88000 - 176} cr2=0"
                )
            elif terminal:
                lines.append(
                    f"AURORA_UEFI_DOMAIN_EVENT: vector=64 error=0 pc={image['entry'] + 30} cpl=3 root={root} "
                    f"frame={arena + 0x88000 - 176} cr2=0"
                )
                lines.append(f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used=3 remaining=0 pc=1030")
                lines.append(f"AURORA_UEFI_TIMER_QUIET: epoch={epoch} ticks=3 drains=0 compiled=3 root=42")
            else:
                lines.append(
                    f"AURORA_UEFI_DOMAIN_EVENT: vector=129 error=0 pc={image['return_pc']} cpl=3 root={root} "
                    f"frame={arena + 0x88000 - 176} cr2=0"
                )
        if mode == "program-pending":
            lines += [
                "AURORA_UEFI_TIMER_PENDING: epoch=3",
                f"AURORA_UEFI_DOMAIN_EVENT: vector=64 error=0 pc={arena + 0x22000 + 102} cpl=0 root={kernel_root} "
                f"frame={arena + 0x47000} cr2=0",
                f"AURORA_UEFI_TIMER_DRAIN: epoch=3 root={kernel_root} ss=16",
            ]
        lines.append(f"AURORA_PROGRAM_COMMAND_END: success={0 if failing else 1} used=0 epoch={epoch}")
        if failing:
            lines.append("Program stopped: checked fault or budget exhausted; output discarded.")
        else:
            if note and missing:
                lines.append("Note is missing.")
            else:
                lines.append("output> " + value)
                expected.append(value)
    lines += ["AURORA_CONSOLE_EXIT", "AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0"]
    return "\r\n".join(lines) + "\r\n", expected, 2 if failure else 1


checks = 0
for mode in module.admission.MODES:
    if mode in ("program-owner", "program-ordinal", "program-unknown", "program-transaction"):
        continue
    text, expected, commands = fixture(mode)
    module.validate(text, mode, expected, commands, images, timer)
    checks += 1
    doubled = text.replace(f"id=0 root={kernel_root}\r\n", f"id=0 root={kernel_root}\r\r\n")
    module.validate(doubled, mode, expected, commands, images, timer)
    checks += 1
    changes = [
        text.replace(f"id=0 root={kernel_root}\r\n", f"id=0 root={kernel_root}\r\r\r\n"),
        text.replace("domains=2", "domains=3", 1),
        text.replace("used=0 epoch=", "used=1 epoch=", 1),
        text.replace("output> A", "output> B", 1),
        text.replace("cpl=3", "cpl=0", 1),
        text.replace("transaction=0 source=0", "transaction=3 source=0", 1),
        text.replace("AURORA_CONSOLE_EXIT", ""),
        text + "output> A\r\n",
        text.replace("phase=service", "phase=request", 1),
        text.replace("epoch=2 role=", "epoch=1 role=", 1),
        text.replace("vector=129 error=0 pc=1010", "vector=129 error=0 pc=1011", 1),
    ]
    if mode.endswith(("fault", "budget")):
        pieces = text.split("AURORA_UEFI_USER_RUN:")
        changes.append(pieces[0] + "AURORA_UEFI_USER_RUN:" + "AURORA_UEFI_USER_RUN:".join(pieces[4:]))
    if mode.endswith("fault"):
        changes.append(text.replace("pc=1090", "pc=1091").replace("pc=2090", "pc=2091"))
    if mode.endswith("budget"):
        changes.append(text.replace("used=3 remaining=0", "used=2 remaining=1"))
    if mode == "program-pending":
        changes += [
            text.replace("AURORA_UEFI_TIMER_DRAIN:", "MISSING_DRAIN:"),
            text.replace("AURORA_UEFI_TIMER_DRAIN: epoch=3", "AURORA_UEFI_TIMER_DRAIN: epoch=4"),
            text.replace(f"pc={arena + 0x22000 + 102}", f"pc={arena + 0x22000 + 105}"),
            text.replace(f"cpl=0 root={kernel_root}", f"cpl=0 root={kernel_root + 4096}"),
        ]
    for invalid in changes:
        if invalid == text:
            continue
        try:
            module.validate(invalid, mode, expected, commands, images, timer)
        except ValueError:
            checks += 1
        else:
            raise SystemExit("FAIL: accepted changed transcript in " + mode)
# Actual note bytes and an extra EOF round, including missing/empty values.
for mode, value, missing in [
    ("program-console", "", True),
    ("program-console", "", False),
    ("program-console", "changed", False),
    ("program-console", "z" * 53, False),
] + [
    ("program-" + phase + "-" + outcome, "AB", False)
    for phase in ("request", "service", "completion")
    for outcome in ("fault", "budget")
]:
    text, expected, commands = fixture(mode, note=True, value=value, missing=missing)
    reads = {index: None if missing else value for index in range(commands)}
    module.validate(text, mode, expected, commands, images, timer, reads)
    checks += 1
    for changed, plan in (
        (text.replace("source=12", "source=0", 1), reads),
        (text.replace("kind=note", "kind=upper", 1), reads),
        (text, {}),
        (text, {**reads, commands - 1: (value or "") + "extra"}),
        (text.replace("phase=completion", "phase=service", 1), reads),
        ("output> partial\r\n" + text, reads),
    ):
        try:
            module.validate(changed, mode, expected, commands, images, timer, plan)
        except ValueError:
            checks += 1
        else:
            raise SystemExit("FAIL: note lifecycle/output/EOF oracle accepted drift")

# Saved results use the unchanged upper protocol and acknowledge storage only
# after the whole command retires. Readback is exercised by the real PTY runner.
for mode in ["program-console"] + [
    "program-" + phase + "-" + outcome
    for phase in ("request", "service", "completion")
    for outcome in ("fault", "budget")
]:
    text, _, commands = fixture(mode)
    text = text.replace("kind=upper", "kind=upper-note").replace("output> A", "Note saved.")
    saves = {index: "AA" if index == 0 and commands == 2 else "A" for index in range(commands)}
    module.validate(text, mode, [], commands, images, timer, {}, saves)
    checks += 1
    for changed, plan in (
        (text.replace("kind=upper-note", "kind=upper", 1), saves),
        (text, {}),
        (text, {**saves, commands - 1: "too long"}),
        (text.replace("used=0 epoch=", "used=1 epoch=", 1), saves),
        (text.replace("Note saved.", "output> A", 1), saves),
        (text.replace("Note saved.", "", 1), saves),
        (text.replace("Note saved.", "Note saved.\r\nNote saved.", 1), saves),
        (text.replace("AURORA_PROGRAM_COMMAND_END:", "Note saved.\r\nAURORA_PROGRAM_COMMAND_END:", 1), saves),
        (text.replace("phase=completion", "phase=service", 1), saves),
        (text + "output> partial\r\n", saves),
    ):
        try:
            module.validate(changed, mode, [], commands, images, timer, {}, plan)
        except ValueError:
            checks += 1
        else:
            raise SystemExit("FAIL: saved-output lifecycle oracle accepted drift")

# Maximum saved output retains all rounds; empty saves retire with zero rounds.
text, _, _ = fixture("program-console", value="A" * 53)
text = text.replace("kind=upper", "kind=upper-note").replace("output> " + "A" * 53, "Note saved.")
empty = (
    "AURORA_PROGRAM_COMMAND_BEGIN: grant=9 length=0 domains=2 kind=upper-note\r\n"
    "AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=159\r\nNote saved.\r\n"
)
text = text.replace("AURORA_CONSOLE_EXIT", empty + "AURORA_CONSOLE_EXIT")
module.validate(text, "program-console", [], 2, images, timer, {}, {0: "A" * 53, 1: ""})
checks += 1

# `upper note` when missing uses the existing authenticated missing read.
text, expected, commands = fixture("program-console", note=True, value="", missing=True)
module.validate(text.replace("length=8", "length=10"), "program-console", expected, commands, images, timer, {0: None})
checks += 1

for mode, reason in module.FAILSTOP_REASONS.items():
    image = images["bounds" if mode == "program-transaction" else "clean"]
    vector = 6 if mode == "program-unknown" else 129
    pc = image["probe_pc"] if vector == 6 else image["return_pc"]
    text = (
        "AURORA_PROGRAM_COMMAND_BEGIN: grant=1 length=1 domains=2 kind=upper\r\n"
        f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3 root=42\r\n"
        "AURORA_UEFI_RUNTIME_FAIL: " + reason + "\r\n"
    )
    module.validate_failstop(text, mode, 35, images)
    checks += 1
    for changed, status in [
        (text, 33),
        (text + "output> A\r\n", 35),
        (text + "aurora> ", 35),
        (text.replace("cpl=3", "cpl=0"), 35),
        (text.replace(f"pc={pc}", f"pc={pc + 1}"), 35),
        (text + "AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=1\r\n", 35),
    ]:
        try:
            module.validate_failstop(changed, mode, status, images)
        except ValueError:
            checks += 1
        else:
            raise SystemExit("FAIL: malformed authority oracle accepted output/recovery/wrong site")
print(f"PASS: {checks} protected-console transcript positive/refusal controls; no guest executed")

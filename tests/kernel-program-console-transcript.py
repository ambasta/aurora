#!/usr/bin/env python3
"""Guest-free positive and refusal controls for the protected console PTY oracle."""

from pathlib import Path
import importlib.util
import re

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


def fixture(mode, note=False, value="A", missing=False, file_command=None):
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
        reading = note or file_command is not None
        saving_file = file_command is not None and file_command.startswith("upper ") and not missing
        length = len(file_command) if file_command is not None else 8 if note else 2 if failing else len(value)
        rounds = (len(value) + 1 if not missing else 1) if reading else len(value)
        kind = "upper-file" if saving_file else "file" if file_command is not None else "note" if note else "upper"
        lines.append(f"AURORA_PROGRAM_COMMAND_BEGIN: grant={1 + command * 8} length={length} domains=2 kind={kind}")
        stop = phases.index(mode.split("-")[1]) if failing else 2
        sequence = phases + phases[: stop + 1] if failing else phases * rounds
        for offset, phase in enumerate(sequence):
            epoch += 1
            role = "service" if phase == "service" else "client"
            transaction = 0 if phase == "request" else 3 + command * 8 + offset // 3
            source = (
                {"request": 12, "service": 11, "completion": 14 if saving_file else 13}[phase]
                if reading
                else phases.index(phase)
            )
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
                f"AURORA_UEFI_TIMER_PENDING: epoch={epoch}",
                f"AURORA_UEFI_DOMAIN_EVENT: vector=64 error=0 pc={arena + 0x22000 + 102} cpl=0 root={kernel_root} "
                f"frame={arena + 0x47000} cr2=0",
                f"AURORA_UEFI_TIMER_DRAIN: epoch={epoch} root={kernel_root} ss=16",
            ]
        lines.append(f"AURORA_PROGRAM_COMMAND_END: success={0 if failing else 1} used=0 epoch={epoch}")
        if failing:
            lines.append("Program stopped: checked fault or budget exhausted; output discarded.")
        else:
            if reading and missing:
                lines.append("File is missing." if file_command is not None else "Note is missing.")
            elif saving_file:
                lines.append("File saved.")
            else:
                lines.append("output> " + value)
                expected.append(value)
    lines += ["AURORA_CONSOLE_EXIT", "AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0"]
    return "\r\n".join(lines) + "\r\n", expected, 2 if failure else 1


checks = 0
for mode in module.admission.MODES:
    if mode.startswith("program-file-call") or mode in (
        "program-owner",
        "program-ordinal",
        "program-unknown",
        "program-transaction",
    ):
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

# Named reads and replacements retain the original command length and one EOF
# round. A missing upper selection uses the ordinary authenticated read protocol.
for mode, command, value, missing in (
    [
        ("program-console", verb + " chosen", value, missing)
        for verb in ("cat", "upper")
        for value, missing in (
            ("", True),
            ("", False),
            ("Ab !", False),
            ("Z" * 49, False),
            ("File saved.", False),
            ("File is missing.", False),
            ("Note is missing.", False),
        )
    ]
    + [("program-pending", "upper chosen", "AB", False)]
    + [
        ("program-" + phase + "-" + outcome, "upper chosen", "AB", False)
        for phase in ("request", "service", "completion")
        for outcome in ("fault", "budget")
    ]
):
    text, expected, commands = fixture(mode, value=value, missing=missing, file_command=command)
    files = {index: {"command": command, "value": None if missing else value} for index in range(commands)}
    module.validate(text, mode, expected, commands, images, timer, expected_files=files)
    checks += 1
    saving = command.startswith("upper ") and not missing
    kind = "upper-file" if saving else "file"
    marker = "File saved." if saving else "File is missing." if missing else "output> " + value
    changed_plan = {**files, commands - 1: {"command": command, "value": value + "extra"}}
    changes = [
        (text.replace("source=12", "source=0", 1), files),
        (text.replace("source=11", "source=1", 1), files),
        (text.replace("source=14" if saving else "source=13", "source=13" if saving else "source=14", 1), files),
        (text.replace("kind=" + kind, "kind=upper-note", 1), files),
        (text.replace("kind=" + kind, "kind=file" if saving else "kind=upper-file", 1), files),
        (text.replace(f"length={len(command)}", f"length={len(command) + 1}", 1), files),
        (text, {}),
        (text, changed_plan),
        (text, {**files, commands: {"command": command, "value": value}}),
        (text, {**files, commands - 1: {"command": "cat note", "value": value}}),
        (text, {**files, commands - 1: {"command": "cat ../x", "value": value}}),
        (text, {**files, commands - 1: {"command": "cat toolongnm", "value": value}}),
        (text, {**files, commands - 1: {"command": command, "value": "x" * 50}}),
        (text, {**files, commands - 1: {"command": command, "value": "bad\x01"}}),
        (text.replace(marker + "\r\n", "", 1), files),
        (text.replace(marker + "\r\n", marker + "\r\n" + marker + "\r\n", 1), files),
        (text.replace("AURORA_PROGRAM_COMMAND_END:", marker + "\r\nAURORA_PROGRAM_COMMAND_END:", 1), files),
        (text + "File saved.\r\n", files),
        (text + "File is missing.\r\n", files),
        ("output> partial\r\n" + text, files),
    ]
    if saving:
        changes += [
            (text.replace("File saved.", "Note saved.", 1), files),
            (text.replace("File saved.", "output> " + value, 1), files),
        ]
    if missing:
        changes += [
            (text.replace("File is missing.", "output> ", 1), files),
            (text.replace("File is missing.", "File saved.", 1), files),
        ]
    if mode == "program-pending":
        pending = re.search(r"AURORA_UEFI_TIMER_PENDING:[^\r\n]*\r\n", text)[0]
        changes.append((text.replace(pending, "") + pending, files))
    if mode == "program-console":
        runs = list(re.finditer(r"AURORA_UEFI_USER_RUN:[^\r\n]*\r\nAURORA_UEFI_DOMAIN_EVENT:[^\r\n]*\r\n", text))
        final_round = text[runs[-3].start() : runs[-1].end()]
        extra_round = re.sub(r"epoch=(\d+)", lambda match: "epoch=" + str(int(match[1]) + 3), final_round)
        extra_round = re.sub(
            r"transaction=(\d+)",
            lambda match: "transaction=" + str(int(match[1]) + int(match[1] != "0")),
            extra_round,
        )
        extra_eof = text[: runs[-1].end()] + extra_round + text[runs[-1].end() :]
        extra_eof = re.sub(
            r"(AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=)(\d+)",
            lambda match: match[1] + str(int(match[2]) + 3),
            extra_eof,
        )
        changes += [
            (text[: runs[-3].start()] + text[runs[-1].end() :], files),
            (extra_eof, files),
        ]
    for control, (changed, plan) in enumerate(changes):
        need_changed = changed != text or plan != files
        if not need_changed:
            raise SystemExit("FAIL: named-file hostile control did not change its fixture")
        try:
            module.validate(changed, mode, expected, commands, images, timer, expected_files=plan)
        except ValueError:
            checks += 1
        else:
            raise SystemExit(
                f"FAIL: named-file lifecycle/phase/EOF/output oracle accepted drift: {mode} {command} "
                f"missing={missing} length={len(value)} control={control}"
            )

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
# Independent returning-call transcripts: retained caller epoch across a real
# peer run, with exact hardware frames and old-owner drains at all three stops.
images["clean"]["call_pc"] = 1020


def file_call_fixture(mode, reply):
    fault, exhausted = mode.endswith("-fault"), mode.endswith("-budget")
    result = 0 if fault or exhausted else reply
    caller_root, peer_root = arena + 0x90000, arena + 0xA0000
    lines = [
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena}",
        f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual=18446620928407240704 id=0 root={kernel_root}",
        "AURORA_FILE_CALL_READY: one byte",
        "AURORA_FILE_CALL_BEGIN: generation=1",
    ]

    def event(vector, pc, root, cpl=3):
        frame = arena + (0x88000 - 176 if cpl == 3 else 0x47000)
        lines.append(
            f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl={cpl} root={root} frame={frame} cr2=0"
        )

    def quiet(epoch, ticks):
        event(64, arena + 0x22000 + 102, kernel_root, 0)
        lines.extend(
            [
                f"AURORA_UEFI_TIMER_DRAIN: epoch={epoch} root={kernel_root} ss=16",
                f"AURORA_UEFI_TIMER_QUIET: epoch={epoch} ticks={ticks} "
                f"drains=1 compiled=1 context=0 root={kernel_root}",
            ]
        )

    def tick(used):
        event(64, 1030, caller_root)
        lines.append(f"AURORA_UEFI_TIMER_TICK: epoch=1 used={used} remaining={128 - used} pc=1030 flags=514")

    lines.extend(
        [
            "AURORA_UEFI_USER_RUN: epoch=1 role=client phase=request client=0 transaction=0 "
            f"source={17 if fault else 24 if exhausted else 16} root={caller_root}",
            f"AURORA_UEFI_TIMER_ARM: epoch=1 budget=128 root={caller_root}",
        ]
    )
    tick(1)
    event(130, 1020, caller_root)
    lines.append("AURORA_CALL_PARK: ticket=2 epoch=1 ticks=1 remaining=127")
    quiet(1, 1)
    lines.extend(
        [
            "AURORA_UEFI_USER_RUN: epoch=2 role=service phase=service client=0 transaction=2 "
            f"source={4 if fault else 11} root={peer_root}",
            f"AURORA_UEFI_TIMER_ARM: epoch=2 budget=128 root={peer_root}",
        ]
    )
    event(6 if fault else 129, 2090 if fault else 2010, peer_root)
    quiet(2, 0)
    lines.extend(
        [
            f"AURORA_CALL_SERVICE: epoch=2 event={'bounds' if fault else 'returned'} value={0 if fault else reply}",
            "AURORA_CALL_RESUME: epoch=1 ticks=1 remaining=127",
        ]
    )
    event(130, 1020, caller_root)
    for used in range(2, 129 if exhausted else 3):
        tick(used)
    if not exhausted:
        event(129, 1010, caller_root)
    quiet(1, 128 if exhausted else 2)
    answer = (
        "Program stopped: checked fault or budget exhausted; output discarded."
        if result == 0
        else "EOF"
        if result == 2
        else "File is missing."
        if result == 3
        else "byte> " + chr(result >> 8)
    )
    lines.extend(
        [
            f"AURORA_CALL_COMPLETE: epoch=1 event={'budget' if exhausted else 'returned'} "
            f"value={0 if exhausted else 40 + result}",
            f"AURORA_FILE_CALL_END: result={result} used=0",
            answer,
            "AURORA_CONSOLE_EXIT",
            "AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0",
            "AURORA_UEFI_OK",
        ]
    )
    return "\r\n".join(lines) + "\r\n", [result], [0 if fault else reply]


for mode, reply in [
    ("program-file-call", 18433),
    ("program-file-call", 2),
    ("program-file-call", 3),
    ("program-file-call-fault", 18433),
    ("program-file-call-budget", 18433),
]:
    text, results, replies = file_call_fixture(mode, reply)
    module.validate_file_call(text, mode, results, replies, images, timer)
    checks += 1
    mutations = [
        text.replace("cr2=0", "cr2=1", 1),
        text.replace("error=0", "error=1", 1),
        text.replace("cpl=3", "cpl=0", 1),
        text.replace("flags=514", "flags=2", 1),
        text.replace("flags=514", "flags=12802", 1),
        text.replace(f"frame={arena + 0x88000 - 176}", f"frame={arena + 0x88000 - 184}", 1),
        text.replace(f"root={arena + 0x90000}", f"root={arena + 0x90000 + 4096}", 1),
        text.replace("vector=130 error=0 pc=1020", "vector=130 error=0 pc=1021", 1),
        text.replace("AURORA_CALL_RESUME: epoch=1", "AURORA_CALL_RESUME: epoch=2", 1),
        text.replace("ticks=1 remaining=127", "ticks=2 remaining=126", 1),
        text.replace("used=2 remaining=126", "used=1 remaining=127", 1),
        text.replace("transaction=2 source=", "transaction=3 source=", 1),
        text.replace("AURORA_UEFI_TIMER_DRAIN: epoch=1", "AURORA_UEFI_TIMER_DRAIN: epoch=2", 1),
        text.replace(f"pc={arena + 0x22000 + 102}", f"pc={arena + 0x22000 + 105}", 1),
        text.replace("AURORA_CALL_COMPLETE: epoch=1", "AURORA_CALL_COMPLETE: epoch=2", 1),
        text.replace("AURORA_CONSOLE_EXIT", ""),
        text + "byte> H\r\n",
        text.replace("AURORA_FILE_CALL_END:", "byte> H\r\nAURORA_FILE_CALL_END:", 1),
        text.replace(
            "AURORA_CALL_RESUME:",
            f"AURORA_UEFI_TIMER_ARM: epoch=1 budget=128 root={arena + 0x90000}\r\nAURORA_CALL_RESUME:",
            1,
        ),
    ]
    call_line = next(line for line in text.splitlines(keepends=True) if "vector=130 " in line)
    resume_position = text.index("AURORA_CALL_RESUME:")
    moved_repeat = text[:resume_position] + text[resume_position:].replace(call_line, "", 1)
    mutations.extend(
        [
            text.replace("generation=1", "generation=0", 1),
            text.replace("ticket=2", "ticket=0").replace("transaction=2", "transaction=0"),
            moved_repeat.replace("AURORA_CALL_PARK:", call_line + "AURORA_CALL_PARK:", 1),
        ]
    )
    for changed in mutations:
        if changed == text:
            continue
        try:
            module.validate_file_call(changed, mode, results, replies, images, timer)
        except ValueError:
            checks += 1
        else:
            raise SystemExit("FAIL: returning file-call oracle accepted changed transcript in " + mode)

# Independent single-transaction streaming EOF/missing transcripts. Multi-byte
# and midpoint cases run in the existing actual guest path.
for data in ("", None):
    reply = 2 if data == "" else 3
    result = module.wc_result(data)
    caller_root, peer_root = arena + 0x90000, arena + 0xA0000

    def wc_event(vector, pc, root):
        return (
            f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3 root={root} "
            f"frame={arena + 0x88000 - 176} cr2=0"
        )

    lines = [
        f"AURORA_UEFI_OWNERSHIP_OK: arena={arena}",
        f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual=18446620928407240704 id=0 root={kernel_root}",
        "AURORA_WC_BEGIN: generation=1",
        f"AURORA_UEFI_USER_RUN: epoch=1 role=client phase=request client=0 transaction=0 source=32 root={caller_root}",
        f"AURORA_UEFI_TIMER_ARM: epoch=1 budget=128 root={caller_root}",
        wc_event(130, 1020, caller_root),
        "AURORA_WC_DEBIT: epoch=1 used=1 remaining=127",
        "AURORA_CALL_PARK: ticket=2 epoch=1 ticks=1 remaining=127",
        "AURORA_UEFI_TIMER_QUIET: epoch=1 ticks=1",
        f"AURORA_UEFI_USER_RUN: epoch=2 role=service phase=service client=0 transaction=2 source=11 root={peer_root}",
        f"AURORA_UEFI_TIMER_ARM: epoch=2 budget=128 root={peer_root}",
        wc_event(129, 2010, peer_root),
        "AURORA_WC_DEBIT: epoch=2 used=1 remaining=127",
        "AURORA_UEFI_TIMER_QUIET: epoch=2 ticks=1",
        f"AURORA_CALL_SERVICE: epoch=2 event=returned value={reply}",
        "AURORA_CALL_RESUME: epoch=1 ticks=1 remaining=127",
        wc_event(129, 1010, caller_root),
        "AURORA_UEFI_TIMER_QUIET: epoch=1 ticks=1",
        f"AURORA_CALL_COMPLETE: epoch=1 event=returned value={result}",
        "AURORA_WC_TOTAL: calls=1 caller=1 service=1",
        f"AURORA_WC_END: result={result} used=0",
        module.wc_answer(result),
    ]
    text = "\r\n".join(lines) + "\r\n"
    module.validate_wc(text, [(data, 32)], images, timer)
    checks += 1
    for changed in (
        text.replace("generation=1", "generation=0"),
        text.replace("ticket=2", "ticket=0").replace("transaction=2", "transaction=0"),
        text.replace("used=1 remaining=127", "used=2 remaining=126", 1),
        text.replace("calls=1 caller=1 service=1", "calls=1 caller=1 service=0"),
        text.replace("event=returned value=" + str(result), "event=parked value=" + str(result)),
        text.replace("AURORA_WC_END:", "0 0 0\r\nAURORA_WC_END:"),
        text.replace("AURORA_CALL_RESUME: epoch=1", "AURORA_CALL_RESUME: epoch=2"),
    ):
        try:
            module.validate_wc(changed, [(data, 32)], images, timer)
        except ValueError:
            checks += 1
        else:
            raise SystemExit("FAIL: wc oracle accepted changed lifecycle/counts")

print(f"PASS: {checks} protected-console transcript positive/refusal controls; no guest executed")

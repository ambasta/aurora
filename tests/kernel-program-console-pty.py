#!/usr/bin/env python3
"""Original-clock PTY gate for an explicitly selected, admitted native image."""

from pathlib import Path
import argparse
import errno
import json
import os
import pty
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tty

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from kernel_layout import LAYOUT

import kernel_program_console_admission as admission
import kernel_uefi_console_clock as clock
import qemu_transport as transport


def need(okay, message):
    if not okay:
        raise ValueError(message)


def validate_domain_events(text, images, timer, returning=False):
    arenas = re.findall(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", text)
    need(len(arenas) == 1, "Missing unique kernel arena")
    arena = int(arenas[0])
    kernel_root = arena + 0x11000
    need(
        re.search(
            r"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual=18446620928407240704 "
            r"id=0 root=" + str(kernel_root) + r"(?:\r{1,2}\n)",
            text,
        ),
        "Wrong shared timer admission root",
    )
    records = [line for line in text.splitlines() if line.startswith("AURORA_")]
    event_pattern = re.compile(
        r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) "
        r"cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)"
    )
    events = []
    live_epoch = None
    live_image = None
    live_root = None
    terminal_seen = False
    drains = 0
    caller_epoch = None
    for position, line in enumerate(records):
        run = re.fullmatch(
            r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) "
            r"phase=(request|service|completion) client=0 transaction=\d+ source=\d+ root=(\d+)",
            line,
        )
        if run:
            live_epoch = int(run[1])
            live_image = images["bounds" if run[2] == "service" else "clean"]
            live_root = arena + (0xA0000 if run[2] == "service" else 0x90000)
            need(int(run[4]) == live_root, "Run launched under another root")
            terminal_seen = False
            if run[2] == "client":
                caller_epoch = live_epoch
        resume = re.fullmatch(r"AURORA_CALL_RESUME: epoch=(\d+) ticks=\d+ remaining=\d+", line)
        if resume:
            need(returning and int(resume[1]) == caller_epoch and live_epoch is None, "Invalid resume owner")
            live_epoch = caller_epoch
            live_image = images["clean"]
            live_root = arena + 0x90000
            terminal_seen = False
        if line.startswith("AURORA_CALL_PARK:"):
            need(returning and live_epoch == caller_epoch, "Invalid parked owner")
            terminal_seen = True
        if re.fullmatch(r"AURORA_(?:UEFI_TIMER_TICK|WC_DEBIT): epoch=\d+ used=\d+ remaining=0(?: .*)?", line):
            terminal_seen = True
        event = event_pattern.fullmatch(line)
        if event:
            vector, error, pc, cpl, root, frame, cr2 = map(int, event.groups())
            events.append((vector, error, pc, cpl))
            need(error == 0 and cr2 == 0 and live_epoch is not None, "Unexpected exception authority")
            if cpl == 0:
                need(
                    vector == 64
                    and terminal_seen
                    and root == kernel_root
                    and arena + 0x44000 <= frame <= arena + 0x48000 - LAYOUT.fault_frame_size
                    and frame % 8 == 0
                    and arena + 0x22000 + timer["drain_begin"] <= pc <= arena + 0x22000 + timer["drain_end"],
                    "Unauthorized supervisor timer event",
                )
                need(
                    position + 1 < len(records)
                    and records[position + 1]
                    == f"AURORA_UEFI_TIMER_DRAIN: epoch={live_epoch} root={kernel_root} ss=16",
                    "Supervisor timer lacks immediately paired old-owner drain",
                )
                drains += 1
                continue
            need(
                cpl == 3
                and vector in ((6, 64, 129, 130) if returning else (6, 64, 129))
                and root == live_root
                and frame == arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size,
                "Invalid active-domain frame",
            )
            if vector == 130:
                need(live_epoch == caller_epoch and pc == images["clean"]["call_pc"], "Unknown call site/owner")
            if vector == 129:
                need(pc == live_image["return_pc"], "Unknown user return site")
                terminal_seen = True
            if vector == 6:
                if returning:
                    need(pc == live_image["bounds_pc"], "Unknown emitted fault site")
                terminal_seen = True
            if vector == 64:
                need(
                    live_image["entry"] <= pc < live_image["entry"] + live_image["size"],
                    "Timer interrupted outside admitted user image",
                )
        if returning and line.startswith("AURORA_UEFI_TIMER_TICK:"):
            tick = re.fullmatch(
                r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=\d+ remaining=\d+ pc=(\d+) flags=(\d+)", line
            )
            previous = event_pattern.fullmatch(records[position - 1]) if position else None
            need(
                tick
                and previous
                and int(tick[1]) == live_epoch
                and int(previous[1]) == 64
                and int(previous[4]) == 3
                and int(previous[3]) == int(tick[2])
                and int(tick[3]) & 0x202 == 0x202
                and int(tick[3]) & 0x3000 == 0,
                "Tick lacks adjacent owned hardware frame or safe flags",
            )
        if line.startswith("AURORA_WC_DEBIT:"):
            debit = re.fullmatch(r"AURORA_WC_DEBIT: epoch=(\d+) used=\d+ remaining=\d+", line)
            need(returning and debit and int(debit[1]) == live_epoch, "WC boundary debit has active owner")
        if line.startswith("AURORA_UEFI_TIMER_DRAIN:"):
            need(
                position > 0
                and event_pattern.fullmatch(records[position - 1])
                and int(event_pattern.fullmatch(records[position - 1])[4]) == 0,
                "Unpaired drain record",
            )
        if line.startswith("AURORA_UEFI_TIMER_QUIET:"):
            live_epoch = None
    need(drains == text.count("AURORA_UEFI_TIMER_DRAIN:"), "Unconsumed drain record")
    return events


def wc_result(data):
    if data is None:
        return 3
    raw = data.encode("ascii")
    words = 0
    inside = False
    for byte in raw:
        space = byte == 32 or 9 <= byte <= 13
        words += not space and not inside
        inside = not space
    return 1 | (raw.count(10) << 8) | (words << 16) | (len(raw) << 24)


def wc_answer(result):
    if result == 0:
        return "Program stopped: checked fault or budget exhausted; output discarded."
    if result == 3:
        return "File is missing."
    return " ".join(str((result >> shift) & 255) for shift in (8, 16, 24))


def crc_result(data):
    if data is None:
        return 3
    crc = 0xFFFFFFFF
    for byte in data.encode("ascii"):
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return 1 | ((crc ^ 0xFFFFFFFF) << 8)


def crc_answer(result):
    return wc_answer(result) if result in (0, 3) else f"{result >> 8:08x}"


def validate_wc(text, plans, images, timer, *, checksum=False):
    tag = "CRC" if checksum else "WC"
    result_of = crc_result if checksum else wc_result
    answer_of = crc_answer if checksum else wc_answer
    validate_domain_events(text, images, timer, returning=True)
    parts = list(
        re.finditer(
            rf"AURORA_{tag}_BEGIN: generation=(\d+)\r?\n(.*?)"
            rf"AURORA_{tag}_END: result=(\d+) used=0\r?\n",
            text,
            re.S,
        )
    )
    need(
        len(parts) == len(plans) == text.count(f"AURORA_{tag}_BEGIN:") == text.count(f"AURORA_{tag}_END:"),
        "Exact wc command retirement count",
    )
    generations = [int(x[1]) for x in parts]
    need(all(x > 0 for x in generations) and generations == sorted(set(generations)), "Fresh wc selections")
    for part, (data, phase) in zip(parts, plans):
        body = part[2]
        expected = result_of(data) if phase == 32 else 0
        need(int(part[3]) == expected, "Exact streaming counts or discarded failure")
        need(text[part.end() :].startswith(answer_of(expected) + "\r\n"), "WC presentation after retirement")
        need(
            not re.search(r"^(?:[0-9a-f]{8}|\d+ \d+ \d+|File is missing\.|Program stopped:.*)\r?$", body, re.M),
            "No partial wc presentation",
        )
        runs = list(
            re.finditer(
                r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) "
                r"phase=(request|service) client=0 transaction=(\d+) source=(\d+) root=(\d+)",
                body,
            )
        )
        need(bool(runs), "WC has caller")
        caller = int(runs[0][1])
        need(
            runs[0][2] == "client"
            and runs[0][3] == "request"
            and runs[0][4] == "0"
            and int(runs[0][5]) == phase + (16 if checksum else 0),
            "Exact wc caller authority",
        )
        parks = list(re.finditer(r"AURORA_CALL_PARK: ticket=(\d+) epoch=(\d+) ticks=(\d+) remaining=(\d+)", body))
        resumes = list(re.finditer(r"AURORA_CALL_RESUME: epoch=(\d+) ticks=(\d+) remaining=(\d+)", body))
        expected_calls = (2 if phase in (34, 36) else 3) if phase != 32 else (1 if data is None else len(data) + 1)
        need(
            len(parks) == len(resumes) == expected_calls <= 50 and len(runs) == expected_calls + 1,
            "Bounded byte requests including EOF",
        )
        tickets = [int(p[1]) for p in parks]
        need(all(t > 0 for t in tickets) and tickets == sorted(set(tickets)), "Fresh ordered wc tickets")
        service_epochs = []
        for i, (park, resume, run) in enumerate(zip(parks, resumes, runs[1:])):
            epoch = int(run[1])
            service_epochs.append(epoch)
            need(
                run[2] == "service"
                and run[3] == "service"
                and int(run[4]) == tickets[i]
                and int(run[5]) == (4 if phase == 33 and i == 2 else 5 if phase == 35 and i == 2 else 11),
                "Exact wc service transaction",
            )
            need(int(park[2]) == caller and tuple(park.groups()[1:]) == resume.groups(), "WC original caller resume")
            need(park.start() < run.start() < resume.start(), "WC real peer between park and resume")
            if i:
                need(resumes[i - 1].start() < park.start(), "WC next request after prior return")
        need(
            service_epochs == sorted(set(service_epochs)) and all(e > caller for e in service_epochs),
            "Fresh service run epochs",
        )
        services = re.findall(r"AURORA_CALL_SERVICE: epoch=(\d+) event=(returned|bounds) value=(\d+)", body)
        wanted_services = []
        for i, epoch in enumerate(service_epochs):
            failed = i == 2 and phase in (33, 35)
            reply = 0 if failed else 3 if data is None else 2 if i == len(data) else 1 | (ord(data[i]) << 8)
            wanted_services.append((str(epoch), "bounds" if failed else "returned", str(reply)))
        need(services == wanted_services, "WC exact byte/EOF service replies")
        traps = list(re.finditer(r"AURORA_UEFI_DOMAIN_EVENT: vector=130 ", body))
        need(
            len(traps) == expected_calls + int(phase == 36)
            and all(t.start() < p.start() for t, p in zip(traps, parks))
            and all(resumes[i - 1].start() < traps[i].start() for i in range(1, len(traps))),
            "WC each published request has one caller trap",
        )
        terminals = [
            (int(v), int(pc))
            for v, pc in re.findall(r"AURORA_UEFI_DOMAIN_EVENT: vector=(6|129) error=0 pc=(\d+) ", body)
        ]
        wanted_terminals = [
            (6, images["bounds"]["bounds_pc"]) if i == 2 and phase == 33 else (129, images["bounds"]["return_pc"])
            for i in range(expected_calls)
            if not (i == 2 and phase == 35)
        ]
        if phase not in (34, 36):
            wanted_terminals.append((129, images["clean"]["return_pc"]))
        need(terminals == wanted_terminals, "WC exact hardware terminal sites")
        used = {"caller": 0, "service": 0}
        arms = 0
        for line in body.splitlines():
            arm = re.fullmatch(r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=\d+", line)
            if arm:
                owner = "caller" if int(arm[1]) == caller else "service"
                need(
                    int(arm[1]) in [caller] + service_epochs and int(arm[2]) == 128 - used[owner],
                    "WC arm carries remaining allowance",
                )
                arms += 1
            debit = re.fullmatch(
                r"AURORA_(?:WC_DEBIT|UEFI_TIMER_TICK): epoch=(\d+) used=(\d+) remaining=(\d+)(?: pc=\d+ flags=\d+)?",
                line,
            )
            if debit:
                epoch, total, left = map(int, debit.groups())
                need(epoch in [caller] + service_epochs, "WC debit owner")
                owner = "caller" if epoch == caller else "service"
                need(total == used[owner] + 1 and total + left == 128, "WC cumulative IRQ and boundary debit")
                used[owner] = total
        quiet = [int(e) for e in re.findall(r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ", body)]
        wanted_quiet = [caller]
        for epoch in service_epochs:
            wanted_quiet.extend((epoch, caller))
        need(quiet == wanted_quiet, "WC every park/peer/final continuation quiesces")
        probes = re.findall(r"AURORA_WC_BOUNDARY_PROBE: role=(client|service)", body)
        need(
            probes == (["client" if phase == 36 else "service"] if phase in (36, 37) else []),
            "Exact explicit boundary-exhaustion probe",
        )
        if phase in (36, 37):
            target = caller if phase == 36 else service_epochs[-1]
            debits = re.findall(rf"AURORA_WC_DEBIT: epoch={target} used=(\d+) remaining=(\d+)", body)
            need(debits[-2:] == [("127", "1"), ("128", "0")], "Actual boundary127 to128 refusal")
        need(arms == 1 + expected_calls, "No caller rearm/reset on wc resume")
        total = re.findall(rf"AURORA_{tag}_TOTAL: calls=(\d+) caller=(\d+) service=(\d+)", body)
        need(total == [(str(expected_calls), str(used["caller"]), str(used["service"]))], "WC final debit totals")
        need(used["caller"] >= expected_calls and used["service"] >= expected_calls - 1, "WC boundary charges")
        if phase in (34, 35, 36, 37):
            need(used["caller" if phase in (34, 36) else "service"] == 128, "WC injected original quota exhaustion")
        completed = list(
            re.finditer(r"AURORA_CALL_COMPLETE: epoch=(\d+) event=(parked|returned|budget) value=(\d+)", body)
        )
        need(
            len(completed) == expected_calls and all(int(c[1]) == caller for c in completed), "WC continuation outcomes"
        )
        need(
            [c[2] for c in completed]
            == ["parked"] * (expected_calls - 1) + ["budget" if phase in (34, 36) else "returned"],
            "WC only final resume terminates",
        )
        need(int(completed[-1][3]) == expected, "WC returned live counters")
    need(
        len(re.findall(r"^[0-9a-f]{8}\r?$" if checksum else r"^\d+ \d+ \d+\r?$", text, re.M))
        == sum(phase == 32 and data is not None for data, phase in plans),
        "No duplicate wc count presentation",
    )
    return {"crc_commands" if checksum else "wc_commands": len(parts)}


def validate_file_call(text, mode, expected, service_results, images, timer):
    need(mode in admission.MODES and mode.startswith("program-file-call"), "Exact file-call profile")
    need("FAIL" not in text and text.count("AURORA_FILE_CALL_READY:") == 1, "File-call startup/failure")
    need(
        text.count("AURORA_PROGRAM_CONSOLE_QUIET:") == text.count("AURORA_UEFI_OK") == 1,
        "File-call final quiescence/restoration",
    )
    validate_domain_events(text, images, timer, returning=True)
    parts = list(
        re.finditer(
            r"AURORA_FILE_CALL_BEGIN: generation=(\d+)\r?\n(.*?)"
            r"AURORA_FILE_CALL_END: result=(\d+) used=0\r?\n",
            text,
            re.S,
        )
    )
    need(
        len(parts) == len(expected) == text.count("AURORA_FILE_CALL_BEGIN:") == text.count("AURORA_FILE_CALL_END:"),
        "Exact file-call lifecycle count",
    )
    need(all(int(part[1]) > 0 for part in parts), "Nonzero command generations")
    need(all(int(a[1]) < int(b[1]) for a, b in zip(parts, parts[1:])), "Fresh command incarnations")
    need(len(service_results) == len(expected), "Exact service expectations")
    need(
        text.count("AURORA_CONSOLE_EXIT") == 1
        and text.count("AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0") == 1,
        "Exact quiescent console exit",
    )
    for index, (part, result) in enumerate(zip(parts, expected)):
        body = part[2]
        fault = index == 0 and mode.endswith("-fault")
        exhausted = index == 0 and mode.endswith("-budget")
        need(int(part[3]) == result, "Actual copied file result")
        park = re.findall(r"AURORA_CALL_PARK: ticket=(\d+) epoch=(\d+) ticks=(\d+) remaining=(\d+)", body)
        resume = re.findall(r"AURORA_CALL_RESUME: epoch=(\d+) ticks=(\d+) remaining=(\d+)", body)
        need(len(park) == len(resume) == 1 and park[0][1:] == resume[0], "Original caller continuation")
        ticket, epoch, used, left = map(int, park[0])
        need(ticket > 0, "Nonzero transaction ticket")
        need(epoch == 2 * index + 1 and 0 < used < 128 and used + left == 128, "Original budget before park")
        launches = re.findall(
            r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) phase=(request|service) "
            r"client=(\d+) transaction=(\d+) source=(\d+) root=(\d+)",
            body,
        )
        need(
            [row[:6] for row in launches]
            == [
                (str(epoch), "client", "request", "0", "0", str(17 if fault else 24 if exhausted else 16)),
                (str(epoch + 1), "service", "service", "0", str(ticket), str(4 if fault else 11)),
            ],
            "Exact selected caller/service authority",
        )
        park_at, resume_at = body.index("AURORA_CALL_PARK:"), body.index("AURORA_CALL_RESUME:")
        service_at = body.index("AURORA_CALL_SERVICE:")
        done_at = body.index("AURORA_CALL_COMPLETE:")
        need(
            re.findall(r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=(\d+)", body)
            == [(str(epoch), "128", launches[0][6]), (str(epoch + 1), "128", launches[1][6])],
            "Exactly two initial budgets, no resume reset",
        )
        quiet = re.findall(r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ", body)
        need(quiet == [str(epoch), str(epoch + 1), str(epoch)], "Park, peer and caller quiescence")
        need(park_at < service_at < resume_at < done_at, "Real peer execution while caller parked")
        for owner, key in ((epoch, "clean"), (epoch + 1, "bounds")):
            ticks = list(
                re.finditer(rf"AURORA_UEFI_TIMER_TICK: epoch={owner} used=(\d+) remaining=(\d+) pc=(\d+)", body)
            )
            need([int(t[1]) for t in ticks] == list(range(1, len(ticks) + 1)), "Continuous timer debit")
            image = images[key]
            need(
                all(
                    int(t[1]) + int(t[2]) == 128 and image["entry"] <= int(t[3]) < image["entry"] + image["size"]
                    for t in ticks
                ),
                "Bounded original image and quota",
            )
            if key == "clean":
                need(
                    len(ticks) >= used
                    and all(t.start() < park_at for t in ticks[:used])
                    and all(resume_at < t.start() < done_at for t in ticks[used:]),
                    "Caller ticks outside park",
                )
                if exhausted:
                    need((ticks[-1][1], ticks[-1][2]) == ("128", "0"), "Original budget exhausts after resume")
            else:
                need(all(park_at < t.start() < resume_at for t in ticks), "Service ticks only while caller parked")
        events = [
            tuple(map(int, row))
            for row in re.findall(
                r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) "
                r"cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)",
                body,
            )
        ]
        calls = [row for row in events if row[0] == 130]
        need(
            len(calls) == 2 and all(row[1:4] == (0, images["clean"]["call_pc"], 3) for row in calls),
            "Only exact returning call site, including rejected repeat",
        )
        terminals = [(row[0], row[2]) for row in events if row[0] in (6, 129)]
        need(
            terminals
            == ([(6, images["bounds"]["bounds_pc"])] if fault else [(129, images["bounds"]["return_pc"])])
            + ([] if exhausted else [(129, images["clean"]["return_pc"])]),
            "Exact peer and caller terminal events",
        )
        call_positions = [match.start() for match in re.finditer(r"AURORA_UEFI_DOMAIN_EVENT: vector=130 ", body)]
        need(
            call_positions[0] < park_at and resume_at < call_positions[1] < done_at,
            "First call parks; rejected repeat occurs only after resume",
        )
        peer = (6, images["bounds"]["bounds_pc"]) if fault else (129, images["bounds"]["return_pc"])
        need(
            any((row[0], row[2]) == peer and row[1] == 0 and row[3] == 3 for row in events),
            "Actual service terminal site",
        )
        need(
            re.findall(r"AURORA_CALL_SERVICE: epoch=(\d+) event=(returned|bounds) value=(\d+)", body)
            == [(str(epoch + 1), "bounds" if fault else "returned", str(service_results[index]))],
            "Copied service reply or emitted fault",
        )
        need(
            re.findall(r"AURORA_CALL_COMPLETE: epoch=(\d+) event=(returned|budget) value=(\d+)", body)
            == [(str(epoch), "budget" if exhausted else "returned", str(0 if exhausted else 40 + result))],
            "Result returns into retained caller locals",
        )
        answer = (
            "Program stopped: checked fault or budget exhausted; output discarded."
            if result == 0
            else "EOF"
            if result == 2
            else "File is missing."
            if result == 3
            else "byte> " + chr(result >> 8)
        )
        need(text[part.end() :].startswith(answer + "\r\n"), "Exact response follows retirement")
        need(
            not re.search(r"(?:byte> |^EOF$|File is missing\.|output discarded\.)", body, re.M),
            "No result before retirement",
        )
    need(
        len(re.findall(r"^(?:byte> .*|EOF|File is missing\.|Program stopped: .*output discarded\.)\r?$", text, re.M))
        == len(parts) + len(re.findall(r"AURORA_(?:WC|CRC)_END: result=(?:0|3) used=0", text)),
        "No duplicate results outside calls",
    )
    return dict(file_calls=len(parts), call_local_sum=40)


def validate(
    text, mode, expected_outputs, commands, images, timer, expected_reads=None, expected_saves=None, expected_files=None
):
    expected_reads = {} if expected_reads is None else expected_reads
    expected_saves = {} if expected_saves is None else expected_saves
    expected_files = {} if expected_files is None else expected_files
    need("AURORA_UEFI_RUNTIME_FAIL" not in text and "AURORA_UEFI_FAIL" not in text, "Runtime or payload failed closed")
    need(text.count("AURORA_PROGRAM_CONSOLE_READY:") == 1, "Console restart or missing readiness")
    begins = [
        (int(grant), int(length))
        for grant, length in re.findall(
            r"AURORA_PROGRAM_COMMAND_BEGIN: grant=(\d+) length=(\d+) domains=2 "
            r"kind=(?:upper-file|file|upper-note|upper|note)\r?\n",
            text,
        )
    ]
    endings = [
        (int(success), int(epoch))
        for success, epoch in re.findall(r"AURORA_PROGRAM_COMMAND_END: success=([01]) used=0 epoch=(\d+)", text)
    ]
    need(len(begins) == len(endings) == commands, "Missing command lifecycle evidence")
    need(
        text.count("AURORA_PROGRAM_COMMAND_BEGIN:") == text.count("AURORA_PROGRAM_COMMAND_END:") == commands,
        "Unexpected or malformed command ownership interval",
    )
    need(all(a[0] < b[0] for a, b in zip(begins, begins[1:])), "Endpoint generation reused")
    need(all(0 <= length <= 64 for _, length in begins), "Unbounded admitted input")
    need(all(a[1] <= b[1] for a, b in zip(endings, endings[1:])), "Timer epoch reset")
    epochs = [int(value) for value in re.findall(r"AURORA_UEFI_USER_RUN: epoch=(\d+) ", text)]
    need(epochs and all(a < b for a, b in zip(epochs, epochs[1:])), "Run epoch missing or reused")
    command_matches = list(
        re.finditer(
            r"AURORA_PROGRAM_COMMAND_BEGIN: grant=\d+ length=(\d+) domains=2 "
            r"kind=(upper-file|file|upper-note|upper|note)\r?\n(.*?)"
            r"AURORA_PROGRAM_COMMAND_END: success=([01]) used=0 epoch=(\d+)\r?\n([^\r\n]*)",
            text,
            re.S,
        )
    )
    command_parts = [match.groups() for match in command_matches]
    need(len(command_parts) == commands, "Unmatched command ownership interval")
    need(set(expected_reads) <= set(range(commands)), "Unexpected note command index")
    need(set(expected_saves) <= set(range(commands)), "Unexpected saved-output command index")
    need(set(expected_files) <= set(range(commands)), "Unexpected named-file command index")
    saved_count = 0
    missing_count = 0
    file_saved_count = 0
    file_missing_count = 0
    for command_index, (length, kind, part, success, ending_epoch, result) in enumerate(command_parts):
        need((kind == "note") == (command_index in expected_reads), "Unexpected note/upper command")
        need((kind == "upper-note") == (command_index in expected_saves), "Unexpected saved-output command")
        need((kind in ("file", "upper-file")) == (command_index in expected_files), "Unexpected named-file command")
        if kind in ("upper-note", "upper-file"):
            marker = "File saved." if kind == "upper-file" else "Note saved."
            if kind == "upper-note":
                need(int(length) == len(expected_saves[command_index]) <= 53, "Bounded exact saved-output length")
                saved_count += int(success == "1")
            else:
                file_saved_count += int(success == "1")
            need(marker not in part, "Value was saved before retirement")
            match = command_matches[command_index]
            response_end = command_matches[command_index + 1].start() if command_index + 1 < commands else len(text)
            prompt = text.find("aurora> ", match.end())
            if prompt >= 0:
                response_end = min(response_end, prompt)
            response = text[match.start(6) : response_end]
            need(response.count(marker) == int(success == "1"), "Duplicate or unexpected save acknowledgment")
            need(
                result
                == (
                    marker
                    if success == "1"
                    else "Program stopped: checked fault or budget exhausted; output discarded."
                ),
                "Saved-output terminal response mismatch",
            )
        rounds = int(length)
        sources = {"request": 0, "service": 1, "completion": 2}
        if kind == "note":
            expected = expected_reads[command_index]
            need(
                (int(length) == 8 or (int(length) == 10 and expected is None))
                and (expected is None or len(expected) <= 53),
                "Bounded exact note command",
            )
            rounds = len(expected or "") + 1
            sources = {"request": 12, "service": 11, "completion": 13}
            missing_count += int(expected is None and success == "1")
        if kind in ("file", "upper-file"):
            planned = expected_files[command_index]
            command = planned["command"]
            expected = planned["value"]
            parsed = re.fullmatch(r"(cat|upper) ([A-Za-z0-9_.-]{1,8})", command)
            need(parsed and parsed[2] not in ("note", ".", ".."), "Invalid expected file command")
            need(int(length) == len(command), "Named-file trace must retain original command length")
            need(
                expected is None or (len(expected) <= 49 and all(32 <= ord(byte) <= 126 for byte in expected)),
                "Unbounded or nonprintable expected file value",
            )
            saving = parsed[1] == "upper" and expected is not None
            need(kind == ("upper-file" if saving else "file"), "Wrong named-file command kind")
            rounds = len(expected or "") + 1
            sources = {"request": 12, "service": 11, "completion": 14 if saving else 13}
            file_missing_count += int(expected is None and success == "1")
            need(
                result
                == (
                    ("File saved." if saving else "File is missing." if expected is None else "output> " + expected)
                    if success == "1"
                    else "Program stopped: checked fault or budget exhausted; output discarded."
                ),
                "Named-file terminal response mismatch",
            )
        runs = re.findall(
            r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) "
            r"phase=(request|service|completion) client=0 transaction=(\d+) source=(\d+) root=\d+",
            part,
        )
        phases = [item[2] for item in runs]
        if success == "1":
            need(phases == ["request", "service", "completion"] * rounds, "Missing or reordered byte handoff")
        else:
            failed_phase = mode.split("-")[1]
            prefix = {"request": 1, "service": 2, "completion": 3}[failed_phase]
            need(
                rounds >= 2
                and phases == ["request", "service", "completion"] + ["request", "service", "completion"][:prefix],
                "Fault did not follow one completed byte",
            )
        for offset, (_, role, phase, transaction, source) in enumerate(runs):
            need(role == ("service" if phase == "service" else "client"), "Wrong role for phase")
            need((int(transaction) == 0) == (phase == "request"), "Wrong transaction launch authority")
            if success == "1" or offset + 1 < len(runs):
                need(int(source) == sources[phase], "Wrong healthy source phase")
            if phase == "completion":
                need(transaction == runs[offset - 1][3], "Completion changed transaction")
        if runs:
            need(int(ending_epoch) == int(runs[-1][0]), "Retirement epoch does not match last run")
    actual_outputs = re.findall(r"^output> ([^\r\n]*)\r?\n", text, re.M)
    need(actual_outputs == expected_outputs, "Partial, duplicate, missing or wrong completed output")
    # Every full output must immediately follow a successful zero-resource end.
    need(
        len(re.findall(r"AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=\d+\r?\noutput> ", text))
        == len(expected_outputs),
        "Output was exposed before authenticated retirement",
    )
    need(
        len(re.findall(r"AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=\d+\r?\nNote saved\.", text))
        == saved_count,
        "Saved output lacks complete authenticated retirement",
    )
    need(len(re.findall(r"^Note is missing\.\r?$", text, re.M)) == missing_count, "Missing-note outcome mismatch")
    need(
        len(re.findall(r"AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=\d+\r?\nNote is missing\.", text))
        == missing_count,
        "Missing-note output preceded authenticated retirement",
    )
    for marker, count in (("File saved.", file_saved_count), ("File is missing.", file_missing_count)):
        need(
            len(re.findall(r"^" + re.escape(marker) + r"\r?$", text, re.M)) == count,
            "Duplicate or unexpected named-file terminal response",
        )
        need(
            len(re.findall(r"AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=\d+\r?\n" + re.escape(marker), text))
            == count,
            "Named-file terminal response preceded authenticated retirement",
        )
    events = validate_domain_events(text, images, timer)
    failed = mode not in ("program-console", "program-pending")
    faults = [pc for vector, _, pc, _ in events if vector == 6]
    need(len(faults) == int(mode.endswith("fault")), "Wrong emitted-fault count")
    need(sum(success == 0 for success, _ in endings) == int(failed), "Wrong recovery count")
    need(
        text.count("Program stopped: checked fault or budget exhausted; output discarded.") == int(failed),
        "Missing single contained-failure report",
    )
    if failed:
        phase = mode.split("-")[1]
        expected_source = (
            {"request": 6, "service": 5, "completion": 7}[phase]
            if mode.endswith("budget")
            else {"request": 8, "service": 4, "completion": 10}[phase]
        )
        need(
            re.search(r"phase=" + phase + r" client=0 transaction=\d+ source=" + str(expected_source) + r" ", text),
            "Requested fault/budget phase did not execute",
        )
        if mode.endswith("budget"):
            need(re.search(r"AURORA_UEFI_TIMER_TICK: epoch=\d+ used=3 remaining=0 ", text), "Budget did not exhaust")
            need(
                re.search(r"AURORA_UEFI_TIMER_QUIET: epoch=\d+ ticks=3 drains=\d+ compiled=[1-9]\d* ", text),
                "Budget lacks authenticated compiled-PC timer evidence",
            )
        else:
            owner = "bounds" if phase == "service" else "clean"
            need(faults == [images[owner]["bounds_pc"]], "Fault did not match admitted emitted bounds site")
    if mode == "program-pending":
        need(
            "AURORA_UEFI_TIMER_PENDING:" in text and "AURORA_UEFI_TIMER_DRAIN:" in text,
            "Pending IRQ did not drain under the old runtime owner",
        )
        transforming_parts = [part for _, kind, part, _, _, _ in command_parts if kind == "upper-file"]
        if transforming_parts:
            need(
                any(
                    "AURORA_UEFI_TIMER_PENDING:" in part and "AURORA_UEFI_TIMER_DRAIN:" in part
                    for part in transforming_parts
                ),
                "Named-file transformation lacks its own pending IRQ ownership/drain evidence",
            )
    need(text.count("AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0") == 1, "Missing quiescent exit")
    need(text.count("AURORA_CONSOLE_EXIT") == 1, "Missing single exit")
    return dict(
        commands=commands,
        grants=[item[0] for item in begins],
        runs=len(epochs),
        last_epoch=endings[-1][1],
        completed_outputs=len(actual_outputs),
        saved_outputs=saved_count,
        saved_files=file_saved_count,
        missing_files=file_missing_count,
        recovered=int(failed),
    )


FAILSTOP_REASONS = {
    "program-owner": "program request capability/state",
    "program-ordinal": "program phase/version/ordinal",
    "program-unknown": "exception site authority",
    "program-transaction": "program service capability/byte",
}


def validate_failstop(part, mode, status, images):
    reason = "AURORA_UEFI_RUNTIME_FAIL: " + FAILSTOP_REASONS[mode]
    need(status == 35 and part.count(reason) == 1, "Malformed authority did not fail stop exactly once")
    need(
        "output> " not in part
        and "AURORA_PROGRAM_COMMAND_END:" not in part
        and "aurora> " not in part
        and "output discarded." not in part,
        "Malformed authority exposed output or recovered",
    )
    need(part.count("AURORA_PROGRAM_COMMAND_BEGIN:") == 1, "Malformed command restarted")
    image = images["bounds" if mode == "program-transaction" else "clean"]
    vector = 6 if mode == "program-unknown" else 129
    pc = image["probe_pc"] if mode == "program-unknown" else image["return_pc"]
    need(
        pc != 0 and f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3 " in part,
        "Malformed image did not reach its admitted CPL3 envelope/probe",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=admission.MODES, default="program-console")
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--read-only-recovery", action="store_true")
    args = parser.parse_args()
    need(
        not args.read_only_recovery or args.mode.endswith(("-fault", "-budget")),
        "Read-only recovery requires a fault or budget profile",
    )
    admission.configure_paths(args.build_dir, ROOT)
    admitted = admission.checked(args.mode)
    admission_digest = admission.digest(admission.RECEIPT)
    evidence_root = ROOT / "build/program-console-evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=args.mode + "-guest-", dir=evidence_root))
    shutil.copy2(admission.RECEIPT, output / "admission.json")
    print("Protected-console guest evidence: " + str(output))

    def unchanged():
        need(
            admission.checked(args.mode) == admitted and admission.digest(admission.RECEIPT) == admission_digest,
            "Admitted image or report changed during guest execution",
        )

    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    if not qemu:
        raise admission.Blocked("QEMU unavailable")
    selected = subprocess.check_output(
        [
            "bash",
            "-c",
            "set -e; source scripts/uefi-firmware.sh; uefi_firmware_select; "
            'printf "%s\\0" "$UEFI_FIRMWARE_COMBINED" "$UEFI_FIRMWARE_CODE" '
            '"$UEFI_FIRMWARE_VARS" "${UEFI_FIRMWARE_ARGS[@]}"',
        ],
        cwd=ROOT,
    )
    firmware, code, variables, *firmware_args = selected.decode().split("\0")[:-1]
    command = transport.profile_command(
        "uefi",
        args.mode,
        qemu,
        admission.BUILD / "esp",
        os.environ.get("QEMU_DATA", ""),
        firmware=firmware,
        code=code,
        variables=variables,
    )
    receipt = clock.receipt(
        command, qemu, firmware, code, variables, os.environ.get("QEMU_DATA", ""), esp=str(admission.BUILD / "esp")
    )
    receipt.update(timeout_argv=None, test_supervision="private PTY, 180-second total deadline", mode=args.mode)
    (output / "clock.json").write_text(json.dumps(receipt, indent=2) + "\n")
    master, slave = pty.openpty()
    tty.setraw(slave)
    transcript = bytearray()
    process = None
    deadline = time.monotonic() + 180
    expected_outputs = []
    expected_reads = {}
    expected_saves = {}
    expected_files = {}
    commands = 0
    metrics = {
        "status": "incomplete",
        "mode": args.mode,
        "read_only_recovery": args.read_only_recovery,
        "clock": "tcg-original-clock",
        "purpose": "guest",
        "admission_sha256": admission_digest,
    }
    try:
        with (output / "qemu.stderr").open("wb") as errors:
            process = transport.start(command, cwd=ROOT, stdin=slave, stdout=slave, stderr=errors)
            os.close(slave)
            slave = -1

            def receive(marker, begin):
                while marker not in transcript[begin:]:
                    need(time.monotonic() < deadline, "PTY deadline waiting for " + repr(marker))
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        try:
                            data = os.read(master, 65536)
                        except OSError as error:
                            if error.errno != errno.EIO:
                                raise
                            data = b""
                        need(data, "QEMU closed before expected response")
                        transcript.extend(data)
                        need(len(transcript) <= 4 * 1024 * 1024, "PTY evidence exceeded bound")
                    elif transport.exited(process):
                        need(select.select([master], [], [], 0)[0], "QEMU exited early")

            def send(data, burst=False):
                if burst:
                    need(os.write(master, data) == len(data), "Incomplete PTY burst")
                else:
                    for byte in data:
                        need(time.monotonic() < deadline, "Input deadline")
                        need(os.write(master, bytes([byte])) == 1, "Incomplete PTY byte")
                        time.sleep(0.003)

            def command_upper(data, expected=None, failure=False):
                nonlocal commands
                begin = len(transcript)
                send(b"upper\r\n")
                receive(b"text> ", begin)
                begin = len(transcript)
                send(data)
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).decode("ascii")
                commands += 1
                if failure:
                    need("output> " not in part and "output discarded." in part, "Failed command exposed output")
                else:
                    need(expected is not None and "output> " + expected + "\r\n" in part, "Wrong output")
                    expected_outputs.append(expected)

            def note_write(content):
                begin = len(transcript)
                send(b"write note " + content + b"\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:])
                need(
                    b"Note saved.\r\n" in part and b"AURORA_PROGRAM_COMMAND_BEGIN:" not in part,
                    "Write must update the quiescent Aurora value without launching domains",
                )

            def note_read(expected, failure=False):
                nonlocal commands
                begin = len(transcript)
                send(b"cat note\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).decode("ascii")
                expected_reads[commands] = expected
                commands += 1
                if failure:
                    need(
                        "output> " not in part and "Note is missing." not in part and "output discarded." in part,
                        "Failed note read exposed output",
                    )
                elif expected is None:
                    need("Note is missing.\r\n" in part, "Missing note not distinguished")
                else:
                    need("output> " + expected + "\r\n" in part, "Actual protected note contents differ")
                    expected_outputs.append(expected)

            def note_upper(expected, failure=False):
                nonlocal commands
                begin = len(transcript)
                send(b"upper note\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).decode("ascii")
                if expected is None:
                    expected_reads[commands] = None
                else:
                    expected_saves[commands] = expected
                commands += 1
                need("output> " not in part, "Saved-output command exposed a separate stream")
                if failure:
                    need("Note saved." not in part and "output discarded." in part, "Failed program replaced the note")
                elif expected is None:
                    need("Note is missing.\r\n" in part and "Note saved." not in part, "Missing note was created")
                else:
                    need(part.count("Note saved.\r\n") == 1, "Complete protected output was not saved exactly once")

            def file_local(command, expected):
                begin = len(transcript)
                send(command.encode("ascii") + b"\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).decode("ascii")
                need(
                    part.count("\r\n" + expected + "\r\n") == 1
                    and "AURORA_PROGRAM_COMMAND_BEGIN:" not in part
                    and "AURORA_UEFI_USER_RUN:" not in part
                    and "output> " not in part
                    and "File saved." not in part,
                    "File update/list/remove must return the exact quiescent SessionFiles reply without domains",
                )

            def file_write(name, content):
                size = len(content)
                file_local("write " + name + " " + content, f"wrote {name}: {size} byte" + ("" if size == 1 else "s"))

            def file_command(verb, name, expected, failure=False):
                nonlocal commands
                command = verb + " " + name
                begin = len(transcript)
                send(command.encode("ascii") + b"\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).decode("ascii")
                expected_files[commands] = {"command": command, "value": expected}
                commands += 1
                if failure:
                    need(
                        "output> " not in part
                        and "File saved." not in part
                        and "File is missing." not in part
                        and "output discarded." in part,
                        "Failed named-file command exposed or replaced partial output",
                    )
                elif expected is None:
                    need(
                        part.count("File is missing.\r\n") == 1
                        and "File saved." not in part
                        and "output> " not in part,
                        "Missing named file was created or exposed as an empty file",
                    )
                elif verb == "upper":
                    need(
                        part.count("File saved.\r\n") == 1 and "output> " not in part,
                        "Protected file replacement was not acknowledged exactly once",
                    )
                else:
                    need("output> " + expected + "\r\n" in part, "Actual protected file contents differ")
                    expected_outputs.append(expected)

            receive(b"aurora> ", 0)
            tty.setraw(master)
            if args.mode in FAILSTOP_REASONS:
                begin = len(transcript)
                send(b"upper\n")
                receive(b"text> ", begin)
                begin = len(transcript)
                send(b"hostile envelope\n")
                reason = "AURORA_UEFI_RUNTIME_FAIL: " + FAILSTOP_REASONS[args.mode]
                receive((reason + "\r\n").encode(), begin)
                status = transport.wait_exit(process, 5)
                part = bytes(transcript[begin:]).decode("ascii")
                validate_failstop(part, args.mode, status, admitted["user_images"])
                unchanged()
                metrics.update(
                    status="passed",
                    exit_status=35,
                    failstop=FAILSTOP_REASONS[args.mode],
                )
                print("PASS: malformed protected command authority fails stop without output or recovery")
                return

            if args.mode.startswith("program-file-call"):
                expected = []
                service_results = []
                call_times = []

                def peek(name, value, failure=False):
                    begin = len(transcript)
                    started = time.monotonic()
                    send(("peek " + name + "\n").encode())
                    receive(b"aurora> ", begin)
                    call_times.append(time.monotonic() - started)
                    part = bytes(transcript[begin:]).decode("ascii")
                    reply = 3 if value is None else 2 if value == "" else 1 | (ord(value) << 8)
                    expected.append(0 if failure else reply)
                    service_results.append(0 if failure and args.mode.endswith("-fault") else reply)
                    if failure:
                        need(
                            "output discarded." in part and "byte> " not in part and "File is missing." not in part,
                            "Failed call exposed partial result",
                        )
                    else:
                        answer = "File is missing." if value is None else "EOF" if value == "" else "byte> " + value
                        need(
                            part.count("\r\n" + answer + "\r\n") == 1
                            and part.index("AURORA_FILE_CALL_END:") < part.index("\r\n" + answer),
                            "Exact partial result only after retirement",
                        )

                file_write("alpha", "Hello")
                peek("alpha", "H", failure=args.mode != "program-file-call")
                peek("alpha", "H")
                file_local("copy alpha beta", "wrote beta: 5 bytes")
                peek("beta", "H")
                file_write("alpha", "x")
                peek("alpha", "x")
                peek("beta", "H")
                file_write("empty", "")
                peek("empty", "")
                peek("missing", None)
                for invalid in ("peek alpha extra", "peek ", "cat alpha", "upper alpha"):
                    file_local(invalid, "Unknown command. Type help.")
                file_local("rm alpha", "files: removed (RAM-only).")
                peek("alpha", None)
                wc_plans = []

                def wc(name, data, phase=32):
                    begin = len(transcript)
                    send(("wc " + name + "\n").encode())
                    receive(b"aurora> ", begin)
                    wc_plans.append((data, phase))
                    result = wc_result(data) if phase == 32 else 0
                    part = bytes(transcript[begin:]).decode("ascii")
                    need(part.count("\r\n" + wc_answer(result) + "\r\n") == 1, "Actual wc response")

                wc("beta", "Hello", 33 if args.mode.endswith("-fault") else 34 if args.mode.endswith("-budget") else 32)
                if args.mode.endswith("-budget"):
                    wc("beta", "Hello", 35)
                    wc("beta", "Hello", 36)
                    wc("beta", "Hello", 37)
                wc("beta", "Hello")
                wc("empty", "")
                wc("missing", None)
                file_write("alpha", "a " * 24 + "z")
                wc("alpha", "a " * 24 + "z")
                for invalid in ("wc ", "wc alpha extra", "wc note"):
                    file_local(invalid, "Unknown command. Type help.")
                crc_plans = []

                def crc(name, data, phase=32):
                    begin = len(transcript)
                    send(("crc " + name + "\n").encode())
                    receive(b"aurora> ", begin)
                    crc_plans.append((data, phase))
                    result = crc_result(data) if phase == 32 else 0
                    part = bytes(transcript[begin:]).decode("ascii")
                    need(part.count("\r\n" + crc_answer(result) + "\r\n") == 1, "Actual CRC response")

                crc(
                    "beta", "Hello", 33 if args.mode.endswith("-fault") else 34 if args.mode.endswith("-budget") else 32
                )
                if args.mode.endswith("-budget"):
                    for phase in (35, 36, 37):
                        crc("beta", "Hello", phase)
                crc("beta", "Hello")
                crc("empty", "")
                crc("missing", None)
                crc("alpha", "a " * 24 + "z")
                file_write("alpha", "123456789")
                crc("alpha", "123456789")
                crc("beta", "Hello")
                for invalid in ("crc ", "crc alpha extra", "crc note"):
                    file_local(invalid, "Unknown command. Type help.")
                begin = len(transcript)
                send(b"exit\n")
                receive(b"AURORA_UEFI_OK", begin)
                need(transport.wait_exit(process, 5) == 33, "File-call normal guest exit")
                unchanged()
                metrics.update(
                    validate_file_call(
                        bytes(transcript).decode("ascii"),
                        args.mode,
                        expected,
                        service_results,
                        admitted["user_images"],
                        admitted["timer"],
                    ),
                    **validate_wc(
                        bytes(transcript).decode("ascii"), wc_plans, admitted["user_images"], admitted["timer"]
                    ),
                    **validate_wc(
                        bytes(transcript).decode("ascii"),
                        crc_plans,
                        admitted["user_images"],
                        admitted["timer"],
                        checksum=True,
                    ),
                    status="passed",
                    exit_status=33,
                    command_seconds=call_times,
                )
                print("PASS: command-bound returning file byte, live locals, original budget and retired authority")
                return

            # Returning file calls are opt-in. Legacy profiles must reject even
            # syntactically valid commands without launching a domain.
            for invalid in (
                "wc alpha",
                "wc note",
                "wc ",
                "wc alpha extra",
                "crc alpha",
                "crc note",
                "crc ",
                "crc alpha extra",
            ):
                file_local(invalid, "Unknown command. Type help.")

            if args.mode == "program-console":
                file_local("ls", "files: empty (RAM-only).")
                file_command("upper", "missing", None)
                file_command("cat", "missing", None)
                file_local("ls", "files: empty (RAM-only).")
                file_local("append missing x", "files: not found (RAM-only).")
                file_local("append note x", "files: note is reserved.")
                file_write("alpha", "Hello,")
                file_local("append alpha  Aurora", "wrote alpha: 7 bytes")
                file_local("append alpha ", "wrote alpha: 0 bytes")
                file_local("copy alpha beta", "wrote beta: 13 bytes")
                file_command("cat", "beta", "Hello, Aurora")
                file_local("copy missing beta", "files: not found (RAM-only).")
                file_local("copy alpha note", "files: note is reserved.")
                file_local("copy alpha beta extra", "files: invalid name or content.")
                file_write("beta", "Keep Lower")
                file_command("cat", "alpha", "Hello, Aurora")
                file_command("upper", "alpha", "HELLO, AURORA")
                file_command("cat", "alpha", "HELLO, AURORA")
                file_command("cat", "beta", "Keep Lower")
                file_command("upper", "alpha", "HELLO, AURORA")
                file_command("cat", "alpha", "HELLO, AURORA")
                file_write("alpha", "x")
                file_command("cat", "alpha", "x")
                file_write("alpha", "")
                file_command("upper", "alpha", "")
                file_command("cat", "alpha", "")
                file_write("abcdefgh", "z" * 49)
                file_command("cat", "abcdefgh", "z" * 49)
                file_local("append abcdefgh x", "files: invalid name or content.")
                file_command("upper", "abcdefgh", "Z" * 49)
                file_command("cat", "abcdefgh", "Z" * 49)
                file_write("delta", "Last untouched")
                file_local("ls", "files: alpha beta abcdefgh delta")
                file_local("copy abcdefgh alpha", "wrote alpha: 49 bytes")
                file_command("cat", "alpha", "Z" * 49)
                file_command("cat", "abcdefgh", "Z" * 49)
                file_local("copy alpha alpha", "wrote alpha: 49 bytes")
                file_local("copy alpha fifth", "files: full (4 files).")
                file_local("write fifth rejected", "files: full (4 files).")
                file_command("upper", "fifth", None)
                file_command("cat", "fifth", None)
                # Existing selections remain writable even when all slots are full.
                file_write("alpha", "full store")
                file_command("upper", "alpha", "FULL STORE")
                file_command("cat", "alpha", "FULL STORE")
                file_command("cat", "beta", "Keep Lower")
                file_command("cat", "delta", "Last untouched")
                file_local("write alpha " + "q" * 50, "files: invalid name or content.")
                file_command("cat", "alpha", "FULL STORE")
                file_local("rm beta", "files: removed (RAM-only).")
                file_command("cat", "beta", None)
                file_write("newfile", "Reused slot")
                file_local("ls", "files: alpha newfile abcdefgh delta")
                file_command("cat", "newfile", "Reused slot")
                file_command("cat", "abcdefgh", "Z" * 49)
                note_upper(None)
                note_read(None)
                note_write(b"Hello, Aurora")
                note_upper("HELLO, AURORA")
                note_read("HELLO, AURORA")
                note_upper("HELLO, AURORA")
                note_read("HELLO, AURORA")
                note_write(b"first")
                note_read("first")
                note_read("first")
                note_write(b"x")
                note_read("x")
                note_write(b"")
                note_upper("")
                note_read("")
                note_write(b"z" * 53)
                note_read("z" * 53)
                # Damaged and overlong replacement attempts must preserve the note.
                for rejected_note in (b"write note " + b"q" * 54 + b"\n", b"write note bad\x01\n"):
                    begin = len(transcript)
                    send(rejected_note)
                    receive(b"aurora> ", begin)
                    need(b"Line rejected:" in transcript[begin:], "Invalid note replacement accepted")
                note_read("z" * 53)
                note_upper("Z" * 53)
                note_read("Z" * 53)
            elif args.mode == "program-pending":
                file_write("pending", "pending file")
                file_write("other", "Remain lower")
                file_command("upper", "pending", "PENDING FILE")
                file_command("cat", "pending", "PENDING FILE")
                file_command("cat", "other", "Remain lower")
                note_write(b"pending note")
                note_upper("PENDING NOTE")
                note_read("PENDING NOTE")
            else:
                file_write("recover", "recover this file")
                file_write("other", "Remain lower")
                if args.read_only_recovery:
                    file_command("cat", "recover", "recover this file", failure=True)
                else:
                    file_command("upper", "recover", "RECOVER THIS FILE", failure=True)
                file_command("cat", "recover", "recover this file")
                file_command("cat", "other", "Remain lower")
                file_command("upper", "recover", "RECOVER THIS FILE")
                file_command("cat", "recover", "RECOVER THIS FILE")
                file_command("cat", "other", "Remain lower")
                note_write(b"recover this note")
                note_read("recover this note")
                note_upper("RECOVER THIS NOTE")
                note_read("RECOVER THIS NOTE")
            command_upper(b"Hello, Aurora 42!\n", "HELLO, AURORA 42!")
            command_upper(b"next command\n", "NEXT COMMAND")
            for payload in (b"help", b"status", b"exit"):
                command_upper(payload + b"\r\n", payload.decode("ascii").upper())
            command_upper(b"\n", "")
            command_upper(b"abx\x08cZ!\r\n", "ABCZ!")
            command_upper(b"a" * 64 + b"\n", "A" * 64)
            # Rejected text never opens a Mailbox command, including an overlong
            # line whose backspace would otherwise hide its invalid history.
            for rejected in (b"a" * 65 + b"\x08\n", b"\xffx\n", b"\x1bexit\n", b"\x00x\n"):
                begin = len(transcript)
                send(b"upper\n")
                receive(b"text> ", begin)
                begin = len(transcript)
                send(rejected)
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:])
                need(
                    b"Line rejected:" in part and b"AURORA_PROGRAM_COMMAND_BEGIN:" not in part,
                    "Rejected line launched a protected command",
                )
            # Original-clock FIFO overload is observed as rejection/recovery;
            # hardware OE identity itself is covered by the hosted UART model.
            begin = len(transcript)
            send(b"upper\n")
            receive(b"text> ", begin)
            begin = len(transcript)
            send(b"z" * 256, burst=True)
            time.sleep(0.2)
            send(b"\n")
            receive(b"aurora> ", begin)
            need(b"Line rejected:" in transcript[begin:], "FIFO overload was not rejected")
            command_upper(b"healthy after rejection\n", "HEALTHY AFTER REJECTION")
            begin = len(transcript)
            send(b"exit\n")
            receive(b"AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0\r\n", begin)
            need(transport.wait_exit(process, 5) == 33, "QEMU did not exit cleanly")
            while select.select([master], [], [], 0)[0]:
                try:
                    tail = os.read(master, 65536)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    break
                if not tail:
                    break
                transcript.extend(tail)
            unchanged()
            metrics.update(
                validate(
                    bytes(transcript).decode("ascii"),
                    args.mode,
                    expected_outputs,
                    commands,
                    admitted["user_images"],
                    admitted["timer"],
                    expected_reads,
                    expected_saves,
                    expected_files,
                ),
                status="passed",
                exit_status=process.returncode,
            )
    finally:
        cleanup_errors, _, unsettled = transport.finish(process, fds=(master, slave if slave != -1 else None))
        (output / "transcript.log").write_bytes(transcript)
        (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
        if unsettled:
            raise transport.ChildNotReaped("; ".join(cleanup_errors))
        need(not cleanup_errors, "; ".join(cleanup_errors))
    print("PASS: protected Aurora command PTY, bounded input, copied stream, recovery and quiescent exit")
    if args.read_only_recovery:
        print("PASS: read-only selected-file cancellation and authenticated retirement")


def terminate(_signal, _frame):
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, terminate)
    try:
        main()
    except admission.Blocked as error:
        print("BLOCKED: program console PTY: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise SystemExit("FAIL: program console PTY: " + str(error)) from error

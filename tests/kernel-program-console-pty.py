#!/usr/bin/env python3
"""Original-clock PTY gate for an explicitly selected native image."""

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
import struct
import sys
import tempfile
import time
import tty

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from kernel_layout import LAYOUT
from kernel_elf import Elf, PF_R, SHF_ALLOC
from kernel_profiles import FIXTURE_MODES, serial_fixture_byte
from kernel_uefi_oracle import loader_selection

import qemu_transport as transport
import kernel_volume


class Blocked(Exception):
    pass


def need(okay, message):
    if not okay:
        raise ValueError(message)


def validate_domain_events(text, images, timer, returning=False):
    arenas = re.findall(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", text)
    need(len(arenas) == 1, "Missing unique kernel arena")
    arena = int(arenas[0])
    kernel_root = arena + LAYOUT.kernel_tables_offset
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
            live_root = arena + (
                (LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size)
                if run[2] == "service"
                else LAYOUT.tables_offset
            )
            need(int(run[4]) == live_root, "Run launched under another root")
            terminal_seen = False
            if run[2] == "client":
                caller_epoch = live_epoch
        resume = re.fullmatch(r"AURORA_CALL_RESUME: epoch=(\d+) ticks=\d+ remaining=\d+", line)
        if resume:
            need(returning and int(resume[1]) == caller_epoch and live_epoch is None, "Invalid resume owner")
            live_epoch = caller_epoch
            live_image = images["clean"]
            live_root = arena + LAYOUT.tables_offset
            terminal_seen = False
        if line.startswith("AURORA_CALL_PARK:"):
            need(returning and live_epoch == caller_epoch, "Invalid parked owner")
            terminal_seen = True
        if line.startswith("AURORA_APPEND_PARK:"):
            need(returning and live_epoch is not None and live_epoch != caller_epoch, "Invalid parked producer")
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
                    and arena + LAYOUT.kernel_stack_bottom
                    <= frame
                    <= arena + LAYOUT.kernel_stack_top - LAYOUT.fault_frame_size
                    and frame % 8 == 0
                    and arena + LAYOUT.kernel_payload_offset + timer["drain_begin"]
                    <= pc
                    <= arena + LAYOUT.kernel_payload_offset + timer["drain_end"],
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
                site = images["clean"]["call_pc"] if live_epoch == caller_epoch else images["bounds"]["serve_pc"]
                need(returning and pc == site, "Unknown role-specific Call/Serve site")
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


def validate_retained_service(text, *, final=False):
    """Real registry identities and allocator evidence, independent of run epochs."""
    parts = list(
        re.finditer(
            r"AURORA_(FILE_CALL|WC|CRC)_BEGIN: generation=(\d+)\r?\n(.*?)"
            r"AURORA_\1_END: result=(\d+) used=(\d+)\r?\n",
            text,
            re.S,
        )
    )
    need(
        len(parts) == len(re.findall(r"AURORA_(?:FILE_CALL|WC|CRC)_BEGIN:", text)),
        "Every read command has a retirement envelope",
    )
    need(
        len(parts) == text.count("AURORA_FILE_SERVICE_BEGIN:") == text.count("AURORA_FILE_SERVICE_END:"),
        "Exactly one retained service binding and release per command",
    )
    previous_service = previous_generation = 0
    retained = False
    callers, services = set(), set()
    for part in parts:
        body = part[3]
        begin = list(
            re.finditer(
                r"AURORA_FILE_SERVICE_BEGIN: service=(\d+) caller=(\d+) generation=(\d+) "
                r"root=(\d+) used=8 reused=([01])\r?\n",
                body,
            )
        )
        end = list(
            re.finditer(
                r"AURORA_FILE_SERVICE_END: service=(\d+) caller=(\d+) generation=(\d+) "
                r"root=(\d+) retained=([01]) used=(\d+) scrubbed=1\r?\n",
                body,
            )
        )
        need(len(begin) == len(end) == 1, "Exact retained-service boundary evidence")
        service, caller, generation, root, reused = map(int, begin[0].groups())
        need(
            service > 0 and caller > 0 and caller != service and caller not in callers and caller not in services,
            "Fresh actual caller incarnation distinct from every service",
        )
        need(generation == int(part[2]) and generation > previous_generation, "Fresh authenticated read generation")
        need(reused == int(retained), "Reuse only follows a healthy retained boundary")
        if retained:
            need(service == previous_service, "Healthy service retains exact registry incarnation")
        else:
            need(service not in services and service not in callers, "Retired service incarnation never resurrects")
        runs = list(re.finditer(r"AURORA_UEFI_USER_RUN:.*? role=(client|service) .*? root=(\d+)", body))
        need(
            runs and begin[0].end() <= runs[0].start() and runs[-1].end() < end[0].start(),
            "Service binding precedes execution and cleanup follows it",
        )
        need(all(int(run[2]) == root for run in runs if run[1] == "service"), "Retained service actual protected root")
        need(
            end[0].groups()[:4] == begin[0].groups()[:4], "Release authenticates original participants, grant and root"
        )
        retained = int(part[4]) != 0
        need(
            int(end[0][5]) == int(retained) and int(end[0][6]) == int(part[5]) == (4 if retained else 0),
            "Healthy-only service leases; failures retire all leases",
        )
        need(body[end[0].end() :] == "", "Scrubbed service boundary immediately precedes presentation envelope")
        callers.add(caller)
        services.add(service)
        previous_service, previous_generation = service, generation
    if final:
        exit_records = list(re.finditer(r"AURORA_FILE_SERVICE_EXIT: service=(\d+) used=0 scrubbed=1\r?\n", text))
        need(len(exit_records) == text.count("AURORA_FILE_SERVICE_EXIT:") == 1, "One final service scrub")
        need(
            int(exit_records[0][1]) == (previous_service if retained else 0), "Exit retires exact retained incarnation"
        )
        need(
            parts and parts[-1].end() < exit_records[0].start() < text.index("AURORA_PROGRAM_CONSOLE_QUIET:"),
            "All command results precede final service retirement and quiet",
        )
    return len(parts)


def validate_wc(text, plans, images, timer, *, checksum=False):
    validate_retained_service(text)
    tag = "CRC" if checksum else "WC"
    result_of = crc_result if checksum else wc_result
    answer_of = crc_answer if checksum else wc_answer
    validate_domain_events(text, images, timer, returning=True)
    parts = list(
        re.finditer(
            rf"AURORA_{tag}_BEGIN: generation=(\d+)\r?\n(.*?)"
            rf"AURORA_{tag}_END: result=(\d+) used=[04]\r?\n",
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
    # Every file-call mode, the baseline included, boots text-fixture: its loader
    # echoes the mode's fw_cfg row before any other record (PTY startup may
    # duplicate CR before the first prompt).
    loader_selection(text.replace("\r", ""), mode)
    validate_retained_service(text, final=True)
    need(mode.startswith("program-file-call"), "Exact file-call profile")
    need("FAIL" not in text and text.count("AURORA_FILE_CALL_READY:") == 1, "File-call startup/failure")
    need(
        text.count("AURORA_PROGRAM_CONSOLE_QUIET:") == text.count("AURORA_UEFI_OK") == 1,
        "File-call final quiescence/restoration",
    )
    validate_domain_events(text, images, timer, returning=True)
    parts = list(
        re.finditer(
            r"AURORA_FILE_CALL_BEGIN: generation=(\d+)\r?\n(.*?)"
            r"AURORA_FILE_CALL_END: result=(\d+) used=[04]\r?\n",
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
    previous_epoch = 0
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
        need(epoch > previous_epoch and 0 <= used < 128 and used + left == 128, "Fresh original budget before park")
        previous_epoch = epoch + 1
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
        == len(parts) + len(re.findall(r"AURORA_(?:WC|CRC)_END: result=(?:0|3) used=[04]", text)),
        "No duplicate results outside calls",
    )
    return dict(file_calls=len(parts), call_local_sum=40)


# Append owns one live caller and one live producer, never scalar per-byte
# reentry. Exact public readback consumes the resulting replies after retirement.
def validate_append(part, mode, expected, success, ending_epoch, images):
    need(expected is not None and len(expected) <= 49, "Append selects a present bounded file")
    runs = list(
        re.finditer(
            r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) "
            r"phase=(request|service|completion) client=0 transaction=(\d+) source=(\d+) root=(\d+)",
            part,
        )
    )
    need(runs and len([run for run in runs if run[2] == "client"]) == 1, "Append launches its caller exactly once")
    caller = int(runs[0][1])
    need(runs[0].groups()[1:5] == ("client", "request", "0", "16"), "Append owns one source-16 request lifetime")
    services = runs[1:]
    parks = list(re.finditer(r"AURORA_CALL_PARK: ticket=(\d+) epoch=(\d+) ticks=(\d+) remaining=(\d+)", part))
    resumes = list(re.finditer(r"AURORA_CALL_RESUME: epoch=(\d+) ticks=(\d+) remaining=(\d+)", part))
    producer_parks = list(re.finditer(r"AURORA_APPEND_PARK: ticket=(\d+) terminal=([01])", part))
    producer_resumes = list(re.finditer(r"AURORA_APPEND_RESUME: ticket=(\d+)", part))
    launches = list(re.finditer(r"AURORA_APPEND_LAUNCH: operation=(\d+)", part))
    failed_mode = "" if success else mode
    before = "-before-" in failed_mode
    request_failure = failed_mode in ("program-request-fault", "program-request-budget")
    service_failure = failed_mode in ("program-service-fault", "program-service-budget")
    construction_failure = failed_mode in ("program-append-construct-fault", "program-append-construct-budget")
    producer_return = failed_mode == "program-append-producer-return"
    completion_failure = failed_mode in ("program-completion-fault", "program-completion-budget")
    terminal_budget = failed_mode == "program-append-terminal-budget"
    cancelled = failed_mode.removeprefix("program-append-cancel-") if "-cancel-" in failed_mode else ""
    calls = (
        0
        if before
        else 1
        if request_failure or construction_failure or producer_return
        else 2
        if service_failure or completion_failure or cancelled in ("pending", "delivered", "replied")
        else len(expected) + 1
    )
    activations = calls - int(cancelled in ("pending", "delivered"))
    replies = activations - int(service_failure or construction_failure or producer_return or terminal_budget)
    completions = replies - int(cancelled in ("replied", "terminal"))
    need(len(parks) == calls <= 50 and len(services) == activations, "Append bounds bytes plus terminal EOF")
    need(len(producer_parks) == replies and len(resumes) == completions, "Only accepted peer replies resume the caller")
    need(len(launches) == int(activations != 0), "Append launches one producer only after a real request")
    need(len(producer_resumes) == max(0, activations - 1), "Later producer activations resume its retained locals")
    tickets = [int(park[1]) for park in parks]
    need(all(ticket > 0 for ticket in tickets) and tickets == sorted(set(tickets)), "Append tickets never repeat")
    service_epochs = [int(run[1]) for run in services]
    need(
        service_epochs == sorted(set(service_epochs)) and all(epoch > caller for epoch in service_epochs),
        "Append service activations allocate fresh epochs",
    )
    terminal = replies == len(expected) + 1
    need(
        [int(park[2]) for park in producer_parks] == [0] * (replies - int(terminal)) + [1] * int(terminal),
        "Only the complete candidate emits one terminal producer park",
    )
    for index, service in enumerate(services):
        park = parks[index]
        need(
            service[2] == service[3] == "service" and int(service[4]) == tickets[index] and service[5] == "17",
            "Append producer owns the current delivered transaction and private source entry",
        )
        need(int(park[2]) == caller and park.start() < service.start(), "Append suspends before activating its peer")
        if index == 0:
            need(park.start() < launches[0].start() < service.start(), "Producer cannot launch before request zero")
        else:
            need(
                int(producer_resumes[index - 1][1]) == tickets[index]
                and service.start() < producer_resumes[index - 1].start(),
                "Fresh activation resumes the exact new ticket",
            )
        if index < replies:
            need(
                int(producer_parks[index][1]) == tickets[index] and service.start() < producer_parks[index].start(),
                "Producer parks each accepted reply once",
            )
        if index < completions:
            resume = resumes[index]
            need(
                park.groups()[1:] == resume.groups() and producer_parks[index].start() < resume.start(),
                "Append restores the exact caller epoch and remaining allowance after producer park",
            )
            if index + 1 < len(parks):
                need(resume.start() < parks[index + 1].start(), "Append next request follows its prior reply")
    traps = list(re.finditer(r"AURORA_UEFI_DOMAIN_EVENT: vector=130 error=0 pc=(\d+) ", part))
    call_traps = [trap for trap in traps if int(trap[1]) == images["clean"]["call_pc"]]
    serve_traps = [trap for trap in traps if int(trap[1]) == images["bounds"]["serve_pc"]]
    need(
        len(call_traps) == calls and all(trap.start() < park.start() for trap, park in zip(call_traps, parks)),
        "Append publishes one exact Call trap per request",
    )
    need(
        len(serve_traps) == replies + int(terminal_budget)
        and len(traps) == len(call_traps) + len(serve_traps)
        and all(trap.start() < park.start() for trap, park in zip(serve_traps, producer_parks)),
        "Append publishes one exact Serve trap per attempted producer reply",
    )
    terminals = [
        tuple(map(int, match.groups()))
        for match in re.finditer(r"AURORA_UEFI_DOMAIN_EVENT: vector=(6|129) error=0 pc=(\d+) ", part)
    ]
    wanted = []
    if producer_return:
        wanted.append((129, images["bounds"]["return_pc"]))
    elif (service_failure or construction_failure) and mode.endswith("fault"):
        wanted.append((6, images["bounds"]["bounds_pc"]))
    elif not success and mode.endswith("fault"):
        wanted.append((6, images["clean"]["bounds_pc"]))
    elif success or mode in ("program-append-copy", "program-append-backing"):
        wanted.append((129, images["clean"]["return_pc"]))
    need(terminals == wanted, "No producer return can replace terminal park and clean caller return")
    used = {"caller": 0, "service": 0}
    arms = 0
    for line in part.splitlines():
        arm = re.fullmatch(r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=\d+", line)
        if arm:
            epoch, remaining = map(int, arm.groups())
            owner = "caller" if epoch == caller else "service"
            need(
                epoch in [caller] + service_epochs and remaining == 128 - used[owner],
                "Append activates only the remaining cumulative allowance",
            )
            arms += 1
        debit = re.fullmatch(
            r"AURORA_(?:WC_DEBIT|UEFI_TIMER_TICK): epoch=(\d+) used=(\d+) remaining=(\d+)(?: pc=\d+ flags=\d+)?", line
        )
        if debit:
            epoch, total, remaining = map(int, debit.groups())
            owner = "caller" if epoch == caller else "service"
            need(
                epoch in [caller] + service_epochs and total == used[owner] + 1 and total + remaining == 128,
                "Append charges every IRQ and discarded boundary interval once",
            )
            used[owner] = total
        quiet = re.fullmatch(
            r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ticks=(\d+) drains=\d+ compiled=\d+ context=\d+ root=\d+", line
        )
        if quiet:
            epoch, ticks = map(int, quiet.groups())
            need(
                epoch in [caller] + service_epochs and ticks == used["caller" if epoch == caller else "service"],
                "Append final drain preserves cumulative use",
            )
    need(arms == 1 + activations, "Append never relaunches or replenishes either worker")
    quiets = list(re.finditer(r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ", part))
    wanted_quiets = [caller]
    for index, epoch in enumerate(service_epochs):
        wanted_quiets.append(epoch)
        if index < completions:
            wanted_quiets.append(caller)
    need([int(quiet[1]) for quiet in quiets] == wanted_quiets, "Append drains every parked or terminal original owner")
    need(int(ending_epoch) == wanted_quiets[-1], "Append retirement follows its final authenticated drain")
    receipts = list(
        re.finditer(
            r"AURORA_PROGRAM_APPEND_CALLER: operation=(\d+) calls=(\d+) "
            r"launches=1 producer_launches=1 terminal_park=1 eof=1 clean=1",
            part,
        )
    )
    need(len(receipts) == int(success), "Only terminal park plus clean caller return can capture append output")
    if success:
        need(
            int(receipts[0][1]) == int(launches[0][1]) > 0
            and int(receipts[0][2]) == calls
            and quiets[-1].end() < receipts[0].start(),
            "Append fixed result is captured only after final caller drain",
        )
    if not success and mode.endswith("budget"):
        need(
            used["service" if service_failure or construction_failure or terminal_budget else "caller"] == 128,
            "Append exhausts its original cumulative allowance",
        )
        if not terminal_budget:
            need(
                re.search(r"AURORA_UEFI_TIMER_QUIET: epoch=\d+ ticks=128 drains=\d+ compiled=[1-9]\d* ", part),
                "Append budget has actual compiled-PC timer evidence",
            )
    return int(receipts[0][1]) if receipts else None


def validate(
    text,
    mode,
    expected_outputs,
    commands,
    images,
    timer,
    expected_reads=None,
    expected_saves=None,
    expected_files=None,
    expected_store_losses=(),
):
    loader_selection(text.replace("\r", ""), mode)
    selected = mode in FIXTURE_MODES and FIXTURE_MODES[mode][0] == "program-fixture"
    need(
        text.count("AURORA_FIXTURE_READY") == int(selected)
        and text.splitlines().count("AURORA_FIXTURE_READY") == int(selected),
        "Program fixture selector readiness",
    )
    if selected:
        need(
            "AURORA_PCI_WINDOW_CLOSED:" in text
            and "AURORA_UEFI_TIMER_READY:" in text
            and text.index("AURORA_PCI_WINDOW_CLOSED:")
            < text.index("AURORA_FIXTURE_READY")
            < text.index("AURORA_UEFI_TIMER_READY:"),
            "Program selector admission phase",
        )
    expected_reads = {} if expected_reads is None else expected_reads
    expected_saves = {} if expected_saves is None else expected_saves
    expected_files = {} if expected_files is None else expected_files
    need("AURORA_UEFI_RUNTIME_FAIL" not in text and "AURORA_UEFI_FAIL" not in text, "Runtime or payload failed closed")
    need(text.count("AURORA_PROGRAM_CONSOLE_READY:") == 1, "Console restart or missing readiness")
    begins = [
        (int(grant), int(length))
        for grant, length in re.findall(
            r"AURORA_PROGRAM_COMMAND_BEGIN: grant=(\d+) length=(\d+) domains=2 "
            r"kind=(?:append-file|upper-file|file|upper-note|upper|note)\r?\n",
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
            r"kind=(append-file|upper-file|file|upper-note|upper|note)\r?\n(.*?)"
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
    need(set(expected_store_losses) <= set(expected_saves) | set(expected_files), "Unexpected source commit loss")
    saved_count = 0
    missing_count = 0
    file_saved_count = 0
    file_missing_count = 0
    append_operations = []
    failed_append = False
    for command_index, (length, kind, part, success, ending_epoch, result) in enumerate(command_parts):
        store_loss = command_index in expected_store_losses
        need(
            not store_loss or (kind in ("upper-note", "upper-file") and success == "1"),
            "Source commit loss must follow successful protected retirement",
        )
        need((kind == "note") == (command_index in expected_reads), "Unexpected note/upper command")
        need((kind == "upper-note") == (command_index in expected_saves), "Unexpected saved-output command")
        need(
            (kind in ("file", "upper-file", "append-file")) == (command_index in expected_files),
            "Unexpected named-file command",
        )
        if kind in ("upper-note", "upper-file"):
            marker = "File saved." if kind == "upper-file" else "Note saved."
            if kind == "upper-note":
                need(int(length) == len(expected_saves[command_index]) <= 53, "Bounded exact saved-output length")
                saved_count += int(success == "1" and not store_loss)
            else:
                file_saved_count += int(success == "1" and not store_loss)
            need(marker not in part, "Value was saved before retirement")
            match = command_matches[command_index]
            response_end = command_matches[command_index + 1].start() if command_index + 1 < commands else len(text)
            prompt = text.find("aurora> ", match.end())
            if prompt >= 0:
                response_end = min(response_end, prompt)
            response = text[match.start(6) : response_end]
            need(
                response.count(marker) == int(success == "1" and not store_loss),
                "Duplicate or unexpected save acknowledgment",
            )
            if store_loss:
                cause = "exit status=0" if kind == "upper-note" else "consumer_rejected"
                need(
                    response.count("File service unavailable; result unknown.\r\n") == 1
                    and response.count("AURORA_FILE_SERVICE_LOST:") == 1
                    and response.count(" cause=" + cause + " volatile_data=lost\r\n") == 1,
                    "Post-commit loss must follow observed exit/rejection, not a fault or retry",
                )
            else:
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
        if kind in ("file", "upper-file", "append-file"):
            planned = expected_files[command_index]
            command = planned["command"]
            expected = planned["value"]
            parsed = re.fullmatch(r"(cat|upper|append) ([A-Za-z0-9_.-]{1,8})(?: (.*))?", command)
            need(parsed and parsed[2] not in ("note", ".", ".."), "Invalid expected file command")
            need(int(length) == len(command), "Named-file trace must retain original command length")
            need(
                expected is None or (len(expected) <= 49 and all(32 <= ord(byte) <= 126 for byte in expected)),
                "Unbounded or nonprintable expected file value",
            )
            saving = parsed[1] == "upper" and expected is not None
            appending = parsed[1] == "append"
            need((parsed[3] is not None) == appending, "Only append carries a canonical suffix")
            need(
                kind == ("append-file" if appending else "upper-file" if saving else "file"),
                "Wrong named-file command kind",
            )
            rounds = len(expected or "") + 1
            sources = {"request": 12, "service": 15 if appending else 11, "completion": 14 if saving else 13}
            file_missing_count += int(expected is None and success == "1")
            need(
                store_loss
                or result
                == (
                    (
                        planned["reply"]
                        if appending
                        else "File saved."
                        if saving
                        else "File is missing."
                        if expected is None
                        else "output> " + expected
                    )
                    if success == "1"
                    else "Program stopped: checked fault or budget exhausted; output discarded."
                ),
                "Named-file terminal response mismatch",
            )
        if kind == "append-file":
            operation = validate_append(part, mode, expected, success == "1", ending_epoch, images)
            if operation is not None:
                append_operations.append(operation)
            failed_append |= success == "0"
            continue
        need(
            "AURORA_CALL_PARK:" not in part
            and "AURORA_CALL_RESUME:" not in part
            and "AURORA_PROGRAM_APPEND_CALLER:" not in part
            and "AURORA_APPEND_PARK:" not in part
            and "AURORA_APPEND_RESUME:" not in part
            and "AURORA_APPEND_LAUNCH:" not in part
            and "AURORA_UEFI_DOMAIN_EVENT: vector=130 " not in part,
            "Only active append can enter the returning Call transport",
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
    need(append_operations == sorted(set(append_operations)), "Append completion operations cannot replay")
    need(text.count("AURORA_PROGRAM_APPEND_CALLER:") == len(append_operations), "No append receipt outside its command")
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
    events = validate_domain_events(
        text, images, timer, returning=any(kind == "append-file" for _, kind, *_ in command_parts)
    )
    failed = mode not in ("program-console", "program-pending")
    faults = [pc for vector, _, pc, _ in events if vector == 6]
    need(len(faults) == int(mode.endswith("fault")), "Wrong emitted-fault count")
    need(sum(success == 0 for success, _ in endings) == int(failed), "Wrong recovery count")
    need(
        text.count("Program stopped: checked fault or budget exhausted; output discarded.") == int(failed),
        "Missing single contained-failure report",
    )
    if failed and not failed_append:
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
        for changed_kind in ("upper-file", "append-file"):
            changing_parts = [part for _, kind, part, _, _, _ in command_parts if kind == changed_kind]
            if changing_parts:
                need(
                    any(
                        "AURORA_UEFI_TIMER_PENDING:" in part and "AURORA_UEFI_TIMER_DRAIN:" in part
                        for part in changing_parts
                    ),
                    "Named-file mutation lacks its own pending IRQ ownership/drain evidence: " + changed_kind,
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


APPEND_RECOVERY_MODES = {
    "program-append-before-fault",
    "program-append-before-budget",
    "program-append-eof-fault",
    "program-append-eof-budget",
    "program-append-copy",
    "program-append-construct-fault",
    "program-append-construct-budget",
    "program-append-producer-return",
    "program-append-terminal-budget",
    "program-append-cancel-pending",
    "program-append-cancel-delivered",
    "program-append-cancel-replied",
    "program-append-cancel-terminal",
}
APPEND_FAILSTOP_REASONS = {
    "program-owner": "call envelope",
    "program-ordinal": "call envelope",
    "program-transaction": "append service authority",
    "program-unknown": "exception site authority",
    "program-append-backing": "append backing",
    "program-append-root": "exception root authority",
    "program-append-site": "call exact site and endpoint",
    "program-append-service-site": "append Serve site",
    "program-append-service-root": "exception root authority",
    "program-append-service-backing": "append service authority",
}

FAILSTOP_REASONS = {
    "program-owner": "program request capability/state",
    "program-ordinal": "program phase/version/ordinal",
    "program-unknown": "exception site authority",
    "program-transaction": "program service capability/byte",
}


def validate_failstop(part, mode, status, images, *, append=False, full_text=""):
    reason = "AURORA_UEFI_RUNTIME_FAIL: " + (APPEND_FAILSTOP_REASONS if append else FAILSTOP_REASONS)[mode]
    need(status == 35 and part.count(reason) == 1, "Malformed authority did not fail stop exactly once")
    need(
        "output> " not in part
        and "AURORA_PROGRAM_COMMAND_END:" not in part
        and "aurora> " not in part
        and "output discarded." not in part,
        "Malformed authority exposed output or recovered",
    )
    need(part.count("AURORA_PROGRAM_COMMAND_BEGIN:") == 1, "Malformed command restarted")
    service_probe = mode.startswith("program-append-service-") or (append and mode == "program-transaction")
    image = images["bounds" if mode == "program-transaction" or service_probe else "clean"]
    vector = (
        130
        if mode in ("program-append-root", "program-append-site") or service_probe
        else 6
        if mode == "program-unknown"
        else 129
    )
    # program-unknown: the fixture resumes the client at its wrapper's bad_entry
    # ud2, just after the return site, which is no registered site.
    pc = (
        image["serve_pc" if service_probe else "call_pc"]
        if vector == 130
        else image["return_pc"] + (2 if mode == "program-unknown" else 0)
    )
    need(
        mode != "program-unknown"
        or pc
        not in [image.get(k) for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")],
        "Unknown UD2 aliases a registered site",
    )
    need(
        pc != 0 and f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3 " in part,
        "Malformed image did not reach its admitted CPL3 envelope/probe",
    )
    if append:
        clients = re.findall(
            r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=client "
            r"phase=request client=0 transaction=0 source=16 root=\d+",
            part,
        )
        need(len(clients) == part.count(" role=client ") == 1, "Hostile append still owns one live caller")
        need(not re.search(r" source=(?:12|13) ", part), "Hostile append cannot fall back to scalar byte relaunches")
        if mode in ("program-append-root", "program-append-site"):
            need(
                part.count("AURORA_UEFI_DOMAIN_EVENT: vector=130 ") == 1 and " role=service " not in part,
                "Wrong root/site must be rejected before publishing the first request",
            )
        if service_probe:
            need(
                part.count("AURORA_UEFI_DOMAIN_EVENT: vector=130 ") == 2
                and part.count(" role=service ") == 1
                and "AURORA_APPEND_PARK:" not in part,
                "Wrong producer authority rejects its first Serve reply",
            )
        if mode == "program-append-backing":
            quiet = re.findall(r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ", part)
            need(bool(quiet), "Original-backing probe follows authenticated final drain")
            validate_append(part, mode, "originalsuffix", False, quiet[-1], images)
    if mode in ("program-append-root", "program-append-service-root"):
        arena = re.findall(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", full_text)
        need(len(arena) == 1, "Root probe retains one admitted arena")
        need(
            re.search(
                rf"AURORA_UEFI_DOMAIN_EVENT: vector=130 error=0 pc={pc} cpl=3 "
                rf"root={int(arena[0]) + LAYOUT.kernel_tables_offset} ",
                part,
            ),
            "Append actual-root probe must reach the wrong kernel CR3",
        )


def snapshot_service_program(path, mode):
    """Select existing probe data, never executable instructions or pinned bytes."""
    elf = Elf(path)
    symbols = [symbol for symbol in elf.symbols if symbol.name == "aurora_service_probe_mode"]
    need(len(symbols) == 1, "Unique defined snapshot service selector")
    symbol = symbols[0]
    need(
        symbol.kind == 1 and symbol.bind == 1 and symbol.size == 8 and 0 < symbol.section < len(elf.sections),
        "Bounded global selector object",
    )
    section = elf.sections[symbol.section]
    need(
        section.kind == 1
        and section.flags == SHF_ALLOC
        and section.address <= symbol.address <= section.address + section.size - 8,
        "Snapshot selector must be immutable allocated data",
    )
    segments = [
        segment
        for segment in elf.segments
        if segment.kind == 1 and segment.address <= symbol.address <= segment.address + segment.file_size - 8
    ]
    need(len(segments) == 1 and segments[0].flags == PF_R, "Snapshot selector read-only NX load segment")
    offset = section.offset + symbol.address - section.address
    need(
        offset == segments[0].offset + symbol.address - segments[0].address
        and 0 <= offset <= len(elf.data) - 8
        and elf.data[offset : offset + 8] == bytes(8),
        "Snapshot selector file bounds/default",
    )
    data = bytearray(elf.data)
    struct.pack_into("<Q", data, offset, mode)
    return bytes(data)


def production_case_volume(source, programs, directory, service_case=None):
    """Untrusted file payloads in a private ESP; the production kernel is unchanged."""
    target = directory / "esp"
    shutil.copytree(source, target)
    path = target / "aurora/system"
    data = path.read_bytes()
    _, _, _, count, stride, names, _, payload, _, _, _ = struct.unpack_from("<8sIIIIQQQQII", data)
    entries = []
    for index in range(count):
        name, length, _, offset, size = struct.unpack_from("<QIIQQ", data, 64 + index * stride)
        entries.append((data[names + name : names + name + length], data[payload + offset : payload + offset + size]))
    if service_case:
        if service_case == "console-commit":
            replacement = (programs / "console-commit-hostile-aurora").read_bytes()
        else:
            replacement = snapshot_service_program(
                programs / "process-isolation-6", 12 if service_case == "snapshot-read" else 13
            )
        need(sum(name == b"bin/file-service" for name, _ in entries) == 1, "Unique designated service file")
        entries = [(name, replacement if name == b"bin/file-service" else data) for name, data in entries]
        path.write_bytes(kernel_volume.volume(entries))
        return target
    for name, binary in (
        ("hostile", "process-hostile-aurora"),
        ("lifecycle", "process-lifecycle-aurora"),
        ("probe", "host-files-probe-aurora"),
        ("privileged", "process-isolation-3"),
        ("raw-write", "process-isolation-6"),
    ):
        entries.append((name.encode(), (programs / binary).read_bytes()))
    for name, edits in (
        ("wx", "p1.flags=7"),
        ("interp", "p3.type=3"),
        ("oversize", "p2.memsz=0xffffffffffffffff"),
        ("quota", "p2.memsz=0x8000000"),
    ):
        entries.append((name.encode(), kernel_volume.elf(edits)))
    entries.append((b"tree/seed", b""))
    path.write_bytes(kernel_volume.volume(entries))
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="program-console")
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--read-only-recovery", action="store_true")
    parser.add_argument("--append-recovery", action="store_true")
    parser.add_argument("--program-cases", type=Path, help="existing hostile program build products; private ESP only")
    parser.add_argument(
        "--service-case",
        choices=("snapshot-read", "snapshot-close", "console-commit"),
        help="private designated-service payload using --program-cases build products",
    )
    args = parser.parse_args()
    args.append_recovery |= args.mode in APPEND_RECOVERY_MODES or (
        args.mode.startswith("program-append-") and args.mode in APPEND_FAILSTOP_REASONS
    )
    need(
        not args.read_only_recovery or args.mode.endswith(("-fault", "-budget")),
        "Read-only recovery requires a fault or budget profile",
    )
    need(not (args.append_recovery and args.read_only_recovery), "Choose one recovery command")
    need(
        not args.append_recovery
        or args.mode.endswith(("-fault", "-budget"))
        or args.mode in APPEND_RECOVERY_MODES
        or args.mode in APPEND_FAILSTOP_REASONS,
        "Append recovery requires an existing fault/budget/hostile profile",
    )
    need(args.mode.startswith("program-"), "Expected a protected program-console profile")
    build = args.build_dir.resolve()
    need(not args.program_cases or args.mode == "program-console", "Program data cases require production")
    need(not args.service_case or args.program_cases, "Service data cases require existing program artifacts")
    user_images = json.loads((build / "user-images.json").read_text())
    if (build / "user-sets.json").exists():
        # A packed bank: the images this mode's row runs, by role.
        chosen = json.loads((build / "user-sets.json").read_text())[args.mode]
        user_images = {role: user_images[name] for role, name in chosen.items()}
    admitted = dict(
        user_images=user_images,
        timer=json.loads((build / "service-timer-metadata.json").read_text()),
    )
    evidence_root = ROOT / "build/program-console-evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=args.mode + "-guest-", dir=evidence_root))
    print("Protected-console guest evidence: " + str(output))

    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    if not qemu:
        raise Blocked("QEMU unavailable")
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
    esp = (
        production_case_volume(build / "esp", args.program_cases, output, args.service_case)
        if args.program_cases
        else build / "esp"
    )
    command = transport.profile_command(
        "uefi",
        args.mode,
        qemu,
        esp,
        os.environ.get("QEMU_DATA", ""),
        firmware=firmware,
        code=code,
        variables=variables,
    )
    master, slave = pty.openpty()
    tty.setraw(slave)
    transcript = bytearray()
    process = None
    deadline = time.monotonic() + (300 if args.program_cases else 180)
    expected_outputs = []
    expected_reads = {}
    expected_saves = {}
    expected_files = {}
    expected_store_losses = set()
    commands = 0
    metrics = {
        "status": "incomplete",
        "mode": args.mode,
        "read_only_recovery": args.read_only_recovery,
        "append_recovery": args.append_recovery,
        "clock": "tcg-original-clock",
        "purpose": "guest",
    }
    if args.service_case:
        metrics["service_case"] = args.service_case
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

            def file_append(name, suffix, expected, failure=False):
                nonlocal commands
                command = "append " + name + " " + suffix
                reply = f"wrote {name}: {len(suffix)} byte" + ("" if len(suffix) == 1 else "s")
                begin = len(transcript)
                send(command.encode("ascii") + b"\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).decode("ascii")
                expected_files[commands] = {"command": command, "value": expected, "reply": reply}
                commands += 1
                need(
                    "output> " not in part and "File saved." not in part,
                    "Append has only its existing named-file acknowledgment",
                )
                if failure:
                    need(reply not in part and "output discarded." in part, "Failed append must not publish")
                else:
                    need(
                        part.count("\r\n" + reply + "\r\n") == 1,
                        "Protected append keeps exact one-shot suffix-count acknowledgment",
                    )
                need("kind=append-file" in part, "Append must run real protected participants")

            def run_command(line, status, printed=b""):
                begin = len(transcript)
                send(line.encode("ascii") + b"\n")
                receive(b"aurora> ", begin)
                part = bytes(transcript[begin:]).replace(b"\r\n", b"\n")
                need(part.count(("run: " + status + "\n").encode()) == 1, "Run result: " + line)
                need(not printed or printed in part, "Run stdout/stderr: " + line)
                need(
                    b"AURORA_PROCESS_KERNEL_FAULT" not in part and b"AURORA_PROCESS_FAIL" not in part,
                    "Run escaped its process boundary",
                )
                return part

            def finish_session():
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
                        expected_store_losses,
                    ),
                    status="passed",
                    exit_status=process.returncode,
                )

            if serial_fixture_byte(args.mode):
                receive(b"AURORA_FIXTURE_READY", 0)
                send(bytes([FIXTURE_MODES[args.mode][1]]))
            receive(b"aurora> ", 0)
            tty.setraw(master)
            if args.service_case:
                if args.service_case.startswith("snapshot-"):
                    operation = 19 if args.service_case == "snapshot-read" else 20
                    for generation in (1, 2):
                        begin = len(transcript)
                        run_command("run bin/sort", "file service unavailable")
                        part = bytes(transcript[begin:]).decode("ascii")
                        need(
                            re.findall(r"AURORA_FILE_SERVICE_READY: generation=(\d+)\r?\n", part) == [str(generation)],
                            "Snapshot rollback must start a fresh source owner",
                        )
                        need(
                            re.findall(
                                r"AURORA_FILE_SERVICE_LOST: generation=(\d+) transaction=[1-9]\d* "
                                + "cause=invalid_reply operation="
                                + str(operation)
                                + r" volatile_data=lost\r?\n",
                                part,
                            )
                            == [str(generation)],
                            "Snapshot failure must lose exactly its own volatile service generation",
                        )
                        ready_at = part.index("AURORA_FILE_SERVICE_READY:")
                        need(
                            part[:ready_at].count("AURORA_PROCESS_LOADED:") == 1
                            and "AURORA_PROCESS_LOADED:" not in part[ready_at:]
                            and "invalid executable" not in part,
                            "Snapshot failure must load only its owner, never a client or malformed-ELF fallback",
                        )
                        command_upper(b"healthy after snapshot loss\n", "HEALTHY AFTER SNAPSHOT LOSS")
                else:
                    note_write(b"lower")
                    begin = len(transcript)
                    send(b"upper note\n")
                    receive(b"aurora> ", begin)
                    expected_saves[commands] = "LOWER"
                    expected_store_losses.add(commands)
                    commands += 1
                    note_read(None)
                    file_write("a", "lower")
                    begin = len(transcript)
                    send(b"upper a\n")
                    receive(b"aurora> ", begin)
                    expected_files[commands] = {"command": "upper a", "value": "LOWER"}
                    expected_store_losses.add(commands)
                    commands += 1
                    file_command("cat", "a", None)
                    command_upper(b"healthy after commit loss\n", "HEALTHY AFTER COMMIT LOSS")
                text = bytes(transcript).decode("ascii")
                ready = re.findall(r"AURORA_FILE_SERVICE_READY: generation=(\d+)\r?\n", text)
                lost = re.findall(
                    r"AURORA_FILE_SERVICE_LOST: generation=(\d+) transaction=[1-9]\d* "
                    r"cause=(invalid_reply operation=19|invalid_reply operation=20|exit status=0|consumer_rejected) "
                    r"volatile_data=lost\r?\n",
                    text,
                )
                expected_losses = (
                    [("1", "exit status=0"), ("2", "consumer_rejected")]
                    if args.service_case == "console-commit"
                    else [(str(generation), "invalid_reply operation=" + str(operation)) for generation in (1, 2)]
                )
                need(
                    ready == (["1", "2", "3"] if args.service_case == "console-commit" else ["1", "2"])
                    and lost == expected_losses
                    and text.count("AURORA_FILE_SERVICE_LOST:") == 2,
                    "Service restart/loss must follow exact causes without replay or stale generations",
                )
                need(
                    "AURORA_PROCESS_FAIL" not in text and "AURORA_PROCESS_KERNEL_FAULT" not in text,
                    "Service loss escaped snapshot/owner rollback audits",
                )
                finish_session()
                print("PASS: private service payload loss, fresh generations, no replay and healthy console exit")
                return
            if args.mode == "program-append-response":
                file_write("a", "prefix")
                begin = len(transcript)
                send(b"append a suffix\n")
                receive(b"AURORA_PROGRAM_APPEND_CLEARED: saved=0 revision=1 domains=0 leases=0\r\n", begin)
                need(transport.wait_exit(process, 5) == 35, "Failed append response did not take terminal exit")
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
                text = bytes(transcript).decode("ascii")
                part = bytes(transcript[begin:]).decode("ascii")
                settled = re.search(
                    r"AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=(\d+)\r\n"
                    r"AURORA_PROGRAM_APPEND_SETTLED: operation=1 revision=3\r\n"
                    r"wrote\r\nAURORA_PROGRAM_APPEND_RESPONSE_FAILED: committed=1 preserved=1\r\n"
                    r"AURORA_PROGRAM_APPEND_CLEARED: saved=0 revision=1 domains=0 leases=0\r\n$",
                    part,
                )
                need(settled, "Committed append, partial response, retained bytes and final clearing lack exact order")
                need(
                    part.count("AURORA_PROGRAM_COMMAND_BEGIN:") == part.count("AURORA_PROGRAM_COMMAND_END:") == 1
                    and part.count("kind=append-file") == part.count("AURORA_PROGRAM_APPEND_SETTLED:") == 1,
                    "Response failure replayed or changed the protected append",
                )
                validate_append(part, args.mode, "prefixsuffix", True, settled[1], admitted["user_images"])
                runs = re.findall(r"AURORA_UEFI_USER_RUN: epoch=(\d+) ", part)
                need(all(int(a) < int(b) for a, b in zip(runs, runs[1:])), "Response cut reused a runtime epoch")
                need(
                    all(
                        marker not in part
                        for marker in (
                            "aurora> ",
                            "wrote a:",
                            "File saved.",
                            "output> ",
                            "output discarded.",
                            "AURORA_CONSOLE_EXIT",
                            "AURORA_PROGRAM_CONSOLE_QUIET:",
                            "AURORA_UEFI_OK",
                            "_FAIL:",
                        )
                    ),
                    "Failed acknowledgment reported success, rollback, recovery or another prompt",
                )
                events = validate_domain_events(text, admitted["user_images"], admitted["timer"], returning=True)
                need(not any(event[0] == 6 for event in events), "Response cut was mistaken for a worker fault")
                metrics.update(
                    status="passed",
                    exit_status=35,
                    commands=1,
                    runs=len(runs),
                    committed_revision=3,
                    operation=1,
                    partial_response="wrote",
                    retained_then_cleared=True,
                )
                print("PASS: committed append survives actual partial response failure without replay; exit clears RAM")
                return
            if args.mode in FAILSTOP_REASONS or args.mode in APPEND_FAILSTOP_REASONS:
                if args.append_recovery:
                    file_write("hostile", "original")
                    begin = len(transcript)
                    send(b"append hostile suffix\n")
                else:
                    begin = len(transcript)
                    send(b"upper\n")
                    receive(b"text> ", begin)
                    begin = len(transcript)
                    send(b"hostile envelope\n")
                reason_text = (APPEND_FAILSTOP_REASONS if args.append_recovery else FAILSTOP_REASONS)[args.mode]
                reason = "AURORA_UEFI_RUNTIME_FAIL: " + reason_text
                receive((reason + "\r\n").encode(), begin)
                status = transport.wait_exit(process, 5)
                part = bytes(transcript[begin:]).decode("ascii")
                validate_failstop(
                    part,
                    args.mode,
                    status,
                    admitted["user_images"],
                    append=args.append_recovery,
                    full_text=bytes(transcript).decode("ascii"),
                )
                metrics.update(
                    status="passed",
                    exit_status=35,
                    failstop=reason_text,
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
                # A sequential consumer must not leave its allowance or terminal
                # state on the next one-shot caller incarnation.
                peek("alpha", "1")
                begin = len(transcript)
                send(b"exit\n")
                receive(b"AURORA_UEFI_OK", begin)
                need(transport.wait_exit(process, 5) == 33, "File-call normal guest exit")
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
                file_append("alpha", " Aurora", "Hello, Aurora")
                file_append("alpha", "", "Hello, Aurora")
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
                file_append("alpha", "", "")
                file_append("alpha", " spaced ", " spaced ")
                file_command("cat", "alpha", " spaced ")
                file_write("abcdefgh", "z" * 48)
                file_append("abcdefgh", "z", "z" * 49)
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
                file_append("alpha", "!", "full store!")
                file_command("upper", "alpha", "FULL STORE!")
                file_command("cat", "alpha", "FULL STORE!")
                file_command("cat", "beta", "Keep Lower")
                file_command("cat", "delta", "Last untouched")
                file_local("write alpha " + "q" * 50, "files: invalid name or content.")
                file_command("cat", "alpha", "FULL STORE!")
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
                file_append("pending", " append", "pending file append")
                file_command("upper", "pending", "PENDING FILE APPEND")
                file_command("cat", "pending", "PENDING FILE APPEND")
                file_command("cat", "other", "Remain lower")
                note_write(b"pending note")
                note_upper("PENDING NOTE")
                note_read("PENDING NOTE")
            else:
                file_write("recover", "recover this file")
                file_write("other", "Remain lower")
                if args.append_recovery:
                    file_write("empty", "")
                    file_write("fourth", "Last unchanged")
                    file_local("ls", "files: recover other empty fourth")
                if args.append_recovery:
                    file_append("recover", " appended", "recover this file appended", failure=True)
                elif args.read_only_recovery:
                    file_command("cat", "recover", "recover this file", failure=True)
                else:
                    file_command("upper", "recover", "RECOVER THIS FILE", failure=True)
                file_command("cat", "recover", "recover this file")
                file_command("cat", "other", "Remain lower")
                if args.append_recovery:
                    file_command("cat", "empty", "")
                    file_command("cat", "fourth", "Last unchanged")
                    file_local("ls", "files: recover other empty fourth")
                    file_append("recover", " appended", "recover this file appended")
                    file_command("cat", "recover", "recover this file appended")
                    file_write("recover", "recover this file")
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
            if args.mode == "program-console":
                # Real commands against the shipped volume and the one retained
                # service in this boot. No export, host linker or reboot occurs
                # between compiling the object, linking it and launching it.
                for line in ("run", "run   ", "run bin/sort 'x'", "run a b c d e f g h i j k l m n o p q"):
                    begin = len(transcript)
                    send(line.encode() + b"\n")
                    receive(b"aurora> ", begin)
                    part = bytes(transcript[begin:])
                    need(
                        b"Usage: run PATH" in part and b"AURORA_PROCESS_LOADED:" not in part,
                        "Malformed run launched a child",
                    )
                run_command("run absent", "program not found")
                run_command("run sort.au", "invalid executable or arguments")
                run_command("run bin/sort", "exited status=2", b"usage: host-sort DIRECTORY OUTPUT FILE...\n")
                run_command("run bin/cat / copied.txt input.txt", "exited status=0", b"input.txt 17\n")
                run_command("run bin/aurorac --emit-object --target aurora sort.au -o sort.o", "exited status=0")
                run_command("run bin/aurorac --link-object sort.o -o sorted", "exited status=0")
                run_command("run sorted / sorted.txt input.txt", "exited status=0", b"3 lines: 5 3 6\n")
                run_command("run bin/sort / again.txt sorted.txt", "exited status=0", b"3 lines: 5 3 6\n")
                # Naming the service executable cannot mint its sealed Serve
                # authority or replace the original namespace owner.
                run_command("run bin/file-service", "fault vector=6")
                run_command("run sorted / after.txt sorted.txt", "exited status=0", b"3 lines: 5 3 6\n")
                run_command("run bin/cat / copied.txt missing", "exited status=1", b"cannot open missing\n")
                run_command("run sorted / check.txt copied.txt", "exited status=0", b"3 lines: 5 3 6\n")
                run_command("run bin/cat / sorted input.txt", "exited status=0", b"input.txt 17\n")
                run_command("run sorted", "invalid executable or arguments")
                run_command("run bin/sort / final.txt input.txt", "exited status=0", b"3 lines: 5 3 6\n")
                need(
                    bytes(transcript).count(b"AURORA_FILE_SERVICE_READY:") == 1,
                    "Run commands did not retain one service incarnation",
                )
                command_upper(b"healthy after processes\n", "HEALTHY AFTER PROCESSES")
                metrics["same_boot_compile_link_run"] = True
                if args.program_cases:
                    for line, status in (
                        ("run wx", "invalid executable or arguments"),
                        ("run interp", "invalid executable or arguments"),
                        ("run oversize", "invalid executable or arguments"),
                        ("run quota", "resource quota exceeded"),
                        ("run privileged", "fault vector=13"),
                        ("run lifecycle fault", "fault vector=6"),
                        ("run hostile spin", "watchdog"),
                    ):
                        run_command(line, status)
                        command_upper(b"healthy after child\n", "HEALTHY AFTER CHILD")
                        run_command("run bin/sort / final.txt input.txt", "exited status=0", b"3 lines: 5 3 6\n")
                    # Reuse after close and a foreign guessed id are ordinary
                    # client data, not a kernel test hook.
                    run_command(
                        "run probe file input.txt close @1 read @1 0", "exited status=0", b"3 read invalid_handle 0 "
                    )
                    run_command("run probe read 65 0", "exited status=0", b"1 read invalid_handle 0 ")
                    # One raw 64 KiB call crosses two authenticated service messages.
                    # The existing client reopens and checks every committed byte.
                    run_command("run raw-write", "exited status=0")
                    run_command("run lifecycle rpc", "watchdog")
                    run_command("run probe file tree/rpc-pending", "exited status=0", b"1 file not_found 0 ")
                    run_command("run bin/sort / final.txt input.txt", "exited status=0", b"3 lines: 5 3 6\n")
                    command_upper(b"healthy after hostile programs\n", "HEALTHY AFTER HOSTILE PROGRAMS")
                    metrics["hostile_program_data"] = True
            finish_session()
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
    except Blocked as error:
        print("BLOCKED: program console PTY: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        raise SystemExit("FAIL: program console PTY: " + str(error)) from error

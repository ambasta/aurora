#!/usr/bin/env python3
"""Strict copied scratchpad transcript oracle; every run/debit/IRQ/output is consumed.

Expected user commands come from the PTY plan, never from a guest-controlled
success marker. This is test expectation data, not a native file implementation.
"""

from pathlib import Path
import copy
import importlib.util
import re

spec = importlib.util.spec_from_file_location(
    "scratchpad_user_phases", Path(__file__).with_name("kernel-uefi-user-phases-smoke.py")
)
phases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phases)
budget, need, LAYOUT = phases.budget, phases.need, phases.LAYOUT
READY = "AURORA_RAM_SCRATCHPAD_READY: 49-byte session scratchpad; all data is lost on service reset or session exit."
HELP = (
    "put [text]  Replace the session scratchpad (0..49 printable ASCII bytes)\n"
    "append [text]  Append to the existing scratchpad (total at most 49 bytes)\n"
    "get         Read the session scratchpad\n"
    "crc         Compute CRC32C of the session scratchpad\n"
    "help        Show commands\n"
    "status      Show static capacity and service availability\n"
    "exit        Close this session and discard all data"
)
STATUS = "status: capacity=49 printable ASCII bytes; command ceiling=64; retained service=available"
INVALID = "Invalid command. Type help; put/append accept at most 49 printable ASCII bytes."
ABORTED = "aborted: previous data retained"
READ_FAILED = "read failed: output discarded"
COMMITTED_FAILED = "committed; caller failed: do not retry automatically"
INDETERMINATE = "commit indeterminate; service reset: all data lost; do not retry automatically"
RESET = "service reset: all data lost"
LIMIT = "command limit reached; session closed"
NAMED_READY = "AURORA_NAMESPACE_READY: four named RAM files; all data is lost on owner reset or session exit."
NAMED_HELP = (
    "write NAME TEXT  Write a named RAM file (0..49 printable ASCII bytes)\n"
    "cat NAME         Read a named RAM file\n"
    "help             Show commands\n"
    "status           Show static capacity and owner availability\n"
    "exit             Close this session and discard all data"
)
NAMED_STATUS = (
    "status: capacity=4 files; names=1..8 characters; values=0..49 printable ASCII bytes; "
    "command ceiling=64; retained owner=available"
)
NAMED_INVALID = "Invalid command, name or content. Type help; note is reserved."
LINE_REJECTED = "Line rejected: too long, non-ASCII/control byte, or UART error."
NAMED_MISSING = "files: not found (RAM-only)."
NAMED_RESET = "owner reset: all data lost"
NAMED_INDETERMINATE = "commit indeterminate; owner reset: all data lost; do not retry automatically"
NAMED_UNAVAILABLE = "namespace unavailable; session closed"


def validate(status, text, plan, metadata, *, fixture=False, namespace=False, case="normal"):
    need(type(status) is int and type(text) is str and isinstance(plan, list) and plan, "Scratchpad receipt types")
    cleaned = copy.deepcopy(metadata)
    call_pc = cleaned["images"]["clean"].pop("call_pc")
    serve_pc = cleaned["images"]["bounds"].pop("serve_pc")
    budget.metadata_valid(cleaned, "namespace-console" if namespace else "user-call")
    for name, pc in (("clean", call_pc), ("bounds", serve_pc)):
        row = cleaned["images"][name]
        need(type(pc) is int and row["return_pc"] + 4 <= pc < row["compiled_begin"], "Scratchpad exact role site")
    # Only startup may contain QEMU's documented ONLCR duplication. Once the
    # first prompt is observed, the runner resets its private PTY to raw mode.
    boundary = text.find("aurora> ")
    startup_failure = namespace and case == "d"
    need(
        (startup_failure and boundary == -1) or (boundary >= 0 and "\r" not in text[boundary:].replace("\r\n", "\n")),
        "Scratchpad command output contains a non-CRLF carriage return",
    )
    if plan[-1]["effect"] == "timeout":
        prefix = "NAMESPACE" if namespace else "SCRATCHPAD"
        partial = "wrote" if namespace else "sa"
        need(
            re.search(rf"AURORA_{prefix}_SETTLED: command=2 used=4 service=1\r\n{partial}\Z", text) is not None,
            "Timeout output is byte-exact then EOF, with no additional CR or retry",
        )
    text = text.replace("\r", "")
    # Both scratchpad rows boot storage-fixture, whose loader echoes the row first.
    mode = ("namespace-console" if namespace else "ram-scratchpad-console") + ("-fixture" if fixture else "")
    text = phases.loader_selection(text, mode)
    lines = text.splitlines()
    start = next(
        (
            i
            for i, row in enumerate(lines)
            if row.startswith(
                (
                    "AURORA_UEFI_TIMER_",
                    "AURORA_SCRATCHPAD",
                    "AURORA_NAMESPACE",
                    "AURORA_RAM_FILE",
                    "AURORA_UEFI_USER_",
                    "AURORA_UEFI_DOMAIN_",
                    "AURORA_UEFI_RUNTIME_",
                )
            )
        ),
        None,
    )
    need(start is not None, "Scratchpad admitted timer missing")
    prefix = "\n".join(lines[:start]) + "\n"
    budget.firmware_prefix(prefix, "budget")
    need(
        start > 0 and re.fullmatch(r"AURORA_PCI_WINDOW_CLOSED: reads=\d+", lines[start - 1]) is not None,
        "No unconsumed bytes between the validated firmware prefix and runtime",
    )
    arena = int(re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", prefix)[1])
    kernel = arena + LAYOUT.kernel_tables_offset
    roots = [arena + LAYOUT.tables_offset, arena + LAYOUT.tables_offset + LAYOUT.table_pages * LAYOUT.page_size]
    records = lines[start:]
    position = 0

    def peek():
        return records[position] if position < len(records) else ""

    def take(wanted):
        nonlocal position
        need(peek() == wanted, "Scratchpad sequence expected " + repr(wanted) + "; got " + repr(peek()))
        position += 1

    run, segment, _ = phases.ram_run_parser(take, peek, arena, metadata, call_pc, serve_pc, mode)
    marker = "NAMESPACE" if namespace else "SCRATCHPAD"

    take(f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual={budget.APIC} id=0 root={kernel}")
    if fixture:
        take(f"AURORA_{marker}_FIXTURE_READY")
    epoch = 1
    run(1, epoch, 1, 0, 8)
    segment(1, epoch, 8, exhausted=startup_failure)
    if startup_failure:
        take("AURORA_RAM_FILE_RESET: outcome=reset data_lost=1")
        take(NAMED_UNAVAILABLE)
        take("AURORA_NAMESPACE_EXIT: used=0 volatile=1")
        take("AURORA_UEFI_LANGUAGE_OK: value=42")
        take("AURORA_UEFI_OK")
        need(status == 33 and position == len(records), "Failed startup retires all owners without a prompt")
        return {"commands": 0, "service_generations": 1, "verified_teardown": True, "startup_exhausted": True}
    take(NAMED_READY if namespace else READY)
    generation, caller, ticket, commands = 1, 2, 0, 0
    ended = False
    for step in plan:
        fields = {"command", "reply", "exchanges", "effect"}
        need(set(step) == fields or (namespace and set(step) == fields | {"echo"}), "Closed command-plan shape")
        command, reply, count, effect = (step[key] for key in ("command", "reply", "exchanges", "effect"))
        need(
            type(command) is str and type(reply) is str and type(count) is int and 0 <= count <= 51,
            "Command-plan values",
        )
        take("aurora> " + step.get("echo", command))
        if effect == "local":
            need(count == 0, "Local command admitted no protected exchanges")
            for row in reply.split("\n"):
                take(row)
            continue
        if effect == "limit":
            need(commands == 64 and count == 0 and reply == LIMIT, "Exact command ceiling")
            take(LIMIT)
            ended = True
            break
        need(
            effect
            in {
                "normal",
                "preloss",
                "readloss",
                "commitloss",
                "servicefault",
                "badresult",
                "reset",
                "backing",
                "timeout",
                *(
                    {"ownerfault", "callerbudget", "ownerbudget", "abortbudget", "callerwait", "servicewait"}
                    if namespace
                    else set()
                ),
            },
            "Unknown fixture effect",
        )
        need(fixture or effect == "normal", "Production cannot select a fault fixture")
        commands += 1
        need(
            commands <= 64
            and (
                count == 0
                if effect == "callerbudget"
                else count >= (1 if command.startswith("append") and reply == "rejected" else 2)
            ),
            "Bounded protected command",
        )
        if effect != "normal":
            need(commands == 2, "Fixture acts exactly once on second admitted command")
        cleanup, client_epoch = epoch + 1, epoch + 2
        epoch = client_epoch
        caller += 1
        ticket += 1
        take(f"AURORA_{marker}_BEGIN: command={commands} caller={caller} service={generation} root={roots[1]}")
        run(0, client_epoch, 0, 0, 128)
        caller_used = caller_compiled = service_used = service_compiled = 0
        for exchange in range(count):
            caller_used, caller_compiled = segment(0, client_epoch, 128, caller_used, caller_compiled)
            ticket += 1
            epoch += 1
            run(1, epoch, 2, ticket, 120 - service_used)
            last = exchange == count - 1
            service_used, current_compiled = segment(
                1,
                epoch,
                120,
                service_used,
                terminal=6 if effect in {"servicefault", "ownerfault"} and last else 130,
                exhausted=effect == "ownerbudget" and last,
            )
            service_compiled += current_compiled
        disposed = effect in {
            "preloss",
            "readloss",
            "commitloss",
            "servicefault",
            "ownerfault",
            "ownerbudget",
            "abortbudget",
        }
        if namespace and effect in {"preloss", "commitloss"}:
            segment(0, client_epoch, 128, caller_used, caller_compiled, terminal=6)
        elif effect == "callerbudget":
            segment(0, client_epoch, 128, caller_used, caller_compiled, exhausted=True)
        elif not disposed:
            segment(0, client_epoch, 128, caller_used, caller_compiled, terminal=129)
        if effect == "callerwait":
            need(caller_compiled > 0, "Finite caller fixture needs actual compiled-PC hardware progress")
        if effect == "servicewait":
            need(service_compiled > 0, "Finite owner fixture needs actual compiled-PC hardware progress")
        if effect in {"preloss", "readloss", "callerbudget", "abortbudget"}:
            if namespace:
                need(reply == (NAMED_RESET if effect == "abortbudget" else ABORTED), "Namespace precommit outcome")
            else:
                need(count == (2 if effect == "preloss" else 3) and reply == ABORTED, "Exact precommit disposal")
            run(1, cleanup, 3, 0, 8)
            segment(1, cleanup, 8, exhausted=effect == "abortbudget")
        if effect in {"servicefault", "reset", "ownerfault", "ownerbudget", "abortbudget"}:
            outcome = "indeterminate" if effect == "servicefault" else "reset"
            take(f"AURORA_RAM_FILE_RESET: outcome={outcome} data_lost=1")
            epoch += 1
            generation += 1
            caller += 2
            run(1, epoch, 1, 0, 8)
            segment(1, epoch, 8)
        elif effect == "backing":
            take(
                "AURORA_UEFI_RUNTIME_FAIL: "
                + ("namespace" if namespace else "scratchpad")
                + " original command physically retired"
            )
            need(status == 35 and position == len(records), "Stale backing fails before output or prompt")
            return {
                "commands": commands,
                "service_generations": generation,
                "verified_teardown": False,
                "fail_closed": True,
            }
        else:
            take(f"AURORA_{marker}_SETTLED: command={commands} used=4 service={generation}")
        for row in reply.split("\n"):
            take(row)
        if effect == "timeout":
            need(
                reply == ("wrote" if namespace else "sa") and status == 33 and position == len(records),
                "Output timeout has no retry/trailing bytes",
            )
            return {
                "commands": commands,
                "service_generations": generation,
                "verified_teardown": True,
                "output_timeout": True,
            }
    if not ended:
        take("aurora> exit")
        take("AURORA_CONSOLE_EXIT")
    take("AURORA_NAMESPACE_EXIT: used=0 volatile=1" if namespace else "AURORA_RAM_SCRATCHPAD_EXIT: used=0 volatile=1")
    take("AURORA_UEFI_LANGUAGE_OK: value=42")
    take("AURORA_UEFI_OK")
    need(status == 33 and position == len(records), "Exact scratchpad exit and no trailing records")
    return {"commands": commands, "service_generations": generation, "verified_teardown": True}

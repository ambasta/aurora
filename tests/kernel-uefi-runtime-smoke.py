#!/usr/bin/env python3
from pathlib import Path
import importlib.util, json, re, sys, copy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from kernel_layout import LAYOUT

spec = importlib.util.spec_from_file_location("pci", Path(__file__).with_name("kernel-pci-smoke.py"))
pci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pci)
need = pci.need
SUCCESS_MODES = ("runtime", "runtime-span", "runtime-multipage")
MODES = SUCCESS_MODES + (
    "runtime-terminal-input",
    "runtime-terminal-output",
    "runtime-code",
    "runtime-stack",
    "runtime-kernel",
    "runtime-window",
    "runtime-root",
    "runtime-kernel-trap",
    "runtime-entry-stack",
    "runtime-write",
    "runtime-nx",
    "runtime-return",
    "runtime-unknown",
    "runtime-syscall",
    "runtime-sysenter",
)
BASE = LAYOUT.user_code
STACK = LAYOUT.user_stack_bottom
SUFFIX = "AURORA_UEFI_LANGUAGE_OK: value=42\nAURORA_UEFI_OK\n"


def run_console_region(command, log, mode):
    # Reuse the owned QEMU transport; send each byte only after a live-owner park.
    import os, select, subprocess, time

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import qemu_transport as transport
    from kernel_profiles import FIXTURE_MODES

    startup_byte = FIXTURE_MODES.get(mode, ("", None))[1]
    startup_sent = startup_byte is None

    payload = b"x" if mode.endswith(("cancel-ready", "fault")) else b"abcdefghijklmnopqrstuvwxyz012345\n"
    transcript = bytearray()
    process = None
    sent = 0
    deadline = time.monotonic() + 30
    try:
        process = transport.start(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while True:
            ready = select.select([process.stdout], [], [], transport.remaining(deadline))[0]
            need(ready, "Protected console read deadline")
            data = os.read(process.stdout.fileno(), 65536)
            if not data:
                break
            transcript.extend(data)
            if not startup_sent:
                startup_sent = transport.send_startup_byte(process.stdin, startup_byte, transcript)
            need(len(transcript) < 1048576, "Bounded protected console transcript")
            parks = re.findall(
                rb"AURORA_CONSOLE_PARK: ticket=(\d+) live=1 used=32 epoch=(\d+) ticks=(\d+) remaining=(\d+)\r?\n",
                transcript,
            )
            if len(parks) > sent:
                need(len(parks) == sent + 1 and sent < len(payload), "Exactly one pending read per input byte")
                process.stdin.write(payload[sent : sent + 1])
                process.stdin.flush()
                sent += 1
        status = transport.reap_completed(process, deadline)
        need(startup_sent, "Fixture requested its boot selector")
        need(sent == len(payload), "Whole bounded line delivered after live-owner parks")
        return status
    finally:
        log.write_bytes(transcript)
        errors, _, _ = transport.finish(process, streams=[process.stdin, process.stdout] if process else [])
        need(not errors, "Protected console transport cleanup: " + "; ".join(errors))


def validate_console_region(status, text, metadata, mode):
    """Check observable output and cleanup; native tests own scheduling transitions."""
    text = text.replace("\r", "")
    validate_region_metadata(metadata, True)
    need(status == 33 and text.endswith(SUFFIX), "Protected console natural successful exit")
    arenas = re.findall(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+) bytes=1048576 descriptors=\d+", text)
    need(len(arenas) == 1, "Single protected application arena")
    arena = int(arenas[0])
    incarnations = 2 if mode.endswith("cancel") else 1
    image = metadata["clean"]
    events = re.findall(
        r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)\n",
        text,
    )
    need(len(events) == text.count("AURORA_UEFI_DOMAIN_EVENT:"), "Canonical event records")
    returned = faults = 0
    for values in events:
        vector, error, pc, cpl, root, frame, cr2 = map(int, values)
        need(
            error == cr2 == 0
            and cpl == 3
            and root == arena + LAYOUT.tables_offset
            and frame == arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size,
            "Exact application trap authority",
        )
        need(
            (vector == 64 and BASE <= pc < BASE + image["size"])
            or (vector == 129 and pc == image["return_pc"])
            or (mode.endswith("fault") and vector == 6 and pc == image["bounds_pc"]),
            "Exact admitted continuation or terminal site",
        )
        returned += vector == 129
        faults += vector == 6
    need(
        returned == int(not mode.endswith(("cancel", "cancel-ready", "budget", "fault"))),
        "Exactly one expected terminal return",
    )
    need(faults == int(mode.endswith("fault")), "Exact compiler fault count")
    arms = re.findall(r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=\d+\n", text)
    need(
        arms == [(str(i), "128") for i in range(1, incarnations + 1)]
        and text.count("AURORA_UEFI_TIMER_ARM:") == incarnations,
        "One initial budget per incarnation",
    )
    parks = re.findall(
        r"AURORA_CONSOLE_PARK: ticket=(\d+) live=1 used=32 epoch=(\d+) ticks=(\d+) remaining=(\d+)\n", text
    )
    expected_parks = (
        0 if mode.endswith("budget") else 1 if mode.endswith(("cancel", "cancel-ready", "input", "fault")) else 33
    )
    need(
        len(parks) == expected_parks * incarnations
        and text.count("AURORA_CONSOLE_PARK:") == expected_parks * incarnations,
        "Live allocation across every input wait",
    )
    previous = 0
    for index, values in enumerate(parks):
        ticket, epoch, ticks, remaining = map(int, values)
        need(
            ticket == index + 1
            and epoch == (index + 1 if incarnations == 2 else 1)
            and (0 if incarnations == 2 else previous) < ticks < 128
            and ticks + remaining == 128,
            "Monotone tickets and original cumulative budget",
        )
        previous = ticks
    abandoned = int(mode.endswith(("cancel", "cancel-ready", "budget", "fault")))
    value = 2 if mode.endswith("input") else 3 if mode.endswith("output") else 0
    event = 2 if mode.endswith("fault") else 0 if abandoned else 1
    exhausted = int(mode.endswith("budget"))
    expected = (
        rf"AURORA_CONSOLE_REGION_DONE: value={value} event={event} exhausted={exhausted}"
        rf" ticks=(\d+) remaining=(\d+) abandoned={abandoned} peak=32 used=0 pages=0" + "\n"
    )
    done = re.findall(expected, text)
    need(
        len(done) == incarnations and text.count("AURORA_CONSOLE_REGION_DONE:") == incarnations,
        "Exact result and reclamation",
    )
    need(
        all(int(ticks) + int(remaining) == 128 for ticks, remaining in done),
        "Each incarnation budget remains cumulative",
    )
    ticks, remaining = map(int, done[-1])
    need(
        ticks >= previous and ticks + remaining == 128 and (remaining == 0) == bool(exhausted),
        "No budget renewal after resume",
    )
    execution = text[text.index("AURORA_UEFI_TIMER_ARM:") :]
    output = re.sub(r"AURORA_[^\n]*\n", "", execution)
    expected_output = (
        "AB"
        if mode.endswith("output")
        else "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345\n"
        if mode == "runtime-console-region"
        else ""
    )
    need(output == expected_output, "Exact source-produced output across the whole execution")
    need("_FAIL:" not in text, "No concealed runtime failure")
    need(
        metadata["clean"]["size"] <= LAYOUT.image_slot_bytes and metadata["clean"]["user_stack"] <= LAYOUT.stack_cap,
        "Unchanged user caps",
    )
    print("PASS: protected console waits, original budget, result and reclamation: " + mode)


def validate_region_metadata(metadata, console_region=False):
    need(type(metadata) is dict and set(metadata) == {"clean", "bounds"}, "Owned text exact image inventory")
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
    }
    operations = ("allocate", "borrow_length", "at", "set", "resize", "drop")
    extra = {"bytes_" + name + "_pc" for name in operations} | {"user_stack", "compiled_begin", "compiled_end"}
    if console_region:
        extra |= {"console_next_pc", "console_put_pc"}
    for index, name in enumerate(("clean", "bounds")):
        image = metadata[name]
        need(
            type(image) is dict
            and set(image) == keys | (extra if index == 0 else set())
            and all(type(value) is int and 0 <= value < 1 << 64 for value in image.values()),
            "Exact owned text metadata",
        )
        base = BASE + index * LAYOUT.code_stride
        need(
            image["entry"] == base
            and (
                (0 if console_region else 8192) < image["size"] <= LAYOUT.image_slot_bytes
                if index == 0
                else 4 <= image["size"] <= 4096
            ),
            "Owned text image bounds",
        )
        sites = [image[key] for key in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")]
        need(
            all(sites[:3])
            and len(set(pc for pc in sites if pc)) == len([pc for pc in sites if pc])
            and all(pc == 0 or base <= pc <= base + image["size"] - 2 for pc in sites),
            "Owned text exact fault sites",
        )
        need(image["probe_offset"] == image["probe_pc"] == 0, "No owned text probe pointers")
    image = metadata["clean"]
    sites = {image["bytes_" + name + "_pc"] for name in operations}
    if console_region:
        sites |= {image["console_next_pc"], image["console_put_pc"]}
    need(
        len(sites) == (8 if console_region else 6)
        and all(BASE <= pc < BASE + image["size"] for pc in sites)
        and 0 < image["user_stack"] <= LAYOUT.stack_cap
        and BASE <= image["compiled_begin"] < image["compiled_end"] <= BASE + image["size"],
        "Owned text linked stack and six byte sites",
    )


def validate_owned_text(status, text, metadata, mode):
    denied = mode != "runtime-owned-text"
    need(type(status) is int and status == (35 if denied else 33), "Owned text exact exit")
    validate_region_metadata(metadata)
    image = metadata["clean"]
    sites = {value for key, value in image.items() if key.startswith("bytes_")}
    owned = re.findall(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+) bytes=1048576 descriptors=\d+", text)
    need(len(owned) == 1, "One owned arena")
    arena = int(owned[0])
    kernel, domain = arena + LAYOUT.kernel_tables_offset, arena + LAYOUT.tables_offset
    ready = re.findall(
        r"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual=18446620928407240704 id=0 root=(\d+)", text
    )
    need(ready == [str(kernel)] and text.count("AURORA_UEFI_TIMER_READY:") == 1, "Owned text admitted timer root")
    if denied:
        reasons = {
            "runtime-owned-text-site": "text exact operation site",
            "runtime-owned-text-region": "text private region binding",
            "runtime-owned-text-stale": "owned text allocator invariant",
        }
        need(
            mode in reasons and text.endswith("AURORA_UEFI_RUNTIME_FAIL: " + reasons[mode] + "\n"),
            "Exact hostile denial",
        )
        need(
            text.count("AURORA_UEFI_RUNTIME_FAIL:") == 1
            and "AURORA_OWNED_TEXT_CASE:" not in text
            and "AURORA_OWNED_TEXT_OK" not in text
            and "AURORA_UEFI_TIMER_QUIET:" not in text,
            "No false cleanup on fail-stop",
        )
        arm = f"AURORA_UEFI_TIMER_ARM: epoch=1 budget=128 root={domain}\n"
        need(text.count("AURORA_UEFI_TIMER_ARM:") == 1 and arm in text, "Denial original budget")
        events = list(
            re.finditer(
                r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) "
                r"cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)\n",
                text,
            )
        )
        need(events and len(events) == text.count("AURORA_UEFI_DOMAIN_EVENT:"), "Denial trap evidence")
        ticks = 0
        for event in events:
            vector, error, pc, cpl, root, frame, cr2 = map(int, event.groups())
            need(
                vector in (64, 130)
                and error == cr2 == 0
                and (pc in sites if vector == 130 else BASE <= pc < BASE + image["size"])
                and cpl == 3
                and root == domain
                and frame % 8 == 0
                and arena + LAYOUT.rsp0_bottom <= frame <= arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size
                and text.index(arm) < event.start(),
                "Authenticated denial trap",
            )
            if vector == 64:
                ticks += 1
                tick = re.match(
                    r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=(\d+) remaining=(\d+) pc=(\d+) flags=(\d+)\n",
                    text[event.end() :],
                )
                need(tick is not None, "Denial hardware debit")
                epoch, used, remaining, tick_pc, flags = map(int, tick.groups())
                need(
                    (epoch, used, remaining, tick_pc) == (1, ticks, 128 - ticks, pc)
                    and ticks < 128
                    and flags & 0x202 == 0x202
                    and flags & ~LAYOUT.allowed_user_flags == 0,
                    "Denial conserved budget",
                )
        need(text.count("AURORA_UEFI_TIMER_TICK:") == ticks, "No unmatched denial debit")
        final_operation = "set" if mode.endswith("stale") else "allocate"
        need(int(events[-1][3]) == image["bytes_" + final_operation + "_pc"], "Exact denied operation")
        need(int(events[-1][1]) == 130 and SUFFIX not in text, "No forged denial completion")
        if mode.endswith("stale"):
            resize = [event for event in events if int(event[1]) == 130 and int(event[3]) == image["bytes_resize_pc"]]
            need(
                resize
                and resize[-1].start()
                < events[-1].start()
                < text.index("AURORA_OWNED_TEXT_STALE: committed-resize")
                < text.index("AURORA_OWNED_TEXT_FAULT: reason=1")
                < text.index("AURORA_UEFI_RUNTIME_FAIL:"),
                "Ordered committed stale replay",
            )
            need(text.count("AURORA_OWNED_TEXT_FAULT:") == 1, "Single allocator denial")
            need(
                text.count("AURORA_OWNED_TEXT_STALE: committed-resize") == 1
                and text.count("AURORA_OWNED_TEXT_FAULT: reason=1") == 1,
                "Actual stale descriptor after committed resize",
            )
        else:
            need("AURORA_OWNED_TEXT_FAULT:" not in text, "Binding denied before allocator")
        print("PASS: protected owned text hostile authority denied: " + mode)
        return
    need(
        text.endswith(SUFFIX)
        and not any(word in text for word in ("_FAIL:", "AURORA_OWNED_TEXT_FAULT:", "AURORA_OWNED_TEXT_STALE:")),
        "Owned text clean firmware completion",
    )
    patterns = {
        "ARM": r"AURORA_UEFI_TIMER_ARM: epoch=(\d+) budget=(\d+) root=(\d+)",
        "EVENT": r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) "
        r"cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)",
        "TICK": r"AURORA_UEFI_TIMER_TICK: epoch=(\d+) used=(\d+) remaining=(\d+) pc=(\d+) flags=(\d+)",
        "DRAIN": r"AURORA_UEFI_TIMER_DRAIN: epoch=(\d+) root=(\d+) ss=(\d+)",
        "QUIET": r"AURORA_UEFI_TIMER_QUIET: epoch=(\d+) ticks=(\d+) drains=(\d+) "
        r"compiled=(\d+) context=(\d+) root=(\d+)",
        "CASE": r"AURORA_OWNED_TEXT_CASE: scalar=(\d+) abandoned=(\d+) value=(\d+) "
        r"live=(\d+) peak=(\d+) ticks=(\d+) used=0 pages=0",
        "OK": r"AURORA_OWNED_TEXT_OK",
    }
    records = []
    for line in text.splitlines():
        if line.startswith("AURORA_UEFI_TIMER_READY:"):
            continue
        if line.startswith(("AURORA_UEFI_TIMER_", "AURORA_UEFI_DOMAIN_", "AURORA_UEFI_RUNTIME_", "AURORA_OWNED_TEXT_")):
            matches = [(kind, re.fullmatch(pattern, line)) for kind, pattern in patterns.items()]
            matches = [(kind, tuple(map(int, match.groups()))) for kind, match in matches if match]
            need(len(matches) == 1, "Unknown or malformed owned text runtime record")
            records.append(matches[0])
    cursor, seen_sites = 0, set()
    cases = ((128578, 0, 70), (55296, 0, 0), (1114114, 0, 65), (1114112, 1, None), (1114113, 1, None))
    for epoch, (scalar, abandoned, value) in enumerate(cases, 1):
        need(
            cursor < len(records) and records[cursor] == ("ARM", (epoch, 128, domain)),
            "One original budget per incarnation",
        )
        cursor += 1
        ticks, drains, compiled, terminal = 0, 0, 0, False
        while cursor < len(records) and records[cursor][0] == "EVENT":
            vector, error, pc, cpl, root, frame, cr2 = records[cursor][1]
            cursor += 1
            need(error == 0 and cr2 == 0 and frame % 8 == 0, "Exact owned text exception state")
            if cpl == 0:
                need(
                    terminal
                    and vector == 64
                    and root == kernel
                    and arena + LAYOUT.kernel_stack_bottom
                    <= frame
                    <= arena + LAYOUT.kernel_stack_top - LAYOUT.fault_frame_size,
                    "Only quiescent pending IRQ may enter from kernel",
                )
                need(
                    cursor < len(records) and records[cursor] == ("DRAIN", (epoch, kernel, 16)),
                    "Authenticated pending IRQ drain",
                )
                cursor += 1
                drains += 1
                continue
            need(
                not terminal
                and cpl == 3
                and root == domain
                and arena + LAYOUT.rsp0_bottom <= frame <= arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size,
                "Live owned domain exception authority",
            )
            if vector == 130:
                need(pc in sites, "Exact byte operation PC")
                seen_sites.add(pc)
            elif vector == 64:
                need(
                    BASE <= pc < BASE + image["size"] and cursor < len(records) and records[cursor][0] == "TICK",
                    "Hardware timer debit",
                )
                tick_epoch, used, remaining, tick_pc, flags = records[cursor][1]
                cursor += 1
                ticks += 1
                need(
                    (tick_epoch, used, remaining, tick_pc) == (epoch, ticks, 128 - ticks, pc)
                    and ticks <= 128
                    and flags & 0x202 == 0x202
                    and flags & ~LAYOUT.allowed_user_flags == 0,
                    "Contiguous conserved budget",
                )
                compiled += image["compiled_begin"] <= pc < image["compiled_end"]
                terminal = ticks == 128
                need(not terminal or scalar == 1114113, "Only deliberate live-owner loop exhausts budget")
            else:
                need(
                    vector == (6 if scalar == 1114112 else 129)
                    and scalar != 1114113
                    and pc == image["bounds_pc" if scalar == 1114112 else "return_pc"],
                    "Exact source terminal site",
                )
                terminal = True
        need(
            terminal
            and cursor < len(records)
            and records[cursor] == ("QUIET", (epoch, ticks, drains, compiled, 0, kernel)),
            "Drained terminal with exact cumulative budget",
        )
        cursor += 1
        need(cursor < len(records) and records[cursor][0] == "CASE", "Reclamation follows quiescence")
        actual_scalar, actual_abandoned, actual_value, live, peak, actual_ticks = records[cursor][1]
        cursor += 1
        need(
            (actual_scalar, actual_abandoned, actual_ticks) == (scalar, abandoned, ticks)
            and (value is None or actual_value == value)
            and live == abandoned
            and 1 <= peak <= 64
            and (scalar != 1114114 or peak == 64),
            "Source result, quota rollback and abandoned owner evidence",
        )
    need(
        records[cursor:] == [("OK", ())] and seen_sites == sites,
        "Exact completion after all six actual byte operations",
    )
    print("PASS: protected Utf8Text returns, quota rollback, fault/budget and quiescent reclamation")


def validate(status, text, mode, metadata, *, retained=0, final_slot=0):
    if mode.startswith("runtime-console-region"):
        return validate_console_region(status, text, metadata, mode)
    if mode.startswith("runtime-owned-text"):
        return validate_owned_text(status, text, metadata, mode)
    need(type(retained) is int and retained in (0, 2), "Invalid retained pin count")
    need(type(final_slot) is int and final_slot in (0, 1) and (final_slot == 0 or retained == 2), "Invalid final slot")
    need(mode in MODES, "Unknown runtime mode")
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
    }
    need(type(metadata) is dict and set(metadata) == {"clean", "bounds"}, "Malformed metadata set")
    for index, name in enumerate(("clean", "bounds")):
        image = metadata[name]
        need(
            type(image) is dict
            and set(image) == keys
            and all(type(v) is int and 0 <= v < 1 << 64 for v in image.values()),
            "Malformed metadata values",
        )
        base = BASE + index * LAYOUT.code_stride
        size = image["size"]
        need(
            image["entry"] == base
            and (8192 < size <= LAYOUT.image_slot_bytes if mode == "runtime-multipage" else 4 <= size <= 4096),
            "Exact per-profile image allowance",
        )
        if mode == "runtime-multipage":
            need(image["bounds_pc"] > base + 8192, "Actual third-page bounds site")
        sites = [image[k] for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")]
        need(
            all(sites[:3]) and len(set(pc for pc in sites if pc)) == len([pc for pc in sites if pc]),
            "Ambiguous metadata sites",
        )
        need(
            all(pc == 0 or base <= pc <= base + size - 2 for pc in sites) and image["return_pc"] >= base + 2,
            "Metadata site outside image",
        )
        probe = image["probe_pc"]
        offset = image["probe_offset"]
        need(probe == 0 or base <= probe <= base + size - 2 and probe not in sites, "Metadata probe outside image")
        need(
            offset == 0
            or size >= 8
            and 2 <= offset <= size - 8
            and all(not (base + offset < pc + 2 and pc < base + offset + 8) for pc in sites if pc),
            "Metadata probe literal outside image",
        )
        expected_probe = index == 0 and mode in (
            "runtime-stack",
            "runtime-kernel",
            "runtime-window",
            "runtime-write",
            "runtime-return",
            "runtime-unknown",
            "runtime-syscall",
            "runtime-sysenter",
        )
        need(
            bool(probe) == expected_probe and bool(offset) == (index == 0 and mode == "runtime-kernel"),
            "Unexpected metadata probe authority",
        )

    patterns = (
        r"AURORA_UEFI_MULTIPAGE_ROLLBACK_OK: prefixes=3",
        r"AURORA_UEFI_DOMAIN_ENTER: slot=\d+ root=\d+ entry=\d+ stack=\d+",
        r"AURORA_UEFI_DOMAIN_EVENT: vector=\d+ error=\d+ pc=\d+ cpl=\d+ root=\d+ frame=\d+ cr2=\d+",
        r"AURORA_UEFI_DOMAIN_RESTORE: slot=\d+ root=\d+ stack=\d+ event=(returned|bounds) value=\d+",
        r"AURORA_UEFI_DOMAIN_REUSE_OK: frame=\d+",
        rf"AURORA_UEFI_DOMAIN_CLEANUP_OK: used={retained}",
        r"AURORA_UEFI_RUNTIME_ROOT_PROBE: root=\d+",
        r"AURORA_UEFI_RUNTIME_IST_OK",
        r"AURORA_UEFI_RUNTIME_OK",
        (
            "AURORA_UEFI_RUNTIME_FAIL: (exception root authority|exception origin/stack|exception site authorit"
            "y|double fault)"
        ),
    )
    for line in text.splitlines():
        if line.startswith(("AURORA_UEFI_DOMAIN_", "AURORA_UEFI_RUNTIME_", "AURORA_UEFI_MULTIPAGE_")):
            need(any(re.fullmatch(pattern, line) for pattern in patterns), "Malformed runtime record")
    need("AURORA_UEFI_PAYLOAD_FAIL:" not in text and "AURORA_UEFI_FAIL:" not in text, "Unexpected boot failure")
    if mode != "runtime-root":
        need("AURORA_UEFI_RUNTIME_ROOT_PROBE:" not in text, "Unexpected root probe")
    if mode != "runtime-entry-stack":
        need("AURORA_UEFI_RUNTIME_IST_OK" not in text, "Unexpected IST proof")

    start = text.find("AURORA_UEFI_DOMAIN_ENTER:")
    need(start >= 0, "Runtime never entered user domain")
    rollback = "AURORA_UEFI_MULTIPAGE_ROLLBACK_OK: prefixes=3"
    need(
        text.count(rollback) == (1 if mode == "runtime-multipage" else 0), "Exact multipage rollback proof scope/count"
    )
    if mode == "runtime-multipage":
        need(text.index(rollback) < start, "Multipage rollback precedes user execution")
    pci.validate(33, text[:start] + SUFFIX, "pci")
    owned = re.search(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+)", text)
    arena = int(owned[1])
    kernel = arena + LAYOUT.kernel_tables_offset
    enter = list(re.finditer(r"AURORA_UEFI_DOMAIN_ENTER: slot=(\d+) root=(\d+) entry=(\d+) stack=(\d+)", text))
    events = list(
        re.finditer(
            r"AURORA_UEFI_DOMAIN_EVENT: vector=(\d+) error=(\d+) pc=(\d+) cpl=(\d+) root=(\d+) frame=(\d+) cr2=(\d+)",
            text,
        )
    )
    restores = list(
        re.finditer(
            r"AURORA_UEFI_DOMAIN_RESTORE: slot=(\d+) root=(\d+) stack=(\d+) event=(returned|bounds) value=(\d+)", text
        )
    )
    count = 4 if mode in SUCCESS_MODES else 1
    need(
        len(enter) == len(events) == count and len(restores) == (4 if mode in SUCCESS_MODES else 0),
        "Run/event/restoration count",
    )
    for prefix, records in [
        ("AURORA_UEFI_DOMAIN_ENTER:", enter),
        ("AURORA_UEFI_DOMAIN_EVENT:", events),
        ("AURORA_UEFI_DOMAIN_RESTORE:", restores),
    ]:
        need(text.count(prefix) == len(records), "Malformed/duplicate runtime record")
    for index, (entry, event) in enumerate(zip(enter, events)):
        slot, root, pc, sp = map(int, entry.groups())
        wanted_slot = 1 if index == 1 else final_slot if index == 3 else 0
        need(
            slot == wanted_slot
            and root == arena + LAYOUT.tables_offset + slot * LAYOUT.table_pages * LAYOUT.page_size
            and pc == BASE + (1 if index == 1 else 0) * LAYOUT.code_stride
            and sp == LAYOUT.user_stack_top + slot * LAYOUT.user_stack_stride,
            "Wrong private entry layout",
        )
        need(entry.start() < event.start(), "Event before entry")
        vector, error, rip, cpl, actual, frame, cr2 = map(int, event.groups())
        need(actual == root, "Event under foreign root")
        expected_cpl = 0 if mode == "runtime-kernel-trap" else 3
        need(cpl == expected_cpl, "Wrong privilege origin")
        if mode == "runtime-entry-stack":
            need(
                arena + LAYOUT.ist_bottom <= frame <= arena + LAYOUT.ist_top - LAYOUT.fault_frame_size
                and frame % 8 == 0,
                "Wrong IST stack",
            )
        elif mode == "runtime-kernel-trap":
            need(
                arena + LAYOUT.kernel_stack_bottom <= frame < arena + LAYOUT.kernel_stack_top and frame % 8 == 0,
                "Wrong kernel trap stack",
            )
        else:
            need(
                arena + LAYOUT.rsp0_bottom <= frame <= arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size
                and frame % 8 == 0,
                "Wrong RSP0 frame",
            )
        image = metadata["bounds" if index == 1 else "clean"]
        need(image["entry"] == pc, "Fixture metadata entry")
        if mode in SUCCESS_MODES:
            kind = "bounds" if index == 1 else "returned"
            target = image["bounds_pc"] if index == 1 else image["return_pc"]
            need((vector, error, rip) == (6 if index == 1 else 129, 0, target), "Wrong exact contained site")
            restored = restores[index]
            rslot, rroot, rsp, rkind, value = restored.groups()
            need(
                int(rslot) == slot
                and int(rroot) == kernel
                and arena + LAYOUT.kernel_stack_bottom <= int(rsp) < arena + LAYOUT.kernel_stack_top
                and rkind == kind
                and int(value) == (0 if index == 1 else 42),
                "Restored authority/result mismatch",
            )
            need(
                event.start() < restored.start() and (index == 3 or restored.start() < enter[index + 1].start()),
                "Continuation order",
            )
        else:
            if mode in (
                "runtime-code",
                "runtime-stack",
                "runtime-kernel",
                "runtime-window",
                "runtime-write",
                "runtime-nx",
            ):
                address = {
                    "runtime-code": BASE + LAYOUT.code_stride,
                    "runtime-stack": STACK + LAYOUT.user_stack_stride,
                    "runtime-kernel": arena,
                    "runtime-window": pci.WINDOW,
                    "runtime-write": BASE,
                    "runtime-nx": LAYOUT.user_stack_top - 8,
                }[mode]
                err = {
                    "runtime-code": 20,
                    "runtime-stack": 4,
                    "runtime-kernel": 5,
                    "runtime-window": 4,
                    "runtime-write": 7,
                    "runtime-nx": 21,
                }[mode]
                target = address if mode in ("runtime-code", "runtime-nx") else image["probe_pc"]
                need((vector, error, rip, cr2) == (14, err, target, address), "Wrong protection fault/site")
            elif mode in ("runtime-root", "runtime-terminal-input", "runtime-terminal-output"):
                need((vector, error, rip) == (129, 0, image["return_pc"]), "Wrong return-root probe")
            elif mode == "runtime-kernel-trap":
                need((vector, error, rip) == (6, 0, image["bounds_pc"]), "Wrong known kernel UD2")
            elif mode == "runtime-entry-stack":
                need(
                    (vector, error, rip, cr2) == (8, 0, image["return_pc"] - 2, arena + LAYOUT.rsp0_bottom - 8),
                    "Missing exact entry-stack double fault",
                )
            elif mode == "runtime-return":
                need(
                    (vector, error, rip) == (129, 0, image["probe_pc"]) and rip != image["return_pc"],
                    "Wrong forged return site",
                )
            elif mode in ("runtime-syscall", "runtime-sysenter"):
                need(
                    (vector, error, rip) == (6 if mode == "runtime-syscall" else 13, 0, image["probe_pc"]),
                    "Inherited alternate privilege entry",
                )
            elif mode == "runtime-unknown":
                need(
                    (vector, error, rip) == (6, 0, image["probe_pc"])
                    and rip
                    not in [image[k] for k in ("bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")],
                    "Unknown UD2 accepted as known",
                )
    if mode in SUCCESS_MODES:
        pci.validate(status, text, "pci")
        need("AURORA_UEFI_RUNTIME_FAIL:" not in text, "Runtime failure hidden by success")
        reuse = re.findall(r"AURORA_UEFI_DOMAIN_REUSE_OK: frame=(\d+)", text)
        need(len(reuse) == 1 and int(reuse[0]) == arena + LAYOUT.stack_frames_offset, "Wrong reused frame")
        need(
            restores[2].start() < text.index("AURORA_UEFI_DOMAIN_REUSE_OK:") < enter[3].start(),
            "Reuse before retirement",
        )
        for marker in (f"AURORA_UEFI_DOMAIN_CLEANUP_OK: used={retained}", "AURORA_UEFI_RUNTIME_OK"):
            need(text.count(marker) == 1, "Missing unique cleanup/runtime completion")
        need(
            restores[3].start()
            < text.index("AURORA_UEFI_DOMAIN_CLEANUP_OK:")
            < text.index("AURORA_UEFI_RUNTIME_OK")
            < text.index("AURORA_UEFI_LANGUAGE_OK:"),
            "Final cleanup order",
        )
        need(
            "AURORA_UEFI_RUNTIME_ROOT_PROBE:" not in text and "AURORA_UEFI_RUNTIME_IST_OK" not in text,
            "Unexpected failure probe",
        )
    else:
        need(status == 35 and text.count("AURORA_UEFI_RUNTIME_FAIL:") == 1, "Missing unique runtime failure")
        need(
            all(
                marker not in text
                for marker in (
                    "AURORA_UEFI_LANGUAGE_OK",
                    "AURORA_UEFI_OK",
                    "AURORA_UEFI_DOMAIN_REUSE_OK:",
                    "AURORA_UEFI_DOMAIN_CLEANUP_OK:",
                    "AURORA_UEFI_RUNTIME_OK",
                )
            ),
            "Rejected domain continued",
        )
        need(events[0].start() < text.index("AURORA_UEFI_RUNTIME_FAIL:"), "Failure before event")
        if mode == "runtime-root":
            probe = re.findall(r"AURORA_UEFI_RUNTIME_ROOT_PROBE: root=(\d+)", text)
            need(
                len(probe) == 1
                and int(probe[0]) == kernel
                and events[0].start()
                < text.index("AURORA_UEFI_RUNTIME_ROOT_PROBE:")
                < text.index("AURORA_UEFI_RUNTIME_FAIL: exception root authority"),
                "Root probe authority",
            )
        elif mode == "runtime-entry-stack":
            need(
                text.count("AURORA_UEFI_RUNTIME_IST_OK") == 1
                and events[0].start()
                < text.index("AURORA_UEFI_RUNTIME_IST_OK")
                < text.index("AURORA_UEFI_RUNTIME_FAIL: double fault"),
                "Missing IST proof",
            )
        else:
            reason = "exception origin/stack" if mode == "runtime-kernel-trap" else "exception site authority"
            need("AURORA_UEFI_RUNTIME_FAIL: " + reason in text, "Wrong boundary rejection")


def owned_text_controls(prefix, baseline):
    metadata = copy.deepcopy(baseline)
    for image in metadata.values():
        image["probe_pc"] = 0
    image = metadata["clean"]
    image.update(size=11789, user_stack=2008, compiled_begin=BASE + 6000, compiled_end=BASE + 9000)
    operations = ("allocate", "borrow_length", "at", "set", "resize", "drop")
    for index, name in enumerate(operations):
        image["bytes_" + name + "_pc"] = BASE + 11500 + index * 32
    arena = 0x1000000
    kernel, domain, frame = (
        arena + LAYOUT.kernel_tables_offset,
        arena + LAYOUT.tables_offset,
        arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size,
    )
    text = prefix + f"AURORA_UEFI_TIMER_READY: physical=4276092928 virtual=18446620928407240704 id=0 root={kernel}\n"

    def event(vector, pc):
        return f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error=0 pc={pc} cpl=3 root={domain} frame={frame} cr2=0\n"

    cases = ((128578, 0, 70, 5), (55296, 0, 0, 1), (1114114, 0, 65, 64), (1114112, 1, 0, 1), (1114113, 1, 0, 1))
    for epoch, (scalar, abandoned, value, peak) in enumerate(cases, 1):
        text += f"AURORA_UEFI_TIMER_ARM: epoch={epoch} budget=128 root={domain}\n"
        if epoch == 1:
            for name in operations:
                text += event(130, image["bytes_" + name + "_pc"])
        ticks = 128 if epoch == 5 else 0
        for used in range(1, ticks + 1):
            text += event(64, BASE + 6100)
            text += (
                f"AURORA_UEFI_TIMER_TICK: epoch={epoch} used={used} remaining={128 - used} pc={BASE + 6100} flags=514\n"
            )
        if not ticks:
            text += event(6 if abandoned else 129, image["bounds_pc" if abandoned else "return_pc"])
        text += (
            f"AURORA_UEFI_TIMER_QUIET: epoch={epoch} ticks={ticks} drains=0 compiled={ticks} context=0 root={kernel}\n"
        )
        text += (
            f"AURORA_OWNED_TEXT_CASE: scalar={scalar} abandoned={abandoned} "
            f"value={value} live={abandoned} peak={peak} ticks={ticks} used=0 pages=0\n"
        )
    text += "AURORA_OWNED_TEXT_OK\n" + SUFFIX
    validate_owned_text(33, text, metadata, "runtime-owned-text")
    mutants = []
    for old, new in (
        ("epoch=2 budget=128", "epoch=1 budget=128"),
        ("budget=128", "budget=129"),
        ("epoch=5 used=2 remaining=126", "epoch=5 used=1 remaining=127"),
        ("epoch=5 used=128 remaining=0", "epoch=5 used=128 remaining=1"),
        ("cpl=3", "cpl=0"),
        ("vector=129 error=0", "vector=129 error=1"),
        ("vector=129", "vector=255"),
        ("live=1", "live=0"),
        ("peak=64", "peak=65"),
        ("value=70", "value=69"),
        (f"root={domain}", f"root={domain + 4096}"),
    ):
        mutants.append(text.replace(old, new, 1))
    tick = next(line + "\n" for line in text.splitlines() if "epoch=5 used=2 " in line)
    mutants += [text.replace(tick, "", 1), text.replace(tick, tick + tick, 1)]
    terminal = event(129, image["return_pc"])
    mutants.append(text.replace(terminal, "", 1))
    lines = text.splitlines(keepends=True)
    quiet = next(i for i, line in enumerate(lines) if line.startswith("AURORA_UEFI_TIMER_QUIET:"))
    lines[quiet], lines[quiet + 1] = lines[quiet + 1], lines[quiet]
    mutants.append("".join(lines))
    mutants.append(text.replace("AURORA_OWNED_TEXT_OK", "AURORA_UEFI_TIMER_UNKNOWN\nAURORA_OWNED_TEXT_OK"))
    for changed in mutants:
        try:
            validate_owned_text(33, changed, metadata, "runtime-owned-text")
        except ValueError:
            pass
        else:
            raise RuntimeError("Malformed owned text transcript accepted")
    for field, value in (("entry", BASE + 1), ("size", 12289), ("user_stack", 15361), ("bytes_at_pc", BASE - 1)):
        changed = copy.deepcopy(metadata)
        changed["clean"][field] = value
        try:
            validate_owned_text(33, text, changed, "runtime-owned-text")
        except ValueError:
            pass
        else:
            raise RuntimeError("Malformed owned text metadata accepted")
    denial_count = 0
    for mode, reason in (
        ("site", "text exact operation site"),
        ("region", "text private region binding"),
        ("stale", "owned text allocator invariant"),
    ):
        denied = text[: text.index("AURORA_UEFI_TIMER_ARM:")]
        arm = f"AURORA_UEFI_TIMER_ARM: epoch=1 budget=128 root={domain}\n"
        denied += arm + event(130, image["bytes_allocate_pc"])
        if mode == "stale":
            denied += event(130, image["bytes_resize_pc"]) + event(130, image["bytes_set_pc"])
            denied += "AURORA_OWNED_TEXT_STALE: committed-resize\nAURORA_OWNED_TEXT_FAULT: reason=1\n"
        failure = "AURORA_UEFI_RUNTIME_FAIL: " + reason + "\n"
        denied += failure
        validate_owned_text(35, denied, metadata, "runtime-owned-text-" + mode)
        changes = [
            denied.replace(arm, ""),
            re.sub(r"AURORA_UEFI_DOMAIN_EVENT:[^\n]*\n", "", denied),
            denied.replace("cpl=3", "cpl=0", 1),
            denied.replace(f"cpl=3 root={domain}", f"cpl=3 root={kernel}", 1),
            denied + failure,
            denied.replace(failure, SUFFIX + failure),
        ]
        tick = f"AURORA_UEFI_TIMER_TICK: epoch=1 used=1 remaining=127 pc={BASE + 6100} flags=514\n"
        with_tick = denied.replace(arm, arm + event(64, BASE + 6100) + tick)
        validate_owned_text(35, with_tick, metadata, "runtime-owned-text-" + mode)
        changes += [
            with_tick.replace(tick, ""),
            with_tick.replace("used=1 remaining=127", "used=1 remaining=128"),
            with_tick.replace(tick, tick + tick),
        ]
        if mode == "stale":
            fake_resize = event(64, image["bytes_resize_pc"]) + tick.replace(
                str(BASE + 6100), str(image["bytes_resize_pc"])
            )
            changes.append(denied.replace(event(130, image["bytes_resize_pc"]), fake_resize))
        for changed in changes:
            try:
                validate_owned_text(35, changed, metadata, "runtime-owned-text-" + mode)
            except ValueError:
                pass
            else:
                raise RuntimeError("Malformed owned text denial accepted")
        denial_count += len(changes)
    print(f"PASS: owned text transcript 7 positive, {len(mutants) + 4 + denial_count} negative controls")


def console_region_self_test():
    arena = 16777216
    image = dict(
        entry=BASE,
        size=6729,
        return_pc=BASE + 40,
        bounds_pc=BASE + 42,
        overflow_pc=BASE + 44,
        division_zero_pc=0,
        shift_count_pc=0,
        probe_offset=0,
        probe_pc=0,
        user_stack=824,
        compiled_begin=BASE + 64,
        compiled_end=BASE + 6000,
    )
    for index, name in enumerate(("allocate", "borrow_length", "at", "set", "resize", "drop")):
        image["bytes_" + name + "_pc"] = BASE + 6200 + index * 16
    image.update(console_next_pc=BASE + 6300, console_put_pc=BASE + 6310)
    bounds = dict(
        entry=BASE + LAYOUT.code_stride,
        size=100,
        return_pc=BASE + 16400,
        bounds_pc=BASE + 16402,
        overflow_pc=BASE + 16404,
        division_zero_pc=0,
        shift_count_pc=0,
        probe_offset=0,
        probe_pc=0,
    )
    metadata = dict(clean=image, bounds=bounds)
    cases = (
        ("", 33, 1, 0, 1, 0, 0, "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345\n"),
        ("-fault", 1, 1, 0, 2, 0, 1, ""),
        ("-cancel", 1, 2, 0, 0, 0, 1, ""),
        ("-cancel-ready", 1, 1, 0, 0, 0, 1, ""),
        ("-input", 1, 1, 2, 1, 0, 0, ""),
        ("-output", 33, 1, 3, 1, 0, 0, "AB"),
        ("-budget", 0, 1, 0, 0, 1, 1, ""),
    )
    rejected = 0
    for suffix, waits, incarnations, value, event, exhausted, abandoned, output in cases:
        mode = "runtime-console-region" + suffix
        trace = f"AURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes=1048576 descriptors=111\n"
        for epoch in range(1, incarnations + 1):
            trace += f"AURORA_UEFI_TIMER_ARM: epoch={epoch} budget=128 root={arena + LAYOUT.tables_offset}\n"
            for index in range(1, waits + 1):
                ticket = (epoch - 1) * waits + index
                trace += (
                    f"AURORA_CONSOLE_PARK: ticket={ticket} live=1 used=32 epoch={epoch} "
                    f"ticks={index} remaining={128 - index}\n"
                )
            trace += output
            if event:
                pc = image["bounds_pc" if event == 2 else "return_pc"]
                trace += (
                    f"AURORA_UEFI_DOMAIN_EVENT: vector={6 if event == 2 else 129} error=0 pc={pc} cpl=3 "
                    f"root={arena + LAYOUT.tables_offset} "
                    f"frame={arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size} cr2=0\n"
                )
            ticks = 128 if exhausted else waits
            done = (
                f"AURORA_CONSOLE_REGION_DONE: value={value} event={event} exhausted={exhausted} "
                f"ticks={ticks} remaining={128 - ticks} abandoned={abandoned} peak=32 used=0 pages=0\n"
            )
            trace += done
        trace += SUFFIX
        validate_console_region(33, trace, metadata, mode)
        bad_cases = [
            (35, trace, metadata),
            (33, trace.replace(done, "", 1), metadata),
            (33, trace.replace(done, done + done, 1), metadata),
            (33, trace.replace("used=0 pages=0", "used=1 pages=1"), metadata),
            (33, trace.replace(done, done.replace(f"event={event}", "event=9")), metadata),
            (33, trace.replace(done, done.replace(f"remaining={128 - ticks}", "remaining=129")), metadata),
            (33, trace.replace(SUFFIX, "X" + SUFFIX), metadata),
            (33, trace.replace(SUFFIX, "AURORA_UEFI_RUNTIME_FAIL: hidden\n" + SUFFIX), metadata),
        ]
        changed = copy.deepcopy(metadata)
        changed["clean"]["user_stack"] = LAYOUT.stack_cap + 1
        bad_cases.append((33, trace, changed))
        for code, bad, meta in bad_cases:
            try:
                validate_console_region(code, bad, meta, mode)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError("Protected console oracle accepted incorrect output or completion: " + mode)
    print(f"PASS: console behavior {len(cases)} positive, {rejected} negative controls")


def self_test():
    console_region_self_test()
    arena = 0x1000000
    kernel = arena + LAYOUT.kernel_tables_offset
    prefix = (
        f"AURORA_UEFI_ENTRY\nAURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEF"
        f"I_PAYLOAD_ENTRY\nAURORA_UEFI_OWNERSHIP_OK: arena={arena} bytes"
        f"=1048576 descriptors=111\nAURORA_UEFI_PROTECTION_OK: root="
        f"{kernel} stack={arena + (LAYOUT.kernel_stack_top - 512)}\nAURORA_ACPI_CPU: id=0 uid=0 "
        f"enabled=1 capable=0 x2=0\nAURORA_ACPI_TOPOLOGY: records=1 enab"
        f"led=1 capable=0 lapic=4276092928\nAURORA_ACPI_WINDOW_CLOSED: c"
        f"opies=14\nAURORA_PCI_APERTURE: base=3758096384 bytes=268435456"
        f" segment=0 first=0 last=255\nAURORA_PCI_FUNCTION: segment=0 bu"
        f"s=0 device=0 function=0 vendor=32902 product=10688 class=6 sub"
        f"class=0 interface=0 header=0 command=7 secondary=0 subordinate"
        f"=0\nAURORA_PCI_INVENTORY: functions=1 buses=1\nAURORA_PCI_WIND"
        f"OW_CLOSED: reads=39\n"
    )
    metadata = {}
    for index, name in enumerate(("clean", "bounds")):
        base = BASE + index * LAYOUT.code_stride
        metadata[name] = dict(
            entry=base,
            size=128,
            return_pc=base + 60,
            bounds_pc=base + 64,
            overflow_pc=base + 68,
            division_zero_pc=base + 72,
            shift_count_pc=base + 76,
            probe_pc=base + 52,
            probe_offset=0,
        )
    cases = {}
    original_metadata = copy.deepcopy(metadata)
    owned_text_controls(prefix, original_metadata)
    for mode in MODES:
        metadata = copy.deepcopy(original_metadata)
        if mode == "runtime-multipage":
            for image in metadata.values():
                image["size"] = 10000
                image["bounds_pc"] = image["entry"] + 9000
        text = prefix
        if mode == "runtime-multipage":
            text += "AURORA_UEFI_MULTIPAGE_ROLLBACK_OK: prefixes=3\n"
        for i in range(4 if mode in SUCCESS_MODES else 1):
            slot = 1 if i == 1 else 0
            root = arena + LAYOUT.tables_offset + slot * LAYOUT.table_pages * LAYOUT.page_size
            sp = LAYOUT.user_stack_top + slot * LAYOUT.user_stack_stride
            image = metadata["bounds" if slot else "clean"]
            if i == 3:
                text += f"AURORA_UEFI_DOMAIN_REUSE_OK: frame={arena + LAYOUT.stack_frames_offset}\n"
            text += f"AURORA_UEFI_DOMAIN_ENTER: slot={slot} root={root} entry={image['entry']} stack={sp}\n"
            vector = 6 if i == 1 else 129
            error = 0
            pc = image["bounds_pc"] if i == 1 else image["return_pc"]
            cpl = 3
            frame = arena + LAYOUT.rsp0_top - LAYOUT.fault_frame_size
            cr2 = 0
            if mode in (
                "runtime-code",
                "runtime-stack",
                "runtime-kernel",
                "runtime-window",
                "runtime-write",
                "runtime-nx",
            ):
                vector = 14
                error = {
                    "runtime-code": 20,
                    "runtime-stack": 4,
                    "runtime-kernel": 5,
                    "runtime-window": 4,
                    "runtime-write": 7,
                    "runtime-nx": 21,
                }[mode]
                cr2 = {
                    "runtime-code": BASE + LAYOUT.code_stride,
                    "runtime-stack": STACK + LAYOUT.user_stack_stride,
                    "runtime-kernel": arena,
                    "runtime-window": pci.WINDOW,
                    "runtime-write": BASE,
                    "runtime-nx": LAYOUT.user_stack_top - 8,
                }[mode]
                pc = cr2 if mode in ("runtime-code", "runtime-nx") else image["probe_pc"]
            elif mode == "runtime-kernel-trap":
                vector = 6
                pc = image["bounds_pc"]
                cpl = 0
                frame = arena + (LAYOUT.kernel_stack_top - 1024)
            elif mode == "runtime-entry-stack":
                vector = 8
                pc = image["return_pc"] - 2
                cr2 = arena + LAYOUT.rsp0_bottom - 8
                frame = arena + LAYOUT.ist_top - LAYOUT.fault_frame_size
            elif mode == "runtime-return":
                pc = image["probe_pc"]
            elif mode == "runtime-unknown":
                vector = 6
                pc = image["probe_pc"]
            elif mode in ("runtime-syscall", "runtime-sysenter"):
                vector = 6 if mode == "runtime-syscall" else 13
                pc = image["probe_pc"]
            text += (
                f"AURORA_UEFI_DOMAIN_EVENT: vector={vector} error={error} pc={pc}"
                f" cpl={cpl} root={root} frame={frame} cr2={cr2}\n"
            )
            if mode in SUCCESS_MODES:
                text += (
                    f"AURORA_UEFI_DOMAIN_RESTORE: slot={slot} root={kernel} stack="
                    f"{arena + (LAYOUT.kernel_stack_top - 1024)} event={'bounds' if i == 1 else 'returned'} v"
                    f"alue={0 if i == 1 else 42}\n"
                )
        if mode in SUCCESS_MODES:
            text += "AURORA_UEFI_DOMAIN_CLEANUP_OK: used=0\nAURORA_UEFI_RUNTIME_OK\n" + SUFFIX
        else:
            reason = "exception site authority"
            if mode == "runtime-root":
                text += f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}\n"
                reason = "exception root authority"
            if mode == "runtime-entry-stack":
                text += "AURORA_UEFI_RUNTIME_IST_OK\n"
                reason = "double fault"
            if mode == "runtime-kernel-trap":
                reason = "exception origin/stack"
            text += f"AURORA_UEFI_RUNTIME_FAIL: {reason}\n"
        case_metadata = copy.deepcopy(metadata)
        case_metadata["bounds"]["probe_pc"] = 0
        if mode not in (
            "runtime-stack",
            "runtime-kernel",
            "runtime-window",
            "runtime-write",
            "runtime-return",
            "runtime-unknown",
            "runtime-syscall",
            "runtime-sysenter",
        ):
            case_metadata["clean"]["probe_pc"] = 0
        case_metadata["clean"]["probe_offset"] = 88 if mode == "runtime-kernel" else 0
        cases[mode] = (33 if mode in SUCCESS_MODES else 35, text, case_metadata)
    rejected = 0
    for mode, (status, text, metadata) in cases.items():
        validate(status, text, mode, metadata)
        invalid = [
            (0, text),
            (status, text + "AURORA_UEFI_DOMAIN_CLEANUP_OK: used=1\n"),
            (status, text + "AURORA_UEFI_RUNTIME_FAIL: forged\n"),
        ]
        if mode != "runtime-root":
            invalid.append((status, text + f"AURORA_UEFI_RUNTIME_ROOT_PROBE: root={kernel}\n"))
        if mode != "runtime-entry-stack":
            invalid.append((status, text + "AURORA_UEFI_RUNTIME_IST_OK\n"))
        for line in text.splitlines():
            invalid.extend(
                [(status, text.replace(line + "\n", "", 1)), (status, text.replace(line + "\n", (line + "\n") * 2, 1))]
            )
        if mode in SUCCESS_MODES:
            invalid.append((status, text + "AURORA_UEFI_RUNTIME_FAIL: unexpected\n"))
            last = [line for line in text.splitlines() if line.startswith("AURORA_UEFI_DOMAIN_RESTORE:")][-1] + "\n"
            invalid.append((status, text.replace(last, "", 1) + last))
        else:
            invalid.extend([(status, text + SUFFIX), (status, text + "AURORA_UEFI_RUNTIME_OK\n")])
        event = re.search(r"AURORA_UEFI_DOMAIN_EVENT:[^\n]+", text)[0]
        for key, value in [("root", "0"), ("frame", "0"), ("pc", "0"), ("cpl", "2"), ("error", "255")]:
            altered = re.sub(rf"{key}=\d+", f"{key}={value}", event)
            invalid.append((status, text.replace(event, altered, 1)))
        for field, value in [
            ("return_pc", 0),
            ("bounds_pc", BASE - 2),
            ("overflow_pc", BASE + LAYOUT.code_stride),
            ("size", 12289 if mode == "runtime-multipage" else 8192),
            ("entry", 0),
            ("return_pc", True),
            ("probe_offset", 4096),
        ]:
            altered = copy.deepcopy(metadata)
            old = altered["clean"][field]
            altered["clean"][field] = value
            bad = text.replace(f"pc={old} ", f"pc={int(value)} ") if field == "return_pc" else text
            try:
                validate(status, bad, mode, altered)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError(f"Invalid runtime metadata accepted: {mode} {field}")
        if mode == "runtime-multipage":
            for name in ("clean", "bounds"):
                for field, value in (("size", 4096), ("size", 12289), ("bounds_pc", metadata[name]["entry"] + 64)):
                    altered = copy.deepcopy(metadata)
                    altered[name][field] = value
                    try:
                        validate(status, text, mode, altered)
                    except ValueError:
                        rejected += 1
                    else:
                        raise RuntimeError("Multipage scope or later-page terminal proof lost")
            for legacy in ("runtime", "runtime-span"):
                try:
                    validate(status, text, legacy, metadata)
                except ValueError:
                    rejected += 1
                else:
                    raise RuntimeError("Legacy runtime image allowance widened")
        rollback = "AURORA_UEFI_MULTIPAGE_ROLLBACK_OK: prefixes=3\n"
        if mode == "runtime-multipage":
            invalid += [
                (status, text.replace(rollback, replacement))
                for replacement in (
                    "",
                    rollback + rollback,
                    rollback.replace("=3", "=0"),
                    rollback.replace("=3", "=2"),
                    rollback.replace("=3", "=4"),
                )
            ]
            invalid.append((status, text.replace(rollback, "") + rollback))
        else:
            invalid.append((status, rollback + text))
        for code, bad in invalid:
            try:
                validate(code, bad, mode, metadata)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError(f"Invalid runtime transcript accepted: {mode}")
    print(f"PASS: UEFI runtime transcripts {len(cases)} positive and {rejected} negative cases")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--console-region-run"]:
        sys.exit(run_console_region(sys.argv[5:], Path(sys.argv[3]), sys.argv[2]))
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    try:
        validate(
            int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
        )
    except ValueError as error:
        sys.exit(f"FAIL: {error}")

#!/usr/bin/env python3
"""Original-clock developer PTY gate with a separate review-pinned qualification mode."""

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
import kernel_program_console_admission as admission
import kernel_uefi_console_clock as clock


def need(okay, message):
    if not okay:
        raise ValueError(message)


def validate(text, mode, expected_outputs, commands, images, timer):
    need("AURORA_UEFI_RUNTIME_FAIL" not in text and "AURORA_UEFI_FAIL" not in text, "Runtime or payload failed closed")
    need(text.count("AURORA_PROGRAM_CONSOLE_READY:") == 1, "Console restart or missing readiness")
    begins = [
        (int(grant), int(length))
        for grant, length in re.findall(r"AURORA_PROGRAM_COMMAND_BEGIN: grant=(\d+) length=(\d+) domains=2", text)
    ]
    endings = [
        (int(success), int(epoch))
        for success, epoch in re.findall(r"AURORA_PROGRAM_COMMAND_END: success=([01]) used=0 epoch=(\d+)", text)
    ]
    need(len(begins) == len(endings) == commands, "Missing command lifecycle evidence")
    need(all(a[0] < b[0] for a, b in zip(begins, begins[1:])), "Endpoint generation reused")
    need(all(0 <= length <= 64 for _, length in begins), "Unbounded admitted input")
    need(all(a[1] <= b[1] for a, b in zip(endings, endings[1:])), "Timer epoch reset")
    epochs = [int(value) for value in re.findall(r"AURORA_UEFI_USER_RUN: epoch=(\d+) ", text)]
    need(epochs and all(a < b for a, b in zip(epochs, epochs[1:])), "Run epoch missing or reused")
    command_parts = re.findall(
        r"AURORA_PROGRAM_COMMAND_BEGIN: grant=\d+ length=(\d+) domains=2(.*?)"
        r"AURORA_PROGRAM_COMMAND_END: success=([01]) used=0 epoch=(\d+)",
        text,
        re.S,
    )
    need(len(command_parts) == commands, "Unmatched command ownership interval")
    for length, part, success, ending_epoch in command_parts:
        runs = re.findall(
            r"AURORA_UEFI_USER_RUN: epoch=(\d+) role=(client|service) "
            r"phase=(request|service|completion) client=0 transaction=(\d+) source=(\d+) root=\d+",
            part,
        )
        phases = [item[2] for item in runs]
        if success == "1":
            need(phases == ["request", "service", "completion"] * int(length), "Missing or reordered byte handoff")
        else:
            failed_phase = mode.split("-")[1]
            prefix = {"request": 1, "service": 2, "completion": 3}[failed_phase]
            need(
                int(length) >= 2
                and phases == ["request", "service", "completion"] + ["request", "service", "completion"][:prefix],
                "Fault did not follow one completed byte",
            )
        for offset, (_, role, phase, transaction, source) in enumerate(runs):
            need(role == ("service" if phase == "service" else "client"), "Wrong role for phase")
            need((int(transaction) == 0) == (phase == "request"), "Wrong transaction launch authority")
            if success == "1" or offset + 1 < len(runs):
                need(int(source) == {"request": 0, "service": 1, "completion": 2}[phase], "Wrong healthy source phase")
            if phase == "completion":
                need(transaction == runs[offset - 1][3], "Completion changed transaction")
        if runs:
            need(int(ending_epoch) == int(runs[-1][0]), "Retirement epoch does not match last run")
    actual_outputs = re.findall(r"(?:^|\n)output> ([^\r\n]*)\r?\n", text)
    need(actual_outputs == expected_outputs, "Partial, duplicate, missing or wrong completed output")
    # Every full output must immediately follow a successful zero-resource end.
    need(
        len(re.findall(r"AURORA_PROGRAM_COMMAND_END: success=1 used=0 epoch=\d+\r?\noutput> ", text))
        == len(expected_outputs),
        "Output was exposed before authenticated retirement",
    )
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
        if re.fullmatch(r"AURORA_UEFI_TIMER_TICK: epoch=\d+ used=\d+ remaining=0 .*", line):
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
                    and arena + 0x44000 <= frame <= arena + 0x48000 - 176
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
                cpl == 3 and vector in (6, 64, 129) and root == live_root and frame == arena + 0x88000 - 176,
                "Invalid active-domain frame",
            )
            if vector == 129:
                need(pc == live_image["return_pc"], "Unknown user return site")
                terminal_seen = True
            if vector == 6:
                terminal_seen = True
            if vector == 64:
                need(
                    live_image["entry"] <= pc < live_image["entry"] + live_image["size"],
                    "Timer interrupted outside admitted user image",
                )
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
    need(text.count("AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0") == 1, "Missing quiescent exit")
    need(text.count("AURORA_CONSOLE_EXIT") == 1, "Missing single exit")
    return dict(
        commands=commands,
        grants=[item[0] for item in begins],
        runs=len(epochs),
        last_epoch=endings[-1][1],
        completed_outputs=len(actual_outputs),
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
    parser.add_argument(
        "--qualification", action="store_true", help="Require external exact-image review; never rebuild the image"
    )
    args = parser.parse_args()
    verify = admission.reviewed if args.qualification else admission.checked
    reviewed = verify(args.mode)
    admission_digest = admission.digest(admission.RECEIPT)
    evidence_root = ROOT / "build/program-console-evidence"
    evidence_root.mkdir(parents=True, exist_ok=True)
    purpose = "qualified" if args.qualification else "developer"
    output = Path(tempfile.mkdtemp(prefix=args.mode + "-" + purpose + "-", dir=evidence_root))
    shutil.copy2(admission.RECEIPT, output / "admission.json")
    print("Protected-console " + purpose + " evidence: " + str(output))

    def unchanged():
        need(
            verify(args.mode) == reviewed and admission.digest(admission.RECEIPT) == admission_digest,
            "Admitted source, image or receipt changed during guest execution",
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
    command = [qemu]
    if os.environ.get("QEMU_DATA"):
        command += ["-L", os.environ["QEMU_DATA"]]
    command += [
        "-machine",
        "q35",
        "-accel",
        "tcg",
        "-cpu",
        "qemu64",
        "-smp",
        "1",
        "-m",
        "128M",
        *firmware_args,
        "-drive",
        "format=raw,file=fat:ro:build/uefi/esp,snapshot=on",
        "-nic",
        "none",
        "-display",
        "none",
        "-serial",
        "stdio",
        "-monitor",
        "none",
        "-no-reboot",
        "-device",
        "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
    receipt = clock.receipt(command, qemu, firmware, code, variables, os.environ.get("QEMU_DATA", ""))
    receipt.update(timeout_argv=None, test_supervision="private PTY, 180-second total deadline", mode=args.mode)
    (output / "clock.json").write_text(json.dumps(receipt, indent=2) + "\n")
    master, slave = pty.openpty()
    tty.setraw(slave)
    transcript = bytearray()
    process = None
    deadline = time.monotonic() + 180
    expected_outputs = []
    commands = 0
    metrics = {
        "status": "incomplete",
        "mode": args.mode,
        "clock": "tcg-original-clock",
        "purpose": purpose,
        "qualification_eligible": False,
        "admission_sha256": admission_digest,
    }
    try:
        with (output / "qemu.stderr").open("wb") as errors:
            process = subprocess.Popen(
                command, cwd=ROOT, stdin=slave, stdout=slave, stderr=errors, start_new_session=True
            )
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
                    elif process.poll() is not None:
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
                status = process.wait(timeout=5)
                part = bytes(transcript[begin:]).decode("ascii")
                validate_failstop(part, args.mode, status, reviewed["user_images"])
                unchanged()
                metrics.update(
                    status="passed",
                    exit_status=35,
                    failstop=FAILSTOP_REASONS[args.mode],
                    qualification_eligible=args.qualification,
                )
                print("PASS: malformed protected command authority fails stop without output or recovery")
                return

            if args.mode not in ("program-console", "program-pending"):
                command_upper(b"discard me\n", failure=True)
            command_upper(b"Hello, Aurora 42!\n", "HELLO, AURORA 42!")
            command_upper(b"next command\n", "NEXT COMMAND")
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
            need(process.wait(timeout=5) == 33, "QEMU did not exit cleanly")
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
                    reviewed["user_images"],
                    reviewed["timer"],
                ),
                status="passed",
                exit_status=process.returncode,
                qualification_eligible=args.qualification,
            )
            print("PASS: protected Aurora command PTY, bounded input, copied stream, recovery and quiescent exit")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        os.close(master)
        if slave != -1:
            os.close(slave)
        (output / "transcript.log").write_bytes(transcript)
        (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")


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

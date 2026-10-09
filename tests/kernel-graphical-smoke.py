#!/usr/bin/env python3
"""Compiler-free parser, pixel, choreography and cleanup controls; never guests."""

from contextlib import contextmanager
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kernel_graphical_smoke as smoke


def transcript(rows):
    lines = [
        "AURORA_UEFI_ENTRY\r\nAURORA_UEFI_EXIT_OK: attempts=1\r\nAURORA_UEFI_PAYLOAD_ENTRY\r\n"
        "AURORA_UEFI_OWNERSHIP_OK: arena=16777216 bytes=1048576 descriptors=111\r\n"
        "AURORA_UEFI_PROTECTION_OK: root=16846848 stack=17068032\r\n"
        "AURORA_UEFI_LANGUAGE_OK: value=42\r\nAURORA_UEFI_OK\r\n"
    ]
    for kind, row in rows:
        reason = row.get("reason", "")
        body = " ".join(f"{key}={value}" for key, value in row.items() if key != "reason")
        lines.append(smoke.PREFIX + kind + ": " + (reason + " " if reason else "") + body + "\r\n")
    return "".join(lines).encode()


def expected(case):
    name, selector, data = case
    model = smoke.reference(smoke.byte_samples(data or b"exit\r"), fail_after={b"F": 0, b"I": 55}.get(selector))
    rows = [("CAPTURE_GATE", dict(base=smoke.BASE, bytes=smoke.SIZE))]
    if selector != b"?":
        rows += [("CAPTURE_RELEASED", dict(selector=b"GCDcdFI".index(selector) + 1))]
    idle = name == "idle4096"
    if selector == b"G":
        rows += [
            ("PRE_SAMPLE", dict(completed=n, stores=model["frame_stores"][n]))
            for n in ([0] if idle else range(model["consumed"]))
        ]
    if selector in (b"?", b"C", b"D", b"c", b"d"):
        terminal = dict.fromkeys(smoke.FIELDS["CONSOLE_FAIL"], 0)
        terminal["reason"] = "capture selector" if selector == b"?" else "paired service authority"
        rows += [("CONSOLE_FAIL", terminal)]
    elif idle:
        stores = model["frame_stores"][0]
        rows += [
            (
                "CONSOLE_FAIL",
                dict(
                    entries=1,
                    samples=4097,
                    output_attempts=0,
                    stores=stores,
                    completed=0,
                    wakes=4096,
                    pixel_attempts=stores,
                    reason="NATIVE_IDLE_WAKE_DEADLINE: limit=4096",
                ),
            )
        ]
    else:
        stores = len(model["stores"])
        rows += [
            (
                "CONSOLE_COMPLETE",
                dict(
                    completion=model["completion"],
                    wakes=0 if selector in (b"F", b"I") else 2,
                    stores=stores,
                    entries=1,
                    samples=model["consumed"] + (0 if selector in (b"F", b"I") else 2),
                    output_attempts=0,
                    completed=model["consumed"],
                    pixel_attempts=stores + (model["completion"] == 2),
                ),
            )
        ]
    return model, rows


class Controls(unittest.TestCase):
    def test_matrix_and_mutations(self):
        self.assertEqual(len(smoke.CASES), 13)
        for case in smoke.CASES:
            model, rows = expected(case)
            raw = transcript(rows)
            self.assertEqual(smoke.markers(raw, final=True), rows)
            smoke.validate(rows, case[1], model, case[0] == "idle4096")
            for index in range(len(rows)):
                for changed in (rows[:index] + rows[index + 1 :], rows[:index] + [rows[index]] + rows[index:]):
                    with self.assertRaises((ValueError, IndexError)):
                        smoke.validate(changed, case[1], model, case[0] == "idle4096")
            for key, value in rows[-1][1].items():
                if key in ("reason", "wakes"):
                    continue
                bad = copy.deepcopy(rows)
                bad[-1][1][key] = value + 1
                with self.assertRaises(ValueError):
                    smoke.validate(bad, case[1], model, case[0] == "idle4096")
            for bad in (
                raw[:-1],
                raw + b"junk",
                raw + b"junk\r\n",
                raw + raw[-10:],
                raw.replace(b"base=", b"base=0"),
                raw.replace(b"stores=", b"sto\rres="),
                raw.replace(b"CAPTURE_GATE", b"UNKNOWN"),
                raw.replace(b"AURORA_UEFI_OK\r\n", b"AURORA_UEFI_OK\r\noutput> unexpected text\r\n"),
                raw.replace(b"AURORA_UEFI_ENTRY\r\n", b""),
                raw.replace(b"bytes=1921024", b"bytes=-1"),
            ):
                with self.assertRaises(ValueError):
                    smoke.markers(bad, final=True)
        model = smoke.reference(smoke.byte_samples(b"".join(smoke.PRODUCTION)))
        rows = [("CONSOLE_COMPLETE", dict(completion=0, wakes=4, stores=len(model["stores"])))]
        smoke.validate(smoke.markers(transcript(rows), production=True, final=True), b"G", model, production=True)

    def test_real_baseline_and_pixel_prefix(self):
        baseline = bytes(range(256)) * (smoke.SIZE // 256)
        for count in (0, 55):
            model = smoke.reference([], fail_after=count)
            raw = bytearray(baseline)
            for offset, value in model["stores"]:
                raw[offset : offset + 4] = value.to_bytes(4, "little")
            ppm = b"P6\n800 600\n255\n" + smoke.ppm_rgb(800, 600, 800, 1, raw)
            smoke.compare(baseline, raw, ppm, stores=model["stores"])
            for offset in (0, smoke.VISIBLE, (128 * 800 + 32) * 4):
                bad = bytearray(raw)
                bad[offset] ^= 1
                with self.assertRaises(ValueError):
                    smoke.compare(baseline, bad, ppm, stores=model["stores"])
            with self.assertRaises(ValueError):
                smoke.compare(baseline, raw, ppm[:-1] + bytes([ppm[-1] ^ 1]), stores=model["stores"])
            with self.assertRaises(ValueError):
                smoke.compare(baseline, model["pixels"][32:-32], ppm, stores=model["stores"])

    def test_selector_then_samples_and_sentinel(self):
        case = next(case for case in smoke.CASES if case[0] == "fixture-G")
        model, rows = expected(case)
        events, index = [], 0
        channel = SimpleNamespace(serial_bytes=transcript(rows[:1]), proc=SimpleNamespace(wait=lambda **kw: 0))
        channel.stop = lambda: events.append("stop")
        channel.capture = lambda name: (events.append(name) or b"", b"")
        channel.drain_serial = lambda: None
        channel.command = lambda name: events.append(name)

        def write(channel, data):
            nonlocal index
            events.append(data)
            index += 2 if index == 0 else 1
            channel.serial_bytes = transcript(rows[: index + 1])

        @contextmanager
        def fake_guest(*args):
            yield channel

        with (
            patch.object(smoke, "guest", fake_guest),
            patch.object(smoke, "send", write),
            patch.object(smoke, "compare"),
            patch.object(smoke, "wait", lambda ch, pred: self.assertTrue(pred(smoke.markers(ch.serial_bytes)))),
        ):
            smoke.capture_case(None, case, None, {})
        sent = [event for event in events if isinstance(event, bytes)]
        self.assertEqual(sent, [b"G", b"e", b"x", b"i", b"t", b"\r!"])
        self.assertLess(events.index("baseline"), events.index(b"G"))
        self.assertLess(events.index("sample-00"), events.index(b"e"))

    def test_window_failure_restores_once(self):
        for fail_at in ("production", "case", None):
            with tempfile.TemporaryDirectory() as temporary:
                args = SimpleNamespace(evidence=Path(temporary) / "new")
                events = []

                def action(name):
                    def run(*args):
                        events.append(name)
                        if name == fail_at:
                            raise ValueError("injected")

                    return run

                with (
                    patch("builtins.print"),
                    patch.object(smoke, "production_case", action("production")),
                    patch.object(smoke, "capture_case", action("case")),
                    patch.object(smoke, "restoration", action("restore")),
                ):
                    if fail_at:
                        with self.assertRaises(ValueError):
                            smoke.window(args)
                    else:
                        smoke.window(args)
                self.assertEqual(events.count("restore"), 1)
                self.assertEqual(events[-1], "restore")
                if fail_at:
                    self.assertEqual(events.count("case"), int(fail_at == "case"))
                self.assertEqual(json.loads((args.evidence / "summary.json").read_text())[-1]["status"], "passed")

    def test_idle_has_no_intermediate_pause_or_input(self):
        case = next(case for case in smoke.CASES if case[0] == "idle4096")
        model, rows = expected(case)
        events = []
        channel = SimpleNamespace(serial_bytes=transcript(rows[:1]), proc=SimpleNamespace(wait=lambda **kw: 0))
        channel.stop = lambda: events.append("stop")
        channel.capture = lambda name: (events.append(name) or b"", b"")
        channel.drain_serial = lambda: None
        channel.command = lambda name: events.append(name)

        @contextmanager
        def fake_guest(*args):
            yield channel

        def wait(ch, predicate):
            if events.count("cont"):
                ch.serial_bytes = transcript(rows[:3] if len(events) == 4 else rows)
                events.append("wait")
            self.assertTrue(predicate(smoke.markers(ch.serial_bytes)))

        with (
            patch.object(smoke, "guest", fake_guest),
            patch.object(smoke, "wait", wait),
            patch.object(smoke, "send", lambda ch, data: events.append(data)),
            patch.object(smoke, "compare"),
        ):
            smoke.capture_case(None, case, None, {})
        self.assertEqual(events, ["stop", "baseline", b"G", "cont", "wait", "wait", "stop", "terminal", "quit"])

    def test_capture_drift_still_boots_normal_then_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(images=Path(temporary), qemu="qemu", data="", firmware=["-bios", "firmware"])
            proc = SimpleNamespace(wait=lambda **kw: 33)

            def verify(args, mode=None, source=True):
                if mode != "normal":
                    raise ValueError("capture drift")

            with (
                patch.object(smoke, "verify_images", side_effect=verify) as checks,
                patch.object(smoke.subprocess, "Popen", return_value=proc) as launch,
                patch.object(smoke.normal, "validate") as validate,
                patch.object(smoke.capture, "terminate") as reap,
            ):
                with self.assertRaisesRegex(ValueError, "capture drift"):
                    smoke.restoration(args, Path(temporary) / "restore", {})
                launch.assert_called_once()
                validate.assert_called_once_with(33, "", "normal")
                reap.assert_called_once_with(proc)
                self.assertEqual(checks.call_args_list[0].kwargs, dict(source=False))

    def test_bounds_and_cleanup(self):
        stream = io.BytesIO()
        log = smoke.LimitedLog(stream)
        log.size = 4 * 1024 * 1024
        with self.assertRaises(ValueError):
            log.write(b"x")
        self.assertEqual(stream.getvalue(), b"")
        proc = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), returncode=0)
        channel = SimpleNamespace(
            qlog=io.BytesIO(),
            slog=io.BytesIO(),
            receive=lambda: {"QMP": {}},
            command=lambda *args: None,
            drain_serial=lambda: (_ for _ in ()).throw(ValueError("drain")),
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(smoke, "verify_images"),
            patch.object(smoke.os, "openpty", return_value=(10, 11)),
            patch.object(smoke.tty, "setraw"),
            patch.object(smoke.os, "ttyname", return_value="/dev/pts/test"),
            patch.object(smoke.os, "close") as close,
            patch.object(smoke.subprocess, "Popen", return_value=proc),
            patch.object(smoke.capture, "Channel", return_value=channel),
            patch.object(smoke.capture, "terminate", side_effect=ValueError("reap")) as terminate,
        ):
            args = SimpleNamespace(images=Path(temporary), qemu="qemu", data="", firmware=["-bios", "firmware"])
            record = {}
            with self.assertRaises(ValueError):
                with smoke.guest(args, "normal", Path(temporary) / "case", record):
                    raise ValueError("body")
            terminate.assert_called_once_with(proc)
            self.assertEqual(close.call_count, 2)
            self.assertTrue(proc.stdin.closed and proc.stdout.closed and channel.slog.closed)
            self.assertEqual(record["guest_error"], "body")
            self.assertEqual(record["cleanup_errors"], ["reap", "drain"])


if __name__ == "__main__":
    unittest.main()

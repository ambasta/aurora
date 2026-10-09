#!/usr/bin/env python3
"""Compiler-free parser, pixel, choreography and cleanup controls; never guests."""

from contextlib import contextmanager
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
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
    def test_shell_restores_shared_image(self):
        builder = """#!/usr/bin/env bash
set -eu
echo "build:$UEFI_MODE" >> events
mkdir -p build/uefi/esp/EFI/BOOT
[[ $UEFI_MODE != normal || ! -f build/uefi/graphical-console.o ]] || exit 19
[[ $UEFI_MODE == normal ]] || touch build/uefi/graphical-console.o
restoring=0
if [[ $UEFI_MODE == normal && -f first-normal ]]; then
    restoring=1
    [[ ${FAIL_RESTORE:-0} == 0 ]] || exit 29
else
    [[ $UEFI_MODE != normal ]] || touch first-normal
fi
echo "$UEFI_MODE" > build/uefi/esp/EFI/BOOT/BOOTX64.EFI
[[ ${FAIL_BUILD:-} != "$UEFI_MODE" || $restoring == 1 ]] || exit 17
if [[ ${INTERRUPT_AT:-} == "build:$UEFI_MODE" ]]; then
    kill -s "$INTERRUPT_SIGNAL" "$PPID"
    sleep 0.02
    echo 'late-builder-write' > build/uefi/esp/EFI/BOOT/BOOTX64.EFI
fi
"""
        runner = """import os, pathlib, signal, sys, time
p = pathlib.Path
args = sys.argv
if '--stage' in args:
    mode = args[args.index('--stage') + 1]
    out = p(args[args.index('--images') + 1]) / mode
    out.mkdir(parents=True)
    (out / 'image').write_bytes(p('build/uefi/esp/EFI/BOOT/BOOTX64.EFI').read_bytes())
    action = 'stage:' + mode
else:
    image = p(args[args.index('--images') + 1]) / 'normal/image'
    assert image.read_bytes() == b'normal\\n'
    action = 'guest'
with open('events', 'a') as f: f.write(action + '\\n')
if os.environ.get('INTERRUPT_AT') == action:
    os.kill(os.getppid(), getattr(signal, 'SIG' + os.environ['INTERRUPT_SIGNAL']))
    time.sleep(0.02)
    with open('events', 'a') as f: f.write('child-finished\\n')
if os.environ.get('FAIL_STAGE') == action: sys.exit(23)
if action == 'guest':
    with open('events', 'a') as f: f.write('staged-normal-boot\\n')
    sys.exit(int(os.environ.get('GUEST_STATUS', '0')))
"""
        cases = [
            ([], {}, 0),
            (["--build-only"], {}, 0),
            ([], {"FAIL_BUILD": "normal"}, 17),
            ([], {"FAIL_BUILD": "graphical-console-capture"}, 17),
            ([], {"FAIL_STAGE": "stage:graphical-console"}, 23),
            ([], {"GUEST_STATUS": "31"}, 31),
            ([], {"FAIL_RESTORE": "1"}, 29),
            ([], {"GUEST_STATUS": "31", "FAIL_RESTORE": "1"}, 31),
            (["--build-only"], {"FAIL_RESTORE": "1"}, 29),
            ([], {"FAIL_MOVE": "1"}, 37),
            ([], {"GUEST_STATUS": "31", "FAIL_MOVE": "1"}, 31),
            (["--invalid"], {}, 2),
        ]
        for path in ("build", "build/uefi", "build/graphical-smoke"):
            cases.append(([], {"SYMLINK": path}, 2))
        for action in ("build:graphical-console", "stage:graphical-console", "guest"):
            for sig, status in (("INT", 130), ("TERM", 143)):
                cases.append(([], {"INTERRUPT_AT": action, "INTERRUPT_SIGNAL": sig}, status))
        for arguments, overrides, status in cases:
            with self.subTest(arguments=arguments, overrides=overrides), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "scripts").mkdir()
                if "SYMLINK" in overrides:
                    (root / "outside").mkdir()
                    (root / "outside/sentinel").write_bytes(b"unchanged")
                    link = root / overrides["SYMLINK"]
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to(root / "outside", target_is_directory=True)
                elif arguments != ["--invalid"]:
                    (root / "build/uefi/esp/EFI/BOOT").mkdir(parents=True)
                    (root / "build/uefi/esp/EFI/BOOT/BOOTX64.EFI").write_bytes(b"previous")
                    (root / "build/uefi/graphical-console.o").touch()
                shutil.copy(ROOT / "scripts/kernel-graphical-smoke.sh", root / "scripts")
                (root / "scripts/kernel-uefi-build.sh").write_text(builder)
                (root / "scripts/kernel-uefi-build.sh").chmod(0o755)
                (root / "scripts/kernel_graphical_smoke.py").write_text(runner)
                (root / "scripts/uefi-firmware.sh").write_text(
                    "uefi_firmware_select() { UEFI_FIRMWARE_COMBINED=rom; UEFI_FIRMWARE_CODE=; UEFI_FIRMWARE_VARS=; }\n"
                )
                (root / "scripts/uefi-linker.sh").write_text("uefi_linker_select() { :; }\n")
                (root / "bin").mkdir()
                for name in ("make", "as", "ld", "objcopy", "objdump", "nm", "readelf"):
                    (root / "bin" / name).symlink_to("/bin/true")
                (root / "bin/python3").symlink_to(sys.executable)
                (root / "bin/mv").write_text(
                    "#!/usr/bin/env bash\n"
                    "if [[ ${FAIL_MOVE:-0} == 1 && ${@: -1} == */last-build ]]; then exit 37; fi\n"
                    'exec /bin/mv "$@"\n'
                )
                (root / "bin/mv").chmod(0o755)
                env = {k: v for k, v in os.environ.items() if not k.startswith("KERNEL_TEST_")}
                for name in (
                    "AURORA_TEST_CONTEXT",
                    "KERNEL_USER_PROBE_MODE",
                    "KERNEL_CONSOLE",
                    "UEFI_MODE",
                    "UEFI_CONSOLE_HANDOFF",
                ):
                    env.pop(name, None)
                env.update(
                    PATH=str(root / "bin") + os.pathsep + env["PATH"], QEMU="/bin/true", CXX="/bin/true", **overrides
                )
                result = subprocess.run(
                    ["bash", "scripts/kernel-graphical-smoke.sh", *arguments],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                if "SYMLINK" in overrides:
                    self.assertTrue(link.is_symlink())
                    self.assertEqual((root / "outside/sentinel").read_bytes(), b"unchanged")
                    self.assertFalse((root / "events").exists())
                    continue
                if arguments == ["--invalid"]:
                    self.assertFalse((root / "build").exists())
                    continue
                events = (root / "events").read_text().splitlines()
                move_failed = overrides.get("FAIL_MOVE") == "1"
                self.assertEqual(events[-1], "staged-normal-boot" if move_failed else "build:normal")
                self.assertEqual(events.count("build:normal"), 1 if move_failed else 2)
                restored = overrides.get("FAIL_RESTORE") != "1" and not move_failed
                shared = root / "build/uefi/esp/EFI/BOOT/BOOTX64.EFI"
                self.assertEqual(shared.exists() and shared.read_bytes() == b"normal\n", restored)
                self.assertEqual((root / "build/uefi/graphical-console.o").exists(), move_failed)
                self.assertEqual("PASS: shared normal" in result.stdout, restored)
                self.assertEqual("restoration exited" in result.stderr, not restored)
                self.assertEqual("staged-normal-boot" in events, "guest" in events)
                self.assertEqual(len(list((root / "build/graphical-smoke").glob("*/build-normal-restoration.log"))), 1)
                window = next((root / "build/graphical-smoke").iterdir())
                self.assertEqual((window / "previous-build/esp/EFI/BOOT/BOOTX64.EFI").read_bytes(), b"previous")
                self.assertEqual((window / "last-build/esp/EFI/BOOT/BOOTX64.EFI").is_file(), not move_failed)

    def test_primary_and_restoration_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(evidence=Path(tmp) / "new")
            with (
                patch("builtins.print"),
                patch.object(smoke, "production_case", side_effect=ValueError("primary")),
                patch.object(smoke, "restoration", side_effect=ValueError("restoration")),
            ):
                with self.assertRaisesRegex(ValueError, "primary"):
                    smoke.window(args)
            rows = json.loads((args.evidence / "summary.json").read_text())
            self.assertEqual([row["error"] for row in rows], ["ValueError: primary", "ValueError: restoration"])
            self.assertTrue(all(row["status"] == "failed" for row in rows))

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

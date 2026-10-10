#!/usr/bin/env python3
"""Compiler-free parser, pixel, choreography and cleanup controls; never guests."""

from contextlib import contextmanager
import copy
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kernel_graphical_smoke as smoke
from kernel_graphical_oracle import file_response


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
mkdir -p build/uefi/esp/EFI/BOOT build/uefi/objects
rm -f build/uefi/objects/*.{o,su,ci}
[[ $UEFI_MODE == normal ]] || touch build/uefi/objects/graphical-console.o
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
if any(flag in args for flag in ('--start-run', '--save-failure', '--finish-run')):
    sys.path.insert(0, REAL_SCRIPTS)
    import kernel_graphical_smoke as real
    real.ROOT = p.cwd()
    from unittest.mock import patch
    if '--save-failure' in args and os.environ.get('FAIL_CAPTURE'):
        if os.environ['FAIL_CAPTURE'] == 'rename':
            with patch.object(p, 'rename', side_effect=OSError('cross-device rename')): real.main()
        else:
            with patch.object(real.shutil, 'copy2', side_effect=OSError('no space left')): real.main()
    else:
        real.main()
    sys.exit()
if '--stage' in args:
    mode = args[args.index('--stage') + 1]
    out = p(args[args.index('--images') + 1]) / mode
    out.mkdir(parents=True)
    (out / 'image').write_bytes(p('build/uefi/esp/EFI/BOOT/BOOTX64.EFI').read_bytes())
    action = 'stage:' + mode
else:
    image = p(args[args.index('--images') + 1]) / 'normal/image'
    assert image.read_bytes() == b'normal\\n'
    evidence = p(args[args.index('--evidence') + 1])
    (evidence / 'production').mkdir(parents=True)
    (evidence / 'production/state-00.bin').write_bytes(b'physical capture')
    (evidence / 'production/state-00.ppm').write_bytes(b'screen capture')
    (evidence / 'production/serial.log').write_bytes(b'guest serial')
    if os.environ.get('GUEST_PIN'): (evidence.parent / '.keep').touch()
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
        runner = runner.replace("REAL_SCRIPTS", repr(str(ROOT / "scripts")))
        cases = [
            ([], {}, 0),
            ([], {"AURORA_GRAPHICAL_KEEP_RUNS": "all"}, 0),
            ([], {"GUEST_PIN": "1"}, 0),
            (["--build-only"], {}, 0),
            ([], {"FAIL_BUILD": "normal"}, 17),
            ([], {"FAIL_BUILD": "graphical-console-capture"}, 17),
            ([], {"FAIL_STAGE": "stage:graphical-console"}, 23),
            ([], {"GUEST_STATUS": "31"}, 31),
            ([], {"GUEST_STATUS": "31", "FAIL_CAPTURE": "rename"}, 31),
            ([], {"GUEST_STATUS": "31", "FAIL_CAPTURE": "copy"}, 31),
            ([], {"FAIL_RESTORE": "1"}, 29),
            ([], {"GUEST_STATUS": "31", "FAIL_RESTORE": "1"}, 31),
            (["--build-only"], {"FAIL_RESTORE": "1"}, 29),
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
                    (root / "build/uefi/legacy.o").write_bytes(b"evidence")
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
                env = {k: v for k, v in os.environ.items() if not k.startswith("KERNEL_TEST_")}
                for name in (
                    "AURORA_TEST_CONTEXT",
                    "KERNEL_USER_PROBE_MODE",
                    "KERNEL_CONSOLE",
                    "UEFI_MODE",
                    "UEFI_CONSOLE_HANDOFF",
                    "AURORA_GRAPHICAL_KEEP_RUNS",
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
                self.assertEqual(events[-1], "build:normal")
                self.assertEqual(events.count("build:normal"), 2)
                restored = overrides.get("FAIL_RESTORE") != "1"
                shared = root / "build/uefi/esp/EFI/BOOT/BOOTX64.EFI"
                self.assertEqual(shared.exists() and shared.read_bytes() == b"normal\n", restored)
                self.assertFalse((root / "build/uefi/objects/graphical-console.o").exists())
                self.assertEqual((root / "build/uefi/legacy.o").read_bytes(), b"evidence")
                self.assertEqual("PASS: shared normal" in result.stdout, restored)
                self.assertEqual("restoration exited" in result.stderr, not restored)
                self.assertEqual("staged-normal-boot" in events, "guest" in events)
                self.assertEqual(len(list((root / "build/graphical-smoke").glob("*/build-normal-restoration.log"))), 1)
                window = next((root / "build/graphical-smoke").glob("run-*"))
                if "guest" in events:
                    kept = (
                        status != 0
                        or overrides.get("AURORA_GRAPHICAL_KEEP_RUNS") == "all"
                        or overrides.get("GUEST_PIN")
                    )
                    for suffix in ("bin", "ppm"):
                        self.assertEqual((window / f"guests/production/state-00.{suffix}").exists(), bool(kept))
                    self.assertEqual((window / "guests/production/serial.log").read_bytes(), b"guest serial")
                    self.assertFalse((window / "guests/screen-captures.json").exists())
                self.assertFalse((window / "previous-build").exists())
                self.assertFalse((window / "last-build").exists())
                self.assertEqual(
                    json.loads((window / smoke.RUN_MARKER).read_text())["status"], "passed" if status == 0 else "failed"
                )
                primary_failed = status != 0 and (status != 29 or overrides.get("GUEST_STATUS") == "31")
                self.assertEqual((window / "failed-build").exists(), primary_failed)
                self.assertEqual((window / "failed-restoration").exists(), not restored)
                if overrides.get("FAIL_CAPTURE"):
                    self.assertIn("could not retain failed build", result.stderr)
                    self.assertEqual((window / "failed-build/objects").exists(), overrides["FAIL_CAPTURE"] == "copy")
                    self.assertTrue((window / "build-graphical-console-capture.log").is_file())

    def test_successful_capture_cleanup_is_scoped(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            window = root / "build/graphical-smoke/run-current"
            guests = window / "guests"
            dumps = (
                "production/state-00.bin",
                "production/state-00.ppm",
                "production/probe-00-01.bin",
                "editing/baseline.bin",
                "editing/sample-63.ppm",
                "editing/terminal.bin",
            )
            preserved = (
                "summary.json",
                "production/serial.log",
                "production/qmp.jsonl",
                "production/qemu.stderr",
                "production/review.bin",
                "review/baseline.bin",
                "production/review/terminal.bin",
                "screen-captures.json",
            )
            for name in (*dumps, *preserved):
                path = guests / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            (window / "images").mkdir()
            (window / "images/payload.bin").write_bytes(b"staged image")
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(window)
                smoke.finish_run(window, 0)
            self.assertFalse(any((guests / name).exists() for name in dumps))
            for name in preserved:
                self.assertEqual((guests / name).read_bytes(), name.encode())
            self.assertEqual((window / "images/payload.bin").read_bytes(), b"staged image")

    def test_cleanup_validates_paths_before_deletion_and_preserves_errors(self):
        for failure in ("guests-link", "case-link", "dump-link", "unlink"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                window = root / "build/graphical-smoke/run-current"
                case = window / "guests/production"
                case.mkdir(parents=True)
                outside = root / "review"
                outside.mkdir()
                (outside / "state-01.bin").write_bytes(b"review evidence")
                (case / "state-00.bin").write_bytes(b"owned capture")
                raw = case / "state-01.bin"
                if failure == "dump-link":
                    raw.symlink_to(outside / raw.name)
                else:
                    raw.write_bytes(b"owned capture")
                if failure in ("guests-link", "case-link"):
                    target = window / "guests" if failure == "guests-link" else case
                    target.rename(root / "owned")
                    target.symlink_to(outside, target_is_directory=True)
                with patch.object(smoke, "ROOT", root), patch("builtins.print") as output:
                    smoke.start_run(window)
                    if failure == "unlink":
                        with patch.object(smoke.os, "unlink", side_effect=PermissionError("read-only capture")):
                            smoke.finish_run(window, 0)
                    else:
                        smoke.finish_run(window, 0)
                    self.assertEqual(json.loads((window / smoke.RUN_MARKER).read_text())["status"], "passed")
                    self.assertTrue(
                        any(str(call.args[0]).startswith("WARN: could not discard") for call in output.call_args_list)
                    )
                self.assertEqual((outside / "state-01.bin").read_bytes(), b"review evidence")
                if failure in ("dump-link", "unlink"):
                    self.assertEqual((case / "state-00.bin").read_bytes(), b"owned capture")

    def test_late_pins_and_cleanup_interruptions_preserve_remaining_dumps(self):
        for action in ("pin-before", "pin-delete", "interrupt-before", "SIGINT", "SIGTERM"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                window = root / "build/graphical-smoke/run-current"
                case = window / "guests/production"
                case.mkdir(parents=True)
                for suffix in ("bin", "ppm"):
                    (case / ("state-00." + suffix)).write_bytes(b"capture")
                unlink = smoke.os.unlink

                def during_delete(path, *, dir_fd=None):
                    if action == "interrupt-before":
                        raise KeyboardInterrupt("before removal")
                    unlink(path, dir_fd=dir_fd)
                    if action == "pin-delete":
                        (window / ".keep").touch()
                    if action.startswith("SIG"):
                        os.kill(os.getpid(), getattr(signal, action))

                previous = signal.getsignal(signal.SIGTERM)
                try:
                    with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                        smoke.start_run(window)
                        if action == "pin-before":
                            (window / ".keep").touch()
                        with (
                            patch.object(smoke.os, "unlink", during_delete),
                            patch.object(sys, "argv", ["runner", "--finish-run", str(window), "--status", "0"]),
                        ):
                            smoke.main()
                finally:
                    signal.signal(signal.SIGTERM, previous)
                self.assertEqual(json.loads((window / smoke.RUN_MARKER).read_text())["status"], "passed")
                self.assertEqual(len(list(case.iterdir())), 2 if action in ("pin-before", "interrupt-before") else 1)
                self.assertFalse((window / "guests/screen-captures.json").exists())

    def test_cleanup_ancestor_swap_cannot_delete_outside_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            window = root / "build/graphical-smoke/run-current"
            case = window / "guests/production"
            outside = root / "outside"
            case.mkdir(parents=True)
            outside.mkdir()
            (case / "state-00.bin").write_bytes(b"owned capture")
            (outside / "state-00.bin").write_bytes(b"outside sentinel")
            original = root / "original-production"
            unlink = smoke.os.unlink

            def swap_then_unlink(name, *, dir_fd=None):
                case.rename(original)
                case.symlink_to(outside, target_is_directory=True)
                return unlink(name, dir_fd=dir_fd)

            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(window)
                with patch.object(smoke.os, "unlink", side_effect=swap_then_unlink):
                    smoke.finish_run(window, 0)
            self.assertEqual((outside / "state-00.bin").read_bytes(), b"outside sentinel")
            self.assertFalse((original / "state-00.bin").exists())
            self.assertEqual(json.loads((window / smoke.RUN_MARKER).read_text())["status"], "passed")

    def test_retention_bounds_and_preserves_unowned_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (outside / "evidence").write_text("unchanged")
            (base / "run-link").symlink_to(outside, target_is_directory=True)
            protected = ("run-legacy", "run-invalid", "run-active", "run-pinned", "run-markerlink", "run-duplicate")
            for name in protected:
                (base / name).mkdir()
                (base / name / "evidence").write_text("unchanged")
            (base / "run-invalid" / smoke.RUN_MARKER).write_text('{"status": []}')
            (base / "run-duplicate" / smoke.RUN_MARKER).write_text(
                '{"schema": "' + smoke.RUN_SCHEMA + '", "status": "running", "status": "passed", "finished_ns": 1}'
            )
            (base / "run-markerlink" / smoke.RUN_MARKER).symlink_to(outside / "evidence")
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(base / "run-active")
                smoke.start_run(base / "run-pinned")
                (base / "run-pinned/.keep").touch()
                smoke.finish_run(base / "run-pinned", 31)
                windows = []
                for index, status in enumerate((0, 31, 0, 31, 0, 31, 0, 31)):
                    folder = base / f"run-{index}"
                    folder.mkdir()
                    smoke.start_run(folder)
                    smoke.finish_run(folder, status)
                    self.assertTrue(folder.is_dir(), "the current run must survive")
                    windows.append(folder)
                self.assertEqual([p.name for p in windows if p.exists()], ["run-4", "run-5", "run-6", "run-7"])
                for name in protected:
                    self.assertEqual((base / name / "evidence").read_text(), "unchanged")
                self.assertEqual((outside / "evidence").read_text(), "unchanged")
                self.assertTrue((base / "run-link").is_symlink())

    def test_concurrent_retention_keeps_active_windows(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            with patch.object(smoke, "ROOT", root):
                for name in ("active", *map(str, range(8))):
                    folder = base / ("run-" + name)
                    folder.mkdir()
                    smoke.start_run(folder)
            command = (
                "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                "import kernel_graphical_smoke as s; s.ROOT=Path(sys.argv[2]); "
                "s.finish_run(Path(sys.argv[3]), int(sys.argv[4]))"
            )
            children = [
                subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        command,
                        str(ROOT / "scripts"),
                        str(root),
                        str(base / f"run-{i}"),
                        str(i % 2),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for i in range(8)
            ]
            for child in children:
                stdout, stderr = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, stdout + stderr)
            statuses = [json.loads(path.read_text())["status"] for path in base.glob("run-*/" + smoke.RUN_MARKER)]
            self.assertCountEqual(statuses, ["running", "passed", "passed", "failed", "failed"])
            self.assertTrue((base / "run-active").exists())

    def test_standalone_reader_pins_before_checks_and_concurrent_prune(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "1"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            old = base / "run-old"
            (old / "images").mkdir(parents=True)
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(old)
                smoke.finish_run(old, 0)
                argv = [
                    "runner",
                    "--images",
                    str(old / "images"),
                    "--evidence",
                    str(old / "guests"),
                    "qemu",
                    "firmware",
                    "",
                    "",
                    "",
                ]

                def concurrent_completion(*args):
                    new = base / "run-new"
                    new.mkdir()
                    smoke.start_run(new)
                    smoke.finish_run(new, 0)
                    self.assertTrue((old / "images").exists())
                    self.assertTrue((old / "guests").exists())

                with (
                    patch.object(sys, "argv", argv),
                    patch.object(smoke, "expected_firmware_argv", return_value=[]),
                    patch.object(
                        smoke, "verify_images", side_effect=lambda *a: self.assertTrue((old / ".keep").exists())
                    ),
                    patch.object(smoke.signal, "signal"),
                    patch.object(smoke, "CASES", []),
                    patch.object(smoke, "production_case", side_effect=concurrent_completion),
                    patch.object(smoke, "restoration"),
                ):
                    smoke.main()
                self.assertTrue((old / ".keep").exists())
                self.assertTrue((old / "guests/summary.json").exists())
                old.joinpath(".keep").unlink()  # Simulate deliberate release of this fixture's pin.
                later = base / "run-later"
                later.mkdir()
                smoke.start_run(later)
                smoke.finish_run(later, 0)
                self.assertFalse(old.exists())
                with patch.object(sys, "argv", argv), patch.object(smoke, "verify_images") as check:
                    with self.assertRaisesRegex(ValueError, "missing smoke run directory"):
                        smoke.main()
                    check.assert_not_called()

    def test_foreign_managed_images_require_an_existing_regular_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            foreign = root / "foreign/build/graphical-smoke/run-review"
            (foreign / "images").mkdir(parents=True)
            marker = foreign / smoke.RUN_MARKER
            contents = json.dumps(dict(schema=smoke.RUN_SCHEMA, status="passed", finished_ns=1))
            marker.write_text(contents)
            pin = foreign / ".keep"
            with patch.object(smoke, "ROOT", current):
                with self.assertRaisesRegex(ValueError, "owning checkout"):
                    smoke.pin_reused_images(foreign / "images")
                self.assertFalse(pin.exists())
                self.assertFalse((foreign.parent / ".retention.lock").exists())
                target = root / "ordinary-file"
                target.touch()
                pin.symlink_to(target)
                with self.assertRaisesRegex(ValueError, "owning checkout"):
                    smoke.pin_reused_images(foreign / "images")
                pin.unlink()
                pin.mkdir()
                with self.assertRaisesRegex(ValueError, "owning checkout"):
                    smoke.pin_reused_images(foreign / "images")
                pin.rmdir()
                pin.touch()
                smoke.pin_reused_images(foreign / "images")
                self.assertEqual(marker.read_text(), contents)
                self.assertFalse((foreign.parent / ".retention.lock").exists())
                marker.write_text(
                    '{"schema": "' + smoke.RUN_SCHEMA + '", "status": "running", "status": "passed", "finished_ns": 1}'
                )
                with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                    smoke.pin_reused_images(foreign / "images")
                unmanaged = root / "unmanaged/images"
                unmanaged.mkdir(parents=True)
                smoke.pin_reused_images(unmanaged)
                self.assertFalse((unmanaged.parent / ".keep").exists())

    def test_pruning_failure_warns_without_changing_execution_result(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "1"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            with patch.object(smoke, "ROOT", root), patch("builtins.print") as output:
                old = base / "run-old"
                old.mkdir()
                smoke.start_run(old)
                smoke.finish_run(old, 0)
                current = base / "run-current"
                current.mkdir()
                smoke.start_run(current)
                with patch.object(smoke.shutil, "rmtree", side_effect=PermissionError("read-only evidence")):
                    smoke.finish_run(current, 0)
                self.assertTrue(old.exists())
                self.assertTrue(current.exists())
                self.assertEqual(json.loads((current / smoke.RUN_MARKER).read_text())["status"], "passed")
                self.assertTrue(
                    any(str(call.args[0]).startswith("WARN: could not prune") for call in output.call_args_list)
                )

    def test_retention_controls_and_failure_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp, patch("builtins.print"):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            folder = base / "run-review"
            folder.mkdir()
            source = root / "build/uefi"
            (source / "objects").mkdir(parents=True)
            (source / "objects/future.o").write_text("partial object")
            (source / "payload.elf").write_text("partial link")
            (source / "unrelated.log").write_text("old evidence")
            outside = root / "outside"
            outside.write_text("unchanged")
            (source / "objects/alias.o").symlink_to(outside)
            object_inode = (source / "objects").stat().st_ino
            with patch.object(smoke, "ROOT", root), patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "all"}):
                smoke.start_run(folder)
                smoke.save_failure(folder / "failed-build")
                smoke.finish_run(folder, 31)
                self.assertTrue((folder / ".keep").is_file())
            saved = folder / "failed-build"
            self.assertFalse((source / "objects").exists())
            self.assertEqual((saved / "objects").stat().st_ino, object_inode)
            self.assertEqual((saved / "objects/future.o").read_text(), "partial object")
            self.assertEqual((saved / "payload.elf").read_text(), "partial link")
            self.assertTrue((saved / "objects/alias.o").is_symlink())
            self.assertFalse((saved / "unrelated.log").exists())
            self.assertEqual(outside.read_text(), "unchanged")
            with patch.object(smoke, "ROOT", root), patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "1"}):
                for index in range(3):
                    current = base / f"run-new{index}"
                    current.mkdir()
                    smoke.start_run(current)
                    smoke.finish_run(current, 31)
                self.assertTrue(folder.exists())
                self.assertFalse((base / "run-new0").exists())
                self.assertFalse((base / "run-new1").exists())
                self.assertTrue((base / "run-new2").exists())
            for value in ("0", "-1", "1.5", "1000", "", "ALL"):
                with patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": value}), self.assertRaises(ValueError):
                    smoke.retained_runs()

    def test_stage_copies_only_required_current_artifacts(self):
        for mode in ("normal", *smoke.admission.MODES):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                build = root / "build/uefi"
                with (
                    patch.object(smoke, "ROOT", root),
                    patch.object(smoke.admission, "BUILD", build),
                    patch.object(smoke.admission, "RECEIPT", build / "graphical-console-admission.json"),
                    patch.object(smoke.admission, "checked"),
                    patch.object(smoke.admission, "source_files", return_value=[]),
                ):
                    files = smoke.admission.build_files(mode)
                    if mode != "normal":
                        files += [
                            build / name
                            for name in (
                                "graphical-console-admission.json",
                                "graphical-console-build.json",
                                "graphical-console-build-start.json",
                            )
                        ]
                    for path in files:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("current")
                    (build / "legacy.o").write_text("unrelated")
                    (build / "historical.log").write_text("unrelated")
                    (build / "old-captures").mkdir()
                    (build / "old-captures/evidence").write_text("unrelated")
                    images = root / "images"
                    smoke.stage(mode, images)
                    args = SimpleNamespace(images=images)
                    smoke.verify_images(args, mode)
                    saved = {str(p.relative_to(images / mode)) for p in (images / mode).rglob("*") if p.is_file()}
                    self.assertEqual(saved, {str(p.relative_to(build)) for p in files} | {"smoke-image.json"})
                    (images / mode / "payload.bin").write_text("changed")
                    with self.assertRaisesRegex(ValueError, "staged image drift"):
                        smoke.verify_images(args, mode)
                    files[0].unlink()
                    with self.assertRaisesRegex(ValueError, "missing artifact"):
                        smoke.stage(mode, root / "missing")
                    files[0].symlink_to(build / "historical.log")
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        smoke.stage(mode, root / "symlink")

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
        self.assertEqual(len(smoke.CASES), 19)
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

    def test_named_file_reference_state(self):
        slots = [None] * 4
        self.assertEqual(file_response(b"ls", slots), "files: empty (RAM-only).")
        for name in (b"a", b"b", b"c", b"d"):
            self.assertEqual(
                file_response(b"write " + name + b" old suffix", slots), f"wrote {name.decode()}: 10 bytes"
            )
        saved = slots.copy()
        for command, response in (
            (b"write e x", "files: full (4 files)."),
            (b"rm note", "files: note is reserved."),
            (b"write note", "files: invalid name or content."),
            (b"cat note x", "files: invalid name or content."),
            (b"write a " + b"x" * 50, "files: invalid name or content."),
            (b"write a bad\x01", "files: invalid name or content."),
            (b"write a bad\xff", "files: invalid name or content."),
            (b"write 123456789 x", "files: invalid name or content."),
            (b"write . x", "files: invalid name or content."),
            (b"write .. x", "files: invalid name or content."),
            (b"rm a/b", "files: invalid name or content."),
            (b"ls a", "files: invalid name or content."),
            (b"cat A", "files: not found (RAM-only)."),
            (b"rm e", "files: not found (RAM-only)."),
            (b"writeX a x", "Unknown command. Type help."),
        ):
            with self.subTest(command=command):
                self.assertEqual(file_response(command, slots), response)
                self.assertEqual(slots, saved)
        self.assertEqual(file_response(b"write b X", slots), "wrote b: 1 byte")
        self.assertEqual(file_response(b"cat b", slots), "X")
        self.assertEqual(file_response(b"write b ", slots), "wrote b: 0 bytes")
        self.assertEqual(file_response(b"cat b", slots), "")
        self.assertEqual(file_response(b"rm a", slots), "files: removed (RAM-only).")
        self.assertEqual(file_response(b"write A._-0123 " + b"x" * 49, slots), "wrote A._-0123: 49 bytes")
        self.assertEqual(file_response(b"cat A._-0123", slots), "x" * 49)
        self.assertEqual(file_response(b"ls", slots), "files: A._-0123 b c d")

    def test_named_file_guest_bounds_and_semantic_pixel_mutations(self):
        baseline = b"\xa5" * smoke.SIZE
        for name, consumed, before, after, observed in (
            ("files-demo", 75, b"cat todo\n", b"cat ideas\n", b"cat todo\n"),
            ("files-capacity", 79, b"rm a\n", b"rm c\n", b"ls\n"),
        ):
            case = next(case for case in smoke.CASES if case[0] == name)
            model, _ = expected(case)
            self.assertEqual(model["completion"], 0)
            self.assertEqual(model["consumed"], consumed)
            self.assertEqual(case[2][consumed:], b"!")
            prefix = case[2][: case[2].index(observed) + len(observed)]
            changed = prefix.replace(before, after)
            self.assertNotEqual(prefix, changed)
            original = smoke.reference(smoke.byte_samples(prefix + b"exit\n"))
            mutant = smoke.reference(smoke.byte_samples(changed + b"exit\n"))
            frame = original["frames"][len(prefix)]
            wrong_frame = mutant["frames"][len(changed)]
            self.assertNotEqual(frame, wrong_frame)
            raw = bytearray(baseline)
            for row, y in enumerate(range(128, 146)):
                raw[(y * smoke.PITCH + 32) * 4 : (y * smoke.PITCH + 440) * 4] = frame[row * 1632 : (row + 1) * 1632]
            ppm = b"P6\n800 600\n255\n" + smoke.ppm_rgb(800, 600, 800, 1, raw)
            smoke.compare(baseline, raw, ppm, frame=frame)
            with self.assertRaisesRegex(ValueError, "pixels differ"):
                smoke.compare(baseline, raw, ppm, frame=wrong_frame)

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
